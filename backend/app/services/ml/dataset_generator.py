"""Synthetic Floor-Plan Dataset Generator for Ultralytics YOLO.

Renders multi-room architectural floor-plan images using the 14 canonical Furniture
Library SVG templates, real-world dimensions, structural walls, doors, and windows.
Produces mathematically exact YOLO bounding box and OBB annotations, prevents data
leakage between train/val/test splits, and auto-generates data.yaml.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from app.data.classes import (
    CANONICAL_ML_CLASSES,
    CLASS_BY_ITEM_ID,
    CLASS_NAMES,
    MLClassInfo,
    class_name_to_id,
    get_yolo_yaml_dict,
)
from app.services.coordinates import DEFAULT_MPP, mm_to_world, normalize_angle
from app.services.ml.annotation import GroundTruthAnnotation
from app.services.ml.svg_rasterizer import get_furniture_image


@dataclass
class RoomSpec:
    room_id: str
    room_name: str
    category: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    def contains_point(self, px: float, py: float) -> bool:
        return self.x0 <= px <= self.x1 and self.y0 <= py <= self.y1


class SyntheticFloorPlanGenerator:
    """Generates synthetic architectural floor plans and exact ground-truth annotations."""

    def __init__(self, mpp: float = DEFAULT_MPP) -> None:
        self.mpp = mpp  # metres per pixel; 0.01 means 1 px = 10 mm

    def mm_to_px(self, mm: float) -> float:
        return mm_to_world(mm, self.mpp)

    def generate_single_plan(
        self,
        canvas_w: int = 1024,
        canvas_h: int = 1024,
        seed: int | None = None,
        style: str = "architectural",
    ) -> tuple[Image.Image, list[GroundTruthAnnotation], list[RoomSpec], str]:
        """Generate a complete floor plan with walls, doors, windows, and placed furniture.

        Returns:
            (PIL Image, list of GroundTruthAnnotation, list of RoomSpec, layout_signature)
        """
        rng = random.Random(seed)

        # 1. Background canvas
        bg_col = (252, 250, 246) if style == "architectural" else (255, 255, 255)
        image = Image.new("RGBA", (canvas_w, canvas_h), (*bg_col, 255))
        draw = ImageDraw.Draw(image)

        # 2. Partition canvas into rooms (2x2 or 2x3 or 3x2 apartment layout)
        margin = rng.randint(40, 70)
        usable_w = canvas_w - 2 * margin
        usable_h = canvas_h - 2 * margin

        # Define 4-6 rooms (covering Bedroom 1, 2, 3, Living Room, Dining Room, Kitchen)
        split_x = margin + int(usable_w * rng.uniform(0.45, 0.55))
        split_y1 = margin + int(usable_h * rng.uniform(0.35, 0.45))
        split_y2 = margin + int(usable_h * rng.uniform(0.65, 0.75))

        room_specs = [
            RoomSpec("living_room", "Living Room", "Living Room", margin, margin, split_x, split_y1),
            RoomSpec("dining_room", "Dining Room", "Dining & Kitchen", margin, split_y1, split_x, split_y2),
            RoomSpec("kitchen", "Kitchen", "Dining & Kitchen", margin, split_y2, split_x, canvas_h - margin),
            RoomSpec("bedroom_1", "Bedroom 1", "Bedroom", split_x, margin, canvas_w - margin, split_y1),
            RoomSpec("bedroom_2", "Bedroom 2", "Bedroom", split_x, split_y1, canvas_w - margin, split_y2),
            RoomSpec("bedroom_3", "Bedroom 3", "Bedroom", split_x, split_y2, canvas_w - margin, canvas_h - margin),
        ]

        # Structural wall thickness
        wall_t = rng.randint(6, 10)
        wall_col = (20, 20, 20, 255)
        grid_col = (235, 230, 222, 255)

        # Draw subtle tile/grid lines inside rooms
        for r in room_specs:
            gw = rng.choice([40, 50, 60])
            for gx in range(int(r.x0) + gw, int(r.x1), gw):
                draw.line([(gx, r.y0), (gx, r.y1)], fill=grid_col, width=1)
            for gy in range(int(r.y0) + gw, int(r.y1), gw):
                draw.line([(r.x0, gy), (r.x1, gy)], fill=grid_col, width=1)

        # 3. Draw structural walls
        outer_box = [margin, margin, canvas_w - margin, canvas_h - margin]
        draw.rectangle(outer_box, outline=wall_col, width=wall_t + 2)

        # Internal separating walls
        draw.line([(split_x, margin), (split_x, canvas_h - margin)], fill=wall_col, width=wall_t)
        draw.line([(margin, split_y1), (split_x, split_y1)], fill=wall_col, width=wall_t)
        draw.line([(margin, split_y2), (split_x, split_y2)], fill=wall_col, width=wall_t)
        draw.line([(split_x, split_y1), (canvas_w - margin, split_y1)], fill=wall_col, width=wall_t)
        draw.line([(split_x, split_y2), (canvas_w - margin, split_y2)], fill=wall_col, width=wall_t)

        # Draw windows (cyan architectural openings) on exterior walls
        win_col = (100, 180, 210, 255)
        for r in room_specs:
            # Exterior window on left or right wall
            if r.x0 == margin:
                wy0 = r.y0 + r.h * 0.35
                draw.line([(margin, wy0), (margin, wy0 + r.h * 0.3)], fill=win_col, width=wall_t + 2)
            if r.x1 == canvas_w - margin:
                wy0 = r.y0 + r.h * 0.35
                draw.line([(canvas_w - margin, wy0), (canvas_w - margin, wy0 + r.h * 0.3)], fill=win_col, width=wall_t + 2)

        annotations: list[GroundTruthAnnotation] = []

        # 4. Place furniture items by room with exact dimensions & orientations
        for r in room_specs:
            # Room label watermark
            draw.text((r.x0 + 12, r.y0 + 12), r.room_name.upper(), fill=(180, 175, 165, 180))

            if r.category == "Bedroom":
                # Bed against a wall
                bed_info = CLASS_BY_ITEM_ID["bed"]
                bed_w_px = self.mm_to_px(bed_info.width_mm)
                bed_h_px = self.mm_to_px(bed_info.depth_mm)
                bed_rot = rng.choice([0.0, 90.0, 180.0, 270.0])

                # Position bed near center-back of room
                bcx = r.x0 + r.w * rng.uniform(0.45, 0.55)
                bcy = r.y0 + r.h * rng.uniform(0.40, 0.55)

                self._place_item(
                    image, annotations, "bed", bcx, bcy, bed_w_px, bed_h_px, bed_rot, r.room_id
                )

                # 1 or 2 side tables flanking the bed
                side_info = CLASS_BY_ITEM_ID["side-table"]
                st_w_px = self.mm_to_px(side_info.width_mm)
                st_h_px = self.mm_to_px(side_info.depth_mm)
                offset = (bed_w_px / 2.0 + st_w_px / 2.0 + 8) if bed_rot in (0.0, 180.0) else (bed_h_px / 2.0 + st_w_px / 2.0 + 8)

                if bed_rot in (0.0, 180.0):
                    self._place_item(image, annotations, "side-table", bcx - offset, bcy, st_w_px, st_h_px, 0.0, r.room_id)
                    if rng.random() > 0.3:
                        self._place_item(image, annotations, "side-table", bcx + offset, bcy, st_w_px, st_h_px, 0.0, r.room_id)
                else:
                    self._place_item(image, annotations, "side-table", bcx, bcy - offset, st_w_px, st_h_px, 0.0, r.room_id)
                    if rng.random() > 0.3:
                        self._place_item(image, annotations, "side-table", bcx, bcy + offset, st_w_px, st_h_px, 0.0, r.room_id)

                # Dressing table against wall
                if rng.random() > 0.2:
                    dt_info = CLASS_BY_ITEM_ID["dressing-table"]
                    dt_w_px = self.mm_to_px(dt_info.width_mm)
                    dt_h_px = self.mm_to_px(dt_info.depth_mm)
                    dcx = r.x1 - dt_w_px / 2.0 - 15
                    dcy = r.y0 + dt_h_px / 2.0 + 25
                    self._place_item(image, annotations, "dressing-table", dcx, dcy, dt_w_px, dt_h_px, 0.0, r.room_id)

            elif r.category == "Living Room":
                # Loungers Sofa
                sofa_info = CLASS_BY_ITEM_ID["lounger-sofa"]
                sofa_w = self.mm_to_px(sofa_info.width_mm)
                sofa_h = self.mm_to_px(sofa_info.depth_mm)
                sofa_rot = rng.choice([0.0, 90.0, 180.0, 270.0])
                scx = r.x0 + r.w * rng.uniform(0.45, 0.60)
                scy = r.y0 + r.h * rng.uniform(0.35, 0.45)
                self._place_item(image, annotations, "lounger-sofa", scx, scy, sofa_w, sofa_h, sofa_rot, r.room_id)

                # Center Table in front of sofa
                ct_info = CLASS_BY_ITEM_ID["center-table"]
                ct_w = self.mm_to_px(ct_info.width_mm)
                ct_h = self.mm_to_px(ct_info.depth_mm)
                self._place_item(image, annotations, "center-table", scx, scy + sofa_h * 0.8 + 15, ct_w, ct_h, sofa_rot, r.room_id)

                # Console against wall
                if rng.random() > 0.2:
                    c_info = CLASS_BY_ITEM_ID["console"]
                    cw = self.mm_to_px(c_info.width_mm)
                    ch = self.mm_to_px(c_info.depth_mm)
                    self._place_item(image, annotations, "console", r.x0 + cw / 2.0 + 15, r.y0 + r.h * 0.75, cw, ch, 90.0, r.room_id)

                # Partition
                if rng.random() > 0.3:
                    p_info = CLASS_BY_ITEM_ID["partition"]
                    pw = self.mm_to_px(p_info.width_mm)
                    ph = self.mm_to_px(p_info.depth_mm)
                    self._place_item(image, annotations, "partition", r.x1 - pw / 2.0 - 15, r.y0 + r.h * 0.85, pw, ph, 0.0, r.room_id)

                # Bay Window Seat
                if rng.random() > 0.4:
                    bw_info = CLASS_BY_ITEM_ID["bay-window-seat"]
                    bww = self.mm_to_px(bw_info.width_mm)
                    bwh = self.mm_to_px(bw_info.depth_mm)
                    self._place_item(image, annotations, "bay-window-seat", r.x0 + bww / 2.0 + 15, r.y0 + bwh / 2.0 + 10, bww, bwh, 0.0, r.room_id)

            elif r.room_id == "dining_room":
                # Dining Table
                dt_info = CLASS_BY_ITEM_ID["dining-table"]
                dt_w = self.mm_to_px(dt_info.width_mm)
                dt_h = self.mm_to_px(dt_info.depth_mm)
                dcx = r.x0 + r.w * 0.5
                dcy = r.y0 + r.h * 0.5
                self._place_item(image, annotations, "dining-table", dcx, dcy, dt_w, dt_h, 0.0, r.room_id)

                # 4 to 6 Dining Chairs
                chair_info = CLASS_BY_ITEM_ID["dining-chair"]
                cw = self.mm_to_px(chair_info.width_mm)
                ch = self.mm_to_px(chair_info.depth_mm)
                chair_offsets_x = [-dt_w * 0.28, dt_w * 0.28]
                for cx_off in chair_offsets_x:
                    self._place_item(image, annotations, "dining-chair", dcx + cx_off, dcy - dt_h / 2.0 - ch / 2.0 - 3, cw, ch, 180.0, r.room_id)
                    self._place_item(image, annotations, "dining-chair", dcx + cx_off, dcy + dt_h / 2.0 + ch / 2.0 + 3, cw, ch, 0.0, r.room_id)

            elif r.room_id == "kitchen":
                # Kitchen Base counter along wall
                kb_info = CLASS_BY_ITEM_ID["kitchen-base"]
                kb_w = self.mm_to_px(kb_info.width_mm)
                kb_h = self.mm_to_px(kb_info.depth_mm)
                kbcx = r.x0 + kb_w / 2.0 + 15
                kbcy = r.y1 - kb_h / 2.0 - 15
                self._place_item(image, annotations, "kitchen-base", kbcx, kbcy, kb_w, kb_h, 0.0, r.room_id)

                # Chimney above base counter
                ch_info = CLASS_BY_ITEM_ID["chimney"]
                ch_w = self.mm_to_px(ch_info.width_mm)
                ch_h = self.mm_to_px(ch_info.depth_mm)
                self._place_item(image, annotations, "chimney", kbcx, kbcy - kb_h / 2.0 - ch_h / 2.0 - 4, ch_w, ch_h, 0.0, r.room_id)

            # Place a Door for each room opening
            door_info = CLASS_BY_ITEM_ID["door"]
            dw = self.mm_to_px(door_info.width_mm)
            dh = self.mm_to_px(door_info.depth_mm)
            door_x = r.x0 + dw / 2.0 + 10
            door_y = r.y1 - dh / 2.0 - 5
            self._place_item(image, annotations, "door", door_x, door_y, dw, dh, 0.0, r.room_id)

        # Entrance Shoe Rack in first room or near door
        sr_info = CLASS_BY_ITEM_ID["shoe-rack"]
        sr_w = self.mm_to_px(sr_info.width_mm)
        sr_h = self.mm_to_px(sr_info.depth_mm)
        self._place_item(image, annotations, "shoe-rack", margin + sr_w / 2.0 + 10, margin + sr_h / 2.0 + 10, sr_w, sr_h, 0.0, "living_room")

        # Convert image to RGB for training
        rgb_image = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
        rgb_image.paste(image, mask=image.split()[3])

        # Apply slight realistic drawing noise/blur if requested
        if rng.random() > 0.5:
            rgb_image = rgb_image.filter(ImageFilter.GaussianBlur(radius=0.3))

        # Compute layout structural signature to prevent test/val leakage
        sig_items = sorted([(a.class_name, round(a.cx, -1), round(a.cy, -1)) for a in annotations])
        layout_sig = hashlib.sha256(json.dumps(sig_items).encode()).hexdigest()[:16]

        return rgb_image, annotations, room_specs, layout_sig

    def _place_item(
        self,
        canvas: Image.Image,
        annotations: list[GroundTruthAnnotation],
        item_id: str,
        cx: float,
        cy: float,
        w: float,
        h: float,
        rotation: float,
        room_id: str | None,
    ) -> None:
        """Render and alpha-composite an SVG furniture item onto the canvas and add annotation."""
        int_w = max(4, int(round(w)))
        int_h = max(4, int(round(h)))
        item_img = get_furniture_image(item_id, int_w, int_h)

        rot_deg = normalize_angle(rotation)
        if rot_deg != 0.0:
            # Rotate with transparent expansion
            rotated = item_img.rotate(-rot_deg, resample=Image.BICUBIC, expand=True)
        else:
            rotated = item_img

        # Calculate top-left for centered paste
        paste_x = int(round(cx - rotated.width / 2.0))
        paste_y = int(round(cy - rotated.height / 2.0))

        # Alpha composite onto canvas
        canvas.paste(rotated, (paste_x, paste_y), mask=rotated.split()[3])

        # Record exact annotation
        info = CLASS_BY_ITEM_ID[item_id]
        anno = GroundTruthAnnotation(
            class_id=info.class_id,
            class_name=info.class_name,
            cx=cx,
            cy=cy,
            w=w,
            h=h,
            rotation=rot_deg,
            room_id=room_id,
            confidence=1.0,
        )
        annotations.append(anno)


def generate_yolo_dataset(
    output_dir: Path,
    num_samples: int = 50,
    train_ratio: float = 0.70,
    val_ratio: float = 0.20,
    test_ratio: float = 0.10,
    canvas_size: int = 640,
    seed: int = 42,
) -> dict[str, Any]:
    """Generate a reproducible YOLO dataset with train/val/test splits and data.yaml."""
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    labels_dir = output_dir / "labels"

    for split in ("train", "val", "test"):
        (images_dir / split).mkdir(parents=True, exist_ok=True)
        (labels_dir / split).mkdir(parents=True, exist_ok=True)

    generator = SyntheticFloorPlanGenerator()
    seen_signatures: set[str] = set()

    counts = {"train": 0, "val": 0, "test": 0}
    total_annotations = 0

    rng = random.Random(seed)

    for i in range(num_samples):
        # Prevent near-identical layout leakage
        for attempt in range(10):
            sample_seed = seed + i * 100 + attempt
            img, annos, _, sig = generator.generate_single_plan(
                canvas_w=canvas_size,
                canvas_h=canvas_size,
                seed=sample_seed,
            )
            if sig not in seen_signatures or attempt == 9:
                seen_signatures.add(sig)
                break

        # Determine split based on ratios
        r = rng.random()
        if r < train_ratio:
            split = "train"
        elif r < train_ratio + val_ratio:
            split = "val"
        else:
            split = "test"

        counts[split] += 1
        sample_id = f"plan_{i:04d}"

        # Save image
        img_path = images_dir / split / f"{sample_id}.png"
        img.save(img_path, format="PNG")

        # Save YOLO labels (.txt)
        label_path = labels_dir / split / f"{sample_id}.txt"
        lines = [a.to_yolo_line(canvas_size, canvas_size) for a in annos]
        label_path.write_text("\n".join(lines), encoding="utf-8")

        # Also save YOLO OBB labels
        obb_path = labels_dir / split / f"{sample_id}_obb.txt"
        obb_lines = [a.to_yolo_obb_line(canvas_size, canvas_size) for a in annos]
        obb_path.write_text("\n".join(obb_lines), encoding="utf-8")

        total_annotations += len(annos)

    # Generate data.yaml (Phase 10)
    yaml_lines = [
        f"path: {output_dir.resolve().as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        f"nc: {len(CANONICAL_ML_CLASSES)}",
        "names:",
    ]
    for cid, cname in get_yolo_yaml_dict().items():
        yaml_lines.append(f"  {cid}: {cname}")

    data_yaml_path = output_dir / "data.yaml"
    data_yaml_path.write_text("\n".join(yaml_lines), encoding="utf-8")

    return {
        "dataset_path": str(output_dir.resolve()),
        "data_yaml": str(data_yaml_path.resolve()),
        "samples_count": counts,
        "total_samples": num_samples,
        "total_annotations": total_annotations,
        "num_classes": len(CANONICAL_ML_CLASSES),
    }


def record_failure_example(
    original_image: Image.Image | str | Path | bytes,
    predictions: list[dict[str, Any]],
    ground_truth: list[GroundTruthAnnotation | dict[str, Any]],
    failure_type: str,
    dataset_version: str = "v1.2",
    model_version: str = "mynest-yolo-v1",
    storage_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Store failure cases for future dataset retraining (Requirement 29).

    Captures: original image, prediction, ground truth/correction, failure type,
    dataset version, and model version.
    """
    import uuid
    from io import BytesIO
    from datetime import datetime, timezone
    from app.core.config import BACKEND_DIR

    target_dir = Path(storage_dir or (BACKEND_DIR / "storage" / "failure_dataset"))
    target_dir.mkdir(parents=True, exist_ok=True)

    case_id = f"failure_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    case_dir = target_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    # Save original image
    pil_img: Image.Image
    if isinstance(original_image, Image.Image):
        pil_img = original_image
    elif isinstance(original_image, bytes):
        pil_img = Image.open(BytesIO(original_image)).convert("RGB")
    else:
        pil_img = Image.open(Path(original_image)).convert("RGB")

    img_path = case_dir / "original_image.png"
    pil_img.save(img_path, format="PNG")

    # Serialize GT and predictions
    gt_serialized = [
        g.model_dump() if hasattr(g, "model_dump") else (g.__dict__ if hasattr(g, "__dict__") else g)
        for g in ground_truth
    ]

    metadata = {
        "case_id": case_id,
        "failure_type": failure_type,
        "dataset_version": dataset_version,
        "model_version": model_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "predictions": predictions,
        "ground_truth": gt_serialized,
    }

    meta_path = case_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")

    return {
        "case_id": case_id,
        "case_dir": str(case_dir.resolve()),
        "image_path": str(img_path.resolve()),
        "metadata_path": str(meta_path.resolve()),
        "failure_type": failure_type,
        "dataset_version": dataset_version,
        "model_version": model_version,
    }

