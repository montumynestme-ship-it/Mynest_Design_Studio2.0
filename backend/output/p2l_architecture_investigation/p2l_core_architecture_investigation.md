# MyNest Design Studio — Core 3D AI Render Architecture Investigation

**Mode:** investigation & planning only. **No code changes, no FAL calls.** Evidence is consolidated from Phases 2–2K (live plan `f6b65d2b`, dvid `1831bf84`) plus direct source tracing.

## 1. Executive summary
The **deterministic half of the pipeline is sound**: canonical furniture reaches the Three.js scene with exact identity/position/rotation (Phase 2H-2: 22/22, 0 delta), on immutable append-only design versions. The **weakness is the AI half**: the image-to-image model receives only a **base PNG + prompt text — no structured geometry conditioning** (`fal_flux_adapter.generate`), so furniture is unreliably preserved (Phase 2K: ≥1 side table not identifiable, positions recomposed). Secondary gaps: provenance (production metadata lacks a base-PNG hash), honest output validation (status not evidence-driven), opening wall-association (3 `NEEDS_REVIEW`), and room-identity overlap. **The primary lever is structured conditioning + output validation, not a bigger model.**

## 2. Verified end-to-end flow (source references)
```
Editor (DesignCanvas.tsx, Konva) → placement handlePlace (DesignStudio.tsx:261; w=width*SCALE,h=depth*SCALE)
 → save_layout (floor_plan_service.py:248, append-only DesignVersion, _furniture_fingerprint dedup)
 → GET /scene (floor_plans.py:102 → scene_service.build_scene:214; group_by_room; _attach_opening_placements:146)
 → fetchScene (lib/scene.ts:115; computeMpp:126 global mpp = 2.0/first-bed)
 → RoomScene3D.tsx (furniture group pos=(cx-roomcx)*mpp,(cy-roomcy)*mpp rot=-θ; aiCamera.ts solveAiCamera; near-wall cutaway)
 → BaseRenderBatch.tsx base PNG 1216×832 + CaptureHook (projectFurnitureBoxes, onFurnitureTransforms)
 → POST /generate (floor_plans.py:173 → generation_service.generate:885)
     capture_generation_snapshot (floor_plan_service.py:315, freezes version) │ build_room_prompts │ base_render_service.validate_base_render (dims only)
     ThreadPoolExecutor per room (generation_service.py:1220)
 → FalFluxAdapter.generate (ai/fal_flux_adapter.py; body={prompt,image_url,num_images,output_format,seed})
 → raw output → _to_png + postgen fidelity (fidelity_service.calculate_room_fidelity) → AIGeneration/AIGenerationImage (db/models.py) → UI
```
Providers: `ai/registry.py` → `fal_flux_adapter` (flux-kontext/dev **edit**; controlnet canny/depth path exists but `FAL_USE_CONTROLNET=false`), `nvidia_flux_adapter`, `mock_adapter`.

## 3. Architecture diagram (existing)
Six responsibilities already have owners:
1. **Canonical** → `DesignVersion` (append-only) + `floor_plan_service`.
2. **Geometry/scene prep** → `scene_service.build_scene`, `prompt_service.group_by_room`.
3. **Base render** → `RoomScene3D` + `BaseRenderBatch` + `base_render_service` (+ Phase 2J `render_input_contract`).
4. **AI orchestration** → `generation_service.generate` + `ai/registry` + adapters.
5. **Output validation** → `fidelity_service`, `furniture_object_validation_service`, `furniture_inventory_validation_service`, `vision_validation_service` (mostly audit-only / NOT_CALIBRATED).
6. **Versioned results/observability** → `AIGeneration` + frozen snapshot + debug_artifacts.

## 4. Findings table
| ID | File · function | Existing behavior (evidence) | Weakness | Impact | Test/validation | Recommendation | Risk |
|---|---|---|---|---|---|---|---|
| **F1** | `ai/fal_flux_adapter.py` body | FAL gets `{prompt, image_url(base PNG), num_images, output_format, seed}` only | **No structured conditioning** (no depth/edge/mask/coords) | Model free to move/drop/alter furniture | 2K: ≥1 side table lost, recomposition | Enable/evaluate the **existing** canny/depth controlnet path as a controlled experiment | Med (changes base-→output coupling) |
| **F2** | `generation_service._render_room` | edit/img2img; random per-gen seed | Preservation is model-dependent, high variance | Furniture/identity/position drift | 2K verified pair; 2H-4 | Output validation + conditioning (F1/F7) | — |
| **F3** | `RoomScene3D.tsx` cutaway | near-wall cutaway restores low-furniture visibility | (addressed Phase 2B) small items still <0.5% frame | Low saliency → weak base signal | 2H-2 captures | saliency floor for tiny items (P2) | Low |
| **F4** | `generation_service` render_debug | records `geometry_hash`,`prompt_hash`,`seed` — **no base-PNG sha** | Can't prove exact base bytes per attempt; dvid drifts | Unauditable provenance; stale-pair risk | 2H-3/2K; render_debug.json keys | **Persist base sha256 + dims** in gen metadata | Low |
| **F5** | `scene_service._attach_opening_placements` | sets `verified`/`wall_id` + (2I) `status` | 3 openings `wall_id=None` NEEDS_REVIEW; verify count drifted 11→10 | Doors/windows off-wall in render | 2J contract; test_opening_geometry_audit (fails 10 vs 11) | Harden wall-snapping; keep explicit status (**door/window phase deferred**) | Med |
| **F6** | `scene_service.build_scene` / `group_by_room` | overlapping `kitchen-dining-area` + `kitchen`/`dining-area`; duplicate "Bedroom 3" label (unique ids) | Room overlap/duplicate | Grouping/double-count risk; prompt-manifest mismatch | 2F-1; 2J contract (unique ids OK, labels flagged) | Dedup/flag overlapping rooms | Med |
| **F7** | `fidelity_service`/UI status | `ai_geometry_faithful` not driven by output detection | Overconfident status | Users can't tell real from fallback | furniture-missing artifact claimed "faithful" vs 2K evidence | Drive status from `furniture_object_validation`; honest PASS/UNCERTAIN/FAIL | Low-Med |
| **F8** | `lib/scene.ts computeMpp` | global mpp = 2.0/first-bed (scene order) | Absolute scale depends on room order/version | Possible absolute-scale skew (relative OK) | 2G-1 (BR1 bed 2.26m vs 2.0m target) | Document; calibrate per-plan deterministically | Low |
| **F9** | `aiCamera.ts solveAiCamera` | corner viewpoint, fov 46, centroid target | No clipping found | **Not a defect** | 2H-2 (all boxes in-frame) | optional framing/lighting presets (P2) | Low |
| **F10** | `furniture_object_validation_service` etc. | validators exist, audit-only/NOT_CALIBRATED | Not wired to production gate/status | Output defects not caught in prod | prior phases | Wire as advisory output check (F7) | Low-Med |

Confirmed defects: F5 (unverified openings + count drift), F6 (room overlap), F7 (overconfident status), F4 (provenance gap). Architectural risk: F1/F2 (no conditioning). Addressed: F3. Not a defect: F9. Unresolved: F8 absolute scale, F5 drift root cause.

## 5. Geometry-preservation & coordinate audit
- **Units:** library mm (`data/furniture.ts`) → placement px via `SCALE` → scene metres via **global `mpp`** (`computeMpp`, first bed = 2.0 m). **Relative proportions uniform/preserved.** Absolute anchor is room-order dependent (F8).
- **Transform:** furniture group `pos=(cx−roomcx)·mpp,(cy−roomcy)·mpp`, `rot=−θ`, footprint `w·mpp×h·mpp`. **Measured exact** (2H-2: dX=dZ=0.0000 m, dRot=0.0000°; dims within mesh overhang ≤0.045 m).
- **Openings:** projected onto supporting wall with `wall_relative{normalized,along,perp_removed}`; unverified → authored position + explicit NEEDS_REVIEW.
- **Three validation responsibilities (Phase 2 invariants):** (1) canonical integrity — **guaranteed** (append-only immutable versions; generation binds a frozen snapshot); (2) deterministic scene fidelity — **validated** (2H-2 exact + render_input_contract); (3) **AI image fidelity — NOT reliably validatable** (documented limitation; image-space only).

## 6. AI quality bottleneck analysis
Ordered by evidence:
1. **Conditioning (primary):** no structured lock (F1) → the model's biggest freedom source.
2. **Output validation (secondary):** no evidence-based gate (F7/F10) → defects pass silently.
3. **Base saliency (tertiary):** tiny items <0.5% frame (F3) weaken the signal.
4. **Model size: NOT the bottleneck** — flux-kontext/dev preserves bed/wardrobe/dressing; the failure is geometric fidelity, addressable by conditioning + validation, not a larger model.

## 7. Existing vs proposed architecture
All six layers **already exist**; the gaps are: conditioning strategy unused (F1), output validation not evidence-driven (F7/F10), provenance incomplete (F4), room-identity overlap (F6), opening wall-association (F5). **Reuse, don't rebuild** — no new services/queues/DBs are warranted.

## 8. Prioritized plan
**P0 — correctness/provenance/version isolation**
- F4: persist base-PNG `sha256`+dims in generation metadata (`generation_service` write path). Acceptance: every generation record correlates to its exact base bytes. Risk low.
- Verify + guard that a stale async generation result cannot be shown as "current" over a newer design version (`AIGeneration.design_version_id` already recorded via frozen snapshot — add an explicit staleness check in the list/display path). Acceptance: a generation bound to version N is marked stale when latest > N.

**P1 — render quality & honest validation**
- F1: controlled **depth/canny conditioning experiment** via the existing `FAL_USE_CONTROLNET` path (separate approval; FAL cost). Acceptance: measured furniture-preservation improvement vs the edit baseline on the persisted pair.
- F7/F10: drive output status from `furniture_object_validation_service` (PASS/UNCERTAIN/FAIL), never label-only.
- F5: opening wall-snapping hardening + explicit status (status field already added 2I/2J; **door/window correction deferred**).
- F6: detect/flag overlapping & duplicate rooms before generation (render_input_contract extension).

**P2 — optimization/enhancement**
- F3 saliency floor; F8 deterministic absolute-scale calibration; camera/lighting/material presets; caching deterministic base renders when inputs unchanged.

## 9. Regression test plan & acceptance
- Canonical immutability during generation (snapshot frozen; DB version unchanged).
- Unit/coordinate conversion + exact transform (2H-2 harness: per-room uid coverage + 0-delta transforms).
- Opening wall-association + explicit unplaced status (2J contract; `test_render_input_contract`).
- Furniture identity/room-uniqueness/duplicate detection (2J contract — 18 tests pass).
- Deterministic scene reproducibility (same version+settings → same transforms).
- Version association per result; **stale async not overwriting newer** (new P0 test).
- Image dims/format/corrupted-image handling (`base_render_service`, `_to_png`).
- Provider errors/timeouts/missing credentials (`fal_flux_adapter` transport diagnostic exists).
- Output validation failure/fallback distinguishable from success (F7).
- **Baselines:** the persisted 2H-4 pair is the reproducible fixture; compare before/after on identical input/version/settings. Separate automated metrics (object count, provenance) from human visual review.

## 10. Minimal implementation sequence (await approval)
1. F4 base-sha persistence + stale-generation guard (P0; independent, low risk).
2. F7/F10 evidence-based status (P1; reuses existing validators).
3. F6 overlapping-room flagging (P1; render_input_contract extension).
4. F1 conditioning experiment (P1; **separate FAL-cost approval**, measured on the fixture).
5. F5 opening hardening (**after** the deferred door/window phase is opened).
Each is small, independently testable, rollback-safe.

## 11. Open questions (cannot be resolved from source/tests alone)
- Why did opening verification drift **11→10** with the **same canonical version** (F5)? Needs `structured_walls` reconstruction provenance/timestamps.
- Why does `design_version_id` change between reads with identical furniture (F4)? Needs DB version history.
- Is BR1's bed intentionally larger than BR3's, or is the global-mpp anchor mis-scaling (F8)? Needs the source plan's true drawing scale.
- Does conditioning (depth/canny) actually improve preservation for this model? Needs the approved FAL experiment.

## Confirmation
No source/schema/migration/API/dependency/config changes. No FAL calls. Investigation and planning only — awaiting approval before any implementation. Claims are grounded in cited source and prior-phase evidence; AI-output geometry preservation is **not** claimed solved.
