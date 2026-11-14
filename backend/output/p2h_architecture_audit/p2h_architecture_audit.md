# Phase 2H — 3D AI Render Input Architecture Audit (read-only)

**Plan:** `f6b65d2b-4f96-4931-9f08-67dbd09776f6` (MR.MATHUR) · **design_version:** `1831bf84…` · Backend live :8001. No code changes, no FAL calls in this report (the FAL payload evidence reuses the already-approved Phase 2H-4 request).

## 1. End-to-end production data flow
```
Editor (2D) ──save_layout──► DesignVersion (append-only, immutable canonical_json)
   │                                   │
   │                      get_latest_version_info ─► /scene (build_scene)
   ▼                                   ▼
LayoutItem{uid,item_id,cx,cy,w,h,rotation,label}   Scene{rooms[id,label,bbox,furniture[],
                                                        opening_placements[],walls}
                                   │  (group_by_room: furniture-anchor clustering → room label)
                                   ▼
Frontend fetchScene ─► BaseRenderBatch ─► RoomScene3D(aiRenderMode, dpr=1, cutaway)
   furniture: group pos=(cx-roomcx)*mpp,(cy-roomcy)*mpp  rot=-θ  footprint=w*mpp×h*mpp
   openings:  opening_placements projected on supporting wall
   camera:    solveAiCamera (corner viewpoint, fov 46, target=furniture centroid)
                                   ▼
   deterministic BASE PNG (1216×832) + base_render_meta(sha, boxes)
                                   ▼
POST /generate(rooms, base_renders{room:dataURI}, base_render_meta)
   capture_generation_snapshot(freeze version) │ build_room_prompts │ base_render_service.validate_base_render(§L)
                                   ▼
FalFluxAdapter.generate ─► fal.run/fal-ai/flux-kontext/dev (edit)
   body = { prompt(text, inventory), image_url(BASE PNG), num_images:1, output_format:png, seed }
                                   ▼
raw FAL OUTPUT PNG ─► postgen fidelity/validation ─► stored (storage/generations) ─► UI
```

## 2. Source files/functions per stage
| Stage | File · function |
|---|---|
| Canonical persist | `floor_plan_service.save_layout` (append-only; `_furniture_fingerprint` dedup) |
| Version select | `floor_plan_service.get_latest_version_info` / `_latest_version` |
| Scene build / room grouping | `scene_service.build_scene`; `prompt_service.group_by_room`,`_seed_label` |
| Scene client model | `frontend/src/lib/scene.ts` (`fetchScene`, `computeMpp`) |
| Deterministic 3D | `RoomScene3D.tsx` (furniture mapping, cutaway classifier, lights, floor), `Furniture.tsx` (meshes), `furniture3d.ts` (kind/height/color) |
| Camera | `aiCamera.ts` `solveAiCamera`/`solveEyeLevelCamera` |
| Base capture + measurement | `BaseRenderBatch.tsx`; `RoomScene3D CaptureHook`; `furnitureBoxes.ts projectFurnitureBoxes` |
| Prompt | `prompt_service.build_room_prompts`; `fal_flux_adapter._build_fal_edit_prompt` |
| FAL request | `fal_flux_adapter.generate` (body above), `core/config.py` (`FAL_IMAGE_MODEL`, `FAL_USE_CONTROLNET=false`) |
| Generate orchestration | `generation_service.generate` / `_render_room`; `base_render_service.validate_base_render` |
| Validators | `furniture_object_validation_service`, `furniture_inventory_validation_service`, `furniture_geometry_validation_service` |

## 3. Canonical → live-scene → base comparison (Phase 2H-2, live data)
- **22 canonical furniture instances, 22 captured, 22 PASS; 0 missing/unexpected/duplicate; 8 rooms covered.** Position delta 0.0000 m, rotation 0.0000°, dim overhang ≤0.045 m (mesh detail). Each uid in exactly one room (disjoint). **The 2D→3D transform and room grouping are faithful.** (Evidence: `backend/output/p2h2_live_transform_audit/`.)
- Coordinate systems: canonical plan-px → scene metres via **one global `mpp`** (anchored to the first bed in scene order = Bedroom 3); uniform, proportion-preserving. Absolute-scale anchor is version/order-dependent (unresolved, see RC table).

## 4. Actual FAL payload evidence (Phase 2H-4 request `01a133ca-ae45-70b2-a3ed-95dcf5a04daa`)
- **base image:** sha256 `04ea7854…` (persisted) → submitted (pixel-identical re-encode) `9e670a46…`, **1216×832**.
- **model/endpoint:** `fal-ai/flux-kontext/dev`, `https://fal.run/...`, conditioning **edit (image-to-image)**.
- **params:** `{num_images:1, output_format:png, seed:1558158484}`; controlnet off; guidance/steps = provider defaults.
- **prompt:** sha256 `7fe63b11…`, 11040 chars (room identity + exact inventory list + geometry-preservation text).
- **room:** `bedroom-1`; canonical UIDs bed/2×side-table/wardrobe/dressing.
- **Structured furniture/opening geometry sent to the model: NONE.** The model receives only the base **pixels** + prompt **text**. There is **no geometric lock** (no coords/sizes/rotations/masks). This is the central architectural fact.

## 5. Furniture identity & visibility audit
- **Base (deterministic):** post-cutaway, all canonical items are **visually present** in the base (Phase 2B/2H-4). Pre-cutaway bases occluded low items behind the 2.7 m walls (the earlier “present-but-invisible” symptom — addressed by the near-wall cutaway in `RoomScene3D`).
- **AI output (Phase 2H-4, one run):** of 5 BR1 items → **3 PRESERVED** (bed, wardrobe, dressing-table rendered **with mirror**), **2 AMBIGUOUS** side tables (only **4 distinct objects** in the output ⇒ ≥1 side table not preserved); positions **strongly recomposed** (diff 15.47).
- **Variance:** the earlier Phase 2C run (seed 1587969140) dropped a side table **and** made the dressing table a bench; this run preserved the dressing-with-mirror but lost a side table and recomposed. ⇒ **FAL preservation is high-variance across seed/prompt** (hypothesis; needs a seed study).
- **Saliency:** smallest furniture boxes occupy **<0.5% of the frame** (BR1 side table 0.42%). Small base signal correlates with non-preservation.

## 6. Door/window position & wall-association audit (live `opening_placements`)
| room | editor doors/windows | placements | unverified (wall_id=None) |
|---|---|---|---|
| living-area | 1/1 | 2 | 0 |
| bedroom-3 | 3/0 | 3 | **1 door** |
| bedroom-1 | 1/1 | 2 | 0 |
| kitchen-dining-area | 1/0 | 1 | **1 door** |
| bedroom-2 | 1/1 | 2 | 0 |
| kitchen | 0/0 | 1 (pdf window) | 0 |
| dining-area | 1/0 | 1 | 0 |
| bedroom-3-2 (dup/empty) | 0/1 | 1 | **1 window** |

- Most openings are **editor-sourced, verified, wall-associated** (render on their supporting wall). 
- **3 openings are UNVERIFIED (`wall_id=None, verified=False`)** → rendered at the *authored* position, **not wall-snapped** → a proven source of door/window position inconsistency (Known Issue #3). First divergence = **opening→wall association** in `scene_service` (not the base renderer, not AI).
- Openings are also **split across the overlapping `kitchen` / `kitchen-dining-area` rooms** (Phase 2F-1 duplicate/overlap finding), and `bedroom-3-2` is a duplicate-room artifact. Case classification: *opening lost during conversion* = none; *assigned to wrong wall* = not proven; *present but unverified/authored-position* = the 3 above. (Opening geometry/orientation **not modified** — audit only.)

## 7. Camera & framing audit (`solveAiCamera`, read-only)
- Per room, **no furniture is clipped** — all projected boxes lie within [0,1216]×[0,832] (measured from the Phase 2H-2 captures).
- Framing bounds are reasonable; the open-top dollhouse view with near-wall cutaway shows the interior.
- **Not a framing defect.** The only framing-adjacent concern is low **saliency** of small items (<0.5% frame), which feeds RC1, not a clipping/FOV bug. (Camera unchanged.)

## 8. Root-cause table
| # | Symptom | Earliest proven divergence | Evidence | Confidence | Unresolved |
|---|---|---|---|---|---|
| RC1 | Furniture missing/mismatched in AI | **FAL raw output** (no structured lock; only base pixels+text) | 2H-4: 5 base → 4 output objects; diff 15.47 recomposition | **HIGH** (divergence) | model *mechanism* (drop vs merge vs reposition) UNPROVEN |
| RC2 | Item in base but not in output | FAL raw output (base is correct post-cutaway) | 2H-2 all visible; 2H-4 side table lost | HIGH | which uid; seed dependence |
| RC2b | Low item invisible in base (historical) | deterministic base render (wall occlusion) | Phase 2B cutaway restored visibility | HIGH (addressed) | none |
| RC3 | Door/window position mismatch | **opening→wall association** (`scene_service`) | 3 openings `verified=False, wall_id=None` | MED-HIGH | why those 3 fail to snap; overlapping-room split |
| RC4 | Camera framing | none (no clipping) | per-room bounds in-frame | HIGH (not a defect) | small-item saliency <0.5% |
| RC5 | Status indicators unreliable | AI-faithful status not evidence-backed | `furniture-missing/ai-render-evidence.json` claims "ai_geometry_faithful:true" for all rooms, contradicting 2H-4 pixel evidence (side table lost) | MED-HIGH | how the indicator is computed vs actual detection |

Deterministic fidelity status is **evidence-backed** (2H-2). The **AI-geometry-faithful status is NOT** (RC5).

## 9. Minimal proposed changes (ordered by dependency & risk; NOT implemented)
1. **AI-output validation made evidence-based (lowest risk).** Drive the "ai_geometry_faithful" indicator from actual object-level detection of the output vs the base boxes (the validators already exist: `furniture_object_validation_service`). Stop reporting a label as proof (RC5). No render/model change.
2. **Opening→wall association hardening (low-med risk, backend only).** Investigate the 3 `verified=False` openings; improve wall-snapping so every opening resolves a `wall_id` or is explicitly surfaced as unplaced (RC3). Do not change already-corrected orientations.
3. **Base saliency for small items (med risk, render only).** Ensure small furniture (<0.5% frame) is visually distinguishable in the base (size/contrast floor), building on the cutaway (RC1/RC4-saliency). Deterministic only; no camera change.
4. **Structured geometry grounding for the model (higher risk, separate approved experiment).** The model currently gets no geometric lock. Evaluate image-conditioned control (e.g., the existing `FAL_USE_CONTROLNET`/depth/canny path) as a *separate, approved* experiment — not a prompt/param tweak to the current production path (RC1/RC2).
5. **Seed-variance study (needs FAL approval).** 2–3 linked single-room runs varying only the seed on the persisted base to quantify per-item preservation variance (RC1/RC2).

## 10. Regression tests required before any implementation
- **Deterministic transform audit** (per room): every canonical uid captured; position/rotation deltas within tolerance; each uid in exactly one room (2H-2 harness as the basis).
- **Opening wall-association test:** every rendered opening has a `wall_id` or is explicitly flagged unplaced; no silent authored-position fallback without a flag.
- **Base visibility/saliency test:** each canonical item's base box is non-degenerate and ≥ a documented frame-fraction threshold.
- **AI-output object audit (detection-based):** output distinct-object count/identity vs base boxes, reported as PASS/UNCERTAIN (never label-only).
- **Room-identity invariants:** unique room ids; no overlapping/duplicate rooms double-counting furniture (2F-1).

## Restrictions honored
Audit only — **no code changes, no FAL calls** (the payload evidence reuses the approved 2H-4 request). No changes to model/prompt/params/thresholds, canonical furniture/coords/dims/rotations/room assignments, walls/rooms/doors/windows/orientation, camera, or frontend stack. Fixture data (`base_scene.json`, `furniture-missing/*`) is labeled as such and **not** reported as production evidence (live `/scene` + the persisted 2H-4 request are the production sources).
