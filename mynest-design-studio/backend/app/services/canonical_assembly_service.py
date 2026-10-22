"""Final deterministic canonical floor-plan assembly (audit stage 10).

Composes the deterministic stages into ONE canonical structure:
  OCR/text → dimensions → walls → room boundaries → doors/windows →
  furniture/object detections (advisory) → vision semantic validation (advisory).

Absolute rules honoured here:
- The existing canonical 2D geometry is the SOURCE OF TRUTH. Canonical furniture is
  copied VERBATIM — every uid/item_id/cx/cy/w/h/rotation is preserved unchanged.
- Architecture (walls/rooms/openings) preserves source geometry from the vector
  extraction; nothing is AI-generated, no coordinate is guessed, no furniture moved.
- Doors/windows use WALL-OWNERSHIP; shared walls stay single shared spans; UNCERTAIN
  entities are preserved (never fabricated into confident assignments).
- Detections and vision output are ADVISORY layers, kept separate — they never
  override the authoritative canonical furniture or the deterministic geometry.
- Deterministic: identical input → identical output (stable ordering + a content
  hash over the authoritative furniture + architecture).
No FLUX / no image generation.
"""

from __future__ import annotations

import hashlib
import json
import math
from io import BytesIO
from typing import Any

from app.services import (
    floor_plan_service,
    geometry_extraction_service,
    shape_extraction_service,
)

_FURN_KEYS = ("uid", "item_id", "cx", "cy", "w", "h", "rotation")


def _canonical_furniture(file_id: str) -> list[dict[str, Any]]:
    """Canonical furniture, copied verbatim (source of truth), stably ordered."""
    canon = floor_plan_service.get_canonical(file_id)
    items: list[dict[str, Any]] = []
    for f in canon.get("furniture", []) or []:
        item = {k: f.get(k) for k in ("uid", "item_id", "label", "cx", "cy", "w", "h", "rotation")}
        items.append(item)
    # stable order by uid so output is deterministic; never changes coordinates
    items.sort(key=lambda f: str(f.get("uid")))
    return items


def assemble(
    file_id: str, include_text: bool = False, include_vision: bool = False,
) -> dict[str, Any]:
    """Build the final canonical floor-plan JSON deterministically."""
    path, file_type, _ = floor_plan_service.get_floor_plan_file(file_id)

    furniture = _canonical_furniture(file_id)

    walls_raw: list[Any] = []
    openings_raw: list[dict[str, Any]] = []
    page: dict[str, float] = {}
    if file_type == "pdf":
        try:
            geo = geometry_extraction_service.extract_walls(str(path))
            walls_raw = geo.get("walls", []) or []
            openings_raw = geo.get("openings", []) or []
            page = geo.get("page", {}) or {}
        except Exception:  # noqa: BLE001 — a plan without vectors still yields furniture
            walls_raw, openings_raw, page = [], [], {}

    shapes = shape_extraction_service.extract_shapes(
        walls_raw, openings=openings_raw, source="vector")

    text_layer: list[dict[str, Any]] = []
    text_status = "skipped"
    if include_text:
        try:
            from app.services import text_extraction_service as tx
            img = _source_image(file_id)
            layer = tx.extract_text_from_image(img)
            text_layer = layer["text"]
            text_status = layer["engine"]
        except Exception as exc:  # noqa: BLE001 — OCR engine optional
            text_status = f"unavailable: {type(exc).__name__}"

    vision: dict[str, Any] = {"status": "skipped"}
    if include_vision:
        from app.services import vision_validation_service as vv
        extraction = {"text": text_layer, "walls": shapes["walls"],
                      "openings": shapes["openings"], "rooms": shapes["rooms"],
                      "furniture": []}
        try:
            vision = vv.run_vision_validation(_source_image(file_id), extraction)
        except Exception as exc:  # noqa: BLE001
            vision = {"status": f"error: {type(exc).__name__}"}

    architecture = {
        "coordinate_space": "world_px",
        "page": page,
        "walls": shapes["walls"],
        "junctions": shapes["junctions"],
        "rooms": shapes["rooms"],
        "openings": shapes["openings"],
    }

    canonical = {
        "file_id": file_id,
        "source_of_truth": "canonical_2d_geometry",
        "coordinate_space": "world_px",
        "furniture": furniture,                 # VERBATIM — never altered
        "architecture": architecture,
        "text": text_layer,
        "furniture_candidates": [],             # advisory detections only, never in `furniture`
        "vision_validation": vision,
    }
    canonical["report"] = _build_report(canonical, shapes, text_status)
    canonical["uncertainty_summary"] = _uncertainty_summary(canonical)
    canonical["content_hash"] = _content_hash(furniture, architecture)
    return canonical


def _build_report(
    canonical: dict[str, Any], shapes: dict[str, Any], text_status: str,
) -> dict[str, Any]:
    arch = canonical["architecture"]
    return {
        "furniture_count": len(canonical["furniture"]),
        "walls": len(arch["walls"]),
        "junctions": shapes["stats"].get("junctions", 0),
        "junctions_L": shapes["stats"].get("junctions_L", 0),
        "junctions_T": shapes["stats"].get("junctions_T", 0),
        "rooms_confirmed": shapes["stats"].get("rooms_confirmed", 0),
        "rooms_uncertain": shapes["stats"].get("rooms_uncertain", 0),
        "openings": len(arch["openings"]),
        "openings_valid": shapes["stats"].get("openings_valid", 0),
        "openings_uncertain": shapes["stats"].get("openings_uncertain", 0),
        "text_elements": len(canonical["text"]),
        "text_engine": text_status,
        "vision_status": canonical["vision_validation"].get("status"),
        "stages": {
            "ocr_text": "present" if canonical["text"] else "empty",
            "walls": "vector",
            "rooms": "topology",
            "openings": "wall_ownership",
            "furniture": "canonical_source_of_truth",
            "vision": canonical["vision_validation"].get("status"),
        },
    }


def _uncertainty_summary(canonical: dict[str, Any]) -> dict[str, Any]:
    arch = canonical["architecture"]
    uncertain_rooms = [r["id"] for r in arch["rooms"] if r.get("status") == "UNCERTAIN"]
    uncertain_openings = [o["id"] for o in arch["openings"] if o.get("status") != "VALID"]
    low_conf_text = [t.get("text") for t in canonical["text"] if t.get("low_confidence")]
    vis = canonical["vision_validation"].get("validated", {}) if isinstance(
        canonical["vision_validation"], dict) else {}
    return {
        "uncertain_rooms": uncertain_rooms,
        "uncertain_openings": uncertain_openings,
        "low_confidence_text": low_conf_text,
        "vision_uncertain": [u.get("entity_id") for u in (vis.get("uncertain") or [])],
        "vision_contradictions": len(vis.get("contradictions") or []),
        "counts": {
            "uncertain_rooms": len(uncertain_rooms),
            "uncertain_openings": len(uncertain_openings),
            "low_confidence_text": len(low_conf_text),
        },
    }


def _content_hash(furniture: list[dict[str, Any]], architecture: dict[str, Any]) -> str:
    """Deterministic hash over the AUTHORITATIVE furniture + architecture geometry."""
    payload = {
        "furniture": [{k: f.get(k) for k in _FURN_KEYS} for f in furniture],
        "walls": [[w["id"], w["x1"], w["y1"], w["x2"], w["y2"]] for w in architecture["walls"]],
        "rooms": [[r["id"], r.get("status"), r.get("polygon")] for r in architecture["rooms"]],
        "openings": [[o["id"], o.get("supporting_wall_id"), o.get("status")]
                     for o in architecture["openings"]],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ── Annotated source image ───────────────────────────────────────────────────

def _source_image(file_id: str):
    r = floor_plan_service.get_floor_plan_pil_image(file_id)
    return r[0] if isinstance(r, tuple) else r


def _rotated_rect(
    cx: float, cy: float, w: float, h: float, deg: float,
) -> list[tuple[float, float]]:
    r = math.radians(deg)
    cos, sin = math.cos(r), math.sin(r)
    return [(cx + dx * cos - dy * sin, cy + dx * sin + dy * cos)
            for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]


def render_annotated_image(file_id: str, assembled: dict[str, Any] | None = None) -> bytes:
    """Deterministically annotate the SOURCE plan image with the extracted walls,
    rooms, openings and canonical furniture. Purely a visualization — reads geometry,
    changes nothing. Returns PNG bytes."""
    from PIL import ImageDraw
    assembled = assembled or assemble(file_id)
    img = _source_image(file_id).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    arch = assembled["architecture"]
    page = arch.get("page") or {}
    # world px -> image px scale, derived from the real sizes (no guessing).
    pw = float(page.get("width") or img.width)
    k = img.width / pw if pw else 1.0

    def P(x: float, y: float) -> tuple[float, float]:
        return (x * k, y * k)

    for w in arch["walls"]:
        draw.line([P(w["x1"], w["y1"]), P(w["x2"], w["y2"])], fill=(120, 120, 120, 255), width=3)
    for r in arch["rooms"]:
        col = (0, 150, 0, 255) if r.get("status") == "CONFIRMED" else (210, 140, 0, 255)
        poly = [P(px, py) for px, py in r.get("polygon", [])]
        if len(poly) >= 3:
            draw.polygon(poly, outline=col)
    for o in arch["openings"]:
        col = (0, 0, 255, 255) if o.get("status") == "VALID" else (255, 0, 0, 255)
        cx, cy = P(o.get("cx", 0), o.get("cy", 0))
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline=col, width=2)
    for f in assembled["furniture"]:
        poly = [P(x, y) for x, y in _rotated_rect(
            float(f["cx"]), float(f["cy"]), float(f["w"]), float(f["h"]),
            float(f.get("rotation", 0)))]
        draw.polygon(poly, outline=(150, 90, 40, 255))
        draw.text((poly[0][0], poly[0][1] - 10), str(f["item_id"]), fill=(120, 60, 20, 255))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
