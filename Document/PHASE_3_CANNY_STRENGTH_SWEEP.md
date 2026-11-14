# Phase 3 — Bounded Canny Strength Sweep (executed, authorized)

**Result in one line:** Across **6 authorized paid renders** (Living Area + Bedroom 3 × `control_lora_strength` 0.5/0.65/0.8), every output **preserved the canonical inventory, geometry and camera exactly** but **looked like the flat deterministic base — no photorealism at any strength**. The hypothesis that a lower strength restores photorealism is **refuted**. **Strength is not the lever.** Evidence (INFERRED) points to the base render being used as the dominant **init image** as the cause; the next smallest conditioning change is to reduce/disable that init influence while keeping the Canny lock.

**Spend:** owner-authorized **6 renders, $0.48** (2 MP × $0.04/MP each); **6 issued, 6 succeeded, no retries**; cap not exceeded. Provider/model/defaults unchanged (env-only for the run).

---

## 1. Authorization & controls
Owner approved **all 6 renders ($0.48)** after the Step-1 plan. Controls (env-only, production defaults untouched): `FAL_USE_CONTROLNET=true`, `FAL_SINGLE_ATTEMPT=true` (exactly one billed submission per render, no retry), `control_lora_strength` set per render via `FAL_CONTROL_STRENGTH` (adapter clamps [0,2] — all three values supported). Same base render + seed + prompt + dims per room; only strength varied.

## 2. Executed renders — provenance (VERIFIED)
Provider `fal`, model `fal-ai/flux-control-lora-canny`, `conditioning_mode=canny_controlnet`, design version `85759b78…` (v79), all outputs **1216×832** (== capture frame). Full record: `…/scratchpad/canny_sweep_provenance.json`.

| # | room | strength | base sha16 | output sha16 | request id | status |
|---|---|---|---|---|---|---|
| 1 | Living Area | 0.5 | `b3b9315a564d8615` | `dfab2a15f6c8…` | `01a17bcd-c2f9-7e00-823d-85bf9cbd7832` | ok |
| 2 | Living Area | 0.65 | `b3b9315a564d8615` | `4fe1b78e6f72…` | `01a17bd0-6b2a-72c1-a2f0-04a60c292512` | ok |
| 3 | Living Area | 0.8 | `b3b9315a564d8615` | `52c3c55e9849…` | `01a17bd0-a5b8-7ce3-bc62-661aa9867216` | ok |
| 4 | Bedroom 3 | 0.5 | `40ac59845ef052a4` | `65ba692fb383…` | `01a17bd0-e4e0-7c12-9c72-a8b99a2bcbb2` | ok |
| 5 | Bedroom 3 | 0.65 | `40ac59845ef052a4` | `49350a9f624e…` | `01a17bd1-16b4-7b61-9466-fa28a4cf9019` | ok |
| 6 | Bedroom 3 | 0.8 | `40ac59845ef052a4` | `193e4a422b3d…` | `01a17bd1-42af-70d0-9f42-48723b6684de` | ok |

Baseline for comparison (no new cost): edit-path outputs (`174503c2/0.png` Living, `/3.png` Bedroom 3) and the Step-2T Canny @1.0 Living Area (`dc489a8a…`).

## 3. Evaluation — each output vs its canonical + base (human review)
*Detector findings are NOT used (OWLv2 is `NOT_CALIBRATED` and its weights are absent — §6). These are human-reviewed conclusions on the actual images.*

**Living Area** (canonical: 2 Loungers Sofa [L-sectional] + 1 Console):

| strength | missing | extra | identity/type | walls/openings | photorealism | contract verdict |
|---|---|---|---|---|---|---|
| 0.5 | none | none | sectional + console preserved | preserved (same shell/camera) | **none** (flat clay ≈ base) | layout **faithful**, appearance **not improved** |
| 0.65 | none | none | preserved | preserved | **none** | faithful / not improved |
| 0.8 | none | none | preserved | preserved | **none** | faithful / not improved |

**Bedroom 3** (canonical: 1 Bed + 2 Side Table + 1 Dressing Table):

| strength | missing | extra | identity/type | walls/openings | photorealism | contract verdict |
|---|---|---|---|---|---|---|
| 0.5 | none visible | none | base massing preserved | preserved | **none** (flat ≈ base) | faithful / not improved |
| 0.65 | none visible | none | preserved | preserved | **none** | faithful / not improved |
| 0.8 | none visible | none | preserved | preserved | **none** | faithful / not improved |

Position/orientation/exact dimensions: **not independently measurable** from these perspective-free dollhouse renders beyond "visually unchanged from the base" (the Canny lock holds them); marked **not_assessable** for precise metrics. Cropping/occlusion/merging: none observed. **No output violated the canonical contract**, so none is rejected on fidelity — but **none delivered the photorealism that is the point of AI rendering**, so none is acceptable as a final render.

## 4. Finding
Across **both rooms and all three strengths (and the 1.0 baseline)** the Canny output is **essentially the flat base render**: perfect structure/inventory preservation, **zero photorealism gain**. Lowering `control_lora_strength` from 1.0 → 0.5 did **not** restore photorealism. **The strength parameter is not the fidelity↔photorealism lever.**

## 5. Root cause (INFERRED, code-supported) + next smallest change
The Canny path (`_build_control_body`) passes the deterministic base render as **both** the Canny `control_lora_image_url` **and** the init `image_url` (because `FAL_CONTROL_USE_INIT=true` by default). The **init image dominates** the result, so the output is a near-copy of the flat base regardless of `control_lora_strength` (which only governs the edge-lock). This is **INFERRED** from the adapter code + the invariance across strengths — **not** experimentally isolated.
- **Next smallest conditioning change (separately authorized, bounded):** keep the Canny `control_lora` structure lock but **reduce or remove the init-image influence** — set `FAL_CONTROL_USE_INIT=false` (or, if the model exposes one, lower an init/denoise strength) — so the model repaints photorealistic materials/lighting **from the prompt** onto the Canny-locked geometry. Test on the same Living Area + Bedroom 3 bases (≈ 2–4 renders, ≈ $0.16–$0.32). This is the defensible next step toward faithful photorealistic rendering.

## 6. Detector status & limitations (honest)
- **No detector metrics:** OWLv2 weights are **not present locally** (HF cache absent) and must not be downloaded; the detector is **`NOT_CALIBRATED`**. All §3 conclusions are **human review**, not calibrated detection. torch 2.14.0+cpu is installed, so inference could run once weights are authorized.
- **Scope:** 6 renders, 2 rooms, one design version (v79), one seed per room. **Not production-wide.** A visually attractive output is never accepted on appearance alone; here the issue is the opposite (faithful but not photorealistic).

## 7. Tests (offline; before/after)
No production code changed in Phase 3 (configuration/env only). The Phase-2 dimension-correspondence fix (`assess_output_inventory` output-vs-capture guard + tests) was already applied.
```
pytest -q tests/test_output_inventory_assessment.py tests/test_output_fidelity_validation.py
         tests/test_ai_fidelity_conditioning.py tests/test_render_inclusion.py
         tests/test_fal_flux_adapter.py                           → 77 passed, 0 failed (exit 0)
```

## 8. Git / files
Not a git repo → no diff. **No production code changed this phase.** Artifacts: 6 output PNGs + `canny_sweep_provenance.json` in the session scratchpad; this report is the only new project file. Canonical geometry/furniture, provider/model defaults, and the Furniture Library are unchanged; deterministic fallback intact.

## 9. Recommendation & next action
- **Do NOT adopt any swept strength** (0.5/0.65/0.8) — none improved appearance; all equal the flat base, same as 1.0.
- **Next concrete step:** a bounded, separately-authorized experiment varying the **init-image influence** (`FAL_CONTROL_USE_INIT=false` / init-strength) with the Canny lock retained, to test whether photorealism can be recovered while preserving the canonical layout. Keep the deterministic render as the trusted fallback and AI outputs `UNVERIFIED` until a calibrated detector exists.
- **Not claimed:** that furniture fidelity + photorealism are jointly solved — this experiment establishes that *strength alone does not solve it* and identifies the next lever.
