"""Deterministic authoritative-2D → 3D conversion fidelity gate.

The authoritative 2D design is the SOURCE OF TRUTH; the deterministic 3D scene must
reproduce it object-for-object. `validation_service.validate_2d_to_3d` enforces, for
every furniture item (uid → exactly one 3D object, same uid), that uid / type /
position / dimensions / rotation / scale / room assignment / count are unchanged
within tolerance (no missing, no extra, no duplicate uid), and for doors / windows /
walls that identity, wall association, offset, dimensions, orientation and geometry
are unchanged (no missing / extra openings, no altered walls).

On failure the gate returns a STRUCTURED result and the generation pipeline refuses
BEFORE any base render / fal call — it never auto-corrects, invents, or moves objects.

The 12 synthetic cases drive the pure comparator with id-aligned structures; the
integration tests prove the real scene passes and that generation refuses on failure
without calling the provider.
"""

from unittest import mock

from fastapi.testclient import TestClient

from app.services import floor_plan_service, generation_service, scene_service
from app.services import validation_service as vs
from app.services.ai import registry
from app.services.ai.mock_adapter import MockAdapter

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


# ── builders for an id-aligned authoritative-2D / 3D pair ───────────────────────
def _furn(uid, type="bed", room="room-1", cx=500.0, cy=350.0, w=1800.0, h=2000.0,
          rotation=0.0, scale=1.0):
    return {"uid": uid, "item_id": type, "room": room, "cx": cx, "cy": cy,
            "w": w, "h": h, "rotation": rotation, "scale": scale}


def _door(id="door-1", wall_id="w1", offset=100.0, w=900.0, h=50.0, rotation=0.0):
    return {"id": id, "wall_id": wall_id, "offset": offset, "w": w, "h": h, "rotation": rotation}


def _window(id="win-1", wall_id="w2", offset=200.0, w=1200.0, h=40.0, rotation=90.0):
    return {"id": id, "wall_id": wall_id, "offset": offset, "w": w, "h": h, "rotation": rotation}


def _wall(id="w1", x1=0.0, y1=0.0, x2=1000.0, y2=0.0, room="room-1"):
    return {"id": id, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "room": room}


def _design():
    """A canonical matching authoritative-2D / 3D design (deep-copied per side)."""
    import copy
    base = {
        "furniture": [_furn("f-1", "bed", cx=500, cy=350),
                      _furn("f-2", "sofa", room="room-2", cx=1200, cy=800)],
        "doors": [_door("door-1"), _door("door-2", wall_id="w3", offset=300)],
        "windows": [_window("win-1"), _window("win-2", wall_id="w4", offset=150)],
        "walls": [_wall("w1"), _wall("w2", x1=0, y1=0, x2=0, y2=800, room="room-2")],
    }
    return copy.deepcopy(base), copy.deepcopy(base)


def _cats(report):
    return {m["category"] for m in report["mismatches"]}


# ── 1. exact match → PASS ───────────────────────────────────────────────────────
def test_01_exact_match_passes():
    exp, act = _design()
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is True
    assert rep["status"] == "SCENE_FAITHFUL"
    assert rep["mismatches"] == []


# ── 2. furniture moved → FAIL ───────────────────────────────────────────────────
def test_02_furniture_moved_fails():
    exp, act = _design()
    act["furniture"][0]["cx"] += 50.0
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "FURNITURE_MOVED" in _cats(rep)


# ── 3. furniture rotated → FAIL ─────────────────────────────────────────────────
def test_03_furniture_rotated_fails():
    exp, act = _design()
    act["furniture"][0]["rotation"] = 90.0
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "FURNITURE_ROTATED" in _cats(rep)


# ── 4. furniture resized → FAIL ─────────────────────────────────────────────────
def test_04_furniture_resized_fails():
    exp, act = _design()
    act["furniture"][0]["w"] += 100.0
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "FURNITURE_RESIZED" in _cats(rep)


# ── 5. missing furniture → FAIL ─────────────────────────────────────────────────
def test_05_missing_furniture_fails():
    exp, act = _design()
    act["furniture"] = [act["furniture"][0]]  # drop f-2
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False
    assert "FURNITURE_MISSING" in _cats(rep)
    assert any(m["id"] == "f-2" for m in rep["mismatches"] if m["category"] == "FURNITURE_MISSING")


# ── 6. extra furniture → FAIL ───────────────────────────────────────────────────
def test_06_extra_furniture_fails():
    exp, act = _design()
    act["furniture"].append(_furn("f-99", "lamp", cx=10, cy=10))
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "FURNITURE_EXTRA" in _cats(rep)


# ── 7. wrong room → FAIL ────────────────────────────────────────────────────────
def test_07_wrong_room_fails():
    exp, act = _design()
    act["furniture"][0]["room"] = "room-9"
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "FURNITURE_WRONG_ROOM" in _cats(rep)


# ── 8. duplicate UID → FAIL ─────────────────────────────────────────────────────
def test_08_duplicate_uid_fails():
    exp, act = _design()
    # Same uid mapped to two distinct 3D objects (violates uid → exactly one object).
    act["furniture"].append(_furn("f-1", "bed", cx=500, cy=350))
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "FURNITURE_DUPLICATE_UID" in _cats(rep)


# ── 9. missing door → FAIL ──────────────────────────────────────────────────────
def test_09_missing_door_fails():
    exp, act = _design()
    act["doors"] = [act["doors"][0]]  # drop door-2
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "DOOR_MISSING" in _cats(rep)


# ── 10. extra door → FAIL ───────────────────────────────────────────────────────
def test_10_extra_door_fails():
    exp, act = _design()
    act["doors"].append(_door("door-99", wall_id="w1", offset=700))
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "DOOR_EXTRA" in _cats(rep)


# ── 11. moved window → FAIL ─────────────────────────────────────────────────────
def test_11_moved_window_fails():
    exp, act = _design()
    act["windows"][0]["offset"] += 75.0  # slid along its wall
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "WINDOW_MOVED" in _cats(rep)


# ── 12. changed wall geometry → FAIL ────────────────────────────────────────────
def test_12_changed_wall_geometry_fails():
    exp, act = _design()
    act["walls"][0]["x2"] += 120.0  # wall endpoint moved
    rep = vs.validate_2d_to_3d(exp, act)
    assert rep["passed"] is False and "WALL_GEOMETRY" in _cats(rep)


# ── bonus: window wall-association + door reorientation are caught ───────────────
def test_window_wall_reassignment_and_door_reorientation_fail():
    exp, act = _design()
    act["windows"][0]["wall_id"] = "w-other"
    act["doors"][0]["rotation"] = 45.0
    rep = vs.validate_2d_to_3d(exp, act)
    cats = _cats(rep)
    assert "WINDOW_WALL_CHANGED" in cats and "DOOR_REORIENTED" in cats


# ── integration: the real deterministic scene is faithful (no false positives) ──
def test_real_scene_is_faithful():
    canonical = floor_plan_service.get_canonical(FID)
    scene = scene_service.build_scene(FID, canonical=canonical)
    rep = vs.validate_scene_2d_to_3d(canonical, scene)
    assert rep["passed"] is True, rep["mismatches"][:10]
    assert rep["counts"]["furniture"]["expected"] == rep["counts"]["furniture"]["actual"]


# ── integration: a failed gate refuses generation with NO provider call ─────────
def test_generation_refused_on_gate_failure_without_provider_call():
    from app.main import app

    calls = {"n": 0}

    class ImgAdapter(MockAdapter):
        name = "nvidia"
        model = "black-forest-labs/flux.1-dev"
        supports_control_image = True  # img2img → the 2D→3D gate runs before render

        def generate(self, request):
            calls["n"] += 1
            return super().generate(request)

    failed_report = {
        "passed": False, "status": "SCENE_VALIDATION_FAILED",
        "error_code": "SCENE_2D_3D_MISMATCH",
        "mismatches": [{"category": "FURNITURE_MISSING", "id": "f-x",
                        "reason": "furniture 'f-x' is missing from the 3D scene",
                        "expected": None, "actual": None}],
        "counts": {},
    }

    with mock.patch.object(registry, "get_adapter", return_value=ImgAdapter()), \
         mock.patch.object(registry, "validate_provider",
                           return_value={"status": "OK", "message": "ok"}), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False), \
         mock.patch.object(vs, "validate_scene_2d_to_3d", return_value=failed_report), \
         TestClient(app) as client:
        r = client.post(f"/api/floor-plans/{FID}/generate", json={
            "provider": "nvidia", "count": 1,
            "design_intent": {"style": "modern"},
            "rooms": ["Living Area", "Kitchen"], "fresh_generation": True,
        })

    assert r.status_code == 201
    body = r.json()
    assert calls["n"] == 0  # the provider/fal was NEVER called — refused before render
    assert body["status"] == "failed"
    assert body["images"] == []
    assert body["validation"] and body["validation"]["error_code"] == "SCENE_2D_3D_MISMATCH"
    assert body["error"] and "SCENE_2D_3D_MISMATCH" in body["error"]
    assert all("SCENE_2D_3D_MISMATCH" in e["detail"] for e in body["room_errors"])
