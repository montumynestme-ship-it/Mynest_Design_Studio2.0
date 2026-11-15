# Phase 2 Step 3 — Reconstructed Wall Coverage & Confidence Audit

**Scope:** STRICT REPORT-ONLY. No source, fixtures, schema, or Git state changed; no commits; no AI/paid calls. One read-only analysis script was run from the scratchpad (outside the repo).
**Branch:** `feature/phase-1-empty-architectural-plans` · **Date:** 2026-11-14
**Evidence classes:** `VERIFIED` · `AGENT-REPORTED` · `INFERRED` · `UNKNOWN` · `NOT_ASSESSABLE`

---

## ⚠️ Headline finding (VERIFIED, high severity)

Only **~35% of reconstructed bands are high-confidence `MEASURED_FROM_PAIRED_FACES`**, and **Phase 2 Step 1 consumes ONLY those, exclusively** — so the other ~65% of physical walls are **dropped from the 3D shell** whenever ≥3 measured bands exist. For plan `f6b65d2b` the combined scene would render **21 of 56 walls (35 missing)**. This is a correctness regression introduced by Step 1's selection logic (not a backend reconstruction defect), and the single most important result of this audit. Details in §6.

---

## 1. Git state `VERIFIED`
Branch `feature/phase-1-empty-architectural-plans`; working tree unchanged from the Step 2 report (6 modified + untracked Phase 1/2 artifacts + 3 harnesses). Full `git status --short` in §Final. Nothing committed.

## 2. Fixtures & tests containing reconstruction data `VERIFIED`
| Fixture / test | Reconstruction data |
|---|---|
| `backend/storage/floor_plans/**/original.pdf` | Real plan PDFs (many; several are duplicate uploads) |
| `backend/storage/floor_plans/MR_MATHUR_BASIC_LAYOUT.pdf` | Real plan (failed to parse — see §Limits) |
| `tests/test_reconstructed_walls_layer.py` | Synthetic (paired/single/far-apart/degenerate) + real `f6b65d2b` counts |
| `tests/test_wall_thickness_provenance.py` | `f6b65d2b` 179-face invariant + synthetic provenance |
| `tests/test_wall_reconstruction.py`, `test_wall_topology.py`, `test_room_reconstruction_geometry.py`, `test_room_reconstruction_raster.py` | Topology/room reconstruction fixtures |
| `frontend/src/lib/measuredWalls.test.ts` | Synthetic selector tests (filter-level only) |

## 3. Counts by `thickness_source` (with denominators) `VERIFIED`
**Live test:** `tests/test_reconstructed_walls_layer.py::test_f6b65d2b_reconstructed_layer_and_face_invariant` **PASSED** — plan `f6b65d2b`: **179 face strokes → 56 bands = 21 MEASURED (37.5%) / 34 CONFIGURED_FALLBACK (60.7%) / 1 UNVERIFIED (1.8%)**.

**Offline multi-plan tally** (read-only script; `extract_walls` + `build_reconstructed_walls`, no DB), 29/30 PDFs parsed:
```
plan            faces  bands  meas   fb  unv  %meas
f6b65d2b          179     56    21   34    1   37.5
64-face plan       64      9     1    7    1   11.1   (appears several times)
10-face plan       10      7     3    4    0   42.9   (appears many times)
-------------------------------------------------------
TOTAL            1006    315   109  197    9   34.6
```
- **Aggregate: 109/315 bands MEASURED = 34.6%**; 197 FALLBACK = 62.5%; 9 UNVERIFIED = 2.9%.
- Denominator caveat (`VERIFIED`): the `unassigned` set contains **duplicate uploads** of a few plans, so the aggregate is weighted by duplicates. Distinct-plan coverage observed: **11.1%** (64-face), **37.5%** (f6b65d2b), **42.9%** (10-face). All well under 50%.

## 4. Do measured bands cover complete walls or fragments? `VERIFIED`
`build_reconstructed_walls` collapses the 179 face strokes to one band **per physical wall** (`wall_reconstruction.py:271-337`), merging collinear fragments first (`_collapse` Phase 1, `:147-172`) then pairing opposing faces (Phase 2, `:176-224`). A MEASURED band therefore represents a **complete** physical wall (its two faces), not a fragment. The 56 bands are a complete, de-duplicated wall set; the issue is confidence, not fragment coverage.

## 5. Root causes of missing / rejected high-confidence pairs `VERIFIED`
From `_collapse` (`:131-224`) and `build_reconstructed_walls` (`:303-326`):
1. **Single-face wall** — drawn as one stroke, no opposing parallel face → unpaired → `CONFIGURED_FALLBACK`. **Dominant cause** (34/56 on f6b65d2b).
2. **Face spacing outside `[0.65·th, min(pair_tol, 1.35·th)]`** where `th` is the plan-wide dominant thickness (`measure_tolerances`, `:45-106`) → not paired. A wall thicker/thinner than the dominant thickness cannot pair.
3. **Insufficient longitudinal overlap** `< max(0.75·th, 0.4·min_len)` (`:191`) → staggered/fragmented faces don't pair.
4. **Not a mutual best match** (`:205-208`) → three competing nearby faces leave one unpaired.
5. **Paired but separation implausible** (outside `[0.65·th, min(pair_tol,1.35·th)]` in `:320`) → `UNVERIFIED` (1/56).
6. **Angled walls** are excluded **upstream** (`geometry_extraction_service.py:158-161`, axis-aligned only) → never reach reconstruction.
7. **Single dominant-thickness assumption** — one `th` per plan, so plans with mixed wall thicknesses measure only the dominant family.
These fallbacks are **honest** (the code refuses to invent a thickness) — not bugs in the reconstruction. (`VERIFIED`.)

## 6. How records reach the renderer, and what triggers fallback `VERIFIED`
Flow: `scene_service.build_scene` emits `reconstructed_walls` (all 56 bands) → `scene.reconstructed_walls` → `Scene3DModal.tsx:167` / `BaseRenderBatch.tsx:258` pass it to `RoomScene3D` → `selectMeasuredWalls` → `solidWalls`.

**Two frontend gates, both lossy:**
- **`measuredWalls.ts:59`** — `if (w.thickness_source !== 'MEASURED_FROM_PAIRED_FACES') continue;` → **only the ~35% measured bands survive; the 65% FALLBACK/UNVERIFIED bands are discarded.**
- **`RoomScene3D` selection** — `solidWalls = measuredWalls.length >= 3 ? measuredWalls : boundaryWalls.length >= 3 ? boundaryWalls : realWalls`:
  - **`measuredWalls ≥ 3` (the common case):** the shell is the **measured subset only** → the discarded 65% of walls are **not rendered** (missing walls), and for an architectural room the complete closed `boundaryWalls` shell is **overridden** by a partial set.
  - **`measuredWalls < 3`:** falls back to `realWalls` (all face strokes) → every wall renders, but **doubled** (the pre-Step-1 behavior).

**`VERIFIED` defect (Step 1 selection):** the measured subset is used *exclusively* rather than as a *thickness refinement over a complete wall set*. Consequence for `f6b65d2b`: combined shell = 21 of 56 walls (**35 missing**). Pre-Step-1 rendered all walls (doubled); Step 1 traded "complete-but-doubled" for "single-but-incomplete."

**Fallback cause classification:** not "absent backend data" (all 56 bands are present) and not "room filtering" primarily — it is a **frontend selection choice** (filter to measured-only + exclusive use). The low measured **percentage** is a backend reconstruction-coverage property (§5); the **missing walls** are a frontend-selection defect.

## 7. Measured coverage vs real-world accuracy `VERIFIED`
`MEASURED_FROM_PAIRED_FACES` means a thickness was derived from two real faces' **pixel separation** — a geometric measurement in **world px**, explicitly **not** calibrated to millimetres (`wall_reconstruction.py:282-284`; `measure_tolerances` returns a px tolerance ~30px, never a per-wall mm thickness — `test_wall_thickness_provenance.py:69-73`). "Measured" ≠ "physically accurate." **No physical calibration is claimed or exists.**

## 8. Test-coverage gaps `VERIFIED`
- `measuredWalls.test.ts` asserts the filter **excludes** FALLBACK/UNVERIFIED bands — i.e. it **codifies the lossy behavior as correct** and never checks shell **completeness**.
- No test asserts the rendered shell contains **all** physical walls (count vs reconstructed bands), so the §6 missing-walls regression is **uncaught**.
- No fixture with **mixed wall thicknesses** (to exercise the single-dominant-thickness limit).
- No multi-plan coverage assertion; no live/real-plan render test.

## 9. Smallest safe next implementation proposal (NOT implemented)
Renderer-only, additive; fixes the §6 regression and raises effective coverage to 100% of walls:
1. **Consume ALL reconstructed bands, not just measured.** Change the selector to include every band (they are one-per-physical-wall centerlines), using `thickness_px` per band — the **measured** separation where `MEASURED_FROM_PAIRED_FACES`, else the honest `10.0 px` fallback — × `mpp`. This renders **every** wall once (no missing), dedups double-lines for the measured ones, and applies measured thickness where confident.
2. **Keep `boundaryWalls` precedence for architectural rooms** (don't let a partial set override the complete closed shell), or ensure the all-bands shell is complete before preferring it.
3. **Add a completeness regression test**: rendered shell wall count ≈ reconstructed band count (and ≥ physical wall count), plus a mixed-thickness fixture. Do not assert the filter drops bands.
No backend, schema, reconstruction-algorithm, canonical, `mpp`, or calibration change is required.

## 10. Limitations `VERIFIED` / `NOT_ASSESSABLE`
- **Supabase down** → no live combined-view render to visually confirm the missing-walls regression; the conclusion rests on verified counts + the exact selection code (conclusive) — **not** a production claim.
- **Duplicate PDFs** inflate the aggregate denominator (§3); distinct-plan figures given alongside.
- **`MR_MATHUR_BASIC_LAYOUT.pdf` failed to parse** (1/30) — not counted; cause not investigated (out of scope).
- All evidence is **synthetic/fixture + offline**; not generalized to production accuracy.

## Final — `git status --short` & no-change confirmation `VERIFIED`
```
 M frontend/src/components/design-studio/BaseRenderBatch.tsx
 M frontend/src/components/design-studio/DesignCanvas.tsx
 M frontend/src/components/design-studio/RoomScene3D.tsx
 M frontend/src/components/design-studio/Scene3DModal.tsx
 M frontend/src/lib/scene.ts
 M frontend/src/pages/DesignStudio.tsx
?? docs/audits/PHASE1_ARCHITECTURAL_VIEW_IMPLEMENTATION.md
?? docs/audits/PHASE2_DETERMINISTIC_3D_INSPECTION.md
?? docs/audits/PHASE2_STEP2_SHARED_WALL_DEDUP_FINDINGS.md
?? docs/audits/PHASE2_STEP3_RECONSTRUCTION_COVERAGE_AUDIT.md   (this file)
?? frontend/architectural-harness.html
?? frontend/measured-walls-harness.html
?? frontend/src/components/design-studio/ArchitecturalLayer.tsx
?? frontend/src/dev/architecturalHarness.tsx
?? frontend/src/dev/measuredWallsHarness.tsx
?? frontend/src/lib/architecturalView.test.ts
?? frontend/src/lib/architecturalView.ts
?? frontend/src/lib/measuredWalls.test.ts
?? frontend/src/lib/measuredWalls.ts
```
Only the authorized report was added. No source, fixtures, or canonical data changed; nothing committed; all harnesses and uncommitted work preserved. (The scratchpad analysis script lives outside the repo.)

---

### Bottom line
Reconstructed-wall measured coverage is **~35%** (distinct plans 11–43%); fallbacks are **honest** (single faces, off-dominant spacing, insufficient overlap, angled walls excluded upstream). The urgent issue is **not** backend coverage but **Phase 2 Step 1's frontend selection**, which consumes the measured subset **exclusively** and thereby **drops ~65% of walls** from the shell whenever ≥3 measured bands exist (f6b65d2b: 21 of 56 rendered). The smallest safe fix is to consume **all** reconstructed bands with per-band thickness — rendering every wall once, measured where confident — and add a completeness test. This should be prioritized over chasing higher measured coverage.

*Report-only. No application code, canonical data, or Git state was changed.*
