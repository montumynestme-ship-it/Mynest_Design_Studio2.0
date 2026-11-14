"""Developer-only furniture / geometry inspector.

Builds a self-contained HTML page that makes the EXISTING furniture SVG assets, their
canonical metadata, and (optionally) a design's backend control-image canvas inspectable
in Chrome DevTools. Pure/testable: the catalog view needs no database.

Safety rules (enforced here, not assumed):
* Only trusted, repository-owned SVGs are loaded — resolved from the CLOSED
  ``CLASS_BY_ITEM_ID`` mapping, never from a caller-supplied filename, and only when the
  resolved path stays inside ``svg_rasterizer.SVG_DIR`` (no traversal).
* Inlined SVG markup is sanitized (no ``<script>``, no ``on*`` handlers, no external
  ``href``/``<image>``/``<foreignObject>``) so the dev page cannot execute script or load
  external resources even if an asset were tampered with.
* Every piece of caller/metadata text is HTML-escaped.
* This module never mutates canonical geometry; missing/unmapped/invalid icons are shown
  with their reason, their canonical transform untouched.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from app.data.classes import CANONICAL_ML_CLASSES, svg_name_for_item
from app.services.ml import svg_rasterizer

# Sanitization patterns for inlined (trusted) SVG markup — defensive, not a parser.
_SCRIPT_RE = re.compile(r"<script\b.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_FOREIGN_RE = re.compile(r"<foreignObject\b.*?</foreignObject\s*>", re.IGNORECASE | re.DOTALL)
_ON_ATTR_RE = re.compile(r"\son[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
# href / xlink:href that points anywhere other than a local '#fragment'.
_EXT_HREF_RE = re.compile(
    r"\s(?:xlink:)?href\s*=\s*(\"(?!#)[^\"]*\"|'(?!#)[^']*'|(?![\"'#])[^\s>]+)", re.IGNORECASE
)
_IMAGE_TAG_RE = re.compile(r"<image\b.*?(?:/>|</image\s*>)", re.IGNORECASE | re.DOTALL)


def sanitize_svg_markup(svg_text: str) -> str:
    """Strip anything that could execute script or load an external resource.

    Keeps geometry (paths/rects/circles/lines/polygons, viewBox) so DevTools can still
    inspect the artwork. Applied to trusted repo SVGs as defense-in-depth before inlining.
    """
    s = _SCRIPT_RE.sub("", svg_text)
    s = _FOREIGN_RE.sub("", s)
    s = _IMAGE_TAG_RE.sub("", s)        # <image> can reference external bitmaps
    s = _ON_ATTR_RE.sub("", s)          # onload=, onclick=, …
    s = _EXT_HREF_RE.sub("", s)         # external href / xlink:href
    return s


def read_trusted_svg(item_id: str) -> str | None:
    """Return sanitized SVG markup for a MAPPED item_id, or None.

    Closed-set only: the filename comes from the catalog's ``svg_name`` (never the
    caller), and the resolved path must stay inside ``SVG_DIR``. Anything else → None.
    """
    svg_name = svg_name_for_item(item_id)
    if svg_name is None:
        return None
    base = Path(svg_rasterizer.SVG_DIR).resolve()
    candidate = (base / svg_name).resolve()
    try:
        candidate.relative_to(base)  # reject traversal
    except ValueError:
        return None
    if candidate.suffix.lower() != ".svg" or not candidate.exists():
        return None
    return sanitize_svg_markup(candidate.read_text(encoding="utf-8"))


def list_catalog_items() -> list[dict[str, Any]]:
    """The canonical furniture catalog with SVG mapping + availability (no DB)."""
    base = Path(svg_rasterizer.SVG_DIR)
    items: list[dict[str, Any]] = []
    for info in CANONICAL_ML_CLASSES:
        svg_exists = (base / info.svg_name).exists()
        items.append(
            {
                "item_id": info.item_id,
                "display_name": info.display_name,
                "category": info.category,
                "kind": info.kind,
                "svg_name": info.svg_name,
                "width_mm": info.width_mm,
                "depth_mm": info.depth_mm,
                "height_mm": info.height_mm,
                "svg_exists": svg_exists,
            }
        )
    return items


_PAGE_CSS = """
:root{color-scheme:light dark}
body{font-family:system-ui,sans-serif;margin:0;padding:24px;background:#f7f7f8;color:#1a1a1a}
@media(prefers-color-scheme:dark){body{background:#17181b;color:#e8e8ea}}
h1{font-size:20px;margin:0 0 4px}
.sub{opacity:.7;font-size:13px;margin:0 0 20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{border:1px solid #d0d0d6;border-radius:10px;padding:14px;background:#fff}
@media(prefers-color-scheme:dark){.card{background:#202126;border-color:#35363c}}
.card h2{font-size:15px;margin:0 0 2px}
.cat{font-size:12px;opacity:.65;margin:0 0 10px}
.panels{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.panel{border:1px dashed #c3c3cc;border-radius:8px;padding:8px;min-height:92px;display:flex;flex-direction:column}
.panel .lbl{font-size:10px;letter-spacing:.04em;text-transform:uppercase;opacity:.6;margin-bottom:6px}
.art svg{width:100%;height:84px}
.footprint{align-items:center;justify-content:center}
.fpbox{border:2px solid #2563eb;background:rgba(37,99,235,.08)}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:12px}
td{padding:2px 4px;border-top:1px solid #ececf0;vertical-align:top}
td.k{opacity:.6;white-space:nowrap;width:42%}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px}
.ok{background:#dcfce7;color:#166534}.miss{background:#fee2e2;color:#991b1b}
.rast img{max-width:100%;border:1px solid #ccc;border-radius:6px}
"""


def _footprint_box(width_mm: float, depth_mm: float) -> str:
    # Proportional preview box (purely visual; real geometry is the canonical transform).
    w = max(20.0, min(120.0, float(width_mm) / 25.0))
    h = max(14.0, min(84.0, float(depth_mm) / 25.0))
    return (
        f'<div class="fpbox" style="width:{w:.0f}px;height:{h:.0f}px"></div>'
        f'<div style="font-size:10px;opacity:.6;margin-top:4px">'
        f"{html.escape(str(width_mm))}×{html.escape(str(depth_mm))} mm</div>"
    )


def _catalog_card(item: dict[str, Any], inline_svg: str | None) -> str:
    e = html.escape
    art = inline_svg if inline_svg else '<div class="badge miss">no SVG</div>'
    avail = '<span class="badge ok">mapped</span>' if item["svg_exists"] else '<span class="badge miss">missing</span>'
    rows = "".join(
        f'<tr><td class="k">{e(k)}</td><td>{e(str(v))}</td></tr>'
        for k, v in (
            ("item_id", item["item_id"]),
            ("svg_name", item["svg_name"]),
            ("category", item["category"]),
            ("kind", item["kind"]),
            ("width_mm", item["width_mm"]),
            ("depth_mm", item["depth_mm"]),
            ("height_mm", item["height_mm"]),
        )
    )
    return (
        f'<div class="card" data-item-id="{e(item["item_id"])}" data-svg-name="{e(item["svg_name"])}">'
        f'<h2>{e(item["display_name"])} {avail}</h2>'
        f'<p class="cat">{e(item["item_id"])}</p>'
        f'<div class="panels">'
        f'<div class="panel art"><span class="lbl">SVG artwork (inline)</span>{art}</div>'
        f'<div class="panel footprint"><span class="lbl">Canonical footprint</span>'
        f'{_footprint_box(item["width_mm"], item["depth_mm"])}</div>'
        f"</div>"
        f"<table>{rows}</table>"
        f"</div>"
    )


def _design_metadata_table(design: dict[str, Any]) -> str:
    """Render per-item canonical metadata + fallback reasons for a design view.

    ``design`` is a plain dict (built by the route from canonical/report) — every value
    is escaped. No canonical geometry is altered here.
    """
    e = html.escape
    head = (
        '<tr><td class="k">uid</td><td class="k">item_id</td><td class="k">svg_name</td>'
        '<td class="k">cx,cy</td><td class="k">w×h</td><td class="k">rot</td>'
        '<td class="k">fallback</td></tr>'
    )
    body = ""
    for it in design.get("items", []):
        body += (
            f'<tr><td>{e(str(it.get("uid")))}</td><td>{e(str(it.get("item_id")))}</td>'
            f'<td>{e(str(it.get("svg_name") or ""))}</td>'
            f'<td>{e(str(it.get("cx")))},{e(str(it.get("cy")))}</td>'
            f'<td>{e(str(it.get("w")))}×{e(str(it.get("h")))}</td>'
            f'<td>{e(str(it.get("rotation")))}</td>'
            f'<td>{e(str(it.get("fallback") or ""))}</td></tr>'
        )
    img = ""
    if design.get("control_image_url"):
        img = (
            f'<div class="panel rast"><span class="lbl">Rasterized canvas (PNG)</span>'
            f'<img src="{e(design["control_image_url"])}" alt="control image"></div>'
        )
    meta = "".join(
        f'<tr><td class="k">{e(k)}</td><td>{e(str(v))}</td></tr>'
        for k, v in (
            ("floor_plan_id", design.get("floor_plan_id")),
            ("design_version_id", design.get("design_version_id")),
            ("geometry_fingerprint", design.get("geometry_fingerprint")),
            ("coordinate_frame", design.get("coordinate_frame")),
            ("icons_rendered", design.get("icons_rendered")),
            ("fallback_count", design.get("fallback_count")),
        )
    )
    return (
        f'<div class="card" style="grid-column:1/-1">'
        f"<h2>Design {e(str(design.get('design_version_id') or ''))}</h2>"
        f'<div class="panels">{img}'
        f'<div class="panel"><span class="lbl">Provenance</span><table>{meta}</table></div></div>'
        f"<table>{head}{body}</table></div>"
    )


def build_inspector_html(
    catalog_items: list[dict[str, Any]],
    inline_svgs: dict[str, str | None],
    *,
    design: dict[str, Any] | None = None,
) -> str:
    """Assemble the full inspector HTML. ``inline_svgs`` maps item_id → sanitized SVG."""
    cards = "".join(_catalog_card(it, inline_svgs.get(it["item_id"])) for it in catalog_items)
    design_block = _design_metadata_table(design) if design else ""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>MyNest Furniture Inspector (dev)</title>"
        f"<style>{_PAGE_CSS}</style></head><body>"
        "<h1>Furniture / Geometry Inspector <span class='badge miss'>dev-only</span></h1>"
        "<p class='sub'>Trusted repository SVG assets, canonical footprints and backend "
        "canvas provenance. Inline SVG is DevTools-inspectable. No live generation path is "
        "touched; canonical geometry is read-only.</p>"
        f'<div class="grid">{design_block}{cards}</div>'
        "</body></html>"
    )
