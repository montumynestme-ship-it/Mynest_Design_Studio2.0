# DEF-3 (slice) — Full-Plan 3D Assembly from Architecture

**Date:** 2026-11-14 · **Branch:** `feature/phase-1-empty-architectural-plans`
**Scope:** the authorized **small slice** of DEF-3 — render the full-plan combined scene from architecture, with zero furniture, framing the full wall extent, openings aggregated. Frontend-only; no backend/API/schema/canonical change; no commits.
**Evidence classes:** `VERIFIED` · `INFERRED` · `NOT_ASSESSABLE`

---

## Root cause (confirmed) `VERIFIED`
`Scene3DModal.tsx` built the full-plan `combined` room from **furniture**: it returned `null` when `furniture.length === 0`, derived the bbox from furniture extents, and passed **no** `boundary`/`opening_placements`. So an empty plan showed nothing, walls outside the furniture bbox were cropped, and doors/windows did not render in the combined view.

## What changed (slice) `VERIFIED`
| File | Change |
|---|---|
| `frontend/src/lib/combinedScene.ts` (new) | Pure `buildCombinedRoom(scene)`: extent from **wall endpoints + room-boundary vertices + furniture** (page-bounds fallback, else null); renders with **zero furniture** (no early null); aggregates **every room's `opening_placements`**; furniture passed through **unchanged**. |
| `frontend/src/lib/combinedScene.test.ts` (new) | 9 unit tests (below). |
| `frontend/src/components/design-studio/Scene3DModal.tsx` | Replaced the inline furniture-derived memo with `buildCombinedRoom(scene)` — **net −5 lines** (`+7/−12`). |

**Deliberately NOT in this slice (larger follow-on):** preserving each room's own `boundary` polygon / polygon floor and per-room opening-to-floor association inside the single combined room. `RoomScene3D` renders one room with one boundary, so the combined room still carries **no** `boundary` (rectangular-floor fallback). This is called out as the next DEF-3 step.

## Requirements coverage (§10)
| # | Requirement | Status |
|---|---|---|
| 1 | Renders with zero furniture | ✅ `VERIFIED` (no `null` on empty furniture; harness renders) |
| 2 | Architecture (not furniture) determines extent | ✅ `VERIFIED` (bbox from walls/boundaries + furniture) |
| 3 | Room boundaries preserved | ⏭️ follow-on (single-room model) — honest rectangular floor for now |
| 4 | Walls outside furniture bounds visible | ✅ `VERIFIED` (test: bbox reaches wall extent) |
| 5 | Verified doors/windows preserved | ✅ `VERIFIED` (opening_placements aggregated; harness window carves) |
| 6 | Furniture from the selected version | ✅ `VERIFIED` (passed through unchanged, not inferred) |
| 7 | Furniture not inferred from architecture | ✅ `VERIFIED` (test: furniture === input) |
| 8 | Existing per-room render unchanged | ✅ `VERIFIED` (`BaseRenderBatch` uses `room={room}`, untouched) |
| 9 | Camera works for empty plans | ✅ `INFERRED` (RoomScene3D frames from bbox; furniturePts empty → room-box framing; harness confirms) |
| 10 | Missing geometry honest, not fabricated | ✅ `VERIFIED` (no boundary invented; null only when truly empty) |

## Evidence
- `npx tsc --noEmit` → **0**; `npx vitest run src/lib` → **93 passed** (9 new `combinedScene` + 84 existing, no regressions).
- Tests assert: null scene → null; **zero-furniture + walls → non-null, bbox spans walls**; walls outside furniture bbox included; furniture passed through exactly (identity/transforms, aggregated across rooms, nothing added); opening_placements aggregated; page-bounds fallback; true-empty → null; no boundary (follow-on) + stable id; purity.
- **Visual (delivered):** real `buildCombinedRoom` → `RoomScene3D` on a synthetic **zero-furniture** scene: `bbox=[100,100,600,300]` from the walls, `furniture=0`, `openings=1` — the full house renders with the **shared partition** and a **carved window**, no furniture. Previously this returned `null`/blank.

## Regression safety `VERIFIED`
- The change is confined to the **combined full-plan preview** (`Scene3DModal`). **Per-room base renders** (`BaseRenderBatch`, `room={room}`) are untouched → **no AI base-render regression risk**.
- `buildCombinedRoom` is pure and null-safe; `Scene3DModal`'s `ready`/`!combined` fallbacks still fire only for genuinely empty scenes.

## Limitations / risks
- **Scale with zero furniture:** `mpp = computeMpp(scene.rooms)` falls back to `0.01` when no bed exists (CD-C, blocked on calibration) — an empty plan renders at a different metric scale than a furnished one. Out of this slice.
- **Per-room boundaries/floors** not preserved in the combined view (follow-on).
- **Live real-plan verification `NOT_ASSESSABLE`** — Supabase down, so the real `Scene3DModal` `/scene` flow wasn't exercised; evidence is unit tests + the synthetic harness, not a production claim.

## Git status `VERIFIED`
Modified: `Scene3DModal.tsx` (`+7/−12`). New (untracked): `combinedScene.ts`, `combinedScene.test.ts`, `combined-scene-harness.html`, `dev/combinedSceneHarness.tsx`. No backend/canonical/API/schema change. Nothing committed.

---

### Bottom line
The full-plan dollhouse now assembles from the **architecture**: it renders with **zero furniture**, frames the **full wall extent** (not the furniture bbox), and shows **aggregated door/window openings** — proven by 9 unit tests and a zero-furniture render. The remaining DEF-3 work (per-room boundary/floor preservation, which needs `RoomScene3D` to handle multiple room boundaries) is scoped as the next step.

*Frontend-only slice. Canonical 2D geometry and furniture remain authoritative and untouched.*
