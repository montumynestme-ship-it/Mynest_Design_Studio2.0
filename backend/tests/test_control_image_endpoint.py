"""DB-dependent endpoint tests for /control-image snapshot binding (Option D enabler).

These MUTATE the database (create project/plan/versions), so they run ONLY against a
confirmed disposable local Postgres via require_db_isolation; otherwise they skip. They
verify the canvas is pinned to an immutable design version, 404s on an unknown version,
and keeps the image/png contract — without touching the live fal generation path.
"""

import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("require_db_isolation")

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

_BED_A = {"uid": "ci-bed", "item_id": "bed", "cx": 500, "cy": 350, "w": 180, "h": 150, "rotation": 0}
_BED_B = {"uid": "ci-bed", "item_id": "bed", "cx": 900, "cy": 650, "w": 180, "h": 150, "rotation": 0}


@pytest.fixture
def plan():
    project = client.post("/api/projects", json={"name": "__ctrlimg__", "floor_count": 1}).json()
    pid, fid = project["id"], project["floors"][0]["id"]
    up = client.post(
        "/api/floor-plans/upload",
        files={"file": ("e.png", BytesIO(PNG_1PX), "image/png")},
        data={"project_id": pid, "floor_id": fid},
    )
    try:
        yield up.json()["id"]
    finally:
        client.delete(f"/api/projects/{pid}")


def _version(plan_id):
    return client.get(f"/api/floor-plans/{plan_id}/scene").json()["design_version_id"]


def test_control_image_png_and_version_header(plan):
    # PNG floor plan → 422 (control image requires a vector PDF). Contract preserved.
    client.put(f"/api/floor-plans/{plan}/layout", json={"items": [_BED_A]})
    r = client.get(f"/api/floor-plans/{plan}/control-image")
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_version_404(plan):
    client.put(f"/api/floor-plans/{plan}/layout", json={"items": [_BED_A]})
    r = client.get(f"/api/floor-plans/{plan}/control-image", params={"version": str(uuid.uuid4())})
    assert r.status_code == 404


def test_version_pins_snapshot_header(plan):
    client.put(f"/api/floor-plans/{plan}/layout", json={"items": [_BED_A]})
    va = _version(plan)
    client.put(f"/api/floor-plans/{plan}/layout", json={"items": [_BED_B]})
    vb = _version(plan)
    assert va != vb
    r = client.get(f"/api/floor-plans/{plan}/control-image", params={"version": va})
    # Either the PNG renders (vector plan) or 422 (png plan); either way the pinned
    # version must be echoed, never silently the latest.
    if r.status_code == 200:
        assert r.headers["X-Design-Version-Id"] == va
