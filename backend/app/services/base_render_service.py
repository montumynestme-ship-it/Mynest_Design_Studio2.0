"""Deterministic base-render contract enforcement.

The base render handed to the AI provider MUST be the Three.js PNG capture of the
EXACT validated deterministic 3D scene for the room being generated — nothing else.
This module is the single deterministic checkpoint that the received capture honours
the contract before any provider/fal call:

    Authoritative 2D → SceneRoom → 2D/3D validation → fixed camera →
    Three.js render → PNG → backend (HERE) → AI provider

A capture is accepted ONLY when it is a valid, non-blank PNG of the expected size,
for the expected room, produced from the expected (current) design version. Anything
else — a UI screenshot (wrong size), a stale/old-version capture, a wrong-room
capture, a blank frame, a corrupt/non-PNG blob, a missing capture — is REJECTED with
a structured BASE_RENDER error. On rejection the caller must NOT call fal.ai, must NOT
substitute a mock/placeholder/AI-generated image, and must NOT send a PDF directly.

This module never generates, repairs, or fabricates an image — it only inspects the
bytes it is given and reports a verdict. Scene-level fidelity (missing/extra/moved
furniture, openings, walls) is enforced separately and earlier by
``validation_service.validate_scene_2d_to_3d`` / the §L gate; a base render is only
validated here once that scene is known faithful.
"""

from __future__ import annotations

from typing import Any

from app.services.validation_service import _img_dims, _is_blank_img

# Structured codes — each maps 1:1 to a rejected contract requirement.
MISSING = "BASE_RENDER_MISSING"
CORRUPT = "BASE_RENDER_CORRUPT"
BLANK = "BASE_RENDER_BLANK"
WRONG_VERSION = "BASE_RENDER_WRONG_VERSION"
WRONG_ROOM = "BASE_RENDER_WRONG_ROOM"
WRONG_SIZE = "BASE_RENDER_WRONG_SIZE"


def _result(ok: bool, code: str | None, reason: str | None,
            width: int | None = None, height: int | None = None) -> dict[str, Any]:
    return {"ok": ok, "code": code, "reason": reason, "width": width, "height": height}


def validate_base_render(
    png: bytes | None,
    *,
    expected_version_id: str | None = None,
    declared_version_id: str | None = None,
    expected_room_key: str | None = None,
    declared_room_key: str | None = None,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> dict[str, Any]:
    """Validate one received base-render capture against the contract.

    All ``expected_*`` are opt-in: a check runs ONLY when its expected value is
    provided, so a caller can enforce exactly the guarantees it can assert. When an
    ``expected_version_id`` / ``expected_room_key`` is given, the capture MUST declare
    a matching ``declared_*`` value (a capture that cannot prove its design-version or
    room association is rejected — "stable generation association").

    Checks run in a fixed order (first failure wins): missing → corrupt → blank →
    wrong design version → wrong room → wrong size. Returns a structured
    ``{"ok", "code", "reason", "width", "height"}`` and never mutates or fabricates.
    """
    if not png:
        return _result(False, MISSING,
                       "no base-render PNG reached the backend for this room "
                       "(capture missing or failed after bounded retries)")

    dims = _img_dims(png)
    if dims is None:
        return _result(False, CORRUPT, "base render could not be decoded as a PNG image")
    width, height = dims

    if _is_blank_img(png):
        return _result(False, BLANK,
                       "base render is blank/uniform (not a render of the scene)",
                       width, height)

    if expected_version_id is not None and str(declared_version_id) != str(expected_version_id):
        return _result(
            False, WRONG_VERSION,
            f"base render was produced from a different/stale design version "
            f"(declared={declared_version_id!r}, expected={expected_version_id!r})",
            width, height,
        )

    if expected_room_key is not None and str(declared_room_key) != str(expected_room_key):
        return _result(
            False, WRONG_ROOM,
            f"base render was captured for a different room "
            f"(declared={declared_room_key!r}, expected={expected_room_key!r})",
            width, height,
        )

    if expected_width is not None and expected_height is not None and (
        width != int(expected_width) or height != int(expected_height)
    ):
        return _result(
            False, WRONG_SIZE,
            f"base render size {width}x{height} does not match the expected "
            f"capture size {int(expected_width)}x{int(expected_height)} "
            f"(a UI screenshot or wrong canvas was captured)",
            width, height,
        )

    return _result(True, None, None, width, height)
