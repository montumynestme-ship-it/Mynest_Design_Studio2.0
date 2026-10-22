"""Deterministic spatial validation over a canonical design (PRD §20 / §26).

Runs furniture-furniture collision (SAT) and room-containment checks. Wall and
door-clearance checks activate automatically once walls/doors exist in the
canonical payload.

Also provides `validate_scene_against_canonical` (spec §L): a deterministic
geometry-fidelity check that the reconstructed 3D scene (the geometry the Flux
base render encodes) exactly preserves the authoritative 2D plan — room count,
boundaries, walls, per-room doors/windows, and every furniture item's
type/center/size/rotation. AI output must never be considered geometry-faithful
solely because the API returned an image; it is faithful only when it was an
image-to-image render of a base whose geometry passes this check.
"""

import math
from io import BytesIO
from typing import Any

from PIL import Image
from shapely.geometry import Polygon

from app.data import furniture_catalog
from app.services import geometry_service as geo
from app.services.geometry_service import OrientedRect

# Furniture transforms are integer/rounded world px; anything above this is a
# real change, not float noise.
_POS_EPS = 0.5
_ROT_EPS = 0.5


def _rect(item: dict[str, Any]) -> OrientedRect:
    return OrientedRect(
        float(item["cx"]),
        float(item["cy"]),
        float(item["w"]),
        float(item["h"]),
        float(item.get("rotation", 0)),
    )


def _label(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("item_id") or "item")


def _polygon(room: dict[str, Any]) -> list[geo.Point]:
    return [(float(p[0]), float(p[1])) for p in room.get("polygon", [])]


def validate_canonical(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    # Room-tag annotations are not furniture — exclude from geometry/collision checks.
    furniture: list[dict[str, Any]] = furniture_catalog.strip_annotations(
        canonical.get("furniture", []) or []
    )
    rooms: list[dict[str, Any]] = canonical.get("rooms", []) or []

    # 1) Furniture-furniture collisions (SAT).
    for i in range(len(furniture)):
        for j in range(i + 1, len(furniture)):
            if geo.rects_collide(_rect(furniture[i]), _rect(furniture[j])):
                msg = f"Furniture overlaps: {_label(furniture[i])} ↔ {_label(furniture[j])}"
                results.append(
                    {
                        "rule": "checkFurnitureCollision",
                        "severity": "warning",
                        "message": msg,
                        "targets": [furniture[i].get("uid"), furniture[j].get("uid")],
                    }
                )

    # 2) Room containment (only when rooms are defined).
    if rooms:
        polys = [_polygon(r) for r in rooms]
        for f in furniture:
            center = (float(f["cx"]), float(f["cy"]))
            if not any(geo.point_in_polygon(center, poly) for poly in polys if len(poly) >= 3):
                results.append(
                    {
                        "rule": "validateRoomContainment",
                        "severity": "warning",
                        "message": f"{_label(f)} is outside all rooms (unassigned location)",
                        "targets": [f.get("uid")],
                    }
                )

    if not results:
        results.append(
            {
                "rule": "all",
                "severity": "valid",
                "message": "No spatial issues detected.",
                "targets": [],
            }
        )
    return results


def _fkey(item: dict[str, Any]) -> str:
    """Stable identity for a furniture item — prefer uid, then id."""
    return str(item.get("uid") or item.get("id") or item.get("item_id") or "")


def _ftype(item: dict[str, Any]) -> str:
    return str(item.get("item_id") or item.get("type") or "")


def _scene_furniture(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every room's furniture from a build_scene() payload."""
    out: list[dict[str, Any]] = []
    for room in scene.get("rooms", []) or []:
        out.extend(room.get("furniture", []) or [])
    return out


def _wall_segments(scene: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    """Extract non-degenerate wall segments from either scene representation."""
    segs: list[tuple[float, float, float, float]] = []
    for w in scene.get("walls", []) or []:
        try:
            if isinstance(w, (list | tuple)) and len(w) >= 4:
                x1, y1, x2, y2 = (float(w[0]), float(w[1]), float(w[2]), float(w[3]))
            elif isinstance(w, dict) and all(k in w for k in ("x1", "y1", "x2", "y2")):
                x1, y1, x2, y2 = float(w["x1"]), float(w["y1"]), float(w["x2"]), float(w["y2"])
            else:
                continue
        except (TypeError, ValueError):
            continue
        if math.hypot(x2 - x1, y2 - y1) > 1e-6:
            segs.append((x1, y1, x2, y2))
    return segs


# Room states whose geometry is proven from source walls (safe to trust as an
# architectural boundary) vs. states that must NOT be accepted as faithful.
_PROVEN_STATES = {"CONFIRMED"}
_UNPROVEN_STATES = {"UNSUPPORTED", "UNCERTAIN", "INVALID"}


def validate_scene_against_canonical(
    canonical: dict[str, Any],
    scene: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic geometry-fidelity check (spec §L).

    Compares the reconstructed 3D `scene` (from scene_service.build_scene) to the
    authoritative `canonical` plan and returns a structured report:

        {
          "status": "GEOMETRY_FAITHFUL" | "GEOMETRY_MISMATCH",
          "geometry_faithful": bool,
          "checks": { <name>: {"passed": bool, ...} },
          "mismatches": [ "human-readable reason", ... ],
        }

    The canonical furniture (uid, item_id, cx, cy, w, h, rotation) is the source
    of truth. Any added / removed / moved / resized / rotated / retyped item, or
    a missing room boundary / opening, fails the check. This is what makes an AI
    render trustworthy: it is only geometry-faithful if it enhanced a base render
    whose scene passes here.
    """
    # Exclude room-tag annotations so the canonical↔scene furniture counts align
    # (annotations are stripped from the reconstructed scene too).
    canonical_furniture = furniture_catalog.strip_annotations(canonical.get("furniture", []) or [])
    scene_furniture = _scene_furniture(scene)
    rooms = scene.get("rooms", []) or []
    doors = scene.get("doors", []) or []
    windows = scene.get("windows", []) or []

    checks: dict[str, Any] = {}
    mismatches: list[str] = []

    # 1. Room count / identity / topology.
    # A geometry-faithful scene has at least one room for a non-empty plan, a room
    # count matching the canonical plan (when it enumerates rooms), and NO room
    # whose geometry could not be proven from source walls (UNSUPPORTED/INVALID).
    canonical_rooms = canonical.get("rooms") or []
    unproven_rooms = [
        (r.get("label") or r.get("id"))
        for r in rooms
        if str(r.get("validation_status", "")).upper() in _UNPROVEN_STATES
    ]
    count_expected_ok = (len(rooms) == len(canonical_rooms)) if canonical_rooms else True
    rc_passed = (
        (len(rooms) >= 1 if canonical_furniture else True)
        and count_expected_ok
        and not unproven_rooms
    )
    checks["room_count"] = {
        "passed": rc_passed,
        "count": len(rooms),
        "expected": len(canonical_rooms) or None,
        "unproven_rooms": unproven_rooms,
    }
    if len(rooms) < 1 and canonical_furniture:
        mismatches.append("No rooms were reconstructed for a non-empty plan.")
    if not count_expected_ok:
        mismatches.append(
            "Room count differs from canonical: "
            f"scene={len(rooms)} canonical={len(canonical_rooms)}")
    if unproven_rooms:
        mismatches.append(f"Rooms whose geometry is not proven from walls: {unproven_rooms}")

    # 2. Boundaries — every architectural room needs a CLOSED, non-zero-area
    # polygon (a furniture-fallback room is exempt from carrying one).
    missing_boundary: list[Any] = []
    degenerate_boundary: list[Any] = []
    for r in rooms:
        is_arch = str(r.get("geometry_source", "")).startswith("architectural")
        boundary = r.get("boundary") or []
        if is_arch and len(boundary) < 4:
            missing_boundary.append(r.get("label") or r.get("id"))
            continue
        if len(boundary) >= 4:
            try:
                if Polygon([(float(p[0]), float(p[1])) for p in boundary]).area <= 0.0:
                    degenerate_boundary.append(r.get("label") or r.get("id"))
            except (TypeError, ValueError, IndexError):
                degenerate_boundary.append(r.get("label") or r.get("id"))
    checks["boundaries"] = {
        "passed": not missing_boundary and not degenerate_boundary,
        "architectural_rooms": sum(
            1 for r in rooms if str(r.get("geometry_source", "")).startswith("architectural")),
        "missing_boundary": missing_boundary,
        "zero_area_boundary": degenerate_boundary,
    }
    if missing_boundary:
        mismatches.append(f"Architectural rooms without a closed boundary: {missing_boundary}")
    if degenerate_boundary:
        mismatches.append(f"Rooms with a zero-area boundary polygon: {degenerate_boundary}")

    # 3. Real wall-geometry validation (never hardcoded): the scene must carry at
    # least one non-degenerate wall segment when the plan has architecture.
    wall_segments = _wall_segments(scene)
    has_architecture = bool(canonical_furniture) or bool(rooms)
    walls_ok = (len(wall_segments) > 0) if has_architecture else True
    checks["walls"] = {
        "passed": walls_ok,
        "segment_count": len(wall_segments),
        "structured_count": len(scene.get("structured_walls") or []),
    }
    if not walls_ok:
        mismatches.append("No valid wall segments in a scene that should have architecture.")

    # 4. Openings attributed to exactly one room (no global broadcast).
    def _opening_uniqueness(
        kind: str, per_room_key: str, global_list: list[dict[str, Any]]
    ) -> None:
        seen: dict[str, int] = {}
        off_wall: list[str] = []
        for r in rooms:
            for o in r.get(per_room_key, []) or []:
                oid = str(o.get("id") or f"{o.get('x')},{o.get('y')}")
                seen[oid] = seen.get(oid, 0) + 1
                # When the opening carries on-wall metadata, it must actually be
                # tied to a real wall segment (never broadcast off-wall).
                if "on_wall" in o and not o.get("on_wall"):
                    off_wall.append(oid)
        duped = [oid for oid, n in seen.items() if n > 1]
        passed = not duped and not off_wall
        checks[kind] = {
            "passed": passed,
            "assigned": len(seen),
            "global": len(global_list),
            "duplicated_across_rooms": duped,
            "off_wall": off_wall,
        }
        if duped:
            mismatches.append(f"{kind}: opening(s) assigned to more than one room: {duped}")
        if off_wall:
            mismatches.append(f"{kind}: opening(s) not on any wall segment: {off_wall}")

    _opening_uniqueness("doors", "doors", doors)
    _opening_uniqueness("windows", "windows", windows)

    # 5. Furniture count.
    count_ok = len(scene_furniture) == len(canonical_furniture)
    checks["furniture_count"] = {
        "passed": count_ok,
        "canonical": len(canonical_furniture),
        "scene": len(scene_furniture),
    }
    if not count_ok:
        mismatches.append(
            f"Furniture count changed: canonical={len(canonical_furniture)} "
            f"scene={len(scene_furniture)}"
        )

    # 6. Per-item type + transform preservation (matched by uid).
    scene_by_key = {_fkey(f): f for f in scene_furniture}
    type_ok = True
    transform_ok = True
    for c in canonical_furniture:
        key = _fkey(c)
        s = scene_by_key.get(key)
        if s is None:
            transform_ok = False
            mismatches.append(f"Furniture '{key}' is missing from the reconstructed scene.")
            continue
        if _ftype(c) != _ftype(s):
            type_ok = False
            mismatches.append(f"Furniture '{key}' type changed: {_ftype(c)} -> {_ftype(s)}")
        for attr in ("cx", "cy", "w", "h"):
            if abs(float(c.get(attr, 0)) - float(s.get(attr, 0))) > _POS_EPS:
                transform_ok = False
                mismatches.append(
                    f"Furniture '{key}' {attr} changed: {c.get(attr)} -> {s.get(attr)}"
                )
        # Rotation compared modulo 360.
        dr = abs((float(c.get("rotation", 0)) - float(s.get("rotation", 0))) % 360.0)
        dr = min(dr, 360.0 - dr)
        if dr > _ROT_EPS:
            transform_ok = False
            mismatches.append(
                f"Furniture '{key}' rotation changed: {c.get('rotation')} -> {s.get('rotation')}"
            )
    extra_keys = set(scene_by_key) - {_fkey(c) for c in canonical_furniture}
    if extra_keys:
        transform_ok = False
        mismatches.append(
            f"Reconstructed scene has furniture absent from canonical: {sorted(extra_keys)}"
        )

    checks["furniture_types"] = {"passed": type_ok}
    checks["furniture_transforms"] = {"passed": transform_ok}

    # 7. Assignment: every canonical item lands in EXACTLY one reconstructed room
    # (none unassigned, none double-counted across rooms).
    assign_counts: dict[str, int] = {}
    for r in rooms:
        for f in r.get("furniture", []) or []:
            assign_counts[_fkey(f)] = assign_counts.get(_fkey(f), 0) + 1
    duplicated_assign = sorted(k for k, n in assign_counts.items() if n > 1)
    unassigned = sorted(
        _fkey(c) for c in canonical_furniture if assign_counts.get(_fkey(c), 0) == 0)
    assign_ok = not duplicated_assign and not unassigned
    checks["furniture_assignment"] = {
        "passed": assign_ok,
        "duplicated_across_rooms": duplicated_assign,
        "unassigned": unassigned,
    }
    if duplicated_assign:
        mismatches.append(f"Furniture assigned to more than one room: {duplicated_assign}")
    if unassigned:
        mismatches.append(f"Canonical furniture not assigned to any room: {unassigned}")

    geometry_faithful = all(c.get("passed", False) for c in checks.values())
    return {
        "status": "GEOMETRY_FAITHFUL" if geometry_faithful else "GEOMETRY_MISMATCH",
        "geometry_faithful": geometry_faithful,
        "checks": checks,
        "mismatches": mismatches,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC AUTHORITATIVE-2D → 3D CONVERSION FIDELITY GATE
#
# The authoritative 2D design is the SOURCE OF TRUTH. The deterministic 3D scene
# (what Three.js reproduces) must carry EVERY object 1:1 with the same identity and
# transform. This gate runs BEFORE any base render / provider call. On failure it
# returns a STRUCTURED failure and the caller must NOT auto-correct, invent, move,
# or fabricate anything, and must NOT call fal.ai — it simply refuses.
#
# Tolerances match the proven §L thresholds (never silently looser). Fields that the
# authoritative side does not specify (room / wall offset / wall-room relationship)
# are compared ONLY when the expected object provides them, so an honest source that
# omits a field never produces a false mismatch.
# ─────────────────────────────────────────────────────────────────────────────

_D2D_POS_TOL = 0.5     # world px — furniture centre & wall endpoints
_D2D_DIM_TOL = 0.5     # world px — width / depth
_D2D_ROT_TOL = 0.5     # degrees — rotation / orientation
_D2D_SCALE_TOL = 0.01  # unitless — scale multiplier
_D2D_OFFSET_TOL = 0.5  # world px — opening offset along its wall


def _angle_delta(a: float, b: float) -> float:
    d = abs((float(a) - float(b)) % 360.0)
    return min(d, 360.0 - d)


def _d2d_norm_furniture(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": str(f.get("uid") or f.get("id") or ""),
        "type": str(f.get("item_id") or f.get("type") or ""),
        "room": (None if f.get("room") is None and f.get("room_id") is None
                 else str(f.get("room") if f.get("room") is not None else f.get("room_id"))),
        "cx": float(f.get("cx", 0.0)),
        "cy": float(f.get("cy", 0.0)),
        "w": float(f.get("w", 0.0)),
        "h": float(f.get("h", 0.0)),
        "rotation": float(f.get("rotation", 0.0) or 0.0),
        "scale": float(f.get("scale", 1.0) if f.get("scale") is not None else 1.0),
    }


def _d2d_norm_opening(o: dict[str, Any]) -> dict[str, Any]:
    wid = o.get("wall_id")
    if wid is None:
        wid = o.get("supporting_wall_id")
    off = o.get("offset")
    if off is None and isinstance(o.get("wall_relative"), dict):
        off = o["wall_relative"].get("along_px")
    return {
        "id": str(o.get("id") or o.get("uid") or ""),
        "wall_id": (None if wid is None else str(wid)),
        "offset": (None if off is None else float(off)),
        "w": float(o.get("w", 0.0)),
        "h": float(o.get("h", 0.0)),
        "rotation": float(o.get("rotation", o.get("wall_angle_deg", 0.0)) or 0.0),
    }


def _d2d_norm_wall(w: Any) -> dict[str, Any]:
    if isinstance(w, (list, tuple)):
        return {"id": None, "x1": float(w[0]), "y1": float(w[1]),
                "x2": float(w[2]), "y2": float(w[3]), "room": None}
    room = w.get("room") if w.get("room") is not None else w.get("room_id")
    return {
        "id": (None if w.get("id") is None else str(w.get("id"))),
        "x1": float(w.get("x1", 0.0)), "y1": float(w.get("y1", 0.0)),
        "x2": float(w.get("x2", 0.0)), "y2": float(w.get("y2", 0.0)),
        "room": (None if room is None else str(room)),
    }


def _dup_ids(items: list[dict[str, Any]], key: str) -> list[str]:
    seen: dict[str, int] = {}
    for it in items:
        seen[it[key]] = seen.get(it[key], 0) + 1
    return sorted(k for k, n in seen.items() if n > 1 and k != "")


def validate_2d_to_3d(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    pos_tol: float = _D2D_POS_TOL,
    dim_tol: float = _D2D_DIM_TOL,
    rot_tol: float = _D2D_ROT_TOL,
    scale_tol: float = _D2D_SCALE_TOL,
    offset_tol: float = _D2D_OFFSET_TOL,
) -> dict[str, Any]:
    """Deterministic per-object equality between the authoritative 2D design and the
    deterministic 3D scene it must reproduce.

    Both ``expected`` (authoritative 2D) and ``actual`` (3D scene) are dicts with any
    of the keys ``furniture`` / ``doors`` / ``windows`` / ``walls``. For every object
    the mapping must be a strict bijection by stable id/uid:

      furniture: uid unchanged · type unchanged · exactly one 3D object per uid ·
                 position/dimensions/rotation/scale within tolerance ·
                 room assignment unchanged · no missing · no extra · no duplicate uid
      doors/windows: id unchanged · wall association unchanged · offset/position ·
                 dimensions · orientation · no missing · no extra openings
      walls:     id unchanged · endpoints/geometry · room relationship

    Returns a STRUCTURED result and NEVER mutates its inputs::

        {"passed": bool,
         "status": "SCENE_FAITHFUL" | "SCENE_VALIDATION_FAILED",
         "error_code": None | "SCENE_2D_3D_MISMATCH",
         "mismatches": [{"category","id","reason","expected","actual"}, ...],
         "counts": {"furniture": {"expected","actual"}, "doors": ..., ...}}
    """
    mismatches: list[dict[str, Any]] = []

    def _fail(category: str, oid: str, reason: str,
              exp: Any = None, act: Any = None) -> None:
        mismatches.append({"category": category, "id": oid, "reason": reason,
                           "expected": exp, "actual": act})

    # ── furniture ────────────────────────────────────────────────────────────
    exp_f = [_d2d_norm_furniture(f) for f in (expected.get("furniture") or [])]
    act_f = [_d2d_norm_furniture(f) for f in (actual.get("furniture") or [])]
    for side, items in (("expected", exp_f), ("actual", act_f)):
        for dup in _dup_ids(items, "uid"):
            _fail("FURNITURE_DUPLICATE_UID", dup,
                  f"uid '{dup}' appears more than once on the {side} side "
                  f"(every 2D uid must map to exactly one 3D object)")
    exp_fm = {f["uid"]: f for f in exp_f}
    act_fm = {f["uid"]: f for f in act_f}
    if len(exp_f) != len(act_f):
        _fail("FURNITURE_COUNT", "", "furniture object count changed",
              len(exp_f), len(act_f))
    for uid in exp_fm.keys() - act_fm.keys():
        _fail("FURNITURE_MISSING", uid, f"furniture '{uid}' is missing from the 3D scene")
    for uid in act_fm.keys() - exp_fm.keys():
        _fail("FURNITURE_EXTRA", uid, f"furniture '{uid}' exists in the 3D scene but not in the 2D design")
    for uid in exp_fm.keys() & act_fm.keys():
        e, a = exp_fm[uid], act_fm[uid]
        if e["type"] != a["type"]:
            _fail("FURNITURE_TYPE", uid, "furniture type changed", e["type"], a["type"])
        if abs(e["cx"] - a["cx"]) > pos_tol or abs(e["cy"] - a["cy"]) > pos_tol:
            _fail("FURNITURE_MOVED", uid, "furniture position changed beyond tolerance",
                  [e["cx"], e["cy"]], [a["cx"], a["cy"]])
        if abs(e["w"] - a["w"]) > dim_tol or abs(e["h"] - a["h"]) > dim_tol:
            _fail("FURNITURE_RESIZED", uid, "furniture dimensions changed beyond tolerance",
                  [e["w"], e["h"]], [a["w"], a["h"]])
        if _angle_delta(e["rotation"], a["rotation"]) > rot_tol:
            _fail("FURNITURE_ROTATED", uid, "furniture rotation changed beyond tolerance",
                  e["rotation"], a["rotation"])
        if abs(e["scale"] - a["scale"]) > scale_tol:
            _fail("FURNITURE_SCALED", uid, "furniture scale changed beyond tolerance",
                  e["scale"], a["scale"])
        if e["room"] is not None and e["room"] != a["room"]:
            _fail("FURNITURE_WRONG_ROOM", uid, "furniture room assignment changed",
                  e["room"], a["room"])

    # ── openings (doors / windows) ─────────────────────────────────────────────
    def _check_openings(kind: str) -> None:
        exp_o = [_d2d_norm_opening(o) for o in (expected.get(kind) or [])]
        act_o = [_d2d_norm_opening(o) for o in (actual.get(kind) or [])]
        cat = kind[:-1].upper()  # "doors" -> "DOOR", "windows" -> "WINDOW"
        for side, items in (("expected", exp_o), ("actual", act_o)):
            for dup in _dup_ids(items, "id"):
                _fail(f"{cat}_DUPLICATE_ID", dup,
                      f"{kind[:-1]} id '{dup}' appears more than once on the {side} side")
        em = {o["id"]: o for o in exp_o}
        am = {o["id"]: o for o in act_o}
        for oid in em.keys() - am.keys():
            _fail(f"{cat}_MISSING", oid, f"{kind[:-1]} '{oid}' is missing from the 3D scene")
        for oid in am.keys() - em.keys():
            _fail(f"{cat}_EXTRA", oid, f"{kind[:-1]} '{oid}' exists in the 3D scene but not in the 2D design")
        for oid in em.keys() & am.keys():
            e, a = em[oid], am[oid]
            if abs(e["w"] - a["w"]) > dim_tol or abs(e["h"] - a["h"]) > dim_tol:
                _fail(f"{cat}_RESIZED", oid, f"{kind[:-1]} dimensions changed beyond tolerance",
                      [e["w"], e["h"]], [a["w"], a["h"]])
            if _angle_delta(e["rotation"], a["rotation"]) > rot_tol:
                _fail(f"{cat}_REORIENTED", oid, f"{kind[:-1]} orientation changed beyond tolerance",
                      e["rotation"], a["rotation"])
            if e["wall_id"] is not None and e["wall_id"] != a["wall_id"]:
                _fail(f"{cat}_WALL_CHANGED", oid, f"{kind[:-1]} wall association changed",
                      e["wall_id"], a["wall_id"])
            if e["offset"] is not None and (
                a["offset"] is None or abs(e["offset"] - a["offset"]) > offset_tol
            ):
                _fail(f"{cat}_MOVED", oid, f"{kind[:-1]} offset/position changed beyond tolerance",
                      e["offset"], a["offset"])

    _check_openings("doors")
    _check_openings("windows")

    # ── walls ──────────────────────────────────────────────────────────────────
    exp_w = [_d2d_norm_wall(w) for w in (expected.get("walls") or [])]
    act_w = [_d2d_norm_wall(w) for w in (actual.get("walls") or [])]
    # Walls must carry a stable id to be compared by identity; fall back to index.
    for lst in (exp_w, act_w):
        for i, w in enumerate(lst):
            if w["id"] is None:
                w["id"] = f"wall_{i}"
    for side, items in (("expected", exp_w), ("actual", act_w)):
        for dup in _dup_ids(items, "id"):
            _fail("WALL_DUPLICATE_ID", dup, f"wall id '{dup}' appears more than once on the {side} side")
    ewm = {w["id"]: w for w in exp_w}
    awm = {w["id"]: w for w in act_w}
    if len(exp_w) != len(act_w):
        _fail("WALL_COUNT", "", "wall count changed", len(exp_w), len(act_w))
    for wid in ewm.keys() - awm.keys():
        _fail("WALL_MISSING", wid, f"wall '{wid}' is missing from the 3D scene")
    for wid in awm.keys() - ewm.keys():
        _fail("WALL_EXTRA", wid, f"wall '{wid}' exists in the 3D scene but not in the 2D design")
    for wid in ewm.keys() & awm.keys():
        e, a = ewm[wid], awm[wid]
        if any(abs(e[k] - a[k]) > pos_tol for k in ("x1", "y1", "x2", "y2")):
            _fail("WALL_GEOMETRY", wid, "wall endpoints/geometry changed beyond tolerance",
                  [e["x1"], e["y1"], e["x2"], e["y2"]], [a["x1"], a["y1"], a["x2"], a["y2"]])
        if e["room"] is not None and e["room"] != a["room"]:
            _fail("WALL_ROOM", wid, "wall room relationship changed", e["room"], a["room"])

    passed = not mismatches
    return {
        "passed": passed,
        "status": "SCENE_FAITHFUL" if passed else "SCENE_VALIDATION_FAILED",
        "error_code": None if passed else "SCENE_2D_3D_MISMATCH",
        "mismatches": mismatches,
        "counts": {
            "furniture": {"expected": len(exp_f), "actual": len(act_f)},
            "doors": {"expected": len(expected.get("doors") or []),
                      "actual": len(actual.get("doors") or [])},
            "windows": {"expected": len(expected.get("windows") or []),
                        "actual": len(actual.get("windows") or [])},
            "walls": {"expected": len(exp_w), "actual": len(act_w)},
        },
    }


def _scene_opening_placements(scene: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Collect the openings the 3D renderer will actually draw (per-room placements
    projected onto their supporting wall), keyed by their stable id. Falls back to a
    room's ``doors``/``windows`` when no placements were attached."""
    out: list[dict[str, Any]] = []
    for room in scene.get("rooms", []) or []:
        placements = room.get("opening_placements")
        if placements:
            out.extend(p for p in placements if str(p.get("kind", "")) == kind[:-1])
        else:
            out.extend(room.get(kind, []) or [])
    return out


def validate_scene_2d_to_3d(
    canonical: dict[str, Any],
    scene: dict[str, Any],
    **tol: float,
) -> dict[str, Any]:
    """Authoritative-2D → deterministic-3D fidelity gate for the real pipeline.

    FURNITURE is the authoritative, user-owned source of truth with stable uids, so it
    gets the full per-object :func:`validate_2d_to_3d` bijection: expected = canonical
    furniture, actual = every room's furniture (tagged with its room id). This catches
    the conversion dropping / duplicating / moving / resizing / rotating / retyping /
    mis-rooming any item. (Canonical furniture carries no room id, so room EQUALITY is
    not asserted here — but the "exactly one 3D object per uid" bijection is, which
    flags a uid that leaked into two rooms.)

    OPENINGS and WALLS are architecture derived deterministically from the plan file;
    the authoritative extraction and the per-room rendered placements use DIFFERENT id
    namespaces, so cross-id equality is not meaningful in this pipeline. Their per-room
    assignment / off-wall / closed-boundary integrity is already enforced (un-weakened)
    by :func:`validate_scene_against_canonical` (§L). Here we add only namespace-safe
    structural integrity that a faithful conversion must satisfy: no duplicate rendered
    opening id, no duplicate wall id, and no zero-length wall.

    Pure/read-only: never mutates canonical or scene and never fabricates geometry.
    The per-object door/window/wall comparison in :func:`validate_2d_to_3d` remains
    available for callers that hold an id-aligned authoritative opening/wall source.
    """
    actual_furniture: list[dict[str, Any]] = []
    for room in scene.get("rooms", []) or []:
        rid = room.get("id") or room.get("label")
        for f in room.get("furniture", []) or []:
            actual_furniture.append({**f, "room": f.get("room") or f.get("room_id") or rid})

    result = validate_2d_to_3d(
        {"furniture": furniture_catalog.strip_annotations(canonical.get("furniture") or [])},
        {"furniture": actual_furniture},
        **tol,
    )
    mismatches: list[dict[str, Any]] = result["mismatches"]

    # Namespace-safe opening/wall integrity (no cross-id comparison).
    for kind in ("doors", "windows"):
        placements = [_d2d_norm_opening(o) for o in _scene_opening_placements(scene, kind)]
        cat = kind[:-1].upper()
        for dup in _dup_ids(placements, "id"):
            mismatches.append({
                "category": f"{cat}_DUPLICATE_ID", "id": dup,
                "reason": f"rendered {kind[:-1]} id '{dup}' appears more than once",
                "expected": None, "actual": None,
            })
    walls = [_d2d_norm_wall(w) for w in (scene.get("structured_walls") or [])]
    for i, w in enumerate(walls):
        if w["id"] is None:
            w["id"] = f"wall_{i}"
    for dup in _dup_ids(walls, "id"):
        mismatches.append({
            "category": "WALL_DUPLICATE_ID", "id": dup,
            "reason": f"wall id '{dup}' appears more than once", "expected": None, "actual": None,
        })
    for w in walls:
        if math.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"]) <= 1e-6:
            mismatches.append({
                "category": "WALL_DEGENERATE", "id": w["id"],
                "reason": "wall has zero length", "expected": None, "actual": None,
            })

    passed = not mismatches
    result["passed"] = passed
    result["status"] = "SCENE_FAITHFUL" if passed else "SCENE_VALIDATION_FAILED"
    result["error_code"] = None if passed else "SCENE_2D_3D_MISMATCH"
    result["counts"]["doors"] = {"rendered": len(_scene_opening_placements(scene, "doors"))}
    result["counts"]["windows"] = {"rendered": len(_scene_opening_placements(scene, "windows"))}
    result["counts"]["walls"] = {"structured": len(walls)}
    return result


def assess_ai_render(
    *,
    used_base_render: bool,
    scene_report: dict[str, Any] | None,
    output_verified: bool | None = None,
) -> dict[str, Any]:
    """Decide how an AI render's OUTPUT geometry fidelity may be reported (spec §L).

    EVIDENCE-DRIVEN (Phase 2I/P0): a geometry-faithful deterministic base used as the
    image-to-image control only establishes that the INPUT was geometry-locked — it
    does NOT prove the generated OUTPUT preserved that geometry. The output claim is
    therefore honest three-state:

    - ``geometry_status = "FAIL"``        no base used, or the base scene failed
      validation (geometry was never locked);
    - ``geometry_status = "UNVERIFIED"``  the base was geometry-faithful and used as
      the img2img control, BUT the output geometry was not checked (no output-level
      furniture/geometry verification ran) — so output fidelity is NOT asserted;
    - ``geometry_status = "FAITHFUL"``    input locked AND an output geometry check
      confirmed preservation (requires ``output_verified=True``).

    ``geometry_faithful`` is kept for backward compatibility but is now honest:
    ``True`` ONLY when verified, ``False`` on FAIL, and ``None`` when UNVERIFIED
    (never ``True`` merely because a valid base was used). ``input_geometry_locked``
    carries the "base was §L-verified and consumed" signal that the UI needs for its
    base-path label. Reporting-only: changes no render output, coordinates, or
    generation.
    """
    scene_ok = bool(scene_report and scene_report.get("geometry_faithful"))
    input_locked = bool(used_base_render and scene_ok)
    if not input_locked:
        status = "FAIL"
        reason = (
            "no deterministic base render was used (geometry not locked)"
            if not used_base_render
            else "the deterministic base scene failed geometry validation"
        )
        geometry_faithful: bool | None = False
    elif output_verified:
        status = "FAITHFUL"
        reason = (
            "image-to-image render of a geometry-faithful base, confirmed by an "
            "output geometry check"
        )
        geometry_faithful = True
    else:
        status = "UNVERIFIED"
        reason = (
            "image-to-image render of a geometry-faithful base, but the OUTPUT "
            "geometry was NOT verified (no output furniture/geometry check ran)"
        )
        geometry_faithful = None
    return {
        "geometry_faithful": geometry_faithful,
        "geometry_status": status,
        "input_geometry_locked": input_locked,
        "output_geometry_verified": bool(output_verified),
        "used_base_render": used_base_render,
        "scene_geometry_faithful": scene_ok,
        "reason": reason,
    }


def _img_dims(data: bytes) -> tuple[int, int] | None:
    try:
        return Image.open(BytesIO(data)).size
    except Exception:  # noqa: BLE001
        return None


def _is_blank_img(data: bytes) -> bool:
    """True if the image is (near) uniformly flat/dark — a degenerate output."""
    try:
        im = Image.open(BytesIO(data)).convert("L").resize((32, 32))
    except Exception:  # noqa: BLE001
        return False
    px = list(im.getdata())
    if not px:
        return True
    mean = sum(px) / len(px)
    return mean < 12 or (max(px) - min(px)) < 8


def _mean_abs_diff_imgs(a: bytes, b: bytes) -> float | None:
    """Mean absolute per-pixel luminance difference (0-255) at 64x64."""
    try:
        ia = Image.open(BytesIO(a)).convert("L").resize((64, 64))
        ib = Image.open(BytesIO(b)).convert("L").resize((64, 64))
    except Exception:  # noqa: BLE001
        return None
    pa, pb = list(ia.getdata()), list(ib.getdata())
    if not pa or len(pa) != len(pb):
        return None
    return sum(abs(int(x) - int(y)) for x, y in zip(pa, pb, strict=False)) / len(pa)


def assess_ai_output_geometry(
    output_png: bytes,
    base_render: bytes | None,
    *,
    aspect_tol: float = 0.10,
    identical_eps: float = 2.0,
) -> dict[str, Any]:
    """DETERMINISTIC post-AI reject gate (diagram stage: VALIDATE AGAINST 2D/3D
    SOURCE -> PASS/FAIL). Compares the AI OUTPUT image against the deterministic
    base render and REJECTS (passed=False) on gross structural divergence that needs
    NO vision detector:
      - blank/degenerate output                       -> FAILED_GEOMETRY_VALIDATION
      - output ~identical to the base (restyle no-op)  -> FAILED_GEOMETRY_VALIDATION
      - aspect-ratio divergence beyond aspect_tol      -> FAILED_GEOMETRY_VALIDATION
    When base_render is None (text-to-image, no source image) only the blank check
    applies. This does NOT attempt per-object (walls/doors/windows/furniture)
    comparison — that needs a vision detector on the AI image and is out of scope.
    Returns {passed, error_code, reason, output_dims, base_dims, aspect_delta,
    mean_abs_diff}.
    """
    out_dims = _img_dims(output_png)
    base_dims = _img_dims(base_render) if base_render is not None else None
    res: dict[str, Any] = {
        "passed": True, "error_code": None, "reason": "ok",
        "output_dims": out_dims, "base_dims": base_dims,
        "aspect_delta": None, "mean_abs_diff": None,
    }
    if out_dims is None:
        res.update(passed=False, error_code="FAILED_GEOMETRY_VALIDATION",
                   reason="AI output could not be decoded as an image")
        return res
    if _is_blank_img(output_png):
        res.update(passed=False, error_code="FAILED_GEOMETRY_VALIDATION",
                   reason="AI output is blank/degenerate")
        return res
    if base_render is None:
        res["reason"] = "no base render to compare (text-to-image); blank check only"
        return res
    # Aspect-ratio comparison (output must keep the base composition's aspect).
    if base_dims and base_dims[0] > 0 and base_dims[1] > 0 and out_dims[1] > 0:
        base_asp = base_dims[0] / base_dims[1]
        out_asp = out_dims[0] / out_dims[1]
        delta = abs(out_asp - base_asp) / base_asp if base_asp else 1.0
        res["aspect_delta"] = round(delta, 4)
        if delta > aspect_tol:
            res.update(passed=False, error_code="FAILED_GEOMETRY_VALIDATION",
                       reason=f"AI output aspect ratio diverged from base "
                              f"({out_asp:.3f} vs {base_asp:.3f}, delta={delta:.1%} > {aspect_tol:.0%})")
            return res
    # Degenerate "no restyle" — output virtually identical to the input base.
    diff = _mean_abs_diff_imgs(output_png, base_render)
    res["mean_abs_diff"] = round(diff, 2) if diff is not None else None
    if diff is not None and diff < identical_eps:
        res.update(passed=False, error_code="FAILED_GEOMETRY_VALIDATION",
                   reason=f"AI output is ~identical to the base render "
                          f"(mean_abs_diff={diff:.2f} < {identical_eps}) -- no restyle applied")
        return res
    return res
