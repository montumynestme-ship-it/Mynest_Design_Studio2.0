# Code Review — Furniture Dictionary + System Prompt (Enforce Boundaries & Test)

**One line:** Reproduced the reported results (**21** targeted, **334** broad) from the current tree, code-reviewed the dictionary / system-prompt / integration, found **2 verified defects + 1 potential risk** in `validate_dictionary`/`render_system_prompt`, fixed them minimally with regression tests (now **25** targeted, **338** broad), and verified the single-source, provider, and acceptance boundaries. **No paid generation; no provider/model/default/canonical change.** Missing/extra furniture is **not** declared resolved — that still needs output-level benchmark evidence.

---

## 1. Baseline reproduced (not taken on trust)
- `tests/test_furniture_dictionary.py` → **21 passed** (reproduced), then **25 passed** after adding 4 tests for the fixes.
- Broad 22-file offline set → **334 passed** (reproduced), then **338 passed** after the fixes.
- Exit 0 both times; the only warnings are **pre-existing** Pillow `getdata` deprecations (not from this work). The implementation report's counts matched the current source.
- Not a git repository (`D:/Latest_mynest_design_version/mynest-design-studio` has no `.git`) → no diff/commit; changed files listed in §5. (The branch in the session header belongs to the separate TeleCRM working directory.)

## 2. Findings (classified)
| # | Class | Finding | Root cause / location |
|---|---|---|---|
| F1 | **Verified defect** | `validate_dictionary` accepted **NaN/±inf dimensions** (`issues: []`). | `furniture_dictionary.validate_dictionary` dims check used `w <= 0 or h <= 0`; `NaN <= 0` is `False`, so a non-finite value passed. |
| F2 | **Verified defect** | A **non-list `items`** or a **non-dict item** raised `AttributeError` instead of a graceful code. | Same function assumed list-of-dicts (`i.get(...)`), and `[i for i in items if not i.get("is_opening")]` crashed on a non-dict / non-list. |
| F3 | **Potential risk** | An **unknown template placeholder** would leak literally (`{{FOO}}`) into the rendered prompt/provenance. | `render_system_prompt` only replaced known keys; no guard for leftovers. (None leak with the current template — latent.) |
| F4 | **Verified OK** | Single source of truth holds. | `build_dictionary` derives every per-design item from the manifest; `furniture_catalog`, `_TYPE_SYNONYMS`, `_OPENING_IDS` are **reused**, not redefined; no static inventory file exists; build is deterministic (test). |
| F5 | **Verified OK** | Manifest is immutable/version-bound at consumption. | `floor_plan_service.capture_generation_snapshot` deep-copies canonical + sets `is_frozen`; `_render_room` builds the manifest from that request-owned snapshot; dictionary carries `design_version_id` + `manifest_fingerprint`. |
| F6 | **Verified OK** | Provider boundary honest. | FAL adapter builds a single combined `prompt` (`_build_fal_edit_prompt`); the Markdown system prompt is **persisted as provenance only**, never injected into the live request; the template header states this. |
| F7 | **Verified OK** | No false `FAITHFUL`. | Dictionary build is best-effort in `_write_room_manifest`; `assess_ai_render` still requires `output_verified=True` (always `False`) → outputs stay `UNVERIFIED`/`NOT_VALIDATABLE`. |
| F8 | **Unresolved (NA)** | "Invalid room references" has nothing to validate. | The dictionary is **per room** (single `room_label`); the canonical manifest carries no per-item canonical room-id, only the section label. No room-reference set exists to check against — documented, not invented. |
| F9 | **Unresolved (by design)** | Units are not physically validated. | `units = "plan_units"` (a constant); the canonical data asserts no mm/cm scale, so none is invented or checked (consistent with prior reports). |

Dynamic prompt values (names, synonyms, room label) come from the catalog/manifest/`_TYPE_SYNONYMS` — not free user text — so prompt injection via dynamic content is low-risk; the leftover-placeholder stripper (F3 fix) also removes any stray `{{…}}` a value could contain.

## 3. Minimal corrections made
- **F1** — `validate_dictionary` now flags `INVALID_DIMENSIONS` when `w`/`h` are non-finite (`math.isfinite`) as well as `<= 0`.
- **F2** — `validate_dictionary` now treats a non-list `items` or any non-dict entry as `MALFORMED_ITEMS` (no crash); validation proceeds over the well-formed entries.
- **F3** — `render_system_prompt` now detects leftover `{{PLACEHOLDER}}` tokens after substitution, **logs a warning**, and strips them so a misleading prompt is never emitted.
No other behavior changed; `build_dictionary`, the matcher, the adapter, provider defaults, and canonical data are untouched.

## 4. Enforced boundaries (verified)
- **A. Canonical input** — the immutable, version-bound manifest is the only source for per-design identity/count/dims/position/rotation/room + architecture; the dictionary derives from it and invents nothing.
- **B. Prompt** — the dictionary-derived Markdown is **guidance** (preservation rules static and ranked above dynamic content and visual enhancement); aliases are recognition hints, not inventory; it does **not** prove the model obeyed, and is provenance (not a FAL system field).
- **C. Output evidence** — `validate_objects`/`assess_output_inventory` classify match/missing/extra/duplicate/ambiguous/occluded/not-assessable; identity comes only from the base registry; detector stays `NOT_CALIBRATED`.
- **D. Acceptance** — input/prompt/format validity never imply output fidelity; `FAITHFUL` needs the existing output-level verification; uncalibrated detections never hard-reject; advisory assessment is non-gating (locked by `test_acceptance_fallback_integration`).
- **E. Fallback** — a rejected/unassessable output never replaces the deterministic render; existing error/partial semantics preserved.

## 5. Files changed (this cycle)
- **`backend/app/services/furniture_dictionary.py`** — F1/F2 (`validate_dictionary` finiteness + malformed-collection safety), F3 (`render_system_prompt` leftover-placeholder stripping), + `logging`/`math`/`re` imports.
- **`backend/tests/test_furniture_dictionary.py`** — +4 tests: NaN/±inf dims rejected; malformed items collection + non-dict item safe; no HTML-comment/leftover placeholder in render; unknown template placeholder stripped (monkeypatched template).

## 6. Regression tests — exact commands & results
Offline; no OWLv2/weights, no provider/network/paid calls, no DB writes.
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q tests/test_furniture_dictionary.py
→ 25 passed   (exit 0)   [21 reproduced + 4 new]

# broad 22-file offline regression (dictionary, acceptance/fallback, manifest, prompt,
#   assessment, object/geometry/inventory validation, 2D→3D, base-render/img2img/output-geometry
#   gates, render-input contract, fal + nvidia adapters):
→ 338 passed  (exit 0; only pre-existing Pillow `getdata` deprecation warnings)   [334 reproduced + 4 new]
```
Pre-existing warnings (Pillow `Image.getdata` deprecation in `generation_service`/`validation_service`/`fal_flux_adapter`) are unrelated to this change and are not new failures.

## 7. Unchanged limitations (honest)
- **Detector uncalibrated** — output-level missing/extra stays `NOT_VALIDATABLE`/`NOT_CALIBRATED`; the dictionary improves label normalization + provenance but proves nothing about pixels.
- **Prompt/dictionary cannot force the model** — on the FAL edit path (no structural lock) furniture can still be dropped/hallucinated; reliable *prevention* needs structural conditioning (separate authorization).
- **Synonyms** limited to the authoritative `_TYPE_SYNONYMS`; out-of-map labels normalize to `None` (honest) rather than guessed.

## 8. Next evidence-based action
A paired **A/B live benchmark** (baseline vs dictionary-informed prompt, identical canonical `v79` inputs, Living Area + Bedroom 3) to measure missing/extra **at the output level**. Smallest useful = 4 renders ≈ **$0.32** (verified $0.04/MP × 2 MP × 4); or a 2-render single arm ≈ $0.16. **Exact approval needed before any call:** render count + hard max cost, and running real paid FAL calls env-only (`FAL_SINGLE_ATTEMPT=true`) with no provider/model/default/production change. Nothing is submitted until approved. Missing/extra furniture remains **unresolved** until that output-level evidence exists.
