"""Topology reconstruction via point->perpendicular-segment junctions (no fabrication)."""

from app.services import wall_reconstruction as wr

TH = 20.0


def _H(y, x0, x1):
    return (y, x0, x1, {0})


def _V(x, y0, y1):
    return (x, y0, y1, {0})


def _types(js):
    return sorted(j["junction_type"] for j in js)


def test_true_L_corner_detected():
    js = wr.find_junctions([_H(0, 0, 200)], [_V(0, 0, 200)], TH)
    assert len(js) == 1 and js[0]["junction_type"] == "L_JUNCTION"


def test_H_endpoint_on_V_body_is_T_junction():
    # H ends at (200,100); V runs x=200 from y=0..300 -> endpoint hits V body mid-span
    js = wr.find_junctions([_H(100, 0, 200)], [_V(200, 0, 300)], TH)
    assert any(j["junction_type"] == "T_JUNCTION" for j in js)


def test_V_endpoint_on_H_body_is_T_junction():
    js = wr.find_junctions([_H(0, 0, 300)], [_V(150, 0, 200)], TH)
    # V endpoint (150,0) lands on H body (y=0, x 0..300) mid-span
    assert any(j["junction_type"] == "T_JUNCTION" for j in js)


def test_endpoint_outside_perpendicular_segment_rejected():
    # H endpoint projects to y=100 but V segment only spans y 200..300 -> no junction
    js = wr.find_junctions([_H(100, 0, 200)], [_V(200, 200, 300)], TH)
    assert js == []


def test_large_gap_rejected():
    # V is 60px (>1x thickness) from the H endpoint -> no evidence
    js = wr.find_junctions([_H(100, 0, 200)], [_V(260, 0, 300)], TH)
    assert js == []


def test_no_infinite_line_intersection():
    # H at y=500 and V spanning y 0..100: their infinite lines cross at (200,500)
    # but the V segment does NOT reach y=500 -> must NOT create a junction.
    js = wr.find_junctions([_H(500, 0, 200)], [_V(200, 0, 100)], TH)
    assert js == []


def _dr(x0, y0, x1, y1, t):
    return [(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1),
            (x0 + t, y0 + t, x1 - t, y0 + t), (x0 + t, y1 - t, x1 - t, y1 - t),
            (x0 + t, y0 + t, x0 + t, y1 - t), (x1 - t, y0 + t, x1 - t, y1 - t)]


def _confirmed(res):
    return [r for r in res["rooms"] if r["validation_status"] == "CONFIRMED"]


def test_closed_rectangular_room():
    r = wr.reconstruct_rooms_topology(_dr(0, 0, 400, 300, 20))
    assert len(_confirmed(r)) == 1
    assert r["stats"]["L"] == 4 and r["stats"]["T"] == 0


def test_multi_room_T_junction_layout():
    # two stacked rooms sharing a middle wall -> 2 rooms, with T-junctions where
    # the shared wall meets the outer walls.
    r = wr.reconstruct_rooms_topology(_dr(0, 0, 400, 300, 20) + _dr(0, 300, 400, 600, 20))
    assert len(_confirmed(r)) == 2
    assert r["stats"]["T"] >= 2


def test_span_split_at_junction_creates_edges():
    # the shared middle wall must be split by the perpendicular junctions
    r = wr.reconstruct_rooms_topology(_dr(0, 0, 400, 300, 20) + _dr(0, 300, 400, 600, 20))
    assert r["stats"]["edges"] > r["stats"]["hspans"] + r["stats"]["vspans"] - 3


def test_no_walls_returns_empty():
    assert wr.reconstruct_rooms_topology([])["rooms"] == []


def test_furniture_never_creates_room():
    r = wr.reconstruct_rooms_topology([], furniture=[{"item_id": "bed", "cx": 50, "cy": 50, "w": 20, "h": 20}])
    assert r["rooms"] == []


def test_six_room_plan():
    # Six stacked rooms sharing horizontal walls that terminate (T-junctions) on
    # the two continuous side walls — a layout the endpoint->body method can prove.
    walls = []
    for i in range(6):
        walls += _dr(0, i * 150, 400, (i + 1) * 150, 20)
    r = wr.reconstruct_rooms_topology(walls)
    assert len(_confirmed(r)) == 6, r["stats"]


def test_near_parallel_unrelated_walls_make_no_junction():
    # Two parallel horizontal walls, no perpendicular endpoint touching either ->
    # no junction may be invented between them.
    assert wr.find_junctions([_H(0, 0, 200), _H(60, 0, 200)], [], TH) == []


def test_open_u_shape_is_not_a_room():
    # Three walls forming an open "U" (missing the fourth side) can NOT close into
    # a cycle -> zero confirmed rooms (no fabricated closure).
    walls = [(0, 0, 0, 200), (200, 0, 200, 200), (0, 200, 200, 200)]
    r = wr.reconstruct_rooms_topology(walls)
    assert _confirmed(r) == []


def test_unsupported_furniture_inside_open_shape_still_no_room():
    # Furniture centroid inside the open U must NOT rescue/fabricate a room.
    walls = [(0, 0, 0, 200), (200, 0, 200, 200), (0, 200, 200, 200)]
    r = wr.reconstruct_rooms_topology(
        walls, furniture=[{"item_id": "sofa", "cx": 100, "cy": 100, "w": 30, "h": 30}])
    assert _confirmed(r) == []


def test_junction_preserves_wall_provenance():
    js = wr.find_junctions([_H(0, 0, 200)], [_V(0, 0, 200)], TH)
    assert len(js) == 1
    j = js[0]
    assert set(j["walls"]) == {"H0", "V0"}       # both incident walls recorded
    assert j["source_ids"] == [0]                # combined source segments
    assert {w["wall_id"] for w in j["incident"]} == {"H0", "V0"}


def test_confirmed_room_carries_edge_and_corner_provenance():
    r = wr.reconstruct_rooms_topology(_dr(0, 0, 400, 300, 20))
    room = _confirmed(r)[0]
    assert room["supporting_wall_ids"]           # maps back to real walls
    assert len(room["corner_junction_ids"]) >= 4  # every corner a proven junction
    assert room["min_edge_coverage"] >= 0.9


def test_opening_on_wall_validation():
    hs = wr._collapse([(0, (0, 0, 400, 0))], 0, TH * 1.6, TH * 2.0)
    vs = wr._collapse([(1, (0, 0, 0, 300))], 1, TH * 1.6, TH * 2.0)
    on = wr.opening_on_wall({"x": 200, "y": 0}, hs, vs, TH)
    assert on["on_wall"] and on["wall_id"] == "H0"
    off = wr.opening_on_wall({"x": 200, "y": 150}, hs, vs, TH)
    assert not off["on_wall"]


def test_furniture_outside_confirmed_room_not_assigned():
    r = wr.reconstruct_rooms_topology(
        _dr(0, 0, 400, 300, 20),
        furniture=[{"uid": "inside", "item_id": "bed", "cx": 200, "cy": 150, "w": 20, "h": 20},
                   {"uid": "outside", "item_id": "bed", "cx": 900, "cy": 900, "w": 20, "h": 20}])
    room = _confirmed(r)[0]
    assert "inside" in room["furniture_ids"]
    assert "outside" not in room["furniture_ids"]
