# DEF-3 (follow-on) — Per-Room Polygon Floors in the Combined View

**Date:** 2026-11-14 · **Branch:** `feature/phase-1-empty-architectural-plans`
**Scope:** the remaining DEF-3 piece — preserve each **architectural** room's floor polygon in the full-plan combined scene (instead of one rectangular fallback floor). Frontend-only; no backend/API/schema/canonical change; no commits.
**Evidence classes:** `VERIFIED` · `INFERRED` · `NOT_ASSESSABLE`

---

## What changed `VERIFIED`
| File | Change |
|---|---|
| `frontend/src/lib/combinedScene.ts` | New pure `collectRoomFloors(scene)` → the world-px boundary polygons of **only** wall-proven **architectural** rooms (a furniture-hull / UNCERTAIN fallback room is excluded). Copies vertices; never mutates. |
| `frontend/src/lib/combinedScene.test.ts` | +5 tests for `collectRoomFloors`. |
| `frontend/src/components/design-studio/RoomScene3D.tsx` | New optional prop `roomFloors?: Array<Array<[number,number]>>`; a memoised `extraFloorShapes` (one `THREE.Shape` per polygon, same world→metre mapping and wood material as the single-room floor); the floor render now does `floorShape → per-room polygon floors → rectangular fallback`. |
| `frontend/src/components/design-studio/Scene3DModal.tsx` | Passes `roomFloors={collectRoomFloors(scene)}` to the combined `RoomScene3D`. |

**Additive & gated:** `roomFloors` defaults to `[]`; when empty (every single-room render, incl. `BaseRenderBatch`) behaviour is **byte-identical** — `floorShape` (the room's own boundary) still wins, else the rectangular fallback. The per-room branch runs only for the combined view (no single `floorShape`, `roomFloors` supplied).

## Requirement coverage (completes DEF-3 §10.3)
- **Room boundaries preserved in the combined view:** ✅ each architectural room renders its own polygon floor.
- **Honest, not fabricated (§10.10):** ✅ a **fallback/UNCERTAIN** room gets **no** polygon floor (never a confirmed floor for unproven geometry) — verified visually (right room = open void).
- **Per-room render unchanged:** ✅ `BaseRenderBatch` passes no `roomFloors`; single-room floor path untouched.

## Evidence
- `npx tsc --noEmit` → **0**; `npx vitest run src/lib` → **98 passed** (5 new `collectRoomFloors` + 93 prior, no regressions).
- `collectRoomFloors` tests: architectural room → included (vertices copied); fallback room → excluded; missing/too-short boundary → excluded; multiple architectural rooms → all (and only those).
- **Visual (delivered):** real `collectRoomFloors` → `RoomScene3D` on a zero-furniture scene with a `left` **architectural** room and a `right` **fallback** room: `roomFloors=1`; the left room shows a real wood **polygon floor**, the right room shows **no floor** (honestly excluded); walls + carved window + zero furniture intact.

## Limitations / risks `VERIFIED` / `NOT_ASSESSABLE`
- **Single-material floors:** all room floors use the same wood material; adjacent rooms read as continuous (acceptable). Per-room floor height is the shared ground plane (no level changes).
- **Opening→floor association** is still global (openings carve walls via position, not per-room) — unchanged; openings already render correctly.
- **Scale** with zero furniture still falls back to `mpp=0.01` (blocked CD-C) — out of scope.
- **Live real-plan verification `NOT_ASSESSABLE`** — Supabase down; evidence is unit tests + synthetic harness, not a production claim.

## Git status `VERIFIED`
Modified (cumulative with DEF-1/slice): `RoomScene3D.tsx`, `Scene3DModal.tsx`. New (untracked): `combinedScene.ts(+test)`, `combined-scene-harness.html`, `dev/combinedSceneHarness.tsx`. No backend/canonical/API/schema change; nothing committed.

---

### Bottom line
DEF-3 is now complete: the full-plan dollhouse assembles from architecture (slice) **and** renders each wall-proven room's **own polygon floor**, while **honestly omitting** floors for unproven (fallback) rooms. Pure `collectRoomFloors` + 5 tests, additive `roomFloors` prop (single-room renders unchanged); tsc 0, vitest 98, visual confirmed.

*Frontend-only. Canonical 2D geometry and furniture remain authoritative and untouched.*
