"""Room-assignment fidelity tests (spec: furniture must not silently leave its
true room because a nearest-seed distance heuristic pulled it elsewhere).

Two adjacent closed rectangles share one wall. A side table sits physically
inside the bedroom rectangle but is numerically closer to the living room's
sofa anchor than to the bed — reproducing the "Bedroom loses its furniture"
class of bug. `architectural_service.reconstruct_rooms` must use the real
wall polygons (per furniture item) to keep it in the bedroom.
"""

from app.services import architectural_service


def _item(
    uid: str, item_id: str, cx: float, cy: float,
    w: float = 400, h: float = 400, rotation: float = 0,
) -> dict:
    return {
        "uid": uid, "item_id": item_id, "cx": cx, "cy": cy,
        "w": w, "h": h, "rotation": rotation,
    }


def _two_adjacent_rooms_walls() -> list[dict]:
    """Two 1000x1000 closed rectangles sharing the wall at x=1000."""
    segments = [
        (0, 0, 1000, 0),
        (1000, 0, 2000, 0),
        (2000, 0, 2000, 1000),
        (2000, 1000, 1000, 1000),
        (1000, 1000, 0, 1000),
        (0, 1000, 0, 0),
        (1000, 0, 1000, 1000),
    ]
    return [
        {"id": f"wall_{i}", "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        for i, (x1, y1, x2, y2) in enumerate(segments)
    ]


def _stray_furniture() -> list[dict]:
    return [
        # Living Area (Room A: x in [0, 1000]) — the sofa anchor.
        _item("sofa", "lounger-sofa", 200, 500, 1200, 800),
        # Bedroom (Room B: x in [1000, 2000]) — the bed anchor, plus a
        # correctly-placed second item so the room's majority label is
        # unambiguous once the stray item is also reassigned here.
        _item("bed", "bed", 1950, 500, 900, 1000),
        _item("near_bed_table", "side-table", 1900, 300),
        # The stray item: physically just inside Room B (x=1020 > 1000) but
        # numerically closer to the sofa (dist 820) than to the bed (dist 930)
        # — the nearest-seed heuristic alone would wrongly pull it into the
        # Living Area group.
        _item("stray_table", "side-table", 1020, 500),
    ]


def test_polygon_containment_overrides_nearest_seed_heuristic() -> None:
    rooms = architectural_service.reconstruct_rooms(
        furniture=_stray_furniture(),
        structured_walls=_two_adjacent_rooms_walls(),
    )

    def _room_containing(uid: str) -> dict:
        for r in rooms:
            if any(it.get("uid") == uid or it.get("id") == uid for it in r["furniture"]):
                return r
        raise AssertionError(f"{uid} not found in any reconstructed room")

    bed_room = _room_containing("bed")
    stray_room = _room_containing("stray_table")
    sofa_room = _room_containing("sofa")

    assert stray_room["id"] == bed_room["id"], (
        "the stray side table sits physically inside the bedroom polygon and "
        "must stay there, not follow the nearest-seed heuristic into the "
        "living room"
    )
    assert sofa_room["id"] != bed_room["id"]
    assert bed_room["geometry_source"] == "architectural"
    assert sofa_room["geometry_source"] == "architectural"


def test_opening_attributed_to_exactly_one_room() -> None:
    door = {"id": "door_shared", "x": 1010, "y": 500, "width": 100, "height": 10}
    rooms = architectural_service.reconstruct_rooms(
        furniture=_stray_furniture(),
        structured_walls=_two_adjacent_rooms_walls(),
        doors=[door],
        windows=[],
    )
    rooms_with_door = [r for r in rooms if any(d.get("id") == "door_shared" for d in r["doors"])]
    assert len(rooms_with_door) == 1


def test_reconstructed_room_exposes_boundary_and_architectural_source() -> None:
    """/scene (reconstruct_rooms) must expose a real boundary polygon and mark
    it 'architectural' when closed walls exist — so the 3D floor uses the
    polygon, not a bbox rectangle (spec §A/§D/Q1,Q4)."""
    rooms = architectural_service.reconstruct_rooms(
        furniture=_stray_furniture(),
        structured_walls=_two_adjacent_rooms_walls(),
    )
    arch = [r for r in rooms if r["geometry_source"] == "architectural"]
    assert arch, "expected at least one architectural room from closed walls"
    for r in arch:
        assert isinstance(r["boundary"], list)
        assert len(r["boundary"]) >= 4  # closed polygon ring
        # Each boundary point is an (x, y) pair.
        assert all(len(pt) == 2 for pt in r["boundary"])


def test_reconstructed_rooms_have_room_specific_openings() -> None:
    """Doors/windows must belong to the correct room, never a global first-item
    broadcast to every room (spec §C/Q2,Q3)."""
    doors = [
        {"id": "d_left", "x": 200, "y": 500},   # inside Room A (x<1000)
        {"id": "d_right", "x": 1800, "y": 500},  # inside Room B (x>1000)
    ]
    windows = [{"id": "win_left", "x": 100, "y": 500}]  # Room A only
    rooms = architectural_service.reconstruct_rooms(
        furniture=_stray_furniture(),
        structured_walls=_two_adjacent_rooms_walls(),
        doors=doors,
        windows=windows,
    )
    # Every door/window is assigned to exactly one room in total.
    all_door_ids = [d.get("id") for r in rooms for d in r["doors"]]
    all_win_ids = [w.get("id") for r in rooms for w in r["windows"]]
    assert sorted(all_door_ids) == ["d_left", "d_right"]
    assert all_win_ids == ["win_left"]
    # No room carries BOTH doors (i.e. not a global broadcast).
    assert all(len(r["doors"]) <= 1 for r in rooms)
