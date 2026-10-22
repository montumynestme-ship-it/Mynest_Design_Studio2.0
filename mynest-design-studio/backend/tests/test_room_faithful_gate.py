"""§L base-geometry gate: a CONFIRMED wall-proven room must stay render-faithful
even when a same-labelled UNCERTAIN furniture-fallback group follows it.

Regression for the real-PDF bug where Living Area and Kitchen showed
BASE_GEOMETRY_INVALID because the fallback twin clobbered the CONFIRMED room's
per-label faithfulness."""

from app.services.generation_service import _room_faithful_map


def _room(label, status, openings=()):
    return {
        "label": label,
        "id": label.lower().replace(" ", "-"),
        "validation_status": status,
        "doors": list(openings),
        "windows": [],
    }


def test_confirmed_room_not_clobbered_by_uncertain_twin():
    # Proven rooms first, then same-labelled fallback groups (real emission order).
    rooms = [
        _room("Living Area", "CONFIRMED"),
        _room("Kitchen", "CONFIRMED"),
        _room("Living Area", "UNCERTAIN"),   # fallback twin
        _room("Kitchen", "UNCERTAIN"),       # fallback twin
        _room("Dining Area", "UNCERTAIN"),   # ONLY ever uncertain
    ]
    fm = _room_faithful_map(rooms)
    assert fm["Living Area"] is True   # CONFIRMED wins, not clobbered
    assert fm["Kitchen"] is True
    assert fm["Dining Area"] is False  # no CONFIRMED room -> honestly stays gated


def test_order_independent_confirmed_wins():
    # Even if the fallback twin is emitted BEFORE the confirmed room.
    rooms = [_room("Bedroom 1", "UNCERTAIN"), _room("Bedroom 1", "CONFIRMED")]
    assert _room_faithful_map(rooms)["Bedroom 1"] is True


def test_off_wall_opening_makes_room_unfaithful():
    rooms = [_room("Study", "CONFIRMED", openings=[{"id": "w1", "on_wall": False}])]
    assert _room_faithful_map(rooms)["Study"] is False


def test_open_plan_label_split_registers_each_subsection():
    rooms = [_room("Kitchen & Dining Area", "CONFIRMED")]
    fm = _room_faithful_map(rooms)
    assert fm["Kitchen"] is True and fm["Dining Area"] is True
