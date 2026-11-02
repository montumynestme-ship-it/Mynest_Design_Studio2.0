# MyNest Design Studio — Faithful 3D AI Render Recovery & Execution Guide

**Document purpose:** A single, actionable guide for investigating and fixing the defects that prevent MyNest Design Studio from producing a visually convincing, geometrically faithful 3D AI interior render.

**Primary objective:** Generate an actual AI-styled 3D render that remains faithful to the canonical 2D design—not merely a successful API response, passing test suite, updated report, or attractive but inaccurate image.

**Project:** MyNest Design Studio
**Primary issue register:** `docs/AI_RENDER_ACCURACY_ISSUES.md` (use the existing register; do not create a duplicate)
**Execution workflow:** `docs/AI_RENDER_ISSUE_EXECUTION_WORKFLOW.md` (if present in the working tree; reconcile with this guide)
**Status:** Execution guide. All issue statuses and implementation assumptions must be re-verified against the current repository.

---

# Part I — Mission and non-negotiable rules

## 1. Definition of the required result

The final deliverable is an actual, reviewable AI-generated interior render for the correct immutable design version, accompanied by its deterministic base render and sufficient provenance to reproduce and assess it.

The output must:

1. Preserve every canonical furniture item's identity, type, count, position, dimensions, orientation, and intended room assignment.
2. Preserve room boundaries, walls, doors, windows, and architectural relationships.
3. Improve only visual appearance: materials, textures, finishes, lighting, shadows, reflections, ceiling treatment, and styling.
4. Be compared against its matching deterministic base render and canonical design.
5. Have its provider/model, conditioning settings, input/output identities, hashes, generation ID, and validation/review decision recorded where available.

A successful provider response, non-empty image, changed output hash, passing input contract, or attractive image does **not** prove fidelity.

## 2. Canonical design contract

The canonical 2D design and its immutable, versioned snapshot are authoritative.

AI and any heuristic must never:

- Add, remove, duplicate, replace, or reinterpret furniture.
- Change furniture ID, catalog identity, type, count, dimensions, position, rotation, or room assignment.
- Move, resize, add, or remove walls, doors, windows, room boundaries, or architectural openings.
- Invent room connections or change room topology.
- Modify canonical data merely to make a render or validator pass.

AI may change visual appearance only. Keep deterministic 3D rendering as the trusted fallback until output-level AI fidelity is demonstrated.

## 3. Engineering rules

- Inspect current code and tests before proposing or editing.
- Establish root cause before implementation.
- Make the smallest evidence-supported change.
- Preserve existing architecture, API contracts, data models, coordinate conventions, provider defaults, and backward compatibility.
- Do not add dependencies, refactor unrelated modules, replace providers, or change production defaults without explicit approval.
- Never weaken tests or change expected results simply to get a pass.
- Never force uncertain furniture/opening/room placement to satisfy validation.
- Preserve existing user changes and uncommitted work.
- Do not reset, clean, overwrite, or discard unrelated files.
- Do not claim a fix without code, regression, and relevant output evidence.

## 4. Evidence labels

Every report must label claims as:

- **VERIFIED:** directly established from inspected source, reproducible test output, actual artifacts, hashes, or database/API evidence.
- **AGENT-REPORTED:** stated in a prior agent report but not independently reproduced.
- **INFERRED:** plausible interpretation requiring further evidence.
- **UNKNOWN / UNVERIFIED:** insufficient evidence.

Keep `CONTRACT_VALID` (input/version/room/request contract) separate from actual visual fidelity. Use `UNVERIFIED` or `not_assessable` when output evidence is insufficient. Do not claim production-wide accuracy from one fixture or a small sample.

---

# Part II — Mandatory repository review

## 5. First action: establish the real project state

Before changing anything, locate and read the actual current versions of:

- `README.md`
- `CORE_PIPELINE_DOCUMENTATION.md`
- `PROJECT_CONTEXT.md`
- `docs/AI_RENDER_ACCURACY_ISSUES.md`
- `docs/AI_RENDER_ISSUE_EXECUTION_WORKFLOW.md`
- `AI_RENDER_FIDELITY_WORKFLOW.md` or its actual equivalent
- Existing pipeline audit, base-render, AI-render, fix, benchmark, and provenance reports
- Latest supplied render ZIPs, paired captures, manifests, and logs

Do not assume a file exists or rely on an old copy if a newer repository copy exists. Record missing files as gaps.

Inspect:

- Git branch, commit, and working-tree status, if this is a Git repository.
- Existing user changes and prior agent modifications.
- Current frontend/backend runtime configuration.
- Active provider, exact model, conditioning path, prompt construction, and feature flags.
- Scene assembly, camera solving, base-render capture, request validation, provider adapters, output validation, persistence, and gallery display.
- Canonical design snapshots, furniture manifests, room mapping, generation records, base images, AI outputs, hashes, logs, and relevant tests.

**Important known environment warning:** a previous agent reported that `D:\Latest_mynest_design_version\mynest-design-studio` was not a Git repository in its inspected environment. This is historical agent-reported information, not proof of the current checkout. Verify again; do not invent a branch or commit.

## 6. Architecture path to trace

Use the actual code, not only this conceptual path:

1. User selects project, floor, room/section, and design version.
2. Frontend loads canonical layout and room metadata.
3. Canonical snapshot/version is resolved.
4. Furniture and architectural scene are assembled deterministically.
5. Camera is solved for the target room.
6. Browser/WebGL captures the deterministic base image.
7. Base-render contract validates image, room, dimensions, and version.
8. Generation service constructs provider request and prompt.
9. Provider adapter sends image and conditioning controls.
10. Provider returns output.
11. Output is persisted with generation/provenance metadata.
12. Post-generation validation runs.
13. Gallery displays base/output and fidelity status.
14. Human review compares output with canonical design.

For every defect, identify the earliest responsible stage. Do not patch a downstream symptom if the root cause is upstream.

---

# Part III — Current evidence and investigation queue

## 7. Evidence currently available in the project conversation

The following is the known context available to this guide. It is not a substitute for checking the current repository and original artifacts.

### 7.1 Latest multi-section render — screenshot-reported / agent-reported

A prior review described `latest_output_3d.zip` and screenshots as showing:

- 4 of 6 sections generated.
- Kitchen and Dining Area failed.
- 179 walls extracted.
- 5 of 7 rooms proven.
- Geometry uncertain.
- Deterministic furniture fidelity displayed as 100%.
- AI furniture fidelity displayed as Not Verified.
- AI geometry displayed as NOT PROVEN.
- Design-version association for the six-section run was not visible and remained UNVERIFIED.

Treat these as **screenshot-reported or agent-reported** until checked against the actual run, database/API records, logs, and artifacts. Do not assume this run is identical to the separate v84 region run below.

### 7.2 Separate Kitchen + Dining v84 run — agent-reported provenance

A prior report supplied this separate run identity:

- Generation: `bbdb3b4f-595d-4624-9ffa-8b518363982a`
- Floor plan: `f6b65d2b-4f96-4931-9f08-67dbd09776f6`
- Design version: `62ef3454-7c52-4760-9333-d40570bb6ded`
- Provider request ID: `01a19694…` (full value was not available in the summary)
- Model: `fal-ai/flux-kontext/dev`
- Output size: `1216 × 832`
- Base SHA-256: `f37840871e0430f071eb077279eaaadeef54b1940fb4cc88ef89434fab6273e7`
- Output SHA-256: `c529cdf1774371e4a5d23e154c6682b17e0e41642f5c06033c1501f41a246429`
- Reported selected UIDs:
  - `kitchen-base-1787478607029`
  - `kitchen-base-1787478608231`
  - `chimney-1787478686293`
  - `dining-table-1787478800756`

The report said the same Kontext path produced strongly restyled bedrooms 1/2/3, a weak/clay-like Living Area, and a weak Kitchen + Dining output. This refutes any blanket statement that the model/provider is incapable of restyling, but does not establish why room outcomes differ. Verify exact records and images before relying on this comparison.

### 7.3 AIR-11 paired capture — agent-reported findings

A prior AIR-11 investigation reported that production `BaseRenderBatch.tsx` mounts `RoomScene3D` with `aiRenderMode`, `ceiling={false}`, and no `enclosed` prop (therefore `enclosed=false`), and uses the elevated dollhouse `solveAiCamera` path (reported FOV 46). A separate `solveEyeLevelCamera` path (reported FOV 72, camera height around 1.5m) was reportedly used in a harness but not production batch capture.

The agent's offline capture metrics reportedly showed:

| Room | Area | Items | Mean item area | Content % | Dark furniture % | Edge % |
|---|---:|---:|---:|---:|---:|---:|
| Living Area | 17.1 m² | 3 | 1.70 m² | 9.3% | 1.0% | 1.3% |
| Bedroom 1 | 13.3 m² | 5 | 1.16 m² | 6.7% | 3.1% | 1.2% |
| Bedroom 2 | 10.8 m² | 5 | 0.95 m² | 8.0% | 1.9% | 1.4% |
| Bedroom 3 | 14.6 m² | 5 | 1.07 m² | 7.2% | 2.1% | 1.1% |
| Kitchen & Dining | 13.8 m² | 2 | 1.42 m² | 3.3% | 0.3% | 0.7% |
| Kitchen twin | 11.1 m² | 2 | 2.17 m² | 10.1% | 0.5% | 1.3% |

The report concluded:
- A simple room-size/framing explanation was not supported by those measurements.
- Kitchen & Dining had fewer/thinner/less room-defining objects than the bedrooms.
- `contentPct` is not a clean furniture predictor because it includes floor/background contributions.
- There was no offline-safe way to add missing furniture mass without violating the canonical design.
- Lighting, shadows, and material contrast were possible presentation-only levers, but an AI benefit would require output evidence.

These are **agent-reported measurements and interpretations**, not independently verified here. Do not assume correlation proves causation.

The paired capture was reported as 14 original PNGs: seven base renders and seven structural/wireframe references. The two sets are different image types, not duplicate copies. A separate ZIP was requested for independent verification, but it has not been confirmed as uploaded in the current conversation. If unavailable, record it as unavailable and continue independent work.

The agent reported a metadata timestamp discrepancy (`2026-11-01T11:44:14.418Z` versus a later stated capture time around `11:50:18Z`). Verify the original metadata and record the exact discrepancy if present; do not silently reconcile it.

### 7.4 AIR-03 room membership — agent-reported investigation

A prior report stated that `room_membership` is optional grouping metadata on a furniture item, distinct from `render_room`; the resolver is pure and does not move furniture; saving a changed membership appends a new immutable design version; missing legacy values load as `None`; invalid values are preserved and rejected safely.

The report also described a hypothetical offline A/B test where assigning a dining table to `KITCHEN` changed room grouping but kept its transform byte-identical. The report recommended using the existing UI control for a real owner-approved design edit, rather than implementing a duplicate persistence mechanism.

Treat this as **agent-reported** until current code/tests are inspected. Do not change a user's canonical design or save a new version without explicit instruction.

### 7.5 Historical paid-generation boundary

A prior user authorization reportedly covered exactly one fal.ai Kitchen + Dining Kontext call with a hard cap of USD $0.05. An agent reported one successful POST and no retries. That historical authorization is exhausted; it is **not permission for another paid call**.

A Canny Arm B experiment was reportedly prepared offline and estimated by the agent at approximately USD $0.08, but was not authorized. Do not run it. Any future paid experiment requires fresh, explicit approval specifying provider/model, request count, and maximum budget.

---

# Part IV — Issue-by-issue resolution protocol

## 8. Use the existing AIR-01 through AIR-12 tracker

Read the entire `docs/AI_RENDER_ACCURACY_ISSUES.md` before acting. AIR-01 through AIR-12 are known to be the intended issue range, but the exact issue titles and current statuses must come from the live tracker—not from guesses in this guide.

For each AIR issue:

1. Copy its exact title and acceptance criteria from the tracker.
2. Verify status against source, tests, runtime records, and artifacts.
3. Reproduce offline where possible.
4. Trace the full data path and establish root cause.
5. Separate confirmed facts from hypotheses.
6. Define the smallest safe correction.
7. Obtain approval if the correction changes canonical data, production behavior, provider defaults, costs, or external services.
8. Implement only authorized changes.
9. Add regression tests that fail before the fix and pass after it.
10. Run targeted tests, relevant integration tests, and type/lint checks as appropriate.
11. Inspect the diff and confirm protected contracts did not change.
12. Validate relevant render artifacts, not just tests.
13. Update the same AIR tracker entry with evidence and remaining risks.
14. Continue to the next actionable issue.

Do not close an issue because a report was written, a test was removed, a validator was bypassed, or a status label changed.

### 8.1 Recommended prioritization

Use the existing tracker priorities if present. Otherwise, prioritize by dependency and risk:

**P0 — Correctness blockers**
- Wrong/stale design-version binding.
- Incorrect room/section membership or furniture inventory.
- Invalid/missing deterministic base render.
- Kitchen/Dining generation failures, if reproducible.
- Walls, doors, windows, room boundaries, or furniture geometry not preserved.
- Output validation incorrectly reports success.

**P1 — Deterministic scene and base quality**
- Incorrect furniture-to-3D model mapping.
- Incorrect room assignment or room grouping.
- Camera framing, crop, clipping, occlusion, or inconsistent viewpoint.
- Deterministic render reproducibility and capture metadata.

**P1 — AI conditioning and visual quality**
- Clay-like or weak restyling.
- Base image insufficiently informative for the target room.
- Prompt/inventory mismatch.
- Conditioning/control settings not actually applied as documented.
- Material, texture, lighting, and shadow quality.

**P2 — Workflow and observability**
- Missing provenance.
- Misleading status labels.
- Gallery comparisons or error messages.
- Performance and UX issues that do not affect geometry fidelity.

This ordering is a suggested dependency order, not a declaration that each defect exists.

---

# Part V — Technical diagnosis and fix guidance

## 9. Canonical snapshot and version binding

Investigate:
- Whether the selected immutable design version is the same version used to build the deterministic scene and AI request.
- Whether the frontend can capture a stale layout while a save is in progress.
- Whether the request includes a declared version and the backend compares it with the expected version.
- Whether room selection, floor-plan identity, and furniture manifest all refer to the same snapshot.
- Whether cache keys include the correct design version and relevant render configuration.

Potential minimal fixes, only if a defect is confirmed:
- Correct the existing version propagation or stale-state handling.
- Refuse generation when the captured base is bound to a different version.
- Invalidate only the stale cache entries proven to be incorrect.
- Add tests for layout edits during capture and for stale base/version mismatch.

Never mutate an old immutable snapshot to make it match a render.

## 10. Furniture inventory and room assignment

Investigate:
- Canonical furniture UIDs, catalog IDs, types, count, dimensions, transforms.
- Room polygon containment and boundary tolerance.
- `render_room` versus grouping metadata such as `room_membership`.
- Open-plan room merging and duplicate derived room behavior.
- Whether the base render and request inventory are constructed from the same canonical source.
- Whether doors/windows are mistakenly represented as furniture or vice versa.

Potential minimal fixes:
- Fix only the incorrect resolver, mapping, or serialization step demonstrated by reproduction.
- Preserve furniture transforms and IDs.
- Use `REVIEW_REQUIRED`, `UNVERIFIED`, or an explicit gate when room membership is ambiguous.
- Improve actionable diagnostics rather than forcing a guessed assignment.

Regression tests must cover legacy missing metadata, invalid tokens, multiple dining items, stale anchors, item duplication, and merged-section inventory where relevant and supported by current architecture.

## 11. Deterministic 3D scene reconstruction

Compare the canonical design with the deterministic scene before blaming AI.

Verify:
- Every expected furniture UID appears exactly once in the appropriate scene.
- 3D asset type matches the canonical catalog identity.
- Dimensions and transforms are derived from canonical values correctly.
- Room assignment is correct.
- Walls/openings/room boundaries are consistent with the source plan.
- Camera does not crop required geometry.
- Apparent missing items are not merely occluded, merged, too small, or outside the camera.
- The base image corresponds to the exact design version.

If the deterministic base is wrong, fix that upstream first. Do not use an AI prompt to hide a deterministic scene defect.

## 12. Camera and paired-capture investigation (AIR-11)

Before changing camera behavior:

1. Inspect the actual production capture call path.
2. Confirm which camera solver is used by the production batch, harness, and interactive viewer.
3. Record camera position, target, FOV, aspect ratio, near/far planes, projection type, room bounds, and crop.
4. Confirm `enclosed`, ceiling, wall visibility, and `aiRenderMode` flags from actual props and defaults.
5. Capture paired base and structural images from the exact same canonical snapshot and camera.
6. Verify all original image bytes, dimensions, hashes, and metadata.
7. Compare multiple confirmed rooms; do not mix uncertain duplicate/twin room captures into the primary comparison.
8. Determine whether differences come from camera/framing, actual object density, occlusion, lighting, geometry, or image-processing effects.

Do not automatically switch all rooms to eye-level camera. An eye-level view may improve furniture prominence but can hide room boundaries or openings and may not be comparable to an existing dollhouse view. Test any camera hypothesis offline first and preserve the current camera as a fallback.

Do not add furniture, enlarge furniture, alter room boundaries, or change canonical placement to improve the image.

## 13. Provider, prompt, and conditioning

Inspect actual effective request payloads, not only comments or documentation.

Verify:
- Exact provider and model identifier.
- Actual endpoint and adapter selected at runtime.
- Image input/base image and dimensions.
- Whether conditioning images are truly supplied and accepted by the endpoint.
- Control types, weights, scales, start/end values, guidance, steps, seed, strength, and other parameters that are actually supported.
- Prompt and negative prompt after all templates and inventory data are interpolated.
- Retry/fallback behavior and whether it silently changes model or conditioning.
- Provider response image dimensions and format.

A prompt saying “preserve geometry exactly” is not a geometric guarantee. Conditioning can reduce drift but must be validated against output. Do not assume that a model name or a documented ControlNet path proves the corresponding control was used.

Potential minimal fixes:
- Correct a proven request-construction bug.
- Ensure the actual canonical inventory is injected accurately.
- Correct mismatched base/output aspect handling.
- Improve prompt clarity without changing provider/model defaults.
- Add a request snapshot test that asserts the effective payload and selected model.
- Keep experimental conditioning behind an explicit, isolated feature flag if approved.

Do not introduce or activate Canny/Depth/ControlNet experiments or switch providers without explicit approval when cost or production behavior may change.

## 14. Post-generation fidelity validation

Evaluate the output in separate dimensions:

| Dimension | Required question |
|---|---|
| Presence | Is each expected object visibly present, or is it occluded/cropped/ambiguous? |
| Extras | Are there objects not in the canonical inventory? |
| Identity/type | Does each visible object correspond to the correct furniture type? |
| Count | Is each canonical object represented exactly once? |
| Position | Is placement consistent where camera comparison permits assessment? |
| Dimensions | Are relative sizes consistent where perspective permits assessment? |
| Rotation | Is orientation consistent where visible and assessable? |
| Room assignment | Is the object in the correct room/zone? |
| Architecture | Are walls, openings, boundaries, and room relationships preserved? |
| Camera | Are base and AI output sufficiently comparable? |
| Appearance | Did materials, textures, lighting, and realism improve? |
| Provenance | Can this output be tied to the exact canonical version and request? |

Do not report precise transform deltas from perspective images unless calibrated geometry or a reliable matching method supports them.

Use classifications:
- `PASS`: supported by adequate evidence.
- `FAIL`: a concrete violation is visible or measured.
- `UNVERIFIED`: evidence insufficient.
- `NOT_ASSESSABLE`: camera, occlusion, cropping, or ambiguity prevents a reliable judgment.

Human review remains required unless the detector is calibrated and validated for the actual production domain.

---

# Part VI — Coding-agent prompts

The prompts below are intended to be copied into the coding agent working in the actual repository. Run them in sequence. Do not run implementation prompts before the corresponding investigation has established root cause.

## Prompt 0 — Master mission and operating contract

```text
You are the senior engineer responsible for MyNest Design Studio's faithful 3D AI-render pipeline.

MISSION
Deliver an actual AI-generated 3D interior render that improves visual appearance while preserving the exact canonical 2D design. Do not stop after an audit, report, documentation update, or passing tests. Continue all safe, authorized, actionable work toward the real render.

MANDATORY FIRST ACTION
Inspect the actual working tree and read README.md, CORE_PIPELINE_DOCUMENTATION.md, PROJECT_CONTEXT.md, docs/AI_RENDER_ACCURACY_ISSUES.md, docs/AI_RENDER_ISSUE_EXECUTION_WORKFLOW.md, and all relevant current reports. Locate files before assuming paths. Read the complete existing AIR tracker and preserve it as the only issue register.

BASELINE
Record Git branch/commit/status if available; preserve all existing modifications. Inspect current runtime provider/model/conditioning configuration, frontend capture path, backend services/adapters, validators, persistence, gallery, canonical fixtures, generation records, base/output images, logs, and tests.

NON-NEGOTIABLE CONTRACT
Canonical 2D design + immutable versioned snapshot is authoritative. AI may change appearance only. It must not change furniture identity/type/count/position/dimensions/rotation/room assignment, walls, room boundaries, doors, windows, or intended geometry. Deterministic rendering remains fallback.

EXECUTION
For every AIR issue: reproduce, trace the full path, establish root cause, define minimal fix, implement only when authorized, add regression coverage, run relevant tests, inspect diff, validate output evidence, update the existing tracker, then continue to the next actionable issue.

EVIDENCE
Label every claim VERIFIED, AGENT-REPORTED, INFERRED, or UNKNOWN. Do not invent paths, IDs, hashes, tests, pricing, or generation outcomes. Separate CONTRACT_VALID from output fidelity. Use UNVERIFIED/NOT_ASSESSABLE when evidence is insufficient.

SAFETY
Do not make paid provider calls, incur cost, change production defaults, deploy, modify canonical user designs, or perform destructive actions without explicit approval. Historical approval is not reusable. Continue offline-safe work while waiting.

STOP CONDITIONS
Stop only the affected operation if a genuine dependency or ambiguity blocks it. Continue independent safe work. Ask for the minimum specific approval/input needed. Never fabricate a render or mark an issue fixed without evidence.

DELIVERABLES
Maintain the existing AIR tracker; provide exact files changed, root cause, test commands/results, output artifacts and provenance, remaining risks, blockers, approval needed, and the next concrete action. Report actual Git status if available. Do not claim success without evidence.
```

## Prompt 1 — Read-only full baseline and issue reconciliation

```text
TASK: REPORT-ONLY BASELINE. Do not edit code, docs, fixtures, datasets, records, canonical designs, configuration, or application state. Do not call any AI provider.

Read all mandatory project documentation and the complete existing docs/AI_RENDER_ACCURACY_ISSUES.md. Inspect current source, tests, runtime configuration, available generation records, and artifacts.

For AIR-01 through AIR-12, copy the exact existing title and status from the tracker. For each issue report:
- What the issue actually claims.
- Current source files/functions involved.
- Reproduction evidence and exact commands.
- Tests that cover it and gaps.
- Artifact/provenance availability.
- Confirmed root cause, or hypotheses still open.
- Dependencies and risk.
- Whether offline-safe work is possible.
- Acceptance criteria.

Verify the latest multi-section run separately from the Kitchen + Dining v84 run. Do not conflate them. Verify the design version, room/section mapping, canonical inventory, base image, AI output, provider/model, request payload, IDs, hashes, and validation status where available.

For AIR-11, inspect production camera/capture wiring and paired captures. Do not assume the prior agent's camera or sparse-object conclusions are correct. For AIR-03, independently inspect room_membership versus render_room semantics and persistence; do not mutate any design.

Output: a concise verified baseline, an AIR issue matrix, root-cause findings, evidence gaps, and a dependency-ordered execution queue. No edits and no paid calls.
```

## Prompt 2 — Root-cause investigation for one AIR issue (read-only)

```text
TASK: Investigate ONLY [AIR-ID — exact tracker title]. REPORT-ONLY; no edits and no paid provider calls.

Read the exact tracker entry and relevant project docs. Inspect all source paths from UI action to persisted output. Reproduce the issue offline where possible. Capture exact commands, test results, logs, request/response data, and artifact identities.

Trace:
UI selection/request → canonical version → room membership/inventory → deterministic scene → camera/base capture → base contract → provider request → provider response → output persistence → post-validation → gallery status.

Distinguish verified facts from hypotheses. Identify the earliest responsible stage and explain why downstream symptoms occur. Check backward compatibility and protected contracts.

Deliver:
1. Reproduction steps and evidence.
2. Confirmed root cause or explicit unresolved hypotheses.
3. Exact files/functions involved.
4. Minimal proposed correction.
5. Regression tests required.
6. Acceptance criteria.
7. Risks/dependencies and whether approval is needed.
8. Existing AIR tracker status recommendation.

Do not implement. Do not claim root cause confirmed if the evidence is ambiguous.
```

## Prompt 3 — Implement one confirmed offline-safe fix

```text
TASK: Implement the approved minimal fix for [AIR-ID]. Root cause and scope have already been confirmed in the investigation report: [PASTE REPORT/DECISION].

Before editing, re-read the relevant current source and inspect Git/working-tree state. Preserve unrelated user changes.

SCOPE
Only change the exact files and behavior required to fix the confirmed root cause. Preserve canonical geometry, furniture transforms/inventory, APIs, schemas, coordinate systems, provider defaults, and backward compatibility. Do not refactor unrelated code or introduce dependencies.

REQUIREMENTS
- Add regression tests that fail for the reproduced defect before the fix.
- Cover relevant legacy, invalid, edge, and failure cases.
- Do not weaken or delete existing tests.
- Do not silently coerce uncertain room/furniture/opening placement.
- Keep deterministic fallback behavior intact.
- Do not make paid calls or alter production configuration.

VALIDATION
Run focused tests first, then relevant integration tests, type checking/linting as appropriate. Provide exact commands and unedited results. Inspect the full diff and confirm no unrelated files or contracts changed.

DELIVER
Root cause, implementation summary, changed files, tests/results, diff review, remaining risks, tracker update proposal, and next issue to investigate. Do not mark FIXED_AND_VERIFIED until the relevant acceptance criteria and output evidence pass.
```

## Prompt 4 — Deterministic 3D baseline and capture audit

```text
TASK: Verify deterministic scene fidelity before further AI experiments. Offline/read-only first. No paid calls and no canonical design edits.

Select the exact immutable canonical design version used by the target benchmark. Verify snapshot identity and integrity. Build or inspect the deterministic scene from that snapshot.

Compare:
- Canonical furniture UIDs, catalog IDs/types, counts, dimensions, positions, rotations, room assignments.
- Scene meshes and their source item IDs.
- Room polygons, walls, doors, windows, and opening relationships.
- Camera framing, clipping, occlusion, crop, FOV, aspect ratio, projection, and camera target.
- Base-render identity, dimensions, and hash.
- Repeatability of the capture.

Do not count a visually occluded object as missing without further evidence. Do not infer exact transforms from an uncalibrated perspective image.

If a deterministic defect is found, report root cause and minimal fix proposal. Implement only if separately authorized. Output a canonical-to-scene reconciliation table and a deterministic baseline acceptance decision.
```

## Prompt 5 — AIR-11 paired-capture and camera root-cause investigation

```text
TASK: Investigate AIR-11 using original paired room captures. Do not change code or camera defaults. Do not make paid AI calls.

Verify the original paired-capture archive:
- Expected 7 base PNGs and 7 structural PNGs, if that is the actual manifest.
- Exact dimensions and PNG validity.
- SHA-256 values against the supplied checksum file.
- Metadata JSON validity and room/version/camera fields.
- Exact capture timestamp and any discrepancies.
- Confirmed rooms versus uncertain duplicate/twin rooms.

Inspect production BaseRenderBatch and RoomScene3D wiring. Confirm actual camera solver, camera position/target, FOV, aspect ratio, projection, enclosed/ceiling/wall visibility, and render flags. Compare production batch, harness, and interactive viewer separately.

Compare confirmed bedroom bases with Living Area and Kitchen + Dining. Determine whether the evidence supports camera framing, sparse object silhouettes, occlusion, room geometry, lighting/contrast, or another cause. Do not treat simple content percentage as a furniture detector. Do not assume correlation proves causation.

Deliver verified image/camera measurements, visual observations, uncertainty labels, and the smallest offline experiment that could discriminate between remaining hypotheses. Preserve the current camera path as fallback. No implementation and no paid calls.
```

## Prompt 6 — Offline presentation-only experiment (no AI generation)

```text
TASK: Design and, only if explicitly authorized, implement a reversible offline experiment for the confirmed presentation issue. No provider calls and no canonical geometry changes.

Candidate variables may include camera framing, lighting, shadows, material contrast, exposure, and capture consistency—but test only variables supported by the AIR-11 evidence.

Create paired deterministic captures from the exact same immutable design version:
- Control: current production base-render settings.
- Experiment: one isolated presentation-only variable changed.
Keep camera, geometry, furniture, dimensions, transforms, room membership, image size, and all other variables constant unless the experiment specifically tests camera framing.

Record configuration, image hashes, dimensions, and visual comparison. Do not claim that a deterministic visual improvement will improve AI output; it only establishes a better/worse conditioning candidate.

Do not alter production defaults. Use a temporary harness or isolated feature flag and provide a rollback plan. If an experiment would affect production behavior, ask for approval first.
```

## Prompt 7 — Prepare a bounded live AI benchmark (no call yet)

```text
TASK: Prepare, but DO NOT execute, the next AI-render benchmark.

Inspect the current provider adapter and exact effective request construction. Confirm:
- Provider and exact model identifier.
- Endpoint and adapter selected at runtime.
- Base image identity/hash/dimensions.
- Canonical design version and room.
- Positive/negative prompt after interpolation.
- Conditioning images, controls, weights, and supported parameters.
- Number of requests and retry behavior.
- Output persistence and validation path.
- Deterministic fallback behavior.

Select the smallest benchmark that can test one explicit hypothesis. Prepare exact commands/application steps, request parameters, expected artifacts, comparison checklist, rollback/fallback, and an estimated cost using current provider pricing. Clearly label estimates and unknown funding status.

Do not probe the provider. Do not make a request. Do not assume historical approval or funding. Return the exact approval statement the owner would need to authorize this bounded run.
```

## Prompt 8 — Execute an explicitly approved live benchmark

```text
TASK: Execute ONLY the benchmark explicitly approved by the owner below. Do not exceed its provider/model, request count, or cost cap.

APPROVAL:
[PASTE THE OWNER'S EXACT APPROVAL, PROVIDER/MODEL, REQUEST COUNT, AND MAXIMUM BUDGET]

Before the call, verify the selected canonical version, room, base hash, request payload, provider/model, and budget. If any differ from approval, STOP and ask.

Execute through the existing project adapter only. No provider replacement, silent fallback, retry beyond the approved count, or production-default change.

Record request ID, provider response, input/output hashes, dimensions, parameters, timestamps, cost evidence if available, and errors. Compare output with the matching base and canonical design using the fidelity checklist.

Reject any output that changes geometry or furniture. Do not retry with extra spending. Deliver actual artifacts and an honest PASS/FAIL/UNVERIFIED assessment.
```

## Prompt 9 — Output fidelity review and issue closure

```text
TASK: Review the actual generated output against its exact canonical design and matching base render. Do not generate another image.

Verify provenance first: canonical version, floor plan, room, furniture manifest, provider/model, conditioning, base hash, output hash, generation/request ID, dimensions, and prompt.

Assess separately:
1. Object presence and missing/extra objects.
2. Identity/type and count.
3. Position, dimensions, rotation, room assignment where measurable.
4. Walls, room boundaries, doors, windows, and architecture.
5. Camera/perspective comparability.
6. Material, texture, lighting, shadow, and visual quality.
7. Reproducibility and provenance completeness.

Classify every criterion PASS, FAIL, UNVERIFIED, or NOT_ASSESSABLE with evidence. Distinguish occluded, merged, cropped, and visually ambiguous objects from truly missing objects. Do not report precise transform differences without calibrated evidence.

Update the existing AIR issue only if its acceptance criteria are satisfied. Keep contract validation separate from visual fidelity. Human review is required unless detector calibration is demonstrated.
```

## Prompt 10 — Final end-to-end release gate

```text
TASK: Determine whether MyNest Design Studio has demonstrated a faithful AI-render result for the approved benchmark. Do not change code or generate new outputs during this review.

Verify:
- Canonical snapshot remains unchanged.
- Deterministic 3D scene matches canonical design.
- Actual AI output exists and is linked to the exact version/room.
- Base and AI output are paired and comparable.
- Furniture inventory, identity, placement, dimensions, rotation, and room assignment are preserved where assessable.
- Walls, doors, windows, and room structure are preserved.
- Visual appearance improved without violating the design contract.
- Relevant tests and integration checks pass.
- Provenance and output artifacts are reproducible.
- Every AIR issue is verified closed, not reproducible, or explicitly unresolved with evidence and next action.

Return a release decision: ACCEPTED FOR THIS BENCHMARK, REJECTED, or UNVERIFIED. Never generalize a small benchmark to all rooms or production-wide accuracy. If not accepted, state the next smallest evidence-supported action.
```

---

# Part VII — Regression and acceptance criteria

## 15. Minimum regression coverage

Use existing test conventions and add only relevant tests. Candidate coverage:

### Canonical/version
- Stale version is rejected.
- Base render version must match the selected immutable snapshot.
- Editing during capture cannot silently bind output to the wrong version.
- Old snapshots remain immutable.

### Furniture and room assignment
- Each canonical UID appears exactly once in the correct scene/render set.
- Identity/type/count/transforms remain unchanged through serialization and scene assembly.
- Legacy optional metadata remains backward compatible.
- Invalid/ambiguous membership fails safely and visibly.
- Merged open-plan sections produce the correct inventory without moving furniture.

### Deterministic rendering
- Correct furniture mesh mapping.
- Correct dimensions/transforms and room membership.
- Walls/openings are preserved.
- Camera/capture does not silently crop required content.
- Same inputs/configuration produce reproducible base output within documented tolerances.

### Provider request
- Runtime provider/model is the configured one.
- Correct base image and canonical inventory are sent.
- Effective prompt and controls match the expected request.
- Unsupported controls are not silently assumed to work.
- Retry/fallback does not silently switch provider/model.

### Output validation and persistence
- Empty/invalid output is rejected.
- Output dimensions/aspect handling is correct.
- Provenance links to the exact base and canonical version.
- A contract-valid request does not automatically become `FAITHFUL`.
- Unassessable output remains `UNVERIFIED` / `not_assessable`.

## 16. Acceptance gate for an actual faithful render

A benchmark output can be accepted only if all applicable criteria are evidenced:

- Correct canonical version and room.
- Correct base image identity.
- Furniture presence/count/type preserved.
- No additional or duplicated furniture.
- Placement/orientation/size preserved where reliably assessable.
- Walls, doors, windows, and room structure preserved.
- Camera comparison adequate for the claims made.
- Visual improvements are real and do not compensate for geometry failure.
- Provenance complete enough to identify and reproduce the run.
- Human review recorded.

If one required criterion is uncertain, do not label the output `FAITHFUL`. Use `UNVERIFIED` or `NOT_ASSESSABLE`.

---

# Part VIII — Execution log template

## 17. Record each execution cycle

Append to the appropriate existing report or AIR tracker entry; do not create duplicate trackers.

```text
Cycle:
Date/time:
AIR issue:
Scope: REPORT-ONLY / IMPLEMENTATION / VALIDATION
Canonical project/floor/floor-plan:
Design version ID:
Room/section:
Generation ID:
Provider/model:
Conditioning:
Base image path + SHA-256:
Output image path + SHA-256:
Prompt/request identity:
Root cause:
Evidence classification:
Files changed:
Tests run (exact commands):
Test results:
Visual review:
Canonical geometry decision:
Furniture fidelity decision:
Architecture fidelity decision:
Provenance decision:
Cost/approval:
Remaining risks:
Git branch/commit/status:
Next concrete action:
```

## 18. Final reporting format for each substantial cycle

The coding agent must report:

1. **Objective and scope**
2. **Verified baseline**
3. **Root cause(s)**
4. **Changes made and exact files**
5. **Tests and exact results**
6. **Render artifacts generated/reviewed**
7. **Fidelity decision and supporting evidence**
8. **AIR tracker updates**
9. **Remaining issues and blockers**
10. **Paid/production approval required**
11. **Next concrete action toward the actual render**
12. **Git status and risks**

---

# Part IX — Immediate next execution sequence

## 19. What the coding agent should do next

Run these in order:

1. **Prompt 1:** read-only baseline and AIR-01…AIR-12 reconciliation.
2. **Prompt 2:** investigate the highest-priority reproducible issue, one issue at a time.
3. **Prompt 3:** implement only confirmed offline-safe fixes after scope approval.
4. **Prompt 4:** establish deterministic 3D correctness for the exact benchmark design version.
5. **Prompt 5:** independently verify AIR-11 paired-capture and camera evidence.
6. **Prompt 6:** run only a reversible offline presentation experiment if supported by evidence and authorized.
7. **Prompt 7:** prepare the exact bounded live AI benchmark without calling the provider.
8. Request fresh owner approval for the specific paid run.
9. **Prompt 8:** execute only the approved benchmark.
10. **Prompt 9:** assess the actual output and update the existing AIR tracker.
11. **Prompt 10:** apply the end-to-end release gate.

Do not wait for a paid benchmark to complete independent offline fixes. Do not run the paid benchmark before the deterministic base and provenance are verified.

## 20. Current known next step

The most recent AIR-11 agent report says the 14 original paired PNGs (7 base + 7 structural) were persisted in:

`D:\Latest_mynest_design_version\mynest-design-studio\air11_paired_capture_v84\`

This is **agent-reported**, not independently verified by this document's author. The next evidence action is to obtain the archive in the review environment and verify image inventory, dimensions, checksums, metadata, and visual pairs. If the archive is not available to the coding agent, it must record the gap and continue other independent baseline work.

The separate `latest_output_3d.zip` and v84 Kitchen + Dining generation must not be conflated. Keep their canonical versions, generation IDs, and provenance separate.

**Mission status:** INCOMPLETE until an actual AI-generated output is reviewed and shown to satisfy the canonical geometry/furniture contract. A report, offline test pass, or prepared benchmark is progress—not completion.
