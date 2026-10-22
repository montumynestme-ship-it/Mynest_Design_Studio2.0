"""100% furniture inventory preservation through the deterministic pipeline.

Invariant (this task): every canonical furniture item survives into the 3D scene
with the SAME identity, type, and room assignment — none silently dropped, merged,
duplicated, or retyped. Uses the real project floor plan + the production scene
builder and validator (never invented fixtures for the real-plan assertions).

Detection/canonical is the authoritative source in this project (the 2D editor
writes canonical furniture via save_layout), so the chain verified here is:

    canonical  ->  scene (per-room)  ->  (base render renders every item)

The base-render stage renders every scene furniture item (each kind has an
explicit 3D spec, unknown ids fall back to a generic box, and the Furniture
component has a default mesh case), and window items render as wall openings — so
no item is invisible. That rendering guarantee is a frontend invariant; here we
lock the data-level inventory that feeds it.
"""

from collections import Counter

from app.services import floor_plan_service, scene_service, validation_service

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


def _canon_and_scene():
    canonical = floor_plan_service.get_canonical(FID)
    scene = scene_service.build_scene(FID)
    scene_items = [f for r in scene.get("rooms", []) for f in r.get("furniture", [])]
    return canonical, scene, scene_items


def test_total_count_preserved():
    canonical, _scene, scene_items = _canon_and_scene()
    assert len(scene_items) == len(canonical["furniture"]) > 0


def test_every_canonical_item_present_exactly_once():
    canonical, _scene, scene_items = _canon_and_scene()
    canon_uids = Counter(str(f["uid"]) for f in canonical["furniture"])
    scene_uids = Counter(str(f["uid"]) for f in scene_items)
    dropped = set(canon_uids) - set(scene_uids)
    extra = set(scene_uids) - set(canon_uids)
    dup = [u for u, n in scene_uids.items() if n > 1]
    assert dropped == set(), f"canonical items missing from scene: {sorted(dropped)}"
    assert extra == set(), f"scene has items not in canonical: {sorted(extra)}"
    assert dup == [], f"items duplicated across rooms: {dup}"


def test_per_type_counts_preserved():
    canonical, _scene, scene_items = _canon_and_scene()
    ct = Counter(str(f["item_id"]) for f in canonical["furniture"])
    st = Counter(str(f["item_id"]) for f in scene_items)
    assert ct == st, f"per-type inventory changed: canonical={dict(ct)} scene={dict(st)}"


def test_repeated_items_remain_individual():
    # Types the reference plan repeats (e.g. 6 side-tables, 3 beds) must remain that
    # many DISTINCT items in the scene — never collapsed to a single instance.
    _canonical, _scene, scene_items = _canon_and_scene()
    st = Counter(str(f["item_id"]) for f in scene_items)
    assert st["side-table"] >= 2
    assert st["bed"] >= 2
    # each instance is a distinct uid
    st_uids = {str(f["uid"]) for f in scene_items if f["item_id"] == "side-table"}
    assert len(st_uids) == st["side-table"]


def test_every_item_assigned_to_exactly_one_room():
    canonical, scene, _ = _canon_and_scene()
    rep = validation_service.validate_scene_against_canonical(canonical, scene)
    fa = rep["checks"]["furniture_assignment"]
    assert fa["passed"] is True
    assert fa["unassigned"] == []
    assert fa["duplicated_across_rooms"] == []


def test_production_validation_furniture_checks_pass():
    canonical, scene, _ = _canon_and_scene()
    rep = validation_service.validate_scene_against_canonical(canonical, scene)
    for check in ("furniture_count", "furniture_types", "furniture_transforms",
                  "furniture_assignment"):
        assert rep["checks"][check]["passed"] is True, (check, rep["mismatches"])


def test_inventory_swap_would_be_detected():
    # Guard the guard: same COUNT but wrong inventory (a side-table replaced by a
    # console) must fail — proves the check is inventory-aware, not count-only.
    import copy
    canonical, scene, _ = _canon_and_scene()
    bad = copy.deepcopy(scene)
    for r in bad["rooms"]:
        for f in r["furniture"]:
            if f["item_id"] == "side-table":
                f["item_id"] = "console"
                f["type"] = "console"
                break
        else:
            continue
        break
    rep = validation_service.validate_scene_against_canonical(canonical, bad)
    assert rep["checks"]["furniture_types"]["passed"] is False
