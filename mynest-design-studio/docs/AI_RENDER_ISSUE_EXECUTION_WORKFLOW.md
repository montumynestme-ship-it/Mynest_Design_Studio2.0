# MyNest Design Studio — AI Render Issue Execution Workflow

**Document type:** Master execution workflow and coding-agent operating instructions
**Project:** MyNest Design Studio
**Status:** Ready for coding-agent use; initial issue statuses must be verified against the live repository
**Primary tracker:** `docs/AI_RENDER_ACCURACY_ISSUES.md` — already exists; preserve and update it
**Scope:** Latest 3D AI render investigation, root-cause analysis, minimal fixes, regression tests, and evidence-based closure

---

## 1. Purpose

Use the latest supplied `latest_output_3d.zip`, the supplied room-membership investigation Markdown, existing project documentation, source code, test suite, and stored generation artifacts to systematically investigate and resolve the current 3D AI-render issues.

This document defines **how to work**. It is not a replacement issue register.

The existing `docs/AI_RENDER_ACCURACY_ISSUES.md` remains the single source of truth for AIR issue IDs, statuses, evidence, owners/agents, dependencies, and closure decisions. Do not create a second competing AIR tracker and do not overwrite the existing tracker.

Work sequentially:

1. Review project context and existing tracker.
2. Establish the exact latest-render baseline.
3. Verify each issue and its evidence.
4. Identify root cause.
5. Plan the smallest safe correction.
6. Implement only confirmed, authorized fixes.
7. Run regression and integration tests.
8. Validate deterministic and AI-render evidence separately.
9. Update the existing tracker.
10. Continue to the next actionable issue.

Do not stop after writing an audit if safe and authorized implementation work remains.

## 2. Mandatory project-context review

Before editing, locate and read the actual current versions of:

- `README.md`
- `CORE_PIPELINE_DOCUMENTATION.md`
- `PROJECT_CONTEXT.md`
- `docs/AI_RENDER_ACCURACY_ISSUES.md`
- `AI_RENDER_FIDELITY_WORKFLOW.md` or its actual equivalent
- Existing pipeline audit, base-render, AI-render, and fix reports
- The supplied room-membership investigation Markdown
- Relevant provider, scene, validation, and rendering documentation

Do not assume a path exists. Record missing documents as gaps.

Inspect:

- Git branch, commit, and working-tree status if this is a Git repository
- Existing uncommitted changes and prior agent work
- Frontend and backend runtime configuration
- Current provider/model/conditioning settings
- Generation records, canonical snapshots, base renders, AI outputs, manifests, hashes, logs, and test results

Preserve existing user work. Never reset, clean, overwrite, or discard unrelated changes.

## 3. Latest render baseline

Use the supplied `latest_output_3d.zip` and its four screenshots as the visual starting evidence. Extract and inspect the actual files. Do not substitute illustrative images or web images.

The screenshots previously showed the following UI-reported facts:

- 4 of 6 sections generated
- Kitchen and Dining Area failed
- 179 walls extracted
- 5 of 7 rooms proven
- Geometry uncertain
- Deterministic furniture fidelity displayed as 100%
- AI furniture fidelity displayed as Not Verified
- AI geometry displayed as NOT PROVEN
- Base path described as image-to-image, with base not §L-verified

These are **screenshot-reported**, not independently verified backend facts. Verify them against current database records, API responses, stored artifacts, logs, and code.

Establish and record the exact association between screenshots and:

- Project/floor/floor-plan ID
- Canonical design version and immutable version ID
- Furniture manifest and transforms
- Room/section mapping
- Base-render file and SHA-256
- AI output file and SHA-256
- Generation ID and provider request ID
- Prompt and effective request body
- Validation results and failure codes

Do not assume that the earlier Kitchen + Dining v84 generation is the same run or same version as the screenshots. Prove the association.

If an artifact is unavailable, record `UNAVAILABLE` and continue independent work. Do not invent hashes, identifiers, or provenance.

## 4. Canonical design contract

The canonical 2D design and its immutable versioned snapshot are the source of truth.

AI must not change:

- Furniture identity, type, inventory, or count
- Furniture position, dimensions, rotation, or room assignment
- Room boundaries, wall geometry, or room relationships
- Door/window identity, placement, dimensions, or intended geometry

AI may improve only visual appearance, materials, textures, lighting, shadows, finishes, and styling.

Keep deterministic rendering as the trusted fallback until AI fidelity is demonstrated with sufficient output-level evidence.

A successful provider response, passing input gate, changed image hash, or attractive image does not prove output fidelity.

## 5. Existing issue tracker — mandatory handling

`docs/AI_RENDER_ACCURACY_ISSUES.md` already exists.

Before adding or changing issues:

1. Read the complete existing file.
2. Preserve its AIR IDs, history, decisions, and useful evidence.
3. Reconcile new findings with existing IDs; do not duplicate issues.
4. Keep closed historical issues and their closure evidence intact.
5. Add newly discovered issues only when they are genuinely distinct.
6. Update status only when the required evidence exists.
7. Record each implementation/test result in the existing issue entry.

Do not replace the issue register with this workflow document. This document explains the process; the existing issue register tracks the work.

Recommended status lifecycle, unless the tracker already defines an equivalent:

`OPEN → INVESTIGATING → ROOT_CAUSE_CONFIRMED → FIX_PLANNED → IMPLEMENTING → TESTING → FIXED_AND_VERIFIED`

Other valid statuses include `BLOCKED`, `UNVERIFIED`, `NOT_REPRODUCIBLE`, and `REJECTED`.

Do not mark an issue `FIXED_AND_VERIFIED` solely because code was changed or tests passed. The acceptance criteria and relevant output evidence must also pass.

## 6. Investigation method for every issue

For each existing AIR issue, use this sequence:

### 6.1 Reproduce and establish evidence

- Identify the exact design version and generation.
- Reproduce offline where possible.
- Capture the actual error, status, response, and relevant logs.
- Inspect the responsible frontend and backend paths.
- Inspect persisted artifacts and provenance.
- Run the existing relevant tests before editing.

### 6.2 Trace the root cause

Follow the complete data path:

- UI selection and request construction
- Canonical snapshot/version binding
- Region/room selection and membership resolution
- Base scene assembly and deterministic capture
- Base-render contract and §L validation
- Provider/model/conditioning request construction
- Provider response and output persistence
- Post-generation validation and gallery presentation

Distinguish confirmed defects from hypotheses. If multiple causes remain plausible, record them separately and design offline tests to discriminate between them.

### 6.3 Define the minimal correction

Before editing, document:

- Confirmed root cause
- Exact files/functions involved
- Expected behavior change
- Protected contracts
- Risks and dependencies
- Regression tests
- Acceptance criteria

Do not implement a speculative fix merely to make the UI show success.

## 7. Initial priority order

Use the existing tracker’s priorities if already established. Otherwise, consider this initial order and revise it only with evidence:

### P0 — Canonical geometry and generation blockers

- Kitchen generation failure
- Dining Area generation failure
- Base render not §L-verified
- Only 5/7 rooms proven
- Incorrect or stale canonical version binding
- Region/room inventory mismatch
- Invalid wall/opening/room reconstruction

### P0 — Output fidelity evidence

- AI furniture fidelity not verified
- AI geometry not proven
- Missing/extra/merged/ambiguous furniture
- Wall, door, or window preservation uncertainty
- Insufficient output provenance

### P1 — Deterministic scene quality

- Furniture model mapping and geometry
- Room-to-scene associations
- Camera framing and crop
- Deterministic render consistency

### P1 — AI visual quality and conditioning

- Clay-like or weakly restyled output
- Prompt preservation dominance
- Base-image suitability
- Conditioning strategy and control parameters
- Material, texture, lighting, and shadow quality

### P2 — Workflow and observability

- Validation status accuracy
- Provenance completeness
- Gallery and failure reporting
- Performance or UX issues that do not affect fidelity

This is a candidate ordering, not proof that every listed issue exists. Reconcile it against the current issue tracker.

## 8. Room-membership investigation — how to use it

The supplied room-membership Markdown is a report-only investigation. Its reported findings include:

- `room_membership` is grouping metadata on a furniture item.
- Allowed tokens reported: `KITCHEN`, `LIVING_AREA`, `INDEPENDENT_DINING`.
- It is distinct from `render_room`, which the report identifies as the field that moves an item between render sets.
- Saving a changed membership appends a new immutable design version.
- Legacy missing values load as `None`.
- Invalid values are stored verbatim and rejected by the resolver.
- The reported offline reproduction found the dining-table transform byte-identical before and after hypothetical membership assignment.

Treat these as agent-reported investigation findings until independently confirmed in the current repository.

Do not reimplement a verified contract. Do not infer that grouping metadata proves AI output room assignment or geometry fidelity. Verify current code and tests before relying on the report.

## 9. Implementation rules

After root cause is confirmed:

1. Make the smallest evidence-supported change.
2. Preserve APIs, data contracts, coordinate systems, canonical snapshots, and business logic.
3. Preserve backward compatibility.
4. Add regression tests for the defect and relevant edge cases.
5. Do not weaken existing tests or alter expected results to force a pass.
6. Do not introduce unrelated refactors, migrations, dependencies, provider changes, or new features.
7. Inspect the complete diff.
8. Run targeted tests, relevant integration tests, lint, and type checks.
9. Update the existing issue tracker with exact evidence.

If a fix would change canonical geometry, furniture transforms, production behavior, or an external contract, stop and request approval.

## 10. Validation and evidence requirements

Report exact commands and actual outcomes.

For each fix, include:

- Tests run and pass/fail counts
- Relevant test output or failure details
- Changed files and reason
- Diff summary
- Regression cases covered
- Before/after behavior
- Remaining risks

For render validation, assess separately:

1. Object presence and missing/extra objects
2. Object identity and type
3. Count
4. Position, dimensions, rotation, where measurable
5. Room assignment
6. Walls, doors, and windows
7. Camera and perspective comparability
8. Visual appearance improvement
9. Provenance and reproducibility

Do not report precise transform differences if camera framing or perspective makes the comparison unreliable. Distinguish missing objects from occluded, merged, cropped, or visually ambiguous objects.

Use `UNVERIFIED` or `not_assessable` when evidence is insufficient. Keep contract/input validation separate from output fidelity.

## 11. Paid generation and external dependencies

No paid AI/API calls are authorized by this workflow.

For any future generation experiment:

- Prepare an offline benchmark plan first.
- Verify the exact provider, model, endpoint, parameters, base image, and design version.
- Estimate cost from current authoritative pricing.
- State the number of requests and maximum budget.
- Obtain separate explicit approval before any charge-incurring request.
- Do not retry, create variations, or switch models without authorization.

The earlier US$0.05 Kontext authorization was for the completed single Kontext request only. It does not authorize a future Canny or other provider request.

## 12. Working cadence

Work in small, reviewable cycles:

**Cycle 1:** baseline, repository context, existing issue tracker reconciliation, artifact provenance.
**Cycle 2:** investigate P0 generation/base/room-proof failures.
**Cycle 3:** fix confirmed P0 defects and run regression tests.
**Cycle 4:** verify deterministic scene and canonical furniture mapping.
**Cycle 5:** investigate AI output fidelity and validation gaps.
**Cycle 6:** investigate visual restyling and conditioning.
**Cycle 7:** implement approved minimal corrections and validate.
**Cycle 8:** close only evidence-supported issues and report remaining blockers.

After each cycle, continue to the next independent actionable issue. A blocked issue does not justify abandoning unrelated safe work.

## 13. Stop conditions

Stop a specific change if:

- Root cause is unsupported by evidence.
- Canonical geometry or furniture transforms would be altered.
- Existing user changes could be overwritten.
- A paid call or production change is required.
- A provider/model/architecture change is required without approval.
- Required artifacts are unavailable and no safe offline path exists.

When blocked, record the exact missing dependency, complete independent work, and leave the issue honestly marked.

## 14. Final reporting

At the end of each cycle, report:

- What was inspected and verified
- What remains agent-reported or inferred
- Root causes confirmed
- Files changed and why
- Exact tests and results
- Issue tracker entries updated
- Issues fixed and verified
- Issues still open, blocked, or unverified
- Git status
- Next concrete issue to investigate

Never fabricate repository inspection, test results, hashes, render artifacts, costs, or successful outcomes.

---

## Final execution instruction

Follow this workflow and maintain `docs/AI_RENDER_ACCURACY_ISSUES.md` as the single source of truth.

Do not create a duplicate AIR tracker. Do not stop after writing reports. Investigate, implement, test, and validate each confirmed issue in priority order, while preserving the canonical 2D design and all existing project contracts. The goal is a demonstrably faithful and visually improved 3D AI render, not merely a passing test suite.
