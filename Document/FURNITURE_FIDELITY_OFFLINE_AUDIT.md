# Missing/Extra Furniture — Offline Root-Cause Audit & Regression Hardening

**One line:** Re-traced the full canonical→manifest→dictionary→prompt→FAL-request→assessment→acceptance→fallback path from source this cycle. **No new confirmed defect** — the earlier confirmed defects were already fixed in prior cycles, and this cycle **verified** the key integrity properties and **locked them with 6 new regression tests** (no production/behavior change). **344 offline tests pass. No paid FAL calls; the benchmark guard was confirmed to abort without executing.** Missing/extra furniture at the OUTPUT level remains **unverified** (uncalibrated detector) — not declared fixed.

Legend: **[VERIFIED this cycle]** = re-derived from source/tests now; **[INHERITED]** = from prior-cycle reports, not re-proven here.

---

## 1. Root-cause report (confirmed / hypotheses / unresolved)
**Confirmed defects found THIS cycle:** none new. The investigation reproduced the pipeline behavior and found the listed concerns already handled:

| Area (directive §2) | Finding | Status |
|---|---|---|
| Every canonical item appears exactly once in the manifest | **[VERIFIED]** 8-item multi-room design (incl. a duplicate same-type pair + a window): `group_by_room` places all 8 uids exactly once — 0 dropped, 0 duplicated; manifest furniture totals = 7 (window excluded). | OK (now tested) |
| Duplicate IDs / malformed / invalid dims rejected safely | **[VERIFIED]** `furniture_dictionary.validate_dictionary` rejects duplicate/missing uid, blank type, non-positive **and non-finite** dims, malformed collections (prior cycle fix). `output_inventory_assessment.validate_base_box_evidence` rejects malformed/dup/non-finite base boxes and (missing/mismatched) version. | OK |
| Types/synonyms resolve against the authoritative catalog | **[VERIFIED]** `normalize_label` reuses `_TYPE_SYNONYMS` (the matcher's map); ambiguous/unknown → `None`, never an arbitrary identity. | OK |
| Prompt describes exact inventory without contradiction/duplication | **[VERIFIED]** the **effective** FAL prompt (`_build_fal_edit_prompt`) parses the inventory from the lead sentence and emits it **once** in an `EXACT EXISTING INVENTORY` block; preservation preamble + negatives (last/overriding) present; theme **replaces** the house style (no contradiction); the 10.6k-char room prompt's redundant camera/`MASTER_CONSTRAINT` text is **stripped** and never sent. Oversized mandatory → raises `FAL_PROMPT_TOO_LONG` (never silently drops a constraint). | OK (now tested) |
| Base image / snapshot / manifest / provenance share one design version | **[VERIFIED]** `capture_generation_snapshot` freezes the version + deep-copies canonical; `_render_room` binds the manifest to `design_version_id` + `geometry_fingerprint`; base-render contract checks declared vs snapshot version; the dictionary + system prompt are persisted version-bound (`test_render_room_persists_version_bound_dictionary_and_system_prompt`). | OK |
| Input validation incorrectly implying output faithful | **[VERIFIED]** `assess_ai_render` only yields `FAITHFUL` with `output_verified=True` (its sole caller passes `False`) → outputs are at best `UNVERIFIED`; deterministic canonical→scene `fidelity` is kept **separate** from AI fidelity (`test_ai_furniture_fidelity_reporting`). | OK |
| Output assessment distinguishes missing/extra/occluded/merged/ambiguous | **[VERIFIED]** `validate_objects` emits PASS/UNCERTAIN/FAIL + missing + advisory extras; occlusion/weak detection → `UNCERTAIN` (never asserted missing); detector stays `NOT_CALIBRATED`. | OK (advisory) |
| Acceptance can reject a realistic image that changes inventory | **[VERIFIED]** deterministic gates (2D→3D fidelity hard-refusal, `BASE_INVENTORY_MISMATCH`, post-AI geometry gate) reject; a rejected room raises → no image saved → `partial`/`failed`; advisory detector assessment is non-gating (`test_acceptance_fallback_integration`). | OK |

**Unresolved question:** "invalid room references" has nothing to validate — the manifest/dictionary are per-room (one `room_label`) and the canonical carries no per-item canonical room-id, only the section label (documented, not invented).

**Hypothesis requiring a real generated output (cannot confirm offline):** whether the FAL **edit path** actually preserves inventory in practice. Prior evidence **[INHERITED]**: the edit path has no structural lock and can hallucinate/drop furniture; the Canny alternative preserves structure but renders flat/artifacted. This is a provider/conditioning limitation, confirmable only by an authorized paid benchmark.

## 2. Minimal code changes
**None to production code** — the audit found the relevant logic already correct. Changes are **test-only** (regression coverage that locks the verified-OK properties above):
- `backend/tests/test_furniture_manifest.py` — +1: every canonical item placed exactly once across sections; manifest furniture totals (openings excluded).
- `backend/tests/test_fal_flux_adapter.py` — +5: effective FAL edit prompt has the inventory **once** + preservation preamble + overriding negatives; `FAL_PROMPT_TOO_LONG` raises instead of truncating a constraint; a user theme **replaces** (not appends) the house style; the edit-path body carries **only supported keys** (defaults, and with the optional `guidance_scale`/`num_inference_steps` knobs).

## 3. Regression tests — exact commands & results
Offline; no OWLv2/weights, no provider/network/paid calls, no DB writes.
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q \
  tests/test_fal_flux_adapter.py tests/test_furniture_manifest.py
→ 51 passed   (exit 0)   [incl. the 6 new tests]

# broad 22-file offline regression (dictionary, acceptance/fallback, manifest, prompt,
#   assessment, object/geometry/inventory validation, 2D→3D, base-render/img2img/output-geometry
#   gates, render-input contract, fal + nvidia adapters):
→ 344 passed  (exit 0; only pre-existing Pillow `getdata` deprecation warnings — not new)
```
No assertion was weakened or removed; no expected result changed. Prior cycle was 338; +6 new tests → 344.

## 4. Pipeline trace — canonical/design-version identity stays connected (offline)
`capture_generation_snapshot(file_id)` → `(snapshot_version_id, canonical)` (frozen, deep-copied) → `furniture_manifest.room_manifest(..., design_version_id=snapshot_version_id, geometry_fingerprint=geom_hash)` → `furniture_dictionary.build_dictionary(manifest)` (carries `design_version_id` + `manifest_fingerprint`) → prompt inventory line = `compact_inventory_line(manifest)` (same source) → `_build_fal_edit_prompt` emits that inventory once → `base_render_service.validate_base_render` checks declared vs `snapshot_version_id` → output assessment reconciles base-box evidence **against that manifest** (`EVIDENCE_MANIFEST_MISMATCH` → `NOT_VALIDATABLE`) and attaches `manifest_binding` → `_write_room_manifest` persists manifest + dictionary + system prompt, all bound to the same version. Verified by the new + existing tests.

## 5. Assessment limitations (honest)
- **Output-level missing/extra is UNVERIFIED** — the detector is uncalibrated (`NOT_CALIBRATED`, no OWLv2 weights, none downloaded). Identity is sourced only from the base registry, never the detector's labels. To make output detection dependable we need **labeled AI outputs** (per-object boxes with canonical uid correspondence) across a multi-room set to calibrate thresholds; until then output verdicts stay advisory.
- **Prompt/dictionary cannot force the model** on the edit path (no structural lock).
- **Camera comparability** between an AI output and the base is `UNVERIFIED` (equal dims ≠ equal projection), so screen-space placement signals remain advisory.

## 6. Benchmark readiness
`scratchpad/run_photoreal_benchmark.py` remains prepared and **guarded**: it aborts unless `RUN_FAL_BENCHMARK=1` **and** `FAL_SINGLE_ATTEMPT=true`, refuses the Canny path, and hard-caps at 4 calls. **Verified this cycle:** run with no auth env → immediate abort, **no FAL call**. The guard was not changed or bypassed; the script was not executed.

## 7. Remaining blockers / next concrete action
1. **Paid-run authorization** (declined earlier this session) for the 4-render / $0.32 paired benchmark — the only way to get output-level evidence on the edit path.
2. **Labeled AI outputs** to calibrate the output detector (the path to a reliable, non-advisory missing/extra verdict). Without either, output-level fidelity cannot be established offline.
Next action: on authorization, run the guarded benchmark through the existing pipeline and inspect each output against its canonical design + base render (geometry vs photorealism separately). Otherwise the AI-render fidelity objective stays **incomplete**.

## 8. Git / worktree status
`D:/Latest_mynest_design_version/mynest-design-studio` is **not** a git repository → no branch/diff/commit. Changed this cycle: 2 test files (+6 tests); no production source/config/default change. (The branch in the session header belongs to the separate TeleCRM working directory.)

**Honest conclusion:** offline integrity is verified and now regression-locked; missing/extra furniture is **not** declared fixed — that requires the authorized output-level benchmark evidence above.
