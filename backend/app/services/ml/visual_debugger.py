"""Visual Debugger for Floor-Plan Object Detection.

Renders color-coded diagnostic overlays on 2D floor plans:
- GREEN: Correct Detection (TP)
- RED: Missing Object (FN)
- ORANGE: Position / Size Mismatch
- YELLOW: Extra Object (FP)
- PURPLE: Wrong Class

Generates expected-vs-predicted.png with detailed class, confidence, rotation,
and millimeter error annotations.
"""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


from app.services.ml.annotation import GroundTruthAnnotation
from app.services.ml.evaluation import DiagnosticStatus, EvaluationReport

# Color palette (RGB)
STATUS_COLORS: dict[DiagnosticStatus, tuple[int, int, int]] = {
    DiagnosticStatus.CORRECT: (34, 197, 94),          # Emerald Green
    DiagnosticStatus.MISSING_OBJECT: (239, 68, 68),    # Crimson Red
    DiagnosticStatus.NOT_DETECTABLE_BY_MODEL: (156, 163, 175), # Light Gray
    DiagnosticStatus.EXTRA_OBJECT: (234, 179, 8),      # Amber Yellow
    DiagnosticStatus.WRONG_CLASS: (168, 85, 247),      # Royal Purple
    DiagnosticStatus.POSITION_MISMATCH: (249, 115, 22),# Vivid Orange
    DiagnosticStatus.SIZE_MISMATCH: (249, 115, 22),    # Vivid Orange
    DiagnosticStatus.ROTATION_MISMATCH: (249, 115, 22),# Vivid Orange
    DiagnosticStatus.DIRECTION_MISMATCH: (220, 38, 38),# Bright Crimson
    DiagnosticStatus.ROOM_MISMATCH: (234, 88, 12),     # Orange Red
    DiagnosticStatus.LOW_CONFIDENCE: (107, 114, 128),  # Neutral Gray
}


def _draw_box_with_label(
    draw: ImageDraw.ImageDraw,
    box: GroundTruthAnnotation,
    color: tuple[int, int, int],
    label_prefix: str = "",
    dash: bool = False,
    extra_tag: str = "",
) -> None:
    """Draw oriented bounding box or rect with text tag."""
    from app.services.coordinates import rotation_to_direction

    corners = box.get_rotated_corners()
    poly_pts = [(round(x), round(y)) for x, y in corners]

    # Draw polygon border
    draw.polygon(poly_pts, outline=(*color, 255), width=3)

    # Draw center dot
    draw.ellipse([box.cx - 3, box.cy - 3, box.cx + 3, box.cy + 3], fill=(*color, 255))

    # Construct label text with N/E/S/W direction
    direction = rotation_to_direction(box.rotation)
    tag = f"{label_prefix}{box.class_name} {box.rotation:.0f}° [{direction}]"
    if extra_tag:
        tag += f" {extra_tag}"
    if box.confidence < 1.0:
        tag += f" ({box.confidence:.2f})"

    tx = int(box.cx - box.w / 2.0)
    ty = max(4, int(box.cy - box.h / 2.0 - 16))

    # Background badge for text legibility
    draw.rectangle([tx - 2, ty - 2, tx + len(tag) * 7 + 4, ty + 12], fill=(*color, 240))
    draw.text((tx, ty), tag, fill=(255, 255, 255))


def render_visual_debugger_overlay(
    image_input: str | Path | bytes | Image.Image,
    report: EvaluationReport,
    output_path: str | Path | None = None,
) -> Image.Image:
    """Render full diagnostic visual debugger overlay and save expected-vs-predicted.png."""
    base_img: Image.Image
    if isinstance(image_input, Image.Image):
        base_img = image_input.copy().convert("RGB")
    elif isinstance(image_input, bytes):
        base_img = Image.open(BytesIO(image_input)).convert("RGB")
    else:
        base_img = Image.open(Path(image_input)).convert("RGB")

    w, h = base_img.size

    # Create image with header for summary metrics
    header_height = 54
    canvas = Image.new("RGB", (w, h + header_height), (24, 24, 27))
    canvas.paste(base_img, (0, header_height))

    draw = ImageDraw.Draw(canvas)

    # 1. Render summary header
    metrics_str = (
        f"EVALUATION: Precision={report.precision:.1%} | Recall={report.recall:.1%} | "
        f"F1={report.f1_score:.1%} | TP={report.tp} | FP={report.fp} | FN={report.fn} | "
        f"Pos Err={report.mean_position_error_mm}mm"
    )
    draw.text((16, 12), metrics_str, fill=(255, 255, 255))

    # Legend indicators
    legend_items = [
        ("CORRECT", STATUS_COLORS[DiagnosticStatus.CORRECT]),
        ("MISSING", STATUS_COLORS[DiagnosticStatus.MISSING_OBJECT]),
        ("EXTRA", STATUS_COLORS[DiagnosticStatus.EXTRA_OBJECT]),
        ("WRONG CLASS", STATUS_COLORS[DiagnosticStatus.WRONG_CLASS]),
        ("MISMATCH", STATUS_COLORS[DiagnosticStatus.POSITION_MISMATCH]),
        ("DIR MISMATCH", STATUS_COLORS[DiagnosticStatus.DIRECTION_MISMATCH]),
    ]
    lx = 16
    ly = 32
    for name, col in legend_items:
        draw.rectangle([lx, ly, lx + 10, ly + 10], fill=col)
        draw.text((lx + 14, ly - 1), name, fill=(200, 200, 200))
        lx += len(name) * 8 + 36

    # 2. Render each matched/unmatched item
    for match in report.matches:
        col = STATUS_COLORS.get(match.status, (200, 200, 200))

        # Render Ground Truth if missing or mismatched
        if match.status in (DiagnosticStatus.MISSING_OBJECT, DiagnosticStatus.NOT_DETECTABLE_BY_MODEL) and match.gt:
            gt_shifted = GroundTruthAnnotation(
                class_id=match.gt.class_id,
                class_name=match.gt.class_name,
                cx=match.gt.cx,
                cy=match.gt.cy + header_height,
                w=match.gt.w,
                h=match.gt.h,
                rotation=match.gt.rotation,
                confidence=match.gt.confidence,
            )
            prefix = "[NOT DETECTABLE] " if match.status == DiagnosticStatus.NOT_DETECTABLE_BY_MODEL else "[MISSING] "
            _draw_box_with_label(draw, gt_shifted, col, label_prefix=prefix)

        elif match.status == DiagnosticStatus.EXTRA_OBJECT and match.pred:
            pred_shifted = GroundTruthAnnotation(
                class_id=match.pred.class_id,
                class_name=match.pred.class_name,
                cx=match.pred.cx,
                cy=match.pred.cy + header_height,
                w=match.pred.w,
                h=match.pred.h,
                rotation=match.pred.rotation,
                confidence=match.pred.confidence,
            )
            _draw_box_with_label(draw, pred_shifted, col, label_prefix="[EXTRA] ")

        elif match.pred:
            pred_shifted = GroundTruthAnnotation(
                class_id=match.pred.class_id,
                class_name=match.pred.class_name,
                cx=match.pred.cx,
                cy=match.pred.cy + header_height,
                w=match.pred.w,
                h=match.pred.h,
                rotation=match.pred.rotation,
                confidence=match.pred.confidence,
            )
            prefix = ""
            if match.status != DiagnosticStatus.CORRECT:
                prefix = f"[{match.status.value}] "
            _draw_box_with_label(draw, pred_shifted, col, label_prefix=prefix)

            # If position mismatch, draw line connecting GT center to predicted center
            if match.gt and match.error_mm > 0.0:
                draw.line(
                    [(match.gt.cx, match.gt.cy + header_height), (match.pred.cx, match.pred.cy + header_height)],
                    fill=(249, 115, 22, 255),
                    width=2,
                )

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out, format="PNG")

    return canvas


def render_detection_overlay(
    image_input: str | Path | bytes | Image.Image,
    detections: list[dict[str, Any]],
    output_path: str | Path | None = None,
) -> Image.Image:
    """Render detection overlay with class, confidence, rotation, direction, room, and wall metrics.

    Produces detection_overlay.png.
    """
    base_img: Image.Image
    if isinstance(image_input, Image.Image):
        base_img = image_input.copy().convert("RGB")
    elif isinstance(image_input, bytes):
        base_img = Image.open(BytesIO(image_input)).convert("RGB")
    else:
        base_img = Image.open(Path(image_input)).convert("RGB")

    w, h = base_img.size
    header_height = 40
    canvas = Image.new("RGB", (w, h + header_height), (24, 24, 27))
    canvas.paste(base_img, (0, header_height))
    draw = ImageDraw.Draw(canvas)

    header_str = f"MYNEST DETECTION OVERLAY — {len(detections)} Objects Detected"
    draw.text((16, 12), header_str, fill=(255, 255, 255))

    for det in detections:
        pos = det["position"]
        cx = float(pos["cx"])
        cy = float(pos["cy"]) + header_height
        bw = float(pos["w"])
        bh = float(pos["h"])
        rot = float(det.get("rotation_deg") or 0.0)
        cname = str(det.get("class", ""))
        conf = float(det.get("class_confidence") or det.get("confidence") or 1.0)
        direction = str(det.get("direction") or "N")
        room_id = det.get("room_id") or ""
        room_side = det.get("room_side") or ""
        dist_mm = float(det.get("distance_to_wall_mm") or 0.0)
        wall_id = det.get("nearest_wall_id")

        anno = GroundTruthAnnotation(
            class_id=int(det.get("class_id") or 0),
            class_name=cname,
            cx=cx,
            cy=cy,
            w=bw,
            h=bh,
            rotation=rot,
            confidence=conf,
        )

        room_tag = f"[{room_id} : {room_side}]" if room_id else f"[{room_side}]"
        _draw_box_with_label(
            draw,
            anno,
            color=(34, 197, 94),
            extra_tag=room_tag,
        )

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out, format="PNG")

    return canvas


class VisualDebugger:
    """Convenience class for generating comparison overlays."""

    def generate_comparison_overlay(
        self,
        image_input: str | Path | Image.Image,
        ground_truth: list[GroundTruthAnnotation],
        predictions: list[GroundTruthAnnotation],
        output_path: str | Path | None = None,
    ) -> Image.Image:
        from app.services.ml.evaluation import evaluate_predictions
        report = evaluate_predictions(ground_truth, predictions)
        return render_visual_debugger_overlay(image_input, report, output_path)

    def generate_detection_overlay(
        self,
        image_input: str | Path | Image.Image,
        detections: list[dict[str, Any]],
        output_path: str | Path | None = None,
    ) -> Image.Image:
        return render_detection_overlay(image_input, detections, output_path)



