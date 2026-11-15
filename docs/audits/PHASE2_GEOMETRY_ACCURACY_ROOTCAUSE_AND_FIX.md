# Deterministic 2D→3D Geometry Accuracy — Root-Cause Report & First Fix

**Date:** 2026-11-14 · **Branch:** `feature/phase-1-empty-architectural-plans`
**Scope note:** The directive spans many P0/P1/P2 areas. Per its own rules (§10 "smallest compatible changes," confirmed-only; §13 stop conditions for contract/architecture changes), I did **root-cause verification first**, then implemented **one** small, high-confidence, renderer-only fix with tests, and I flag the remaining confirmed defects for separately-authorized work (several need contract changes). I did **not** attempt the whole directive in one pass.
**Evidence classes:** `VERIFIED` · `AGENT-REPORTED` · `INFERRED` · `UNKNOWN` · `NOT_ASSESSABLE`

---

## F. Git state `VERIFIED`
Branch `feature/phase-1-empty-architectural-plans`, HEAD `5660f42` (+ baseline `d1d65f7`). Phase 1 + Phase 2 Step 1 remain uncommitted (preserved across the session boundary). This task modified `RoomScene3D.tsx`, `lib/measuredWalls.ts`, `lib/measuredWalls.test.ts`, the dev harness, and added this report. **No commits.** (Directive path note: `measuredWalls.ts`/`wallCarve.ts` are under `frontend/src/lib/`, not `components/design-studio/`.)

---

## A. Root-cause report

### DEF-1 — Measured-shell selection dropped ~65% of walls `VERIFIED` → **FIXED this task**
- **Where:** `frontend/src/lib/measuredWalls.ts:59` (old) filtered to `MEASURED_FROM_PAIRED_FACES` only; `frontend/src/components/design-studio/RoomScene3D.tsx:437-442` (old) used `measuredWalls.length >= 3 ? measuredWalls : …` — the measured subset **exclusively**.
- **Why it's a defect:** `reconstructed_walls` is a **complete, de-duplicated** per-physical-wall set (one band per wall). Keeping only the measured subset and using it exclusively meant the ~65% of walls that are `CONFIGURED_FALLBACK`/`UNVERIFIED` were **not rendered** when ≥3 measured bands existed, and the complete closed `boundaryWalls` shell was overridden.
- **Impact (measured, from Phase 2 Step 3 audit):** measured coverage ≈35% (f6b65d2b: 21/56). The combined 3D scene would render **21 of 56 walls (35 missing)**. This was a correctness regression introduced by Step 1.

### DEF-2 — `_collapse` paired-face span is the UNION, not the overlap `VERIFIED` → **NOT fixed (flagged)**
- **Where:** `backend/app/services/wall_reconstruction.py:213-214` — `ov_a0 = min(fi["a0"], fj["a0"])`, `ov_a1 = max(fi["a1"], fj["a1"])` (variable named `ov_` but computes the union).
- **Why it's a defect (directive P0-A):** faces A `[0,100]` and B `[40,140]` yield a paired centerline `[0,140]`, including `[0,40]` and `[100,140]` supported by **one** face only. The measured centerline can claim length/thickness evidence it doesn't have.
- **Why not fixed here:** the correct behavior (overlap `[max(a0),min(a1)]` + preserve unmatched **tails** as separate single-face bands) changes band **extents and counts**, which would re-baseline the documented `test_reconstructed_walls_layer.py` assertions (56/21/34/1) and can alter room-reconstruction polygonization/topology. That is larger than a "smallest change" and risks existing tests → **needs a focused, test-re-baselined implementation** (directive P0-A asks for partial/full/non-overlap/reversed/fragment regression tests). Stop condition §13 (contract/topology risk) applies.

### DEF-3 — Full-plan combined scene is furniture-derived, not architecture-derived `VERIFIED` → **NOT fixed (flagged)**
- **Where:** `frontend/src/components/design-studio/Scene3DModal.tsx:57-67` — `combined` returns **null when `furniture.length === 0`** and otherwise uses a **furniture** bbox with **no `boundary`/`geometry_source`**.
- **Impact (directive P1 full-plan):** no architectural 3D model without furniture; room boundaries not preserved (rectangular floor fallback); walls outside the furniture bbox omitted; rotated-furniture bbox inexact. The DEF-1 fix improves wall completeness here, but preserving **per-room boundaries/openings** in one combined scene is a larger change (RoomScene3D renders a single room) → separate scoped work.

### Items requiring verification / likely separate work (not confirmed this task)
| Directive item | Status | Note |
|---|---|---|
| Opening bridge / explicit-wall-ID validation (P0) | `AGENT-REPORTED` (prior audits) | Prior audits found association is already evidence-gated (`_find_supporting_wall` projects within segment, rotation ≤25°, perp ≤ tol; unmatched → `verified:false NEEDS_REVIEW`, no teleport — `scene_service.py:224-331`). The directive's specific "explicit wall ID teleports" concern needs a fresh focused re-trace before any change. |
| Wall-ID identity across pipeline (critical item) | `INFERRED` / needs verification | IDs are enumeration-order (`wall_{i:03d}`); `reconstructed_walls` carries `source_wall_ids` provenance. Whether any consumer mismatches needs a dedicated cross-file trace + tests — a **contract-level** investigation (stop condition if it needs a stable-ID schema change). |
| `transform_box_to_canonical` w/h scaling; zero `image_scale`→1.0; mpp validation (P1 coords) | `INFERRED` | Reachability in the live `/scene` path unconfirmed (the vector path may not call it); verify before touching coordinate contracts. |
| Raster empty vs failure states (P0 rooms) | `INFERRED` | Needs explicit success/empty/failure modeling; verify current `reconstruct_rooms_raster` return contract first. |
| Scene/version binding race (P2) | `INFERRED` | `build_scene` + latest-version lookup are separate; needs a controlled concurrency test before change. |
| Diagonal/curved walls (§6) | `VERIFIED` unsupported | Extraction is axis-aligned only (`geometry_extraction_service.py:158-161`); preserved as-is, reported as a limitation (do not force). |

---

## B. Implementation report (DEF-1 fix only)
- **`lib/measuredWalls.ts`** — renamed `selectMeasuredWalls` → `selectReconstructedShell`; it now returns **every** reconstructed band (the complete wall set), one segment per band, with `thicknessM = thickness_px × mpp` and a new `measured: boolean` flag (true only for `MEASURED_FROM_PAIRED_FACES`). A fallback band's single-face centerline renders once at its 10 px fallback thickness — equivalent to the face stroke, never doubled. Fallback thickness is **clearly distinguished** (never labelled measured), per directive P1.
- **`RoomScene3D.tsx`** — consumes `selectReconstructedShell`; **reordered** `solidWalls` to `boundaryWalls → reconstructedShell → realWalls`. So:
  - architectural **per-room** renders keep the complete closed boundary shell (unchanged — no base-render regression);
  - the boundary-less **combined** view now renders the **complete** reconstructed shell (all walls once, measured thickness where confident, dedup of double-lines);
  - plans with no reconstruction fall back to raw face strokes exactly as before.
- **Minimality / compatibility:** renderer-only; no backend, API, schema, canonical, `mpp`, or reconstruction-algorithm change. `WALL_THICKNESS` constant kept as the final fallback; `buildWallPieces` already uses per-wall `thicknessM ?? WALL_THICKNESS`. Verified openings still carve correctly.

## C. Regression test report `VERIFIED`
```
cd frontend && npx tsc --noEmit        # → exit 0
cd frontend && npx vitest run src/lib  # → 7 files, 84 passed, 0 failed, 0 skipped
```
`measuredWalls.test.ts` (9 tests) rewritten to assert the new contract: a `CONFIGURED_FALLBACK` band is **included** as `measured:false` at its fallback thickness; an `UNVERIFIED` band is included; a **mixed** set of 3 bands returns **all 3** (not just the 1 measured); out-of-box/short/degenerate still excluded; offset relative to room centre. No existing assertion was weakened. (Backend untouched this task; its 84-test architecture baseline from prior sessions is unchanged.)

## D. Geometry validation `AGENT-REPORTED` (synthetic) / `NOT_ASSESSABLE` (live)
Harness (`/measured-walls-harness.html`, real `RoomScene3D` + synthetic scene) screenshot delivered: 4 measured outer walls (thick 0.2 m) **+ 1 CONFIGURED_FALLBACK partition (thin 0.1 m) = all 5 rendered once**, window carved. The thin partition (dropped before the fix) is now present, and thickness is honestly distinguished. **Live real-plan confirmation of the combined view is `NOT_ASSESSABLE`** — the backend is down (Supabase "tenant not found"), so no real `/scene` render. Synthetic evidence is not a production-fidelity claim.

## E. Risks & limitations `VERIFIED`
- **DEF-2 (`_collapse` union) is still present** — paired centerlines can over-claim extent until that focused fix lands; the DEF-1 fix does not change `_collapse`.
- **DEF-3 (full-plan)** — no architectural model without furniture, and per-room boundaries/openings aren't preserved in the combined view; the DEF-1 fix only improves wall completeness.
- **Physical scale is `UNVERIFIED`** — thickness is px × furniture-anchored `mpp`; no calibration. "Measured" = derived from two real faces, not physically accurate.
- **Combined-view scale is furniture-anchored** (`computeMpp`) — empty vs furnished plans scale differently (blocked CD-C).
- **No live verification** until Supabase is restored.

---

### Bottom line
Verified the highest-confidence defects and fixed the most impactful safe one: the renderer no longer drops the ~65% of walls lacking a high-confidence measured pair — the combined 3D scene now renders **every** physical wall once, measured thickness where confident and an honestly-flagged fallback otherwise. `tsc` 0, `vitest` 84, visual confirmed. The remaining confirmed defects (`_collapse` overlap/tails, full-plan architecture-derived assembly) and the unverified items (wall-ID identity, coordinate scaling, raster states, version binding) each need their own small, test-backed change — several touch contracts/topology and so, per the directive's stop conditions, await separate authorization. Nothing was committed.

*No canonical geometry, furniture, backend, schema, or API was changed. 2D remains authoritative.*
