# Phase 3 — Architecture Readiness & Root-Cause Report (read-only)

**Mode:** read-only; no source/config/prompt/schema/DB changes, **no FAL calls** (reused cached models + existing artifacts). Plan `f6b65d2b`, design version `1831bf84` (version 31).

## 0. Baseline & artifact inventory
- **Source state:** MyNest is **not a git repo** (no revision hash). Working tree carries the uncommitted P0 change (`validation_service.assess_ai_render`, `generation_service`, `schemas/generation.py`, `GenerationGallery.tsx`, `generations.ts`), the Phase 2I/2J contract (`render_input_contract.py`, `scene_service` opening `status`), and the harness-only `onFurnitureTransforms` instrumentation.
- **Matched Bedroom 1 artifacts (sha256, 1216×832):**
  | Artifact | sha256 | FAL req | params |
  |---|---|---|---|
  | base_render.png | `04ea7854…` | — | dvid 1831bf84 |
  | ai_output.png (img2img) | `b6c9580e…` | `01a133ca` | flux-kontext/dev edit, seed 1558158484, prompt `7fe63b11` |
  | controlnet_output.png (s1.0) | `d8dcd18f…` | `01a134fb` | canny, strength 1.0 |
  | controlnet_s07.png | `dbdd0a4d…` | `01a13511` | canny, strength 0.7 |
  | controlnet_s05.png | `0903c5cd…` | `01a13514` | canny, strength 0.5 |
  All in `backend/output/p2h4_bedroom1_preservation/` and `…/p2k2_controlnet_ab/`. **No other room has a matched base↔output pair** (production persists no base — finding F4).

## A. AI furniture preservation
| Output | distinct /5 | both side tables | notes |
|---|---|---|---|
| img2img baseline | **4/5** | NO | ≥1 side table lost; room recomposed (diff vs base **15.47**) |
| ControlNet 1.0 | **5/5** | YES | all at base positions (diff **1.80**) |
| ControlNet 0.7 | **5/5** | YES | diff **2.50** |
| ControlNet 0.5 | **5/5** | YES | diff **2.72** |
- **CONFIRMED:** img2img (flux-kontext edit) **omits/recomposes** furniture; **Canny ControlNet preserves all 5** at 0.5–1.0 (visual + offline uncalibrated detector: 2 side-table-like + bed + cabinet + chest at every strength). Dressing table is preserved as the base's **3-drawer chest** (not a mirror unit).
- **UNKNOWN / BLOCKER:** additional rooms are **NOT_AUDITABLE** (no matched pairs); this is a **single-room, single-seed** result — not a general guarantee.

## B. Photorealism
- **Request trace (SOURCE-VERIFIED, `ai/fal_flux_adapter.py`):** edit body `{prompt, image_url, num_images, output_format, seed}`; controlnet body `{prompt, control_lora_image_url, control_lora_strength, image_url (init, when `FAL_CONTROL_USE_INIT=true`), image_size, seed}`. Preprocessing = `_to_png` re-encode only (pixel-identical); postprocessing = `_to_png` + degenerate gate; no crop/mask/resize.
- **Init-image coupling — HYPOTHESIS, not causally proven.** ControlNet realism barely changed as strength dropped (diff 1.80→2.72), so **control strength is NOT the realism limiter.** The leading hypothesis is the **init image** (`FAL_CONTROL_USE_INIT=true` sends the base as `image_url`), which anchors the output to the clay base regardless of canny strength. **Causality cannot be confirmed without a no-init FAL generation** (a new call — blocked here).
- **Alternatives identified (not tested, all need FAL):** `FAL_CONTROL_USE_INIT=false` (canny-only), depth vs canny (`FAL_CONTROL_MODEL`), `guidance_scale` tuning.

## C. Physical scale & coordinate conventions
- **Three conventions (SOURCE-VERIFIED):**
  1. Placement `DesignStudio.tsx:45,324` — `SCALE=0.15` ⇒ 1 px = 6.667 mm.
  2. Backend `coordinates.py:14` — `DEFAULT_MPP=0.01` ⇒ 1 px = 10 mm (used by `architectural_service` for PDF→mm).
  3. Render `scene.ts:126 computeMpp = 2.0/max(bed.w,bed.h)` — the scale the **3D scene actually uses**.
- **Intended contract (from source/tests):** library mm → px at placement (`SCALE`); scene normalizes to metres via `computeMpp` (anchor bed = 2.0 m). The three disagree.
- **CONFIRMED discrepancy (+20.3%, uniform):** the anchor bed is 249 px = 1.66 m at placement scale, but `computeMpp` forces it to 2.0 m → all furniture renders **+20.3%** larger than placement implies (quantified across BR1 + BR2). **Relative geometry is exact** (0 position/rotation delta). *(Out of scope to change per constraint.)*

## D. Geometry validation
| Field / check | File · function | Guarantees | Status |
|---|---|---|---|
| scene `geometry_faithful` | `validation_service.validate_scene_against_canonical` | deterministic canonical↔scene match | enforced + tested |
| AI-output `geometry_faithful` / `geometry_status` | `validation_service.assess_ai_render` (P0) | honest tri-state; **FAITHFUL only with `output_verified`** (never set today) → **UNVERIFIED** | my P0; TEST-VERIFIED |
| `assess_ai_output_geometry` | `validation_service.py:771` | **degenerate only** (blank/aspect/identical); docstring: "does NOT attempt per-object comparison" | SOURCE-VERIFIED |
| furniture detector/validator | `furniture_object_validation_service`, `furniture_detector_hybrid` | per-object match | **audit-only, NOT_CALIBRATED, not wired to prod** |
- **False-pass risk:** previously `geometry_faithful=True` from input validity (false pass) — **fixed by P0** (now UNVERIFIED). Output fidelity remains genuinely unverified (no per-object check runs).
- **Missing regression tests:** output-level furniture count/identity gate; de-hardcoded opening/furniture-count fixtures (the 2 drift failures).

## E. Snapshot, persistence & gallery
- **Generation provenance:** binds a frozen snapshot — `floor_plan_service.capture_generation_snapshot` (append-only). **Enforced.**
- **Gallery preview — CONFIRMED mismatch risk:** `GenerationGallery.tsx:41` loads `fetchScene(planId)` = the **current** scene, NOT the generation's `design_version_id` snapshot. ⇒ **a gallery preview can display a later-edited 2D scene alongside an earlier generation's AI output.**
- **Legacy status ambiguity:** addressed by P0 (`geometry_status` + `input_geometry_locked`; UI shows "Not Verified" honestly).

## Test outcomes (executed)
```
pytest test_render_input_contract test_ai_furniture_fidelity_reporting test_ai_output_geometry_gate
  test_img2img_gating test_furniture_manifest test_2d_to_3d_fidelity test_base_render_gate
  test_opening_geometry_audit test_door_window_merge test_furniture_object_validation
  test_furniture_2d_to_3d_audit test_generation_route_and_pacing
=> 138 passed, 3 FAILED
```
- **Passed:** all contract/fidelity/img2img/scene/base tests (incl. the P0 honest-status tests).
- **Failed (pre-existing live-data drift, NOT regressions):** `test_opening_geometry_audit::test_step3_counts_regression` (verified openings 11→10), `test_door_window_merge` ×2 (canonical furniture 33→34). Root cause: the plan was edited; the tests hardcode stale counts.
- **Blocked:** none (cached models used; no FAL).

## Confirmed vs hypotheses vs unknowns
- **Confirmed:** img2img drops/recomposes furniture; ControlNet preserves (single case); +20.3% absolute scale; `assess_ai_output_geometry` is degenerate-only; output validators audit-only; gallery loads current (not snapshot) scene; 3 test failures = data drift.
- **Hypotheses:** init-image coupling causes ControlNet's low realism (not proven without a no-init FAL run); FAL preservation is seed/room-variable.
- **Unknowns:** preservation across other rooms/seeds; the realism fix; mechanism of img2img omission.

## Cross-workstream dependencies
- **A ↔ B coupled:** ControlNet is the preservation lever (A), but its clay-like realism (B) blocks adoption — a realism fix must land *before* enabling ControlNet.
- **D depends on A:** `geometry_status=FAITHFUL` can only ever be reported once an output furniture check (A) is wired.
- **C and E are independent** of A/B/D and of each other.

## Prioritized fix sequence (minimal, dependency-aware — NOT implemented)
1. **P0 (done, pending review):** honest `geometry_faithful`/`geometry_status`. *Acceptance:* no output labeled faithful without output evidence (TEST-VERIFIED).
2. **P1 — E gallery provenance:** load the generation's `design_version_id` scene in `GenerationGallery` (not `fetchScene(planId)`). *Files:* `GenerationGallery.tsx` + a snapshot-scene endpoint. *Acceptance:* gallery 2D preview matches the generation's snapshot even after edits. Independent, low risk.
3. **P1 — D output validator wiring:** run `furniture_object_validation_service` on the output as advisory → let `geometry_status` reach FAITHFUL/FAIL with evidence; de-hardcode the 2 drift tests. *Acceptance:* a missing-item output is flagged, never FAITHFUL.
4. **P1/P2 — A+B realism experiment (BLOCKED on FAL approval):** test `FAL_CONTROL_USE_INIT=false`, depth vs canny, guidance tuning across 2–3 rooms/seeds to resolve preservation-vs-realism *before* any `FAL_USE_CONTROLNET` production change.
5. **P2 — C scale reconciliation:** unify the 3 conventions or document the contract (out of current scope per constraint).

## Blockers requiring approval/evidence
- **FAL calls** for: additional-room preservation audits, the init-image/depth realism experiment. (Production doesn't persist base images → re-render or base-sha persistence needed first.)
- **Stable test fixtures:** the 3 drift failures need a pinned design version or de-hardcoded counts.

**Stopping after this report.** No fixes, config/prompt/schema/DB changes, FAL calls, or commits. All diagnostic artifacts preserved; hashes/IDs recorded above.
