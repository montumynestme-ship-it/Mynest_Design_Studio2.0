# Phase 1 — Additive 2D Architectural View: Implementation Report

**Scope:** additive, frontend-only architectural overlay rendering existing `/scene` data (walls, room boundaries + labels, door/window opening placements) with verified-vs-uncertain distinction, working with zero furniture. No canonical, schema, backend, coordinate-calibration, or 3D changes.
**Branch:** `feature/phase-1-empty-architectural-plans` · **Date:** 2026-11-14
**Evidence classes:** `VERIFIED` · `AGENT-REPORTED` · `INFERRED` · `UNKNOWN` · `NOT_ASSESSABLE`

---

## 1. Git baseline, branch, commit `VERIFIED`
- Root `D:\Latest_mynest_design_version\mynest-design-studio`; branch `feature/phase-1-empty-architectural-plans`.
- Baseline `d1d65f7` is an ancestor (`git merge-base --is-ancestor d1d65f7 HEAD` → true).
- Inspection report preserved and committed separately as `5660f42` *"docs: Phase 1 empty-architecture read-only inspection report"* before any code change.
- No reset/clean/stash; Phase A, `vite.config.ts`, the furniture audit, and earlier harness are untouched.

## 2. Files inspected `VERIFIED`
`frontend/src/lib/scene.ts` (Scene/SceneRoom/OpeningPlacement, `fetchScene`), `components/design-studio/DesignCanvas.tsx`, `RoomScene3D.tsx`, `pages/DesignStudio.tsx`, backend `scene_service.py` (opening_placements/verified contract), and existing frontend tests (`src/lib/*.test.ts`, vitest).

## 3. Root cause of the missing architectural view `VERIFIED`
The editor 2D canvas renders only the **rasterized PDF image + furniture overlay** (`DesignCanvas.tsx`). The extracted vector architecture (walls, room `boundary`, `opening_placements`) was consumed **only by the 3D renderer** and the backend control raster — there was **no 2D vector presentation** of it. The data already existed on `/scene`; the view did not. This implementation adds that presentation, additively.

## 4. Files changed and why `VERIFIED`
| File | Change | Why |
|---|---|---|
| `frontend/src/lib/architecturalView.ts` (new) | Pure `buildArchitecturalView(scene)` → `{available, walls, rooms, openings}` | Testable data transform; selects/classifies existing world-px values, never edits geometry |
| `frontend/src/lib/architecturalView.test.ts` (new) | 13 vitest cases | Covers §6 requirements against the real transform |
| `frontend/src/components/design-studio/ArchitecturalLayer.tsx` (new) | Non-interactive Konva `<Layer listening={false}>` | Draws walls/rooms/openings in world px inside the Stage transform |
| `frontend/src/components/design-studio/DesignCanvas.tsx` (+16) | Additive `architecture` prop + render overlay above furniture | Overlay on; default (null) keeps existing view and furniture editing byte-identical |
| `frontend/src/pages/DesignStudio.tsx` (+79/-3) | `Architecture` toggle, scene fetch effect, memoized view, honest empty/error hint | Switch PDF↔architectural view without losing workflow |
| `frontend/src/dev/architecturalHarness.tsx` + `architectural-harness.html` (new, **throwaway**) | Synthetic visual proof (backend down) | Not imported by the app; remove after review |

## 5. Implemented architectural view `VERIFIED`
A toolbar **“Architecture”** toggle (ghost→primary) overlays, over the existing plan, a read-only layer that draws:
- **Walls** — each extracted face stroke as its own line (near-black), **never merged/snapped**; preserves double-line pairs.
- **Rooms** — boundary polygons; **CONFIRMED** (wall-proven) solid blue + blue label; **UNCERTAIN** furniture-hull fallback dashed amber + “(uncertain)” label — fallback is **not** shown as a confirmed room. Labels only when a valid label exists.
- **Doors** — rotated rects; **verified** solid green; **unverified** dashed amber (needs review). Width/orientation/wall-relationship preserved; nothing teleported; no swing invented.
- **Windows** — rotated rects; **verified** solid blue; **unverified** dashed amber. No invented sill/dimensions.
- **Empty-plan** — renders purely from scene walls/rooms/openings; furniture array is irrelevant (demonstrated with zero furniture).
- **Honest states** — loading / backend-unavailable / no-architecture hints when the scene can’t be shown.

The overlay layer is `listening={false}`, so selection/drag/rotate fall through to furniture unchanged; the default view (toggle off) is unchanged.

## 6. Coordinate transformation used + evidence `VERIFIED`
- Scene `walls`, room `boundary`, and `opening_placements.cx/cy/w/h` are **world px** = `pdf_pt × WORLD_SCALE(2.0)` (`geometry_extraction_service.py:25`). The plan image is rasterized at the same scale (`loadPlanImage`), so plan-image dims == scene page dims == world px.
- The overlay draws at **raw world-px coordinates inside the existing Stage** (`x=offsetX, y=offsetY, scaleX/Y=scale`), so pan/zoom map world→screen identically to the plan image → **alignment is automatic with no new scale**.
- **No** `DEFAULT_MPP=0.01`, frontend `SCALE=0.15`, or 3D mpp is used anywhere in the view; stroke widths/font sizes are divided by the Stage `scale` only to keep constant on-screen size. **No physical-mm claim is made.**

## 7. Verified vs uncertain display `VERIFIED`
Carried faithfully from the data: room `validation_status === 'CONFIRMED' && geometry_source startsWith 'architectural'` → confirmed styling; `opening_placements[].verified` → solid (verified) vs dashed amber (needs review). See the delivered screenshot: Bedroom (CONFIRMED/blue) vs Store (UNCERTAIN/amber); verified door (green) + window (blue) vs unverified window (amber dashed).

## 8. Test commands & results `VERIFIED`
```
cd frontend && npx tsc --noEmit            # → exit 0
cd frontend && npx vitest run src/lib      # → 6 files, 75 passed (13 new architecturalView + 62 existing); 0 failures, 0 regressions
```
The new tests exercise the **real** `buildArchitecturalView` transform (coords preserved, no fabricated wall connections, concave polygons unchanged, incomplete boundary not closed, verified/uncertain openings distinguished, multiple openings keep positions, zero furniture renders, empty state honest, purity). Konva draw primitives are thin and driven entirely by this tested data.

## 9. Before/after screenshots `AGENT-REPORTED` / `NOT_ASSESSABLE` (live)
The **live app** cannot fetch a real scene right now — the **backend is down** (Supabase “tenant not found”), so `GET /scene` fails and the view shows its honest “backend may be offline” state. A **synthetic-data visual proof** driving the real `ArchitecturalLayer` + `buildArchitecturalView` was captured instead (delivered image): `available=true · walls=9 · rooms=2 · openings=3`, all distinctions rendering correctly. Live before/after on a real plan is `NOT_ASSESSABLE` until Supabase is restored.

## 10. Existing behavior & regression assessment `VERIFIED`
- Toggle **off** (default): `architecture=null` → overlay not rendered; DesignCanvas/furniture path byte-identical.
- Overlay layer is non-interactive → furniture selection/drag/rotate, Draw Area, zoom/pan unchanged.
- No existing test changed or weakened; 62 prior lib tests still pass. `tsc` clean.

## 11. Known limitations `VERIFIED`
- **Live evidence blocked** by the down backend (above).
- **Angled walls** are not extracted upstream (axis-aligned only) — out of Phase-1 scope; the overlay faithfully draws whatever walls the scene contains.
- **No physical-mm** is shown (uncalibrated scale, by design).
- Room label placement is a simple vertex-average anchor (may sit off-centre on strongly concave polygons) — cosmetic.
- Overlay draws **above** furniture; in architectural view furniture may be visually under the overlay (intended; editing still works).

## 12. Git diff summary `VERIFIED`
```
 frontend/src/components/design-studio/DesignCanvas.tsx | 16 ++++-
 frontend/src/pages/DesignStudio.tsx                    | 79 +++++++++++++++++++++-
 (new) frontend/src/lib/architecturalView.ts
 (new) frontend/src/lib/architecturalView.test.ts
 (new) frontend/src/components/design-studio/ArchitecturalLayer.tsx
 (new, throwaway) frontend/src/dev/architecturalHarness.tsx
 (new, throwaway) frontend/architectural-harness.html
```

## 13. Git status `VERIFIED`
Branch `feature/phase-1-empty-architectural-plans`; 2 modified + 5 untracked (3 real + 2 throwaway harness) files uncommitted. Baseline `d1d65f7` and inspection commit `5660f42` intact. Nothing staged; no canonical/schema/backend change.

## 14. Remaining Phase 1 completion gaps `VERIFIED`
Against the completion gate:
- Wall connectivity / room topology validation — **supported by the data** (CONFIRMED only when wall-proven); the view surfaces it. ✅
- Door/window evidence & uncertainty **preserved and displayed**. ✅
- **Empty architectural plan renders without furniture.** ✅ (synthetic proof; live pending backend)
- **Canonical geometry unchanged.** ✅
- **Live on-a-real-plan verification** remains **open** until Supabase is restored — the one gap to close for full sign-off.

---

*Additive frontend presentation only. No canonical geometry, furniture transforms, schemas, backend, or 3D behavior changed. The throwaway harness (`src/dev/architecturalHarness.tsx`, `architectural-harness.html`) should be removed before a clean commit.*
