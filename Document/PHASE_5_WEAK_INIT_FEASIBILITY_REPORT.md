# Phase 5 — Weak-Init Feasibility Audit (preparation only)

**Verdict: a weak (low-strength) init-image is NOT feasible on `fal-ai/flux-control-lora-canny`.** The provider contract (verified against fal's own API schema) exposes **no** init-image strength / denoise / influence parameter: `image_url` (the img2img init) is **binary** — present or absent — with a fixed, model-internal influence; the only strength control is `control_lora_strength`, which governs the **Canny control image**, not the init. Therefore the Phase-4 "weak-init" idea cannot be realised **by env config or by a code change** on this model. No paid request is recommended. **Stop condition met** (the parameter does not exist); the smallest alternative investigation is clean edge/line-art or depth conditioning — scoped below, **not implemented**.

*This was an offline audit: no paid requests, no provider probes, no code/default/canonical changes. Nothing was generated.*

---

## 1. Files & configuration inspected
- `backend/app/services/ai/fal_flux_adapter.py` — `_build_control_body` (Canny path) and `_build_body` (edit path).
- `backend/app/core/config.py` — all `FAL_*` parameters.
- Prior reports: `PHASE_3_CANNY_STRENGTH_SWEEP.md`, `PHASE_4_INIT_IMAGE_EXPERIMENT.md` (treated as reported evidence, re-verified below).
- **Authoritative provider schema:** fal's API page for `fal-ai/flux-control-lora-canny` (read-only web fetch; no charge).

## 2. Verified init-image & Canny parameter semantics
**From the adapter (`_build_control_body`) — the exact Canny-path payload:**
`prompt`, `control_lora_image_url` (= base render → Canny), `control_lora_strength` (= `FAL_CONTROL_STRENGTH`, clamped [0,2], **applies to the Canny control**), `num_images`, `output_format`, **`image_url` (= the img2img init) sent ONLY when `FAL_CONTROL_USE_INIT=true`**, `image_size` (pinned to base dims), `seed`, `guidance_scale` (= `FAL_GUIDANCE_SCALE`), `num_inference_steps` (= `FAL_NUM_INFERENCE_STEPS`). **No init-strength/denoise key is constructed.**

**From the fal API schema (VERIFIED):** inputs are `prompt` (req), `image_url` ("image to use for image-to-image generation" — **no influence/strength param**), `image_size` (default landscape_4_3), `num_inference_steps` (default **28**), `seed`, `loras`, `guidance_scale` (default **3.5**), `sync_mode`, `num_images` (1), `enable_safety_checker` (true), `output_format` (default jpeg), `control_lora_image_url` (req), `control_lora_strength` (default **1**, applies to the control image), `preprocess_depth` (default true). **There is NO `strength` / `image_strength` / `denoise` / init-influence parameter.**

**Distinction (task point 5, VERIFIED):** `control_lora_strength` (Canny control) and the init `image_url` are **separate** concepts; the init has **no** strength control of its own. They are not interchangeable.

## 3. Is a weak-init experiment possible with env-only config?
**No — and not by code either.** The model does not accept any init-influence parameter, so:
- There is no `FAL_*` env var that could weaken the init (the adapter has only the binary `FAL_CONTROL_USE_INIT`).
- Even adding a body field in the adapter would be rejected/ignored by the provider — the parameter does not exist in its contract.
Env-configurable knobs that **do** exist (`FAL_GUIDANCE_SCALE`, `FAL_NUM_INFERENCE_STEPS`, `FAL_CONTROL_STRENGTH`) control prompt adherence, step count, and **Canny** strength respectively — **none controls init-image influence**, so none can isolate the weak-init hypothesis.

## 4. Unsupported assumptions / missing provider evidence
- **Resolved:** Phase 4's proposed next step ("verify whether the model exposes a low init/denoise strength") is **answered — it does not.**
- **Missing evidence:** fal's page does **not** state the *magnitude* of the init `image_url`'s influence (it is fixed and undocumented), so the binary init cannot be reasoned about quantitatively. This is a documentation gap, but it does not change the verdict (no knob exists).
- `preprocess_depth` (default true) and `loras` exist but neither is an init-strength control; `preprocess_depth` concerns control-image preprocessing, not the init.

## 5. Proposed experiment matrix
**Weak-init: NOT RECOMMENDED / NOT POSSIBLE** — the required parameter does not exist, so there is no value to sweep and no paid experiment to authorize here.

**Smallest alternative investigation (offline first; NOT implemented in this audit):** the Phase-4 failure was that the **clay base render is a poor Canny source** (its edges rendered as a literal wireframe when the init was removed). The next evidence-supported directions, in increasing scope:
| Option | What to try | Scope | Est. cost (label: ESTIMATE, if later run) |
|---|---|---|---|
| A. Clean line-art / edge control | Feed a clean edge/line map (walls + furniture outlines) as `control_lora_image_url` instead of the clay render, init off | Code/preprocessing change (generate the edge map); not env-only | ~2 renders × $0.08 = **$0.16 (est.)** once built + authorized |
| B. Depth conditioning | Use a depth map + the model's `preprocess_depth`/a depth-control LoRA | Larger; may need a different control input or model capability (model replacement is prohibited) | TBD |
| C. Guidance/steps tuning (init on) | With init ON, raise `guidance_scale` / `num_inference_steps` to see if materials gain realism without flattening | **Env-only**, no code change | ~2–4 renders × $0.08 = **$0.16–$0.32 (est.)** |
**Recommended first:** Option **C** is the only env-only, no-code option and is the cheapest to test whether realism can be nudged with the init retained (keeping geometry). Option **A** is the most promising for the root cause but needs a small, separately-scoped preprocessing change (clean edge map) — **do not implement during this audit**.

## 6. Required owner authorization before any paid execution
No paid run is proposed by this audit. **Any** of the options above requires: (1) explicit approval of the exact request count + max cost, (2) for Options A/B, prior approval of the code/preprocessing change (out of this audit's scope). Pricing basis (verified earlier): $0.04/MP → 1216×832 = 2 MP → $0.08/render.

## 7. Validation criteria (for any future authorized render)
Accept a render only if **all** hold (human review + the advisory assessment; detector remains `NOT_CALIBRATED`):
- **Furniture inventory:** every canonical item present exactly once; **no** extra/duplicated/invented furniture or appliances.
- **Object identity/type:** each item's type preserved (no bed↔sofa swaps, etc.).
- **Placement/orientation/dimensions/room:** visibly consistent with the base (exact metrics `not_assessable` without a calibrated detector).
- **Room structure & openings:** walls, doors, windows, boundaries preserved; **no** invented openings; **no** wireframe/edge artifacts.
- **Camera comparability:** same viewpoint/composition as the base (reject if re-framed).
- **Visual quality:** materials/lighting/texture **meaningfully more photorealistic** than the flat base.
A render that is attractive but violates any geometry/inventory criterion is **rejected**.

## 8. Tests run
**None** — this audit made **no code, config, test, or data changes**, so the existing suite is unaffected and was not re-run. (Prior phases: the offline suite was green — 68 passed in Phase 4.)

## 9. Remaining risks & next action
- **Risk:** the current Canny-on-clay-render approach has a fundamental input mismatch (the deterministic clay massing is not clean line-art), which produced the Phase-4 wireframe artifact when the init was removed. The binary init masks this but flattens materials. There is no middle setting on this model.
- **Next action:** scope **Option A** (clean edge/line-art control input) as a small, separately-approved preprocessing change, and/or run **Option C** (env-only guidance/steps tuning with init on) as a cheap bounded check — both with explicit cost authorization. Keep the deterministic render as the trusted fallback; AI outputs remain `UNVERIFIED`.

**Success of this phase = a decision-ready verdict, not a render:** weak-init is **verified infeasible** on this model; the overall photorealistic-render objective remains **incomplete** until an output passes the canonical contract **and** shows meaningful visual improvement.
