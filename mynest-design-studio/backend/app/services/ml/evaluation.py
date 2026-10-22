"""Evaluation and Error Diagnostics Engine for Floor-Plan Object Detection.

Computes precision, recall, F1, mAP, position errors in millimeters (error_mm),
and classifies diagnostic discrepancies (MISSING_OBJECT, EXTRA_OBJECT, WRONG_CLASS,
POSITION_MISMATCH, SIZE_MISMATCH, ROTATION_MISMATCH).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.coordinates import DEFAULT_MPP, circular_angle_diff, world_to_mm
from app.services.ml.annotation import GroundTruthAnnotation


class DiagnosticStatus(str, Enum):
    CORRECT = "CORRECT"
    MISSING_OBJECT = "MISSING_OBJECT"
    NOT_DETECTABLE_BY_MODEL = "NOT_DETECTABLE_BY_MODEL"
    EXTRA_OBJECT = "EXTRA_OBJECT"
    WRONG_CLASS = "WRONG_CLASS"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    SIZE_MISMATCH = "SIZE_MISMATCH"
    ROTATION_MISMATCH = "ROTATION_MISMATCH"
    DIRECTION_MISMATCH = "DIRECTION_MISMATCH"
    ROOM_MISMATCH = "ROOM_MISMATCH"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


@dataclass
class MatchPair:
    gt: GroundTruthAnnotation | None
    pred: GroundTruthAnnotation | None
    iou: float = 0.0
    status: DiagnosticStatus = DiagnosticStatus.CORRECT
    dx_px: float = 0.0
    dy_px: float = 0.0
    euclidean_error_px: float = 0.0
    error_mm: float = 0.0
    dw_mm: float = 0.0
    dh_mm: float = 0.0
    rotation_error_deg: float = 0.0
    expected_direction: str | None = None
    predicted_direction: str | None = None
    direction_status: str = "MATCH"
    expected_room: str | None = None
    predicted_room: str | None = None
    room_status: str = "MATCH"
    nearest_wall_id: str | None = None
    wall_distance_mm: float = 0.0
    result_status: str = "PASS"  # PASS | WARNING | FAIL | REVIEW


@dataclass
class EvaluationReport:
    total_gt: int = 0
    total_pred: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    mean_position_error_mm: float = 0.0
    mean_rotation_error_deg: float = 0.0
    class_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagnostics_counts: dict[str, int] = field(default_factory=dict)
    matches: list[MatchPair] = field(default_factory=list)


def calculate_iou(box1: GroundTruthAnnotation, box2: GroundTruthAnnotation) -> float:
    """Calculate axis-aligned Intersection over Union (IoU)."""
    x1_min = box1.cx - box1.w / 2.0
    x1_max = box1.cx + box1.w / 2.0
    y1_min = box1.cy - box1.h / 2.0
    y1_max = box1.cy + box1.h / 2.0

    x2_min = box2.cx - box2.w / 2.0
    x2_max = box2.cx + box2.w / 2.0
    y2_min = box2.cy - box2.h / 2.0
    y2_max = box2.cy + box2.h / 2.0

    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)

    inter_w = max(0.0, inter_x_max - inter_x_min)
    inter_h = max(0.0, inter_y_max - inter_y_min)
    inter_area = inter_w * inter_h

    area1 = box1.w * box1.h
    area2 = box2.w * box2.h
    union_area = area1 + area2 - inter_area

    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def evaluate_predictions(
    ground_truth: list[GroundTruthAnnotation],
    predictions: list[GroundTruthAnnotation],
    iou_threshold: float = 0.40,
    position_tolerance_mm: float = 200.0,
    size_tolerance_mm: float = 300.0,
    rotation_tolerance_deg: float = 20.0,
    mpp: float = DEFAULT_MPP,
) -> EvaluationReport:
    """Evaluate predictions against ground truth using greedy bipartite matching."""
    from app.data.classes import CLASS_NAMES, CLASS_BY_NAME
    from app.services.coordinates import rotation_to_direction

    report = EvaluationReport(
        total_gt=len(ground_truth),
        total_pred=len(predictions),
    )

    if not ground_truth and not predictions:
        return report

    # Pairwise cost matrix with spatial association gating
    pos_tol_px = position_tolerance_mm / (mpp * 1000.0)
    candidates: list[tuple[float, int, int]] = []
    for g_idx, gt in enumerate(ground_truth):
        gt_extent = max(gt.w, gt.h)
        for p_idx, pred in enumerate(predictions):
            dist = math.hypot(gt.cx - pred.cx, gt.cy - pred.cy)
            iou = calculate_iou(gt, pred)

            # Spatial gating for matching:
            # - Same class: match if IoU > 0 or center distance within spatial proximity
            # - Different class: only eligible for WRONG_CLASS if overlapping (IoU > 0) or close co-location
            is_same_class = (gt.class_id == pred.class_id)
            if is_same_class:
                if iou > 0.0 or dist <= max(pos_tol_px * 2.0, gt_extent * 1.5):
                    candidates.append((dist, g_idx, p_idx))
            else:
                if iou > 0.0 or dist <= min(gt_extent * 0.75, pos_tol_px):
                    candidates.append((dist, g_idx, p_idx))

    # Sort candidates by distance
    candidates.sort(key=lambda x: x[0])

    matched_gt: set[int] = set()
    matched_pred: set[int] = set()

    for dist, g_idx, p_idx in candidates:
        if g_idx in matched_gt or p_idx in matched_pred:
            continue

        gt = ground_truth[g_idx]
        pred = predictions[p_idx]

        iou = calculate_iou(gt, pred)
        dx = pred.cx - gt.cx
        dy = pred.cy - gt.cy
        euc_px = dist
        err_mm = world_to_mm(euc_px, mpp)
        dw_mm = abs(world_to_mm(pred.w - gt.w, mpp))
        dh_mm = abs(world_to_mm(pred.h - gt.h, mpp))
        rot_err = circular_angle_diff(pred.rotation, gt.rotation)

        expected_dir = rotation_to_direction(gt.rotation)
        predicted_dir = rotation_to_direction(pred.rotation)
        dir_match = (expected_dir == predicted_dir)

        expected_room = gt.room_id
        predicted_room = pred.room_id
        room_match = (expected_room == predicted_room) if (expected_room and predicted_room) else True

        class_info = CLASS_BY_NAME.get(gt.class_name)
        has_rotation = class_info.has_meaningful_rotation if class_info else True

        # Diagnostic classification hierarchy
        if pred.class_id != gt.class_id:
            status = DiagnosticStatus.WRONG_CLASS
            res_status = "FAIL"
        elif has_rotation and not dir_match and rot_err > rotation_tolerance_deg:
            status = DiagnosticStatus.DIRECTION_MISMATCH
            res_status = "FAIL"
        elif iou < iou_threshold or err_mm > position_tolerance_mm:
            status = DiagnosticStatus.POSITION_MISMATCH
            res_status = "WARNING"
        elif max(dw_mm, dh_mm) > size_tolerance_mm:
            status = DiagnosticStatus.SIZE_MISMATCH
            res_status = "WARNING"
        elif has_rotation and rot_err > rotation_tolerance_deg:
            status = DiagnosticStatus.ROTATION_MISMATCH
            res_status = "WARNING"
        elif not room_match:
            status = DiagnosticStatus.ROOM_MISMATCH
            res_status = "WARNING"
        else:
            status = DiagnosticStatus.CORRECT
            res_status = "PASS" if pred.confidence >= 0.50 else "REVIEW"

        matched_gt.add(g_idx)
        matched_pred.add(p_idx)

        pair = MatchPair(
            gt=gt,
            pred=pred,
            iou=round(iou, 4),
            status=status,
            dx_px=round(dx, 2),
            dy_px=round(dy, 2),
            euclidean_error_px=round(euc_px, 2),
            error_mm=round(err_mm, 1),
            dw_mm=round(dw_mm, 1),
            dh_mm=round(dh_mm, 1),
            rotation_error_deg=round(rot_err, 1),
            expected_direction=expected_dir,
            predicted_direction=predicted_dir,
            direction_status="MATCH" if dir_match else "DIRECTION_MISMATCH",
            expected_room=expected_room,
            predicted_room=predicted_room,
            room_status="MATCH" if room_match else "ROOM_MISMATCH",
            nearest_wall_id=None,
            wall_distance_mm=0.0,
            result_status=res_status,
        )
        report.matches.append(pair)

    # Flag missing ground truth (False Negatives or Not Detectable)
    for g_idx in range(len(ground_truth)):
        if g_idx not in matched_gt:
            gt = ground_truth[g_idx]
            # Requirement 21: Check if class is supported by model
            if gt.class_name in CLASS_NAMES:
                status = DiagnosticStatus.MISSING_OBJECT
            else:
                status = DiagnosticStatus.NOT_DETECTABLE_BY_MODEL

            report.matches.append(
                MatchPair(
                    gt=gt,
                    pred=None,
                    iou=0.0,
                    status=status,
                    expected_direction=rotation_to_direction(gt.rotation),
                    expected_room=gt.room_id,
                    result_status="FAIL",
                )
            )

    # Flag extra predictions (False Positives)
    for p_idx in range(len(predictions)):
        if p_idx not in matched_pred:
            pred = predictions[p_idx]
            report.matches.append(
                MatchPair(
                    gt=None,
                    pred=pred,
                    iou=0.0,
                    status=DiagnosticStatus.EXTRA_OBJECT,
                    predicted_direction=rotation_to_direction(pred.rotation),
                    predicted_room=pred.room_id,
                    result_status="FAIL",
                )
            )

    # Calculate overall metrics
    tp_count = sum(1 for m in report.matches if m.status == DiagnosticStatus.CORRECT)
    fp_count = sum(1 for m in report.matches if m.status in (DiagnosticStatus.EXTRA_OBJECT, DiagnosticStatus.WRONG_CLASS))
    fn_count = sum(1 for m in report.matches if m.status == DiagnosticStatus.MISSING_OBJECT)

    report.tp = tp_count
    report.fp = fp_count
    report.fn = fn_count

    precision = tp_count / max(1, tp_count + fp_count)
    recall = tp_count / max(1, tp_count + fn_count)
    f1 = 2 * (precision * recall) / max(1e-6, precision + recall)

    report.precision = round(precision, 4)
    report.recall = round(recall, 4)
    report.f1_score = round(f1, 4)

    # Compute mean errors across matched predictions
    matched_pos_errors = [m.error_mm for m in report.matches if m.gt and m.pred]
    matched_rot_errors = [m.rotation_error_deg for m in report.matches if m.gt and m.pred]

    if matched_pos_errors:
        report.mean_position_error_mm = round(sum(matched_pos_errors) / len(matched_pos_errors), 1)
    if matched_rot_errors:
        report.mean_rotation_error_deg = round(sum(matched_rot_errors) / len(matched_rot_errors), 1)

    # Tally diagnostics counts
    counts: dict[str, int] = {}
    for m in report.matches:
        st_name = m.status.value
        counts[st_name] = counts.get(st_name, 0) + 1
    report.diagnostics_counts = counts

    return report


def format_room_summary_report(
    room_name: str,
    matches: list[MatchPair],
) -> str:
    """Format Section 37 Room Summary Report."""
    lines: list[str] = [f"ROOM: {room_name}", ""]

    room_matches = [m for m in matches if (m.expected_room == room_name or m.predicted_room == room_name)]
    if not room_matches:
        room_matches = matches  # fallback to all matches in single-room evaluations

    for idx, m in enumerate(room_matches, start=1):
        gt = m.gt
        pred = m.pred
        obj_name = (gt.class_name if gt else pred.class_name if pred else "unknown")

        exp_cls = gt.class_name if gt else "None"
        pred_cls = pred.class_name if pred else "None"

        exp_pos = f"({gt.cx:.0f}, {gt.cy:.0f})" if gt else "None"
        pred_pos = f"({pred.cx:.0f}, {pred.cy:.0f})" if pred else "None"
        pos_err = f"{m.error_mm:.1f} mm" if (gt and pred) else "N/A"

        exp_dir = m.expected_direction or "None"
        pred_dir = m.predicted_direction or "None"

        exp_rot = f"{gt.rotation:.0f}°" if gt else "None"
        pred_rot = f"{pred.rotation:.0f}°" if pred else "None"
        rot_err = f"{m.rotation_error_deg:.1f}°" if (gt and pred) else "N/A"

        exp_room = m.expected_room or "None"
        pred_room = m.predicted_room or "None"

        nearest_wall = m.nearest_wall_id or "N/A"
        wall_dist = f"{m.wall_distance_mm:.1f} mm" if m.wall_distance_mm > 0 else "N/A"

        lines.append(f"OBJECT: {obj_name}")
        lines.append(f"Expected class: {exp_cls} | Predicted class: {pred_cls}")
        lines.append(f"Expected position: {exp_pos} | Predicted position: {pred_pos} | Position error: {pos_err}")
        lines.append(f"Expected direction: {exp_dir} | Predicted direction: {pred_dir} | Direction status: {m.direction_status}")
        lines.append(f"Expected rotation: {exp_rot} | Predicted rotation: {pred_rot} | Rotation error: {rot_err}")
        lines.append(f"Expected room: {exp_room} | Predicted room: {pred_room}")
        lines.append(f"Nearest wall: {nearest_wall} | Wall distance: {wall_dist}")
        lines.append(f"Final: {m.result_status}")
        lines.append("")

    return "\n".join(lines).strip()
