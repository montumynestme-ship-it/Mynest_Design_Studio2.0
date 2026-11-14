# Phase 1 — Evidence-Based Output Furniture Assessment (advisory)

**Objective met (to the extent safely possible offline):** the existing output-assessment path can now **consume version-bound deterministic base-render furniture evidence** and report **advisory** missing/extra candidates, while definitive fidelity stays `UNVERIFIED`/`NOT_VALIDATABLE` until a detector is calibrated. **No paid calls, no model-weight download, no new dependency, no provider/default change, no canonical/DB mutation, Furniture Library untouched.** App is not a git repo → no `git diff`.

> **Not claimed:** this does **not** fix missing/extra furniture — it *detects/reports* it when a detector is available, and honestly returns `NOT_VALIDATABLE` otherwise. The visual cure remains Canny structural conditioning (Step 2T, paid tuning).

---

## 1. Phase 0 verified against source
Confirmed the Phase 0 trace: the AI-render workflow already uses the immutable canonical snapshot → version-bound manifest → preservation prompt → provider adapter → honest validation → deterministic fallback; the Furniture Library is decoupled. **Root cause of the missing output assessment (VERIFIED):** the deterministic base-render furniture boxes **exist** (`lib/furnitureBoxes.FurnitureBox` = `{uid, item_id, room?, wall?, x, y, width, height, center_x, center_y}` in **screen-space px of the capture frame**, computed in `RoomScene3D.onFurnitureBoxes` via the same projection the capture uses), carry stable `uid`/`item_id`, and are keyed per room — but `BaseRenderBatch` only **logged them to the console**; they were **never sent to the backend**, so the backend had no base evidence to compare the AI output against. They map **1:1** onto `furniture_object_validation_service.build_object_registry` input (uid/item_id/x/y/width/height, `image_width/height`).

## 2. The bounding-box data contract (new, backward compatible)
- **Request field:** `GenerationRequestBody.base_boxes: dict[room_key, list[box]] | None` (optional; absent → fully compatible).
- **box:** `{uid, item_id, x, y, width, height, center_x, center_y, room?, wall?}`.
- **Coordinate system:** screen-space **pixels**, origin **top-left**, in the **capture frame** (`base_render_meta[room_key].width/height`, i.e. 1216×832) — *not* the provider output dims; the registry is built with the capture dims. (A detector run on a differently-sized output would need normalization — documented as a calibration concern.)
- **Keying:** same `room_key`s as `base_renders` (both stable id and label), so a room's boxes bind to the exact base render/room/version.
- **Version binding + validation (`validate_base_box_evidence`):** rejects `VERSION_MISMATCH` (boxes' declared version ≠ generation snapshot), `MALFORMED_BOX`, `NON_POSITIVE_BOX`, `DUPLICATE_UID`, `NO_BOXES` — evidence from different base renders is never mixed, malformed evidence never enters. **Client evidence is never trusted as proof of output fidelity** — it is only the *base* registry; the *output* verdict needs a detector.

## 3. Integration with the existing assessment service
New `app/services/output_inventory_assessment_service.py` reuses `build_object_registry` + `validate_objects` (identity from the deterministic registry only) to distinguish: expected-detected, **potentially missing**, **potentially extra**, ambiguous/occluded (`UNCERTAIN`), and detector/image/version-unavailable (`NOT_VALIDATABLE`). It **never** derives 3D transforms from 2D detections and **never** claims count==identity. Wired into `generation_service._render_room` as a **non-gating advisory** recorded in provenance (`render_debug.json → output_inventory_assessment`); it **never** sets `geometry_status`/`geometry_faithful` (those stay the honest 2R chain). Best-effort: any failure degrades to `NOT_VALIDATABLE` and never breaks a render.

## 4. Advisory until calibrated (detector status)
- **Detector weights:** OWLv2 (`detect_owlv2`) requires downloading large weights; the HuggingFace cache is **absent on this machine** (verified — no `owlv2` cached). The task forbids downloading large weights, so the assessment calls the detector **only when one is explicitly supplied** — in production `detector=None` → **`NOT_VALIDATABLE` ("no output detector configured")**, with **no download**.
- **Guarantees:** detector output alone can **never** assign `FAITHFUL`; missing detector evidence is **never** converted to a pass; canonical/generated geometry is never altered to force a pass; the deterministic renderer remains the trusted fallback.
- **Corpus:** synthetic stub detections (tests) exercise control flow only; they do **not** establish real detector accuracy. A labelled real-render corpus + calibration is required before any non-advisory status (see §8).

## 5. Files changed and why
**Backend**
1. `app/services/output_inventory_assessment_service.py` *(new)* — `validate_base_box_evidence` + `assess_output_inventory` (pure, advisory, no weight download).
2. `app/schemas/generation.py` — optional `base_boxes` request field.
3. `app/api/floor_plans.py` — pass `body.base_boxes` through.
4. `app/services/generation_service.py` — import the service; `base_boxes` params on `generate()` and `_render_room`; advisory computation after `assess_ai_render` (version-bound, non-gating); record `output_inventory_assessment` in provenance; thread to both `_render_room` call sites.
5. `tests/test_output_inventory_assessment.py` *(new)* — 8 tests.

**Frontend**
6. `components/design-studio/BaseRenderBatch.tsx` — `onComplete` now also returns the base boxes (keyed by **both** id and label, mirroring `base_renders`).
7. `pages/DesignStudio.tsx` — `baseBoxesRef` (reset per capture), capture boxes in `onComplete`, send `base_boxes` (only when a base render exists), import `FurnitureBox`.
8. `lib/generations.ts` — `GenerateBody.base_boxes` optional type.

No furniture assets/APIs/data models/canonical records/IDs/transforms/room assignments changed; **Furniture Library visibility/behavior unchanged**; provider/model defaults unchanged.

## 6. Tests, build — commands, exit codes, results (offline; no paid/DB writes)
```
backend:  pytest -q tests/test_output_inventory_assessment.py              → 8 passed
backend:  pytest -q <output_inventory_assessment + output_fidelity_validation
          + ai_render_furniture_source + ai_fidelity_conditioning + prompt_preservation
          + render_inclusion + containment_sectioning + inventory_reconciliation
          + fal_flux_adapter>                                              → 91 passed, 0 failed (exit 0)
backend:  import generation_service / floor_plans / output_inventory_assessment_service → OK
frontend: ./node_modules/.bin/tsc --noEmit                                 → exit 0
frontend: eslint <3 changed files>                                         → 0 errors, 11 warnings (pre-existing)
```
Coverage (Phase-1 test matrix): version-bound evidence; malformed/duplicate/mismatched/non-positive/empty boxes; missing & extra candidates (stub detector); detector exception & unavailable image → `NOT_VALIDATABLE`; backward compatibility (no `base_boxes` → unchanged); honest status (never `PASS`/`FAITHFUL` without evidence); request-schema optionality. Existing assertions unchanged.
**Not executed (DB constraint):** the end-to-end `generate()` path writes to the shared Postgres, so the in-`generate()` advisory wiring was **not** run end-to-end here; it is a non-gating, try/except-guarded recording whose assessment logic is fully unit-tested and whose module imports cleanly. End-to-end verification needs an isolated DB.

## 7. Prevents / detects / reports?
- **Prevents:** nothing new (prevention is the deterministic inventory + prompt + gate from prior steps).
- **Detects:** YES, **advisory** — when a detector + version-bound evidence are present, it flags potential missing/extra furniture (proven on stub detections).
- **Reports:** YES — records an honest per-room `output_inventory_assessment` (`NOT_VALIDATABLE` until a detector is enabled/calibrated).

## 8. Remaining work before calibration / next step
- **Enable a detector** without violating constraints: either authorize the OWLv2 weight download (or use an already-available detector), then assemble a **labelled real-render corpus** (seeded by Step 2T/2Q artifacts) and measure precision/recall; only then promote advisory findings beyond `NOT_VALIDATABLE`.
- **Normalize output vs capture dims** when the AI output size differs from the capture (1216×832) before matching.
- **Next concrete step toward a faithful render:** the Canny `control_lora_strength` sweep (Step 2T follow-up, paid, separately authorized) to recover photorealism while preserving inventory — the advisory assessment added here is the honest measurement layer for that experiment.

## 9. Git / diff
Not a git repo → no `git diff`. **Changed:** 5 backend files (2 new) + 3 frontend files + this report. **Overall AI visual fidelity remains UNVERIFIED** until actual outputs (with a calibrated detector) establish it; the deterministic render stays the trusted fallback.
