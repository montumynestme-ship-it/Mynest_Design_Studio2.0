# DEF-2 — Correct Paired Wall-Face Overlap & Preserve Unmatched Tails

**Date:** 2026-11-14 · **Branch:** `feature/phase-1-empty-architectural-plans`
**Outcome:** Implemented (backend + tests only). No commits. No frontend/canonical/API/schema change.
**Evidence classes:** `VERIFIED` · `AGENT-REPORTED` · `INFERRED`

---

## 1. Root cause & changed functions `VERIFIED`
The paired-face centreline claimed the **union** of the two faces' longitudinal extents rather than their **intersection**, so a measured centreline could claim double-line support over regions where only one source face exists.

- **Defect site:** `backend/app/services/wall_reconstruction.py` `_collapse()` emitted the paired span as `min(a0)/max(a1)` (union).
- **Where the false claim is realized:** `build_reconstructed_walls()` is the only function that labels a band `MEASURED_FROM_PAIRED_FACES` and assigns the measured `thickness_px`. It consumed the union span and marked the whole thing measured.

**Key constraint discovered (and respected):** `_collapse()` is **shared** — `repair_walls()` → `_collapse()` feeds *both* `build_reconstructed_walls()` (DEF-2's layer) *and* `reconstruct_rooms_topology()` (room topology, explicitly **out of scope** per §5). Changing `_collapse` to overlap+tails **broke 14 topology/room tests** (polygonization needs the full collinear wall extent to close rooms). So the fix was placed in **`build_reconstructed_walls()` only**, leaving `_collapse`/`repair_walls`/topology byte-identical.

**Changed functions:** `build_reconstructed_walls()` (new overlap/tail split) + a module constant `_TAIL_EPS`. `_collapse()` unchanged.

## 2. Before/after geometry `VERIFIED`
Faces A `[0,100]`@y100 and B `[40,140]`@y120 (20 px apart, a valid pair):

| | Measured centreline | Tails |
|---|---|---|
| **Before** | `[0,140]` @ y110, thickness 20 (claims measured over `[0,40]` & `[100,140]` where only one face exists) | none — tails absorbed into the measured band |
| **After** | `[40,100]` @ y110, thickness 20 (only the shared overlap) | `[0,40]`@y100 (face A) + `[100,140]`@y120 (face B), each a single-face `CONFIGURED_FALLBACK` band |

## 3. Unmatched-tail representation `VERIFIED`
Each tail is emitted as its **own band** at that face's **own centreline const** (not the pair midline), carrying **only that face's** `source_wall_ids` → one source const downstream → classified `CONFIGURED_FALLBACK` (never measured). Tails shorter than `_TAIL_EPS` (the module's existing `1e-6` non-degeneracy floor — not a new invented threshold) are not emitted, avoiding zero-length slivers. No wall portion is discarded; no continuity is fabricated.

## 4. Source provenance (before → after) `VERIFIED`
- **Paired band:** `source_wall_ids` = both faces' ids, **unchanged** (`{wall_001, wall_002}`).
- **Tail bands (new):** each carries exactly its single source face id (`("wall_001",)`, `("wall_002",)`).
- All original face-stroke ids are preserved and every band maps to real source faces (verified: `all source_wall_ids non-empty`, all ⊆ the 179 face ids). `structured_walls` (the 179 face layer) is untouched.

## 5. Modified files `VERIFIED`
| File | Change |
|---|---|
| `backend/app/services/wall_reconstruction.py` | `build_reconstructed_walls()` splits measured pairs into overlap (measured) + tails (fallback); added `_TAIL_EPS`. `+101/−22`. |
| `backend/tests/test_reconstructed_walls_layer.py` | 10 new DEF-2 cases + re-baselined f6b65d2b counts with justification. `+~110`. |

## 6. Changed reconstructed-wall counts + geometric explanation `VERIFIED`
Plan `f6b65d2b` (179 face strokes), offline `build_reconstructed_walls`:

| source | before | after | why |
|---|---|---|---|
| total bands | 56 | **81** | +25 preserved tails |
| `MEASURED_FROM_PAIRED_FACES` | 21 | **21** | **stable** — same 21 genuine pairs, now trimmed to the overlap |
| `CONFIGURED_FALLBACK` | 34 | **59** | +25 = the unmatched tails, honestly single-face |
| `UNVERIFIED` | 1 | **1** | unchanged |

The measured count is unchanged (no pair gained or lost); the 25 new bands are exactly the tails that were previously (incorrectly) absorbed into measured spans. Verified: measured thicknesses still within the pairing band `[19.77, 41.07]`; no zero-length segs. The baseline test was updated to `81/21/59/1` **with the geometric reason in a comment** (per §4, not a weakening).

## 7. Room-topology regression `VERIFIED`
`_collapse`/`repair_walls` untouched → topology is byte-identical. `test_wall_topology.py`, `test_wall_reconstruction.py`, `test_room_reconstruction_geometry.py`, `test_room_reconstruction_raster.py` all **pass unchanged**. (An earlier attempt that edited `_collapse` broke 14 of these — confirming the fix must live in `build_reconstructed_walls`.)

## 8. Test commands & results `VERIFIED`
```
cd backend
.venv/Scripts/python.exe -m pytest tests/test_reconstructed_walls_layer.py \
  tests/test_wall_reconstruction.py tests/test_wall_topology.py \
  tests/test_room_reconstruction_geometry.py tests/test_room_reconstruction_raster.py \
  tests/test_wall_thickness_provenance.py -q           # → 68 passed
# broad geometry/scene/opening consumers
... test_geometry_extraction / test_opening_placement{,_fidelity} / test_geometry /
    test_validation_geometry / test_containment_sectioning / test_furniture_placement_2d_to_3d
                                                          # → 76 passed
# scene/reconstructed_walls consumers (build_scene etc.)
... test_2d_to_3d_fidelity / test_air03_merge_integration / test_annotation_exclusion /
    test_door_window_merge / test_furniture_inventory_preservation /
    test_furniture_ownership_boundary / test_gallery_provenance
                                                          # → 66 passed (~2 min, image/scene render)
ruff check app/services/wall_reconstruction.py            # → All checks passed
```
**12 DEF-2 cases covered** (partial/full/contained/no-overlap/reversed/incompatible-perp/fragments-merge/genuine-gap/provenance/determinism/overlap-extent invariant). 0 failures, 0 skips across all runs.

## 9. Remaining limitations `VERIFIED` / `INFERRED`
- **`ruff format --check` is red on this file** — but the **committed baseline is also red** (it "would reformat" before my change); `ruff format` rewrites the **entire file (384 lines)**, which §10 forbids as unrelated churn. So I fixed lint (`ruff check` green) and kept formatting minimal. This is a **pre-existing** repo state, not introduced by DEF-2. (`VERIFIED`.)
- **`mypy app`** surfaces pre-existing, unrelated errors (shapely missing stubs; a numpy/py3.12 `type`-statement syntax error that halts analysis). `wall_reconstruction.py` itself reports no new mypy error. (`VERIFIED` pre-existing.)
- **Live real-plan validation** of the 3D render is `NOT_ASSESSABLE` — Supabase is down; evidence is offline source + the f6b65d2b fixture + synthetic cases.
- The overlap/tail split applies to the **reconstructed-walls layer** (consumed by the 3D renderer after DEF-1). Room topology deliberately still uses the full collinear extent (correct for closing rooms).

## 10. Git diff & status `VERIFIED`
```
 M backend/app/services/wall_reconstruction.py       (+101 / −22)
 M backend/tests/test_reconstructed_walls_layer.py   (+~110)
```
Plus the previously-uncommitted Phase 1 / Phase 2 (DEF-1) work and reports, unchanged. **Nothing committed.** No frontend, canonical, API, schema, or room-topology change.

---

### Bottom line
The measured paired centreline now spans **only the interval both faces share**, and each pair's unmatched tails are **preserved as honest single-face fallback bands** — no measured claim beyond real double-line support, no wall portion discarded. The fix lives in `build_reconstructed_walls` (not the shared `_collapse`), so **room topology is untouched and green**. f6b65d2b: 56→81 bands (21 measured stable, +25 fallback tails), geometrically justified; 12 DEF-2 cases + all downstream consumers pass.

*Backend reconstruction layer only. 2D canonical geometry remains authoritative.*
