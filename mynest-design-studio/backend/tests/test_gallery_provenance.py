"""Phase 4A — gallery provenance: the /scene endpoint can build the scene for a SPECIFIC
immutable design version (a generation's frozen snapshot), so an older generation keeps
referencing its original layout even after the floor plan is edited. A missing version is
a 404 — never a silent fall back to the current scene.
"""

import contextlib
import unittest.mock as mock
import uuid

from fastapi.testclient import TestClient

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
V_OLD = "11111111-1111-1111-1111-111111111111"
V_NEW = "22222222-2222-2222-2222-222222222222"

OLD_FURN = [{"uid": "bed-old", "item_id": "bed", "cx": 1, "cy": 2, "w": 3, "h": 4, "rotation": 0}]
NEW_FURN = [
    {"uid": "bed-old", "item_id": "bed", "cx": 1, "cy": 2, "w": 3, "h": 4, "rotation": 0},
    {"uid": "sofa-new", "item_id": "lounger-sofa", "cx": 9, "cy": 9, "w": 5, "h": 5, "rotation": 0},
]


def _client():
    from app.main import app
    return TestClient(app)


def _fake_build(file_id, canonical=None):
    # Echo the furniture the route passed, so tests can see WHICH snapshot was used.
    return {"page": {"width": 10, "height": 10}, "walls": [],
            "rooms": [{"id": "r1", "label": "Room 1",
                       "furniture": list((canonical or {}).get("furniture", []))}]}


def test_scene_with_version_builds_from_that_snapshot():
    with mock.patch("app.api.floor_plans.scene_service.build_scene", side_effect=_fake_build), \
         mock.patch("app.api.floor_plans.service.get_version_canonical", return_value={"furniture": OLD_FURN}):
        r = _client().get(f"/api/floor-plans/{FID}/scene", params={"version": V_OLD})
    assert r.status_code == 200
    body = r.json()
    assert body["design_version_id"] == V_OLD
    uids = [f["uid"] for f in body["rooms"][0]["furniture"]]
    assert uids == ["bed-old"]


def test_scene_version_not_found_is_404_not_current_fallback():
    with mock.patch("app.api.floor_plans.service.get_version_canonical", return_value=None), \
         mock.patch("app.api.floor_plans.scene_service.build_scene", side_effect=_fake_build) as mb:
        r = _client().get(f"/api/floor-plans/{FID}/scene", params={"version": "does-not-exist"})
    assert r.status_code == 404
    mb.assert_not_called()  # never silently built the CURRENT scene as a fallback


def test_scene_without_version_uses_current_latest():
    with mock.patch("app.api.floor_plans.scene_service.build_scene", side_effect=_fake_build) as mb, \
         mock.patch("app.api.floor_plans.service.get_latest_version_info", return_value=(V_NEW, 2)):
        r = _client().get(f"/api/floor-plans/{FID}/scene")
    assert r.status_code == 200
    assert r.json()["design_version_id"] == V_NEW
    # current path calls build_scene WITHOUT a snapshot canonical
    assert mb.call_args.kwargs.get("canonical") is None


def test_older_generation_keeps_its_snapshot_after_edit():
    # Simulate a later edit: latest is now V_NEW (with extra furniture), but a gallery
    # requesting the OLD generation's version must still get the OLD snapshot.
    def version_canonical(vid, file_id=None):
        return {"furniture": OLD_FURN} if vid == V_OLD else {"furniture": NEW_FURN}

    with mock.patch("app.api.floor_plans.scene_service.build_scene", side_effect=_fake_build), \
         mock.patch("app.api.floor_plans.service.get_version_canonical", side_effect=version_canonical), \
         mock.patch("app.api.floor_plans.service.get_latest_version_info", return_value=(V_NEW, 2)):
        client = _client()
        old = client.get(f"/api/floor-plans/{FID}/scene", params={"version": V_OLD}).json()
        new = client.get(f"/api/floor-plans/{FID}/scene", params={"version": V_NEW}).json()
    assert [f["uid"] for f in old["rooms"][0]["furniture"]] == ["bed-old"]
    assert old["design_version_id"] == V_OLD
    # the edited (new) version has the extra sofa; the old snapshot does NOT
    assert "sofa-new" in [f["uid"] for f in new["rooms"][0]["furniture"]]
    assert "sofa-new" not in [f["uid"] for f in old["rooms"][0]["furniture"]]


# --- Ownership (F-1): a design version must belong to the plan it is requested under,
# else building its scene would mix THIS plan's walls with a FOREIGN plan's furniture. ---

OTHER_PLAN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _FakeDV:
    def __init__(self, floor_plan_id: str, canonical: dict):
        self.floor_plan_id = uuid.UUID(floor_plan_id)
        self.canonical_json = canonical


class _FakeDB:
    def __init__(self, dv):
        self._dv = dv

    def get(self, _model, _vid):  # mirrors Session.get(DesignVersion, vid)
        return self._dv


def _fake_scope(dv):
    @contextlib.contextmanager
    def _cm():
        yield _FakeDB(dv)

    return _cm


def test_get_version_canonical_rejects_foreign_plan_version():
    """A version owned by OTHER_PLAN must NOT resolve under FID — returning None so the
    route 404s instead of mixing FID's walls with the foreign plan's furniture."""
    from app.services import floor_plan_service as svc

    dv = _FakeDV(OTHER_PLAN, {"furniture": OLD_FURN})
    with mock.patch.object(svc, "session_scope", _fake_scope(dv)):
        # requested under the WRONG plan -> None (never a cross-plan snapshot)
        assert svc.get_version_canonical(V_OLD, file_id=FID) is None
        # requested under its OWN plan -> its canonical
        assert svc.get_version_canonical(V_OLD, file_id=OTHER_PLAN) == {"furniture": OLD_FURN}
        # legacy callers without file_id keep the prior behaviour (no ownership gate)
        assert svc.get_version_canonical(V_OLD) == {"furniture": OLD_FURN}


def test_scene_route_404s_a_foreign_plan_version():
    """End-to-end: GET /scene?version=<foreign version> is a 404, and the current scene
    is never built as a silent fallback."""
    dv = _FakeDV(OTHER_PLAN, {"furniture": OLD_FURN})
    from app.services import floor_plan_service as svc

    with mock.patch.object(svc, "session_scope", _fake_scope(dv)), \
         mock.patch("app.api.floor_plans.scene_service.build_scene", side_effect=_fake_build) as mb:
        r = _client().get(f"/api/floor-plans/{FID}/scene", params={"version": V_OLD})
    assert r.status_code == 404
    mb.assert_not_called()
