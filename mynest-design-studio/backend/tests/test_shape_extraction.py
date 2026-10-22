"""Deterministic architectural SHAPE extraction (audit stage 3, reinforced).

Regression coverage for the required cases: fragmented walls, T-junctions,
L-junctions, shared walls, doors on walls, windows on walls, and ambiguous/unowned
openings — plus the source-of-truth invariants (source pixel coords preserved, no
invented walls to close a room, shared walls not duplicated).
"""

import pytest

from app.services import shape_extraction_service as se


def _double_rect(x0, y0, x1, y1, t):
    """A room as a double-line rectangle (outer + inner face offset by thickness t)."""
    return [
        (x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1),
        (x0 + t, y0 + t, x1 - t, y0 + t), (x0 + t, y1 - t, x1 - t, y1 - t),
        (x0 + t, y0 + t, x0 + t, y1 - t), (x1 - t, y0 + t, x1 - t, y1 - t),
    ]


def _confirmed(res):
    return [r for r in res["rooms"] if r["status"] == "CONFIRMED"]


# ── Fragmented walls ─────────────────────────────────────────────────────────

def test_fragmented_walls_merged_deterministically():
    # A clean room, but the top faces are split into dashed fragments (small gaps).
    walls = [w for w in _double_rect(0, 0, 400, 300, 20)
             if w not in ((0, 0, 400, 0), (20, 20, 380, 20))]
    walls += [(0, 0, 180, 0), (205, 0, 400, 0)]        # outer top, 25px gap
    walls += [(20, 20, 180, 20), (205, 20, 380, 20)]   # inner top, 25px gap
    res = se.extract_shapes(walls)
    # The fragmented top collapses to ONE horizontal span near y≈10 (not 2+).
    top = [w for w in res["walls"] if w["orientation"] == "h" and abs(w["y1"] - 10) < 6]
    h_walls = [(w["x1"], w["x2"], w["y1"]) for w in res["walls"] if w["orientation"] == "h"]
    assert len(top) == 1, h_walls
    assert top[0]["x1"] <= 1 and top[0]["x2"] >= 399   # spans the full width
    assert top[0]["evidence_fragments"] >= 2           # provenance to source strokes
    assert len(_confirmed(res)) == 1                   # room still closes


# ── L-junctions ──────────────────────────────────────────────────────────────

def test_l_junctions_detected_at_corners():
    res = se.extract_shapes(_double_rect(0, 0, 400, 300, 20))
    assert res["stats"]["junctions_L"] >= 4            # four corners
    assert any(j["type"] == "L" for j in res["junctions"])


# ── T-junctions ──────────────────────────────────────────────────────────────

def test_t_junctions_detected_on_shared_partition():
    walls = _double_rect(0, 0, 400, 300, 20) + _double_rect(400, 0, 800, 300, 20)
    res = se.extract_shapes(walls)
    assert res["stats"]["junctions_T"] >= 1            # partition meets outer walls
    assert any(j["type"] == "T" for j in res["junctions"])


# ── Shared walls ─────────────────────────────────────────────────────────────

def test_shared_wall_is_single_span_and_two_rooms():
    walls = _double_rect(0, 0, 400, 300, 20) + _double_rect(400, 0, 800, 300, 20)
    res = se.extract_shapes(walls)
    # The shared partition near x≈400 is ONE vertical span, never duplicated.
    shared = [w for w in res["walls"] if w["orientation"] == "v" and abs(w["x1"] - 400) < 12]
    v_walls = [(w["x1"], w["y1"], w["y2"]) for w in res["walls"] if w["orientation"] == "v"]
    assert len(shared) == 1, v_walls
    assert len(_confirmed(res)) == 2


# ── Doors / windows on walls ─────────────────────────────────────────────────

def test_door_attached_to_supporting_wall():
    walls = _double_rect(0, 0, 400, 300, 20)
    door = {"id": "d1", "kind": "door", "cx": 200, "cy": 10, "w": 80, "h": 18}
    res = se.extract_shapes(walls, openings=[door])
    o = res["openings"][0]
    assert o["status"] == "VALID"
    assert o["supporting_wall_id"] is not None
    assert o["source_wall_ids"]                        # provenance to the wall strokes


def test_window_attached_to_supporting_wall():
    walls = _double_rect(0, 0, 400, 300, 20)
    win = {"id": "w1", "kind": "window", "cx": 0, "cy": 150, "w": 18, "h": 90}
    res = se.extract_shapes(walls, openings=[win])
    o = res["openings"][0]
    assert o["status"] == "VALID"
    assert o["supporting_wall_id"] is not None


# ── Ambiguous / unowned openings ─────────────────────────────────────────────

def test_unowned_opening_marked_uncertain():
    walls = _double_rect(0, 0, 400, 300, 20)
    floating = {"id": "f1", "kind": "door", "cx": 2000, "cy": 2000, "w": 80, "h": 18}
    res = se.extract_shapes(walls, openings=[floating])
    o = res["openings"][0]
    assert o["status"] == "UNCERTAIN"
    assert o["supporting_wall_id"] is None


def test_degenerate_opening_marked_invalid():
    walls = _double_rect(0, 0, 400, 300, 20)
    bad = {"id": "b1", "kind": "window", "cx": 200, "cy": 10, "w": 0, "h": 18}
    res = se.extract_shapes(walls, openings=[bad])
    assert res["openings"][0]["status"] == "INVALID"


# ── Source-of-truth invariants ───────────────────────────────────────────────

def test_source_pixel_coordinates_preserved():
    walls = _double_rect(100, 50, 500, 350, 20)
    res = se.extract_shapes(walls)
    assert res["coordinate_space"] == "source_pixels"
    xs = [c for w in res["walls"] for c in (w["x1"], w["x2"])]
    ys = [c for w in res["walls"] for c in (w["y1"], w["y2"])]
    assert min(xs) <= 111 and max(xs) >= 489           # near the real 100..500 extent
    assert min(ys) <= 61 and max(ys) >= 339            # not normalized to 0..1


def test_no_invented_wall_to_close_open_room():
    # A wide opening (>> thickness) through BOTH faces of one side: the room must NOT
    # be confirmed (no fabricated closing wall).
    walls = [w for w in _double_rect(0, 0, 400, 300, 20)
             if w not in ((0, 300, 400, 300), (20, 280, 380, 280))]
    walls += [(0, 300, 130, 300), (270, 300, 400, 300)]     # 140px opening (outer)
    walls += [(20, 280, 130, 280), (270, 280, 380, 280)]    # 140px opening (inner)
    res = se.extract_shapes(walls)
    assert len(_confirmed(res)) == 0                        # honestly not closed


def test_empty_input_is_empty_structure():
    res = se.extract_shapes([])
    assert res["walls"] == [] and res["rooms"] == [] and res["openings"] == []
    assert res["stats"]["raw_segments"] == 0


# ── CV raster path (deterministic OpenCV; skipped if cv2 absent) ──────────────

def test_cv_detects_axis_walls_from_synthetic_image():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from PIL import Image
    img = np.full((400, 600), 255, dtype=np.uint8)      # white background
    # two-room plan: outer box + a middle partition, drawn as thick black walls
    cv2.rectangle(img, (40, 40), (560, 360), 0, 6)
    cv2.line(img, (300, 40), (300, 360), 0, 6)
    res = se.extract_shapes_from_image(Image.fromarray(img))
    assert res["source"] == "raster"
    assert res["coordinate_space"] == "source_pixels"
    # Hough must recover horizontal + vertical wall lines (axis-aligned only).
    assert any(w["orientation"] == "h" for w in res["walls"])
    assert any(w["orientation"] == "v" for w in res["walls"])
    assert res["stats"]["walls"] >= 3
