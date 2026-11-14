# Phase 4C — Step 2R: AI-Fidelity Root Cause + Minimal Offline Repair

**Authorization honored:** offline investigation, code, tests only. **No paid calls, no live generation, no shared-DB writes, no production/default changes.** (DB was only READ to identify the failed generation.)

---

## 1. Confirmed root cause: **#2 — missing structural conditioning** (edit path by default)
Traced the failed generation `174503c2` (Kitchen) end to end against actual source + its persisted request:
- **Runtime config** (`app/core/config.py`): `FAL_IMAGE_MODEL=fal-ai/flux-kontext/dev` (an image-**EDIT** model), **`FAL_USE_CONTROLNET=false` (default)**, `FAL_CONTROL_MODEL=fal-ai/flux-control-lora-canny` (the structural model, used only when the flag is on). `DEFAULT_AI_PROVIDER=nvidia`; the run explicitly used `provider=fal`.
- **Adapter dispatch** (`fal_flux_adapter.generate`, line ~428): `use_controlnet = bool(request.control_image is not None and FAL_USE_CONTROLNET)` → with the default flag off, `use_controlnet=False` → the **edit body** `{"prompt", "image_url"}` is sent (`conditioning_mode="edit"`), i.e. the base render is a *loose edit reference*, **not** a structural lock. The Canny structural path (`_build_control_body` → `control_lora_image_url`, model `flux-control-lora-canny`) exists in code but was **inactive**.
- **Persisted request provenance** (`…/room_1_Kitchen/provider_request_metadata.json`): `provider=fal, model=fal-ai/flux-kontext/dev, prompt_length=12014, geometry_status=UNVERIFIED, inventory_status=MISMATCH`. The huge preservation prompt could not compensate — an edit model reinterprets freely.
- **Result (verified in 2Q):** base render = 2 kitchen-base boxes; AI output = a fully invented stock kitchen.

**Classification of the six candidates:**
1. **Incorrect provider/model selection — NO.** `flux-kontext/dev` is the configured `FAL_IMAGE_MODEL`, deliberately selected via `provider=fal`; **not silently substituted** (request/provenance confirm the configured model).
2. **Unsupported/missing structural conditioning — YES (primary).** `FAL_USE_CONTROLNET=false` → edit path, no geometry lock. The documented depth/Canny pipeline is OFF at runtime.
3. **Control-image wiring/order — NO.** On the edit path there is intentionally no control image; the Canny body wiring (`control_lora_image_url`) is correct when enabled (test added).
4. **Inadequate prompt/inventory — NO.** The prompt was 12k chars with full preservation constraints and the manifest was canonical-derived; stronger prompts cannot fix a non-structural path (not claimed).
5. **Intrinsic model limitation — CONTRIBUTING.** `flux-kontext/dev` in edit mode does not preserve exact furniture without a structural lock.
6. **Inadequate output validation — NO (working correctly).** Provenance honestly recorded `geometry_status=UNVERIFIED` (never FAITHFUL) and `inventory_status=MISMATCH`; `assess_ai_render` only reports FAITHFUL when `output_verified=True`, and the sole caller passes `False`. **No false success.**

**Earliest confirmed defect:** none in dispatch/adapter/provenance — all behave as designed and report honestly. The hallucination is the expected consequence of the **configured edit path with structural conditioning disabled** — a configuration/product decision, not a code bug.

## 2. The actual fix is a product decision → STOP (dependency stated)
Preserving furniture requires **enabling structural conditioning** (`FAL_USE_CONTROLNET=true` → Canny Control-LoRA geometry lock) **and** validating it with a real generation. That is a **production setting change + a paid generation**, both outside this sprint's authorization (and the Canny model's fal entitlement was previously flagged). **Stopped that operation.** Minimum dependency to proceed: authorization for (a) the config change and (b) one benchmarked paid generation on an isolated/non-shared path.

## 3. Smallest supported offline changes implemented (no defaults changed, backward compatible)
1. **`app/services/validation_service.py` — capability guard.** `assess_ai_render(..., structural_conditioning: bool | None = None)`: an output produced **without** structural conditioning (`False` → edit/base path) can **never** be reported geometry-FAITHFUL — it is at most UNVERIFIED, even if an output check later sets `output_verified=True`. `None` (unknown/legacy) preserves prior behavior. Adds `structural_conditioning` to the result and a precise reason. (Directly satisfies Stage-4: "unsupported/missing conditioning cannot be reported as geometry-verified.")
2. **`app/services/ai/fal_flux_adapter.py` — honest per-generate signal.** Exposes `self.last_conditioning_mode` ("edit" | "base" | "canny_controlnet") set in `generate()` from the actual path taken.
3. **`app/services/generation_service.py` — wire + record.** Reads `adapter.last_conditioning_mode`, derives `structural_conditioning` (only `canny_controlnet` is a lock), passes it to `assess_ai_render`, and records `conditioning_mode` in per-render provenance so the edit-path failure class is **diagnosable from the artifacts** (it was previously absent).
4. **`tests/test_ai_fidelity_conditioning.py`** — new (9 tests).

**No behavior regression:** `output_verified` is always `False` in production, so `geometry_status` stays `UNVERIFIED` exactly as before; the guard only forecloses a *future* false-FAITHFUL on the edit path. No new dependency, no provider/model change, no production setting touched.

## 4. Tests — commands, exit codes, counts (offline; no shared-DB/live generation)
```
pytest -q tests/test_ai_fidelity_conditioning.py                      → 9 passed (exit 0)
pytest -q <ai_fidelity_conditioning + containment + render_inclusion +
          inventory_reconciliation + dynamic_rooms + room_assignment +
          kitchen_scene_inventory + room_membership + authoritative_merge +
          prompt_geometry + furniture_inventory_validation +
          base_render_gate + furniture_manifest>                       → 149 passed, 0 failed (exit 0)
imports (generation / validation / fal adapter)                        → OK
```
Coverage (Stage 4): configured model ↔ adapter ↔ request schema (edit→`image_url` / canny→`control_lora_image_url`); control image to the structural stage; **no FAITHFUL without structural conditioning**; legacy (`None`) backward compatible; provider/no-base failure → `FAIL` (fails safe, no false success). Inventory/room-label-from-canonical and design-version/room binding remain covered by `test_render_inclusion` (v79) and the Step-2Q validation.

## 5. Before/after request construction (secrets redacted)
| | BEFORE (failed gen 174503c2, as run) | AFTER enabling structural conditioning (NOT executed — product decision) |
|---|---|---|
| provider / model | `fal` / `fal-ai/flux-kontext/dev` | `fal` / `fal-ai/flux-control-lora-canny` |
| `FAL_USE_CONTROLNET` | `false` | `true` |
| conditioning_mode | **`edit`** (no lock) | `canny_controlnet` (structural lock) |
| body keys | `{prompt, image_url}` | `{prompt, control_lora_image_url, image_url?, …}` |
| geometry_status reportable | UNVERIFIED (correct) | UNVERIFIED until an output check confirms, then FAITHFUL permitted |
(Authorization header `Key <FAL_KEY>` redacted; no key read or logged.)

## 6. Unresolved provider/model limitation
`flux-kontext/dev` on the edit path does not preserve furniture; the supported geometry-lock is the Canny Control-LoRA path, which is **disabled by default** and requires a config change + paid validation (and fal entitlement). Until a **separately authorized benchmark** demonstrates improvement, the real output `174503c2` stays classified as an **observed AI-fidelity FAILURE**; the deterministic render remains the trusted fallback and outputs remain honestly `UNVERIFIED`.

## 7. Confirmations
- **No paid API calls / no live generation.** **No shared-database writes** (reads only, to identify the failed generation). **No destructive cleanup**; the 32 mock/tracking records untouched.
- **No provider defaults, APIs, canonical data, geometry, or transforms changed.** All changes additive and backward compatible.
- **Not claiming AI visual fidelity is fixed** — offline tests lock honesty/observability and the capability guard; they do not improve the rendered output.

## 8. Files changed / git
App not under git (only `floorplan-parser/.git`) → no `git diff`. Changed: `validation_service.py`, `ai/fal_flux_adapter.py`, `generation_service.py`, `tests/test_ai_fidelity_conditioning.py`, + this report.

## 9. Remaining defects, blockers, next action
- **Blocker (the real fix):** enable structural conditioning (`FAL_USE_CONTROLNET=true`) + one **authorized** benchmarked generation on a non-shared path to confirm furniture preservation. Needs: production-config authorization + paid-call authorization + fal Canny entitlement.
- **Secondary:** an output-level furniture detector (to ever reach `FAITHFUL`) remains the blocked calibration/corpus work.
- **Next concrete action:** obtain authorization for the single Canny A/B benchmark (the harness for this was prepared in an earlier step), compare furniture preservation edit vs canny on one Kitchen render, and only then consider changing the default.
