"""Developer-only inspection routes (furniture/geometry inspector).

Gated behind ``config.DEV_TOOLS_ENABLED`` (``MYNEST_DEV_TOOLS=1``). When disabled every
route 404s, so nothing is exposed in a normal/production deployment. Read-only: it never
mutates canonical geometry and never touches the live fal generation path, provider,
model or conditioning. Only trusted repository SVG assets are served/inlined.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response

from app.core import config
from app.data.classes import svg_name_for_item
from app.data.furniture_catalog import is_annotation
from app.services import (
    furniture_inspector,
    geometry_extraction_service,
    svg_geometry_reference,
)
from app.services import floor_plan_service as service
from app.services.floor_plan_service import FloorPlanError

router = APIRouter(prefix="/api/dev", tags=["dev"])
logger = logging.getLogger("app.api.dev_inspector")


def require_dev_tools() -> None:
    """404 unless developer tools are explicitly enabled (access control)."""
    if not config.DEV_TOOLS_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/furniture-svg/{item_id}")
def furniture_svg(item_id: str, _: None = Depends(require_dev_tools)) -> Response:
    """Serve ONE trusted furniture SVG for a mapped ``item_id`` (closed set), else 404."""
    svg = furniture_inspector.read_trusted_svg(item_id)
    if svg is None:
        raise HTTPException(status_code=404, detail="unknown or unmapped furniture item")
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/furniture-inspector", response_class=HTMLResponse)
def furniture_inspector_page(
    file_id: str | None = None, _: None = Depends(require_dev_tools)
) -> HTMLResponse:
    """Render the inspector page. Catalog view needs no DB; ``file_id`` adds a design view."""
    items = furniture_inspector.list_catalog_items()
    inline = {it["item_id"]: furniture_inspector.read_trusted_svg(it["item_id"]) for it in items}
    design = _build_design_view(file_id) if file_id else None
    html = furniture_inspector.build_inspector_html(items, inline, design=design)
    return HTMLResponse(content=html)


def _build_design_view(file_id: str) -> dict[str, Any] | None:
    """Assemble read-only per-item canonical metadata + canvas provenance for a design.

    Best-effort: any failure returns None so the catalog view still renders. Never mutates
    canonical data; the rasterized PNG is the UNCHANGED ``/control-image`` endpoint.
    """
    try:
        canonical = service.get_canonical(file_id)
        info = service.get_latest_version_info(file_id)
        furniture = canonical.get("furniture", []) or []
        try:
            path, file_type, _ = service.get_floor_plan_file(file_id)
            if file_type == "pdf":
                geo = geometry_extraction_service.extract_walls(str(path))
            else:
                geo = {"page": {"width": 1000.0, "height": 750.0, "scale": 1.0}, "walls": []}
        except FloorPlanError:
            geo = {"page": {"width": 1000.0, "height": 750.0, "scale": 1.0}, "walls": []}
        _png, report = geometry_extraction_service.render_control_image_with_report(geo, furniture)
        fallback_by_uid = {str(f.get("uid")): f.get("reason") for f in report.get("fallbacks", [])}
        items: list[dict[str, Any]] = []
        for f in furniture:
            if is_annotation(f.get("item_id")):
                continue
            items.append(
                {
                    "uid": f.get("uid"),
                    "item_id": f.get("item_id"),
                    "svg_name": svg_name_for_item(f.get("item_id")),
                    "cx": f.get("cx"),
                    "cy": f.get("cy"),
                    "w": f.get("w"),
                    "h": f.get("h"),
                    "rotation": f.get("rotation"),
                    "fallback": fallback_by_uid.get(str(f.get("uid"))),
                }
            )
        return {
            "floor_plan_id": file_id,
            "design_version_id": info[0] if info else None,
            "geometry_fingerprint": svg_geometry_reference._fingerprint(canonical),
            "coordinate_frame": report.get("coordinate_frame"),
            "icons_rendered": report.get("icons_rendered"),
            "fallback_count": len(report.get("fallbacks", [])),
            "control_image_url": f"/api/floor-plans/{file_id}/control-image",
            "items": items,
        }
    except Exception as exc:  # noqa: BLE001 — inspector must never 500 the dev page
        logger.warning("[dev inspector] design view unavailable for %s: %s", file_id, exc)
        return None
