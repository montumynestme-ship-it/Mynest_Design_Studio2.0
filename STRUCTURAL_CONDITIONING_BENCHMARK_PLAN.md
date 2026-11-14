# Structural Conditioning — Offline Preflight & One-Room A/B(C) Benchmark Plan

**Status:** `OFFLINE_PREFLIGHT_VERIFIED` · `BENCHMARK_PREPARED` · `BEDROOM1_EXECUTED (2026-11-03)` · `OPEN_PLAN_FIXTURE_CAPTURED (2026-11-04)` · `OPEN_PLAN_RUN_NOT_AUTHORIZED` — see §11 (Bedroom 1 result) and §12 (open-plan K&D Arm-C fixture + prepared one-call run).

This plan prepares a bounded, reproducible one-room benchmark that distinguishes *base-only / image-edit*
from *actual Canny Control-LoRA structural conditioning*, and separates **base-as-control** (Arm B) from
**perspective-structural-as-control** (Arm C). **No fal.ai/NVIDIA/paid call has been made.** Nothing is
submitted until the owner grants the §8 authorization.

This is an offline integration/benchmark-prep milestone. It does **not** demonstrate AI-render fidelity.

---

## 1. Verified request path (independently traced from source)

`DesignStudio.handleGenerate` (`frontend/src/pages/DesignStudio.tsx`)
→ base capture `captureBaseRenders` → `BaseRenderBatch` (`structuralPass=false`) → `base_renders{id,label}`,
  `base_render_meta{design_version_id, room_key, width, height, camera?}`
→ read flag `fetchAiConfig()` → `requireStructuralMode()` (fails CLOSED if unknown)
→ if enabled: `captureStructuralRenders` → `BaseRenderBatch` (`structuralPass=true`, same scene/camera) → `structural_renders{id,label}` + per-room `CameraInfo`
→ `buildStructuralRequestFields()` pairs by stable id/label + `validateStructuralPair()` (version/room/dims/camera) → throws on first bad/missing pair
→ `withStructuralFields()` → `generateDesign()` POST `/api/floor-plans/{id}/generate`
→ `floor_plans.generate` (`backend/app/api/floor_plans.py`) → `GenerationRequestBody` (`schemas/generation.py`)
→ `generation_service.generate` → `structural_enabled = FAL_USE_CONTROLNET and FAL_CONTROL_STRUCTURAL`
→ STRUCTURAL PAIR GATE: `structural_pair.validate_structural_pair` rejects any room lacking a valid, snapshot-bound pair on the DECLARED metadata (version/room/dims/camera), AND `_validate_structural_image_bytes` rejects a structural control whose ACTUAL bytes are missing/corrupt or whose pixel size ≠ the base capture size — both fail CLOSED before any provider call (no silent base fallback). The blank heuristic is intentionally not applied (a sparse edge map is not "blank").
→ `_render_room` builds `GenerationRequest(control_image=base_bytes, structural_image=structural_bytes)`
→ `FalFluxAdapter.generate` → `_build_control_body` → provider request body.

Both images come from the **same immutable design version** (`captureSceneRef` reused for both passes) and the
**same deterministic scene/camera**; the structural image is the **perspective wireframe** (`structuralPass`
in `RoomScene3D` → `StructuralOverride`), **not** the top-down backend `/control-image` canvas. Pairing is by
**stable room id then label** (never array index or display-name ambiguity); mismatched version/room/dims (and
camera, when both sides carry one) are rejected before any submission.

## 2. fal.ai adapter semantics (verified in `fal_flux_adapter.py`)

| Field / behavior | Value |
|---|---|
| Route selector | `use_controlnet = request.control_image is not None AND FAL_USE_CONTROLNET` — **flag-driven only**, never switched by a provider response (cannot silently fall back to the edit endpoint) |
| Edit endpoint (Arm A) | `FAL_API_BASE/FAL_IMAGE_MODEL` = `fal-ai/flux-kontext/dev`; body: `{prompt, image_url=base, …}`; `last_conditioning_mode="edit"` |
| Control endpoint (Arm B/C) | `FAL_QUEUE_BASE/FAL_CONTROL_MODEL` = `fal-ai/flux-control-lora-canny`; `last_conditioning_mode="canny_controlnet"` |
| `control_lora_image_url` (STRUCTURE) | `structural` iff `structural_data_uri AND FAL_CONTROL_STRUCTURAL`, else `base`. `last_control_source` = `"structural"` or `"base"` |
| `image_url` (COLOR init) | the **base render**, present when `FAL_CONTROL_USE_INIT=true` (default) |
| `control_lora_strength` | `FAL_CONTROL_STRENGTH` (default 1.0), clamped [0,2] |
| Structural image encoded | only `if use_controlnet and request.structural_image is not None` |

**Critical for the benchmark:** Arm B and Arm C both report `last_conditioning_mode="canny_controlnet"`. They
are distinguished ONLY by **`last_control_source`** (`base` vs `structural`) plus the **SHA-256 of the control
image actually sent**. `conditioning_mode` alone is NOT sufficient evidence to tell B from C.

## 3. Fixture availability (verified on disk) — `BENCHMARK_FIXTURE_READY`

- **A valid matching base + structural fixture now exists on disk** (captured once via the dev Paired
  Capture tool, offline, no fal call): `backend/benchmarks/fixtures/bedroom-1/` containing
  `base.png`, `structural.png`, `prompt.txt`, `provenance.json`.
  - `design_version_id=12a625b9-409d-4542-bb9d-4ab7ff36afe5` (number 18),
    `floor_plan_id=9de9d0b0-a0d8-41c1-8548-8e4a4503625e`, room **Bedroom 1** (id `bedroom-1`).
  - `base.png` 90,134 bytes, sha256 `c443d1b68d63254e…`, 1216×832.
  - `structural.png` 39,746 bytes, sha256 `ec1b6ab52ea889da…`, 1216×832.
  - `prompt.txt` = the deterministic room prompt for this exact snapshot
    (`build_room_prompts` → "…of a bedroom 1 that contains exactly: 1x Bed.").
  - Both images are from the **same design version, same room, same 1216×832 dims, same deterministic
    camera** (structural is the wireframe pass of the same frame); base ≠ structural (distinct SHAs).
  - The benchmark runner's own `_load_fixtures` accepts it (base + prompt + structural → **Arm C ready**).
- The previously-proposed **`design_version=ecaaa3ce-678d-4c7b-833f-c00071d75b8e`, room `bedroom-1`** was
  **INVALID** (that version had no `bedroom-1`); superseded by the fixture above. Do **not** use it.
- A separate verified base-only fixture also exists (generation `174503c2…`, Bedroom 1,
  `design_version_id=85759b78…`, sha256 `c599d2eb…`, 1216×832) — Arms A/B only; not needed now.

### 3.1 Fixture production (REQUIRED for Arm C) — offline, no paid call
1. `cd frontend && npm run dev` (dev build only — the capture tool is `import.meta.env.DEV`-gated).
2. Open the studio on a plan that contains the target room (a bedroom). Note its `design_version_id`
   and stable room id from the scene.
3. **Menu → "Paired Capture (dev)"** (`DevPairedCapture`) → **Download provenance.json** and, for the
   target room, **download both** `…_<room>_base.png` and `…_<room>_structural.png`.
4. Place in a fixtures dir with the room's `prompt.txt` (copy the exact effective prompt from that room's
   debug artifacts if available, else the room prompt). All three arms then share one base + one prompt;
   only the control input differs. This is the reproducible, pinned input set.

## 4. The three arms (compatible with the current adapter/endpoint contract)

Camera framing is identical across arms (same base render / same capture). Same design version, room, base
render, prompt, seed, and output dimensions (1216×832). Each arm is **one** billable submission,
`FAL_SINGLE_ATTEMPT=true` (no retry, no double-bill).

| Arm | Env | Model / endpoint | `image_url` | `control_lora_image_url` | Expected `last_conditioning_mode` / `last_control_source` |
|---|---|---|---|---|---|
| **A** baseline edit | `FAL_USE_CONTROLNET=false` | `fal-ai/flux-kontext/dev` (edit) | base | — (none) | `edit` / `None` |
| **B** canny, base control | `FAL_USE_CONTROLNET=true`, `FAL_CONTROL_STRUCTURAL=false`, `FAL_CONTROL_MODEL=…-canny/image-to-image` | `fal-ai/flux-control-lora-canny/image-to-image` | base (init) | **base** | `canny_controlnet` / `base` |
| **C** canny, structural control | `FAL_USE_CONTROLNET=true`, `FAL_CONTROL_STRUCTURAL=true`, `FAL_CONTROL_MODEL=…-canny/image-to-image` | `fal-ai/flux-control-lora-canny/image-to-image` | base (init) | **structural** | `canny_controlnet` / `structural` |

> **Init-image endpoint requirement (verified 2026-10-31):** B/C send an init `image_url` (base) because
> `FAL_CONTROL_USE_INIT` defaults true; that field is schema-supported only on the `/image-to-image` variant,
> so the run sets `FAL_CONTROL_MODEL=fal-ai/flux-control-lora-canny/image-to-image`. The default model id is
> the text-to-image route — this is a per-run env, not a default change. (Verified offline: Arm B control =
> base, Arm C control = structural, both with base init; see §5 / the input-pipeline integration test.)

- **Seed policy:** one fixed seed for all arms (default: the fixture's recorded seed, else a fixed constant).
- **Control strength:** `FAL_CONTROL_STRENGTH` unset → default 1.0 for B and C (record the effective value).
- **Submissions:** 3 (A, B, C) × 1 image = **3 billable submissions** (or 2 if Arm C's structural fixture
  is unavailable and only A/B are run).
- **Unavoidable differences:** A uses a different *model/endpoint* than B/C (edit vs control-lora) — inherent
  to the edit-vs-structural comparison; everything controllable (base, prompt, seed, dims, camera) is held equal.

## 5. Per-arm provenance (recorded by the runner, independent of the production pipeline)

room, arm, model, endpoint, `conditioning_mode`, **`control_source`**, `control_strength`, base sha256,
**structural sha256** (Arm C), control-image sha256 (what actually filled `control_lora_image_url`),
`image_url` sha256, output sha256, input/output dims, seed, provider request id, effective prompt (text),
timestamp, output file path. Secrets, Authorization headers and base64 payloads are never logged.

> Production-pipeline note (UPDATED 2026-10-31): the live pipeline now **does** persist
> `control_source`, `control_image_sha256`, `structural_image_sha256`, `control_strength`, `endpoint`, and
> `output_image_sha256` in each room's durable `render_debug.json` (and surfaces them on `GenerationImageResponse`),
> so a generation run through the normal UI is now distinguishable Arm B vs Arm C from stored provenance — not only
> via the runner. All values come from the ACTUAL request/output bytes; `output_image_sha256` is absent on a failed
> render (never fabricated). No DB migration: these live where every other rich provenance field already lives.

## 6. Acceptance criteria (evaluated per output; geometry gates, realism is quality-only)

Geometry/inventory (GATING, human review — the detector stays `NOT_CALIBRATED`/advisory; blankness + aspect
checks are NOT proof of per-element preservation):
1. furniture presence & count; 2. identity/type; 3. position/dimensions/rotation where measurable;
4. room assignment; 5. walls/room-boundary; 6. doors/windows (no invented openings); 7. camera/perspective
comparability vs the base. Realism (QUALITY, non-gating): 8. materials/lighting/texture improvement.
9. provenance completeness/reproducibility. Use `UNVERIFIED`/`not_assessable` where evidence is insufficient;
keep automated checks and human review separate. **A more attractive but geometrically wrong output is a
FAILED candidate.** No output is `FAITHFUL` without output-level human review.

## 7. Comparison procedure
For each arm: record provenance, save the output PNG, and human-review each output against (a) the canonical
2D design and (b) the deterministic base render, scoring geometry and realism **separately**. Compare B vs C
to judge whether the perspective structural control preserves inventory/geometry better than the base control,
and whether either beats the edit baseline (A) on geometry without losing realism.

## 8. Cost & authorization — `COST_VERIFIED` (live fal pricing, checked 2026-10-31)
Per-MP rates read directly from the live fal model pages on 2026-10-31:
- `fal-ai/flux-kontext/dev` (Arm A): **$0.025 / megapixel** — <https://fal.ai/models/fal-ai/flux-kontext/dev>
- `fal-ai/flux-control-lora-canny/image-to-image` (Arms B, C): **$0.04 / megapixel** —
  <https://fal.ai/models/fal-ai/flux-control-lora-canny/image-to-image>

Billing is per **output** megapixel, **rounded up to the next whole MP**. Output 1216×832 = 1,011,712 px =
**1.0117 MP → billed as 2 MP**. (Input/control image size does not add cost; billed on success only.)

| Arm | Model | Rate | Billed MP | Cost/successful call |
|---|---|---|---|---|
| A | flux-kontext/dev | $0.025/MP | 2 | **$0.050** |
| B | flux-control-lora-canny/image-to-image | $0.04/MP | 2 | **$0.080** |
| C | flux-control-lora-canny/image-to-image | $0.04/MP | 2 | **$0.080** |

- **Expected total (A+B+C, 1 call each):** **$0.21 USD**. (If fal billed the true 1.0117 MP instead of
  rounding up, it would be ≈$0.106; $0.21 is the conservative round-up figure used for the cap.)
- **Worst case:** `FAL_SINGLE_ATTEMPT=true` forces exactly one submission per arm (no retry), and
  `BENCH_MAX_CALLS` hard-caps total calls, so worst case = **3 calls = $0.21** (A/B only = $0.13).
- **INR estimate:** ≈ **₹20** at 96.5 INR/USD (source Pluang, 22 Jul 2026 — ~3 months stale; rate not
  authoritative, amount is immaterial at this scale). Confirm against a live rate if INR precision matters.
- **Proposed hard USD cap:** **$0.25** (covers the $0.21 round-up total with headroom).

**Endpoint note (verified 2026-10-31):** Arms B/C send an init `image_url` (base) alongside
`control_lora_image_url` because `FAL_CONTROL_USE_INIT` defaults true. The init image is schema-supported
only on the **`/image-to-image`** variant, so the approved B/C run must set
`FAL_CONTROL_MODEL=fal-ai/flux-control-lora-canny/image-to-image` (the default is the text-to-image route).
This is a per-run env, **not** a default change. The $0.04/MP rate above is for the image-to-image variant.

**Owner approval required before any live run:** (1) the hard max USD cap ($0.25 proposed); (2) go-ahead to
run `RUN_FAL_BENCHMARK=1 FAL_SINGLE_ATTEMPT=true BENCH_ARMS=A,B,C BENCH_MAX_CALLS=3
FAL_CONTROL_MODEL=fal-ai/flux-control-lora-canny/image-to-image` for exactly those arms with **no**
provider/model/flag-default or production change; (3) the fixtures dir `backend/benchmarks/fixtures/bedroom-1`.

## 9. Runner
`backend/benchmarks/structural_ab_benchmark.py` — bounded + guarded: aborts unless `RUN_FAL_BENCHMARK=1` AND
`FAL_SINGLE_ATTEMPT=true`, hard `MAX_CALLS` cap, refuses Arm C without a structural fixture, records the §5
provenance to `structural_ab_provenance.json`. Verified to **exit immediately with no fal call** when the auth
env is absent. It reuses the real `FalFluxAdapter` (per-arm env via `importlib.reload`) — no new conditioning
strategy, no provider change.

## 10. Remaining risks / fixture readiness — `BENCHMARK_FIXTURE_READY`
- **Arm C structural fixture CAPTURED (2026-10-31).** `backend/benchmarks/fixtures/bedroom-1/` has
  `base.png` + `structural.png` + `prompt.txt` (+ `provenance.json`), all from design version
  `12a625b9…`, room Bedroom 1, 1216×832; the runner's `_load_fixtures` accepts it. Arms A/B/C can run
  once the paid run is authorized. (Capture required the backend on port **8001** — the Vite proxy's
  target — not 8000; nothing was listening on 8001 beforehand.)
- **Pricing VERIFIED (§8, 2026-10-31):** $0.025/MP (A) and $0.04/MP (B/C) from the live fal pages; bounded
  total $0.21 for A/B/C (proposed cap $0.25). `COST_VERIFIED`.
- **Still UNVERIFIED (requires the authorized paid run):** whether the live fal endpoint accepts the exact
  request body (esp. the B/C init `image_url` on the `/image-to-image` route); and output-level geometry
  fidelity (human review of real Arm A/B/C outputs). `LIVE_PROVIDER_DELIVERY` and `FAITHFUL` remain unproven.
- **Residual guard note:** `BENCH_ARMS` defaults to `A,B,C` and `BENCH_MAX_CALLS` to 3; the approved run must
  pass both explicitly so an approval for fewer arms cannot accidentally run all three (gated by auth env regardless).
- Production provenance now distinguishes B/C (resolved 2026-10-31); it lives in the on-disk `render_debug.json`
  store (same durability as all other rich provenance), not a DB column — making it DB-durable is a separate,
  approval-gated migration, not done here.

## 11. EXECUTED — Bedroom 1 A/B/C run (2026-11-03, owner-authorized)

Owner authorized a bounded run (hard cap **$0.25**). 3 paid fal calls via `benchmarks/structural_ab_benchmark.py`,
`RUN_FAL_BENCHMARK=1 FAL_SINGLE_ATTEMPT=true BENCH_ARMS=A,B,C BENCH_MAX_CALLS=3
FAL_CONTROL_MODEL=fal-ai/flux-control-lora-canny/image-to-image`, fixture `backend/benchmarks/fixtures/bedroom-1`
(design version `12a625b9-409d-4542-bb9d-4ab7ff36afe5` v18, floor-plan `9de9d0b0…`, room **Bedroom 1**). Runner exit 0.

**`PROVENANCE_VERIFIED`** (independently checked against `output/structural_ab_provenance.json`, the fixture
`provenance.json`, and the output PNGs):
- All 3 arms shared the SAME base (`sha256 c443d1b6…`), seed `1234567`, effective prompt, room, and `1216×832` dims;
  camera identity guaranteed by construction (base + structural are the same RoomScene3D frame: base then `structuralPass`).
  Arm C control = structural (`sha256 ec1b6ab5…`), distinct from the base.
- A — `flux-kontext/dev`, mode `edit`, control `None`, out `32cf5639…`, req `01a1a09c-8f2b-7e41-b37b-6de645519e52`, 12.95s.
- B — `…canny/image-to-image`, mode `canny_controlnet`, control **base**, strength 1.0, out `7ab0e37f…`,
  req `01a1a09c-c4d5-7fa3-9913-a32b4b44a3ba`, 171.84s.
- C — same model, mode `canny_controlnet`, control **structural**, strength 1.0, out `6aefa15e…`,
  req `01a1a09f-639e-7af0-81d6-3f6f848de9b3`, 10.42s. All outputs `1216×832`.

**`EXPECTED_COST`**: ≈ **$0.21** (A $0.05 + B $0.08 + C $0.08 at the §8 per-MP rates). **No invoice/usage record was
inspected — billing is NOT confirmed.**

**`HUMAN_REVIEWED`** (visual inspection of the 4 PNGs; NOT calibrated/detector measurement, NOT `FAITHFUL`):
- **A (edit):** geometry preserved (1 bed, same position/orientation/footprint, 2 pillows, rug; no extra furniture, no drift);
  realism ≈ unchanged from the flat base (near-copy).
- **B (Canny, base-control):** geometry preserved (no wireframe-cage, no hallucination); realism modestly warmer but still
  fairly flat/clay — consistent with the historical Canny "faithful-but-flat" finding.
- **C (Canny, STRUCTURAL-control):** geometry preserved (1 bed, correct position/orientation/footprint matching the edge map;
  **no wireframe-cage artifact** — the Phase-4 init-off failure did NOT recur; no hallucinated furniture); realism clearly
  improved (photoreal rumpled duvet, wood-grain headboard) — best of the three. Minor: a subtle horizontal groove/shelf line
  appeared on the headboard surface (material detail, not an added object; still 1 bed).

**Scope & limits:** ONE bedroom fixture only — **NOT** production-wide accuracy; no output is `FAITHFUL`. The hard case
(sparse open-plan Kitchen & Dining, AIR-11/12) was **NOT** tested here. Geometry fidelity is `HUMAN_REVIEWED`, not
pixel-measured; precise position/dimension/rotation deltas remain `UNVERIFIED` (no calibrated output detector). On this
fixture Arm C preserved geometry AND improved realism simultaneously — i.e. did **not** reproduce the historical
geometry-vs-photorealism trade-off — but this is a single-room result.

**Next (NOT executed):** a bounded, Arm-C-only paid run on the sparse open-plan Kitchen & Dining base (its own structural
fixture) to test whether Arm C holds on the actual clay case — requires fresh owner authorization (§12).

## 12. PREPARED — Open-plan Kitchen & Dining Arm-C bounded run (fixture capture PENDING)

**Canonical case (identified + verified, offline):** the sparse open-plan AIR-11/12 case is design version
**v84 `62ef3454-7c52-4760-9333-d40570bb6ded`** (frozen, `is_frozen=true`) of plan `f6b65d2b`, room
**`kitchen-dining-area` "Kitchen & Dining Area"** — CONFIRMED, **2 furniture** (chimney panel + dining table: the sparse
case AIR-11 identified). Verified from the frozen canonical (`backend/tests/fixtures/canonical_v84_62ef3454.json`) and the
live backend version-pinned scene (`GET /api/floor-plans/f6b65d2b…/scene?version=62ef3454…` -> HTTP 200). **Do NOT use the
plan's current latest (v119 — now generic "Room 1..5");** the AIR-11/12 case is the FROZEN v84. No canonical change.

**Fixture capture — PENDING (tooling gap, documented):** a valid Arm-C pair needs `base.png` + a *pixel-aligned*
`structural.png`, both from the SAME `RoomScene3D` frame (v84, room `kitchen-dining-area`, 1216x832). **No existing dev
tool captures BOTH version-pinning AND the structural pass:** `DevPairedCapture` renders base+structural but calls
`fetchScene(planId)` with no version (latest-only -> would capture v119); the `harness` is version-pinned (`?version=`)
but renders only the BASE pass (`toDataURL`, no `structuralPass`). So capturing the frozen v84 K&D structural pair needs a
small OFFLINE dev-tool change — add an optional `version` to `DevPairedCapture` (`fetchScene(planId, version)`), or a
`structuralPass` mode to the harness — plus the dev environment (Vite 5173, proxy -> backend 8000, both offline) and the
Paired Capture flow. **No canonical/furniture/room-membership/wall/opening/camera change; offline; no fal call.**

**Capture procedure (offline, no paid call):**
1. (one-time) add an optional `version` param to `DevPairedCapture` so it fetches the frozen v84 scene; `npm run dev` (Vite 5173 -> backend 8000).
2. Pin to v84, trigger "Paired Capture (dev)"; for room `kitchen-dining-area` download `…_base.png` + `…_structural.png` (both 1216x832) + `provenance.json`.
3. Place in `backend/benchmarks/fixtures/kitchen-dining-v84/` with the room's `prompt.txt` (the deterministic K&D room prompt) + `config.json` `{seed, room_label:"Kitchen & Dining Area", design_version_id:"62ef3454…"}`.
4. Record base/structural byte-size + sha256 + pairing guarantees (same version/room/dims/camera, base != structural).

**Pair validation + payload wiring (VERIFIED offline against current source):**
- `structural_pair.validate_structural_pair` + `_validate_structural_image_bytes` fail CLOSED on any version/room/dims/camera mismatch or wrong-size/corrupt structural bytes — no silent base fallback (`generation_service.py:2072-2093`).
- `_build_control_body`: `use_structural = structural_data_uri AND FAL_CONTROL_STRUCTURAL` -> structural fills `control_lora_image_url`, base is the SEPARATE `image_url` init; `last_control_source="structural"`; a wrong-image swap is impossible by construction (`fal_flux_adapter.py:395-416`).
- Cap: `FAL_SINGLE_ATTEMPT=true` -> exactly 1 billable POST (verified across all layers + 5 cost-cap tests).
- Offline tests (exact): `pytest tests/test_structural_conditioning.py tests/test_perspective_structural_pass.py tests/test_input_pipeline_integration.py tests/test_provenance_conditioning.py` -> **40 passed**. No new gap found -> no new test added.

**Bounded Arm-C-only run (NOT executed; awaiting authorization):**
- Command: `RUN_FAL_BENCHMARK=1 FAL_SINGLE_ATTEMPT=true BENCH_ARMS=C BENCH_MAX_CALLS=1 FAL_CONTROL_MODEL=fal-ai/flux-control-lora-canny/image-to-image BENCH_FIXTURES=backend/benchmarks/fixtures/kitchen-dining-v84` via `benchmarks/structural_ab_benchmark.py`.
- Provider/model: fal `fal-ai/flux-control-lora-canny/image-to-image`; conditioning `canny_controlnet`, control=structural, `control_lora_strength` 1.0, base as `image_url` init; dims 1216x832; fixed seed.
- **Max billable attempts: 1** (`FAL_SINGLE_ATTEMPT` + `BENCH_MAX_CALLS=1`); **expected requests: 1**.
- **`EXPECTED_COST`: ~$0.08** (1 render x 2 MP x $0.04/MP round-up; no invoice). Proposed hard cap **$0.10**.
- Output/provenance: `backend/benchmarks/fixtures/kitchen-dining-v84/output/bench_C.png` + `structural_ab_provenance.json`.
- Failure handling: fail-closed PAIR GATE before any call; on provider failure no image saved (no fabricated output); the deterministic base render remains the trusted fallback.
- Human-review acceptance (geometry GATING, realism QUALITY, separate; **no `FAITHFUL` without review**): the 2 K&D items present + count-correct, identity/type, position/footprint vs base, room assignment, walls/openings, camera comparability; then realism vs the clay base; provenance complete. A prettier-but-wrong output = FAILED.

**[2026-11-04] FIXTURE CAPTURED (offline, no fal call) — `kitchen-dining-v84` READY.** Instead of a `DevPairedCapture`
version param, the version-pinned `harness.tsx` was given a `structural=1` URL param (renders the `structuralPass`) and a
`window.__captured_png` export; the v84 K&D base + structural were captured via the browser (Vite 5173 -> user's backend
8000) and written to `backend/benchmarks/fixtures/kitchen-dining-v84/`:
- `base.png` — 1216x832, 143,122 B, **sha256 `f9bcd81670d88e6b716b3425b95298ecb81ba9aa34a16f5c1b4e29f70c9bc17d`**.
- `structural.png` — 1216x832, 42,842 B, **sha256 `056fbc4099516aa495f5154c79e9da674a3ac4b4d62e4ae9937476293a92d7ff`** (DISTINCT from base).
- `prompt.txt` — 10,581 B, sha256 `acca9537…`, inventory **"1x Chimney, 1x Dining Table"** (the merged scene room `kitchen-dining-area`, via `build_region_prompt` over its exact items — not the over-segmented "Kitchen" section).
- `config.json` {seed 1234567, room_label "Kitchen & Dining Area", design_version_id `62ef3454…`} + `provenance.json` (hashes, pairing guarantees, inventory).
- **Visual verification (not just hashes/dims):** base = the sparse open-plan K&D (chimney + hood block + wood dining table on a wood floor); structural = the SAME composition as a clean wireframe (same camera/positions), genuinely the edge-map pass.
- **Pair validation (offline):** `structural_pair.validate_structural_pair(base_meta, structural_meta)` -> `True/OK`; fail-closed on wrong-room (`STRUCTURAL_WRONG_ROOM`) and wrong-dims (`STRUCTURAL_WRONG_SIZE`). Tests: `pytest tests/test_structural_conditioning.py tests/test_perspective_structural_pass.py tests/test_input_pipeline_integration.py` -> **31 passed**.

**[2026-11-04] EXECUTED — open-plan Arm-C run (owner-authorized, hard cap $0.10).** 1 paid fal call,
`BENCH_ARMS=C BENCH_MAX_CALLS=1 FAL_SINGLE_ATTEMPT=true`, runner exit 0.
- **`PROVENANCE_VERIFIED`:** mode `canny_controlnet`, **control=structural** (`056fbc40…`), base init `f9bcd816…`, strength 1.0,
  dims 1216x832, output `bench_C.png` sha `14fe2926e87d80d0`, req `01a1a4e5-8108-7a02-9918-9181d3d59096`, 205.7s, 1 billable call.
- **`EXPECTED_COST` ~$0.08** (1 x 2 MP x $0.04/MP; no invoice inspected).
- **`HUMAN_REVIEWED` (visual; not detector; NOT `FAITHFUL`):** **Layout/geometry PRESERVED** — the 3 object footprints sit at
  the SAME positions as the base, same camera, **no wireframe-cage artifact** (unlike the historical Canny init-off failure),
  **no hallucinated extra furniture**, floor intact. **BUT object IDENTITY DRIFTED:** the canonical **Chimney** was re-rendered
  as a **door** (handle + panel), and the gray hood/appliance box as a **kitchen oven/microwave** (controls, heating element);
  only the dining table kept its type. Realism improved only modestly (still fairly flat on this sparse/white scene).
- **Verdict:** **FAILED the geometry/inventory gate on IDENTITY** (chimney->door; an oven-like object not in the "1x Chimney,
  1x Dining Table" inventory), even though position/footprint/count/camera held. A prettier-but-wrong output is a FAILED
  candidate. So **the structural-edge route does NOT solve the open-plan case**: it holds LAYOUT (an improvement over init-off
  Canny) but does NOT preserve object IDENTITY on sparse, ambiguous furniture silhouettes. Contrast the Bedroom 1 result (§11),
  where identity held — the difference is base sparsity/ambiguity (AIR-11), not the conditioning route alone. No `FAITHFUL`.

**Readiness note:** the open-plan Arm-C experiment is now DONE (above). Any further paid run (e.g. a different open-plan room,
a strength sweep, or depth conditioning) requires its own fresh owner authorization.
