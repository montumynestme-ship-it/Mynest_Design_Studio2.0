"""Regression tests for the wardrobe icon-mapping fix (and the trusted-asset invariant).

Confirmed defect: ``item_id='wardrobe'`` had no SVG mapping (it is not an ML detection
class) and fell back to ``unmapped_item_id`` even though ``wardrobe.svg`` exists. The fix
adds a trusted library-icon supplement resolved by ``svg_name_for_item`` — no ML class, no
geometry change. Expected values here are independent (the asset filename, the catalog,
and canonical coordinates), not read back from the renderer.
"""

from pathlib import Path

import pytest

from app.data.classes import CLASS_BY_ITEM_ID, EXTRA_ICON_SVGS, svg_name_for_item
from app.services import furniture_inspector as fi
from app.services import geometry_extraction_service as g
from app.services.ml import svg_rasterizer

SVG_DIR = Path(svg_rasterizer.SVG_DIR)
GEO = {"page": {"width": 1000.0, "height": 750.0, "scale": 1.0}, "walls": []}
WARDROBE = {"uid": "wardrobe-1787646602167", "item_id": "wardrobe",
            "cx": 400.0, "cy": 300.0, "w": 120.0, "h": 60.0, "rotation": 0.0}


# 1 — wardrobe resolves to the correct trusted SVG, inside the approved dir
def test_wardrobe_resolves_to_trusted_svg():
    assert svg_name_for_item("wardrobe") == "wardrobe.svg"
    p = (SVG_DIR / "wardrobe.svg").resolve()
    p.relative_to(SVG_DIR.resolve())  # raises if outside the approved asset dir
    assert p.exists()


def test_wardrobe_inline_markup_loads():
    svg = fi.read_trusted_svg("wardrobe")
    assert svg is not None and "<svg" in svg.lower()


# 3 — every mapped asset (ML classes + supplement) exists within the approved dir
def test_all_mapped_svgs_exist_within_asset_dir():
    base = SVG_DIR.resolve()
    names = {c.svg_name for c in CLASS_BY_ITEM_ID.values()} | set(EXTRA_ICON_SVGS.values())
    for n in names:
        p = (base / n).resolve()
        p.relative_to(base)  # no traversal
        assert p.exists(), f"missing trusted asset: {n}"


# 4/5/6/7 — rendering a wardrobe preserves identity + transform; it is drawn, not a fallback
def test_wardrobe_rendered_preserves_identity_and_transform():
    item = dict(WARDROBE)
    _png, report = g.render_control_image_with_report(GEO, [item])
    assert report["icons_rendered"] == 1
    assert report["fallbacks"] == []
    # canonical fields untouched by rendering
    assert item == WARDROBE


def test_three_reported_wardrobes_all_map():
    furn = [
        {"uid": u, "item_id": "wardrobe", "cx": 100.0 + i * 60, "cy": 200.0, "w": 120.0, "h": 60.0, "rotation": 0.0}
        for i, u in enumerate(
            ["wardrobe-1787646602167", "wardrobe-1787646606853", "wardrobe-1787646614206"]
        )
    ]
    _png, report = g.render_control_image_with_report(GEO, furn)
    assert report["furniture_count"] == 3
    assert report["icons_rendered"] == 3
    assert report["fallbacks"] == []


# 9 — unknown item_id still falls back explicitly; no filename is guessed from item_id
def test_unknown_item_still_unmapped():
    assert svg_name_for_item("totally-unknown") is None
    assert svg_name_for_item("") is None
    assert svg_name_for_item(None) is None
    _png, report = g.render_control_image_with_report(
        GEO, [{"uid": "u", "item_id": "totally-unknown", "cx": 400.0, "cy": 300.0, "w": 40.0, "h": 40.0, "rotation": 0.0}]
    )
    assert report["fallbacks"][0]["reason"] == "unmapped_item_id"


# 10 — a supplement value is a bare filename; read_trusted_svg still rejects traversal
def test_supplement_values_are_safe_filenames():
    for name in EXTRA_ICON_SVGS.values():
        assert "/" not in name and "\\" not in name and ".." not in name
    assert fi.read_trusted_svg("../../etc/passwd") is None


# 11 — deterministic output for a wardrobe-containing canvas
def test_wardrobe_canvas_deterministic():
    a, _ = g.render_control_image_with_report(GEO, [dict(WARDROBE)])
    b, _ = g.render_control_image_with_report(GEO, [dict(WARDROBE)])
    assert a == b


# 14 — inspector design-view metadata agrees with the canvas report (DB-free, monkeypatched)
def test_design_view_reports_resolved_wardrobe_svg(monkeypatch):
    from app.api import dev_inspector
    from app.services import floor_plan_service as svc

    canonical = {"furniture": [dict(WARDROBE)]}
    monkeypatch.setattr(svc, "get_canonical", lambda fid: canonical)
    monkeypatch.setattr(svc, "get_latest_version_info", lambda fid: ("dv-x", 3))

    def _no_file(fid):
        raise svc.FloorPlanError(404, "no file")

    monkeypatch.setattr(svc, "get_floor_plan_file", _no_file)  # forces the non-pdf geo path
    design = dev_inspector._build_design_view("fp")
    assert design is not None
    it = design["items"][0]
    assert it["item_id"] == "wardrobe" and it["svg_name"] == "wardrobe.svg" and it["fallback"] is None
    assert design["icons_rendered"] == 1 and design["fallback_count"] == 0
    assert design["design_version_id"] == "dv-x"
