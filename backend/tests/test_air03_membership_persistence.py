"""AIR-03 Step 4 — room_membership persistence: save / reload / versioning (offline).

Exercises the real API save path + reload, proving the structured field survives a
round-trip, a changed value creates a new immutable version, an identical save does not,
legacy items (no field) load cleanly, and an unsupported value is stored verbatim (never
silently coerced to a successful/valid assignment).
"""
from __future__ import annotations

import io
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import floor_plan_service

client = TestClient(app)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _dining(membership=None):
    it = {"uid": "dt-1", "item_id": "dining-table", "cx": 500.0, "cy": 500.0,
          "w": 225.0, "h": 135.0, "rotation": -90.0}
    if membership is not None:
        it["room_membership"] = membership
    return it


@pytest.fixture
def plan() -> Iterator[str]:
    project = client.post("/api/projects", json={"name": "__membership_test__", "floor_count": 1}).json()
    pid, fid = project["id"], project["floors"][0]["id"]
    up = client.post(
        "/api/floor-plans/upload",
        files={"file": ("empty.png", io.BytesIO(PNG), "image/png")},
        data={"project_id": pid, "floor_id": fid},
    )
    assert up.status_code == 201, up.text
    yield up.json()["id"]
    client.delete(f"/api/projects/{pid}")


def _save(plan_id, items):
    r = client.put(f"/api/floor-plans/{plan_id}/layout", json={"items": items})
    assert r.status_code == 200, r.text


def _reload_membership(plan_id):
    items = floor_plan_service.get_layout(plan_id).items
    return next((i.room_membership for i in items if i.uid == "dt-1"), "MISSING")


def test_membership_survives_save_and_reload(plan):
    _save(plan, [_dining("KITCHEN")])
    assert _reload_membership(plan) == "KITCHEN"


def test_changed_membership_creates_new_immutable_version(plan):
    _save(plan, [_dining("KITCHEN")])
    v1 = floor_plan_service.get_latest_version_info(plan)[1]
    _save(plan, [_dining("LIVING_AREA")])
    v2 = floor_plan_service.get_latest_version_info(plan)[1]
    assert v2 == v1 + 1                       # append-only new version
    assert _reload_membership(plan) == "LIVING_AREA"


def test_identical_membership_save_does_not_spawn_version(plan):
    _save(plan, [_dining("KITCHEN")])
    v1 = floor_plan_service.get_latest_version_info(plan)[1]
    _save(plan, [_dining("KITCHEN")])         # byte-identical
    v2 = floor_plan_service.get_latest_version_info(plan)[1]
    assert v2 == v1


def test_untagged_legacy_item_loads_as_none(plan):
    _save(plan, [_dining(None)])              # no room_membership key
    assert _reload_membership(plan) is None


def test_unsupported_value_is_stored_verbatim_not_coerced(plan):
    # The backend stores exactly what was sent; it NEVER silently coerces an invalid
    # value into a valid/successful assignment. The resolver treats it as review-required.
    _save(plan, [_dining("GARAGE")])
    assert _reload_membership(plan) == "GARAGE"
    from app.services import room_membership_service as M
    decisions = M.resolve_dining_memberships(
        [_dining("GARAGE")],
        [{"id": "kda", "label": "Kitchen & Dining Area", "validation_status": "CONFIRMED",
          "furniture": [{"uid": "dt-1", "item_id": "dining-table"},
                        {"uid": "ch", "item_id": "chimney"}]}],
    )
    assert decisions[0]["status"] == M.REVIEW_REQUIRED
    assert decisions[0]["reason"].startswith("INVALID_MEMBERSHIP")


def test_membership_removed_when_cleared(plan):
    _save(plan, [_dining("KITCHEN")])
    assert _reload_membership(plan) == "KITCHEN"
    _save(plan, [_dining(None)])              # user cleared the assignment
    assert _reload_membership(plan) is None
