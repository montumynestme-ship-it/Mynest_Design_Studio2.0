# AI Render Fidelity & Output-Quality — Diagnosis (generation `2d40354b`)

**Outcome: no code change — every actionable item is STOP-gated (an open-plan membership product decision, or provider/conditioning tuning that needs paid validation + approval). No confirmable, safely-fixable code defect was found; the gates and statuses are behaving honestly.** Diagnosed the exact latest generation behind the screenshots with real runtime artifacts. **MyNest only — TeleCRM never read/run/edited. No paid calls. No files changed. DB read-only.**

> ⚠️ **Operational risk found:** drive **C: is 100% full (616 MB free)**. The harness/scratchpad and some caches write to C:, and this already caused write errors this session. A full disk can make the server fail to persist outputs/caches and degrade renders. **Recommend freeing C: before the next generation** (HF cache is already redirected to D: per project notes; check `storage/render_cache`, debug_artifacts, and user temp).

Labels: **[VERIFIED]** reproduced from artifacts; **[INFERRED]**; **[UNVERIFIED]/[not_assessable]**.

## Baseline [VERIFIED]
- Dir: `D:\Latest_mynest_design_version\mynest-design-studio` (MyNest); **not a git repo** → no branch/commit/diff; tree unchanged. Session cwd is a TeleCRM git repo — untouched.
- Generation **`2d40354b-edd7-4e58-b984-6567a9cabf57`**, 2026-10-28 15:48. Canonical geometry hash `49f3226afcc32532` (v79 design), style ref `70a288508223f2fb`. Provider **fal**, model **fal-ai/flux-kontext/dev**, `conditioning_mode=edit` (img2img), `FAL_USE_CONTROLNET=false`, guidance/steps = fal defaults (optional envs unset). Base capture 1216×832.

## Room-by-room (from the actual artifacts) [VERIFIED]
| Room | Status | Provider/model | Conditioning | Out dims | Inventory | Geometry status | Note |
|---|---|---|---|---|---|---|---|
| Living Area | success | fal / flux-kontext/dev | edit | 1216×832 | MATCH | UNVERIFIED | genuine fal edit (seed 1444570007) |
| Bedroom 1 | success | fal / flux-kontext/dev | edit | 1344×768 | MATCH | UNVERIFIED | genuine fal edit (seed 1444884194) |
| Bedroom 2 | success | fal / flux-kontext/dev | edit | — | MATCH | UNVERIFIED | genuine fal edit |
| Bedroom 3 | success | fal / flux-kontext/dev | edit | — | MATCH | UNVERIFIED | genuine fal edit |
| Kitchen | **failed** | — (blocked pre-provider) | — | — | **MISMATCH** (missing Chimney) | — | `BASE_INVENTORY_MISMATCH`; provider never called |
| Dining Area | **failed** | — (blocked pre-provider) | — | — | — | — | `BASE_RENDER_WRONG_ROOM` (declared='Kitchen', expected='Dining Area') |

## Section 3 — "isometric" (Living, Bed 2) vs "photoreal" (Bed 1, Bed 3) [VERIFIED: not a path/selection defect]
Checked each hypothesis against `provider_request_metadata.json` / `render_debug.json`:
1. **Same workflow?** Yes — all four are `provider=fal`, `model=fal-ai/flux-kontext/dev`, `conditioning_mode=edit`, same `geometry_hash`, same style ref. ✔
2. **Deterministic preview shown instead of AI?** No evidence — all four are real fal responses (`status=success`, `cache_hit=False`, **distinct seeds**, and an `output_inventory_assessment` was computed on a returned image). Not base-render substitutions. *(I could not byte-diff the output pixels against the base: outputs live in Postgres/`render_cache`, not in `debug_artifacts`; so "output ≠ base" is strongly supported by metadata but the pixels were [not_assessable] offline.)*
3. **Wrong artifact selected?** No per-room path divergence found. ✔
4. **Output actually from the configured provider/model?** Yes (fal / flux-kontext/dev for all). ✔
5. **Params differ?** Only **prompt, seed, and output dims** differ per room; **edit mode has no strength parameter**, and guidance/steps use fal defaults for all. No per-room conditioning difference. ✔
6. **Silent fallback to another path?** None detected. ✔
7. **Stale/mismatched cache image?** `cache_hit=False` for all four. ✔

**Root cause [INFERRED, strongly supported]:** the quality variance is **inherent variability of the img2img EDIT path** (flux-kontext/dev transforms the deterministic isometric base more for some rooms than others, given each room's base content, prompt, and seed). It is **not** a wrong-artifact, wrong-provider, wrong-cache, or different-pipeline defect. Improving realism would require **conditioning/prompt/guidance tuning** (e.g., enabling ControlNet, raising `guidance_scale`, or a stronger photoreal instruction) — each needs **paid generation to validate** and a provider/strategy decision. → **STOP** (no paid calls; not a provable offline code defect; provider/strategy changes need approval).

## Section 4 — fidelity statuses are honest, not defects [VERIFIED]
- `AI geometry: NOT PROVEN` / `furniture: Not Verified` / `geometry: UNVERIFIED`: by design (AIR-01). The **input** geometry is locked (`input_geometry_locked=True`, stable `geometry_hash`), but there is **no calibrated OUTPUT-image detector**, so the system honestly refuses to claim FAITHFUL. Correct — do not relabel.
- `Topology: 5/7 rooms proven`: the scene has **5 CONFIRMED** rooms (Living, Bed 1, Bed 2, Bed 3, Kitchen & Dining Area) + **2 UNCERTAIN** (the "Kitchen" counter twin, the "Bedroom 3" window twin) = 7; 5 proven. Accurate.
- `inventory_status`: MATCH for the four rendered rooms (their base contained the expected furniture). Correct.
- `output_inventory_assessment = NOT_VALIDATABLE (advisory)`: honest — no output detector. Correct.
These statuses correctly separate **input preservation** (provable) from **output fidelity** (genuinely UNVERIFIED). No false-pessimistic status to correct.

## Section 5 — Kitchen & Dining failures (both honest refusals) [VERIFIED]
- **Kitchen → `BASE_INVENTORY_MISMATCH`:** the "Kitchen" section's furniture `[kitchen-base×2, chimney]` is split across the CONFIRMED "Kitchen & Dining Area" (chimney) and the UNCERTAIN "Kitchen" twin (counters); no single base room holds all three → honest refusal before the provider. (Full trace: `reports/KITCHEN_BASE_RENDER_POLICY_C_RESULT.md`.)
- **Dining Area → `BASE_RENDER_WRONG_ROOM`:** the Dining section has no own room (the dining-table lives in the combined "Kitchen & Dining Area"); the base it received was **declared for 'Kitchen'**, so `base_render_service.validate_base_render` correctly rejected it as the wrong room — it did **not** send a mismatched base to fal.
- **Both** are the same **unresolved open-plan Kitchen/Dining membership/merge** issue (`merge_map` empty, REVIEW_REQUIRED). Resolving either by routing a section to a different room = a membership decision → **STOP** (explicit stop condition). The validators are **correctly** rejecting renders that cannot be proven faithful; neither was bypassed.

## Why no code change (stop conditions hit)
- Quality variance → provider/conditioning **tuning** needing **paid validation** + strategy approval. ✗
- Kitchen/Dining → **open-plan membership product decision** (and inventing counter ownership is forbidden). ✗
- Fidelity statuses → already **honest**; relabeling would be **weakening validation**. ✗
No silent substitution, wrong-artifact, or stale-cache defect was found that could be safely corrected offline.

## Tests / validation
No code changed → contract unchanged. Governing behavior is locked by existing suites run green earlier this session: `test_inventory_mismatch_status`, `test_inventory_gate_generate`, `test_containment_sectioning` → **34 passed**. The Dining `BASE_RENDER_WRONG_ROOM` path is covered by `base_render_service.validate_base_render` tests. I did **not** re-run the full suite this cycle (C: at 100% risks spurious I/O failures, and nothing was changed). No test was weakened.

## Invariants [VERIFIED]
Nothing edited → canonical furniture identity/uids/transforms, walls, doors, windows, room boundaries, and the versioned snapshot untouched; `geometry_hash` stable; `validate_scene_2d_to_3d` remains SCENE_FAITHFUL (earlier). Deterministic design remains the trusted, complete fallback.

## Remaining risks / unknowns
- Output pixels were **not** byte-diffed against the base (outputs not in `debug_artifacts`); "AI output ≠ deterministic base" for the four rooms is [INFERRED] from metadata, not pixel-proven offline. A definitive check needs the stored output images (Postgres/`render_cache`) or a fresh render.
- **C: 100% full** may itself cause output/cache write failures on the next run.
- Visual realism is subjective and **UNVERIFIED**; no output fidelity detector exists.

## Next concrete actions (to get a trustworthy, higher-quality render)
1. **Free C: drive** before any new generation (operational blocker).
2. **Owner decision on open-plan Kitchen & Dining membership/merge** — this unblocks BOTH failed sections (Kitchen inventory + Dining base-room). If "merge": composite the combined open-plan base so one base image carries all Kitchen+Dining furniture; then both gates pass naturally, with no furniture moved and no ownership invented. Ship with a v79 regression test; keep the 34 existing tests green.
3. **For realism consistency (needs approval + budget):** a controlled A/B with `FAL_GUIDANCE_SCALE`/`FAL_NUM_INFERENCE_STEPS` set, or ControlNet enabled, on a single authorized paid render — measured against the canonical base — before changing any default. Not done here (no paid authorization).
4. **To pixel-verify** the isometric rooms are genuine AI output (not base), pull the stored outputs from Postgres/`render_cache` and diff against `base_render.png` — safe, offline, once disk space allows.

**Honest note:** no renders were generated and no output pixels were visually compared this cycle; realism remains UNVERIFIED. The diagnosis rests on verified provider/request metadata and the reproduced gate behavior.
