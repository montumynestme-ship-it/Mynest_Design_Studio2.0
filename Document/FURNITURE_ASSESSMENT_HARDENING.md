# Advisory Furniture Assessment — Verification & Hardening

**One line:** Inspected the 7 review hypotheses against source; **5 were confirmed defects** and are fixed with narrow, backward-compatible changes; **2 were already protected / test-only**. All results stay advisory + `NOT_CALIBRATED`, the detector stays optional (no weight download), and nothing can set `FAITHFUL`. **269 offline tests pass. No paid generation was performed.** A bounded live-benchmark plan is prepared below but **not executed** — it needs explicit authorization.

---

## 1. Confirmed root-cause findings (Stage 1)
Traced: canonical snapshot → `furniture_manifest` → deterministic base render + `base_boxes` → generation → `output_inventory_assessment_service` → persisted advisory result (`_save_debug_artifacts`).

| # | Hypothesis | Verdict | Evidence in source |
|---|---|---|---|
| 1 | Duplicate manifest UIDs concealed by set reconciliation | **CONFIRMED** | `reconcile_with_manifest` guarded the uid path with `len(set)==len(list)`; duplicate uids fell through to the item_id-count fallback, which can MATCH two different items sharing a uid. |
| 2 | Equal image dims ≠ equal camera/projection | **CONFIRMED (annotate)** | `assess_output_inventory` proceeds on equal dims; `validate_objects` derives placement/ordering from screen space. The inference was already fenced (advisory + `NOT_CALIBRATED`, detector `None` in prod) but not explicitly flagged. `validate_objects` FAIL logic is asserted by `test_furniture_object_validation.py`, so it must not change — the fix is an explicit `camera_comparability` flag, not a matcher change. |
| 3 | Opening exclusion inconsistent between reconciliation and object validation | **CONFIRMED** | `assess_output_inventory` passed the **full** `base_boxes` as `base_furniture` to `build_object_registry` (no `base_openings`), so a window/door box became a furniture object → fabricated missing/extra furniture. Reconciliation already excludes openings → inconsistent. |
| 4 | `validate_base_box_evidence()` not enforced at every entry | **CONFIRMED (defense-in-depth)** | Enforced in the production caller (`_render_room`), but `assess_output_inventory` trusted its input, so a direct/other caller could feed malformed boxes. |
| 5 | Missing version identifiers permit unbound evidence | **CONFIRMED** | `validate_base_box_evidence` only rejected a mismatch when **both** ids were present; a missing `declared_version_id` with a present `expected_version_id` was silently accepted as unbound. |
| 6 | Empty-manifest behavior ambiguous for empty rooms | **Defined; needed explicit tests** | Empty rooms are omitted from the manifest (`room_manifest` → `None`) and hard-gated before render (`_classify_base_gate`); reconciliation → `NOT_ASSESSABLE`. No code defect — added explicit tests. |
| 7 | Object matcher may not distinguish substitution/duplicate/occlusion/false-positive | **Already honest; no change** | `validate_objects` returns `UNCERTAIN` for missing/occluded/type-inconsistent, routes unmatched detections to advisory `extras` (never a forced FAIL), and a FAIL requires strong **type-consistent** corroboration. Conservative by design; left unchanged. |

## 2. Changed files & why (Stage 2 — only confirmed defects)
- **`backend/app/services/output_inventory_assessment_service.py`**
  - **H5** `validate_base_box_evidence`: when `expected_version_id` is given (production always supplies the snapshot id), a missing `declared_version_id` is now rejected (`MISSING_DECLARED_VERSION`) and a mismatch stays `VERSION_MISMATCH`. With no expected version (legacy), the check is skipped — backward compatible.
  - **H1** `reconcile_with_manifest`: duplicate stable uid on **either** side now returns a new `AMBIGUOUS` status (never a false MATCH via the count fallback).
  - **H4** `assess_output_inventory`: defensively re-validates `base_boxes` through `validate_base_box_evidence` (structural validity only; version is the caller's concern) → malformed/duplicate/non-positive evidence can’t enter from any caller.
  - **H3** `assess_output_inventory`: splits openings from furniture, passing furniture as `base_furniture` and openings as `base_openings` to `build_object_registry`; openings-only evidence → `NOT_VALIDATABLE`. Architectural evidence is preserved (openings keep their separate slot), not weakened.
  - **H2** `assess_output_inventory`: the evaluated result now carries `camera_comparability: "UNVERIFIED"`, making explicit that equal dims do not establish camera/projection comparability and placement signals are advisory only.
- **`backend/app/services/generation_service.py`** — `_render_room` treats `AMBIGUOUS` like `MISMATCH` → `NOT_VALIDATABLE: EVIDENCE_MANIFEST_MISMATCH` (no false pass on ambiguous identity).
- **Tests** — extended `tests/test_output_inventory_assessment.py` (H2/H3/H4/H5) and `tests/test_manifest_prompt_output_pipeline.py` (H1 ambiguity, H6 empty/openings-only).

No change to canonical geometry, furniture placement, provider defaults, generation model, API contracts, DB schemas, `validate_objects` matching logic, or the Furniture Library.

## 3. Regression tests — exact commands & results (Stage 3)
Offline; stub detectors; **no OWLv2/weights, no provider calls, no paid API, no DB writes.**
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q \
  tests/test_output_inventory_assessment.py tests/test_manifest_prompt_output_pipeline.py \
  tests/test_furniture_manifest.py tests/test_furniture_object_validation.py \
  tests/test_output_fidelity_validation.py
→ 71 passed   (exit 0)

# broad regression set (19 files; manifest/prompt/generation/assessment/validation/adapter):
… + test_furniture_inventory_validation, test_furniture_geometry_validation,
    test_ai_render_furniture_source, test_ai_fidelity_conditioning,
    test_ai_furniture_fidelity_reporting, test_containment_sectioning, test_render_inclusion,
    test_authoritative_merge, test_room_tag_annotation, test_inventory_mismatch_status,
    test_postgen_status_surfaced, test_prompt_preservation, test_render_input_contract,
    test_fal_flux_adapter
→ 269 passed  (exit 0; only pre-existing Pillow `getdata` deprecation warnings)
```
New-case coverage: duplicate manifest/evidence uid → `AMBIGUOUS`; missing/mismatched/correct version binding; opening filtering (window not matched as furniture, openings-only → `NOT_VALIDATABLE`); malformed/non-finite/non-positive/duplicate base boxes rejected inside `assess_output_inventory`; missing image / missing detector / detector exception; differing dims → `NOT_VALIDATABLE`; equal dims → `camera_comparability: UNVERIFIED`; missing/extra/duplicate/substituted detections (existing); empty manifest + openings-only rooms; advisory + deterministic-fallback contracts intact. Not run (deliberately): DB-backed `test_air03_*` integration tests (shared Postgres, mutate rows); the changed paths are covered by the mocked/pure tests above.

## 4. Integration findings & remaining risks
- The production caller (`_render_room`) is the only entry that runs the assessment; it validates evidence **with** version binding, reconciles against **this** manifest, and (now) the assessor re-checks structural validity itself.
- In production the detector is `None` → the outcome is `NOT_VALIDATABLE`; the hardening changes *why/how* it’s gated (and would gate correctly once a calibrated detector exists), not the current production verdict.
- **Residual risks:** (a) prompt-based preservation is a soft constraint (the model may still deviate); (b) a future calibrated detector under a **changed camera** could still emit advisory placement signals — `camera_comparability: UNVERIFIED` flags this, and resolving it (camera/projection check) is a separate, pre-calibration work item; (c) reconciliation trusts `base_boxes` only after version + structural + manifest checks.

## 5. Documentation
This report is the Stage deliverable; it complements [FURNITURE_MANIFEST_PRESERVATION_PIPELINE.md](FURNITURE_MANIFEST_PRESERVATION_PIPELINE.md). Prior reports and unrelated docs are unchanged.

## 6. Prepared live-benchmark plan (NOT executed — authorization required)
**Verified runtime config (source + `backend/.env`):** `DEFAULT_AI_PROVIDER=fal`; `FAL_IMAGE_MODEL=fal-ai/flux-kontext/dev`; `FAL_USE_CONTROLNET=false` ⇒ **edit path** (base PNG as `image_url`, **no structural lock**); `FAL_CONTROL_USE_INIT=true`; `FAL_SINGLE_ATTEMPT=false` (⇒ the adapter may retry → >1 billed call per render); `FAL_GUIDANCE_SCALE`/`FAL_NUM_INFERENCE_STEPS` unset (adapter defaults 3.5 / 28); `AI_DEMO_MODE` off. Prior phases established the edit path does not guarantee geometry/inventory preservation.

**Fixtures:** canonical design version `v79` (already used in Phases 3–4), rooms **Living Area** + **Bedroom 3**, each with its existing deterministic base render + base_boxes (same snapshot the manifest binds to).

**Bounded request plan (smallest useful):** 2 rooms × 1 render = **2 renders**, `FAL_SINGLE_ATTEMPT=true` (one billed submission each, no retry), env-only, defaults otherwise unchanged. Optional A/B second arm (edit vs `FAL_USE_CONTROLNET=true` Canny) would be **4 renders** — propose the 2-render arm first.

**Cost (verified pricing, labeled ESTIMATE):** fal $0.04/MP; 1216×832 ≈ 2 MP ⇒ **$0.08/render** ⇒ **$0.16** for 2 renders (**$0.32** if the 4-render A/B arm is approved). Billed only on success.

**Evidence checklist / comparison criteria (human review + advisory assessment; detector stays `NOT_CALIBRATED`):** furniture inventory (every manifest item once, no extra/duplicate/substitute), object identity/type, placement/room assignment (advisory — `camera_comparability: UNVERIFIED`), architecture (walls/doors/windows, no invented openings, no wireframe artifact), camera comparability, visual quality (meaningfully more photorealistic than the flat base), provenance (design version + `manifest_fingerprint` + base/output sha + provider request id + `conditioning_mode`). Accept only if **all** geometry/inventory criteria hold **and** visual quality improves; an attractive but non-faithful render is rejected; deterministic render remains the trusted fallback.

**Exact authorization needed to execute:** explicit approval of (1) the render count + max cost (2 renders / $0.16, or 4 / $0.32 for A/B), and (2) running real paid fal calls env-only (`FAL_SINGLE_ATTEMPT=true`) with **no** change to provider/model/Canny/init defaults or production settings. Nothing is submitted until that approval is given.

## 7. Git status
`D:/Latest_mynest_design_version/mynest-design-studio` is **not** a git repository → no diff/commit. Changed: the 2 source files + 2 test files in §2. (The branch in the session header, `fix/quotation-edit-items-and-pdf-finish`, belongs to the separate TeleCRM working directory, not this project.)

**No paid generation, provider probe, or production/default change was performed in this task.** Completion of this cycle ≠ completion of the overall AI-render fidelity objective, which still requires the authorized live benchmark and human review above.
