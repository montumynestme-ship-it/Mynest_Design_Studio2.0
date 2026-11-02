"""Deterministic canonical → SVG geometry reference.

A *derived* vector artifact that communicates the authoritative 2D design — room
boundaries, walls, doors/windows, and furniture footprints with stable IDs, types and
rotation — using the project's existing ``canonical_world_px`` coordinate frame
(world = pdf_pt × ``geometry_extraction_service.WORLD_SCALE``, top-left origin, y-down).

Design contract (NON-NEGOTIABLE, mirrors the rest of the pipeline):

* The canonical 2D design is the single source of truth. This module ONLY reads it; it
  never mutates canonical JSON, never invents a transform, and never "corrects" an
  uncertain placement to make anything pass. A missing/ambiguous field is REPORTED
  (``warnings``), not guessed.
* Furniture is positioned purely from the canonical transform (``cx``/``cy``/``w``/``h``/
  ``rotation``) — never from a screenshot or a detector. The rotated footprint uses the
  SAME formula as ``geometry_extraction_service._rotated_rect`` so the reference is
  geometrically identical to the deterministic base canvas.
* Architectural geometry (rooms/walls/openings) comes from the deterministic
  ``scene_service.build_scene`` output (also world px); it is kept visually SEPARATE from
  furniture (distinct ``<g>`` layers + styling), never merged into one ambiguous blob.

The output is deterministic: identical ``canonical`` + ``scene`` + options produce a
byte-identical SVG (stable ordering, fixed float formatting, no timestamps/randomness).

This is an ADDITIONAL artifact. It is NOT wired into the live fal.ai request: the active
``fal-ai/flux-kontext/dev`` *edit* endpoint takes a single ``image_url`` (the base
render), so a second conditioning image is left behind the ``try_rasterize_png`` /
endpoint integration boundary (see the audit) rather than silently changing provider
behaviour, defaults, or conditioning mode.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

from app.data.classes import CLASS_BY_ITEM_ID
from app.data.furniture_catalog import is_annotation

# Canonical frame label recorded on the artifact (matches schemas.floor_plan.PositionPayload).
COORDINATE_FRAME = "canonical_world_px"

# Visual tokens — deterministic, reference-style (NOT a photoreal render). Architecture is
# cool/neutral; furniture is warm; the two layers never share a colour.
_WALL_STROKE = "#1a1a1a"
_ROOM_CONFIRMED = "#2563eb"
_ROOM_UNCERTAIN = "#9ca3af"
_DOOR_COLOR = "#d4a017"   # gold — same semantic as the PDF door geometry
_WINDOW_COLOR = "#0ea5e9"  # cyan — same semantic as the PDF window geometry
_FURN_FILL = "#e9d5c3"
_FURN_STROKE = "#5a3c28"
_FURN_UNKNOWN_FILL = "#f0e6dc"  # a furniture item whose item_id is not in the catalog
_LABEL_COLOR = "#3a2819"


def _f(v: float) -> str:
    """Fixed 2-dp formatting so equal geometry yields byte-identical text."""
    return f"{float(v):.2f}"


def _attr(v: str) -> str:
    """Escape a value for an XML ATTRIBUTE context.

    ``xml.sax.saxutils.escape`` only handles ``& < >``; an attribute value also needs
    quotes escaped, otherwise a user-controlled uid/item_id/label containing ``"`` could
    break out of the attribute and inject arbitrary SVG/script. Used for every attribute
    that carries canonical identifiers; text-node content uses plain ``escape``.
    """
    return escape(str(v), {'"': "&quot;", "'": "&apos;"})


def _fingerprint(canonical: dict[str, Any]) -> str:
    """Stable furniture fingerprint for version binding / stale detection.

    Mirrors ``floor_plan_service._furniture_fingerprint`` (sorted JSON of the furniture
    list) so the reference's fingerprint tracks the exact authoritative inventory.
    """
    furniture = (canonical or {}).get("furniture", []) or []
    raw = json.dumps(furniture, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class GeometryReference:
    """A rendered geometry reference plus its provenance and per-item data contract."""

    svg: str
    items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def _rotated_corners(cx: float, cy: float, w: float, h: float, deg: float) -> list[tuple[float, float]]:
    """Footprint corners — identical math to geometry_extraction_service._rotated_rect."""
    r = math.radians(deg)
    cos, sin = math.cos(r), math.sin(r)
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return [(cx + dx * cos - dy * sin, cy + dx * sin + dy * cos) for dx, dy in corners]


def _uid_to_room(scene: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    """Map furniture uid -> {room_id, room_label} using the PROVEN scene assignment.

    Read-only: a furniture item's room is taken from the deterministic reconstruction
    (``scene.rooms[].furniture[].id/room_id``), never guessed. Items the scene did not
    assign simply have no entry here (reported as UNASSIGNED, not invented).
    """
    out: dict[str, dict[str, str]] = {}
    for room in (scene or {}).get("rooms", []) or []:
        rid = str(room.get("id") or "")
        rlabel = str(room.get("label") or rid)
        for it in room.get("furniture", []) or []:
            uid = it.get("id") or it.get("uid")
            if uid:
                out[str(uid)] = {"room_id": rid, "room_label": rlabel}
    return out


def reference_items(
    canonical: dict[str, Any], scene: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """The per-item data contract echoed from canonical (no invented fields).

    Returns ``(items, warnings)``. Each item preserves the AVAILABLE canonical fields:
    ``uid``, ``item_id`` (type), ``cx``/``cy`` (position), ``w``/``h`` (dimensions),
    ``rotation``, and the room assignment (from the proven scene, or the user-authored
    ``render_room``/``room_membership`` intent, else ``None``). A ``missing`` list names
    required fields that were absent — surfaced, never back-filled.
    """
    uid_room = _uid_to_room(scene)
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    furniture = (canonical or {}).get("furniture", []) or []
    # Deterministic ordering by uid (stable across equal inputs).
    for f in sorted(furniture, key=lambda x: str(x.get("uid", ""))):
        item_id = f.get("item_id")
        uid = f.get("uid")
        if is_annotation(item_id):
            continue  # styling/annotation marker — not a physical furniture object
        missing = [k for k in ("uid", "item_id", "cx", "cy", "w", "h") if f.get(k) is None]
        room = uid_room.get(str(uid))
        room_id = room["room_id"] if room else (f.get("render_room") or f.get("room_membership"))
        if item_id is not None and item_id not in CLASS_BY_ITEM_ID:
            warnings.append(f"unknown item_id '{item_id}' (uid={uid}) not in canonical catalog")
        if missing:
            warnings.append(f"furniture uid={uid} missing required field(s): {', '.join(missing)}")
        items.append(
            {
                "uid": uid,
                "item_id": item_id,
                "cx": f.get("cx"),
                "cy": f.get("cy"),
                "w": f.get("w"),
                "h": f.get("h"),
                "rotation": f.get("rotation", 0.0),
                "room_id": room_id,
                "room_assignment_source": (
                    "scene" if room else ("canonical_intent" if room_id else "unassigned")
                ),
                "missing": missing,
            }
        )
    return items, warnings


def _render_architecture(scene: dict[str, Any] | None) -> tuple[str, int, int]:
    """Rooms + walls + openings as a single ``architecture`` layer. Returns (svg, wall_count, opening_count)."""
    if not scene:
        return '<g id="architecture"/>', 0, 0
    parts: list[str] = ['<g id="architecture" fill="none">']

    # Rooms (sorted by id for determinism). UNCERTAIN rooms are dashed so the reviewer
    # can see which boundaries are geometry-proven vs reconstructed-but-unconfirmed.
    opening_count = 0
    for room in sorted(scene.get("rooms", []) or [], key=lambda r: str(r.get("id", ""))):
        boundary = room.get("boundary") or []
        status = str(room.get("status") or "").upper()
        stroke = _ROOM_CONFIRMED if status == "CONFIRMED" else _ROOM_UNCERTAIN
        dash = "" if status == "CONFIRMED" else ' stroke-dasharray="12 8"'
        if len(boundary) >= 3:
            pts = " ".join(f"{_f(p[0])},{_f(p[1])}" for p in boundary)
            parts.append(
                f'<polygon points="{pts}" stroke="{stroke}" stroke-width="2"{dash}/>'
            )
            xs = [p[0] for p in boundary]
            ys = [p[1] for p in boundary]
            lbl = escape(str(room.get("label") or room.get("id") or ""))
            parts.append(
                f'<text x="{_f(sum(xs) / len(xs))}" y="{_f(sum(ys) / len(ys))}" '
                f'fill="{stroke}" font-size="18" font-family="sans-serif" '
                f'text-anchor="middle">{lbl}</text>'
            )
        # Openings carried on the room (authoritative PDF door/window geometry).
        for door in room.get("doors", []) or []:
            opening_count += 1
            parts.append(_opening_marker(door, _DOOR_COLOR))
        for win in room.get("windows", []) or []:
            opening_count += 1
            parts.append(_opening_marker(win, _WINDOW_COLOR))

    # Walls (raw world-px segments from extraction; kept in source order — deterministic).
    walls = scene.get("walls", []) or []
    for seg in walls:
        if len(seg) >= 4:
            parts.append(
                f'<line x1="{_f(seg[0])}" y1="{_f(seg[1])}" x2="{_f(seg[2])}" '
                f'y2="{_f(seg[3])}" stroke="{_WALL_STROKE}" stroke-width="4"/>'
            )
    parts.append("</g>")
    return "".join(parts), len(walls), opening_count


def _opening_marker(opening: dict[str, Any], color: str) -> str:
    cx = opening.get("cx")
    cy = opening.get("cy")
    if cx is None or cy is None:
        return ""
    return (
        f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="6" fill="{color}" '
        f'stroke="#ffffff" stroke-width="1"/>'
    )


def _render_furniture(items: list[dict[str, Any]]) -> str:
    """Furniture footprints as a separate ``furniture`` layer.

    Each item is its exact canonical footprint (rotated w×h at cx,cy), an orientation
    tick (centre → +x local axis), and a compact ``item_id`` label. The footprint is the
    geometry; the label/colour merely identify it. Items missing a transform are skipped
    here (already reported in ``warnings``) — never drawn at a guessed location.
    """
    parts: list[str] = ['<g id="furniture">']
    for it in items:
        if it["missing"]:
            continue
        cx, cy = float(it["cx"]), float(it["cy"])
        w, h = float(it["w"]), float(it["h"])
        rot = float(it.get("rotation") or 0.0)
        info = CLASS_BY_ITEM_ID.get(it["item_id"])
        fill = _FURN_FILL if info is not None else _FURN_UNKNOWN_FILL
        corners = _rotated_corners(cx, cy, w, h, rot)
        pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in corners)
        # Orientation tick: local +x half-edge midpoint, rotated.
        r = math.radians(rot)
        tx = cx + (w / 2) * math.cos(r)
        ty = cy + (w / 2) * math.sin(r)
        item_id_s = str(it["item_id"] or "?")
        label_text = escape(item_id_s)  # text-node context
        parts.append(
            f'<g data-uid="{_attr(str(it["uid"]))}" data-item-id="{_attr(item_id_s)}">'
            f'<polygon points="{pts}" fill="{fill}" stroke="{_FURN_STROKE}" stroke-width="2"/>'
            f'<line x1="{_f(cx)}" y1="{_f(cy)}" x2="{_f(tx)}" y2="{_f(ty)}" '
            f'stroke="{_FURN_STROKE}" stroke-width="1.5"/>'
            f'<text x="{_f(cx)}" y="{_f(cy)}" fill="{_LABEL_COLOR}" font-size="12" '
            f'font-family="sans-serif" text-anchor="middle">{label_text}</text>'
            f"</g>"
        )
    parts.append("</g>")
    return "".join(parts)


def build_geometry_reference(
    canonical: dict[str, Any],
    scene: dict[str, Any] | None = None,
    *,
    design_version_id: str | None = None,
    geometry_fingerprint: str | None = None,
) -> GeometryReference:
    """Build the deterministic SVG geometry reference from canonical + scene.

    ``design_version_id`` / ``geometry_fingerprint`` are embedded on the root ``<svg>``
    (and in ``<metadata>``) so the artifact is provably bound to one immutable design
    version and a later edit's reference can be detected as stale
    (see ``validate_reference_freshness``). ``geometry_fingerprint`` defaults to a
    furniture fingerprint consistent with ``floor_plan_service._furniture_fingerprint``.
    """
    fp = geometry_fingerprint or _fingerprint(canonical)
    page = (scene or {}).get("page") or {}
    # View box: the world-px page when a scene is present, else the furniture bounds (with
    # a margin) so a vector-less plan still produces a valid, framed reference.
    width = float(page.get("width") or 0.0)
    height = float(page.get("height") or 0.0)
    items, warnings = reference_items(canonical, scene)
    if width <= 0 or height <= 0:
        drawn = [it for it in items if not it["missing"]]
        if drawn:
            maxx = max(float(it["cx"]) + float(it["w"]) / 2 for it in drawn)
            maxy = max(float(it["cy"]) + float(it["h"]) / 2 for it in drawn)
            width = width or (maxx + 50.0)
            height = height or (maxy + 50.0)
        else:
            width = width or 1000.0
            height = height or 750.0

    arch_svg, wall_count, opening_count = _render_architecture(scene)
    furn_svg = _render_furniture(items)

    room_count = len((scene or {}).get("rooms", []) or [])
    meta = {
        "design_version_id": design_version_id,
        "geometry_fingerprint": fp,
        "coordinate_frame": COORDINATE_FRAME,
        "view_width": round(width, 2),
        "view_height": round(height, 2),
        "scale": (scene or {}).get("page", {}).get("scale"),
        "room_count": room_count,
        "wall_count": wall_count,
        "opening_count": opening_count,
        "furniture_count": len(items),
        "furniture_drawn": len([it for it in items if not it["missing"]]),
        "warnings": warnings,
    }
    meta_json = escape(json.dumps(meta, sort_keys=True, default=str))
    dvid_attr = _attr(str(design_version_id)) if design_version_id is not None else ""

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width)} {_f(height)}" '
        f'width="{_f(width)}" height="{_f(height)}" '
        f'data-coordinate-frame="{COORDINATE_FRAME}" '
        f'data-design-version-id="{dvid_attr}" '
        f'data-geometry-fingerprint="{_attr(fp)}">'
        f"<metadata>{meta_json}</metadata>"
        f'<rect x="0" y="0" width="{_f(width)}" height="{_f(height)}" fill="#ffffff"/>'
        f"{arch_svg}{furn_svg}"
        f"</svg>"
    )
    return GeometryReference(svg=svg, items=items, warnings=warnings, meta=meta)


_DVID_RE = re.compile(r'data-design-version-id="([^"]*)"')
_FP_RE = re.compile(r'data-geometry-fingerprint="([^"]*)"')


def validate_reference_freshness(
    svg: str,
    *,
    expected_version_id: str | None = None,
    expected_fingerprint: str | None = None,
) -> tuple[bool, str]:
    """Reject a stale/mismatched reference. Returns ``(ok, reason)``.

    A reference is only trusted for a generation when its embedded design version AND
    geometry fingerprint match what the caller expects — exactly the snapshot-safety
    rule the rest of the pipeline enforces. Never a silent pass on a mismatch.
    """
    dvid = _DVID_RE.search(svg)
    fp = _FP_RE.search(svg)
    if expected_version_id is not None:
        if dvid is None or dvid.group(1) != str(expected_version_id):
            got = dvid.group(1) if dvid else None
            return False, f"STALE_REFERENCE: design_version_id mismatch (got={got}, expected={expected_version_id})"
    if expected_fingerprint is not None:
        if fp is None or fp.group(1) != str(expected_fingerprint):
            got = fp.group(1) if fp else None
            return False, f"STALE_REFERENCE: geometry_fingerprint mismatch (got={got}, expected={expected_fingerprint})"
    return True, "OK"


def try_rasterize_png(svg: str, *, scale: float = 1.0) -> bytes | None:
    """Best-effort SVG→PNG at a controlled scale. INTEGRATION BOUNDARY.

    Returns PNG bytes when an SVG rasterizer (``cairosvg``) is importable, else ``None``
    — never a hard new dependency and never a silent partial render. This is the seam a
    future provider-conditioning path would use IF the selected fal.ai endpoint gained a
    compatible additional-image input; it is deliberately NOT called by the live request.
    """
    try:
        import cairosvg  # type: ignore
    except Exception:  # noqa: BLE001 — optional; absence is reported by returning None
        return None
    return cairosvg.svg2png(bytestring=svg.encode("utf-8"), scale=scale)
