# MyNest Design Studio — Full Pipeline Audit

**Date:** 2026-10-03
**Scope:** PDF upload → architecture extraction → canonical → manual 2D editor → immutable design version → deterministic 3D → camera → base render → pre-FAL validation → fal.ai → output → post-AI validation → save/reject.
**Mode:** Read-only audit. No production code modified. No live fal.ai request made.

## Executable evidence base
- **Full backend suite:** `backend/.venv/Scripts/python.exe -m pytest tests/` → **476 passed, 2 failed** (both `test_invoice_upload.py`, pre-existing `ModuleNotFoundError: reportlab`; unrelated to this pipeline), 0 errors, 0 skipped. Run 2026-10-03, 7m06s.
- **Frontend typecheck:** `npm run type-check` (`tsc --noEmit`) → exit 0.
- **Frontend build:** `npm run build` (`tsc && vite build`) → exit 0.
- **Provider config (effective runtime, from `.env`):** `DEFAULT_AI_PROVIDER=fal`, `FAL_API_BASE=https://fal.run`, `FAL_IMAGE_MODEL=fal-ai/flux-kontext/dev`. NVIDIA registered but not the active default. ✅ (business rule #7)

---

## Stage-by-stage

### 1. PDF upload → backend — **PASS**
- **Files/functions:** `app/api/floor_plans.py::upload_floor_plan` → `floor_plan_service.create_floor_plan` → `_validate_file`.
- **Evidence:** `tests/test_floor_plans.py` (201 + ext/mime/size validation). Rejects with `FloorPlanError` 413/415; deletes file on DB failure.
- **Root cause / impact:** none. **Tests:** existing cover it.

### 2. PDF → architecture extraction (vector/raster/OCR/dimensions/walls/rooms/doors/windows) — **PASS**
- **Files/functions:** `geometry_extraction_service.extract_walls` + `_extract_openings` (gold=door, cyan=window, status VALID/UNCERTAIN/INVALID); `architectural_service.build_structured_walls` / `extract_doors_and_windows` / `reconstruct_rooms`; `shape_extraction_service`, `room_reconstruction_raster`, `wall_reconstruction`.
- **Evidence:** `tests/test_geometry_extraction.py`, `tests/test_door_window_merge.py`, `tests/test_opening_placement.py`; live on fixture FID: 179 walls / 8 doors / 5 windows / 8 rooms. Deterministic; extraction failure → `walls=[]` (furniture still renders), never fabricated geometry.
- **Business impact:** none. **Tests:** existing cover it.

### 3. Canonical architecture (architecture only, no invented furniture) — **PASS**
- **Files/functions:** `floor_plan_service.get_canonical` (returns `{"furniture":[…]}` only); architecture re-derived by `scene_service.build_scene` from the immutable PDF; `canonical_assembly_service.assemble` (diagnostic full doc, not the stored version).
- **Evidence:** live inspection — `canonical` top-level keys = `['furniture']`; architecture is NOT stored in the design version. `tests/test_canonical_assembly.py`, `tests/test_furniture_inventory_preservation.py`.
- **Business impact:** none. Correctly separates architecture (PDF-derived, rule #1) from furniture (user-authored, rule #2).

### 4. Manual furniture editor (add/move/rotate/resize/delete) & ownership — **PASS**
- **Files/functions:** FE `pages/DesignStudio.tsx` (`handlePlace`, `patchPlaced`, delete handler, debounced autosave) → `PUT /layout` → `floor_plan_service.save_layout`. Detection: `floor_plan_service.detect_furniture` is diagnostic — `applied_to_canonical=False` always.
- **Evidence:** `tests/test_furniture_ownership_boundary.py` (8): empty→zero furniture; add/move/rotate/resize/delete; extraction does not overwrite; `test_detection_cannot_inject_furniture_into_canonical` (YOLO/VLM/OCR can never write canonical — rules #2/#3).
- **Business impact:** none.

### 5. Immutable design version (freezes exact layout) — **PASS**
- **Files/functions:** `save_layout` (append-only `DesignVersion`, dedup via `_furniture_fingerprint`); `capture_generation_snapshot` (freezes version, deep-copies canonical); `generation_service.generate` binds to the captured `design_version_id`.
- **Evidence:** `tests/test_generation_snapshot_safety.py` (edit-during-gen, move→new version, delete, A/B independence, dedup).
- **Business impact:** none. Rule #4 satisfied.

### 6. Deterministic 3D reproduces authoritative 2D — **PASS**
- **Files/functions:** `scene_service.build_scene(file_id, canonical=snapshot)`; FE `RoomScene3D` consumes `room.furniture` as-is (no UID minting); `validation_service.validate_2d_to_3d` / `validate_scene_2d_to_3d`.
- **Evidence:** `tests/test_2d_to_3d_fidelity.py` (12 synthetic fail-safe cases + real-scene faithful + generation refusal), `tests/test_furniture_placement_2d_to_3d.py`. No missing/extra/duplicate/misplaced/wrong-room furniture; failures reject, never silently correct/invent (rule #5).
- **Business impact:** none.

### 7. Fixed deterministic camera — **PARTIAL (code-verified, no automated test)**
- **Files/functions:** FE `lib/aiCamera.ts::solveAiCamera` (pure deterministic: "same room in → same camera out"; corner-scored, furniture-centroid target); `RoomScene3D` camera; fixed capture frame.
- **Evidence:** code is a pure deterministic function; verified by `tsc`/build. **No dedicated automated camera test exists.**
- **Root cause:** camera is a pure frontend function with no backend/JS test harness (no vitest configured).
- **Business impact:** low — deterministic by construction; a regression in `solveAiCamera` would not be caught by an automated test.
- **Recommended minimal fix:** none required for correctness; **Tests required:** add a unit test for `solveAiCamera` (same input → identical output; coverage/window scoring) once a JS test runner is configured.

### 8. Base render (deterministic 3D → PNG) — **FAIL (verified dimension defect)**
- **Files/functions:** FE `components/design-studio/BaseRenderBatch.tsx` (`CAPTURE_W/H=1216×832`, `canvas.toDataURL`), `RoomScene3D.tsx:337` `<Canvas dpr={[1, 2]}>`, `pages/DesignStudio.tsx` base_render_meta builder (`width:BASE_CAPTURE_W, height:BASE_CAPTURE_H`).
- **Status:** PNG is generated from deterministic 3D, non-blank, decodable, bound to `design_version_id`/`room_key` ✅ — BUT the **declared dimensions do not match the actual PNG dimensions on HiDPI displays.**
- **Root cause (traced, not assumed):**
  - Capture container = **1216×832 CSS px**.
  - `<Canvas dpr={[1, 2]}>` → react-three-fiber `setPixelRatio(min(devicePixelRatio, 2))`. On a 2× display, dpr=2.
  - WebGL backing store (`canvas.width/height`) = CSS × dpr = **2432×1664**.
  - `canvas.toDataURL()` reads the backing store → **PNG = 2432×1664** (matches the previously observed "actual 2432×1664").
  - `base_render_meta` declares the **CSS constants 1216×832**, not the backing-store size.
  - **Exact transition:** `dpr=[1,2]` → `setPixelRatio(2)` (RoomScene3D Canvas) → backing store doubles; the PNG carries the doubled size while the metadata carries the CSS size.
- **Executable evidence (backend consequence):**
  ```
  HiDPI (dpr=2) capture 2432x1664  vs meta 1216x832 -> BASE_RENDER_WRONG_SIZE
  dpr=1       capture 1216x832     vs meta 1216x832 -> PASS
  ```
  (`base_render_service.validate_base_render` with a simulated 2432×1664 PNG.)
- **Business impact: HIGH.** On any HiDPI/Retina/scaled display (dpr≥2) the Handoff #12 size check rejects **every** base render → no base reaches fal → **AI generation is fully blocked**. Standard (dpr=1) displays are unaffected. The Handoff #12 backend tests fabricated exactly-1216×832 PNGs, so they did not catch this.
- **Recommended minimal fix (do NOT weaken the size check):**
  - **Preferred (determinism):** force a fixed pixel ratio on the capture path — add an optional `dpr` prop to `RoomScene3D`, and in `BaseRenderBatch` render the capture Canvas with `dpr={1}`. The backing store is then deterministically **1216×832** on every machine, matching the meta constants and improving cross-machine determinism (rules #5/#6). Base render is a geometry reference, so losing 2× supersampling is acceptable.
  - **Alternative:** have `BaseRenderBatch`/`DesignStudio` put the **actual** `canvas.width/height` into `base_render_meta` (it already logs them). This makes declared==actual but removes the fixed-size guarantee (variable per device).
- **Tests required:**
  1. A capture-dimension test asserting the produced PNG is exactly 1216×832 regardless of `devicePixelRatio` (needs a JS test runner, or a Playwright e2e assertion on `canvas.width/height`).
  2. A backend test that feeds a **2432×1664** PNG with 1216×832 meta and asserts the *fixed* capture path would not occur — i.e. after the fix, the real capture is 1216×832. (Keep the existing WRONG_SIZE test as the negative case.)

### 9. Pre-FAL validation (base-render contract + geometry gates) — **PASS (contract correct; see Stage 8 for the input defect)**
- **Files/functions:** `base_render_service.validate_base_render` (MISSING/CORRUPT/BLANK/WRONG_VERSION/WRONG_ROOM/WRONG_SIZE); `generation_service.generate` base-contract loop; `_classify_base_gate` (ROOM_EMPTY/BASE_GEOMETRY_INVALID/BASE_RENDER_MISSING/BLANK/CORRUPT); `validation_service.validate_scene_2d_to_3d`; §L `validate_scene_against_canonical`.
- **Evidence:** `tests/test_handoff12_base_render_binding.py` (7: stale version / wrong room / wrong size / missing metadata → reject, `boom.assert_not_called()`; correct metadata not rejected; stale-after-edit rejected), `tests/test_base_render_gate.py`, `tests/test_fal_boundary.py`.
- **Note:** the contract itself is correct and protective (rule: do not weaken). The defect is that the *frontend* feeds it mismatched dimensions (Stage 8), so the correct contract rejects legitimate HiDPI captures.
- **Dining/open-plan (rule #13):** geometry gate NOT weakened — `test_2d_to_3d_fidelity.py`, `test_geometry_lock.py`, `test_img2img_gating.py` green; UNCERTAIN/open-plan rooms remain honestly gated.

### 10. fal.ai request — **PASS**
- **Files/functions:** `generation_service._render_room` → `FalFluxAdapter.generate` (`ai/fal_flux_adapter.py`); only `{prompt (+ geometry-preservation preamble), image_url (validated base), num_images, output_format, seed}` sent.
- **Evidence:** `tests/test_fal_boundary.py` (offline — `httpx.Client` boom-patched; never PDF/screenshot/scene-json/mock/fallback/stale), `tests/test_fal_flux_adapter.py`. Config provider=fal / model=fal-ai/flux-kontext/dev / endpoint=https://fal.run verified (rules #7/#9/#14).
- **Business impact:** none. No live request made.

### 11. Output download → AI output — **PASS**
- **Files/functions:** `FalFluxAdapter._fetch_image` (data-URI or URL; verifies real image bytes, rejects non-image content-type / undecodable), `_to_png`.
- **Evidence:** `tests/test_fal_flux_adapter.py`. No fabrication; real `AIProviderError` on failure with bounded retries; 401/403/422 are provider responses, not transport errors.
- **Business impact:** none.

### 12. Post-AI validation — **PASS**
- **Files/functions:** `validation_service.assess_ai_output_geometry` (decodable / non-blank / aspect / meaningful-diff → `FAILED_GEOMETRY_VALIDATION`), run in `_render_room` **before** cache/save.
- **Evidence:** `tests/test_ai_output_geometry_gate.py` (8: valid restyle passes; blank/corrupt/aspect/identical reject). Deterministic only; no vision/object detector claimed (rule #6).
- **Business impact:** none.

### 13. Save / reject — **PASS**
- **Files/functions:** `generation_service.generate` persistence (`file_storage.save_generation_image` + `AIGenerationImage` only for passing rooms); geometry-lock `_verify_geometry_unchanged`.
- **Evidence:** `tests/test_geometry_lock.py` (failed gen leaves canonical byte-identical, no fallback; success persists), `tests/test_generation_route_and_pacing.py` (total failure → structured 201, never a fake image). Rule #11/#14.
- **Business impact:** none.

---

## Top verified blockers (ordered by pipeline dependency)

1. **[HIGH — BLOCKER] Base-render dimension mismatch (dpr).** `RoomScene3D` `<Canvas dpr={[1,2]}>` produces a 2432×1664 PNG on HiDPI while `base_render_meta` declares 1216×832 → Handoff #12 size check rejects every base render → generation fully blocked on dpr≥2 displays. **Proven executably.** Fix: force `dpr={1}` on the capture-path Canvas (preferred) or report actual canvas dims in meta. *This is the only true blocker and sits at Stage 8, upstream of fal, so it blocks all downstream stages on affected displays.*

2. **[LOW — observation] `DEFAULT_AI_PROVIDER` code fallback is `"nvidia"`.** `config.py` uses `os.getenv("DEFAULT_AI_PROVIDER", "nvidia")`; `.env` sets `fal` so the deployed default is correct, but if `.env` omits the key the system would default to NVIDIA, contradicting rule #7/#9. Fix (optional): change the fallback to `"fal"`.

3. **[LOW — coverage gap] No automated camera test.** `solveAiCamera` is deterministic but untested by any runner; a regression would be silent. Fix: add a unit test once a JS runner exists.

4. **[LOW — coverage gap] Handoff #12 backend tests use synthetic exactly-sized PNGs.** They did not model the real dpr-scaled capture, which is why blocker #1 slipped through. Fix: add a capture-dimension test (Stage 8).

5. **[NONE — not a pipeline blocker] `reportlab` not installed** → 2 `test_invoice_upload.py` failures (unrelated invoice feature). Fix: install `reportlab` or mark those tests optional.

---

## Verdict
Every pipeline stage passes with executable test evidence **except Stage 8 (base render)**, which has a verified, high-severity dimension-binding defect that blocks generation on HiDPI displays. **The pipeline is NOT ready** until blocker #1 is fixed: unit tests pass only because they fabricate exactly-1216×832 PNGs, whereas the real frontend capture is dpr-scaled. No code was modified during this audit; no live fal.ai request was made.
