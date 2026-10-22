"""Per-room AI-render eligibility — dynamic for any plan, room-specific, truthful.

`generation_service.room_eligibility` surfaces the EXISTING deterministic geometry
gate per room (no validation weakened, no geometry fabricated). These tests use the
two real plans present under one project/floor as fixtures (ids are test data, not
production hardcoding — production code contains no plan-specific ids):

  * FID "MR.MATHUR"   — all rooms CONFIRMED (wall-proven), including an open-plan
                        Kitchen+Dining: the single wall cycle that encloses both is
                        labelled "Kitchen & Dining Area", so BOTH sections are eligible
                        (the dining-table sits inside that proven polygon). Proves genuine
                        open-plan sections are confirmed, not dropped.
  * RUPA "Layout2"    — every room UNCERTAIN (PDF walls don't close): proves genuinely
                        unprovable rooms are blocked with a truthful, actionable reason,
                        never hidden and never faked into CONFIRMED (per-room independence).
"""

import io

from fastapi.testclient import TestClient

from app.main import app
from app.services import floor_plan_service, generation_service

client = TestClient(app)

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"   # CONFIRMED-geometry plan
RUPA = "f48e0268-5bfb-4ba9-a8c3-7ae1139e09f5"  # unprovable-geometry plan

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_open_plan_dining_is_confirmed_through_shared_kitchen_polygon():
    r = generation_service.room_eligibility(FID)
    rooms = {x["room"]: x for x in r["rooms"]}
    # A CONFIRMED room is eligible...
    assert rooms["Living Area"]["eligible"] is True
    assert rooms["Living Area"]["status"] == "CONFIRMED"
    # ...and the open-plan Dining Area is CONFIRMED because its only dining furniture sits
    # INSIDE the shared wall-proven Kitchen+Dining polygon (labelled "Kitchen & Dining
    # Area"). This is the deterministic fix for the former BASE_GEOMETRY_INVALID — the §L
    # gate was NOT weakened; the shared polygon is genuinely wall-proven and CONFIRMED.
    assert "Kitchen & Dining Area" in rooms, f"open-plan room expected, got {sorted(rooms)}"
    assert rooms["Kitchen & Dining Area"]["status"] == "CONFIRMED"
    assert rooms["Dining Area"]["eligible"] is True
    assert rooms["Dining Area"]["status"] == "CONFIRMED"
    # This plan is fully wall-proven: every room is eligible, and every eligible room is
    # genuinely proven + non-empty (never a furniture-bbox fallback faked into CONFIRMED).
    assert r["eligible_rooms"] == r["total_rooms"] and r["eligible_rooms"] >= 1
    for x in r["rooms"]:
        if x["eligible"]:
            assert x["status"] == "CONFIRMED" and x["furniture_count"] > 0


def test_unprovable_plan_all_blocked_with_truthful_reason():
    r = generation_service.room_eligibility(RUPA)
    assert r["eligible_rooms"] == 0 and r["total_rooms"] >= 1
    for x in r["rooms"]:
        assert x["eligible"] is False
        assert x["status"] in ("UNCERTAIN", "EMPTY")
        # Truthful, actionable — never a generic BASE_GEOMETRY_INVALID, never CONFIRMED.
        assert "could not be verified" in x["reason"] or "No furniture" in x["reason"]


def test_eligibility_binds_current_design_version():
    r = generation_service.room_eligibility(FID)
    info = floor_plan_service.get_latest_version_info(FID)
    assert info is not None and r["design_version_id"] == info[0]


def test_route_returns_room_eligibility():
    resp = client.get(f"/api/floor-plans/{FID}/room-eligibility")
    assert resp.status_code == 200
    body = resp.json()
    assert "rooms" in body and "design_version_id" in body
    assert any(x["eligible"] for x in body["rooms"])  # FID has eligible rooms


def test_empty_room_reports_empty_not_confirmed():
    # An isolated plan with NO furniture: rooms (if any) must never be eligible, and a
    # room with zero furniture reports EMPTY — never fabricated as CONFIRMED.
    project = client.post("/api/projects", json={"name": "__elig_empty__", "floor_count": 1}).json()
    pid, fid = project["id"], project["floors"][0]["id"]
    try:
        up = client.post(
            "/api/floor-plans/upload",
            files={"file": ("empty.png", io.BytesIO(PNG_1PX), "image/png")},
            data={"project_id": pid, "floor_id": fid},
        )
        plan_id = up.json()["id"]
        r = generation_service.room_eligibility(plan_id)
        assert r["eligible_rooms"] == 0
        for x in r["rooms"]:
            assert x["eligible"] is False
            assert x["status"] in ("EMPTY", "UNCERTAIN")
    finally:
        client.delete(f"/api/projects/{pid}")
