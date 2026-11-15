# Post DEF-3 Verification, Git Audit & Next-Phase Readiness

**Date:** 2026-11-15 · **Branch:** `feature/phase-1-empty-architectural-plans` · **HEAD:** `5660f42`
**Mode:** Review / verification / planning only. No source, tests, reports, harnesses, DB, or Git state changed; nothing committed. Read-only DB probes and scratchpad scripts were run.
**Evidence:** `VERIFIED` · `AGENT-REPORTED` · `INFERRED` · `NOT_ASSESSABLE`
**Headline:** **Supabase is back UP** (DB AUTH OK) — live validation is unblocked, and a read-only real-plan `build_scene` independently confirms DEF-2 and DEF-3 on actual data.

---

## 1. Executive verdict
- **DEF-1: `ACCEPT`** — complete reconstructed shell; verified on the real plan (81 bands render; measured + fallback both included).
- **DEF-2: `ACCEPT`** — overlap (not union) + preserved tails; real-plan counts reproduced; `_collapse`/topology untouched; 68 core tests green.
- **DEF-3 slice: `ACCEPT`** — architecture-derived combined scene; the real plan has **zero furniture** and now renders (was blank), with 13 verified openings aggregated.
- **DEF-3 follow-on: `ACCEPT`** — per-room polygon floors; real plan yields 5 architectural room floors (incl. one concave), fallback rooms excluded.

## 2. Evidence
### `VERIFIED` (inspected / reproduced this review)
- **Real-plan `build_scene('f6b65d2b')`** (live DB + PDF, read-only): `reconstructed_walls = 81 {MEASURED 21, CONFIGURED_FALLBACK 59, UNVERIFIED 1}`; **5 rooms, all `geometry_source === 'architectural'`, CONFIRMED**, boundary pts 4–6 (one **concave**, 6 pts); **13 opening_placements, all verified**; **furniture 0**; walls 179; `geometry_invalid = False` / `GEOMETRY_FAITHFUL`.
- **DEF-2 source** unchanged outside `build_reconstructed_walls` (+ `_TAIL_EPS`); `_collapse`/`repair_walls`/topology untouched (diff + 68 tests).
- **`collectRoomFloors`** returns only `geometry_source === 'architectural'` rooms with `boundary.length ≥ 4`, copies vertices (no mutation); exact-match aligns with the real data (all rooms exactly `'architectural'`) and with `RoomScene3D.floorShape`.
- **Frontend:** `tsc --noEmit` → 0; `vitest run src/lib` → **98 passed**.
- **Supabase:** TCP reachable + `DB AUTH OK`.
### `AGENT-REPORTED`
- The other 3 of 5 failures in the 4-hour run (only 2 captured in the summary tail).
### `INFERRED`
- The 5 full-suite failures are DB-warm-up flakiness (see §4).
### `NOT_ASSESSABLE`
- The **in-app 3D render** of the real combined view (needs the user's backend on :8000 running + browser) — not exercised here; the underlying scene DATA is verified.

## 3. DEF-3 geometry review `VERIFIED`
- **Polygon correctness:** `collectRoomFloors` filters architectural + closed boundary (≥4), copies vertices. `extraFloorShapes` builds one `THREE.Shape` per polygon with the SAME world→metre mapping as the single-room floor (`mx=(px−cx)·mpp`, `mz=(py−cy)·mpp`) and the SAME X/Z axis convention as the walls → floors align with walls. Concave handled (real plan has a 6-pt room; `ShapeGeometry` triangulates concave). Degenerate (<4 pts) excluded → no invalid mesh.
- **Fabrication honesty:** fallback/UNCERTAIN rooms get **no** polygon floor (verified visually: fallback room = open void) — never a rectangular/furniture-derived floor presented as architectural.
- **Holes/courtyards:** a room boundary is a single ring upstream (no holes in the data), so none are silently filled; interior voids aren't representable (matches backend — `INFERRED` limitation, not a defect).
- **Floor priority (verified precedence):** `room.floorShape` → `roomFloors` (combined) → rectangular fallback. With `roomFloors = []` or omitted (every single-room render incl. `BaseRenderBatch`), behaviour is **byte-identical** → no per-room base-render regression.
- **Opening/room ownership:** openings carry a **global** `wall_id` (scene-wide `wall_NNN`, not per-room), so aggregating all rooms' `opening_placements` creates **no ID collision**. Carving is **geometric** (position/perp/angle match to the rendered wall), so an opening carves its own supporting wall regardless of room; the global aggregation has **no cross-room mis-carve**. Verified vs. unverified behaviour preserved (only verified carve).
- **Materials/height:** shared wood material + single ground plane — a **visual** limitation (adjacent floors read continuous), **not** a geometry defect.

## 4. Regression results `VERIFIED`
```
FRONTEND  (cwd frontend)
  npx tsc --noEmit                  → exit 0
  npx vitest run src/lib            → 8 files, 98 passed, 0 failed, 0 skipped (~1.3s)

BACKEND   (cwd backend, venv python)
  pytest test_reconstructed_walls_layer, test_wall_reconstruction, test_wall_topology,
         test_room_reconstruction_geometry, test_room_reconstruction_raster,
         test_wall_thickness_provenance -q
                                    → 68 passed, 2.23s   (DEF-2 core — no DB needed)
  (the two 4-hour-run failures) isolated re-run
                                    → 2 passed, 7.65s
```
**The overnight full run** (`+ test_geometry_extraction`, during Supabase's post-restore warm-up) reported **5 failed / 86 passed in 4h02m**. The pathological runtime and the fact that the two identifiable failures (`test_geometry_extraction::test_geometry_invalid_true_when_not_faithful`, `::test_windows_outside_polygon_confirmed_only_by_wall_ownership`) **pass in 7.65s in isolation** indicate **DB-connection flakiness during the free-tier instance resume — not a code regression**. The DEF-2 reconstruction/topology core is green and fast. `mypy app` / `ruff format --check` not re-run (known pre-existing issues; `ruff check` on the changed file passes). **Recommend a clean full backend re-run now that the DB is warm.**

## 5. Git audit `VERIFIED`
`git diff --check` clean. Branch `feature/phase-1-empty-architectural-plans`, HEAD `5660f42`.

| Group | Files | Independent? |
|---|---|---|
| **Phase 1 view** | `DesignCanvas.tsx` (+16), `DesignStudio.tsx` (+79); new `ArchitecturalLayer.tsx`, `architecturalView.ts`(+test) | ✅ yes (disjoint from the 3D files) |
| **DEF-2** | `backend/.../wall_reconstruction.py` (+123), `tests/test_reconstructed_walls_layer.py` (+120) | ✅ yes (backend only) |
| **DEF-1** | `scene.ts` (+22), `BaseRenderBatch.tsx` (+1), `RoomScene3D.tsx` (shell part), new `measuredWalls.ts`(+test) | ⚠️ shares `RoomScene3D` with DEF-3 |
| **DEF-3 slice** | `Scene3DModal.tsx` (part), new `combinedScene.ts`(buildCombinedRoom)(+test) | ⚠️ shares `Scene3DModal` with DEF-1/follow-on |
| **DEF-3 follow-on** | `RoomScene3D.tsx` (floors), `Scene3DModal.tsx` (roomFloors), `combinedScene.ts` (collectRoomFloors)(+test) | ⚠️ shares `RoomScene3D`/`Scene3DModal` |
| **Reports** | `docs/audits/*.md` (10 untracked) | ✅ |
| **Harnesses** | see §6 | ✅ |

**Dependencies:** DEF-1 and both DEF-3 steps co-edit `RoomScene3D.tsx` and `Scene3DModal.tsx` (adjacent but distinct hunks), and DEF-3 depends on DEF-1's `scene.ts` `ReconstructedWall` type and `measuredWalls`/`combinedScene` libs. **No unexplained/unrelated modifications.** No test relies on an uncommitted feature across groups (DEF-2 tests ↔ backend only; frontend lib tests ↔ their own libs).

## 6. Harness cleanup `VERIFIED`
**No production/test code imports any of these** (grep confirmed). All safe to remove.
| Harness | Paths | Tracking |
|---|---|---|
| Phase A wall-carve | `frontend/src/dev/wallCarveHarness.tsx`, `frontend/wallcarve-harness.html` | **tracked** (in baseline `d1d65f7`) → remove via `git rm` |
| Phase 1 architectural | `frontend/src/dev/architecturalHarness.tsx`, `frontend/architectural-harness.html` | untracked → file delete |
| DEF-1 measured-walls | `frontend/src/dev/measuredWallsHarness.tsx`, `frontend/measured-walls-harness.html` | untracked |
| DEF-3 combined-scene | `frontend/src/dev/combinedSceneHarness.tsx`, `frontend/combined-scene-harness.html` | untracked |
(Note: `frontend/src/harness.tsx` + `harness.html` are a **pre-existing** structural harness, not one of these — leave them.)

## 7. Proposed commit plan (NOT executed — awaiting approval)
Because DEF-1 and DEF-3 co-edit `RoomScene3D.tsx`/`Scene3DModal.tsx`, a clean 5-commit split needs `git add -p` hunk staging. Recommended **pragmatic sequence** (each independently revertible):
1. **Phase 1 view** — `DesignCanvas.tsx`, `DesignStudio.tsx`, `ArchitecturalLayer.tsx`, `architecturalView.ts`(+test).
2. **DEF-2** — `wall_reconstruction.py`, `test_reconstructed_walls_layer.py` (backend; fully isolated).
3. **DEF-1 + DEF-3 (frontend 3D)** — `scene.ts`, `measuredWalls.ts`(+test), `BaseRenderBatch.tsx`, `RoomScene3D.tsx`, `Scene3DModal.tsx`, `combinedScene.ts`(+test). *(Split into 3 via `git add -p` only if per-feature commits are required; the shared files make a single frontend-3D commit lower-risk.)*
4. **Docs** — `docs/audits/*.md`.
- **Exclude the 4 harnesses** (or a separate `git rm` commit for the tracked wall-carve one).
- **Tests ride with their implementation commit.** Each commit builds (`tsc`/`vitest`/`pytest` per group). Required gate before #2: the clean backend re-run (§4). Branch first already done.

## 8. Live-validation readiness `VERIFIED` (DB) / checklist
Supabase reachable; `build_scene` retrieves a real plan (`f6b65d2b`), pins the current version, and returns real architectural boundaries (5) + verified openings (13). **The in-app 3D combined render still needs the user's backend running on :8000** (I must not bind it) + the browser.
**Live checklist (run when the app is up):** 1) empty architectural plan (f6b65d2b IS one — 0 furniture); 2) a furnished plan; 3) multiple architectural rooms (✓ 5); 4) a fallback/UNCERTAIN room (confirm no floor); 5) shared partition; 6) doors & windows carve (✓ 13 verified); 7) non-rectangular room (✓ one 6-pt room); 8) room with incomplete boundary (confirm excluded); 9) furniture near architectural bounds; 10) potential colliding wall IDs (IDs are global — confirm no collision).

## 9. Remaining engineering risks (ranked)
| Rank (by canonical-corruption → 3D-correctness → provenance → UX → dependency) | Item | Class |
|---|---|---|
| — (no canonical-corruption risk from DEF-1/2/3 — all additive, no canonical writes) | — | — |
| 1 | **Wall-ID identity** across extraction/reconstruction/scene (enumeration-order ids) | Hypothesis → investigate |
| 2 | **Coordinate consistency / scale validation** (`transform_box_to_canonical` w/h, mpp validation) | Hypothesis → investigate |
| 3 | **CD-C zero-furniture scale** (`mpp=0.01` fallback; empty vs furnished differ) | Contract-level decision (calibration) |
| 4 | **DEF-2 whole-band-measured fallback** (effectively unreachable) + DEF-2 test gaps | Known limitation |
| 5 | **Opening-to-floor ownership** global (openings carve by geometry, floors per-room) | Known limitation (low) |
| 6 | **Scene/version binding race** (`/scene` build vs latest-version lookup) | Hypothesis → investigate |
| 7 | **Diagonal/curved walls** unsupported (axis-aligned extraction) | Known limitation |
| ops | Harness cleanup · port 5173 | Environment/ops |
| resolved | **Supabase** | Environment (now UP) |

## 10. Next recommended action
**Ready for commit approval**, with one gate: **run a clean full backend suite now that the DB is warm** (to convert the overnight flaky 5/86 into a clean result) — then commit per §7. In parallel, **live validation is now possible** (DB up): start the app and run the §8 checklist. After commit, the highest-value next engineering item is the **wall-ID identity** investigation (rank 1), then coordinate consistency; CD-C/scale remains a calibration decision. No confirmed review defect blocks commit.

*Review only. No code, tests, reports, harnesses, DB, or Git state were modified.*
