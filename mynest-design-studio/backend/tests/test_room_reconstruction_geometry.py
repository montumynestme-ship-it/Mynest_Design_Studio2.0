"""Deterministic room reconstruction geometry (architectural_service.reconstruct_rooms).

Locks the authoritative contract: a room is proven ONLY from a closed wall cycle; furniture
is ASSIGNED to the proven room whose polygon CONTAINS its centre and is NEVER force-assigned
otherwise; reconstruction is deterministic for identical input. Pure; no DB/provider/network.
"""
from __future__ import annotations

from app.services import architectural_service as A


def _wall(i, x1, y1, x2, y2):
    return {"id": i, "x1": x1, "y1": y1, "x2": x2, "y2": y2}


_SQUARE = [
    _wall("w1", 0, 0, 1000, 0), _wall("w2", 1000, 0, 1000, 1000),
    _wall("w3", 1000, 1000, 0, 1000), _wall("w4", 0, 1000, 0, 0),
]


def _confirmed(rooms):
    return [r for r in rooms if str(r.get("validation_status")) == "CONFIRMED"]


def test_closed_walls_prove_exactly_one_room():
    bed = {"uid": "b", "item_id": "bed", "cx": 500, "cy": 500, "w": 180, "h": 200, "rotation": 0}
    rooms = _confirmed(A.reconstruct_rooms([bed], _SQUARE))
    assert len(rooms) == 1
    r = rooms[0]
    assert r["geometry_source"] == "architectural"
    # boundary is a closed polygon (first point repeated) with real area
    assert r["boundary"][0] == r["boundary"][-1] and len(r["boundary"]) >= 5
    x, y, w, h = r["bbox"]
    assert w > 0 and h > 0


def test_contained_furniture_is_assigned_outside_is_not_forced():
    bed = {"uid": "b", "item_id": "bed", "cx": 500, "cy": 500, "w": 180, "h": 200, "rotation": 0}
    far = {"uid": "far", "item_id": "side-table", "cx": 5000, "cy": 5000, "w": 45, "h": 45, "rotation": 0}
    r = _confirmed(A.reconstruct_rooms([bed, far], _SQUARE))[0]
    uids = {f.get("uid") for f in r["furniture"]}
    assert "b" in uids          # centre inside the proven polygon → assigned
    assert "far" not in uids    # centre outside → NEVER force-assigned to the proven room
    assert r["furniture_count"] == 1


def test_reconstruction_is_deterministic():
    furn = [{"uid": "b", "item_id": "bed", "cx": 500, "cy": 500, "w": 180, "h": 200, "rotation": 0}]
    assert A.reconstruct_rooms(furn, _SQUARE) == A.reconstruct_rooms(furn, _SQUARE)


def test_no_walls_proves_no_architectural_room():
    # furniture alone never CREATES an architectural room (no wall cycle to prove one)
    furn = [{"uid": "b", "item_id": "bed", "cx": 500, "cy": 500, "w": 180, "h": 200, "rotation": 0}]
    rooms = A.reconstruct_rooms(furn, [])
    assert _confirmed(rooms) == []   # nothing wall-proven; any grouping is non-authoritative
