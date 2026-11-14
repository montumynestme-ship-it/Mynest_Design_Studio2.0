# Phase 2 — Detector Readiness and Output-Assessment Validation

**Objective:** Verify Phase 1, evaluate actual detector readiness and local availability, audit coordinate and image-dimension correspondences, establish a real-render evaluation corpus, test full assessment paths safely, and add regression coverage without compromising canonical design data or the deterministic fallback.

---

## 1. Verified Phase 1 Findings & Discrepancies

### What Was Verified
1. **Evidence Gathering Contract:**
   - `GenerationRequestBody.base_boxes: dict[str, list[dict[str, Any]]] | None` is optional and backward compatible.
   - `Three.js` screen-space projections (`x, y, width, height, center_x, center_y`) in the capture frame (1216×832) are captured in `BaseRenderBatch.tsx` and forwarded through `DesignStudio.tsx` and `generations.ts` to `POST /api/floor-plans/{id}/generate`.
   - `floor_plans.py` threads `body.base_boxes` to `generation_service.generate()`.
   - In `generation_service._render_room`, `output_inventory_assessment_service.validate_base_box_evidence` verifies version binding (`expected_version_id == declared_version_id`) and rejects mismatches before invoking assessment.
   - Advisory output is recorded in `render_debug.json` via `_save_debug_artifacts(output_inventory_assessment=...)`.
   - The assessment is strictly advisory (`advisory: True`), never gates the render, and never sets `geometry_status=FAITHFUL`.

### Discrepancy Found (Agent Report vs Actual Environment)
- **Previous Agent Report (Phase 1):** Stated that Hugging Face cache was absent on the machine and OWLv2 weights were not installed, assuming no detector could run offline.
- **Actual Verification:**
  - `yolov8n.pt` (6.5 MB) is physically present in the workspace root.
  - The Hugging Face cache is **present locally at `D:\hf_cache`** (specifically `D:\hf_cache\hub\models--google--owlv2-base-patch16-ensemble`, ~600 MB).
  - The script `backend/scripts/ai_output_localization_audit.py` had already configured `os.environ.setdefault("HF_HOME", r"D:\hf_cache")`.
  - Both YOLOv8 and OWLv2 load and execute **completely offline with zero downloads**.

### Hardening Implemented
1. **Non-Finite Coordinate Guard:** Python's `float('nan') <= 0` evaluates to `False`. A box with `width: NaN` or `x: Inf` previously bypassed `w <= 0`. Added `math.isfinite()` checks on `x, y, width, height` in `validate_base_box_evidence` to reject malformed coordinates as `MALFORMED_BOX`.
2. **Auto-Detection of Output Image Dimensions:** `assess_output_inventory` now inspects the input `ai_image` (PIL Image, bytes, or filepath) if `output_width`/`output_height` are omitted, preventing silent coordinate distortion when callers omit dimensions.
3. **Explicit Calibration Status:** Output dictionary now explicitly propagates `calibration_status="NOT_CALIBRATED"`, ensuring consumers cannot treat advisory signals as a calibrated gate.

---

## 2. Actual Detector Availability and Supported Categories

| Property | COCO YOLOv8 (`yolov8n.pt`) | OWLv2 (`google/owlv2-base-patch16-ensemble`) | Hybrid (`furniture_detector_hybrid.py`) |
|---|---|---|---|
| **Local Weights** | Present (`d:\...\yolov8n.pt`, 6.5 MB) | Present (`D:\hf_cache`, ~600 MB) | Both present locally |
| **Required Packages** | `ultralytics 8.4.116`, `torch 2.13.0+cpu` | `transformers 4.57.6`, `torch 2.13.0+cpu` | Both packages available |
| **Offline Inference** | Verified working (<1s on CPU) | Verified working (~15–20s on CPU) | Verified working offline |
| **Internet / Download Needed** | None | None (loads with `local_files_only=True`) | None |
| **Supported Categories** | 13 COCO furniture/appliance classes (bed, couch/sofa, chair, dining table, bench, tv, refrigerator, oven, sink, microwave, toilet, potted plant, vase) | Open-vocabulary (19 interior queries: bed, wardrobe, tall cabinet, chest of drawers, dresser, bedside table, side table, dressing table, desk, chair, sofa, couch, coffee table, tv unit, dining table, dining chair, kitchen cabinet, door, window) | Merged union with tight class-family cross-source deduplication |
| **Critical Limitations** | Completely lacks wardrobe, nightstand/side table, dressing table, console table, kitchen cabinets. Misclassifies vanity stool as "bench". | High false-positive rate on background textures/patterns; hallucinates secondary boxes; slow on CPU (~18s). | Merges benefits but retains OWLv2 latency and potential for extra candidate false alarms. |
| **Object Identity vs Category** | Category only; cannot distinguish object instance identity | Category only; cannot distinguish object instance identity | Category only; identity strictly derived from base registry |

---

## 3. Coordinate and Image-Dimension Correspondence

1. **Coordinate System:**
   - Screen-space pixels, origin top-left (0,0), positive X right, positive Y down.
   - Projected from the live Three.js scene camera (`RoomScene3D`) at capture resolution (`1216×832`).
   - Unclamped: objects partially out-of-frame retain accurate negative coordinates or coordinates exceeding frame bounds.
2. **Dimension Compatibility:**
   - Both base captures and AI renders use `1216×832` in the standard Flux pipeline.
   - When AI output dimensions differ from the capture frame, `assess_output_inventory` returns `NOT_VALIDATABLE` ("output dimensions {ow}x{oh} differ from the base capture frame {iw}x{ih}; object correspondence is not established without a validated projection").
   - Resizing or naive normalization is forbidden because edit-mode AI renders recompose scenes, making uniform linear scaling invalid.

---

## 4. Real-Render Evaluation Corpus

A structured evaluation corpus has been assembled at `backend/output/evaluation_corpus/real_render_evaluation_corpus.json`.

### Dataset Summary
- **Total Traceable Cases:** 3
- **Human-Reviewed Cases:** 3
  1. `P2H4-BEDROOM1-EDIT` (Floor plan `f6b65d2b`, v31 baseline, Bedroom 1, 5 canonical items, edit path).
  2. `P2T-LIVINGAREA-EDIT` (Floor plan `f6b65d2b`, v79, Living Area, 3 canonical items, edit path control).
  3. `P2T-LIVINGAREA-CANNY` (Floor plan `f6b65d2b`, v79, Living Area, 3 canonical items, Canny structural conditioning).
- **Corpus Intake Template:** Defined in the JSON for standardized future additions.
- **Statistical Limitation:** Sample size of N=3 is insufficient for statistical calibration or meaningful train/test splits. Status must strictly remain `NOT_CALIBRATED`.

---

## 5. Detection Evaluation on Real Renders

### Empirical Test: Bedroom 1 (`p2h4` Real Render)
- **Ground Truth Review:** Bed, wardrobe, dressing-table preserved; 1 side-table ambiguous/dropped; 1 side-table altered to bench (or bench added).
- **OWLv2 Output:** 11 detections. Correctly recognized wardrobe (`PASS`), but dressing table and bed had delta/IoU insufficient due to model recomposition (`UNCERTAIN`). Hallucinated 2 extra candidates ('a dressing table', 'a bed') on wall and pattern textures.
- **YOLOv8 Output:** 2 detections ('bed' at 0.83 confidence, 'bench' at 0.32 confidence). Failed to detect wardrobe or side tables due to vocabulary limitations (3 missing candidates).
- **Metric Limitations:** Precision/recall metrics over N=1 or N=3 cases would be statistically meaningless. The evaluation proves that detector confidence alone cannot be trusted for gating.

---

## 6. Full Assessment Path Verification

- **Isolated Test Database Investigation:** The project does not configure an isolated test database; `session_scope()` writes to the shared PostgreSQL instance.
- **Safe Verification Strategy:**
  - Component-level execution was tested using `_render_room()` and mock adapters without touching the database.
  - End-to-end integration tests were validated using `TrackingAdapter` (e.g. `test_air03_gate_generate.py`).
- **Invariants Verified:**
  - Assessment is non-gating and advisory: exceptions or missing evidence never abort generation.
  - Detector failure never becomes a fidelity pass.
  - Canonical design geometry remains byte-locked and unchanged.
  - Deterministic 3D base render remains available as the trusted fallback.
  - Existing requests omitting `base_boxes` remain 100% backward compatible.
  - Furniture Library and editor placement logic are completely preserved.

---

## 7. Regression Tests

Added 6 regression tests in `backend/tests/test_output_inventory_assessment.py`:
1. `test_nan_and_infinite_coordinates_rejected`: Verifies `NaN` and `Inf` coordinates are rejected as `MALFORMED_BOX`.
2. `test_invalid_base_image_dimensions_rejected`: Verifies non-positive base dimensions return `NOT_VALIDATABLE`.
3. `test_output_dimensions_auto_detected_from_pil_image`: Verifies image dimensions are inspected from PIL Image objects when omitted.
4. `test_calibration_status_always_not_calibrated`: Verifies `calibration_status="NOT_CALIBRATED"` across all execution paths.
5. `test_duplicate_and_ambiguous_detections_flagged_extra_never_faithful`: Verifies duplicate detections are routed to extras and prevent false passes.
6. `test_base_boxes_not_mutated_by_assessment`: Confirms input box collections are never mutated.

---

## 8. Test Execution and Verification

### Test Commands and Results
```bash
# 1. Output inventory assessment unit tests (16 tests)
pytest -q tests/test_output_inventory_assessment.py
→ 16 passed in 1.89s (exit code: 0)

# 2. Comprehensive 12-suite regression test run (198 tests)
pytest -q tests/test_output_inventory_assessment.py tests/test_output_fidelity_validation.py \
          tests/test_ai_render_furniture_source.py tests/test_ai_fidelity_conditioning.py \
          tests/test_prompt_preservation.py tests/test_render_inclusion.py \
          tests/test_containment_sectioning.py tests/test_inventory_reconciliation.py \
          tests/test_fal_flux_adapter.py tests/test_furniture_geometry_validation.py \
          tests/test_furniture_detector_hybrid.py tests/test_furniture_object_validation.py
→ 198 passed, 0 failed in 36.47s (exit code: 0)

# 3. Frontend typecheck
cd frontend && ./node_modules/.bin/tsc --noEmit
→ Clean, 0 errors (exit code: 0)
```

---

## 9. Files Changed

1. `backend/app/services/output_inventory_assessment_service.py`:
   - Added `math.isfinite` check for box coordinates.
   - Added positive dimension validation.
   - Added dimension resolution from `ai_image` when parameters are omitted.
   - Explicitly added `calibration_status="NOT_CALIBRATED"` to all results.
2. `backend/app/services/furniture_geometry_validation_service.py`:
   - Updated `detect_owlv2` to point to `D:\hf_cache` if present and load with `local_files_only=True` to prevent accidental online downloads.
3. `backend/tests/test_output_inventory_assessment.py`:
   - Added 6 new regression tests covering coordinate bounds, dimension validation, duplicate handling, and immutability.
4. `backend/output/evaluation_corpus/real_render_evaluation_corpus.json`:
   - Created traceable evaluation corpus with ground truth labels and schema template.
5. `PHASE_2_DETECTOR_READINESS_AND_VALIDATION.md`:
   - This comprehensive report.

---

## 10. Git Status & Blocker Analysis

- **Git Status:** The directory `d:\Latest_mynest_design_version\mynest-design-studio` is not a Git repository root (`fatal: not a git repository`). All modifications are listed explicitly above.
- **Remaining Blockers:**
  1. *CPU Inference Latency:* OWLv2 runs on CPU (~18s per image). Running it inline during interactive generation would add latency.
  2. *Detector Calibration:* Requires a multi-room labelled corpus of ≥30 real renders before tolerances can be calibrated.
  3. *AI Edit-Path Recomposition:* The underlying Flux edit model alters composition. Prompt engineering cannot fix this model-level trait; structural conditioning (Canny) is required.
- **Minimum Required Approval:**
  - Authorization for a bounded `control_lora_strength` sweep (0.5–0.8) on Living Area and Bedroom 3 to evaluate the photorealism vs fidelity tradeoff.
- **Next Concrete Action:**
  - Execute the authorized Canny strength sweep using the advisory output assessment service to quantitatively measure missing and extra candidates across strength levels.
