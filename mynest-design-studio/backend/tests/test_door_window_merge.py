"""Door/Window MERGE (union, dedup) — deterministic backend regression.

scene_service attaches per-room supplemental_doors / supplemental_windows: the
PDF-detected openings the editor did NOT place, deduped GLOBALLY against every
room's editor openings (shared-wall doors are assigned to one room but placed in
the adjacent one). Editor placements win; supplements fill genuine gaps only.
This is additive — canonical furniture, room.doors/windows, walls, and §L
validation are unchanged.
"""

from app.services import scene_service, floor_plan_service

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


# ── Pure global-dedup logic ────────────────────────────────────────────────────

def test_global_dedup_matches_editor_in_other_room():
    # A PDF door assigned to room B, but the editor door is in room A within the
    # dedup radius → must NOT be supplemented (global dedup, not per-room).
    rooms = [
        {"label": "A", "furniture": [{"item_id": "door", "cx": 100.0, "cy": 100.0}],
         "doors": [], "windows": []},
        {"label": "B", "furniture": [],
         "doors": [{"id": "d1", "cx": 130.0, "cy": 100.0, "w": 90, "h": 40, "rotation": 0}],
         "windows": []},
    ]
    scene_service._attach_supplemental_openings(rooms)
    assert rooms[1]["supplemental_doors"] == []  # matched an editor door in room A


def test_far_opening_is_supplemented_and_geometry_preserved():
    rooms = [
        {"label": "A", "furniture": [{"item_id": "door", "cx": 100.0, "cy": 100.0}],
         "doors": [{"id": "d-far", "cx": 900.0, "cy": 900.0, "w": 95, "h": 42, "rotation": 90}],
         "windows": [{"id": "w-far", "cx": 50.0, "cy": 950.0, "w": 300, "h": 20, "rotation": 0}]},
    ]
    scene_service._attach_supplemental_openings(rooms)
    assert len(rooms[0]["supplemental_doors"]) == 1
    assert rooms[0]["supplemental_doors"][0]["w"] == 95  # geometry preserved
    assert len(rooms[0]["supplemental_windows"]) == 1


def test_editor_window_dedups_pdf_window():
    rooms = [{"label": "A",
              "furniture": [{"item_id": "window", "cx": 200.0, "cy": 50.0}],
              "doors": [],
              "windows": [{"id": "w1", "cx": 205.0, "cy": 50.0, "w": 300, "h": 20, "rotation": 0}]}]
    scene_service._attach_supplemental_openings(rooms)
    assert rooms[0]["supplemental_windows"] == []


# ── Real plan ──────────────────────────────────────────────────────────────────

def test_real_plan_supplements_exactly_the_unplaced_openings():
    scene = scene_service.build_scene(FID)
    rooms = scene["rooms"]
    ed_doors = sum(1 for r in rooms for f in r["furniture"]
                   if "door" in str(f["item_id"]) and "window" not in str(f["item_id"]))
    ed_windows = sum(1 for r in rooms for f in r["furniture"] if "window" in str(f["item_id"]))
    supp_doors = sum(len(r.get("supplemental_doors") or []) for r in rooms)
    supp_windows = sum(len(r.get("supplemental_windows") or []) for r in rooms)
    pdf_doors = sum(len(r.get("doors") or []) for r in rooms)
    pdf_windows = sum(len(r.get("windows") or []) for r in rooms)

    # editor 7 doors + 4 windows; PDF 8 doors + 5 windows → 1 door + 1 window added.
    assert (ed_doors, ed_windows) == (7, 4)
    assert (supp_doors, supp_windows) == (1, 1)
    # rendered (editor + supplemental) covers every PDF-detected opening.
    assert ed_doors + supp_doors == pdf_doors == 8
    assert ed_windows + supp_windows == pdf_windows == 5


def test_merge_is_additive_furniture_and_validation_unchanged():
    canonical = floor_plan_service.get_canonical(FID)
    scene = scene_service.build_scene(FID)
    # furniture inventory untouched (still 33 items across rooms)
    furn = [f for r in scene["rooms"] for f in r["furniture"]]
    assert len(furn) == len(canonical["furniture"]) == 33
    # supplemental items are NOT injected into furniture or room.doors/windows
    for r in scene["rooms"]:
        supp_ids = {str(o.get("id")) for o in (r.get("supplemental_doors") or [])
                    + (r.get("supplemental_windows") or [])}
        furn_uids = {str(f.get("uid")) for f in r["furniture"]}
        assert supp_ids.isdisjoint(furn_uids)
    # §L validation is UNAFFECTED by the additive supplemental keys: the furniture
    # checks (what this change must not disturb) still pass. The overall
    # geometry_faithful flag reflects pre-existing room topology (unproven/fragment
    # rooms) and is not this change's concern.
    checks = scene["geometry_validation"]["checks"]
    assert checks["furniture_count"]["passed"] is True
    assert checks["furniture_transforms"]["passed"] is True
    assert checks["furniture_assignment"]["passed"] is True
    # doors/windows checks (opening uniqueness) still pass — supplemental_* is a
    # separate render-only field, not fed into the validated doors/windows.
    assert checks["doors"]["passed"] is True
    assert checks["windows"]["passed"] is True
