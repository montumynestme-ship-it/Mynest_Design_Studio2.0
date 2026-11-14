# Furniture-Preservation Pipeline — Canonical Manifest → Prompt → Output Reconciliation

**One line:** The three stages already existed and are now bound by **one** authoritative manifest — enriched with design-version/schema/fingerprint/units/coordinate-system, used as the **single source** for the prompt's inventory line, and **reconciled against the generated output's base-render evidence**, with the manifest linkage attached to every assessment. Additive and backward-compatible. **No paid generation was performed; no provider/model/default/canonical/Furniture-Library change.**

This implements and offline-validates the furniture-preservation pipeline. It does **not** claim the visual-render objective is solved — that requires a separately authorized live benchmark and human review of actual AI outputs.

---

## 1. Root-cause & integration findings (Stage A)
Traced the live path: AI Render → `capture_generation_snapshot` (immutable design version) → `prompt_service.build_room_prompts` → adapter → `validation_service`/`output_inventory_assessment_service` → debug-artifact persistence.

Most of the requested pipeline **already existed** and was verified in source (not assumed):
- `furniture_manifest.build_manifest`/`room_manifest` builds a per-room manifest from the **immutable snapshot**, using the *same* `prompt_service.group_by_room` grouping as the prompt — so manifest and prompt cannot disagree on room membership.
- `generation_service._render_room` builds the manifest, **hard-gates** empty rooms (`_classify_base_gate`), runs the honest tri-state `assess_ai_render` (never `FAITHFUL` without `output_verified` + structural conditioning), runs advisory `assess_output_inventory`, and **persists** the manifest (`_write_room_manifest`).
- `base_inventory_service` already reconciles the manifest vs the selected deterministic base **by stable uid** (input side), and gates `BASE_INVENTORY_MISMATCH`.
- `furniture_object_validation_service.validate_objects` classifies missing / extra / identity / placement / duplicate / not-assessable / passed; identity comes only from the base registry; detector-gated (`NOT_CALIBRATED`, no weight download).

**Demonstrated gaps (what this change fixes):**
1. **Binding/provenance** — the manifest recorded no `schema_version` / `design_version_id` / `geometry_fingerprint` / `room_label` / `units` / `coordinate_system`; it was bound to the snapshot only implicitly.
2. **Single source of truth** — the prompt's inventory line (`_counted_furniture`) was a *parallel* derivation from the same grouping (consistent today, but able to drift), and there was **no Markdown** representation.
3. **Output↔manifest linkage** — `assess_output_inventory` consumed frontend `base_boxes` with **no check that they match the manifest**, and the assessment result carried no manifest binding.

## 2. Existing components reused (not duplicated)
`furniture_manifest` (extended, not replaced), `prompt_service.group_by_room`/`build_room_prompts`/`_counted_furniture` (rerouted to the manifest), `output_inventory_assessment_service.assess_output_inventory`/`validate_base_box_evidence` (reconciliation added alongside), `furniture_object_validation_service` (unchanged), `base_inventory_service` (unchanged), `generation_service._render_room`/`_write_room_manifest`/`_save_debug_artifacts` (binding + reconciliation wired through existing persistence). No new service, no competing manifest, no new prompt path, no schema/DB migration.

## 3. Files changed
- **`backend/app/services/furniture_manifest.py`** — additive binding fields (`schema_version`, `room_label`, `design_version_id`, `geometry_fingerprint`, `units`, `coordinate_system`, deterministic `manifest_fingerprint`); new derived views from the **one** builder: `compact_inventory_line` (prompt's inventory phrase), `expected_inventory` (furniture-only summary + uids), `binding`, and `to_markdown` (readable preservation instructions from real catalog items). Legacy keys (`furniture_count`/`counts`/`items`/`door_count`/`window_count`) unchanged.
- **`backend/app/services/prompt_service.py`** — `_counted_furniture` now delegates to `furniture_manifest.compact_inventory_line(build_room_manifest(items))` (single source; lazy import breaks the module cycle). Output is **byte-identical** to the prior counting (asserted by tests); no other prompt text changed.
- **`backend/app/services/output_inventory_assessment_service.py`** — new `reconcile_with_manifest(base_boxes, manifest)` → `MATCH` / `MISMATCH` / `NOT_ASSESSABLE`, furniture-only, by stable uid with an item_id-count fallback. Pure/offline/advisory. `assess_output_inventory` unchanged.
- **`backend/app/services/generation_service.py`** — `_render_room` binds the manifest to the snapshot (`design_version_id` + geometry hash); reconciles the base-render evidence against **that** manifest before assessing (a `MISMATCH` ⇒ `NOT_VALIDATABLE: EVIDENCE_MANIFEST_MISMATCH`, never a silent pass on the wrong inventory); and attaches `manifest_binding` + `expected_inventory` to every assessment result (persisted via the existing debug artifacts).
- **Tests** — extended `tests/test_furniture_manifest.py`; new `tests/test_manifest_prompt_output_pipeline.py`.

## 4. Manifest schema — real fixture sample
From a real bedroom fixture (`bed` + 2×`side-table` + `window`), bound to version `v79`:
```json
{
  "schema_version": "mynest.furniture_manifest/1.1",
  "room_label": "Bedroom 1",
  "design_version_id": "v79",
  "geometry_fingerprint": "GEOHASH",
  "units": "plan_units",
  "coordinate_system": "2d_top_down:origin=top_left,x=right,y=down",
  "manifest_fingerprint": "d715bf09...",
  "furniture_count": 3,
  "counts": {"Bed": 1, "Side Table": 2},
  "items": [
    {"uid": "b",  "item_id": "bed",        "name": "Bed",        "cx": 500.0, "cy": 350.0, "w": 1800.0, "h": 2000.0, "rotation": 0.0, "is_opening": false},
    {"uid": "s1", "item_id": "side-table", "name": "Side Table", "cx": 300.0, "cy": 350.0, "w": 450.0,  "h": 450.0,  "rotation": 0.0, "is_opening": false},
    {"uid": "s2", "item_id": "side-table", "name": "Side Table", "cx": 700.0, "cy": 350.0, "w": 450.0,  "h": 450.0,  "rotation": 0.0, "is_opening": false},
    {"uid": "w",  "item_id": "window",     "name": "Window",     "cx": 500.0, "cy": 800.0, "w": 1500.0, "h": 200.0,  "rotation": 0.0, "is_opening": true}
  ],
  "door_count": 0,
  "window_count": 1
}
```
`units` is deliberately `plan_units` (canonical 2D coordinates; physical mm/cm scale is **not** asserted — the canonical data carries none, and inventing one would violate "report the limitation rather than invent values"). The coordinate system **is** known from the renderer/prompt code and stated honestly. Duplicate instances are preserved as **separate** placed objects (`s1`, `s2`), not collapsed.

## 5. How the manifest reaches the provider request (Stage C/D)
Through the **existing** prompt path, with no second/duplicate inventory block. `_room_prompt`'s authoritative lead sentence (`"…contains exactly: {inventory}. Render every one of these items and nothing else…"`) now takes its inventory from `furniture_manifest.compact_inventory_line` — the same manifest used to gate and validate. `to_markdown` exists as the human-readable form of that one manifest for provenance/debug; it is **not** appended to the provider prompt (the prompt already carries the inventory + preservation rules, and the directive forbids a duplicate instruction block). fal receives the inventory and constraints through the supported `prompt` field only — no unsupported provider params, no JSON/Markdown attachment, no change to `image_url`/Canny/init behavior, defaults, retries, or billing.

## 6. How the output is assessed against the same manifest (Stage E/F)
In `_render_room`, the version-validated base-render evidence is first **reconciled against this manifest** (`reconcile_with_manifest`). A `MISMATCH` ⇒ `NOT_VALIDATABLE: EVIDENCE_MANIFEST_MISMATCH` (the evidence is not the same inventory, so output correspondence is unproven). A `MATCH` proceeds to the existing advisory `assess_output_inventory`. Either way the result carries `manifest_binding` + `expected_inventory`, so the recorded assessment is provably tied to this design version/room/inventory. Honesty is preserved end-to-end: the detector stays `None` → `NOT_VALIDATABLE`/`NOT_CALIBRATED`; nothing here can set `FAITHFUL`; the deterministic render remains the trusted fallback; canonical furniture is never moved/resized to make an output pass.

## 7. Regression tests — commands & results
Offline; stub detectors only; **no OWLv2/weights, no provider calls, no paid API, no DB writes.**
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q \
  tests/test_furniture_manifest.py tests/test_manifest_prompt_output_pipeline.py \
  tests/test_output_inventory_assessment.py
→ 32 passed

# touched-module regression set:
… test_ai_render_furniture_source, test_containment_sectioning, test_render_inclusion,
  test_authoritative_merge, test_room_tag_annotation, test_inventory_mismatch_status,
  test_postgen_status_surfaced, test_ai_fidelity_conditioning, test_output_fidelity_validation,
  test_prompt_preservation, test_fal_flux_adapter (+ the three above)
→ 161 passed  (only pre-existing Pillow deprecation warnings)
```
Coverage: manifest extraction from a snapshot; duplicate instances as separate objects; stable uids + room assignment; transforms/units/coordinate-system; **deterministic** serialization (stable `manifest_fingerprint`); binding defaults `None` (backward compatible); prompt inventory = manifest, byte-identical, and present verbatim in `build_room_prompts` output; Markdown lists real items + rules + no example furniture; reconciliation MATCH/MISMATCH (missing & extra) and the uid→count fallback; `NOT_ASSESSABLE` without manifest/evidence; existing advisory-assessment and honesty contracts intact.

Not run (deliberately): the DB-backed integration tests (`test_air03_merge_integration`, `test_air03_membership_persistence`) hit a shared Postgres and mutate rows; the changed code paths are covered by the mocked/pure tests above.

## 8. Git diff summary & status
Not a git repository (`D:/Latest_mynest_design_version/mynest-design-studio` has no `.git`) → no diff/commit. Changes are the 4 source files + 2 test files listed in §3. No canonical designs, Furniture Library, provider defaults, schemas, or DB migrations were modified.

## 9. Remaining risks & limits
- **Prompt-based control is a soft constraint.** As Phase 5 established, the fal model does not *guarantee* compliance; the manifest strengthens the instruction and makes violations detectable, but cannot force the image model to obey. Geometry authority stays with the deterministic render.
- **Detector uncalibrated.** Output-image furniture detection remains `NOT_VALIDATABLE`/`NOT_CALIBRATED` (no OWLv2 weights, no download). The reconciliation makes the output provably *tied to* the manifest and would gate correctly once a calibrated detector is supplied, but today it certifies nothing about pixels.
- **Evidence source.** Reconciliation trusts the frontend `base_boxes` only after version validation **and** manifest match; absent or mismatched evidence degrades honestly to `NOT_VALIDATABLE`.

## 10. No paid generation
**No paid API calls, no live renders, and no provider probes were made.** All validation was offline with stub detectors and pure functions. Provider, model, Canny/init defaults, retry/billing behavior, canonical data, and the Furniture Library are unchanged.
