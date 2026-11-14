# Phase 4C — Step 2U: Missing/Extra Furniture — Root Cause + Output-Validation Hardening

**Authorization honored:** offline only. **No paid calls, no strength sweep, no provider/model default change, no shared-DB writes, no deployments, no unrelated refactors.** App is not a git repo (only `floorplan-parser/.git`) → no `git diff`.

> **Honest headline:** the **deterministic-side** causes of missing/extra furniture are already fixed and verified (2P/2M/2O); status is honest with no false‑FAITHFUL (2R); the prompt forbids invented furniture *and decor* (2S). The **AI‑output** cause is **model‑level** (the `flux-kontext/dev` edit path reinterprets the scene) — confirmed by the 2T A/B — and its fix is **structural conditioning (Canny)**, which is experimental and blocked on strength tuning + paid authorization. This step added **output‑level validation regression coverage** proving the system *detects* missing/extra and never reports them faithful. **No new production code change was warranted** (no new offline‑fixable confirmed defect; wiring an uncalibrated detector is disallowed). I do **not** declare the overall objective complete.

---

## 1. Inspection + pre-edit test run
- Read the prior reports (2S, 2T, investigation) + inspected `generation_service`, `fal_flux_adapter`, `validation_service`, `furniture_object_validation_service`, `furniture_geometry_validation_service`, `vision_validation_service`, canonical/snapshot handling, and tests.
- **Re-ran relevant offline tests before editing → 40 passed (exit 0).** (ai_fidelity_conditioning, prompt_preservation, render_inclusion, containment_sectioning, inventory_reconciliation.)
- Located the 2T artifacts (base `b3b9315a…`, control `b587d7f9…`, Canny `dc489a8a…`) and confirmed their provenance/version binding (v79).

## 2. Confirmed root causes (separated from hypotheses)
| cause | where | status | evidence |
|---|---|---|---|
| Missing furniture in the **deterministic scene** (Kitchen out-of-polygon; Bedroom wardrobe mis-section) | reconstruction/scene | **FIXED** (2M render-inclusion, 2P containment) + honest gate | 2K/2P traces; 2T Living/Bedroom bases MATCH |
| Inventory accounting / silent drops | inventory contract | **FIXED** (2O reconciliation, 22/22 exactly-once) | 2O/2Q traces |
| **Extra/missing/changed furniture in the AI OUTPUT** | **provider/model (edit path)** | **ROOT = no structural conditioning**; fix = Canny (experimental, blocked) | **2T VERIFIED:** edit path reshaped sofa, dropped console, added 3 objects; Canny preserved 3/3, 0 added |
| Prompt lets in invented objects | prompt builder | **FIXED/strengthened** (2S decor prohibition) — supplementary only | 2S tests |
| **Validation only assesses the INPUT, not the OUTPUT** | generation ↔ validation wiring | **Capability EXISTS but UNWIRED + NOT_CALIBRATED** | `output_verified=False` hardcoded; `validate_objects`/`run_geometry_validation` present, "audit-only, NOT_CALIBRATED", needs OWLv2 weights |
| False-positive FAITHFUL | status assignment | **CANNOT occur** | `assess_ai_render` FAITHFUL requires `output_verified=True` (never passed) + structural conditioning (2R guard) |

**Confirmed, not hypothesis:** prompt changes alone cannot fix the model‑level edit hallucination (the 2S‑strength prompt was already in place when 2T's edit output hallucinated). The lever is conditioning.

## 3. What 2U implemented
**Regression tests only** — `backend/tests/test_output_fidelity_validation.py` (6 tests), exercising the REAL output validators against the generated‑image side with **injected stub detections** (no OWLv2 download, no vision model, no paid calls):
- `run_geometry_validation([], None)` and `(base, None)` → **NOT_VALIDATABLE** (no base/image).
- detector raises (weights unavailable) → **NOT_VALIDATABLE** ("detector unavailable"), **never PASS**.
- `validate_objects` with a **missing** canonical object → that object `missing=True`/`UNCERTAIN`, `missing_count≥1`, overall **≠ PASS**.
- `validate_objects` with an **extra/hallucinated** detection → `extra_candidate_count≥1`, overall **≠ PASS**.
- no detections → all missing, overall **≠ PASS**.
- honest chain: a missing/extra or edit‑path output can **never** be `FAITHFUL` (stays `UNVERIFIED`), even if `output_verified=True` were set.

**No production code was changed.** Rationale (evidence-based + scope rules): the deterministic defects are already fixed and the status is already honest, so there is no new confirmed offline‑fixable defect; the only remaining production gap — wiring output assessment into the render path — requires a **calibrated detector + OWLv2 weights**, and the task forbids treating an uncalibrated detector as definitive and forbids paid/heavy default changes. Wiring a detector‑off constant adds no production signal and carries hot‑path risk I cannot validate offline (generation writes to the shared DB). I therefore left production behavior unchanged and documented the exact safe wiring as the next step (§6).

## 4. Does the solution prevent the failure, detect it, or both?
- **Prevent (deterministic/input side):** YES — correct canonical inventory + version binding (2P/2M/2O), inventory gate blocks incomplete bases, strengthened no‑invention prompt (2S). The deterministic base is faithful (2T: Living/Bedroom 3 bases MATCH).
- **Detect (output side):** the capability is present and now **test‑verified to flag missing/extra and to stay NOT_VALIDATABLE/UNVERIFIED without reliable evidence** — but it is **not yet wired** into production (needs a calibrated detector). So detection is proven in code, pending production enablement.
- **Fix the AI visual output:** NOT yet — that requires Canny (2T), which is blocked on strength tuning + paid authorization.

## 5. Tests — commands & results (offline; no paid/DB writes)
```
pytest -q tests/test_output_fidelity_validation.py                         → 6 passed (exit 0)
pytest -q <output_fidelity + ai_fidelity_conditioning + prompt_preservation
          + fal_flux_adapter + containment_sectioning + render_inclusion
          + inventory_reconciliation + dynamic_rooms + kitchen_scene_inventory
          + base_render_gate + furniture_manifest>                          → 104 passed, 0 failed (exit 0)
pre-edit baseline run                                                       → 40 passed (exit 0)
```
Existing assertions unchanged; nothing weakened.

## 6. Remaining limitations & next bounded experiment
- **Detector calibration (blocked):** `validate_objects`/`run_geometry_validation` report `NOT_CALIBRATED`/`NOT_VALIDATABLE` until calibrated on a labelled multi‑room corpus, and need the OWLv2 weights available. **Next offline step:** assemble the labelled corpus (seeded by the 2T/2Q artifacts) + confirm OWLv2 availability, then wire `run_geometry_validation` as an **advisory** (non‑gating, never flips `geometry_status` to FAITHFUL) recording `output_geometry_status` in provenance.
- **Visual fix (blocked, paid):** the only demonstrated cure for extra/missing AI furniture is Canny conditioning (2T), but at `control_lora_strength=1.0` it loses photorealism. **The next bounded experiment to establish whether fidelity AND photorealism are both achievable:** a `control_lora_strength` sweep (e.g. 0.5 / 0.65 / 0.8) on the same faithful Living Area base, scored for added/missing objects AND photorealism — **requires separate paid authorization** (not performed; no strength sweep done here).
- **Scope of evidence:** AI‑output conclusions rest on the single 2T pair + the Latest_Main screenshots — not production‑wide.
- **Open (unconfirmed):** the Latest_Main Bedroom 3 pane showed the deterministic base under a "photorealistic render" title — whether a failed AI render is being surfaced/labelled as success is a UI/provenance question flagged for a separate check (not reproduced in code).

## 7. Acceptance criteria check
1. Canonical inventory + version binding verified ✓ (2Q/2T + §1).
2. Missing/extra cannot be silently reported faithful ✓ (tests §3).
3. Regression tests exercise missing AND extra furniture ✓ (new tests).
4. Existing tests intact, none weakened ✓ (104 passed).
5. No production defaults / shared records changed ✓.
6. No paid generation ✓.
7. Backed by actual test output + inspected artifacts ✓.

## 8. Git / files changed
Not a git repo → no diff. **Changed this step: one new file** — `backend/tests/test_output_fidelity_validation.py`. No production source modified; prior steps' changes intact. Scratchpad artifacts (2T images/scripts) are outside the project tree.

**Not declaring the overall objective complete:** deterministic inventory fidelity is fixed and output‑assessment is proven to detect missing/extra and never falsely pass, but the AI‑visual fix (Canny) and a production output detector remain blocked on authorized paid tuning and a calibration corpus respectively.
