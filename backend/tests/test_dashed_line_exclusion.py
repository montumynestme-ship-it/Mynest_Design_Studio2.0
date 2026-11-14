"""Dashed lines are OVERHEAD / ceiling / beam indications, NOT walls.

A synthetic vector PDF (fpdf) draws four SOLID black walls, one DASHED black beam line,
one gold door rect and one cyan window rect. ``geometry_extraction_service.extract_walls``
must keep the solid lines as walls, classify the dashed line as an overhead candidate
(excluded from the wall inventory and the wall mesh), and keep the door/window as openings
on a solid wall — never promoting the dashed line to a wall. Deterministic, offline.
"""

import pytest

from app.services import geometry_extraction_service as G

fpdf = pytest.importorskip("fpdf")

PAGE = (600, 400)
ROOM = {"x0": 100.0, "y0": 80.0, "x1": 500.0, "y1": 320.0}
DOOR = {"x": 180.0, "y": 315.0, "w": 40.0, "h": 10.0}    # straddles the bottom wall (y=320)
WINDOW = {"x": 380.0, "y": 75.0, "w": 40.0, "h": 10.0}   # straddles the top wall (y=80)
BEAM = {"x0": 150.0, "y": 200.0, "x1": 450.0}            # a DASHED horizontal beam inside the room


def _make_pdf(path: str) -> None:
    pdf = fpdf.FPDF(unit="pt", format=PAGE)
    pdf.set_compression(False)
    pdf.add_page()
    pdf.set_line_width(1.0)
    # Four SOLID black walls (separate lines, not a rect → not read as the sheet frame).
    pdf.set_draw_color(0, 0, 0)
    pdf.line(ROOM["x0"], ROOM["y0"], ROOM["x1"], ROOM["y0"])  # top
    pdf.line(ROOM["x0"], ROOM["y1"], ROOM["x1"], ROOM["y1"])  # bottom
    pdf.line(ROOM["x0"], ROOM["y0"], ROOM["x0"], ROOM["y1"])  # left
    pdf.line(ROOM["x1"], ROOM["y0"], ROOM["x1"], ROOM["y1"])  # right
    # One DASHED black beam line (overhead indication) INSIDE the room.
    pdf.set_dash_pattern(dash=3, gap=3)
    pdf.line(BEAM["x0"], BEAM["y"], BEAM["x1"], BEAM["y"])
    pdf.set_dash_pattern()  # reset to solid
    # Door (gold) + window (cyan) rects straddling a wall → openings, not walls.
    pdf.set_draw_color(0x9E, 0x77, 0x00)
    pdf.rect(DOOR["x"], DOOR["y"], DOOR["w"], DOOR["h"])
    pdf.set_draw_color(0x00, 0xFF, 0xFF)
    pdf.rect(WINDOW["x"], WINDOW["y"], WINDOW["w"], WINDOW["h"])
    pdf.output(path)


@pytest.fixture
def plan_pdf(tmp_path):
    p = tmp_path / "dashed_beam_plan.pdf"
    _make_pdf(str(p))
    return str(p)


def _is_dashed_on_segment(geo, x1w, y1w, x2w, y2w, tol=8.0):
    """True if an overhead candidate matches (world coords) the given segment."""
    import math
    for o in geo["overhead_candidates"]:
        if (math.hypot(o["x1"] - x1w, o["y1"] - y1w) < tol and math.hypot(o["x2"] - x2w, o["y2"] - y2w) < tol):
            return True
    return False


def test_is_dashed_helper():
    assert G._is_dashed(None) is False
    assert G._is_dashed([]) is False
    assert G._is_dashed(([], 0)) is False
    assert G._is_dashed(([3, 3], 0)) is True
    assert G._is_dashed(([2], 0)) is True


def test_solid_walls_kept_dashed_beam_excluded(plan_pdf):
    geo = G.extract_walls(plan_pdf)
    scale = geo["page"]["scale"]
    # Four solid walls survive; the dashed beam does NOT inflate the wall count.
    assert len(geo["walls"]) == 4, f"expected 4 solid walls, got {len(geo['walls'])}"
    # The dashed beam is classified as an overhead candidate (preserved, not discarded).
    assert len(geo["overhead_candidates"]) == 1
    assert geo["overhead_candidates"][0]["classification"] == "overhead_dashed"
    assert _is_dashed_on_segment(geo, BEAM["x0"] * scale, BEAM["y"] * scale, BEAM["x1"] * scale, BEAM["y"] * scale)
    # The dashed beam is NOT present among the walls (no false/duplicate wall at its y).
    beam_y_w = BEAM["y"] * scale
    assert not any(abs((w[1] + w[3]) / 2 - beam_y_w) < 1.0 and abs(w[1] - w[3]) < 1.0 for w in geo["walls"])


def test_dashed_line_not_promoted_to_structured_wall(plan_pdf):
    geo = G.extract_walls(plan_pdf)
    # structured_walls mirrors walls — exactly the 4 solid lines, none from the dash.
    assert len(geo["structured_walls"]) == 4
    assert all(sw["color"] == "#141414" for sw in geo["structured_walls"])


def test_openings_detected_on_solid_walls_not_as_walls(plan_pdf):
    geo = G.extract_walls(plan_pdf)
    kinds = sorted(o["kind"] for o in geo["openings"])
    assert "door" in kinds and "window" in kinds
    # A VALID opening is associated to a real (solid) wall.
    valid = [o for o in geo["openings"] if o.get("validation_status") == "VALID"]
    assert valid, "expected at least one VALID opening associated to a solid wall"
    assert all(o.get("supporting_wall_id") for o in valid)
