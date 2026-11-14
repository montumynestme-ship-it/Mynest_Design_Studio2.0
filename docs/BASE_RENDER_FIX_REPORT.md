# Base-Render DPR Bug — Fix Report

**Date:** 2026-10-03
**Blocker:** HIGH — base-render dimension mismatch on HiDPI displays (the single verified blocker from `PIPELINE_AUDIT_REPORT.md`).
**Final status:** `ROOT_CAUSE_FIXED`

---

## Exact root cause
`RoomScene3D.tsx` rendered the capture Canvas with `<Canvas dpr={[1, 2]}>`. react-three-fiber maps the `dpr` prop to `WebGLRenderer.setPixelRatio(...)`, so on a HiDPI display (`devicePixelRatio = 2`) the renderer pixel ratio became 2. The capture viewport is 1216×832 **CSS** px, and the WebGL backing store = `round(cssSize × pixelRatio)` = **2432×1664**. `canvas.toDataURL()` reads the backing store, so the captured PNG was **2432×1664**, while `base_render_meta` declared the CSS constants **1216×832**. The Handoff #12 backend contract then correctly rejected the capture as `BASE_RENDER_WRONG_SIZE`, blocking every base render (and thus all AI generation) on HiDPI displays.

The contract was correct; the capture produced the wrong pixel dimensions. The fix makes the capture deterministic at pixel ratio 1 so the PNG equals the declared size on every display.

## Files changed (exactly 3 production files + 1 test)
1. **`frontend/src/components/design-studio/RoomScene3D.tsx`**
   - Added an optional prop `dpr?: number | [number, number]` (default `[1, 2]`).
   - `<Canvas dpr={[1, 2]}>` → `<Canvas dpr={dpr}>`.
   - **Interactive 3D preview behavior is unchanged** (still defaults to `[1, 2]`).
2. **`frontend/src/components/design-studio/BaseRenderBatch.tsx`**
   - The capture Canvas now passes `dpr={1}` (only the base-render capture path).
3. **`backend` — no production change.** The Handoff #12 validation (`base_render_service.validate_base_render`, `BASE_RENDER_WRONG_SIZE`) is **unchanged**, as required.
4. **`backend/tests/test_handoff12_base_render_binding.py`** — added two regression tests (below).

**Not touched:** fal.ai integration, NVIDIA, PDF extraction, canonical ownership, 2D→3D geometry, backend expected dimensions, capture metadata values (still 1216×832). No PNG was divided by 2; no validation weakened.

## Before / after dimensions
| | renderer pixel ratio | canvas backing | PNG | base_render_meta | contract |
|---|---|---|---|---|---|
| **Before (dpr=[1,2]) @ devicePixelRatio=2** | 2 | 2432×1664 | 2432×1664 | 1216×832 | `BASE_RENDER_WRONG_SIZE` (reject) |
| **After (dpr=1) @ devicePixelRatio=2** | 1 | 1216×832 | 1216×832 | 1216×832 | PASS |
| **After (dpr=1) @ devicePixelRatio=1** | 1 | 1216×832 | 1216×832 | 1216×832 | PASS |

## Runtime evidence (real browser, not only unit tests)

### Lever proof — real browser at `devicePixelRatio=2` (three.js `setPixelRatio`, which R3F `dpr` sets)
```
FIX capture dpr=1  : renderer_pixel_ratio=1, css[1216,832], canvas_backing[1216,832], png[1216,832], matches_meta=true
OLD BUG capture dpr=2: renderer_pixel_ratio=2, css[1216,832], canvas_backing[2432,1664], png[2432,1664], matches_meta=false
```

### Real-app proof — production BaseRenderBatch + RoomScene3D, live app at `devicePixelRatio=2`, fal NOT called (`/generate` intercepted client-side)
Plan: `mathur.pdf` (`design_version_id=0754745a-a58e-4b62-be9d-401c0945ffdb`). Six `base_renders` (each furnished room keyed by stable id AND display label):

| room_key | PNG | base_render_meta | design_version_id | match |
|---|---|---|---|---|
| room-1 / **Room 1** | 1216×832 | 1216×832 | 0754745a… | ✅ |
| bedroom-1 / **Bedroom 1** | 1216×832 | 1216×832 | 0754745a… | ✅ |
| dining-area / **Dining Area** | 1216×832 | 1216×832 | 0754745a… | ✅ |

`[AI BASE CAPTURE]` logs (`canvas.width/height`) for every room — Room 1, Room 2, Bedroom 1, Room 4, Room 5, Dining Area — all **1216×832**, `capture_exists=true`, `attempts=1`.

- **DPR=1 evidence:** harness `FIX capture dpr=1` → PNG 1216×832 (above).
- **DPR=2 evidence:** real app at `devicePixelRatio=2` → every capture PNG 1216×832 (table above).
- **Living Area / Kitchen / Bedroom evidence:** this plan's furnished rooms are **Room 1** (dining-table), **Bedroom 1** (bed), **Dining Area** (loungers-sofa) — all captured at 1216×832. Capture dimensions are room-content-independent (fixed by capture CSS × renderer pixel ratio), so the result generalizes to Living Area/Kitchen/Bedroom 2; the empty Room 2/4/5 also logged 1216×832.
- **Metadata binding:** every captured room carries `design_version_id=0754745a…` + width/height 1216×832 (Handoff #12 `/scene`→meta flow verified live).

## Backend validation result (Handoff #12 contract, unchanged)
- A real 1216×832 capture is **accepted** by `base_render_service.validate_base_render` (`test_dpr1_capture_1216x832_accepted_by_contract`).
- The old 2432×1664 capture against 1216×832 meta is **still rejected** `BASE_RENDER_WRONG_SIZE` (`test_hidpi_dpr2_capture_2432x1664_still_rejected`) — validation not weakened.
- Since the real app now produces exactly 1216×832 (proven above) and the contract accepts 1216×832 (proven), the real capture passes the contract. `fal.ai was not called` in this verification.

## Tests executed
- `backend/tests/test_handoff12_base_render_binding.py` → **9 passed** (7 existing + 2 new DPR regression).
- New regression tests:
  - `test_dpr1_capture_1216x832_accepted_by_contract` — 1216×832 + meta 1216×832 → accepted.
  - `test_hidpi_dpr2_capture_2432x1664_still_rejected` — 2432×1664 + meta 1216×832 → `BASE_RENDER_WRONG_SIZE` (negative test preserved).
- Full backend suite earlier this session: 476 passed / 2 pre-existing `reportlab` failures (unrelated).

## Build / typecheck result
- `npm run type-check` (`tsc --noEmit`) → exit 0.
- `npm run build` (`tsc && vite build`) → exit 0 (24.4s).

## Downstream confirmation
1. Base-render validation **accepts** the real captured PNG (1216×832). ✅
2. `BASE_RENDER_WRONG_SIZE` **does not** occur for the real capture. ✅
3. The valid base render reaches the pre-FAL boundary (contract passes → would proceed to fal). ✅
4. **fal.ai was not called** during this regression. ✅
5. Interactive 3D preview DPR behavior unchanged (`dpr` defaults to `[1, 2]`). ✅

## Next step (not done here — requires explicit go-ahead)
Run exactly one real fal.ai generation to confirm the full path end-to-end. (Note: the fal account is currently `403 TOP_UP`-locked per prior findings, which would surface as a provider billing error, not a code failure.)

---

### FINAL STATUS: `ROOT_CAUSE_FIXED`
Verified by executable backend tests, a passing typecheck/production build, a real-browser lever proof at `devicePixelRatio=2`, and a real-app capture of the production pipeline at `devicePixelRatio=2` producing 1216×832 PNGs bound to the correct `design_version_id` — with the Handoff #12 validation left unchanged.
