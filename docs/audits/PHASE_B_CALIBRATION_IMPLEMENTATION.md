# Phase B — Backend Metric Calibration: Implementation

**Date:** 2026-11-15 · **Branch:** `feature/phase-1-empty-architectural-plans` · **HEAD:** `f279932` (nothing committed)
**Scope:** approved minimal, additive calibration workflow. **No schema migration; no API contract removed/changed; no canonical geometry touched; no AI render; no commit/push/deploy.** Evidence: `VERIFIED`.

---

## 1. Changed files (minimal) `VERIFIED`
**Backend (modified, additive):**
- `app/services/coordinates.py` — define + convert the calibration unit: `scale_mm_per_px_from_measurement`, `pixel_distance`, `mpp_from_scale_mm_per_px` (+ a doc block defining the field as **mm per WORLD px**).
- `app/services/floor_plan_service.py` — `get_floor_plan_scale` / `set_floor_plan_scale` (reuse `_get_or_404` / `session_scope`).
- `app/schemas/floor_plan.py` — `CalibrationRequest` / `CalibrationResponse`.
- `app/api/floor_plans.py` — `GET` + `PUT /{file_id}/calibration` (additive routes).
- `app/services/scene_service.py` — expose `scale_mm_per_px` / `mpp` / `scale_calibrated` / `scale_source` in `build_scene` (additive).
- `tests/test_calibration.py` (new) — 23 tests.

**Frontend (modified/new, additive):**
- `src/lib/scene.ts` — `Scene` scale fields + `putCalibration()` API helper.
- `src/components/design-studio/Scene3DModal.tsx` — consume the stored scale (via `calibrateScale` `storedMpp`), "Calibrate scale" toggle, honest label.
- `src/components/design-studio/CalibrationOverlay.tsx` (new) — two-point pick on the 2D plan → preview → save.
- `src/lib/putCalibration.test.ts` (new) — 4 tests.

## 2. Calibration architecture & coordinate units `VERIFIED`
- **Definition (ambiguity resolved):** `scale_mm_per_px` = **millimetres per CANONICAL WORLD pixel** (world = pdf_pt × 2.0) — the frame walls/rooms/openings and the 2D calibration canvas share. The renderer's `mpp` (metres per world px) = `scale_mm_per_px / 1000`.
- **User flow:** the designer clicks two points on the 2D plan (RoomSection2D's SVG viewBox IS world px → clicks map to world px via the SVG CTM), types the known real distance in mm, previews `mm/px` + `m/px`, and saves. The backend computes `known_distance_mm / |p2 − p1|` and persists it.
- **Provenance/confidence:** present ⇒ `source: 'user_measurement'`; the frontend `calibrateScale` ranks a saved scale (`high`) above the furniture proxy (`medium`) above the uncalibrated fallback (`none`). Conflict handling (median, flagged, never silent-averaged) already exists for multi-measurement input.
- **Uncalibrated fallback preserved:** NULL scale → `calibrated:false`, relative proportions, honest "scale: uncalibrated" label — no invented metric dimension.
- **Wall height untouched:** still the 2.7 m default (never claimed as measured); horizontal scale is kept separate.

## 3. API / DB compatibility `VERIFIED`
- **No schema migration:** `floor_plans.scale_mm_per_px` already exists in the live DB (provisioned by `create_all`). Only its value is set.
- **Additive API:** two new routes; `GET /scene` gains fields. `FloorPlanResponse` unchanged. Legacy clients/plans unaffected (NULL → uncalibrated).
- **Safety:** `set_floor_plan_scale` validates a positive/finite factor, refuses to overwrite an existing calibration without `overwrite=true` (409), and preserves the prior value on any failure.
- **No `calibration_meta`:** scalar-only provenance uses the existing column; richer provenance/multi-measurement persistence would need a new JSONB column — **not done, flagged for separate approval.**

## 4. Tests & results `VERIFIED`
- **Backend:** `pytest tests/test_calibration.py -q` → **23 passed** (coordinates math incl. zero/negative/non-finite rejection + round-trip; persistence logic via monkeypatched session: set/read/overwrite-guard/invalid-preserves-previous; API 422 validation branches). `ruff` on changed code: clean (the repo's 17 pre-existing E501/F401/I001 are unrelated). `mypy` on the new pure modules: clean (`coordinates.py`, `schemas` → "no issues"; the repo-wide mypy is pre-existingly blocked by a numpy-stub/py-version mismatch, unrelated).
- **Frontend:** `tsc --noEmit` → 0; `vitest run src/lib` → **128 passed / 11 files** (+4 `putCalibration`); `eslint` changed files → 0; `npm run build` → ✓ (27.8 s).

## 5. Real-plan validation — `f6b65d2b` `VERIFIED` (reversible, DB restored)
End-to-end via the service, then **reset to NULL** (DB left exactly as found):

| Step | Result |
|---|---|
| 1. Before | `scale_mm_per_px: None`, scene `scale_calibrated:false`; geometry (walls, rooms, openings) = **(179, 5, 13)** |
| 2. Set `6.0` mm/world-px | persisted → `mpp 0.006`, `calibrated:true`, `source: user_measurement` |
| 3. After | scene now `scale_mm_per_px:6.0, mpp:0.006, scale_calibrated:true`; geometry **(179, 5, 13) — UNCHANGED** |
| 4. Overwrite guard | `set 8.0` without `overwrite` → **409** (prior value kept) |
| 5. Reset | `scale_mm_per_px` → **NULL**; scene back to uncalibrated; geometry identical |

**UI (production build, live backend):** the "Calibrate scale" button renders in the 3D modal; clicking it opens the two-point overlay — *"Click the first point of a known distance on the plan."*, a *Known distance [ ] mm* input, and *Save / Reset / Cancel*; the footer label reflects calibrated vs *"scale: uncalibrated (relative proportions)"*. Verified via DOM read + screenshot.

## 6. Before/after
- **Before:** scale dormant/unreadable; empty plan rendered with the uncalibrated 0.01 fallback, silently.
- **After:** designers can set a real metric scale from a measured distance; it persists, flows into `/scene` and the renderer, and is labelled honestly; absent calibration still falls back to the honest uncalibrated state. Geometry is byte-for-byte unchanged in both states.

## 7. Kitchen & room completeness `VERIFIED`/`NOT_ASSESSABLE`
Empty-plan rooms render completely (5/5, incl. 1 concave). Room **naming** comes from OCR text / furniture tags; the empty plan has neither, so rooms are generic "Room N" and a specific "Kitchen" name is `NOT_ASSESSABLE` here. (The real design's v76+ canonical carries a CONFIRMED "Kitchen & Dining Area" via tags — see `conftest` `frozen_v84`.)

## 8. Limitations & risks
- **Scalar-only provenance** (no multi-measurement/conflict history persisted) — a `calibration_meta` JSONB column is proposed separately.
- **Metric accuracy depends on the designer's measurement**; a bad pick yields a bad scale (mitigated by preview + overwrite-guard). The system still never fabricates a scale on its own.
- Repo-wide `mypy`/`ruff` have pre-existing issues unrelated to this change.
- Calibration writes mutate the shared DB (by explicit user action only).

## 9. Git status & confirmation `VERIFIED`
`git status`: 7 modified (5 backend, 2 frontend — all additive) + new `test_calibration.py`, `calibration.ts(+test)`, `CalibrationOverlay.tsx`, `putCalibration.test.ts`, and reports; prior untracked work + 6 harnesses preserved. `HEAD` unchanged (`f279932`). **No schema migration, no removed/changed API contract, no canonical/furniture change, no AI render, no commit/push/deploy.** The `f6b65d2b` DB row was calibrated for the reversible test and **restored to NULL**.

---

### Bottom line
A minimal, additive, backward-compatible calibration workflow now lets a designer set a trustworthy **mm-per-world-px** scale from a measured distance — persisted in the pre-existing `scale_mm_per_px` column, surfaced in `/scene`, consumed by the renderer, and labelled honestly — while the uncalibrated fallback and all canonical geometry are untouched. 23 backend + 128 frontend tests green; real-plan end-to-end verified and the DB restored; nothing committed.
