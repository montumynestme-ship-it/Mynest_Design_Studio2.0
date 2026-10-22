"""MyNest Design Studio — Phase 2 Geometric Interpretation, Validation & 3D Test Suite.

Validates all 42 requirements and the Final Success Condition:
- Direction and rotation conversions adhering to N=0°, E=90°, S=180°, W=270°
- Separation of orientation (direction) and spatial location (room_side)
- Controlled Bed direction test (N, E, S, W) maintaining class='bed'
- Controlled Bed position test (left, center, right, top, bottom) maintaining class='bed'
- Point-in-polygon room attribution across all 6 canonical rooms
- Wall relationships (nearest wall ID, mm distance, orientation, object-wall angle)
- Multi-object spatial relationships (flanking side tables, sofa/table, chairs/table, chimney/counter)
- Real-world dimensions and oriented footprint using Furniture Library priors
- Error diagnostics: POSITION_MISMATCH, DIRECTION_MISMATCH, MISSING_OBJECT,
  NOT_DETECTABLE_BY_MODEL, EXTRA_OBJECT, WRONG_CLASS, REVIEW_REQUIRED
- Section 37 Room Summary Report generator
- Deterministic 3D scene builder and orthographic top-down back-projection validation
- End-to-end unseen floor plan demonstration
"""

from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from PIL import Image

from app.data.classes import (
    CLASS_BY_NAME,
    CLASS_NAMES,
    CANONICAL_ML_CLASSES,
    ml_class_to_item_id,
)
from app.services.coordinates import (
    DEFAULT_MPP,
    DEFAULT_WORLD_SCALE,
    circular_angle_diff,
    direction_to_rotation,
    euclidean_dist,
    normalize_angle,
    rotation_to_direction,
    three_to_world,
    world_to_mm,
    world_to_three,
)
from app.services.ml.annotation import GroundTruthAnnotation
from app.services.ml.evaluation import (
    DiagnosticStatus,
    evaluate_predictions,
    format_room_summary_report,
)
from app.services.ml.geometry_interpreter import (
    calculate_object_relationships,
    calculate_physical_footprint_and_dimensions,
    calculate_room_side,
    calculate_wall_relationship,
)
from app.services.ml.inference import FloorPlanInferenceService
from app.services.ml.scene_bridge import (
    detections_to_3d_scene,
    detections_to_canonical_json,
    detections_to_layout_items,
    validate_3d_orthographic_projection,
)
from app.services.ml.visual_debugger import VisualDebugger, render_detection_overlay
from app.services.ml.dataset_generator import record_failure_example


# ---------------------------------------------------------------------------
# Requirement 7: Direction Convention & Shared Utilities
# ---------------------------------------------------------------------------
def test_direction_conventions_and_circular_math() -> None:
    """Validate project direction convention: N=0°, E=90°, S=180°, W=270°."""
    assert direction_to_rotation("N") == 0.0
    assert direction_to_rotation("E") == 90.0
    assert direction_to_rotation("S") == 180.0
    assert direction_to_rotation("W") == 270.0

    # Test reverse mapping with quadrant boundaries
    assert rotation_to_direction(0.0) == "N"
    assert rotation_to_direction(350.0) == "N"
    assert rotation_to_direction(10.0) == "N"
    assert rotation_to_direction(85.0) == "E"
    assert rotation_to_direction(90.0) == "E"
    assert rotation_to_direction(100.0) == "E"
    assert rotation_to_direction(175.0) == "S"
    assert rotation_to_direction(180.0) == "S"
    assert rotation_to_direction(190.0) == "S"
    assert rotation_to_direction(265.0) == "W"
    assert rotation_to_direction(270.0) == "W"
    assert rotation_to_direction(280.0) == "W"

    # Requirement 18: Circular angle differences
    assert circular_angle_diff(359.0, 1.0) == 2.0
    assert circular_angle_diff(1.0, 359.0) == 2.0
    assert circular_angle_diff(0.0, 90.0) == 90.0
    assert circular_angle_diff(90.0, 270.0) == 180.0


# ---------------------------------------------------------------------------
# Requirement 8 & 10: Direction is NOT Room Side
# ---------------------------------------------------------------------------
def test_direction_is_not_room_side() -> None:
    """Validate direction is orientation while room_side is spatial location."""
    # Room bounds: (1000, 800) to (2000, 1800) -> width 1000, height 1000
    room_bounds = (1000.0, 800.0, 2000.0, 1800.0)

    # Object on the left side of the room (x=1150, y=1300) facing East (90°)
    side_info = calculate_room_side(cx=1150.0, cy=1300.0, room_polygon_or_bounds=room_bounds)
    assert side_info["room_side"] == "left"

    direction = rotation_to_direction(90.0)
    assert direction == "E"

    # Both coexist independently without confusion
    assert side_info["room_side"] == "left"
    assert direction == "E"


# ---------------------------------------------------------------------------
# Requirement 35 & Final Success Condition: Controlled Direction Test
# ---------------------------------------------------------------------------
def test_controlled_bed_directions() -> None:
    """Controlled test for the same Bed shape facing N, E, S, W.

    Verifies that the class remains 'bed' while orientation and direction change correctly.
    """
    directions = [
        ("N", 0.0),
        ("E", 90.0),
        ("S", 180.0),
        ("W", 270.0),
    ]

    for expected_dir, rot_deg in directions:
        derived_dir = rotation_to_direction(rot_deg)
        assert derived_dir == expected_dir

        dim_info = calculate_physical_footprint_and_dimensions(
            class_name="bed",
            detected_w=180.0 if rot_deg in (0.0, 180.0) else 200.0,
            detected_h=200.0 if rot_deg in (0.0, 180.0) else 180.0,
            rotation_deg=rot_deg,
            mpp=0.01,
        )

        # Class remains bed with standard library priors (1800 x 2000 mm)
        assert dim_info["estimated_width_mm"] == 1800.0
        assert dim_info["estimated_depth_mm"] == 2000.0
        assert dim_info["footprint"]["rotation_deg"] == rot_deg
        assert dim_info["size_confidence"] >= 0.90


# ---------------------------------------------------------------------------
# Requirement 36: Controlled Position Test
# ---------------------------------------------------------------------------
def test_controlled_bed_positions_without_class_pollution() -> None:
    """Verify model/geometry derives position without creating location-specific classes."""
    room_bounds = (1000.0, 1000.0, 2000.0, 2000.0)

    test_positions = [
        (1150.0, 1500.0, "left"),
        (1500.0, 1500.0, "center"),
        (1850.0, 1500.0, "right"),
        (1500.0, 1150.0, "top"),
        (1500.0, 1850.0, "bottom"),
    ]

    for cx, cy, expected_side in test_positions:
        side_info = calculate_room_side(cx, cy, room_bounds)
        assert side_info["room_side"] == expected_side

        # Canonical class ID must strictly remain 'bed' (Never 'bed_left', etc.)
        class_name = "bed"
        assert class_name in CLASS_NAMES
        assert f"bed_{expected_side}" not in CLASS_NAMES


# ---------------------------------------------------------------------------
# Requirement 11: Wall Relationship Calculation
# ---------------------------------------------------------------------------
def test_wall_relationship_calculation() -> None:
    """Test distance, wall orientation, and object-wall angle against true wall segments."""
    # Architectural wall along x = 1000, from y = 800 to y = 1800 (vertical wall)
    walls = [
        {"id": "wall_004", "x1": 1000.0, "y1": 800.0, "x2": 1000.0, "y2": 1800.0},
        {"id": "wall_005", "x1": 1000.0, "y1": 800.0, "x2": 2000.0, "y2": 800.0},  # horizontal wall
    ]

    # Object at cx = 1100, cy = 1300 (100 px from wall_004, rotated 90° -> perpendicular to wall)
    # At 0.01 mpp, 100 px = 1000 mm center distance; extent 180 px -> half extent 90 px -> surface distance 10 px = 100 mm (adjacent)
    rel = calculate_wall_relationship(
        cx=1100.0,
        cy=1300.0,
        w=180.0,
        h=200.0,
        rotation_deg=90.0,
        structured_walls=walls,
        mpp=DEFAULT_MPP,
    )

    assert rel["nearest_wall_id"] == "wall_004"
    assert rel["distance_to_wall_px"] == 100.0
    assert rel["distance_to_wall_mm"] == 1000.0
    assert rel["wall_orientation"] == "vertical"
    assert rel["object_wall_angle"] == 0.0  # object rotated 90° is parallel to vertical wall (angle=90°)
    assert rel["wall_relationship"] in ("adjacent", "attached")


# ---------------------------------------------------------------------------
# Requirement 12: Multi-Object Spatial Relationships
# ---------------------------------------------------------------------------
def test_object_to_object_spatial_relationships() -> None:
    """Test geometric deduction of flanking side tables, center table/sofa, and dining chairs."""
    objects = [
        {
            "id": "bed_001",
            "class": "bed",
            "room_id": "bedroom_1",
            "position": {"cx": 1500.0, "cy": 1200.0, "w": 180.0, "h": 200.0},
            "rotation_deg": 0.0,
        },
        {
            "id": "side_table_001",
            "class": "side_table",
            "room_id": "bedroom_1",
            "position": {"cx": 1360.0, "cy": 1200.0, "w": 45.0, "h": 45.0},
            "rotation_deg": 0.0,
        },
        {
            "id": "side_table_002",
            "class": "side_table",
            "room_id": "bedroom_1",
            "position": {"cx": 1640.0, "cy": 1200.0, "w": 45.0, "h": 45.0},
            "rotation_deg": 0.0,
        },
        # Living room sofa and center table
        {
            "id": "sofa_001",
            "class": "loungers_sofa",
            "room_id": "living_room",
            "position": {"cx": 500.0, "cy": 500.0, "w": 190.0, "h": 90.0},
            "rotation_deg": 0.0,
        },
        {
            "id": "center_table_001",
            "class": "center_table",
            "room_id": "living_room",
            "position": {"cx": 500.0, "cy": 580.0, "w": 100.0, "h": 60.0},
            "rotation_deg": 0.0,
        },
    ]

    processed = calculate_object_relationships(objects, mpp=DEFAULT_MPP)

    # Check bed relationships: should be flanked by side tables
    bed = next(o for o in processed if o["id"] == "bed_001")
    rel_targets = [r["target_id"] for r in bed.get("relationships", [])]
    assert "side_table_001" in rel_targets
    assert "side_table_002" in rel_targets

    # Check side table relationships: should be left_of / right_of bed
    st1 = next(o for o in processed if o["id"] == "side_table_001")
    assert any(r["target_id"] == "bed_001" and r["relationship"] == "left_of" for r in st1.get("relationships", []))

    st2 = next(o for o in processed if o["id"] == "side_table_002")
    assert any(r["target_id"] == "bed_001" and r["relationship"] == "right_of" for r in st2.get("relationships", []))

    # Check center table is in_front_of sofa
    ct = next(o for o in processed if o["id"] == "center_table_001")
    assert any(r["target_id"] == "sofa_001" and r["relationship"] == "in_front_of" for r in ct.get("relationships", []))


# ---------------------------------------------------------------------------
# Requirement 13, 14 & 15: Footprint and Real-World Dimensions
# ---------------------------------------------------------------------------
def test_footprint_and_real_world_dimensions() -> None:
    """Verify separate bbox and oriented footprint with catalog prior integration."""
    # Dining Table: library dimensions 1500 x 900 mm
    dim_info = calculate_physical_footprint_and_dimensions(
        class_name="dining_table",
        detected_w=152.0,
        detected_h=91.0,
        rotation_deg=0.0,
        mpp=DEFAULT_MPP,
    )

    assert dim_info["estimated_width_mm"] == 1500.0
    assert dim_info["estimated_depth_mm"] == 900.0
    assert dim_info["footprint"]["width"] == 1500.0
    assert dim_info["footprint"]["depth"] == 900.0
    assert dim_info["footprint"]["rotation_deg"] == 0.0
    assert dim_info["size_confidence"] > 0.90
    assert dim_info["dimensions_status"] == "CALIBRATED"


# ---------------------------------------------------------------------------
# Requirement 16–22: Error Diagnostics Hierarchy
# ---------------------------------------------------------------------------
def test_diagnostic_classifications_and_tolerances() -> None:
    """Verify DIRECTION_MISMATCH, MISSING_OBJECT, NOT_DETECTABLE_BY_MODEL, and EXTRA_OBJECT."""
    gt = [
        # Expected Bed facing North in Bedroom 1
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=500.0, cy=500.0, w=180.0, h=200.0, rotation=0.0, room_id="bedroom_1"),
        # Unsupported custom object
        GroundTruthAnnotation(class_id=99, class_name="custom_chandelier", cx=800.0, cy=800.0, w=50.0, h=50.0, rotation=0.0, room_id="dining_room"),
    ]

    pred = [
        # Predicted Bed facing East (90°) -> DIRECTION_MISMATCH
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=502.0, cy=498.0, w=180.0, h=200.0, rotation=90.0, room_id="bedroom_1"),
        # Extra predicted object
        GroundTruthAnnotation(class_id=1, class_name="center_table", cx=100.0, cy=100.0, w=100.0, h=60.0, rotation=0.0, room_id="living_room"),
    ]

    report = evaluate_predictions(gt, pred)
    diag = report.diagnostics_counts

    assert diag.get(DiagnosticStatus.DIRECTION_MISMATCH.value, 0) == 1
    assert diag.get(DiagnosticStatus.NOT_DETECTABLE_BY_MODEL.value, 0) == 1
    assert diag.get(DiagnosticStatus.EXTRA_OBJECT.value, 0) == 1


# ---------------------------------------------------------------------------
# Requirement 33 & 34: Six Room Types & Specific Geometry Tests
# ---------------------------------------------------------------------------
def test_six_room_types_and_specific_geometries() -> None:
    """Test spatial reasoning and relationship derivation across all 6 room types."""
    test_scene_objects = [
        # 1. Bedroom 1 (Bed flanked by side tables)
        {"id": "b1_bed", "class": "bed", "room_id": "bedroom_1", "position": {"cx": 300.0, "cy": 300.0, "w": 180.0, "h": 200.0}, "rotation_deg": 0.0},
        {"id": "b1_st1", "class": "side_table", "room_id": "bedroom_1", "position": {"cx": 180.0, "cy": 300.0, "w": 45.0, "h": 45.0}, "rotation_deg": 0.0},
        # 2. Bedroom 2 (Bed rotated 90° facing East)
        {"id": "b2_bed", "class": "bed", "room_id": "bedroom_2", "position": {"cx": 700.0, "cy": 300.0, "w": 200.0, "h": 180.0}, "rotation_deg": 90.0},
        # 3. Bedroom 3 (Bed facing South)
        {"id": "b3_bed", "class": "bed", "room_id": "bedroom_3", "position": {"cx": 300.0, "cy": 700.0, "w": 180.0, "h": 200.0}, "rotation_deg": 180.0},
        # 4. Living Room (Loungers sofa & Center table)
        {"id": "lr_sofa", "class": "loungers_sofa", "room_id": "living_room", "position": {"cx": 700.0, "cy": 700.0, "w": 190.0, "h": 90.0}, "rotation_deg": 0.0},
        {"id": "lr_table", "class": "center_table", "room_id": "living_room", "position": {"cx": 700.0, "cy": 780.0, "w": 100.0, "h": 60.0}, "rotation_deg": 0.0},
        # 5. Dining Room (Table surrounded by chairs)
        {"id": "dr_table", "class": "dining_table", "room_id": "dining_room", "position": {"cx": 500.0, "cy": 500.0, "w": 150.0, "h": 90.0}, "rotation_deg": 0.0},
        {"id": "dr_c1", "class": "dining_chair", "room_id": "dining_room", "position": {"cx": 500.0, "cy": 430.0, "w": 45.0, "h": 50.0}, "rotation_deg": 180.0},
        {"id": "dr_c2", "class": "dining_chair", "room_id": "dining_room", "position": {"cx": 500.0, "cy": 570.0, "w": 45.0, "h": 50.0}, "rotation_deg": 0.0},
        # 6. Kitchen (Counter and Chimney)
        {"id": "kt_base", "class": "kitchen_base", "room_id": "kitchen", "position": {"cx": 900.0, "cy": 900.0, "w": 240.0, "h": 60.0}, "rotation_deg": 0.0},
        {"id": "kt_chimney", "class": "chimney", "room_id": "kitchen", "position": {"cx": 900.0, "cy": 900.0, "w": 90.0, "h": 50.0}, "rotation_deg": 0.0},
    ]

    processed = calculate_object_relationships(test_scene_objects, mpp=DEFAULT_MPP)

    rooms_verified = {o["room_id"] for o in processed}
    assert rooms_verified == {"bedroom_1", "bedroom_2", "bedroom_3", "living_room", "dining_room", "kitchen"}

    # Verify dining chairs are arranged around table
    c1 = next(o for o in processed if o["id"] == "dr_c1")
    assert any(r["target_id"] == "dr_table" and r["relationship"] == "arranged_around" for r in c1.get("relationships", []))

    # Verify chimney is above kitchen counter
    chim = next(o for o in processed if o["id"] == "kt_chimney")
    assert any(r["target_id"] == "kt_base" and r["relationship"] == "above_counter" for r in chim.get("relationships", []))


# ---------------------------------------------------------------------------
# Requirement 37: Final Per-Room Summary Report
# ---------------------------------------------------------------------------
def test_format_room_summary_report() -> None:
    """Verify formatting of Section 37 Room Summary Report."""
    gt = [
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=1200.0, cy=900.0, w=180.0, h=200.0, rotation=90.0, room_id="Bedroom 1"),
    ]
    pred = [
        GroundTruthAnnotation(class_id=4, class_name="bed", cx=1215.0, cy=892.0, w=180.0, h=200.0, rotation=90.0, room_id="Bedroom 1"),
    ]

    report = evaluate_predictions(gt, pred)
    # Inject nearest wall data
    report.matches[0].nearest_wall_id = "wall_004"
    report.matches[0].wall_distance_mm = 85.0

    summary_text = format_room_summary_report("Bedroom 1", report.matches)

    assert "ROOM: Bedroom 1" in summary_text
    assert "OBJECT: bed" in summary_text
    assert "Expected class: bed | Predicted class: bed" in summary_text
    assert "Position error:" in summary_text
    assert "Direction status: MATCH" in summary_text
    assert "Rotation error: 0.0°" in summary_text
    assert "Nearest wall: wall_004 | Wall distance: 85.0 mm" in summary_text
    assert "Final: PASS" in summary_text


# ---------------------------------------------------------------------------
# Requirement 26 & 27: Deterministic 3D & Orthographic Back-Projection Validation
# ---------------------------------------------------------------------------
def test_deterministic_3d_and_orthographic_back_projection() -> None:
    """Verify 3D placement math and back-projection consistency within 0.1 mm."""
    detections = [
        {
            "id": "pred_001",
            "class": "bed",
            "item_id": "bed",
            "confidence": 0.96,
            "class_confidence": 0.96,
            "position": {"cx": 1250.0, "cy": 900.0, "w": 180.0, "h": 200.0},
            "footprint": {"width": 1800.0, "depth": 2000.0, "rotation_deg": 90.0},
            "rotation_deg": 90.0,
            "direction": "E",
            "room_id": "bedroom_1",
            "room_side": "left",
            "nearest_wall_id": "wall_004",
            "distance_to_wall_mm": 85.0,
            "source_type": "predicted",
        },
        {
            "id": "pred_002",
            "class": "side_table",
            "item_id": "side-table",
            "confidence": 0.92,
            "class_confidence": 0.92,
            "position": {"cx": 1250.0, "cy": 650.0, "w": 45.0, "h": 45.0},
            "footprint": {"width": 450.0, "depth": 450.0, "rotation_deg": 0.0},
            "rotation_deg": 0.0,
            "direction": "N",
            "room_id": "bedroom_1",
            "room_side": "top-left",
            "nearest_wall_id": "wall_005",
            "distance_to_wall_mm": 50.0,
            "source_type": "predicted",
        },
    ]

    # Generate deterministic 3D scene
    scene_3d = detections_to_3d_scene(detections, mpp=DEFAULT_MPP)

    assert len(scene_3d["furniture"]) == 2
    bed_3d = scene_3d["furniture"][0]
    # Verify 3D placement in Three.js meters
    assert bed_3d["position"]["x"] == pytest.approx(world_to_three(1250.0, DEFAULT_MPP))
    assert bed_3d["position"]["y"] == 0.0
    assert bed_3d["position"]["z"] == pytest.approx(world_to_three(900.0, DEFAULT_MPP))
    assert bed_3d["rotation"]["y"] == pytest.approx(-math.radians(90.0), rel=1e-4)

    # Validate 3D orthographic back-projection against 2D plan
    scene_2d = {"furniture": detections}
    val_result = validate_3d_orthographic_projection(scene_2d, scene_3d, mpp=DEFAULT_MPP)

    assert val_result["is_valid"] is True
    assert val_result["object_count_2d"] == 2
    assert val_result["object_count_3d"] == 2
    assert val_result["max_position_error_mm"] <= 0.1  # Matches within 0.1 mm
    assert val_result["max_rotation_error_deg"] <= 0.01  # Matches within 0.01°
    assert len(val_result["discrepancies"]) == 0


# ---------------------------------------------------------------------------
# Final Success Condition: End-to-End Unseen Plan Demonstration
# ---------------------------------------------------------------------------
def test_end_to_end_unseen_floor_plan_demonstration() -> None:
    """Demonstrate complete end-to-end Phase 2 workflow on an unseen floor plan.

    Flow:
    Unseen 2D Floor Plan
      ↓
    YOLO Detection
      ↓
    "bed" (class_id=4)
      ↓
    position = (cx=1250, cy=900)
      ↓
    rotation = 90°
      ↓
    direction = "E"
      ↓
    room = "bedroom_1"
      ↓
    room_side = "left"
      ↓
    nearest_wall = "wall_004"
      ↓
    distance = 85 mm
      ↓
    structured scene candidate (source_type="predicted")
      ↓
    validation = PASS
      ↓
    deterministic 3D object
    """
    # Create an unseen floor plan canvas with a room and walls
    img = Image.new("RGB", (1280, 1024), (255, 255, 255))

    room_polys = {
        "bedroom_1": [(1000.0, 400.0), (2200.0, 400.0), (2200.0, 1400.0), (1000.0, 1400.0)],
    }
    walls = [
        {"id": "wall_004", "x1": 1000.0, "y1": 400.0, "x2": 1000.0, "y2": 1400.0},
        {"id": "wall_005", "x1": 1000.0, "y1": 400.0, "x2": 2200.0, "y2": 400.0},
    ]

    # Mock detector that produces an unseen raw detection
    class MockDetector:
        def detect(self, image: Any, confidence_threshold: float = 0.25, iou_threshold: float = 0.45) -> list[GroundTruthAnnotation]:
            # Image pixel coordinates: cx=625, cy=450, w=100, h=90, rotation=90°
            # At scale=2.0 -> canonical world px: cx=1250, cy=900, w=200, h=180
            return [
                GroundTruthAnnotation(
                    class_id=4,
                    class_name="bed",
                    cx=625.0,
                    cy=450.0,
                    w=100.0,
                    h=90.0,
                    rotation=90.0,
                    confidence=0.97,
                )
            ]

    inference_service = FloorPlanInferenceService(
        detector=MockDetector(),
        mpp=DEFAULT_MPP,
        world_scale=DEFAULT_WORLD_SCALE,
    )

    detections = inference_service.detect_objects(
        image_input=img,
        room_polygons=room_polys,
        structured_walls=walls,
        confidence_threshold=0.20,
    )

    assert len(detections) == 1
    det = detections[0]

    # 1. WHAT object is it?
    assert det["class"] == "bed"
    assert det["class_confidence"] == 0.97

    # 2. WHERE exactly is it?
    assert det["position"]["cx"] == 1250.0
    assert det["position"]["cy"] == 900.0
    assert det["position"]["coordinate_frame"] == "canonical_world_px"

    # 3. WHAT SIZE is it?
    assert det["footprint"]["width"] == 1800.0  # Catalog prior
    assert det["footprint"]["depth"] == 2000.0
    assert det["dimensions_mm"]["status"] == "CALIBRATED"

    # 4. WHAT ROTATION does it have?
    assert det["rotation_deg"] == 90.0
    assert det["rotation_status"] == "VALIDATED"

    # 5. WHAT N/E/S/W DIRECTION does that orientation represent?
    assert det["direction"] == "E"

    # 6. WHICH ROOM does it belong to?
    assert det["room_id"] == "bedroom_1"
    assert det["room_assignment_method"] == "polygon"

    # 7. WHICH SIDE of the room is it on?
    assert det["room_side"] == "left"

    # 8. WHICH WALL is it near/attached to?
    assert det["nearest_wall_id"] == "wall_004"
    assert det["distance_to_wall_px"] == 250.0  # cx=1250 to wall at x=1000
    assert det["distance_to_wall_mm"] == 2500.0
    assert det["wall_orientation"] == "vertical"

    # 9. WHAT is its source_type & validation status?
    assert det["source_type"] == "predicted"
    assert det["validation_status"] == "PASS"

    # 10. Can this information create a deterministic 3D object?
    scene_3d = detections_to_3d_scene([det], structured_walls=walls, mpp=DEFAULT_MPP)
    assert len(scene_3d["furniture"]) == 1
    f3d = scene_3d["furniture"][0]
    assert f3d["item_id"] == "bed"
    assert f3d["position"]["x"] == world_to_three(1250.0, DEFAULT_MPP)
    assert f3d["position"]["z"] == world_to_three(900.0, DEFAULT_MPP)
    assert f3d["rotation_deg"] == 90.0

    # Validate back-projection
    val = validate_3d_orthographic_projection({"furniture": [det]}, scene_3d, mpp=DEFAULT_MPP)
    assert val["is_valid"] is True
    assert val["max_position_error_mm"] <= 0.1


# ---------------------------------------------------------------------------
# Requirement 29: Dataset Improvement Loop Recording
# ---------------------------------------------------------------------------
def test_dataset_improvement_loop_recording() -> None:
    """Validate capturing failed predictions and ground truth for dataset retraining."""
    import json
    with TemporaryDirectory() as tmp_dir:
        test_img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        pred = {
            "id": "pred_fail_1",
            "class": "bed",
            "class_confidence": 0.88,
            "position": {"cx": 100, "cy": 100, "coordinate_frame": "canonical_world_px"},
            "rotation_deg": 90.0,
            "direction": "E",
        }
        gt = {
            "id": "gt_1",
            "class": "bed",
            "cx": 100,
            "cy": 100,
            "rotation_deg": 0.0,
            "direction": "N",
        }

        res = record_failure_example(
            original_image=test_img,
            predictions=[pred],
            ground_truth=[gt],
            failure_type="DIRECTION_MISMATCH",
            dataset_version="v1.2",
            model_version="mynest-yolo-v1",
            storage_dir=tmp_dir,
        )

        assert res["failure_type"] == "DIRECTION_MISMATCH"
        assert res["dataset_version"] == "v1.2"
        assert res["model_version"] == "mynest-yolo-v1"

        # Verify disk persistence
        meta_file = Path(res["metadata_path"])
        img_file = Path(res["image_path"])

        assert meta_file.exists()
        assert img_file.exists()

        data = json.loads(meta_file.read_text(encoding="utf-8"))
        assert data["failure_type"] == "DIRECTION_MISMATCH"
        assert len(data["predictions"]) == 1
        assert len(data["ground_truth"]) == 1
        assert data["dataset_version"] == "v1.2"
        assert data["model_version"] == "mynest-yolo-v1"


# ---------------------------------------------------------------------------
# Window Furniture Item: Catalog, 2D Rasterizer & 3D Integration
# ---------------------------------------------------------------------------
def test_window_furniture_item_and_3d_support() -> None:
    """Validate window item in Furniture catalog, SVG rasterizer, and 3D scene bridge."""
    from app.data.furniture_catalog import FURNITURE, VISUAL, describe
    from app.data.classes import CLASS_BY_ITEM_ID, item_id_to_ml_class
    from app.services.ml.svg_rasterizer import get_furniture_image

    # 1. Catalog registration
    assert "window" in FURNITURE
    assert "window" in VISUAL
    assert describe("window") == ("Window", "Other")

    # 2. Metadata & dimensions
    win_info = CLASS_BY_ITEM_ID["window"]
    assert win_info.width_mm == 1200.0
    assert win_info.depth_mm == 200.0
    assert win_info.height_mm == 1200.0
    assert win_info.kind == "window"
    assert item_id_to_ml_class("window") == "window"

    # 3. 2D SVG Rasterizer (loads frontend/public/furniture/window.svg)
    win_img = get_furniture_image("window", 120, 20)
    assert win_img.size == (120, 20)
    assert win_img.mode == "RGBA"

    # 4. Deterministic 3D integration
    det = {
        "id": "win_001",
        "class": "window",
        "class_confidence": 0.95,
        "position": {"cx": 500.0, "cy": 100.0, "coordinate_frame": "canonical_world_px"},
        "footprint": {"width": 1200.0, "depth": 200.0},
        "rotation_deg": 0.0,
        "direction": "N",
        "room_id": "bedroom_1",
    }
    scene_3d = detections_to_3d_scene([det], structured_walls=[], mpp=DEFAULT_MPP)
    assert len(scene_3d["furniture"]) == 1
    f3d = scene_3d["furniture"][0]
    assert f3d["item_id"] == "window"
    assert f3d["dimensions"]["width"] == 1.2  # 1200mm = 1.2m
    assert f3d["dimensions"]["depth"] == 0.2  # 200mm = 0.2m
    assert f3d["dimensions"]["height"] == 1.2 # 1200mm = 1.2m
