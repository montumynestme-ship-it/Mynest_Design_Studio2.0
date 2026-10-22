"""Strict NO-FABRICATION wall reconstruction — algorithm correctness on controlled
synthetic double-line rooms (never the one real plan)."""

from app.services import wall_reconstruction as wr


def _double_rect(x0, y0, x1, y1, t):
    """Room as a double-line rectangle: outer + inner face offset by thickness t."""
    return [
        (x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1),
        (x0 + t, y0 + t, x1 - t, y0 + t), (x0 + t, y1 - t, x1 - t, y1 - t),
        (x0 + t, y0 + t, x0 + t, y1 - t), (x1 - t, y0 + t, x1 - t, y1 - t),
    ]


def _confirmed(res):
    return [r for r in res["rooms"] if r["validation_status"] == "CONFIRMED"]


def test_single_clean_room_confirmed():
    res = wr.reconstruct_rooms(_double_rect(0, 0, 400, 300, 20))
    c = _confirmed(res)
    assert len(c) == 1
    assert c[0]["wall_supported"] is True
    assert c[0]["supporting_wall_ids"]  # maps back to real source segments


def test_two_separate_clean_rooms_confirmed():
    walls = _double_rect(0, 0, 400, 300, 20) + _double_rect(600, 0, 1000, 300, 20)
    assert len(_confirmed(wr.reconstruct_rooms(walls))) == 2


def test_small_dash_gap_merges():
    """A wall split by tiny gaps (<= merge_gap) in BOTH faces is the same wall →
    room still closes."""
    walls = [w for w in _double_rect(0, 0, 400, 300, 20)
             if w not in ((0, 300, 400, 300), (20, 280, 380, 280))]
    walls += [(0, 300, 190, 300), (215, 300, 400, 300)]      # outer, 25px gap
    walls += [(20, 280, 190, 280), (215, 280, 380, 280)]     # inner, 25px gap
    assert len(_confirmed(wr.reconstruct_rooms(walls))) == 1


def test_large_opening_not_fabricated():
    """A wide opening (>> thickness) through BOTH faces must NOT be bridged into a
    wall → the room is NOT confirmed (no fabricated edge)."""
    walls = [w for w in _double_rect(0, 0, 400, 300, 20)
             if w not in ((0, 300, 400, 300), (20, 280, 380, 280))]
    walls += [(0, 300, 140, 300), (260, 300, 400, 300)]      # outer, 120px opening
    walls += [(20, 280, 140, 280), (260, 280, 380, 280)]     # inner, 120px opening
    assert len(_confirmed(wr.reconstruct_rooms(walls))) == 0


def test_two_collinear_separate_walls_not_merged():
    """Two separate rooms with COLLINEAR top/bottom walls must stay two rooms — the
    gap between them must never fuse into one big fabricated room."""
    walls = _double_rect(0, 0, 400, 300, 20) + _double_rect(600, 0, 1000, 300, 20)
    c = _confirmed(wr.reconstruct_rooms(walls))
    assert len(c) == 2
    assert max(r["area"] for r in c) < 400 * 300 * 1.4  # no giant merged polygon


def test_scale_invariance():
    base = _double_rect(0, 0, 400, 300, 20) + _double_rect(600, 0, 1000, 300, 20)
    r1 = _confirmed(wr.reconstruct_rooms(base))
    s = 3.5
    r2 = _confirmed(wr.reconstruct_rooms([(a * s, b * s, c * s, d * s) for a, b, c, d in base]))
    assert len(r1) == len(r2) == 2
    for x, y in zip(sorted(r["area"] for r in r1), sorted(r["area"] for r in r2), strict=True):
        assert abs(y / x - s * s) / (s * s) < 0.15


def test_sliver_rejected():
    walls = _double_rect(0, 0, 400, 400, 20) + _double_rect(600, 0, 1000, 400, 20)
    walls += _double_rect(420, 0, 460, 400, 8)  # thin corridor sliver (aspect >> 4)
    for r in _confirmed(wr.reconstruct_rooms(walls)):
        bw, bh = r["bbox"][2], r["bbox"][3]
        assert max(bw, bh) / max(1e-6, min(bw, bh)) <= 4.0


def test_no_walls_returns_empty():
    assert wr.reconstruct_rooms([])["rooms"] == []


def test_furniture_never_creates_boundary():
    res = wr.reconstruct_rooms(
        [], furniture=[{"item_id": "bed", "cx": 100, "cy": 100, "w": 50, "h": 50}])
    assert res["rooms"] == []


def test_broken_validation_expression_removed():
    """Regression: validation must be real (is_valid & is_simple), not the old
    `... or True` that accepted everything."""
    import inspect
    src = inspect.getsource(wr.reconstruct_rooms)
    assert "or True" not in src
    assert "is_simple" in src


def test_repair_walls_collapses_double_lines_with_provenance():
    """§3: repair_walls collapses double-line faces + merges collinear fragments to
    continuous centrelines, and every repaired wall keeps its original wall-ID
    provenance. Conservative tolerances never bridge a room-width gap."""
    t = 8.0
    segs = _double_rect(0, 0, 400, 300, t)  # 8 faces -> ~4 centrelines
    repaired = wr.repair_walls(segs, {"pair_tol": t * 1.6, "merge_gap": t * 2.0})
    assert 0 < len(repaired) < len(segs)
    for r in repaired:
        assert r["orientation"] in ("h", "v")
        assert r["source_wall_ids"], "repaired wall must retain source provenance"
        assert all(w.startswith("wall_") for w in r["source_wall_ids"])
    # A wide doorway gap must NOT be merged (only sub-thickness gaps heal).
    gapped = [(0, 0, 180, 0), (260, 0, 400, 0)]  # 80px gap >> merge_gap(16)
    rg = wr.repair_walls(gapped, {"pair_tol": t * 1.6, "merge_gap": t * 2.0})
    assert len(rg) == 2, "a room-width gap must stay open, not be healed"


def test_two_nearby_single_line_parallel_walls_do_not_collapse():
    """Two separate parallel architectural single-line walls must NOT collapse into one band.
    They must be preserved as two distinct walls."""
    # Two walls 20px apart, measured thickness 10px
    w1 = (0.0, 100.0, 300.0, 100.0)
    w2 = (0.0, 120.0, 300.0, 120.0)
    repaired = wr.repair_walls([w1, w2], {"pair_tol": 25.0, "merge_gap": 20.0, "thickness": 10.0})
    assert len(repaired) == 2, "Separate parallel walls must not collapse into a single line"
    ys = sorted(r["const"] for r in repaired)
    assert abs(ys[0] - 100.0) < 1e-3
    assert abs(ys[1] - 120.0) < 1e-3


def test_two_nearby_double_line_walls_do_not_fuse_into_one():
    """Two distinct double-line walls separated by a gap (e.g. corridor or cavity)
    must each collapse to their own centerline, NOT fuse into one giant band."""
    t = 10.0
    # Wall A: y=100 and y=110 (centerline ~105)
    # Wall B: y=130 and y=140 (centerline ~135)
    segs = [
        (0.0, 100.0, 300.0, 100.0),
        (0.0, 110.0, 300.0, 110.0),
        (0.0, 130.0, 300.0, 130.0),
        (0.0, 140.0, 300.0, 140.0),
    ]
    repaired = wr.repair_walls(segs, {"pair_tol": t * 1.6, "merge_gap": t * 2.0, "thickness": t})
    assert len(repaired) == 2, "Must produce exactly 2 distinct centerlines, not 1 fused band"
    ys = sorted(r["const"] for r in repaired)
    assert abs(ys[0] - 105.0) < 1.0
    assert abs(ys[1] - 135.0) < 1.0


def test_validate_opening_bridges_requires_intersection():
    """Opening bridges must geometrically intersect the supporting wall line (L_int > 0).
    A displaced or non-intersecting opening must be rejected."""
    wall = (0.0, 100.0, 400.0, 100.0)
    repaired = wr.repair_walls([wall], {"pair_tol": 16.0, "merge_gap": 20.0, "thickness": 10.0})

    # Opening 1: centered at (200, 100), width=60, height=20 -> intersects wall from x=170 to 230
    op_valid = {
        "id": "door_valid", "kind": "door",
        "cx": 200.0, "cy": 100.0, "w": 60.0, "h": 20.0,
        "validation_status": "VALID",
    }
    # Opening 2: centered at (200, 150), width=60, height=20 -> 50px away, no intersection
    op_displaced = {
        "id": "door_far", "kind": "door",
        "cx": 200.0, "cy": 150.0, "w": 60.0, "h": 20.0,
        "validation_status": "VALID",
    }
    # Opening 3: longitudinal range outside wall: (500, 100), width=40, height=20
    op_outside = {
        "id": "door_outside", "kind": "door",
        "cx": 500.0, "cy": 100.0, "w": 40.0, "h": 20.0,
        "validation_status": "VALID",
    }
    bridges = wr.validate_opening_bridges(
        [op_valid, op_displaced, op_outside], repaired, thickness=10.0
    )
    assert len(bridges) == 3
    valid_b = next(b for b in bridges if b["opening_id"] == "door_valid")
    assert valid_b["bridge_applied"] is True
    assert valid_b["intersection_length"] > 0
    assert valid_b["supporting_wall_id"] is not None

    far_b = next(b for b in bridges if b["opening_id"] == "door_far")
    assert far_b["bridge_applied"] is False
    assert far_b["reason"] == "no_geometric_wall_intersection"

    out_b = next(b for b in bridges if b["opening_id"] == "door_outside")
    assert out_b["bridge_applied"] is False
    assert out_b["reason"] == "no_geometric_wall_intersection"

