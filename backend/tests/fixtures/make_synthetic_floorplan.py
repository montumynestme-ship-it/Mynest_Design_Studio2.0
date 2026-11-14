"""Deterministic generator for the SYNTHETIC floor-plan fixture.

Run: ``python tests/fixtures/make_synthetic_floorplan.py`` → writes
``synthetic_floorplan.pdf`` beside this script.

This is a hand-authored, fully synthetic vector PDF — NOT a customer plan and NOT a
claim about real-world extraction accuracy. It draws a single rectangular room with
four black wall lines, one gold door rect, and one cyan window rect, at the exact
coordinates documented in ``synthetic_floorplan_provenance.md``, matching the colour/
shape contract that ``geometry_extraction_service.extract_walls`` reads
(door ``#9e7700``, window ``#00ffff``, near-black walls; a full-page rect would be
mistaken for the sheet frame, so each wall is a separate LINE, not a rect).

Page: 600×400 pt. World coordinates = PDF points × WORLD_SCALE (2.0).
"""

from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

# Room rectangle in PDF points (well inside the page so no wall lies on the sheet border).
ROOM = {"x0": 100.0, "y0": 80.0, "x1": 500.0, "y1": 320.0}
# Opening rects (PDF points): placed straddling a wall so extraction links them VALID.
DOOR = {"x": 180.0, "y": 315.0, "w": 40.0, "h": 10.0}   # on the bottom wall (y=320)
WINDOW = {"x": 380.0, "y": 75.0, "w": 40.0, "h": 10.0}  # on the top wall (y=80)

OUT = Path(__file__).with_name("synthetic_floorplan.pdf")


def build() -> bytes:
    pdf = FPDF(unit="pt", format=(600, 400))
    # Fixed creation date → stable bytes on regeneration.
    pdf.creation_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    pdf.set_compression(False)
    pdf.add_page()
    pdf.set_line_width(1.0)

    # Walls — four black lines (NOT a rect, which would read as the sheet frame).
    pdf.set_draw_color(0, 0, 0)
    pdf.line(ROOM["x0"], ROOM["y0"], ROOM["x1"], ROOM["y0"])  # top
    pdf.line(ROOM["x0"], ROOM["y1"], ROOM["x1"], ROOM["y1"])  # bottom
    pdf.line(ROOM["x0"], ROOM["y0"], ROOM["x0"], ROOM["y1"])  # left
    pdf.line(ROOM["x1"], ROOM["y0"], ROOM["x1"], ROOM["y1"])  # right

    # Door — gold rect straddling the bottom wall.
    pdf.set_draw_color(158, 119, 0)  # #9e7700
    pdf.rect(DOOR["x"], DOOR["y"], DOOR["w"], DOOR["h"], style="D")

    # Window — cyan rect straddling the top wall.
    pdf.set_draw_color(0, 255, 255)  # #00ffff
    pdf.rect(WINDOW["x"], WINDOW["y"], WINDOW["w"], WINDOW["h"], style="D")

    return bytes(pdf.output())


if __name__ == "__main__":
    OUT.write_bytes(build())
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
