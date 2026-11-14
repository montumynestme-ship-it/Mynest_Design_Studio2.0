# Photorealistic AI Render — Root Cause, Offline Prep & Benchmark (awaiting paid authorization)

**One line:** All safe offline work is done: the current FAL runtime and fixtures are verified from source, the realism-vs-fidelity root cause is confirmed, **no code change was justified** (the live prompt already single-sources the manifest; the only adapter-supported lever is env-only `guidance_scale`), and an **executable, guarded paired benchmark is prepared**. The actual AI-render objective is **incomplete by design** — it needs one paid run, which requires explicit authorization (cost below). **No paid call was made.**

---

## 1. Verified baseline & current configuration (from source + `backend/.env`, this cycle)
- `DEFAULT_AI_PROVIDER=fal`; `FAL_IMAGE_MODEL=fal-ai/flux-kontext/dev`; `FAL_USE_CONTROLNET=false` ⇒ **edit path** (base PNG as `image_url`, **no structural geometry lock**); `FAL_CONTROL_USE_INIT=true`; `FAL_SINGLE_ATTEMPT=false` (⇒ the adapter may retry → >1 billed call/render unless set true); `FAL_GUIDANCE_SCALE`/`FAL_NUM_INFERENCE_STEPS` unset (adapter defaults 3.5 / 28); `AI_DEMO_MODE` off; **FAL key present** (benchmark is runnable once authorized).
- **FAL request contract (edit path, verified in `_build_body`):** `{prompt, image_url, num_images, output_format, seed?, guidance_scale?, num_inference_steps?}` — a **single combined `prompt`** built by `_build_fal_edit_prompt(request.prompt)`; **no separate system-prompt field**. The only isolated, adapter-supported knobs are `guidance_scale` (prompt adherence — NOT a geometry lock) and `num_inference_steps`.
- **Fixtures intact & executable:** `storage/debug_artifacts/174503c2-…/` has Living Area (base sha16 `b3b9315a564d8615`) and Bedroom 3 (`40ac59845ef052a4`), each with `prompt.txt`, `base_render.png`, `base_render_meta.json`, `furniture_manifest.json` — the exact Phase 3/4 provenance (v79). 176 base renders exist on disk overall.

## 2. Confirmed root cause of the realism↔fidelity trade-off (+ hypotheses)
- **CONFIRMED (prior phases, re-verified from config this cycle):** the active **edit path has no structural conditioning** — it is photorealistic but free to drop/add/alter furniture. The alternative **Canny path** (`FAL_USE_CONTROLNET=true`) preserves structure but renders **flat/clay** (Phase 3 strength sweep) and, with the init removed, produces a **wireframe artifact** (Phase 4). `flux-control-lora-canny` has **no weak-init/denoise knob** (Phase 5). So the trade-off is a **provider/model + conditioning limitation**, not a code defect, and **prompt length cannot resolve it**.
- **HYPOTHESIS (untested, cheap, adapter-supported):** raising `guidance_scale` on the edit path increases prompt adherence and *may* reduce missing/extra furniture at some realism cost. This is the single controlled variable for the benchmark — labeled a hypothesis, not a fix.
- **Rejected as causes:** manifest/dictionary/prompt inconsistency (single-sourced; tested), base-render identity mismatch (version/room-bound; gated), and "the prompt enforces geometry" (it does not — guidance only).

## 3. Change decision this cycle: NONE (evidence-backed)
No code or default change was justified. The live prompt already carries the manifest-derived inventory + `_EDIT_PREAMBLE` preservation (single source); injecting the Markdown system prompt as a second block would **duplicate instructions** and exceed the condenser budget — the directive forbids redundant blocks. The system prompt stays **provenance-only** (honest; it does not influence the live request). The benchmark's candidate arm is therefore an **env-only `guidance_scale`** variation — no code, no default, no provider/model change.

## 4. Prepared benchmark (executable, guarded — NOT run)
Script: `…/scratchpad/run_photoreal_benchmark.py`. It **aborts** unless `RUN_FAL_BENCHMARK=1` **and** `FAL_SINGLE_ATTEMPT=true`, refuses the Canny path, and hard-caps at `MAX_CALLS=4`. Verified this cycle: with no auth env it exits immediately (no fal call).
- **Paired, one controlled variable (`guidance_scale`):** per room, **BASELINE** (guidance unset → model default) vs **CANDIDATE** (`guidance_scale=4.5`). Everything else identical: same base render (sha asserted), same `prompt.txt`, same seed, same dims (1216×832), edit path.
- **Rooms:** Living Area (seed 1552711625) + Bedroom 3 (seed 1553235270), v79 fixture.
- **Renders:** 2 rooms × 2 arms = **4**, `FAL_SINGLE_ATTEMPT=true` (one billed submission each, no retry).
- **Per-output provenance recorded:** room, arm, guidance, base sha16, output sha, dims, seed, model, conditioning_mode, request id, effective prompt, file path → `photoreal_benchmark_provenance.json` + `bench_<room>_<arm>.png`.

## 5. Acceptance criteria — defined BEFORE any result
Photorealism and geometry fidelity are judged **separately** (human review; detector stays `NOT_CALIBRATED`, advisory):
- **Geometry/inventory (gating):** every canonical item present exactly once; no extra/duplicate/substituted/invented furniture; identity/type preserved; room assignment preserved; walls/doors/windows preserved with no invented openings; camera comparable to the base; **no wireframe artifact**.
- **Photorealism (quality):** materials/lighting/shadows/finishes meaningfully more realistic than the flat base.
- **Verdict rule:** a render passes only if **all** geometry/inventory criteria hold **AND** photorealism improves. **A more realistic but geometrically wrong output is a FAILED candidate.** No output is `FAITHFUL` without this output-level review; failures keep the deterministic render as the trusted result.

## 6. Cost & the exact authorization required
- **Pricing (verified, ESTIMATE):** fal $0.04/MP; 1216×832 ≈ 2 MP ⇒ **$0.08/render**. **4 renders ⇒ $0.32** (hard cap). A 2-render baseline-only arm ⇒ **$0.16**. Billed on success only.
- **To proceed I need explicit approval of:** (1) the render count + **hard max cost** (4 / $0.32, or 2 / $0.16), and (2) running real paid fal calls env-only (`RUN_FAL_BENCHMARK=1 FAL_SINGLE_ATTEMPT=true`) with **no** provider/model/Canny/init default or production change. Storage/assessment/fallback are as in §4–§5. Nothing is submitted until this is granted.

## 7. Tests (this cycle; no code changed)
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q \
  tests/test_furniture_dictionary.py tests/test_acceptance_fallback_integration.py \
  tests/test_manifest_prompt_output_pipeline.py tests/test_furniture_manifest.py \
  tests/test_ai_furniture_fidelity_reporting.py tests/test_fal_flux_adapter.py
→ 90 passed   (exit 0; only pre-existing Pillow `getdata` deprecation warnings)
```
No production code changed this cycle, so the broad **338-passing** offline suite from the prior cycle is unchanged. Benchmark guard verified: aborts with no fal call absent authorization.

## 8. Files changed & git
- **New (scratchpad, not production):** `run_photoreal_benchmark.py` (guarded benchmark runner).
- **New (project root):** this report. No source/test/config/default change this cycle.
- Not a git repository → no diff/commit. (The session-header branch belongs to the separate TeleCRM working directory.)

## 9. Separate findings, limitations & next action
- **Geometry fidelity:** unproven at the output level until the benchmark runs; the edit path cannot *guarantee* it.
- **Photorealism:** the edit path is the realistic option; the structural-lock alternative is flat/artifacted (prior evidence).
- **Detector:** uncalibrated — output-level missing/extra stays advisory/`NOT_VALIDATABLE`.
- **Next concrete action:** obtain §6 authorization, run the 4-render paired benchmark through the existing pipeline, inspect each output against its canonical design + base render (geometry vs photorealism separately), and report actual artifacts. If the trade-off persists, the evidence-backed alternative is a structural-conditioning change (clean edge/line-art or depth control) — a separate, larger, authorization-gated effort, not prompt tuning.

**The actual AI-render objective is incomplete:** no AI image has been generated or inspected in this cycle, and none will be until the paid run is authorized.
