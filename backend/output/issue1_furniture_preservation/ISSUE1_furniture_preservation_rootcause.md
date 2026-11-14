# Issue 1 — AI Render Furniture Identity & Placement: Root-Cause Analysis

**Priority:** P0 (design correctness). **Mode:** investigation only — no code/config/FAL changes. **Attempt:** BR1, floor plan `f6b65d2b`, design version `1831bf84`, req `01a133ca`, base `04ea7854`, output `b6c9580e`, 1216×832. Artifacts verified to belong to this exact attempt (base/output sha match recorded metadata; `render_input_contract` provenance = PASS).

## 1. Root-cause verdict: **PARTIALLY PROVEN**
- **Proven:** every canonical item is faithful through the deterministic pipeline and visible in the base; the divergence occurs **only at the AI image-to-image output**; the prompt already forbids the operations the model performed; the model receives **no structured conditioning**; furniture validators are **not auto-run** on the output; and the "geometry-faithful" status is set from **base validation, not output inspection**.
- **Not proven:** the *specific mechanism* for the 2 ambiguous side tables (omitted vs merged vs hidden by the recomposition) — image-space evidence cannot isolate it.

## 2. Evidence chain (each stage)
| Stage | Source | Result | Tag |
|---|---|---|---|
| Canonical data | `DesignVersion.canonical_json` (append-only); `data/furniture.ts` | 5 items w/ stable uids (bed, 2 side-table, wardrobe, dressing) | **[VERIFIED]** |
| 2D→3D scene | `RoomScene3D.tsx` (pos=(cx−roomcx)·mpp, rot=−θ) | 5 transforms, **0 position/rotation delta** | **[VERIFIED]** Phase 2H-2 |
| Base image | `BaseRenderBatch.tsx`, cutaway | all 5 **visibly identifiable** (bed, 2 tables, wardrobe, 3-drawer chest) | **[VERIFIED]** Phase 2H-4 |
| AI input | `ai/fal_flux_adapter.py` body = `{prompt, image_url(base PNG), num_images, output_format, seed}` | **base PNG + text only — no depth/edge/mask** | **[VERIFIED]** |
| Prompt | `production_prompt.txt` L59/62/68 | "Do NOT add, move, remove, or rotate any furniture"; "Preserve the exact furniture count" | **[VERIFIED]** — already prohibits the failure |
| AI output | raw FAL output | **4 distinct objects** (bed, wardrobe, dressing+mirror, 1 bench); positions **recomposed** (diff 15.47); 2 side tables AMBIGUOUS | **[VERIFIED]** Phase 2K |
| Validator | `generation_service._render_room` postgen | only `_mean_abs_diff(png, base) < 4.0 → LOW_FIDELITY`; **no furniture detection**. `fidelity_service.calculate_room_fidelity` evaluates the **canonical layout**, not the output pixels. `furniture_object_validation_service` exists but is **audit-only, not called** in the render path | **[VERIFIED]** |
| UI status | `generation_service` | `geometry_faithful` = "img2img render of a validated base (§L) — never merely because Flux returned bytes" → set from **input validity, not output** | **[VERIFIED]** |

## 3. Exact failure point
**The AI image-to-image output stage** (submitted base → raw FAL output). Everything upstream is faithful. The model recomposes/omits furniture **despite explicit prompt prohibitions**, because it has creative freedom with **no structural lock** and the output is **never checked for furniture presence** before being accepted/labeled faithful.

## 4. Answers to the required questions
- **All 5 in base, correctly transformed?** **[VERIFIED] Yes** — 0 transform delta; all visible in the base.
- **2D uids → 3D objects/room traceable?** **[VERIFIED] Yes** — uid carried via `userData.item_id`; each uid in exactly one room (render_input_contract: 22/22, 0 duplicates).
- **What evidence supports 3-preserved/2-ambiguous?** **[VERIFIED]** image inspection of the verified pair (crops/overlay): bed/wardrobe/dressing identifiable; only 4 distinct objects total ⇒ ≥1 side table not distinctly identifiable. (Not a detector count — direct visual + object-count.)
- **Did AI omit, merge, hide-by-perspective, or just make hard to ID?** **[HYPOTHESIS / UNKNOWN]** — recomposition prevents binding; cannot prove which. Count fact: 5→4 distinct objects.
- **Does the prompt prohibit add/delete/merge/move/rotate/resize?** **[VERIFIED] Yes** (L59/62/68 + count lock) — and it was still violated ⇒ prompt text is insufficient.
- **Img2img uses only base PNG + prompt, or structured guidance?** **[VERIFIED] Only base PNG + prompt** (controlnet depth/canny path exists but `FAL_USE_CONTROLNET=false`).
- **Validators auto-run on every output?** **[VERIFIED] No** — only the mean-abs-diff degenerate check runs; `furniture_object_validation_service` is audit-only.
- **Can it detect a missing/duplicated item before marking success?** **[VERIFIED] No.**
- **Does status reflect measured output evidence?** **[VERIFIED] No** — `geometry_faithful` is derived from base validity, not output inspection.

## 5. Prioritized recommendations (smallest safe first)
**P0 — honest status (no FAL cost).** Do not label an output `geometry_faithful` without output evidence. Downgrade to `UNCERTAIN` unless an output furniture check passes. *Files:* `generation_service.py` (postgen status), status/`fidelity` reporting, frontend status display. *Risk:* low. *Acceptance:* an output that drops a canonical item is **never** shown as faithful.

**P1a — run the existing furniture validator on the output (no FAL cost, local compute).** Wire `furniture_object_validation_service` (uses the existing `furniture_detector_hybrid`/OWLv2) into the postgen path as an advisory PASS/UNCERTAIN/FAIL per item, recorded on the generation. *Files:* `generation_service._render_room`, `furniture_object_validation_service`. *Risk:* low-med (detector recall limits → report UNCERTAIN, never false FAIL). *Acceptance:* missing/duplicate items surfaced before success.

**P1b — structured conditioning experiment (FAL cost; separate approval).** Evaluate the **existing** depth/canny path (`FAL_USE_CONTROLNET`) on this persisted base — the only lever likely to actually improve preservation, since the prompt is already maximal. *Files:* `config.py` (flag), `fal_flux_adapter` (already supports it). *Acceptance:* measured furniture-preservation improvement vs the edit baseline on the fixture.

**P1c — base saliency for small items (no FAL).** Make side tables (<0.5% of frame) more distinguishable in the base. *Files:* `RoomScene3D`/`furniture3d`. *Risk:* med (render change). 

**P2 — deterministic compositing / geometry-preserving render (future).** If img2img cannot meet the bar, composite the restyled surfaces onto the deterministic furniture silhouettes. Larger change; design later.

**Not recommended:** strengthen the prompt (already strong, proven insufficient); retrain/replace the model (no evidence of need).

## 6. Regression tests & acceptance
- **Status honesty:** `geometry_faithful` requires output evidence (unit test: no output check ⇒ status not "faithful").
- **Output furniture audit wired:** a fixture output missing an item ⇒ flagged, not marked success.
- **Inputs:** existing `render_input_contract` (18 tests pass) for canonical/room/opening/provenance.
- **Acceptance principle:** all 5 items individually identifiable with intended relative position/orientation; if unprovable, the app must **not** label the output geometry-faithful.

## 7. Files/functions that would change (for the P0/P1a fixes)
- `backend/app/services/generation_service.py` — postgen path: call the output validator; set honest status.
- `backend/app/services/furniture_object_validation_service.py` — invoked as the output gate (exists).
- status/`fidelity_service` reporting + frontend status component — honest PASS/UNCERTAIN/FAIL.

## 8. Open questions / missing evidence
- Mechanism of the side-table loss (omit vs merge vs reposition) — unprovable from one image.
- Whether depth/canny conditioning actually improves preservation for flux-kontext/dev — needs the approved FAL experiment.
- Production generations don't persist the base PNG (F4) — production attempts aren't auditable without a read-only base re-render.

**Approval checkpoint:** stopping here. No files edited, no settings changed, no FAL calls. Awaiting approval before implementing any recommendation (P0 honest-status + P1a output-validator wiring are the smallest, no-FAL starting point).
