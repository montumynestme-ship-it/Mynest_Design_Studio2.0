"""Generation snapshot / design-version safety.

A generation must render an IMMUTABLE, frozen snapshot of the design: the exact
design version (architectural geometry + furniture layout + camera) captured when
generation started. Editing furniture afterwards appends a NEW design version and
must never change what an in-flight (or already-finished) generation rendered, and
each generated result must clearly identify which design version produced it.

Covers:
  A. Generate → edit furniture DURING generation → generation still uses the original version.
  B. Generate → move bed → a new generation uses the new version.
  C. Generate → delete furniture → a new generation reflects the deletion.
  D. Two generations from two versions remain independent (later edits change neither).

Providers are mocked (offline). Each test runs on its own throwaway plan so the
shared fixture is never mutated.
"""

import io
from collections.abc import Iterator
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.floor_plan import LayoutItem, LayoutPayload
from app.services import floor_plan_service, generation_service
from app.services.ai import registry
from app.services.ai.mock_adapter import MockAdapter

client = TestClient(app)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

ROOM = "Bedroom 1"


def _item(uid, item_id="bed", cx=500.0, cy=350.0, w=1800.0, h=2000.0, rotation=0.0):
    return {"uid": uid, "item_id": item_id, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rotation}


def _LayoutPayload(items):
    return LayoutPayload(items=[LayoutItem(**it) for it in items])


@pytest.fixture
def plan() -> Iterator[str]:
    project = client.post("/api/projects", json={"name": "__snapshot_test__", "floor_count": 1}).json()
    pid, fid = project["id"], project["floors"][0]["id"]
    up = client.post(
        "/api/floor-plans/upload",
        files={"file": ("empty.png", io.BytesIO(PNG_BYTES), "image/png")},
        data={"project_id": pid, "floor_id": fid},
    )
    assert up.status_code == 201, up.text
    yield up.json()["id"]
    client.delete(f"/api/projects/{pid}")


def _save(plan_id, items):
    r = client.put(f"/api/floor-plans/{plan_id}/layout", json={"items": items})
    assert r.status_code == 200, r.text


def _generate(plan_id, adapter=None):
    """Run a real generation (offline mock provider) for a single room."""
    adapter = adapter or MockAdapter()
    with mock.patch.object(registry, "get_adapter", return_value=adapter):
        return generation_service.generate(
            file_id=plan_id, provider="mock", count=1,
            design_intent={"style": "Modern"}, requested_rooms=[ROOM],
            fresh_generation=True,
        )


def _snapshot_furniture(design_version_id):
    canon = floor_plan_service.get_version_canonical(design_version_id)
    assert canon is not None
    return canon.get("furniture", []) or []


# ── A. Edit DURING generation → generation keeps its original snapshot ──────────
def test_edit_during_generation_uses_original_version(plan):
    _save(plan, [_item("bed-1", cx=500)])
    before = floor_plan_service.get_latest_version_info(plan)
    assert before is not None
    orig_id, orig_num = before

    class EditMidRender(MockAdapter):
        _edited = False

        def generate(self, request):
            # Simulate the user moving the bed WHILE the render is running.
            if not EditMidRender._edited:
                EditMidRender._edited = True
                floor_plan_service.save_layout(
                    plan, _LayoutPayload([_item("bed-1", cx=900)])
                )
            return super().generate(request)

    resp = _generate(plan, EditMidRender())

    # The generation is bound to the version captured at START, not the edited one.
    assert resp.design_version_id == orig_id
    assert resp.design_version_number == orig_num
    # Its frozen snapshot still holds the ORIGINAL furniture (bed at 500).
    snap = _snapshot_furniture(orig_id)
    assert len(snap) == 1 and snap[0]["cx"] == 500
    # The mid-generation edit created a NEW, later version (bed at 900) that is now current.
    after = floor_plan_service.get_latest_version_info(plan)
    assert after is not None and after[1] > orig_num
    current = floor_plan_service.get_canonical(plan)["furniture"]
    assert len(current) == 1 and current[0]["cx"] == 900


# ── B. Move bed → a new generation uses the new version ────────────────────────
def test_move_creates_new_version_for_new_generation(plan):
    _save(plan, [_item("bed-1", cx=500)])
    g1 = _generate(plan)
    id_a, num_a = g1.design_version_id, g1.design_version_number

    _save(plan, [_item("bed-1", cx=900)])  # move the bed → new version
    g2 = _generate(plan)
    id_b, num_b = g2.design_version_id, g2.design_version_number

    assert id_a != id_b
    assert num_b == num_a + 1
    assert _snapshot_furniture(id_a)[0]["cx"] == 500   # first generation's snapshot
    assert _snapshot_furniture(id_b)[0]["cx"] == 900   # second generation's snapshot


# ── C. Delete furniture → a new generation reflects the deletion ───────────────
def test_delete_reflected_in_new_generation(plan):
    _save(plan, [_item("bed-1"), _item("sofa-1", "sofa", cx=1200)])
    g1 = _generate(plan)
    id_a = g1.design_version_id

    _save(plan, [_item("bed-1")])  # delete the sofa → new version
    g2 = _generate(plan)
    id_b = g2.design_version_id

    assert id_a != id_b
    assert {f["uid"] for f in _snapshot_furniture(id_a)} == {"bed-1", "sofa-1"}
    assert {f["uid"] for f in _snapshot_furniture(id_b)} == {"bed-1"}  # deletion reflected


# ── D. Two generations from two versions remain independent ────────────────────
def test_two_generations_from_two_versions_independent(plan):
    _save(plan, [_item("bed-1", cx=500), _item("sofa-1", "sofa", cx=1200)])
    g1 = _generate(plan)
    id_a = g1.design_version_id

    _save(plan, [_item("bed-1", cx=900)])  # move bed + delete sofa → new version
    g2 = _generate(plan)
    id_b = g2.design_version_id

    assert id_a != id_b
    snap_a, snap_b = _snapshot_furniture(id_a), _snapshot_furniture(id_b)
    assert {f["uid"] for f in snap_a} == {"bed-1", "sofa-1"} and snap_a[0]["cx"] == 500
    assert {f["uid"] for f in snap_b} == {"bed-1"} and snap_b[0]["cx"] == 900

    # A LATER edit must change NEITHER prior generation's frozen snapshot.
    _save(plan, [_item("bed-1", cx=111)])
    snap_a2, snap_b2 = _snapshot_furniture(id_a), _snapshot_furniture(id_b)
    assert snap_a2 == snap_a   # generation 1 snapshot immutable
    assert snap_b2 == snap_b   # generation 2 snapshot immutable
    # Each result still identifies its own producing version.
    assert g1.design_version_id == id_a and g2.design_version_id == id_b
    assert g1.design_version_number != g2.design_version_number


# ── Bonus: an identical (no-op) save does not spawn a redundant version ─────────
def test_identical_save_does_not_spawn_version(plan):
    _save(plan, [_item("bed-1", cx=500)])
    v1 = floor_plan_service.get_latest_version_info(plan)
    _save(plan, [_item("bed-1", cx=500)])  # byte-identical → no-op
    v2 = floor_plan_service.get_latest_version_info(plan)
    assert v1 == v2  # same version id + number; no explosion of redundant versions
