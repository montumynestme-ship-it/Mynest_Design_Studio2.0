# Door/Window/Furniture Position Mismatch — Investigation & Result

**Outcome:** The reported **door/window/furniture position/dimension/rotation/room-transform mismatches are NOT reproducible** — the deterministic 3D reconstruction reproduces every canonical transform faithfully (`validate_scene_2d_to_3d` = `SCENE_FAITHFUL`, **0 mismatches**). The **only** reproducible issue is **room assignment** for 2 wall-mounted `kitchen-base` cabinets, whose canonical positions are correct but fall **outside the reconstructed Kitchen & Dining room boundary** (an upstream raster room-boundary under-capture). **No safe minimal fix exists offline** without moving user-authored furniture, force-snapping to satisfy a validator, or inventing room geometry — all prohibited. **STOPPED before any geometry change, per the stop conditions. No files changed. No TeleCRM access. No paid calls. DB read-only.**

Keep separate: **contract validation** (structured, below) vs **visual review** (not performed — `not_assessable` here).

## 1. Baseline
- Repo: `mynest-design-studio/` (MyNest). **Not a git repository** → no branch/commit/diff; working tree unchanged. TeleCRM never touched.
- Fixture: design version **`85759b78`** (v79), floor plan **`f6b65d2b`** (the standard test fixture + the generation `803af570` shown in `main_zip_222.zip`). Canonical: `walls=0`, `doors=0`, `windows=0` (top-level), furniture 35; openings exist as door/window furniture items.

## 2. Reproduction & classification (measured)
| Category | Result | Evidence |
|---|---|---|
| Door/window identity/dims/orientation/**wall association**/position | **NOT reproduced** | `validate_scene_2d_to_3d` = `SCENE_FAITHFUL`, 0 mismatches (checks openings' wall/offset/dims/orientation) |
| Furniture **position/dimensions/rotation** | **NOT reproduced** | same gate, 0 mismatches (checks uid/type/pos/dims/rot per object) |
| Furniture **room assignment** (wall-mounted kitchen-base) | **REPRODUCED** | `validate_scene_against_canonical` → "Rooms whose geometry is not proven from walls: ['Kitchen', 'Bedroom 3']"; 2 `kitchen-base` land in an UNCERTAIN fallback, not the CONFIRMED room |
| Coordinate conversion / axis / units | **NOT reproduced** | conversions round-trip exactly (prior coordinate-convention tests: 30 passed); positions world-px, faithful |
| Occlusion/cropping mistaken for misplacement | **not_assessable** | no visual review performed this cycle |

**`validate_scene_2d_to_3d`** is the authoritative object-for-object gate (it fails on any furniture move/rotate/resize/missing/extra/wrong-room and any door/window move/reorient/wall-change/missing/extra and any wall-geometry change). For v79 it returns **PASS / 0 mismatches** → the deterministic 3D reconstruction is **transform-faithful** to canonical.

## 3. Root cause of the one reproduced issue (room assignment)
`architectural_service.reconstruct_rooms` assigns furniture by polygon **containment** → else **wall-ownership** (`furniture.nearest_wall_id` ∈ a proven room's `supporting_wall_ids`, exactly one owner) → else **UNCERTAIN leftover** (`architectural_service.py` ~lines 282–321). For the 2 `kitchen-base`:
- **Containment fails:** the CONFIRMED **"Kitchen & Dining Area"** bbox is `x 1094–1486, y 326–875`. kb1 `(1605, 389)` is **119 px right** of the right edge; kb2 `(1396, 244)` is **82 px above** the top edge — **both outside the room's bounding box** (the chimney `(1230,368)` is inside, and is correctly assigned). Nearest CONFIRMED boundary distance: **118.7 px / 82.6 px** (~1.2 m / 0.8 m).
- **Wall-ownership fails:** enrichment did compute `nearest_wall_id` (kb1→`wall_162`, kb2→`wall_036`, `attached`), **but those walls are owned by ZERO CONFIRMED rooms** (`wall_036` is not in Kitchen & Dining's `supporting_wall_ids`) → `owners != 1` → no assignment.
- → both `kitchen-base` fall to the UNCERTAIN "Kitchen" fallback. Downstream this produces the `BASE_INVENTORY_MISMATCH` that blocked Kitchen rendering (prior report).

**Interpretation:** the furniture is **not misplaced** (canonical transforms are reproduced faithfully); the **reconstructed Kitchen & Dining room polygon under-captures** the counter zone where the cabinets sit (along walls `wall_162`/`wall_036`, which the raster reconstruction did not include in the room). This is an **upstream `room_reconstruction_raster` boundary** issue, not a door/window/furniture transform error. Source: `scene_service.build_scene` (walls/enrichment/rooms wiring, lines ~373–399), `room_reconstruction_raster` (room contours), `architectural_service.reconstruct_rooms` (assignment).

## 4. Why no fix was made (stop conditions)
A correction would require one of the following — **all prohibited by this task**:
- **Move/snap the cabinets** into the room → changes user-authored placements (and they are already canonical-faithful). ✗
- **Force assignment via a large tolerance** (the cabinets are 82–119 px / ~1 m outside; a near-boundary rule that large would mis-assign furniture in other plans) → "do not force furniture into rooms to satisfy a validator." ✗
- **Extend the room boundary** to include the counter zone → cannot be established from the structured data alone (the bounding walls aren't assigned to the room); doing so would **invent room geometry** and needs the PDF/raster visual to prove correctness. ✗

Per "Stop before making a speculative geometry change if … the proposed fix would require inventing geometry or changing user-authored placements," I stopped.

## 5. Before/after measurements
No "after" — no change made. **Before (measured):** K&D bbox `x 1094–1486, y 326–875`; kitchen-base at `(1605,389)` and `(1396,244)` → outside the bbox by 119 px (x) and 82 px (y) respectively; nearest CONFIRMED boundary = Kitchen & Dining at 118.7 px / 82.6 px; `nearest_wall_id` = `wall_162`/`wall_036`, owned by 0 CONFIRMED rooms. Transform fidelity: `validate_scene_2d_to_3d` PASS (0 mismatches).

## 6. Tests / validation run (read-only; no code changed)
```
# read-only DB + offline reconstruction (no provider/paid calls, no writes):
validate_scene_2d_to_3d(canonical_v79, scene)        -> passed=True, SCENE_FAITHFUL, 0 mismatches
validate_scene_against_canonical(canonical_v79, scene) -> geometry_faithful=False,
        only mismatch: "Rooms whose geometry is not proven from walls: ['Kitchen','Bedroom 3']"
```
No source changed → no new tests added and the standing offline geometry/coordinate suites (72 passed previously) are unaffected. (Existing `test_room_reconstruction_geometry.py::test_contained_furniture_is_assigned_outside_is_not_forced` already locks the "outside item is NOT force-assigned" behavior that this case correctly follows.)

## 7. Remaining risks & unresolved
- **Unresolved (upstream):** the Kitchen & Dining reconstructed polygon under-captures the counter zone, so wall-mounted cabinets there cannot be proven into the room. Fixing it safely requires PDF/raster visual analysis of `room_reconstruction_raster` for this plan — out of this offline structured scope — and must be validated to not regress other plans.
- **No transform defect** exists to fix (door/window/furniture positions are faithful); changing anything there would be a regression.

## 8. Next concrete action
Open a **separate, PDF-aware investigation of `room_reconstruction_raster`** for `f6b65d2b`: determine whether walls `wall_162`/`wall_036` (and the counter zone) should bound the Kitchen & Dining room, using the rendered PDF/raster as evidence. Only if the correct boundary is **proven from source geometry** should the room contour be extended (upstream), with a regression test that the 2 `kitchen-base` then assign to the CONFIRMED room and `validate_scene_2d_to_3d` still passes — **never** by moving furniture or forcing assignment. Until then, geometry is left unchanged (transforms are faithful; the deterministic fallback remains trustworthy).

**Honest note:** this is a structured contract investigation; no renders were generated or visually reviewed, and no single fixture is claimed to prove complete visual fidelity.
