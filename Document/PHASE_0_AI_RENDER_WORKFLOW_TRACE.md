# Phase 0 — AI Furniture-Render Workflow: Trace, Finding, and Scope Decision

**Mode:** trace-before-editing (as the task mandates). **Outcome:** the "new" canonical‑manifest / validation / preservation‑prompt pipeline is **already the single live AI‑render integration** (built/hardened across Steps 2K–2U); there is **no separate "old furniture‑to‑AI‑render integration" to disable or replace**, and the **Furniture Library is a decoupled editor component already fully preserved**. A disable/replace would risk a working pipeline on a premise the trace refutes, so I did **not** perform it. I added verification tests only; **no production code was changed**, no assets/APIs/data models/canonical records touched.

---

## 1. Verified call path (traced from source, not assumed)
**AI Render button → request:** `DesignStudio.tsx` "AI Render" (`:837`) runs one deterministic capture (`BaseRenderBatch`) then `generateDesign(planId, …)` (`lib/generations.ts:118` → `POST /api/floor-plans/{planId}/generate`). The request body carries **only**: `design_intent` (incl. the free‑text theme), `all_sections`, `fresh_generation`, `base_renders` (deterministic PNG captures keyed by room), and `base_render_meta` (design‑version + room + dims binding). **No furniture/inventory is sent from the client** (`DesignStudio.tsx:619‑627`).

**Request schema (VERIFIED):** `schemas/generation.GenerationRequestBody` has fields `{provider, count, design_intent, rooms, all_sections, fresh_generation, base_renders, base_render_meta}` — **no `furniture`/`inventory`/`manifest`/`items`/`objects`**. A client therefore cannot inject or bypass the canonical inventory.

**Backend generation (VERIFIED):** `generation_service.generate()` (`:1291`) takes furniture **only** from `floor_plan_service.capture_generation_snapshot(file_id)` (`:1341‑1342`) — the **immutable, versioned** design snapshot (`[SNAPSHOT] generation bound to design_version_id=…`). From that snapshot it:
1. extracts the canonical furniture inventory;
2. builds the **version‑bound** per‑room manifest (`furniture_manifest.room_manifest`, consuming the same snapshot grouping);
3. builds the **preservation prompt** (`fal_flux_adapter._build_fal_edit_prompt`: exact‑inventory lead + structural‑preservation preamble + decor prohibition + negatives last);
4. passes the manifest + effective prompt through the provider adapter (`registry.get_adapter`);
5. assigns an **honest** output status (`validation_service.assess_ai_render(output_verified=False)` → `UNVERIFIED`; never `FAITHFUL` without structural conditioning — Step 2R guard);
6. keeps the **deterministic render as the trusted fallback** (base render + `BASE_RENDER_*` contract; no text‑to‑image).

**Mismatched‑manifest guard (VERIFIED):** the base‑render contract (`:1571‑1598`) validates each base render's `base_render_meta.design_version_id` against `expected_version_id=snapshot_version_id` → a base captured from a **different** version than the generation snapshot is rejected (`BASE_RENDER_WRONG_VERSION/ROOM/SIZE`) before it can reach the provider. Manifest and base are both bound to the same immutable version.

**Furniture Library (VERIFIED separate):** `components/design-studio/FurnitureLibrary.tsx` has **zero** references to `generateDesign`/`/generate`/AI Render — it is a pure editor component. The Library places furniture → `save_layout` → a new immutable canonical version; the AI render later reads that **saved snapshot**. The Library is upstream of the canonical design, **not** part of the AI‑render furniture‑gathering path.

## 2. Finding: the task's "old vs new" split does not exist
There is **one** AI‑render furniture workflow, and it is already the manifest‑based pipeline the task describes as the "new" replacement:

| Task's "new pipeline" step | Current live state |
|---|---|
| Extract inventory from the immutable canonical snapshot | **Done** (`capture_generation_snapshot`) |
| Version‑bound furniture manifest + validation | **Done** (`furniture_manifest` + base‑render version contract + inventory gate `BASE_INVENTORY_MISMATCH`) |
| Furniture‑preservation prompt from the validated manifest | **Done** (`_build_fal_edit_prompt`, hardened in 2S) |
| Pass manifest + effective prompt through the provider adapter | **Done** (+ `effective_prompt.txt`/`conditioning_mode` provenance, 2S/2R) |
| Assess the generated **image** for missing/extra/changed | **NOT wired in‑path** (see §4) — capability exists, blocked |
| Preserve `UNVERIFIED`/`NOT_VALIDATABLE` when evidence insufficient | **Done** (2R/2U; no false `FAITHFUL`) |
| Deterministic render as trusted fallback | **Done** |

So "temporarily disable the old integration and replace it" is a **no‑op**: there is nothing distinct to disable, and the replacement components are already the live path. Executing a disable/replace would risk breaking a working, tested pipeline for no benefit — out of line with "smallest reversible change."

## 3. Acceptance criteria — status against the existing pipeline
| criterion | status | evidence |
|---|---|---|
| Furniture Library visible/usable; editing/placement work | **Preserved (untouched)** | `FurnitureLibrary.tsx` decoupled; frontend `tsc --noEmit` exit 0 |
| Old AI‑render furniture integration disabled/replaced at the intended point | **N/A — already the manifest pipeline** (no separate old path) | §1 trace |
| Manifest/prompt use the correct canonical design version | **Yes** | snapshot binding + base‑render version contract; new test |
| Invalid/mismatched manifests cannot silently enter the request | **Yes** | request carries no furniture; base‑render `WRONG_VERSION` guard; new test |
| Output assessment handles missing/extra honestly | **Yes (capability + honest status)**; in‑path image assessment not wired (§4) | 2U output‑validation tests; `UNVERIFIED`/`NOT_VALIDATABLE` |
| Deterministic fallback intact | **Yes** | base‑render contract; no text‑to‑image |
| Unrelated editor functionality unaffected | **Yes (no change made)** | no production code changed; tsc exit 0 |

## 4. The one genuine gap (blocked, out of Phase‑0 scope)
Assessing the **generated image** (not just the input design) for missing/extra furniture requires: (a) the deterministic base's **screen‑space furniture boxes** (currently a frontend‑only artifact from `BaseRenderBatch`, not threaded to the backend) to build the object registry, and (b) a **calibrated** detector (OWLv2 weights + a labelled corpus — `validate_objects`/`run_geometry_validation` report `NOT_CALIBRATED`/`NOT_VALIDATABLE` until then). Both are non‑trivial and blocked — not a small reversible Phase‑0 change. The capability is present and test‑covered (Step 2U); wiring it is a separately‑scoped task (thread base boxes + calibrate), and the proven **visual** cure (Canny structural conditioning, Step 2T) needs authorized paid strength‑tuning.

## 5. What I changed
- **Production code: none.** No furniture assets/APIs/data models/canonical records/IDs/transforms/room assignments changed; Furniture Library and editor untouched; provider/model defaults unchanged; deterministic fallback intact.
- **Tests added (offline, no DB writes):** `backend/tests/test_ai_render_furniture_source.py` — (1) the generation request carries **no** client furniture (only snapshot‑sourced inventory can enter); (2) every per‑room manifest furniture uid is a real uid of the **canonical snapshot version** (version‑bound, never invented).

## 6. Tests & build — commands and results
```
pytest -q tests/test_ai_render_furniture_source.py tests/test_output_fidelity_validation.py
         tests/test_prompt_preservation.py                 → 12 passed (exit 0)
frontend: ./node_modules/.bin/tsc --noEmit                 → exit 0 (editor + Furniture Library intact)
```

## 7. Git / diff
App is not a git repository (only `floorplan-parser/.git`) → no `git diff`. **Changed this step: one new test file** (`backend/tests/test_ai_render_furniture_source.py`) + this report. No other files touched.

## 8. Recommendation / next action
- **Do not** perform a disable/replace: the trace shows the canonical‑manifest pipeline is already the sole live AI‑render integration, and the Furniture Library is already preserved. Treat Phase 0 as **verified‑already‑in‑place**.
- **Next real step** (separately scoped): wire the output‑image fidelity assessment in‑path — thread the deterministic base's furniture screen‑space boxes to the backend and record a non‑gating `NOT_VALIDATABLE` advisory until a detector is calibrated — and run the authorized Canny `control_lora_strength` sweep (Step 2T follow‑up) to recover photorealism while preserving inventory.
- **Not claimed:** AI visual fidelity is not fixed; the deterministic render remains the trusted fallback and AI outputs remain honestly `UNVERIFIED`.
