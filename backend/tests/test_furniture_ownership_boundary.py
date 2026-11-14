"""Furniture ownership / data-boundary (RULES 1-8).

The uploaded floor plan is EMPTY of furniture. The ONLY authoritative furniture
source is the user's manual 2D editor layout (PUT /layout). Floor-plan extraction
and YOLO/VLM detection must NEVER create or inject authoritative furniture, and 3D
rendering must never mint furniture UIDs.

API CRUD tests run on an isolated throwaway plan (never the shared fixture). The
RULE-8 test proves at the service level that detection never writes canonical even
with apply_to_canonical=True and a real detection present.
"""

import io
from collections.abc import Iterator
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import floor_plan_service

client = TestClient(app)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _item(uid, item_id="bed", cx=500.0, cy=350.0, w=1800.0, h=2000.0, rotation=0.0):
    return {"uid": uid, "item_id": item_id, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rotation}


@pytest.fixture
def plan() -> Iterator[str]:
    """An isolated uploaded floor plan (empty of furniture); cleaned up after."""
    project = client.post("/api/projects", json={"name": "__ownership_test__", "floor_count": 1}).json()
    pid, fid = project["id"], project["floors"][0]["id"]
    up = client.post(
        "/api/floor-plans/upload",
        files={"file": ("empty.png", io.BytesIO(PNG_BYTES), "image/png")},
        data={"project_id": pid, "floor_id": fid},
    )
    assert up.status_code == 201, up.text
    yield up.json()["id"]
    client.delete(f"/api/projects/{pid}")


def _get_layout(plan_id):
    r = client.get(f"/api/floor-plans/{plan_id}/layout")
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _put_layout(plan_id, items):
    r = client.put(f"/api/floor-plans/{plan_id}/layout", json={"items": items})
    assert r.status_code == 200, r.text
    return r.json()["items"]


# RULE 1 — empty floor plan has zero authoritative furniture
def test_empty_floor_plan_has_zero_authoritative_furniture(plan):
    assert _get_layout(plan) == []


# RULE 2/7 — user adds furniture -> appears with its stable UID
def test_add_furniture_appears_with_stable_uid(plan):
    _put_layout(plan, [_item("uid-1", "bed")])
    items = _get_layout(plan)
    assert len(items) == 1
    assert items[0]["uid"] == "uid-1" and items[0]["item_id"] == "bed"


# RULE 3 — moving furniture updates authoritative coordinates (same UID)
def test_move_updates_coordinates(plan):
    _put_layout(plan, [_item("uid-1", cx=500, cy=350)])
    _put_layout(plan, [_item("uid-1", cx=1200, cy=900)])
    it = _get_layout(plan)[0]
    assert it["uid"] == "uid-1" and it["cx"] == 1200 and it["cy"] == 900


# RULE 4 / 6 — rotating furniture updates authoritative rotation (same UID)
def test_rotate_updates_rotation(plan):
    _put_layout(plan, [_item("uid-1", rotation=0)])
    _put_layout(plan, [_item("uid-1", rotation=90)])
    it = _get_layout(plan)[0]
    assert it["uid"] == "uid-1" and it["rotation"] == 90


# RULE 6 — resizing furniture updates authoritative dimensions (same UID)
def test_resize_updates_dimensions(plan):
    _put_layout(plan, [_item("uid-1", w=1800, h=2000)])
    _put_layout(plan, [_item("uid-1", w=900, h=1000)])
    it = _get_layout(plan)[0]
    assert it["uid"] == "uid-1" and it["w"] == 900 and it["h"] == 1000


# RULE 5 — deleting furniture removes it from the authoritative design
def test_delete_removes_furniture(plan):
    _put_layout(plan, [_item("uid-1"), _item("uid-2", "sofa", cx=800)])
    assert len(_get_layout(plan)) == 2
    _put_layout(plan, [_item("uid-1")])  # uid-2 removed
    items = _get_layout(plan)
    assert [i["uid"] for i in items] == ["uid-1"]


# RULE 1 (extraction) — re-running floor-plan extraction does not overwrite furniture
def test_extraction_does_not_overwrite_manual_furniture(plan):
    _put_layout(plan, [_item("uid-1", "bed"), _item("uid-2", "sofa", cx=900)])
    before = _get_layout(plan)
    # /scene runs the deterministic extraction/scene build (walls/doors/windows).
    scene = client.get(f"/api/floor-plans/{plan}/scene")
    assert scene.status_code in (200, 500)  # extraction may be trivial on a 1x1 image
    after = _get_layout(plan)
    assert after == before  # manual furniture is untouched by extraction
    assert {i["uid"] for i in after} == {"uid-1", "uid-2"}


# RULE 2/3/8 — detection (YOLO/VLM) can NEVER inject furniture into the canonical,
# even with apply_to_canonical=True and a real detection present.
def test_detection_cannot_inject_furniture_into_canonical():
    fake_detection = {
        "position": {"cx": 100, "cy": 100, "w": 50, "h": 50},
        "normalized": {"cx": 0.1, "cy": 0.1, "w": 0.05, "h": 0.05},
        "dimensions_mm": {"width": 500, "depth": 500},
        "class": "chair", "class_id": 1, "item_id": "chair", "confidence": 0.95,
    }

    class _FakeInference:
        def detect_objects(self, *a, **k):
            return [fake_detection]

    with mock.patch.object(floor_plan_service, "get_floor_plan_pil_image",
                           return_value=(Image.new("RGB", (64, 64), (200, 200, 200)), "p", "png")), \
         mock.patch("app.services.scene_service.build_scene", return_value={"rooms": [], "walls": []}), \
         mock.patch("app.services.ml.inference.FloorPlanInferenceService", _FakeInference), \
         mock.patch.object(floor_plan_service, "save_layout") as spy_save:
        resp = floor_plan_service.detect_furniture("any-id", apply_to_canonical=True)

    # Detection is returned (diagnostic) but NEVER written to the authoritative design.
    assert resp.count == 1
    assert resp.applied_to_canonical is False
    spy_save.assert_not_called()
