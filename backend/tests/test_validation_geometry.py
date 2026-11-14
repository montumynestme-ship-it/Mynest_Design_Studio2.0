"""Deterministic scene-vs-canonical geometry validation (spec §L)."""

import copy

from app.services import validation_service


def _canonical() -> dict:
    return {
        "furniture": [
            {"uid": "bed", "item_id": "bed", "cx": 500, "cy": 300, "w": 1800, "h": 2000, "rotation": 0},
            {"uid": "st1", "item_id": "side-table", "cx": 300, "cy": 300, "w": 450, "h": 450, "rotation": 0},
            {"uid": "sofa", "item_id": "lounger-sofa", "cx": 1500, "cy": 800, "w": 1900, "h": 900, "rotation": 90},
        ]
    }


def _scene_from(canonical: dict, *, geometry_source: str = "architectural") -> dict:
    """Build a faithful build_scene-style payload from a canonical plan."""
    furniture = copy.deepcopy(canonical["furniture"])
    for f in furniture:
        f["type"] = f["item_id"]
    return {
        "walls": [[0, 0, 2000, 0], [2000, 0, 2000, 2000]],
        "structured_walls": [{"id": "w1"}, {"id": "w2"}],
        "doors": [{"id": "d1", "x": 100, "y": 1900}],
        "windows": [{"id": "win1", "x": 500, "y": 1950}],
        "rooms": [
            {
                "label": "Bedroom 1",
                "geometry_source": geometry_source,
                "boundary": [[0, 0], [2000, 0], [2000, 2000], [0, 2000], [0, 0]],
                "doors": [{"id": "d1", "x": 100, "y": 1900}],
                "windows": [{"id": "win1", "x": 500, "y": 1950}],
                "furniture": furniture,
            }
        ],
    }


def test_faithful_scene_passes() -> None:
    c = _canonical()
    report = validation_service.validate_scene_against_canonical(c, _scene_from(c))
    assert report["geometry_faithful"] is True
    assert report["status"] == "GEOMETRY_FAITHFUL"
    assert report["mismatches"] == []


def test_missing_furniture_fails_count() -> None:
    c = _canonical()
    scene = _scene_from(c)
    scene["rooms"][0]["furniture"].pop()  # drop the sofa
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["geometry_faithful"] is False
    assert report["checks"]["furniture_count"]["passed"] is False


def test_moved_furniture_fails_transform() -> None:
    c = _canonical()
    scene = _scene_from(c)
    scene["rooms"][0]["furniture"][0]["cx"] = 9999  # move the bed
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["geometry_faithful"] is False
    assert report["checks"]["furniture_transforms"]["passed"] is False
    assert any("cx changed" in m for m in report["mismatches"])


def test_rotated_furniture_fails_transform() -> None:
    c = _canonical()
    scene = _scene_from(c)
    scene["rooms"][0]["furniture"][2]["rotation"] = 45  # was 90
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["furniture_transforms"]["passed"] is False


def test_retyped_furniture_fails_type() -> None:
    c = _canonical()
    scene = _scene_from(c)
    scene["rooms"][0]["furniture"][0]["item_id"] = "dining-table"
    scene["rooms"][0]["furniture"][0]["type"] = "dining-table"
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["furniture_types"]["passed"] is False


def test_extra_furniture_fails() -> None:
    c = _canonical()
    scene = _scene_from(c)
    scene["rooms"][0]["furniture"].append(
        {"uid": "ghost", "item_id": "console", "type": "console", "cx": 1, "cy": 1, "w": 1, "h": 1, "rotation": 0}
    )
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["geometry_faithful"] is False
    assert report["checks"]["furniture_count"]["passed"] is False


def test_architectural_room_without_boundary_fails() -> None:
    c = _canonical()
    scene = _scene_from(c)
    scene["rooms"][0]["boundary"] = []  # architectural but no polygon
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["boundaries"]["passed"] is False


def test_opening_duplicated_across_rooms_fails() -> None:
    c = _canonical()
    scene = _scene_from(c)
    # Same door id assigned to a second room = global-broadcast bug.
    scene["rooms"].append(
        {
            "label": "Bedroom 2",
            "geometry_source": "architectural",
            "boundary": [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            "doors": [{"id": "d1", "x": 100, "y": 1900}],
            "windows": [],
            "furniture": [],
        }
    )
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["doors"]["passed"] is False


def test_furniture_fallback_room_does_not_require_boundary() -> None:
    c = _canonical()
    scene = _scene_from(c, geometry_source="furniture_fallback")
    scene["rooms"][0]["boundary"] = []  # allowed for a fallback room
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["boundaries"]["passed"] is True


def test_unproven_room_fails_room_count() -> None:
    # A room whose geometry could not be proven from walls (UNCERTAIN/UNSUPPORTED)
    # must not be accepted as geometry-faithful.
    c = _canonical()
    scene = _scene_from(c)
    scene["rooms"][0]["geometry_source"] = "furniture_fallback"
    scene["rooms"][0]["validation_status"] = "UNCERTAIN"
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["room_count"]["passed"] is False
    assert report["geometry_faithful"] is False


def test_missing_walls_fails_wall_check() -> None:
    # No valid wall segments in a plan that has architecture -> walls check fails
    # (never hardcoded True).
    c = _canonical()
    scene = _scene_from(c)
    scene["walls"] = []
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["walls"]["passed"] is False


def test_zero_area_boundary_fails() -> None:
    c = _canonical()
    scene = _scene_from(c)
    # collapsed (degenerate) boundary -> zero area
    scene["rooms"][0]["boundary"] = [[0, 0], [10, 0], [20, 0], [0, 0]]
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["boundaries"]["passed"] is False


def test_furniture_assigned_to_two_rooms_fails() -> None:
    c = _canonical()
    scene = _scene_from(c)
    # duplicate the bed into a second room -> assigned twice
    dup = copy.deepcopy(scene["rooms"][0]["furniture"][0])
    scene["rooms"].append({
        "label": "Bedroom 2", "geometry_source": "architectural",
        "boundary": [[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]],
        "doors": [], "windows": [], "furniture": [dup],
    })
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["furniture_assignment"]["passed"] is False


def test_off_wall_opening_fails_when_annotated() -> None:
    c = _canonical()
    scene = _scene_from(c)
    scene["rooms"][0]["doors"][0]["on_wall"] = False
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["doors"]["passed"] is False


def test_assess_ai_render_trust_rules() -> None:
    # AIR-07: a fidelity claim must be honest — "FAITHFUL" requires INDEPENDENT output-level
    # evidence. A geometry-faithful base used as the img2img control only locks the INPUT; it
    # must NEVER by itself produce "FAITHFUL"/True. Keep FAIL / UNVERIFIED / FAITHFUL distinct.
    faithful = {"geometry_faithful": True}
    unfaithful = {"geometry_faithful": False}

    # Input locked, output NOT verified → UNVERIFIED (not True on input validity alone).
    r = validation_service.assess_ai_render(used_base_render=True, scene_report=faithful)
    assert r["geometry_status"] == "UNVERIFIED"
    assert r["geometry_faithful"] is None
    assert r["input_geometry_locked"] is True
    assert r["output_geometry_verified"] is False

    # FAITHFUL requires an output-level check (output_verified=True) on a locked base.
    rf = validation_service.assess_ai_render(
        used_base_render=True, scene_report=faithful, output_verified=True)
    assert rf["geometry_status"] == "FAITHFUL"
    assert rf["geometry_faithful"] is True

    # No base render → FAIL (uncontrolled); never trustworthy.
    rn = validation_service.assess_ai_render(used_base_render=False, scene_report=faithful)
    assert rn["geometry_status"] == "FAIL"
    assert rn["geometry_faithful"] is False

    # Base render but the base scene failed validation → FAIL (geometry was never locked).
    ru = validation_service.assess_ai_render(used_base_render=True, scene_report=unfaithful)
    assert ru["geometry_status"] == "FAIL"
    assert ru["geometry_faithful"] is False

    # Even output_verified=True cannot manufacture FAITHFUL without a locked base input.
    rx = validation_service.assess_ai_render(
        used_base_render=False, scene_report=faithful, output_verified=True)
    assert rx["geometry_status"] == "FAIL"
    assert rx["geometry_faithful"] is False
