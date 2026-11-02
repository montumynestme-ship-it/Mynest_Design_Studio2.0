"""DB-free tests for the developer-only furniture/geometry inspector.

Covers: trusted SVG asset loading, closed-set + path-traversal safety, SVG sanitization
(no script/handlers/external refs), HTML escaping of metadata, dev-only access control,
and page assembly. No database, no network, no fal.
"""

import pytest
from fastapi import HTTPException

from app.api import dev_inspector
from app.core import config
from app.services import furniture_inspector as fi


# ── asset loading ────────────────────────────────────────────────────────────────
def test_read_trusted_svg_returns_markup_for_mapped_item():
    svg = fi.read_trusted_svg("bed")
    assert svg is not None and "<svg" in svg.lower()


def test_catalog_lists_items_with_svg_availability():
    items = fi.list_catalog_items()
    assert len(items) >= 14
    bed = next(i for i in items if i["item_id"] == "bed")
    assert bed["svg_name"] == "bed.svg" and bed["svg_exists"] is True


# ── closed-set + path-traversal safety ────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["totally-unknown", "../../etc/passwd", "bed/../door", "", "room-tag"])
def test_read_trusted_svg_rejects_unmapped_or_traversal(bad):
    assert fi.read_trusted_svg(bad) is None


# ── SVG sanitization ───────────────────────────────────────────────────────────────
def test_sanitize_strips_script_handlers_and_external_refs():
    hostile = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        "<script>alert(1)</script>"
        '<rect width="5" height="5" onload="evil()" href="http://evil.test/x"/>'
        '<image href="http://evil.test/p.png"/>'
        "<foreignObject><b>x</b></foreignObject>"
        '<path d="M0 0 L10 10"/></svg>'
    )
    out = fi.sanitize_svg_markup(hostile)
    low = out.lower()
    assert "<script" not in low
    assert "onload" not in low
    assert "http://evil.test" not in out
    assert "<image" not in low
    assert "foreignobject" not in low
    assert '<path d="M0 0 L10 10"/>' in out  # geometry preserved for DevTools


def test_local_fragment_href_is_kept():
    out = fi.sanitize_svg_markup('<svg><use href="#star"/></svg>')
    assert 'href="#star"' in out


# ── HTML escaping of metadata ──────────────────────────────────────────────────────
def test_design_metadata_is_html_escaped():
    items = fi.list_catalog_items()
    inline = {it["item_id"]: None for it in items}
    design = {
        "floor_plan_id": "fp", "design_version_id": "dv", "geometry_fingerprint": "abc123",
        "coordinate_frame": "canonical_world_px", "icons_rendered": 0, "fallback_count": 1,
        "control_image_url": "/api/floor-plans/fp/control-image",
        "items": [{
            "uid": "<script>alert(1)</script>", "item_id": 'x"&<b>', "svg_name": None,
            "cx": 1, "cy": 2, "w": 3, "h": 4, "rotation": 0, "fallback": "unmapped_item_id",
        }],
    }
    html = fi.build_inspector_html(items, inline, design=design)
    assert "<script>alert(1)</script>" not in html   # hostile uid never raw
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&amp;" in html


# ── page assembly ──────────────────────────────────────────────────────────────────
def test_inspector_page_has_inline_svg_and_devonly_marker():
    items = fi.list_catalog_items()
    inline = {it["item_id"]: fi.read_trusted_svg(it["item_id"]) for it in items}
    html = fi.build_inspector_html(items, inline)
    assert html.startswith("<!doctype html>")
    assert "dev-only" in html
    assert "<svg" in html.lower()          # inline artwork present
    assert 'data-item-id="bed"' in html


# ── access control ──────────────────────────────────────────────────────────────────
def test_require_dev_tools_blocks_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "DEV_TOOLS_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        dev_inspector.require_dev_tools()
    assert exc.value.status_code == 404


def test_require_dev_tools_allows_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "DEV_TOOLS_ENABLED", True)
    assert dev_inspector.require_dev_tools() is None
