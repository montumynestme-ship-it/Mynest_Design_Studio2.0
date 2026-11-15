# DEF-2 Independent Review & DEF-3 Readiness Assessment

**Date:** 2026-11-14 · **Branch:** `feature/phase-1-empty-architectural-plans` · **HEAD:** `5660f42`
**Mode:** Review-only. No source, tests, fixtures, or Git state changed; nothing committed. One read-only scratchpad probe (outside the repo) was run.
**Evidence classes:** `VERIFIED` (inspected/reproduced) · `AGENT-REPORTED` · `INFERRED` · `NOT_VERIFIED`

---

## A. Executive verdict
- **DEF-2: `ACCEPT`.** Independently reproduced: paired band = the true overlap (not union), tails preserved with correct provenance/classification, fixture counts reproduced, `_collapse`/topology genuinely untouched, downstream-safe. Minor non-blocking findings below.
- **DEF-1 compatibility: `VERIFIED`.** The complete reconstructed shell still renders measured + fallback bands; fallback is never mislabelled measured; no wall omitted or duplicated. One minor cosmetic interaction noted.
- **DEF-3 readiness: `READY FOR SEPARATE IMPLEMENTATION`** (frontend-only, no contract change), with a scope caveat about `RoomScene3D`'s single-room model.

## B/C. DEF-2 findings

### Confirmed-correct behavior `VERIFIED` (reproduced via `build_reconstructed_walls` directly)
- **Paired overlap is the intersection.** Directive's exact example `A[0,100]@0, B[40,140]@20` →
  `MEASURED (40,10,100,10)` ids `{wall_001, wall_002}` — i.e. `[40,100]` at the midline y=10, **not** `[0,140]`. ✓ (§4.1.1–4.1.4)
- **Tails preserved at each face's own centreline with single-face provenance:** `[0,40]@y0 {wall_001}` and `[100,140]@y20 {wall_002}`, both `CONFIGURED_FALLBACK`. ✓ (§4.2)
- **Degenerate / touching-only / no-overlap not measured:** `A[0,100]/B[100,200]` (no longitudinal overlap) → two `CONFIGURED_FALLBACK`, no measured band. The `_collapse` pairing gate (overlap ≥ `max(0.75·th, 0.4·min_len)`) prevents such a pair from ever reaching the measured branch. ✓ (§4.1.5)
- **3 parallel faces** `@0/@20/@40`: the closest mutual-best pair is measured, the third is single-face fallback — sane, no duplicate/overlapping bands. ✓
- **Thickness** = perpendicular `spread` (`consts[-1]-consts[0]`), set only when `spread ∈ [lo,hi]`; measured thicknesses on f6b65d2b all within `[19.77, 41.07]`. ✓ (§4.1.3)
- **Centreline consistency:** measured band at `(const_a+const_b)/2`; tails at their side's mean const. ✓
- **Determinism:** repeated `build_reconstructed_walls` runs are byte-equal. ✓ (§5 determinism)

### Provenance & classification `VERIFIED`
- Measured band keeps **both** source ids; each tail keeps **exactly** its one source id (probe: fallback bands have 1 id for tails/single faces; multi-id fallback bands are legitimate collinear-merged single-face walls, one const cluster → not measured). ✓ (§4.3)
- IDs are the real `wall_NNN` provenance (every band `source_wall_ids ⊆` the 179 face ids; no fabricated/index-derived id introduced beyond the existing `wall_{i:03d}` scheme, which is unchanged). ✓
- Classification uses the actual source-face perpendicular relationship (`id_const`), not a count/order accident. ✓

### Fixture counts `VERIFIED` (reproduced, not trusted)
`f6b65d2b`: **total 81 · measured 21 · fallback 59 · unverified 1** — reproduced exactly. The +25 bands are preserved tails (all map to real source segments); the measured count is stable because the same 21 `_collapse` pairs are simply trimmed to overlap. No physical wall **portion** is represented twice (overlap vs tail intervals are disjoint; a face id legitimately appears in both its overlap band and its tail band because the face spans both). No zero-length segs. The re-baselined test (`81/21/59/1`) is justified by geometry, with the reasoning in a code comment. ✓ (§6)

### Topology compatibility `VERIFIED` (from the actual diff)
`git diff` of `wall_reconstruction.py` touches only `_overlap` (adds `_TAIL_EPS`) and `build_reconstructed_walls` (loop + helpers `_face_lon`/`_seg_for`/`_emit`). `_collapse`, `repair_walls`, `measure_tolerances` are **unchanged** (grep over the diff for `_collapse`/`ov_a0`/`ov_a1`/`min(fi`/`max(fi` → no matches). `reconstruct_rooms_topology` consumes `repair_walls`, **not** `build_reconstructed_walls`, so topology cannot be affected — confirmed by the full topology suite passing. ✓

### Downstream compatibility `VERIFIED`
Only `scene_service.build_scene` (`:491`) consumes `build_reconstructed_walls`, passing the list straight into `scene["reconstructed_walls"]` with no count / one-band-per-wall / all-measured / index-identity assumption. The frontend `selectReconstructedShell` iterates **all** bands (no fixed count). Safe. ✓

### Defects / limitations (non-blocking)
1. `INFERRED` (low) — **Fallback-to-whole-measured path** (`:406-407`): if the two sides can't be resolved or `ov1-ov0 ≤ _TAIL_EPS`, the whole band is emitted as measured over the union. **Effectively unreachable** for real pairs (a measured band always has `spread>0` → both sides non-empty; the `_collapse` gate guarantees substantial raw overlap), so it's a defensive branch, not an observed defect — but it is the one place a union-extent measured claim could survive. Worth a guarding test.
2. `VERIFIED` (low) — **Thickness = full perpendicular `spread`** even for a contained pair; this is the distance between the outer faces, consistent with prior behavior and the pairing band, but it is a *separation*, not a calibrated physical thickness (correctly labelled px/uncalibrated).

### DEF-2 test-quality review `VERIFIED`
The 12 cases assert **actual geometry** (`seg` extents via `pytest.approx`), **classification** (`thickness_source`), **provenance** (`source_wall_ids` sets), centreline const, and determinism — not merely band counts. Good.
**Gaps (reported, not added):** no test for 3+ parallel faces / one face in multiple candidate pairings (behavior verified by probe, not locked); no near-`_TAIL_EPS` short-tail or pairing-tolerance-boundary (`lo`/`hi`) case; no explicit "touching-only not measured" or "no duplicate emitted bands" assertion; the unreachable fallback branch (finding 1) is untested. Severity low–medium (behavior independently probed sound; tests just don't pin these).

## D. DEF-1 regression findings `VERIFIED`
`frontend/src/lib/measuredWalls.ts` `selectReconstructedShell` has **no measured-only filter** (only an invalid-seg `continue`); it returns the **complete** set with a `measured: boolean` flag (true only for `MEASURED_FROM_PAIRED_FACES`). `RoomScene3D` order is `boundaryWalls≥3 → reconstructedShell≥3 → realWalls`. Therefore with DEF-2's output: every band renders once (measured + fallback + tails), fallback is never labelled measured, no wall is omitted, and none is doubled.
- `INFERRED` (low, live-only) — **DEF-1×DEF-2 cosmetic interaction:** a tail renders at its face's centreline (≈ half-thickness off the measured band's midline), so a partially-overlapping double-line wall shows a measured centreline over the overlap plus thin fallback tails slightly offset at the ends. Geometrically honest, not a duplicate/omission; may read as a small discontinuity at wall ends. Only visually confirmable with a live render (Supabase down).

## E. Test evidence (executed during THIS review)
```
cd backend
.venv/Scripts/python.exe -m pytest tests/test_reconstructed_walls_layer.py \
  tests/test_wall_reconstruction.py tests/test_wall_topology.py \
  tests/test_room_reconstruction_geometry.py tests/test_room_reconstruction_raster.py \
  tests/test_wall_thickness_provenance.py tests/test_geometry_extraction.py -q
  → 91 passed, 0 failed, 0 skipped, ~31s
```
Plus a read-only probe reproducing the overlap example, touching-only, 3-parallel, and the f6b65d2b 81/21/59/1 tally with integrity checks (all green). `git diff --check` clean. Not executed here (cited as `AGENT-REPORTED` from the DEF-2 report): the 76 geometry/scene + 66 scene-consumer runs (the latter needs ~2 min and image rendering). `mypy app` / `ruff format --check` were **not** re-run but are known pre-existing issues (see H).

## F. Git status & change isolation `VERIFIED`
Tracked (`git diff --stat`): **DEF-2** = `wall_reconstruction.py` (+123), `test_reconstructed_walls_layer.py` (+120); **Phase 1 + DEF-1** = `BaseRenderBatch` (+1), `DesignCanvas` (+16), `RoomScene3D` (+47), `Scene3DModal` (+2), `scene.ts` (+22), `DesignStudio` (+79). Untracked: 6 audit reports, `ArchitecturalLayer.tsx`, `architecturalView.ts(+test)`, `measuredWalls.ts(+test)`, 2 harness `.html` + 2 dev `.tsx`.
**Isolation:** DEF-2 lives entirely in 2 backend files; DEF-1/Phase 1 are disjoint frontend files; reports/harnesses are untracked. DEF-2 **can be reviewed and committed independently** of DEF-1/Phase 1. No unexplained/unrelated changes; no whole-file reformat churn.

## G. DEF-3 readiness `VERIFIED` (issues) / `INFERRED` (scope)
All reported issues confirmed against `Scene3DModal.tsx:57-67`: returns `null` when `furniture.length === 0`; bbox derived from furniture; the synthetic `combined` room carries **no** `boundary`, `geometry_source`, or `opening_placements`.
- **Affected component:** `Scene3DModal.tsx` (full-plan preview). Per-room base renders (`BaseRenderBatch`, `room={room}`) are **not** affected → AI base-render regression risk is low.
- **Data contracts:** none need to change — `Scene` already carries `walls`, `reconstructed_walls`, and per-room `boundary`/`opening_placements`. No API/schema change.
- **Minimal scope:** (1) build the combined bbox from the **architectural** extent (walls/rooms), not furniture; (2) don't return `null` with zero furniture; (3) still source furniture from the selected version (unchanged). This alone makes empty plans render and includes walls outside the furniture bbox (DEF-1's shell already draws all in-box reconstructed walls).
- **Constraint / larger follow-on:** `RoomScene3D` renders a **single** room with one `boundary`/floor. Preserving **per-room** boundaries, polygon floors, and opening placements in one combined scene exceeds the minimal change and bumps against that single-room model — a separate, larger step (render multiple boundaries, or pass an architectural multi-room structure). Recommend splitting DEF-3 into (a) extent/empty-plan slice (small, safe) and (b) per-room-boundary preservation (larger).
- **Regression tests to require:** empty-plan renders a model; combined extent covers all walls; no furniture inferred into geometry; existing per-room render unchanged.

## H. Remaining risks
- **Live real-plan validation `NOT_VERIFIED`** — Supabase down; no end-to-end `/scene` render, so the DEF-1×DEF-2 cosmetic interaction and the combined-view behavior are unconfirmed on a real plan.
- **Pre-existing repo issues (not introduced by DEF-2):** `wall_reconstruction.py` does not pass `ruff format --check` on the committed baseline either (running `ruff format` rewrites the whole file — forbidden churn); `mypy app` halts on unrelated errors (shapely stubs, a numpy/py3.12 syntax issue). `ruff check` (lint) on the changed file passes.
- **Calibration:** thickness is uncalibrated px (honestly labelled); no physical-mm claim.
- Many duplicate/old `unassigned` plan PDFs inflate any aggregate coverage denominator (noted in Step 3).

## I. Final recommendation
**Accept DEF-2** and **authorize DEF-3**, split into the small extent/empty-plan slice first, then the larger per-room-boundary preservation. Before or alongside DEF-3, consider: (1) a guarding test for the unreachable whole-band-measured fallback and the touching-only/boundary cases (test gaps, §C); (2) deciding commit strategy for the growing uncommitted stack (DEF-2 is independently committable). Live verification of the combined view and the DEF-1×DEF-2 end-rendering remains blocked until Supabase is restored.

*Independent review. No code, tests, fixtures, or Git state were modified.*
