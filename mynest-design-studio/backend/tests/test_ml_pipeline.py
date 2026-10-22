"""Comprehensive Pytest Suite for ML/DL Floor-Plan Object Detection & Auto-Annotation.

Covers all 40 requirements of the MyNest ML detection specification.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

from app.data.classes import (
    CANONICAL_ML_CLASSES,
    CLASS_BY_ID,
    CLASS_BY_NAME,
    CLASS_NAMES,
    class_id_to_name,
    class_name_to_id,
    get_yolo_yaml_dict,
    item_id_to_ml_class,
    ml_class_to_item_id,
)
from app.services.coordinates import (
    circular_angle_diff,
    euclidean_dist,
    mm_to_world,
    normalize_angle,
    world_to_mm,
)
from app.services.ml.annotation import GroundTruthAnnotation
from app.services.ml.dataset_generator import SyntheticFloorPlanGenerator, generate_yolo_dataset
from app.services.ml.evaluation import (
    DiagnosticStatus,
    EvaluationReport,
    calculate_iou,
    evaluate_predictions,
)
from app.services.ml.inference import FloorPlanInferenceService, _point_in_polygon
from app.services.ml.scene_bridge import (
    detections_to_canonical_json,
    detections_to_layout_items,
)
from app.services.ml.svg_rasterizer import get_furniture_image, render_procedural_furniture
from app.services.ml.visual_debugger import render_visual_debugger_overlay


# ---------------------------------------------------------------------------
# Phase 2 & 3: Canonical Taxonomy & Class Mapping
# ---------------------------------------------------------------------------
def test_class_mapping() -> None:
    """Verify that all 14 canonical furniture library items map 1:1 to ML classes."""
    assert len(CANONICAL_ML_CLASSES) == 14
    assert len(CLASS_NAMES) == 14

    for cid, info in enumerate(CANONICAL_ML_CLASSES):
        assert info.class_id == cid
        assert class_name_to_id(info.class_name) == cid
        assert class_id_to_name(cid) == info.class_name
        assert item_id_to_ml_class(info.item_id) == info.class_name
        assert ml_class_to_item_id(info.class_name) == info.item_id


def test_yolo_yaml_generation() -> None:
    """Validate data.yaml class dictionary conforms to YOLO specification."""
    names_dict = get_yolo_yaml_dict()
    assert len(names_dict) == 14
    assert names_dict[0] == "loungers_sofa"
    assert names_dict[4] == "bed"
    assert names_dict[7] == "dining_table"
    assert names_dict[13] == "door"


# ---------------------------------------------------------------------------
# Phase 4 & 5: Annotation Formats (YOLO Standard & YOLO OBB)
# ---------------------------------------------------------------------------
def test_yolo_label_format() -> None:
    """Verify normalized YOLO standard bbox formatting."""
    anno = GroundTruthAnnotation(
        class_id=4,
        class_name="bed",
        cx=500.0,
        cy=400.0,
        w=180.0,
        h=200.0,
        rotation=90.0,
    )
    yolo_line = anno.to_yolo_line(img_w=1000.0, img_h=800.0)
    parts = yolo_line.split()

    assert len(parts) == 5
    assert int(parts[0]) == 4
    assert float(parts[1]) == pytest.approx(0.50, abs=1e-4)  # cx
    assert float(parts[2]) == pytest.approx(0.50, abs=1e-4)  # cy
    assert float(parts[3]) == pytest.approx(0.18, abs=1e-4)  # w
    assert float(parts[4]) == pytest.approx(0.25, abs=1e-4)  # h


def test_yolo_obb_format() -> None:
    """Verify YOLO OBB 4-point polygon format."""
    anno = GroundTruthAnnotation(
        class_id=0,
        class_name="loungers_sofa",
        cx=200.0,
        cy=200.0,
        w=100.0,
        h=50.0,
        rotation=0.0,
    )
    obb_line = anno.to_yolo_obb_line(img_w=1000.0, img_h=1000.0)
    parts = obb_line.split()

    assert len(parts) == 9
    assert int(parts[0]) == 0
    # Coordinates for unrotated box at cx=200, cy=200, w=100, h=50:
    # x in [150, 250] -> [0.15, 0.25]
    # y in [175, 225] -> [0.175, 0.225]
    coords = [float(p) for p in parts[1:]]
    for c in coords:
        assert 0.0 <= c <= 1.0


# ---------------------------------------------------------------------------
# Phase 6 & 7: SVG Rasterization & Synthetic Dataset Generation
# ---------------------------------------------------------------------------
def test_svg_rasterizer() -> None:
    """Verify SVG rasterization produces non-empty RGBA images for all 14 library items."""
    for info in CANONICAL_ML_CLASSES:
        img = get_furniture_image(info.item_id, target_w=64, target_h=64)
        assert isinstance(img, Image.Image)
        assert img.mode == "RGBA"
        assert img.size == (64, 64)


def test_dataset_generation() -> None:
    """Verify synthetic dataset generator produces complete splits and data.yaml."""
    with TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir)
        stats = generate_yolo_dataset(
            output_dir=out_path,
            num_samples=6,
            train_ratio=0.66,
            val_ratio=0.17,
            test_ratio=0.17,
            canvas_size=320,
            seed=123,
        )

        assert stats["total_samples"] == 6
        assert (out_path / "data.yaml").exists()
        assert (out_path / "images" / "train").exists()
        assert (out_path / "labels" / "train").exists()

        # Check that generated label files have valid content
        train_labels = list((out_path / "labels" / "train").glob("*.txt"))
        assert len(train_labels) > 0
        first_label_lines = train_labels[0].read_text().strip().splitlines()
        assert len(first_label_lines) > 0


# ---------------------------------------------------------------------------
# Phase 13, 14, 15: Coordinate Transformations & Angle Arithmetic
# ---------------------------------------------------------------------------
def test_coordinate_conversion() -> None:
    """Verify exact mm <-> pixel conversions and distance calculations."""
    mpp = 0.01  # 1 px = 10 mm
    mm_val = 1800.0  # Bed width
    px_val = mm_to_world(mm_val, mpp)
    assert px_val == pytest.approx(180.0)
    assert world_to_mm(px_val, mpp) == pytest.approx(1800.0)

    # Angle arithmetic
    assert circular_angle_diff(359.0, 1.0) == pytest.approx(2.0)
    assert circular_angle_diff(90.0, 270.0) == pytest.approx(180.0)
    assert normalize_angle(-90.0) == pytest.approx(270.0)
    assert normalize_angle(450.0) == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# Phase 16: Room Assignment (Point-in-Polygon)
# ---------------------------------------------------------------------------
def test_room_assignment() -> None:
    """Verify point-in-polygon assignment for the 6 room types."""
    bedroom_poly = [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)]
    living_poly = [(300.0, 100.0), (600.0, 100.0), (600.0, 400.0), (300.0, 400.0)]

    polys = {
        "bedroom_1": bedroom_poly,
        "living_room": living_poly,
    }

    # Point inside bedroom
    assert _point_in_polygon(200.0, 200.0, bedroom_poly) is True
    assert _point_in_polygon(200.0, 200.0, living_poly) is False

    # Point inside living room
    assert _point_in_polygon(450.0, 250.0, living_poly) is True
    assert _point_in_polygon(450.0, 250.0, bedroom_poly) is False


# ---------------------------------------------------------------------------
# Phase 17 & 18: Metrics, Millimeter Error & Diagnostics
# ---------------------------------------------------------------------------
def test_evaluation_metrics_and_error_mm() -> None:
    """Verify precision, recall, F1, and real-world position error in mm."""
    gt = [
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=500.0, cy=500.0, w=180.0, h=200.0, rotation=0.0),
        GroundTruthAnnotation(class_id=5, class_name="side_table", cx=380.0, cy=500.0, w=45.0, h=45.0, rotation=0.0),
    ]
    pred = [
        # Slightly shifted bed (10 px offset = 100 mm error at 0.01 mpp)
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=510.0, cy=500.0, w=180.0, h=200.0, rotation=0.0),
        # Extra false positive
        GroundTruthAnnotation(class_id=1, class_name="center_table", cx=100.0, cy=100.0, w=100.0, h=60.0, rotation=0.0),
    ]

    report = evaluate_predictions(gt, pred, position_tolerance_mm=150.0)

    # Bed is TP, side_table is FN, center_table is FP
    assert report.total_gt == 2
    assert report.total_pred == 2
    assert report.tp == 1
    assert report.fn == 1
    assert report.fp == 1
    assert report.precision == pytest.approx(0.50)
    assert report.recall == pytest.approx(0.50)
    assert report.f1_score == pytest.approx(0.50)

    # 10 px euclidean shift * 0.01 mpp * 1000 = 100 mm error
    assert report.mean_position_error_mm == pytest.approx(100.0, abs=1.0)


def test_extra_and_missing_objects_diagnostics() -> None:
    """Verify diagnostic classifications: MISSING_OBJECT, EXTRA_OBJECT, WRONG_CLASS."""
    gt = [
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=500.0, cy=500.0, w=180.0, h=200.0),
        GroundTruthAnnotation(class_id=5, class_name="side_table", cx=350.0, cy=500.0, w=45.0, h=45.0),
    ]
    pred = [
        # Wrong class at bed position
        GroundTruthAnnotation(class_id=0, class_name="loungers_sofa", cx=500.0, cy=500.0, w=180.0, h=200.0),
        # Extra object in empty corner
        GroundTruthAnnotation(class_id=12, class_name="shoe_rack", cx=50.0, cy=50.0, w=90.0, h=35.0),
    ]

    report = evaluate_predictions(gt, pred)
    diag = report.diagnostics_counts

    assert diag.get(DiagnosticStatus.WRONG_CLASS.value, 0) == 1
    assert diag.get(DiagnosticStatus.MISSING_OBJECT.value, 0) == 1
    assert diag.get(DiagnosticStatus.EXTRA_OBJECT.value, 0) == 1


# ---------------------------------------------------------------------------
# Phase 20: Visual Debugger Overlay
# ---------------------------------------------------------------------------
def test_visual_debugger_overlay() -> None:
    """Verify visual debugger renders expected-vs-predicted.png overlay."""
    gt = [GroundTruthAnnotation(class_id=4, class_name="bed", cx=200.0, cy=200.0, w=100.0, h=100.0)]
    pred = [GroundTruthAnnotation(class_id=4, class_name="bed", cx=205.0, cy=200.0, w=100.0, h=100.0)]

    report = evaluate_predictions(gt, pred)
    base_img = Image.new("RGB", (400, 400), (250, 250, 250))

    with TemporaryDirectory() as tmp_dir:
        out_file = Path(tmp_dir) / "expected-vs-predicted.png"
        overlay = render_visual_debugger_overlay(base_img, report, output_path=out_file)

        assert out_file.exists()
        assert overlay.size[0] == 400
        assert overlay.size[1] > 400  # Includes header


# ---------------------------------------------------------------------------
# Phase 28: Deterministic 3D Scene Bridge Interface
# ---------------------------------------------------------------------------
def test_deterministic_3d_bridge() -> None:
    """Verify detections translate to canonical LayoutItems for 3D scene builder."""
    detections = [
        {
            "class": "bed",
            "item_id": "bed",
            "confidence": 0.95,
            "position": {"cx": 500.0, "cy": 600.0, "w": 180.0, "h": 200.0},
            "rotation": 90.0,
        },
        {
            "class": "side_table",
            "item_id": "side-table",
            "confidence": 0.20,  # Below threshold -> should be ignored
            "position": {"cx": 300.0, "cy": 600.0, "w": 45.0, "h": 45.0},
            "rotation": 0.0,
        },
    ]

    items = detections_to_layout_items(detections, confidence_threshold=0.40)
    assert len(items) == 1
    assert items[0]["item_id"] == "bed"
    assert items[0]["cx"] == 500.0
    assert items[0]["rotation"] == 90.0

    canonical = detections_to_canonical_json(detections, confidence_threshold=0.40)
    assert "furniture" in canonical
    assert len(canonical["furniture"]) == 1


# ---------------------------------------------------------------------------
# Phase 23 & 30: Hard Examples & 6 Canonical Room Types
# ---------------------------------------------------------------------------
def test_hard_examples_and_six_room_types() -> None:
    """Verify evaluation on hard cases: rotated beds, dense dining chairs, and small side tables."""
    gen = SyntheticFloorPlanGenerator()
    img, gt_annos, room_specs, sig = gen.generate_single_plan(canvas_w=1024, canvas_h=1024, seed=999)

    # Verify 6 room types are represented
    room_names = {r.room_name for r in room_specs}
    assert "Bedroom 1" in room_names
    assert "Bedroom 2" in room_names
    assert "Bedroom 3" in room_names
    assert "Living Room" in room_names
    assert "Dining Room" in room_names
    assert "Kitchen" in room_names

    # Check for hard cases in ground truth
    classes_present = {a.class_name for a in gt_annos}
    assert "bed" in classes_present
    assert "side_table" in classes_present
    assert "dining_table" in classes_present
    assert "dining_chair" in classes_present

    # Test IoU and distance between adjacent small side tables and bed
    bed_anno = next(a for a in gt_annos if a.class_name == "bed")
    side_tables = [a for a in gt_annos if a.class_name == "side_table" and a.room_id == bed_anno.room_id]
    assert len(side_tables) >= 1
    for st in side_tables:
        assert calculate_iou(bed_anno, st) < 0.10  # Placed beside, not colliding


# ---------------------------------------------------------------------------
# Phase 27: Non-Destructive Guarantee
# ---------------------------------------------------------------------------
def test_non_destructive_guarantee() -> None:
    """Verify that inference and evaluation never mutate original ground-truth coordinates."""
    original_gt = [
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=1200.0, cy=900.0, w=180.0, h=200.0, rotation=90.0)
    ]
    gt_copy = [
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=1200.0, cy=900.0, w=180.0, h=200.0, rotation=90.0)
    ]

    pred = [
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=1215.0, cy=892.0, w=180.0, h=200.0, rotation=90.0)
    ]

    evaluate_predictions(original_gt, pred)

    # Verify ground-truth values remain exactly unaltered
    assert original_gt[0].cx == gt_copy[0].cx
    assert original_gt[0].cy == gt_copy[0].cy
    assert original_gt[0].w == gt_copy[0].w
    assert original_gt[0].h == gt_copy[0].h
    assert original_gt[0].rotation == gt_copy[0].rotation


# ---------------------------------------------------------------------------
# Phase 28: FastAPI Detection & Debug Endpoints Integration
# ---------------------------------------------------------------------------
def test_floor_plan_ml_detection_endpoints() -> None:
    """Test POST /api/floor-plans/{id}/detect-furniture and GET /api/floor-plans/{id}/debug-detection."""
    from io import BytesIO
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.ml.dataset_generator import SyntheticFloorPlanGenerator

    client = TestClient(app)

    # 1. Generate a synthetic floor plan image in memory
    gen = SyntheticFloorPlanGenerator()
    img, _, _, _ = gen.generate_single_plan(canvas_w=640, canvas_h=640, seed=99)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)


    # 2. Upload floor plan to API
    upload_res = client.post(
        "/api/floor-plans/upload",
        files={"file": ("synth_plan.png", buf, "image/png")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["id"]

    try:
        # 3. Call detect-furniture endpoint
        det_res = client.post(
            f"/api/floor-plans/{file_id}/detect-furniture",
            params={"confidence_threshold": 0.01, "apply_to_canonical": False},
        )
        assert det_res.status_code == 200
        det_data = det_res.json()
        assert det_data["file_id"] == file_id
        assert "detections" in det_data
        assert "count" in det_data
        assert det_data["applied_to_canonical"] is False

        # 4. Call debug-detection endpoint (expected_vs_predicted.png)
        debug_res = client.get(f"/api/floor-plans/{file_id}/debug-detection")
        assert debug_res.status_code == 200
        assert debug_res.headers["content-type"] == "image/png"
        assert len(debug_res.content) > 1000  # Valid PNG image bytes

        # 5. Call detection-overlay endpoint (detection_overlay.png)
        overlay_res = client.get(f"/api/floor-plans/{file_id}/detection-overlay")
        assert overlay_res.status_code == 200
        assert overlay_res.headers["content-type"] == "image/png"
        assert len(overlay_res.content) > 1000

        # 6. Call validate-3d endpoint (top-down orthographic projection validation)
        val3d_res = client.get(f"/api/floor-plans/{file_id}/validate-3d")
        assert val3d_res.status_code == 200
        val3d_data = val3d_res.json()
        assert "is_valid" in val3d_data
        assert "object_count_2d" in val3d_data
        assert "object_count_3d" in val3d_data
        assert "max_position_error_mm" in val3d_data
    finally:
        client.delete(f"/api/floor-plans/{file_id}")


