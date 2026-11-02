"""End-to-end tests for GET /api/floor-plans/{file_id}/geometry-reference.

Uses the real TestClient + DB exactly like test_floor_plans.py / test_handoff12_*:
a throwaway project+floor is created, a 1px PNG is uploaded, and immutable design
versions are created through PUT /layout. Everything is cleaned up by deleting the
project (cascade). No fal/paid calls; the SVG is never wired into generation here.

NOTE on geometry coverage: a PNG plan has no extractable walls/openings (vector
extraction is PDF-only), so the walls/doors/windows assertions verify that the endpoint
faithfully reflects whatever scene_service.build_scene produces (consistency with
/scene), not that a specific wall count exists. No PDF fixture ships with the repo.
"""

import re
import uuid
from io import BytesIO
from unittest import mock
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import floor_plan_service

client = TestClient(app)

# These tests MUTATE the database (create projects/plans/versions). They run only
# against an explicitly-confirmed disposable local test DB; otherwise they skip. See
# conftest.require_db_isolation / db_isolation_status.
pytestmark = pytest.mark.usefixtures("require_db_isolation")

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

_BED_A = {"uid": "ref-bed", "item_id": "bed", "cx": 500, "cy": 350, "w": 180, "h": 150, "rotation": 0}
_BED_B = {"uid": "ref-bed", "item_id": "bed", "cx": 900, "cy": 650, "w": 180, "h": 150, "rotation": 0}


def _url(plan_id: str, version: str | None = None) -> str:
    base = f"/api/floor-plans/{plan_id}/geometry-reference"
    return f"{base}?version={version}" if version else base


def _version_of(plan_id: str) -> str:
    return client.get(f"/api/floor-plans/{plan_id}/scene").json()["design_version_id"]


@pytest.fixture
def plan():
    """A throwaway project+floor with one uploaded PNG plan; cascade-deleted after."""
    project = client.post("/api/projects", json={"name": "__geomref__", "floor_count": 1}).json()
    pid, fid = project["id"], project["floors"][0]["id"]
    up = client.post(
        "/api/floor-plans/upload",
        files={"file": ("empty.png", BytesIO(PNG_1PX), "image/png")},
        data={"project_id": pid, "floor_id": fid},
    )
    plan_id = up.json()["id"]
    try:
        yield plan_id
    finally:
        client.delete(f"/api/projects/{pid}")


def _put(plan_id: str, items: list[dict]) -> None:
    r = client.put(f"/api/floor-plans/{plan_id}/layout", json={"items": items})
    assert r.status_code == 200, r.text


# 1 — successful response, content type, parseable SVG
def test_success_returns_parseable_svg(plan):
    _put(plan, [_BED_A])
    r = client.get(_url(plan))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/svg+xml")
    root = ET.fromstring(r.text)  # raises if not well-formed XML
    assert root.tag.endswith("svg")
    assert 'data-uid="ref-bed"' in r.text


# 2 — version binding: version A still renders A's furniture after B exists
def test_version_binding_pins_immutable_version(plan):
    _put(plan, [_BED_A])
    version_a = _version_of(plan)
    _put(plan, [_BED_B])  # append v2 (bed moved)
    version_b = _version_of(plan)
    assert version_a != version_b

    svg_a = client.get(_url(plan, version_a)).text
    assert f'data-design-version-id="{version_a}"' in svg_a
    assert 'x1="500.00" y1="350.00"' in svg_a   # A's centre marker
    assert 'x1="900.00"' not in svg_a           # not B's position


# 3 — unknown version → 404, no fallback to current
def test_unknown_version_404(plan):
    _put(plan, [_BED_A])
    r = client.get(_url(plan, str(uuid.uuid4())))
    assert r.status_code == 404


# 4 — version belonging to another plan → 404
def test_wrong_plan_version_404(plan):
    _put(plan, [_BED_A])
    other = client.post("/api/projects", json={"name": "__geomref2__", "floor_count": 1}).json()
    opid, ofid = other["id"], other["floors"][0]["id"]
    try:
        oplan = client.post(
            "/api/floor-plans/upload",
            files={"file": ("e.png", BytesIO(PNG_1PX), "image/png")},
            data={"project_id": opid, "floor_id": ofid},
        ).json()["id"]
        _put(oplan, [_BED_A])
        other_version = _version_of(oplan)
        r = client.get(_url(plan, other_version))  # other plan's version on THIS plan
        assert r.status_code == 404
    finally:
        client.delete(f"/api/projects/{opid}")


# 5 — missing floor plan → 404 (established API contract)
def test_missing_floor_plan_404():
    r = client.get(_url(str(uuid.uuid4())))
    assert r.status_code == 404


# 6 — geometry preservation: furniture identity/type/transform + scene consistency
def test_geometry_preserved_and_scene_consistent(plan):
    _put(plan, [_BED_A])
    r = client.get(_url(plan))
    svg = r.text
    assert 'data-uid="ref-bed"' in svg and 'data-item-id="bed"' in svg
    assert 'x1="500.00" y1="350.00"' in svg  # transform honoured (centre marker)
    # The embedded metadata must reflect the SAME scene /scene returns (no divergent
    # geometry): wall/opening/room counts come from build_scene either way.
    meta = _read_metadata(svg)
    scene = client.get(f"/api/floor-plans/{plan}/scene").json()
    assert meta["wall_count"] == len(scene.get("walls", []) or [])
    assert meta["room_count"] == len(scene.get("rooms", []) or [])
    assert meta["furniture_drawn"] == 1


# 7 — determinism
def test_deterministic_output(plan):
    _put(plan, [_BED_A])
    a = client.get(_url(plan)).text
    b = client.get(_url(plan)).text
    assert a == b


# 8 — canonical immutability: a GET creates no version and mutates nothing
def test_get_does_not_mutate_canonical_or_add_version(plan):
    _put(plan, [_BED_A])
    before_version = _version_of(plan)
    before_layout = client.get(f"/api/floor-plans/{plan}/layout").json()
    client.get(_url(plan))
    client.get(_url(plan, before_version))
    assert _version_of(plan) == before_version
    assert client.get(f"/api/floor-plans/{plan}/layout").json() == before_layout


# 9 — invalid/incomplete geometry follows existing validation (schema rejects it)
def test_incomplete_geometry_rejected_at_persistence(plan):
    # cx missing → LayoutItem schema (required float) rejects at PUT; the reference
    # therefore never has to guess a position.
    r = client.put(
        f"/api/floor-plans/{plan}/layout",
        json={"items": [{"uid": "x", "item_id": "bed", "cy": 10, "w": 10, "h": 10, "rotation": 0}]},
    )
    assert r.status_code == 422


# 10 — version consistency: rendered furniture and embedded id never diverge
def test_version_and_canonical_cannot_diverge(plan):
    _put(plan, [_BED_A])
    version_a = _version_of(plan)
    _put(plan, [_BED_B])  # latest is now B
    # Simulate a concurrent append landing AFTER the id is resolved: force
    # get_latest_version_info to report A while the live latest is B. The fix reads the
    # canonical BY that id, so the SVG must show A's furniture AND A's id — never B's
    # canonical under A's id.
    info_a = (version_a, 1)
    with mock.patch.object(floor_plan_service, "get_latest_version_info", return_value=info_a):
        svg = client.get(_url(plan)).text
    assert f'data-design-version-id="{version_a}"' in svg
    assert 'x1="500.00" y1="350.00"' in svg  # A's position, bound to A's id
    assert 'x1="900.00"' not in svg


# 11 — SVG safety: user-controlled identifiers are escaped, cannot inject elements
def test_svg_injection_is_escaped(plan):
    evil_uid = 'bed"><script>alert(1)</script>'
    evil_type = 'x"><script>alert(2)</script>'
    _put(plan, [{"uid": evil_uid, "item_id": evil_type, "cx": 300, "cy": 300,
                 "w": 40, "h": 40, "rotation": 0}])
    r = client.get(_url(plan))
    assert r.status_code == 200
    svg = r.text
    # No live script element / unescaped break-out survived into the document.
    assert "<script>" not in svg
    assert '"><script' not in svg
    # Escaped forms are present instead, and the document still parses as XML.
    assert "&lt;script&gt;" in svg
    ET.fromstring(svg)


def _read_metadata(svg: str) -> dict:
    import json
    m = re.search(r"<metadata>(.*?)</metadata>", svg, re.DOTALL)
    assert m, "metadata block missing"
    # Attribute/text escaping turns & < > into entities; unescape for JSON parsing.
    raw = m.group(1).replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return json.loads(raw)
