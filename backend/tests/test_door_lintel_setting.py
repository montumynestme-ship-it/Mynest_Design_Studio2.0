"""Door lintel (head) height — authoritative project setting on door placements.

Reconstruction plan §2/§7.2/D4 + §17: a door's vertical extent is floor → lintel, read
from the project setting ``DOOR_LINTEL_HEIGHT_MM``. When the setting is unset or invalid
the lintel is honestly UNVERIFIED and NO height is guessed. These are pure, offline unit
tests of ``scene_service._attach_opening_placements`` (no DB, no provider, no paid call).
Canonical furniture is never mutated — the fields are additive and door-only.
"""

from app.core import config
from app.services import scene_service as S


def _room_with(item_id: str) -> dict:
    """A one-opening room (no structured walls → the NEEDS_REVIEW placement branch,
    which still carries the door-only lintel fields from the shared base dict)."""
    return {
        "furniture": [
            {"uid": f"{item_id}-1", "item_id": item_id,
             "cx": 100.0, "cy": 100.0, "w": 90.0, "h": 40.0, "rotation": 0.0},
        ]
    }


def _placement(item_id: str, kind: str) -> dict:
    rooms = [_room_with(item_id)]
    S._attach_opening_placements(rooms, structured_walls=[])
    return next(p for p in rooms[0]["opening_placements"] if p["kind"] == kind)


def test_lintel_from_project_setting(monkeypatch):
    monkeypatch.setattr(config, "DOOR_LINTEL_HEIGHT_MM", 2032.0)
    p = _placement("door", "door")
    assert p["lintel_height_mm"] == 2032.0
    assert p["lintel_verified"] is True
    assert p["lintel_source"] == "project_setting"
    # Additive — the existing placement contract is untouched.
    assert p["kind"] == "door" and "verified" in p and "status" in p


def test_lintel_unset_is_unverified_never_guessed(monkeypatch):
    monkeypatch.setattr(config, "DOOR_LINTEL_HEIGHT_MM", None)
    p = _placement("door", "door")
    assert p["lintel_height_mm"] is None        # no guessed value
    assert p["lintel_verified"] is False
    assert p["lintel_source"] == "unset"


def test_lintel_invalid_value_treated_as_unset(monkeypatch):
    for bad in (0.0, -5.0, float("nan"), float("inf")):
        monkeypatch.setattr(config, "DOOR_LINTEL_HEIGHT_MM", bad)
        p = _placement("door", "door")
        assert p["lintel_height_mm"] is None, f"{bad} must not become a confirmed height"
        assert p["lintel_verified"] is False
        assert p["lintel_source"] == "unset"


def test_window_placement_has_no_lintel_fields(monkeypatch):
    # Lintel is a DOOR concept only; windows must not gain the fields.
    monkeypatch.setattr(config, "DOOR_LINTEL_HEIGHT_MM", 2032.0)
    p = _placement("window", "window")
    assert "lintel_height_mm" not in p
    assert "lintel_verified" not in p


def test_canonical_furniture_not_mutated(monkeypatch):
    # The furniture item the placement derives from is never altered.
    monkeypatch.setattr(config, "DOOR_LINTEL_HEIGHT_MM", 2032.0)
    rooms = [_room_with("door")]
    before = dict(rooms[0]["furniture"][0])
    S._attach_opening_placements(rooms, structured_walls=[])
    assert rooms[0]["furniture"][0] == before
