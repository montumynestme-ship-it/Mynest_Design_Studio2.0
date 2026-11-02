# MyNest Design Studio — AI Render Fidelity Workflow

> **Status:** DRAFT WORKFLOW — for review/approval. This document is the *procedure*; it
> does not itself execute any investigation or fix.
> **Default mode:** `REPORT-ONLY`. No implementation, no paid AI/API calls, no production
> or database changes, no deploy, no push/PR until the specific gate in §A authorizes it.
> **Core invariant:** the canonical 2D design is the single source of truth. AI may change
> only appearance (materials, textures, lighting, styling); it must never change furniture
> inventory/identity/type/count/position/dimensions/rotation/room-assignment, or
> walls/rooms/doors/windows/their geometry. A pretty render that changes the design is a
> **failed** render; the deterministic base render is the trusted fallback.

Each claim below is tagged **[VERIFIED]** (checked against current code/tests this session),
**[DOC-CLAIM]** (asserted by repo docs, *not* confirmed in code — must be verified before
reliance), or **[UNVERIFIED]** (not yet established). The workflow requires every executing
agent to re-verify, because code and data drift.

---

## A. Purpose, Scope, and Non-Negotiable Rules

**Objective.** Investigate and resolve AI-render fidelity problems: missing/extra furniture;
furniture identity/type/count/position/dimension/rotation/room-assignment mismatches;
door/window omission/addition/displacement/distortion; canonical↔scene↔render mismatches;
camera/FOV/crop/aspect differences that make comparison unreliable; and information loss
anywhere across catalog→canvas→JSON→API→scene→prompt→conditioning→generation→post-processing.
These are **investigation targets, not confirmed root causes.**

**Non-negotiable rules.**
1. **Canonical geometry invariant** (above) is absolute. Never force uncertain furniture or
   opening placement merely to satisfy a validator or a test.
2. **Deterministic fallback policy.** When AI output fidelity is not established by evidence,
   the deterministic base render stays the trusted artifact; the render is reported
   `UNVERIFIED`, never "faithful".
3. **Evidence & provenance.** Every factual claim cites a file+function, a hash, a test name
   with its exact command and exit code, or an artifact path. Distinguish VERIFIED vs
   agent-reported vs inferred vs unknown. Never fabricate evidence or present a doc claim as
   code truth.
4. **Modes.** `REPORT-ONLY` (default: read, trace, measure, propose) → `IMPLEMENTATION` (only
   after §A gate) → `VALIDATION`. No stage auto-promotes.
5. **Approval gates (STOP and ask).** Required before: any code/test/fixture/doc-of-record
   edit; any paid or cost-incurring AI/API generation; any expensive experiment; any
   production/database/config/schema/dependency change; any deploy, destructive op, push, PR,
   or merge; and any scope expansion beyond approved issue IDs and file set.

**The implementation gate:** no implementation begins until (a) the audit report identifies an
**evidence-supported** root cause, (b) the user approves the exact issue IDs + file scope, and
(c) the agent re-confirms working-tree state. Absent all three, stay in REPORT-ONLY.

---

## B. Initial Repository and Project-State Review

Before any analysis, the executing agent must record:
- **VCS state.** Branch, commit SHA, `git status --short`, and the working-tree diff **of the
  actual tracked checkout**. *(Known limitation [VERIFIED]: the live working tree
  `D:\…\mynest-design-studio` is **not** a git repository; the tracked copy is a review branch
  / PR on `montumynestme-ship-it/Mynest_Design_Studio2.0`. Record this and do not run git ops
  against the non-repo path.)*
- **Phase & history.** Current phase, prior decisions, known failures, completed work, open
  issues (cross-reference existing reports in `docs/` and `backend/output/`).
- **Docs read** (list each, mark read vs skimmed vs unavailable): `README.md`,
  `docs/CORE_PIPELINE_DOCUMENTATION.md`, `docs/ARCHITECTURE.md`, `PROJECT_CONTEXT.md`,
  `docs/PIPELINE_AUDIT_REPORT.md`, `docs/BASE_RENDER_FIX_REPORT.md`, `docs/AI_RENDER_FIX_REPORT.md`,
  `backend/output/ai_render_issue_triage/AI_RENDER_ISSUE_TRIAGE.md`.
- **Tests & commands.** Backend: `cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m
  pytest -p no:cacheprovider -q`. Frontend: `cd frontend && ./node_modules/.bin/tsc --noEmit`,
  `./node_modules/.bin/eslint .`, `npm run build`, `./node_modules/.bin/playwright test`.
- **Canonical fixture.** The approved frozen geometry baseline is **DesignVersion v31**,
  id `1831bf84-f9d6-4d4f-aedc-4ad95d6145fe`, committed at
  `backend/tests/fixtures/canonical_v31_1831bf84.json`, canonical sha256
  `228aad99d20dbdbb96bfe8e3ed3e07817432caa353f357870bde44b0eaac3323`
  (22 real furniture, 8 doors, 4 windows, 0 `room-tag` annotations) [VERIFIED]. Floor plan
  `f6b65d2b-4f96-4931-9f08-67dbd09776f6`.
- **Access limitations.** Record anything not inspected (missing artifacts, no live provider
  funding, DB-only data). **Never claim a file, image, artifact, or test was inspected unless
  it was.**

---

## C. End-to-End Pipeline Mapping

Trace the **actually executed** path — from real calls and data, never from file names,
comments, prompts, or docs. The current executed topology [VERIFIED this session]:

`canonical_json (furniture only)` → `scene_service.build_scene(file_id, canonical=None)`
(walls/doors/windows from the **immutable floor-plan file** via
`geometry_extraction_service.extract_walls`; furniture from the canonical) →
`architectural_service.reconstruct_rooms` → frontend `BaseRenderBatch.tsx` + `RoomScene3D.tsx`
WebGL capture (1216×832 base PNG) → `registry.get_adapter(DEFAULT_AI_PROVIDER)` →
`FalFluxAdapter` (`fal-ai/flux-kontext/dev`) → img2img edit → validation gates →
`file_storage.save_generation_image(GENERATIONS_DIR/{gen}/{index}.png)` →
`GenerationGallery.tsx`.

For **every** stage below capture: Input + provenance · source file/function/path ·
transformation · output artifact/data · invariants/checks · evidence collected · confirmed
defects / hypotheses / unknowns · next consumer.

| # | Stage | Primary source (verify paths) | Notes to verify |
|---|---|---|---|
| 1 | Frozen canonical & authoritative JSON | `DesignVersion.canonical_json` (`app/db/models.py`); `floor_plan_service.get_canonical` | Canonical array holds furniture **and** openings (`door`,`window`,`bay-window-seat`) **and** annotations (`room-tag`). [VERIFIED] |
| 2 | Furniture IDs, catalog, dims, SVG mapping, 2D canvas | `frontend/src/data/furniture.ts`, `src/components/design-studio/DesignCanvas.tsx`, `public/furniture/*.svg` | Icon→item_id mapping; annotation category (`room-tag`). |
| 3 | Canvas→JSON, save/autosave, API payload, persistence | `src/store/useEditorStore.ts`, `src/lib/api.ts`, backend save-layout path | Payload equality canonical↔persisted. |
| 4 | Snapshot/version selection & normalization | `generation_service` (binds the immutable snapshot version at persist) | append-only, immutable versions. [VERIFIED] |
| 5 | Deterministic 3D scene (walls/rooms/furniture/openings) | `scene_service.build_scene`, `architectural_service` | walls from file; CONFIRMED vs UNCERTAIN rooms; open-plan merge. [VERIFIED] |
| 6 | 3D object/model selection & transforms | `frontend/src/lib/furniture3d.ts`, `RoomScene3D.tsx` | coord/scale/rotation/room transforms; `computeMpp`. |
| 7 | Camera + base-render capture | `frontend/src/lib/aiCamera.ts` (`AI_FOV=46`,`ENCLOSED_FOV=72`,`baseCaptureFov`), `BaseRenderBatch.tsx`, `scene.ts` (`BASE_CAPTURE_W/H=1216/832`) | deterministic solver, per-room fit. [VERIFIED] |
| 8 | Base-render validation & preconditions | `base_render_service.validate_base_render`, `generation_service._classify_base_gate` | strict contract: version/room/size, fail-closed, no substitution. [VERIFIED] |
| 9 | AI request construction (image+prompt+theme+settings) | `generation_service`, `fal_flux_adapter._build_fal_edit_prompt` / `_build_body` | **single-pass edit**, image_url + prompt; mandatory-first prompt budgeting. [VERIFIED] |
| 10 | Provider/adapter execution | `registry.get_adapter`, `FalFluxAdapter.generate` (fal), `NvidiaFluxAdapter`, `MockAdapter` | active = `fal`; nvidia fallback; mock in `AI_DEMO_MODE`. [VERIFIED] |
| 11 | Post-processing, validation, persistence, retrieval | `generation_service` (`_to_png`, `assess_ai_output_geometry`, `_compute_postgen_status`, `assess_ai_render`); `file_storage`; `app/api/generations.py` | output dims **not** persisted (derivable from `{index}.png`). [VERIFIED] |
| 12 | Output presentation / comparison UI | `GenerationGallery.tsx` | AI output is a standalone `<img>`; viewpoint not guaranteed. [VERIFIED] |

**Conditioning reality — must be re-verified every run.** `docs/CORE_PIPELINE_DOCUMENTATION.md`
describes a **two-pass Depth + Canny ControlNet** pipeline ("✅ Fully Implemented",
Depth strength 1.0 + Canny strength 1.0, "rigid structural conditioning") **[DOC-CLAIM]**. The
code shows `FAL_USE_CONTROLNET=False` by default → the **single-pass image-edit path runs**
(`image_url` + prompt, no depth/edge/mask); the Canny Control-LoRA path exists
(`_build_control_body`, `fal-ai/flux-control-lora-canny`) but is **gated off**, and no Depth
LoRA pass was found **[VERIFIED]**. The workflow treats "two-pass ControlNet is active" as a
discrepancy to confirm from `app/core/config.py` + the runtime `AI_RENDER_CONFIG` log line,
never as fact. (This absence of structured conditioning is triage root cause **F1** and a
leading fidelity hypothesis.)

---

## D. Canonical-to-Render Traceability

Trace ONE controlled design (recommend the frozen v31 fixture) through every stage, capturing
where available: design id · frozen version id · canonical JSON hash · per-item furniture
(uid, item_id, type, count, cx/cy, w/h, rotation, room) · door/window (id, dims, host wall,
position) · scene object ids + transforms · camera settings + base-image hash · the **exact**
AI request + effective config (provider/model/seed/strength/guidance/resolution/conditioning)
· generation id · output image hash/bytes/dims · final review decision + artifacts.

**Join key for backend provenance [VERIFIED]:** `(generation_id, index)` links the output
(`GENERATIONS_DIR/{generation_id}/{index}.png`), the DB row (`AIGenerationImage`), and the
per-room provenance dir (`DEBUG_ARTIFACTS_DIR/{generation_id}/room_{index}_{label}/`:
`provider_request_metadata.json`, `provider_response_metadata.json`, `prompt.txt`,
SHA-verified `base_render.png` + `base_render_meta.json`). Actual **output dimensions** and the
fal `request_id` are **not** persisted — output dims are derivable offline from the stored PNG;
`request_id` is only in logs. Where IDs do not persist across a stage, **document the mapping
method and its uncertainty; never invent stable identities.** Never expose secrets or customer
data (`backend/.env`, keys, tokens) in any report.

---

## E. Issue Classification and Root-Cause Analysis

Maintain an **issue matrix** with: Issue ID · Symptom · Design/version · Expected state ·
Observed state · Earliest divergence stage · Evidence · Classification
(Verified/Agent-reported/Inferred/Unknown) · Confidence (or not-assessable) · Impact + invariant
· Root cause (confirmed/hypothesis/unresolved) · Proposed minimal fix (only if evidence-justified)
· Regression criteria · Status (Open/Investigating/Confirmed/Approved/Implemented/Verified/Blocked).

Classify each furniture/opening problem as exactly one of: **Missing · Extra · Wrong
identity/type · Wrong count · Wrong position · Wrong dimensions/scale · Wrong rotation · Wrong
room assignment · Door/window or wall-relationship mismatch · Occluded/merged/cropped/ambiguous
· Camera mismatch · Not assessable.** Do **not** call a cropped/occluded object "missing"
without evidence, and do **not** assert exact transform errors when camera comparability is
inadequate (use §F).

Seed the matrix from the existing triage register (issues A–D; root causes F1–F9 in
`AI_RENDER_ISSUE_TRIAGE.md`) but **re-verify each** — do not reopen a resolved item without new
evidence, and do not present a hypothesis as a confirmed cause.

---

## F. Camera and Image Comparability

Before any geometric image comparison, complete this checklist and record each value with its
source: camera position & target · projection type · FOV (or ortho scale) · aspect ratio +
output dimensions · crop/framing/zoom/orientation · room coverage/occlusion/visibility ·
base-render vs final-render comparability.

**Known baseline [VERIFIED]:** the deterministic base capture uses a shared, deterministic
camera (`solveAiCamera`/`solveEyeLevelCamera`, FOV 46/72, aspect 1216/832, per-room distance
fit). The **AI output is a standalone image** whose viewpoint the edit path does not control, so
a shared base FOV does **not** guarantee the output is framed identically. **Distinguish camera
mismatch from scene-geometry mismatch.** If comparable camera evidence cannot be obtained, label
the comparison `UNVERIFIED` / `not_assessable` — never guess a transform delta from
incomparable framing.

---

## G. AI Prompt, Theme, and Conditioning Review

Inspect the **exact** prompt/settings actually sent (from `prompt.txt` + request metadata +
`_build_fal_edit_prompt`), covering: system/user prompt · theme/style · negative prompt (if any)
· base image + any other conditioning · model/provider/version · strength/guidance/resolution/seed
· depth/Canny/ControlNet **only if confirmed active** (see §C discrepancy) · retries/fallback
adapters/post-processing.

Evaluate whether wording/conditioning *encourages* layout change, but **do not assume prompt
wording is the root cause when upstream data or scene construction may already be wrong** —
prioritize the earliest divergence (§H). Known prompt behavior [VERIFIED]: `_build_fal_edit_prompt`
reserves the mandatory geometry/inventory/negatives and trims only the optional theme (≤2200
chars); the user theme replaces the fixed house style. **No paid/cost-incurring generation in
REPORT-ONLY.**

---

## H. Root-Cause Prioritization and Minimal Fix Plan

Prioritize the **earliest evidence-supported divergence** (fixing a late symptom while an upstream
stage is wrong wastes effort). For each proposed fix document: confirmed evidence + root cause ·
why the change addresses the cause · exact files/components in scope · required behavior +
preserved contracts · risks/backward-compat · tests + render comparisons needed · acceptance
criteria · whether explicit user approval is required (default: yes).

Avoid broad refactors, model switches, prompt rewrites, new dependencies, schema or architecture
changes unless evidence justifies them **and** the user approves the scope. Never force uncertain
placement to satisfy a validator.

---

## I. Implementation Protocol (post-approval only)

1. Confirm approved issue IDs + file scope in writing.
2. Re-inspect the latest implementation and working-tree state.
3. Make the **smallest** supported change.
4. Preserve APIs, data contracts, coordinate systems, and business logic unless explicitly
   approved otherwise. Do **not** modify live DB records, frozen canonical versions, or the AI
   generation pipeline to make a test pass.
5. Add regression coverage **without** weakening existing tests or changing expected results
   solely to go green. (Pattern already established: pin data-dependent tests to the frozen v31
   fixture via the `frozen_v31` conftest fixture; keep annotation-exclusion in its own test.)
6. Leave unrelated issues untouched.
7. STOP and request approval on any scope expansion or unexpected risky dependency.

---

## J. Validation and Regression Protocol

Validate at the right levels and record exact commands + exit codes + passed/failed/skipped:
unit (transform/serialization) · contract (canonical↔payload) · scene-construction (furniture +
openings) · camera/capture (where available) · request/adapter · validation-service · e2e where
practical · **before/after render comparison using the same canonical design and a comparable
camera** (§F).

Assess these **separately** (never collapse into one pass/fail): (1) presence + missing/extra
counts · (2) identity/type + inventory count · (3) position/dimensions/rotation · (4) room
assignment · (5) wall/door/window preservation · (6) camera comparability · (7) appearance
improvements that do not violate geometry. **Matching total counts do not prove identity or
transform equality.**

Detector outputs (e.g. `furniture_detector_hybrid`, dormant/NOT_CALIBRATED) are **advisory only**
until calibration/reliability is demonstrated; human review is required when automatic evidence
is insufficient. Keep `CONTRACT_VALID` evidence separate from `LEGACY_NON_CONTRACT`; never present
synthetic/legacy examples or a small sample or passing unit tests as proof of production-wide
accuracy. Known constraint [VERIFIED]: `assess_ai_render` is an honest tri-state —
`geometry_status` is `FAIL`/`UNVERIFIED`/`FAITHFUL`, and the AI **output** stays `UNVERIFIED`
(`geometry_faithful = None`) unless an output-level geometry check sets `output_verified=True`
(which no production path currently does). Do not report the output as faithful on the strength
of a locked *input* alone.

---

## K. Final Render Review and Acceptance Criteria

Structured 3-way review per design: (1) canonical design + object inventory · (2) deterministic
3D scene + base render · (3) final AI render. For each discrepancy record expected vs observed,
evidence, camera comparability (§F), classification (§E), and review outcome.

**Acceptance criteria.** Accept a render only when: no unexplained inventory differences · no
unauthorized changes to canonical geometry/transforms in the deterministic scene · AI-induced
geometry changes are explicitly assessed and documented · camera comparability is established or
explicitly marked unverified · no unresolved critical invariant violation is reported as success
· the deterministic fallback is retained whenever AI fidelity is not established. **Do not invent
numerical accuracy thresholds** — if the project does not already define one, record the proposed
threshold as *requiring approval*.

---

## L. Reports and Deliverables

Produced during later execution phases (not all required now): initial pipeline audit report ·
issue/root-cause register · evidence & provenance manifest · approved minimal-fix plan ·
implementation report · regression-test report · before/after render-review report · final
closure summary with unresolved risks.

Every report must separate **Verified facts · Agent-reported (unconfirmed) · Inferences ·
Unknown/blocked**, and must include exact commands + exit codes, changed-file lists, git status +
relevant diffs, artifact references/hashes where available, and limitations. **Never fabricate
evidence.** Never expose secrets or customer data.

---

## M. Stop Conditions

STOP and report (do not guess) when: the canonical design or expected version cannot be
identified · required source, render artifacts, or logs are unavailable · the real production
path cannot be distinguished from a mock/dev harness (`AI_DEMO_MODE`/`MockAdapter`) · camera
mismatch prevents reliable geometry comparison · a proposed fix needs unapproved scope expansion ·
a paid API call / costly experiment / production op / destructive change / deployment is required
· a test failure cannot be classified with sufficient evidence · a proposed solution would violate
the canonical geometry invariant.

---

## Appendix — Known State Snapshot (verify before relying on any item)

- **Active provider/model [VERIFIED]:** `DEFAULT_AI_PROVIDER=fal` → `FalFluxAdapter`,
  `fal-ai/flux-kontext/dev`; `FAL_USE_CONTROLNET=False` → single-pass edit; nvidia = fallback,
  mock = `AI_DEMO_MODE`.
- **Conditioning discrepancy [DOC-CLAIM vs VERIFIED]:** docs say two-pass Depth+Canny ControlNet
  is active; code runs single-pass image-edit with no depth/edge/mask. Confirm per run.
- **Frozen baseline [VERIFIED]:** v31 `1831bf84`, sha256 `228aad99…3323`, 22 furniture / 8 doors /
  4 windows / 0 annotations; fixture at `backend/tests/fixtures/canonical_v31_1831bf84.json`.
- **Open-plan ambiguity [VERIFIED]:** Kitchen & Dining — `group_by_room` splits sections while
  `reconstruct_rooms` yields one CONFIRMED `kitchen-dining-area` + UNCERTAIN twins; honest
  base-inventory MISMATCH is surfaced (product decision pending).
- **Annotations [VERIFIED]:** `room-tag` ∈ `ANNOTATION_IDS`; excluded from furniture grouping and
  the 3D scene; covered by `backend/tests/test_annotation_exclusion.py`.
- **Output provenance gap [VERIFIED]:** actual output dimensions + fal `request_id` not persisted
  (dims derivable offline from `{index}.png`).
- **Known remaining test failures at time of writing [VERIFIED]:** `test_invoice_upload` ×2
  (`ModuleNotFoundError: reportlab` — environment/dependency, out of scope) and
  `test_validation_geometry::test_assess_ai_render_trust_rules` (stale expectation of the old
  overconfident `geometry_faithful=True`; the honest tri-state now returns `None`). Both require
  owner authorization before any change.
