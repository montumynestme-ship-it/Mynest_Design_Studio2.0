# Phase 4C — Step 2S: Permanent Fix for Missing/Extra Furniture — Implementation + Honest Status

**Authorization honored:** offline investigation, code, tests only. **No paid generation, no live AI calls, no provider/default change, no shared-DB writes, no production changes.** App is not a git repo (only `floorplan-parser/.git`) → no `git diff`.

> **Headline honesty:** the **deterministic-side** causes of missing/extra furniture are fixed and test-verified (sectioning, render-inclusion, inventory accounting, honest validation). The **AI-output** cause — the fal `flux-kontext/dev` image-EDIT model reinterpreting the scene — is **not** fixable by prompt or scene changes; it requires **structural conditioning (Canny)**, which is a production-config + paid-validation **product decision (blocked)**. Per the Definition of Done, with **no new output-level evidence**, I do **not** claim the visual defect is fixed.

---

## 1. Confirmed root causes (evidence; reproduced against current source)
| cause | stage | evidence | status |
|---|---|---|---|
| **Kitchen base units out-of-polygon → UNCERTAIN twin → omitted from the confirmed base** | reconstruction/scene | 2K/2M traces; `inventory_status=MISMATCH (missing Chimney/Kitchen Base)` | **FIXED** (render-inclusion, 2M/2N.2) + honest gate |
| **Bedroom wardrobe mis-sectioned (proximity vs containment)** | `group_by_room` sectioning | 2P: wardrobe geometrically in Bedroom 3 but sectioned to Bedroom 1 | **FIXED** (containment-aware sectioning, 2P) |
| **Silent-drop / duplicate / unmapped accounting gaps** | inventory contract | 2O reconciliation (22/22 exactly-once) | **FIXED** (reconciliation diagnostic, 2O) |
| **AI output adds furniture/appliances/decor; reinterprets rooms** | provider/model + conditioning | screenshots (`Latest_Main_2.0.zip`): Living adds pouf/coffee table/decor; **Bedroom 2 adds TV/ottoman/sofa/coffee table**; v79 Kitchen = full invented kitchen | **ROOT = missing structural conditioning** (edit path, `FAL_USE_CONTROLNET=false`). Fix is a product decision (§6). |
| **Prompt is already strong** — not the cause | prompt builder | `fal_flux_adapter._build_fal_edit_prompt`: inventory lead, structural preamble, negatives last, never truncates mandatory, theme can't override | **CONFIRMED adequate** — tightened only for decor (§4) |
| **Output never checked (input-only validation)** | validation | `assess_ai_render(output_verified=False)` → always UNVERIFIED; honest, no false success | **Honest**; detector = blocked (needs corpus, §6) |

Rejected as primary causes (evidence): incorrect provider/model selection (configured, not substituted); control-image misrouting (edit path has no control image *by design*; Canny body wiring is correct — tested); prompt truncation dropping inventory (mandatory reserved first, fails safe); false-positive FAITHFUL (cannot occur — `output_verified=False`, plus the 2R guard).

## 2. What this step (2S) implemented — smallest evidence-supported offline changes
### Fix A — Forbid invented **decor/accessories**, not just "furniture" (prompt)
Evidence: even on a **faithful base** (Living Area, Bedroom 1) the renders added decor (plants, art, vases, a pouf). The contract permits improving *existing* decor's appearance but not inventing new objects. Tightened the four prohibition sites in `fal_flux_adapter.py`:
- `_EDIT_PREAMBLE`: "…do NOT invent furniture, **appliances, or decor/accessories** that are not already present."
- `_FAL_NEGATIVES`: "…do NOT invent furniture, **appliances, or decor/accessories (plants, artwork, rugs, cushions, curtains, mirrors, lamps, vases, ornaments)** …"
- Inventory lead: "render every one of these items **exactly once** and nothing else — no extra, duplicate, missing, **substituted, or invented furniture, appliances, or decor**."
- `_FAL_STYLE_PREFIX`: styling applies to **EXISTING** objects/surfaces only and "**introduces no new object**."
(Additions deliberately kept concise so the mandatory sections never crowd the user theme out of the budget — verified theme still fits, §3.)

### Fix B — Persist the **exact effective prompt** sent to the provider (provenance)
Evidence: only the room prompt (`prompt.txt`) + a prompt hash were stored; the *assembled/trimmed* text actually sent to fal was not auditable. Added:
- `fal_flux_adapter`: `self.last_effective_prompt = body.get("prompt")` (the real request-body prompt).
- `generation_service._save_debug_artifacts`: writes `effective_prompt.txt` when provided; call site passes `adapter.last_effective_prompt`. (No credentials in prompt text.)

**Important:** Fix A is **supplementary** — a stronger prompt does **not** guarantee object preservation on an edit model. It is expected to reduce decor additions marginally at best.

### Already implemented in prior steps (confirmed intact this step)
Containment sectioning (2P), render-inclusion + floor patch (2M/2N.2), inventory reconciliation (2O), conditioning-aware fidelity guard — "no geometry-FAITHFUL without structural conditioning" — + `conditioning_mode` provenance (2R). Honest statuses (Not Verified / NOT PROVEN / Incomplete Generation) and the deterministic fallback are preserved.

## 3. Tests — commands & results (offline; no live generation / shared-DB writes)
```
pytest -q tests/test_prompt_preservation.py                                   → 4 passed
pytest -q test_prompt_preservation test_ai_fidelity_conditioning test_fal_flux_adapter
         test_containment_sectioning test_render_inclusion test_inventory_reconciliation
         test_dynamic_rooms test_kitchen_scene_inventory test_base_render_gate
         test_furniture_manifest test_prompt_geometry                          → 119 passed, 0 failed (exit 0)
imports (generation / fal adapter / validation)                               → OK
```
New `test_prompt_preservation.py` locks: inventory leads with "exactly once … no extra/duplicate/missing/substituted/invented furniture, appliances, or decor"; decor prohibition present in preamble+negatives; theme is styling-only and the **negatives remain last** (theme can't override); mandatory constraints **fail safe** on overflow (never dropped); a long theme is trimmed while inventory+negatives survive. Existing `test_fal_flux_adapter.py` (48) stays green — no contract regression. Mapping to the required test matrix: items 1–7, 12 are covered by these + 2O/2P/2M tests; items 8–11 by the 2R conditioning/fallback guards.

## 4. Fixes implemented vs recommendations still unimplemented
**Implemented (offline, this step + prior steps):** decor prohibition; effective-prompt persistence; containment sectioning; render-inclusion; inventory reconciliation; conditioning-aware fidelity guard; conditioning provenance.
**Not implemented (blocked — require authorization):**
- **Structural conditioning (the actual visual fix)** — production-config + paid validation (§6).
- **Output-level furniture detector** — needs a labelled calibration corpus (§6).
- **Enabling a provider default / new capability** — explicitly out of scope.

## 5. Actual renders compared
No new renders were generated (no paid calls). The only output evidence is the **prior** `Latest_Main_2.0.zip` screenshots (documented in `AI_RENDER_LATEST_OUTPUT_INVESTIGATION.md`) and the v79 fal Kitchen output `174503c2` (Step 2Q). **Before/after of the decor-prohibition change cannot be measured without an authorized generation** — so no before/after furniture-count claim is made.

## 6. Prepared (blocked) work — exact bounded experiment + corpus
**A. Structural-conditioning A/B (the fix for extra/altered furniture) — needs authorization + funding:**
- Settings for the run only (no production default change): `FAL_USE_CONTROLNET=true`, `FAL_SINGLE_ATTEMPT=true` (one billed submission), model `fal-ai/flux-control-lora-canny`; base `image_url`/`control_lora_image_url` = a **faithful-base** room's deterministic `base_render.png` (e.g. Living Area), same seed as the current edit output.
- **Cost estimate:** fal Canny ≈ **$0.04/MP**; 1216×832 ≈ 1.01 MP → billed 2 MP → **≈ $0.08 for one image** (≤ a $0.15 cap).
- **Acceptance:** the Canny output shows **zero added furniture/appliances/decor** and **preserved object count** vs the base, judged on the actual image, and is at least as faithful as the edit-path output for the same room/seed. Only then consider changing the default.
**B. Output-level validation corpus (to ever reach FAITHFUL):** assemble ≥ N labelled triples `(base_render, AI_output, canonical_inventory)` spanning rooms/designs with human object-presence/count labels; calibrate the existing detector (`furniture_detection_service`/`vision_validation_service`) to measured precision/recall before wiring `output_verified`. Until then, outputs stay **UNVERIFIED** (never FAITHFUL).

## 7. Remaining risks & blockers
- **Primary blocker:** the extra/altered-furniture defect is intrinsic to the non-structural edit path; only structural conditioning (§6A) addresses it — **paid + config authorization required**.
- Decor-prohibition prompt change is **unvalidated on real output** (no generation run) — may help marginally.
- Output-level fidelity remains **UNVERIFIED** (no calibrated detector).
- `Latest_Main_2.0.zip` Bedroom 3 showed a deterministic base in the "photorealistic" pane — whether that room's AI render failed (fallback) or the UI captured the base is **indeterminate**; flagged for a provenance check (not reproduced in code this step).

## 8. Git / working-tree / files changed
Not a git repository → no diff. **Changed this step:**
- `backend/app/services/ai/fal_flux_adapter.py` — decor/accessory prohibition (preamble, negatives, inventory lead, style prefix); `last_effective_prompt` exposure.
- `backend/app/services/generation_service.py` — persist `effective_prompt.txt` (param + write + call site).
- `backend/tests/test_prompt_preservation.py` — new (4 tests).
Prior steps' files (`prompt_service.py`, `scene_service.py`, `room_membership_service.py`, `validation_service.py`, `furniture_manifest.py`, `inventory_reconciliation_service.py`, frontend `RoomScene3D.tsx`/`RenderRoomControl.tsx`/etc.) are intact. No provider defaults, APIs, canonical data, geometry, or transforms changed.

## 9. Next concrete action to demonstrate reliable inventory preservation
**Authorize and run the single Canny A/B (§6A)** on a faithful-base room, then inspect the actual image for added/missing furniture vs the base. That is the only step that can produce the output-level evidence required to declare the visual defect fixed. In parallel (offline), begin the §6B labelled corpus so a real FAITHFUL status becomes possible.

**Definition-of-Done status:** deterministic inventory integrity — **met & tested**; honest unverified-status + fallback accuracy — **met**; prompt hardened — **met**; **controlled visual proof that missing/extra furniture decreased — NOT met (blocked on authorized generation).** Not claiming overall success.
