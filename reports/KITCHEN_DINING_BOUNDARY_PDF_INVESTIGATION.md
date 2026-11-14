# Kitchen & Dining Boundary — PDF-Aware Investigation

**Outcome:** The prior findings are **confirmed against the PDF source**, and the root cause is now **source-proven**: the reconstructed Kitchen & Dining polygon **under-captures** because the raster **floor contour** was cut at the counter inner edges (its top/right edges lie on **no structural wall** — open cuts), while the kitchen is actually **enclosed by real structural walls** (`wall_036` top, `wall_162`/`wall_161`/`wall_163`/`wall_164` right) with the two `kitchen-base` counters correctly placed inside that enclosure. **No geometry was edited** — a minimal, provably-safe correction is **not** available (the enclosing walls lie outside the current room, so the fix requires a larger room-reconstruction change and an owner decision on floor-contour vs wall-enclosure semantics). **No files changed. No TeleCRM access. No paid calls. DB read-only.** Bedroom 3 has a **different, benign** cause (a window opening 27px outside the interior; the room renders fine).

## 1. Baseline & source identity (verified)
- Repo: `mynest-design-studio/` (MyNest). **Not a git repository** → no branch/commit/diff; working tree unchanged. TeleCRM never touched.
- Canonical: design version **`85759b78`** (v79), floor plan **`f6b65d2b`**.
- **Source PDF:** `backend/storage/floor_plans/unassigned/unassigned/f6b65d2b-…/original.pdf` — type pdf, **4179 bytes, sha256(16) `e440a2184e9196ad`** (a small vector plan). Not substituted.

## 2. Reported findings — verified
| Prior finding | Verified? |
|---|---|
| `validate_scene_2d_to_3d` = SCENE_FAITHFUL, 0 transform mismatches | **Yes** (re-run) |
| `validate_scene_against_canonical` flags Kitchen + Bedroom 3 not proven from walls | **Yes** |
| 2 `kitchen-base` outside the K&D polygon | **Yes** — centres (1605,389),(1396,244); K&D bbox x[1094–1486] y[326–875] |
| `wall_162`/`wall_036` owned by zero confirmed rooms | **Yes** |
| Cabinet transforms match canonical | **Yes** (faithful) |

## 3. PDF-aware root cause (source-proven)
Wall geometry (from the extracted structured walls — all **structural**, black `#141414`, thickness 10):
- **`wall_036`** horizontal at **y=214**, x 1139–1490 — a real wall **above** the K&D top edge (y=326).
- **`wall_162`** vertical at **x=1647**, y 232–493 — a real wall **right of** the K&D right edge (x=1486).

**Do the reconstructed polygon's edges lie on walls?** (measured)
- K&D **top edge y≈326**: only `wall_098` (a 22px stub) — essentially an **OPEN CUT** (no wall).
- K&D **right edge x≈1486**: **no wall at all** — an **OPEN CUT**.

**Are the excluded counter strips wall-enclosed?** (measured)
- **Top strip** (y 214–326, the top `kitchen-base`): bounded above by `wall_036`; **open on the left and (mostly) bottom** → connects to the kitchen.
- **Right strip** (x 1486–1647, the right `kitchen-base`): bounded by `wall_161` (top), `wall_162` (right), `wall_163`+`wall_164` (bottom); **open on the left** → connects to the kitchen.

**Conclusion:** the kitchen is enclosed by `wall_036` (top) and `wall_161/162/163/164` (right); the two `kitchen-base` are **counters against those walls, inside the enclosure**. The reconstructed polygon stops at **open cuts** (the counter inner edges) because the **raster floor-region contour excludes the perimeter counter footprints** (counters are drawn as filled/hatched boxes, so the floor mask carves around them). So the polygon is a correct **floor** contour but an **under-captured room enclosure**. This is NOT cabinetry-mistaken-for-walls — `wall_036`/`wall_162` are genuine structural walls; the cabinets are separate furniture inside them. **Earliest responsible stage:** `room_reconstruction_raster` (floor-contour extraction) — the proven room's boundary/`supporting_wall_ids` follow the floor mask, so the enclosing walls `wall_036`/`wall_162` are never associated with the room (hence "owned by zero confirmed rooms").

*(Visual evidence: `kd_boundary_overlay.png`, sent to you — blue = reconstructed polygon; red = `wall_036`/`wall_162`; green = the two counters in the excluded strips.)*

## 4. Bedroom 3 — independent cause (benign, not a defect)
The CONFIRMED "Bedroom 3" room contains all its furniture (door, wardrobe, bed, 2 side-tables, dressing-table) and **rendered successfully** (one of the 4 successful sections in generation `803af570`). Its only UNCERTAIN-fallback item is a **single window opening** at (875,1547), 27.2px outside the eroded interior (expected for a wall-mounted opening; `nearest_wall=wall_073`). **No render impact; not a reconstruction defect** — distinct from the Kitchen cause.

## 5. Why no geometry was edited (Phase 3 safety gate not met)
The source establishes the Kitchen *is* wall-enclosed, but a **minimal, provably-safe** correction is not available, and the required change is **not minimal**:
- The enclosing walls (`wall_036` y=214, `wall_162` x=1647) lie **outside the current room's bbox**, so no bbox/proximity rule captures them without an arbitrary distance threshold (**prohibited**).
- Extending the **floor** contour over the counter footprints would **convert fixtures into floor/walls** (**prohibited**: "do not invent walls or convert non-structural cabinetry into walls").
- Correctly enclosing the counters requires either **preferring the vector wall cycle** (`reconstruct_rooms_topology`) for this room or **re-deriving the room enclosure from the structural walls** — a core room-reconstruction change with **high cross-plan regression risk**, not a one-line fix.
- There is a genuine **semantic/owner decision**: should the deterministic room boundary be the **floor region** (current, excludes counters) or the **wall enclosure** (includes counters for rendering)? That decision changes behavior for every plan and must be made by the owner, not guessed.

Per "if the source does not establish the [safe fix] unambiguously, do not edit geometry; report the ambiguity and propose the smallest owner decision," I stopped.

## 6. Before/after evidence
No "after" (no change). **Before (measured):** K&D bbox x[1094–1486] y[326–875]; top/right edges on open cuts (no wall); enclosing walls `wall_036`(y214), `wall_162`(x1647) real & structural but unassociated with the room; `kitchen-base` at (1605,389),(1396,244) in the wall-enclosed counter strips, 119px/82px beyond the bbox; `validate_scene_2d_to_3d` PASS (transforms faithful).

## 7. Tests / validation run (read-only; no code changed)
```
validate_scene_2d_to_3d(v79)         -> passed=True, SCENE_FAITHFUL, 0 mismatches
validate_scene_against_canonical(v79)-> geometry_faithful=False, only: Kitchen & Bedroom 3 not proven from walls
```
No source changed → no new tests added; standing offline geometry suites (72 passed previously) unaffected.

## 8. Remaining uncertainty & next action (smallest owner decision)
- **Owner decision needed:** define whether the deterministic room boundary should follow the **wall enclosure** (so perimeter counters/fixtures are inside the room) or remain the **floor region**. This is the crux and governs any fix.
- **If wall-enclosure is chosen:** the smallest scoped change is in `room_reconstruction_raster` / room-proving — associate a proven room with the **structural walls that enclose it** (not only those touching the floor contour), so `wall_036`/`wall_162` become `supporting_wall_ids` of Kitchen & Dining and wall-ownership assigns the counters **without moving furniture or inventing geometry**. It must ship with a regression test on this exact fixture (the 2 `kitchen-base` assign to the CONFIRMED room; `validate_scene_2d_to_3d` still PASS) **and** a broad room-reconstruction regression run to prove no other plan regresses.
- **Bedroom 3:** no action (benign window-opening fallback, renders fine).

**Honest note:** structured + PDF-raster evidence only; no AI renders were generated or visually compared. The transform geometry is faithful; the open item is the room-enclosure semantics, which is an owner decision.
