"""Deterministic 3D base-render handoff — regression tests.

Proves the base-render gate classifies failures DISTINCTLY (a missing/blank base
render is never mislabelled as invalid canonical geometry), that the room-key
contract resolves a room to its STABLE id (not just a display label), and that a
valid base passes the gate so any NVIDIA/provider error stays a SEPARATE result.

These are the guarantees for the "BASE_GEOMETRY_INVALID — no deterministic 3D base
render was available" bug:
  A canonical geometry invalid       -> BASE_GEOMETRY_INVALID
  B base image missing               -> BASE_RENDER_MISSING (geometry is fine)
  C blank / corrupt base image       -> BASE_RENDER_BLANK / BASE_RENDER_CORRUPT
  D room/base key mismatch           -> BASE_RENDER_MISSING (resolved via id/label)
  E provider failure after valid base-> NOT a gate code (separate result)
"""

from io import BytesIO

from PIL import Image

from app.services import prompt_service
from app.services.generation_service import _classify_base_gate, _room_id_map

_ALL_GATE_CODES = {
    "ROOM_EMPTY",
    "BASE_GEOMETRY_INVALID",
    "BASE_RENDER_MISSING",
    "BASE_RENDER_BLANK",
    "BASE_RENDER_CORRUPT",
}


def _png(color) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


def _nonblank_png() -> bytes:
    """A clearly non-uniform image so _is_blank() returns False."""
    img = Image.new("RGB", (64, 64), (10, 10, 10))
    for x in range(64):
        for y in range(64):
            if (x // 8 + y // 8) % 2 == 0:
                img.putpixel((x, y), (230, 200, 160))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_FURN = {"furniture_count": 3}
_EMPTY = {"furniture_count": 0}


# ── A valid base render passes the gate (E: provider error stays separate) ───────────

def test_valid_base_passes_gate():
    code, reason = _classify_base_gate(_FURN, True, _nonblank_png())
    assert code is None and reason is None


def test_gate_never_returns_a_provider_error_code():
    # The gate only ever emits base/geometry codes; a NVIDIA/provider failure is
    # raised elsewhere as a distinct result, never conflated with a base failure.
    for base in (None, _png((0, 0, 0)), _nonblank_png(), b"not-a-png"):
        code, _ = _classify_base_gate(_FURN, True, base)
        assert code is None or code in _ALL_GATE_CODES


# ── B: base image missing is NOT geometry-invalid ────────────────────────────────────

def test_missing_base_is_render_missing_not_geometry_invalid():
    code, reason = _classify_base_gate(_FURN, True, None)
    assert code == "BASE_RENDER_MISSING"
    assert "canonical geometry is fine" in reason
    assert code != "BASE_GEOMETRY_INVALID"


# ── A: canonical geometry invalid is distinct from a missing base ────────────────────

def test_geometry_invalid_distinct_from_missing():
    # Geometry unfaithful takes precedence and is reported honestly as geometry,
    # even when a base render is also absent.
    code, _ = _classify_base_gate(_FURN, False, None)
    assert code == "BASE_GEOMETRY_INVALID"
    # But with faithful geometry, the SAME missing base is a render-miss, proving
    # the two conditions are never collapsed into one label.
    assert _classify_base_gate(_FURN, True, None)[0] == "BASE_RENDER_MISSING"


# ── C: blank / corrupt base rejected ─────────────────────────────────────────────────

def test_blank_base_rejected():
    code, _ = _classify_base_gate(_FURN, True, _png((0, 0, 0)))
    assert code == "BASE_RENDER_BLANK"


def test_corrupt_base_rejected():
    code, _ = _classify_base_gate(_FURN, True, b"\x00\x01 not an image \xff")
    assert code == "BASE_RENDER_CORRUPT"


# ── Empty room refused before anything else ──────────────────────────────────────────

def test_empty_room_refused():
    assert _classify_base_gate(_EMPTY, True, _nonblank_png())[0] == "ROOM_EMPTY"
    assert _classify_base_gate(None, True, _nonblank_png())[0] == "ROOM_EMPTY"


# ── D: room-key contract — resolve to a STABLE id, CONFIRMED wins ────────────────────

def _room(label, status, rid=None):
    return {
        "label": label,
        "id": rid or label.lower().replace(" ", "-"),
        "validation_status": status,
    }


def test_room_id_map_prefers_confirmed_id():
    rooms = [
        _room("Living Area", "CONFIRMED", rid="room-uuid-1"),
        _room("Living Area", "UNCERTAIN", rid="room-uuid-fallback"),
    ]
    id_map = _room_id_map(rooms)
    norm = prompt_service._normalize_section_name("Living Area")
    assert id_map[norm] == "room-uuid-1"          # stable CONFIRMED id, not the twin


def test_room_id_map_confirmed_wins_regardless_of_order():
    rooms = [
        _room("Kitchen", "UNCERTAIN", rid="k-fallback"),
        _room("Kitchen", "CONFIRMED", rid="k-confirmed"),
    ]
    norm = prompt_service._normalize_section_name("Kitchen")
    assert _room_id_map(rooms)[norm] == "k-confirmed"


def test_room_id_map_open_plan_split():
    id_map = _room_id_map([_room("Kitchen & Dining Area", "CONFIRMED", rid="open-1")])
    assert id_map[prompt_service._normalize_section_name("Kitchen")] == "open-1"
    assert id_map[prompt_service._normalize_section_name("Dining Area")] == "open-1"


def test_room_id_map_never_fabricates():
    # A room without an id contributes no mapping (no invented id).
    assert _room_id_map([{"label": "Ghost", "validation_status": "CONFIRMED"}]) == {}
    assert _room_id_map([]) == {}
