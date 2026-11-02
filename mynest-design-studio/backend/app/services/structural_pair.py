"""Validate a base-render / perspective-structural-render pair before conditioning.

Snapshot binding (Section 6): a structural image used as the Canny STRUCTURE control must
come from the SAME immutable design version and room as the base render, with compatible
dimensions and camera. A mismatched / missing / stale pair is REJECTED before any provider
request — never a silent substitution of a newer-version structural image. Pure + offline.

The ``*_meta`` dicts mirror the existing ``base_render_meta`` contract
(``design_version_id``, ``room_key``, ``width``, ``height``) plus an optional ``camera``
({``fov``, ``aspect``, ...}).
"""

from typing import Any


def _dims(meta: dict[str, Any], override: tuple[int, int] | None) -> tuple[int, int] | None:
    if override is not None:
        return override
    w, h = meta.get("width"), meta.get("height")
    if w is None or h is None:
        return None
    try:
        return int(w), int(h)
    except (TypeError, ValueError):
        return None


def validate_structural_pair(
    base_meta: dict[str, Any] | None,
    structural_meta: dict[str, Any] | None,
    *,
    base_dims: tuple[int, int] | None = None,
    structural_dims: tuple[int, int] | None = None,
) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``ok`` only when base and structural share the same immutable
    design version AND room AND compatible dimensions AND (when both present) camera."""
    if base_meta is None:
        return False, "BASE_MISSING: no base metadata for this room"
    if structural_meta is None:
        return False, "STRUCTURAL_MISSING: no structural metadata for this room"

    bv = str(base_meta.get("design_version_id") or "")
    sv = str(structural_meta.get("design_version_id") or "")
    if not bv or not sv or bv != sv:
        return False, f"STRUCTURAL_WRONG_VERSION: base={bv or None} structural={sv or None}"

    bk = str(base_meta.get("room_key") or "")
    sk = str(structural_meta.get("room_key") or "")
    if not bk or not sk or bk != sk:
        return False, f"STRUCTURAL_WRONG_ROOM: base={bk or None} structural={sk or None}"

    bd = _dims(base_meta, base_dims)
    sd = _dims(structural_meta, structural_dims)
    if bd is not None and sd is not None and bd != sd:
        return False, f"STRUCTURAL_WRONG_SIZE: base={bd} structural={sd}"

    bc = base_meta.get("camera") or {}
    sc = structural_meta.get("camera") or {}
    for k in ("fov", "aspect"):
        if k in bc and k in sc and bc[k] != sc[k]:
            return False, f"STRUCTURAL_CAMERA_MISMATCH: {k} base={bc[k]} structural={sc[k]}"

    return True, "OK"
