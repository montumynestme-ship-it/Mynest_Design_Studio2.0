"""DB-free tests for SVG furniture icons in the backend geometry canvas
(``geometry_extraction_service.render_control_image_with_report``) and for the
unchanged single-image fal request contract.

Geometry comes from the synthetic PDF fixture (see synthetic_floorplan_provenance.md);
furniture is a controlled canonical snapshot. Expected values are independent of the
function under test (fixture coordinates, the catalog mapping, and pixel probes at known
world-px locations). No DB, no network, no fal calls.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image

from app.data.classes import CLASS_BY_ITEM_ID
from app.services import geometry_extraction_service as g
from app.services.ml import svg_rasterizer

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_floorplan.pdf"

BED = {"uid": "bed-1", "item_id": "bed", "cx": 600.0, "cy": 400.0, "w": 180.0, "h": 150.0, "rotation": 0.0}


def _geo():
    return g.extract_walls(str(FIXTURE))


def _png_to_img(png: bytes) -> Image.Image:
    return Image.open(BytesIO(png)).convert("RGB")


def _any_nonwhite_in_bbox(img: Image.Image, cx, cy, w, h) -> bool:
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    x1, y1 = int(cx + w / 2), int(cy + h / 2)
    for x in range(max(0, x0), min(img.width, x1), 4):
        for y in range(max(0, y0), min(img.height, y1), 4):
            if img.getpixel((x, y)) != (255, 255, 255):
                return True
    return False


# 1 — icon lookup by the EXISTING furniture mapping
def test_icon_lookup_by_mapping():
    for item_id in ("bed", "lounger-sofa", "dining-table"):
        info = CLASS_BY_ITEM_ID[item_id]
        assert (svg_rasterizer.SVG_DIR / info.svg_name).exists()


# 2 — representative furniture renders as an icon (no fallback)
def test_representative_icon_rendered():
    png, report = g.render_control_image_with_report(_geo(), [BED])
    assert report["icons_rendered"] == 1
    assert report["fallbacks"] == []
    img = _png_to_img(png)
    assert _any_nonwhite_in_bbox(img, BED["cx"], BED["cy"], BED["w"], BED["h"])


# 3 — missing / invalid icon → recorded fallback, no crash
def test_unmapped_item_falls_back():
    png, report = g.render_control_image_with_report(
        _geo(), [{"uid": "u", "item_id": "totally-unknown", "cx": 600, "cy": 400, "w": 80, "h": 80, "rotation": 0}]
    )
    assert report["icons_rendered"] == 0
    assert report["fallbacks"] == [{"uid": "u", "item_id": "totally-unknown", "reason": "unmapped_item_id"}]
    assert _png_to_img(png)  # still valid PNG


def test_missing_svg_file_falls_back(monkeypatch, tmp_path):
    # Point the asset dir at an empty folder so a MAPPED item's svg is absent.
    monkeypatch.setattr(svg_rasterizer, "SVG_DIR", tmp_path)
    _, report = g.render_control_image_with_report(_geo(), [BED])
    assert report["icons_rendered"] == 0
    assert report["fallbacks"][0]["reason"] == "svg_file_missing"


# 4 — canonical inventory preserved; annotations excluded
def test_inventory_count_excludes_annotations():
    furniture = [BED, {"uid": "t", "item_id": "room-tag", "cx": 0, "cy": 0, "w": 0, "h": 0, "rotation": 0}]
    _, report = g.render_control_image_with_report(_geo(), furniture)
    assert report["furniture_count"] == 1  # room-tag excluded


# 5 — incomplete transform is reported, not guessed/drawn
def test_incomplete_transform_reported():
    _, report = g.render_control_image_with_report(
        _geo(), [{"uid": "x", "item_id": "bed", "cx": 600, "cy": 400, "rotation": 0}]  # no w/h
    )
    assert report["fallbacks"] == [{"uid": "x", "item_id": "bed", "reason": "missing_transform"}]
    assert report["icons_rendered"] == 0


# 6 — placement: content at the canonical position, not elsewhere
def test_placement_at_canonical_position():
    png, _ = g.render_control_image_with_report(_geo(), [BED])
    img = _png_to_img(png)
    assert _any_nonwhite_in_bbox(img, BED["cx"], BED["cy"], BED["w"], BED["h"])
    # A far-away empty corner stays white (item not drawn in the wrong place).
    assert img.getpixel((40, 760)) == (255, 255, 255)


# 7 — walls preserved + coordinate origin/scale
def test_walls_and_coordinate_frame():
    png, report = g.render_control_image_with_report(_geo(), [BED])
    assert (report["width"], report["height"]) == (1200, 800)  # 600x400 pt x scale 2
    assert report["scale"] == 2.0
    assert report["coordinate_frame"] == "canonical_world_px"
    img = _png_to_img(png)
    r, gg, b = img.getpixel((600, 160))  # midpoint of the top wall (world px)
    assert r < 70 and gg < 70 and b < 70  # black wall stroke present


# 8 — deterministic output
def test_deterministic_png():
    a, _ = g.render_control_image_with_report(_geo(), [BED])
    b, _ = g.render_control_image_with_report(_geo(), [BED])
    assert a == b


# 11 — injection resistance: a hostile item_id only hits the closed catalog lookup
def test_hostile_item_id_is_safe():
    evil = '"><script>alert(1)</script>'
    png, report = g.render_control_image_with_report(
        _geo(), [{"uid": "e", "item_id": evil, "cx": 600, "cy": 400, "w": 60, "h": 60, "rotation": 0}]
    )
    assert report["fallbacks"][0]["reason"] == "unmapped_item_id"  # no SVG loaded for it
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG output, no markup surface


# 12 — PNG output + backward-compatible wrapper
def test_png_contract_and_legacy_wrapper():
    geo = _geo()
    legacy = g.render_control_image(geo, [BED])
    withrep, _ = g.render_control_image_with_report(geo, [BED])
    assert legacy[:8] == b"\x89PNG\r\n\x1a\n"
    assert legacy == withrep  # wrapper returns exactly the report function's bytes


# 13 & 15 — the live fal edit request stays a SINGLE image with no unsupported fields
def test_fal_edit_body_has_no_unsupported_image_fields():
    from app.services.ai.base import GenerationRequest
    from app.services.ai.fal_flux_adapter import FalFluxAdapter

    adapter = FalFluxAdapter()
    req = GenerationRequest(prompt="ROOM: Test.\nINVENTORY: bed.", style=None, count=1,
                            width=1216, height=832, seed=7)
    body = adapter._build_body(req, "data:image/png;base64,QUJD")
    allowed = {"prompt", "image_url", "num_images", "output_format", "seed",
               "guidance_scale", "num_inference_steps"}
    assert set(body).issubset(allowed), f"unexpected fal body keys: {set(body) - allowed}"
    assert "image_url" in body  # exactly one conditioning image
    for forbidden in ("control_image", "reference_images", "image_urls", "controlnet", "control_lora_image_url"):
        assert forbidden not in body
