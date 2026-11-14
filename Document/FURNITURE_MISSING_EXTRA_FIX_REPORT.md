# Missing & Extra Furniture — Detection, Prevention & Acceptance (Fix Report)

**One line:** I traced the complete runtime path for the two defects. The **confirmed pipeline-level defects were already corrected** in the two prior cycles (manifest binding/single-source; assessment hardening — see §3); this cycle **verified the acceptance/fallback decision is honest and added the integration coverage that was missing** to lock it. The remaining gap in *output-level* missing/extra detection is a **detector-calibration + provider/conditioning limitation, not an unfixed code defect**, and cannot be closed offline without model weights or a conditioning change (both out of scope). **No paid generation; no provider/model/default change. Broad offline suite: 313 passed.**

This does **not** declare missing/extra furniture solved — that needs the authorized live benchmark in §8 with output-level evidence.

---

## 1. Where each defect is actually handled (runtime trace)
`AI Render` → `capture_generation_snapshot` (immutable version) → `furniture_manifest` (version-bound) → deterministic base render + `base_boxes` → deterministic gates → provider → post-AI gate → advisory assessment → persisted provenance → response/gallery.

Acceptance is decided **only by deterministic, detector-free gates**; the detector-based assessment is advisory and never gates.

| Defect | Prevention (input side, deterministic — gates) | Detection (output side, advisory) |
|---|---|---|
| **Missing furniture** | Manifest is the single inventory source for the prompt's lead line; `_classify_base_gate` (empty room); **`BASE_INVENTORY_MISMATCH`** (expected uid absent from the selected base, present elsewhere → refuse, pre-provider); **2D→3D fidelity gate** (every uid → one object, transform/room preserved → hard refusal). | `assess_output_inventory` + `validate_objects` report `missing` candidates — **advisory, `NOT_CALIBRATED`**; `NOT_VALIDATABLE` in production (no detector). |
| **Extra furniture** | Prompt says "render…nothing else" (manifest-derived); no second inventory path; openings excluded from furniture consistently. | `validate_objects` routes unmatched detections to advisory `extras` (`EXTRA_CANDIDATE_REVIEW`); duplicate detections → extras — **never a forced FAIL**, advisory only. |

## 2. Hypotheses — confirmed / rejected / limitation (Section 3)
**A. Missing furniture**
- Omitted from manifest / wrong room filtering / UID-type mapping / manifest→prompt serialization: **rejected as live defects** — the manifest uses the same `group_by_room` as the prompt, the prompt's inventory line is now manifest-derived (single source), and `base_inventory_service` reconciles by stable uid. Covered by tests.
- Preservation instructions not derived from the manifest: **was true, fixed** (prior cycle — `_counted_furniture` now delegates to `furniture_manifest.compact_inventory_line`).
- Loss of base-render conditioning / structural info: **provider/conditioning LIMITATION** — the active FAL **edit path** has no structural lock (see §6); not a code defect.
- Cropping/occlusion/ambiguity & detector false negatives: **honestly handled** — `validate_objects` returns `UNCERTAIN` (never asserts missing without corroboration).
- Assessment not propagated / rejected-but-shown-as-success: **rejected** — assessment is persisted to provenance; rejected rooms raise → no image saved → `failed`/`partial`; nothing false-passes.

**B. Extra furniture**
- Hallucinated / duplicated by the model: **provider LIMITATION** (edit path), not a code defect; advisory detection records candidates.
- Opening/architectural misclassification: **was true, fixed** (prior cycle — openings split from furniture in the registry + reconciliation).
- Detector false positives: **honestly handled** — extras are advisory, downgrade a clean PASS to `UNCERTAIN`, never force a FAIL.
- Extra findings discarded / statuses not influencing acceptance: **rejected / by design** — findings are persisted; they intentionally do **not** gate because the detector is `NOT_CALIBRATED` (gating uncalibrated detections is explicitly prohibited without approval).

**Matcher taxonomy** (`MISSING`/`EXTRA`/`DUPLICATE`/identity/`AMBIGUOUS`/`NOT_ASSESSABLE`/`NOT_VALIDATABLE`): present and used; duplicate stable ids now → `AMBIGUOUS` (prior cycle). Verified, unchanged this cycle.

## 3. Files changed & why
**This cycle (offline, additive):**
- **`backend/tests/test_acceptance_fallback_integration.py` (NEW)** — drives the real `generation_service._render_room` (DB-free spy adapter) to lock the acceptance contract: a manifest↔evidence mismatch degrades the advisory result to `NOT_VALIDATABLE` (`EVIDENCE_MANIFEST_MISMATCH`) **without failing the render**; matching evidence without a detector stays `NOT_VALIDATABLE`; missing declared version → `NOT_VALIDATABLE`; **no path is `FAITHFUL`**; the manifest binding + expected inventory are persisted in provenance.

**Prior cycles (already landed; their reports stand) — no new production change was needed this cycle:**
- `furniture_manifest.py` — version/schema/fingerprint/units/coordinate-system binding; `compact_inventory_line`/`expected_inventory`/`binding`/`to_markdown` from one builder. → [FURNITURE_MANIFEST_PRESERVATION_PIPELINE.md](FURNITURE_MANIFEST_PRESERVATION_PIPELINE.md)
- `prompt_service.py` — prompt inventory line routed through the manifest (single source).
- `output_inventory_assessment_service.py` — duplicate-uid `AMBIGUOUS`, version-binding enforcement, internal evidence re-validation, opening separation, `camera_comparability: UNVERIFIED`. → [FURNITURE_ASSESSMENT_HARDENING.md](FURNITURE_ASSESSMENT_HARDENING.md)
- `generation_service.py` — manifest bound to the snapshot; reconcile evidence against that manifest; `MISMATCH`/`AMBIGUOUS` → `NOT_VALIDATABLE`; binding + expected inventory attached to the assessment.

## 4. Exact behavioral changes (this cycle)
**None to production code.** The acceptance/fallback decision was traced and found already correct and honest; the only change is new regression coverage. (Had a confirmed acceptance defect existed, the smallest safe correction would have been applied — none was found.)

## 5. Production acceptance / fallback behavior (verified)
- Hard acceptance = deterministic gates (base contract, membership, **2D→3D fidelity hard-refusal**, `BASE_INVENTORY_MISMATCH`, post-AI geometry gate). A rejected room **raises → no image saved →** `failed`/`partial`; the deterministic base render is persisted as evidence and remains the trusted result.
- `assess_ai_render` is always called with `output_verified=False` ⇒ **no AI output is ever `FAITHFUL`** (at best `UNVERIFIED`); `FAIL`/`UNVERIFIED`/`NOT_VALIDATABLE` are distinct from success in the response.
- The detector-based assessment is **advisory, `NOT_CALIBRATED`, non-gating**, wrapped so a failure degrades to `NOT_VALIDATABLE` and **cannot bypass or flip the acceptance gate**. It is persisted to provenance (`render_debug.json`); it is deliberately **not** surfaced in the API/gallery as authoritative (surfacing an uncalibrated advisory as a verdict would mislead).
- Note: the secondary `BASE_INVENTORY_MISMATCH` gate is fail-open on its *own* internal error, but the primary **2D→3D fidelity** gate (same uid→object guarantee) is fail-closed, so the normal acceptance gate is never bypassed.

## 6. Generation-side cause & remaining limitations (verified from source + `backend/.env`)
`DEFAULT_AI_PROVIDER=fal`; `FAL_IMAGE_MODEL=fal-ai/flux-kontext/dev`; `FAL_USE_CONTROLNET=false` ⇒ **edit path (no structural geometry lock)**; `FAL_CONTROL_USE_INIT=true`; `FAL_SINGLE_ATTEMPT=false` (⇒ the adapter may retry → >1 billed call/render); guidance/steps unset (adapter 3.5/28); `AI_DEMO_MODE` off. Prior phases (3–5) established the edit path does **not** guarantee geometry/inventory preservation and that `flux-control-lora-canny` has no weak-init knob.
- **Provider/model/conditioning LIMITATION** — prompt-based preservation is a soft constraint on the edit path; reliable *prevention* of hallucinated/dropped furniture needs a structural-conditioning change (separate authorization) or a cleaner control input.
- **Detector LIMITATION** — output-level missing/extra stays `NOT_VALIDATABLE`/`NOT_CALIBRATED` (no OWLv2 weights; no download). The pipeline maps detections → canonical objects only through the deterministic base registry (identity from uid/item_id, never the detector's labels); residual uncertainty: occlusion, camera change (`camera_comparability: UNVERIFIED`), and detector noise.

## 7. Regression tests — exact commands & results
Offline; stub/spy adapters; **no OWLv2/weights, no provider calls, no paid API, no DB writes.**
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q \
  tests/test_acceptance_fallback_integration.py
→ 3 passed   (exit 0)

# broad offline regression (20 files: acceptance gates, manifest, prompt, assessment,
#   object/geometry/inventory validation, 2D→3D, base-render/img2img/output-geometry gates,
#   render-input contract, fal + nvidia adapters):
→ 313 passed (exit 0; only pre-existing Pillow `getdata` deprecation warnings)
```
New-case coverage (this cycle): manifest↔evidence mismatch is advisory + non-gating (render still succeeds) and recorded as `EVIDENCE_MANIFEST_MISMATCH`/`NOT_VALIDATABLE` with manifest binding; matching evidence + no detector → `NOT_VALIDATABLE`; missing declared version → `NOT_VALIDATABLE`; **never `FAITHFUL`**. Not run (deliberately): DB-backed `generate()` integration tests that mutate the shared Postgres; the acceptance path is covered DB-free via `_render_room`.

## 8. Live benchmark plan & cost (prepared — NOT executed)
**Fixtures:** canonical version `v79`, rooms **Living Area** + **Bedroom 3**, each with its existing deterministic base render + `base_boxes`; a case where all furniture should be preserved (both) and cases able to reveal missing/extra (the edit path's known hallucination).
**Bounded plan:** 2 rooms × 1 render = **2 renders**, `FAL_SINGLE_ATTEMPT=true` (one billed submission each, no retry), env-only, defaults unchanged. Optional A/B second arm (edit vs `FAL_USE_CONTROLNET=true` Canny) = 4 renders.
**Cost (verified pricing, ESTIMATE):** $0.04/MP; 1216×832 ≈ 2 MP ⇒ **$0.08/render** ⇒ **$0.16** (2 renders) / **$0.32** (4-render A/B). Billed on success only.
**Per render, record:** canonical version + room; expected inventory + stable uids; base-render sha; effective provider/model + conditioning (`conditioning_mode`); output sha + provider request id; missing/extra review checklist; accept/reject criteria (all geometry/inventory criteria hold AND visual quality improves, else reject); deterministic fallback remains.
**Exact approval needed to execute:** explicit approval of (1) render count + max cost (2/$0.16 or 4/$0.32), and (2) running real paid FAL calls env-only (`FAL_SINGLE_ATTEMPT=true`) with no provider/model/Canny/init default or production change. Nothing is submitted until then.

## 9. Git status & environment
`D:/Latest_mynest_design_version/mynest-design-studio` is **not** a git repository → no diff/commit; the only new file this cycle is `backend/tests/test_acceptance_fallback_integration.py`. (The branch in the session header belongs to the separate TeleCRM working directory.) Env limitation: DB-backed `generate()` tests require the shared Postgres + a seeded fixture, so acceptance was verified via the DB-free `_render_room` caller.

## 10. Next concrete action toward end-to-end fidelity
Obtain authorization for the §8 2-render benchmark to gather **output-level evidence** on the current edit path, and in parallel scope (do not implement) a structural-conditioning improvement (clean edge/line-art control input) as the path to reliable *prevention* — since prompt + input gates cannot force the edit model to preserve inventory. Until that evidence exists, missing/extra furniture is **not** declared resolved.

## 11. Prohibited actions — compliance
No paid provider calls; no provider/model/default/production change; no deployment/destructive/unrelated refactor; no weakened tests; no claim that unit tests prove visual fidelity; no `FAITHFUL` from input/inventory checks alone.
