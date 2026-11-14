# `synthetic_floorplan.pdf` — provenance & expected geometry

**Synthetic. Hand-authored. Not a customer plan.** Generated deterministically by
`make_synthetic_floorplan.py` (fpdf). It exists only to exercise the real wall/opening
extractor + the SVG geometry-reference builder offline. It is **not** evidence about
real-world floor-plan extraction accuracy.

## Source drawing (PDF points, page 600 × 400)
- Room rectangle drawn as **four separate black lines** (a single rect would be read as
  the sheet frame): `x0=100, y0=80, x1=500, y1=320`.
- **Door**: gold (`#9e7700`) rect `x=180, y=315, w=40, h=10` — straddles the bottom wall.
- **Window**: cyan (`#00ffff`) rect `x=380, y=75, w=40, h=10` — straddles the top wall.

## Expected extraction (`geometry_extraction_service.extract_walls`, `WORLD_SCALE = 2.0`)
Everything below is **world px = PDF pt × 2**, independently derived from the coordinates
above — NOT read back from the SVG builder.

- `page`: width `1200`, height `800`, scale `2.0`.
- `walls` (4), as `[x0, y0, x1, y1]`:
  - top `[200, 160, 1000, 160]`
  - bottom `[200, 640, 1000, 640]`
  - left `[200, 160, 200, 640]`
  - right `[1000, 160, 1000, 640]`
- `openings` (2):
  - **door**: `cx=400, cy=640, w=80, h=20`, `validation_status=VALID`
  - **window**: `cx=800, cy=160, w=80, h=20`, `validation_status=VALID`

## Room boundary used in the DB-free tests (world px)
`[(200,160), (1000,160), (1000,640), (200,640)]` — the room rectangle × 2, specified
directly from the source drawing (room reconstruction itself is DB-backed and out of
scope for the offline tests).

Verified once at authoring time; `test_geometry_reference_pdf.py` re-asserts it on every
run so a regeneration that changes the geometry fails loudly.
