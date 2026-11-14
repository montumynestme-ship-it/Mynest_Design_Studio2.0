# Phase 4C — Step 2P: Bedroom Sectioning Fix (containment-aware grouping) — IMPLEMENTED

**Mode:** Implementation. Containment-aware sectioning so `group_by_room` defers to authoritative CONFIRMED-room containment, fixing the Bedroom 1 wardrobe section↔scene disagreement. No canonical/geometry/threshold change; no provider/prompt-content change; no frontend change; no shared-DB writes; no paid calls. Target v79 of `85759b78…` (FID `f6b65d2b…`).

---

## 1. Confirmed root cause (evidence)
- `wardrobe-1787646606853` canonical: `room=None, room_membership=None, render_room=None` → **canonical does not encode the room**.
- **Documented product rule** (`architectural_service.reconstruct_rooms`, lines 246–297): *"Assign each furniture item to the proven room whose polygon geometrically CONTAINS its centre … There is NO broad nearest-room reassignment"* — polygon containment is **authoritative**; `group_by_room` is explicitly non-authoritative ("only LABELS furniture").
- **Geometry (VERIFIED):** the wardrobe (802,958) is **inside Bedroom 3's CONFIRMED polygon** (covers=True, 23px inside) and **outside Bedroom 1** (83px). So it is reconstructed/rendered correctly in **Bedroom 3**.
- **Defect:** `group_by_room` assigns each non-anchor item to its **nearest bed seed** (proximity, wall-free by design) → it clustered the wardrobe into **Bedroom 1**'s section. The section (prompt/manifest/inventory) therefore disagreed with authoritative geometry, so the `Bedroom 1` inventory gate flagged **MISMATCH** ("missing wardrobe") and (protectively) blocked Bedroom 1 — which would otherwise prompt the AI for a wardrobe its base lacks (phantom-furniture risk). Intent = **Bedroom 3**, established from the documented containment rule (not from proximity).

## 2. Files changed + why (backend only; all new params optional → backward compatible)
1. **`app/services/prompt_service.py`**
   - `group_by_room(furniture, merge_map=None, containment_map=None)` — new optional `containment_map` `{item_uid → seed_uid of its CONFIRMED room}`; in the bucket loop, a mapped item is sectioned WITH that seed instead of the nearest-seed guess. No map / no match → unchanged.
   - `build_section_containment_map(scene_rooms)` — new pure helper deriving the map from CONFIRMED, non-combined rooms that have a seed (skips `"… & …"` open-plan rooms → `merge_map`'s domain; skips dining seeds; skips seedless/UNCERTAIN rooms).
   - Threaded `containment_map` through `get_eligible_sections`, `room_bboxes`, `build_room_prompts` (and its internal `room_bboxes` call).
2. **`app/services/furniture_manifest.py`** — `build_manifest` / `room_manifest` accept + pass `containment_map`, so the **inventory gate's manifest** matches the corrected sections.
3. **`app/services/generation_service.py`** — compute `containment_map = prompt_service.build_section_containment_map(scene_rooms)` once (alongside `merge_map`, from the same scene) and thread it to `get_eligible_sections`, `build_room_prompts`, the reconciliation `group_by_room`, the gate's `room_manifest`, the reconciliation diagnostic, and `_render_room` (which forwards to `room_manifest`).
4. **`tests/test_containment_sectioning.py`** — new regression tests.

`room_eligibility`'s core output already aggregates by authoritative scene-room membership, so it needed no change.

## 3. Test commands & actual results (offline; NO generation-path/shared-DB writes)
```
pytest -q tests/test_containment_sectioning.py tests/test_dynamic_rooms.py \
         tests/test_render_inclusion.py tests/test_room_assignment.py \
         tests/test_kitchen_scene_inventory.py tests/test_inventory_reconciliation.py \
         tests/test_room_membership.py tests/test_authoritative_merge.py
   → 68 passed (exit 0)
pytest -q tests/test_prompt_geometry.py tests/test_furniture_inventory_validation.py \
         tests/test_base_render_gate.py tests/test_furniture_manifest.py
   → 72 passed (exit 0)
import generation_service / prompt_service / furniture_manifest → OK
```
`test_containment_sectioning.py` covers: nearest-seed default (no map); containment override; no-op when already with its seed; unknown-seed fallback; `build_section_containment_map` (maps contained items, skips UNCERTAIN/combined/seedless, excludes dining); and the **real v79 integration**. Required coverage met: reported Bedroom 1 case ✓, furniture near shared boundaries ✓, dynamic-room/sectioning unchanged (`test_dynamic_rooms` green — asserts section labels, wall-free fixtures → no containment → unchanged) ✓, Kitchen render-inclusion regression (`test_render_inclusion` green) ✓, exactly-once ✓, canonical transforms unchanged ✓, legacy/no-`render_room` ✓.

## 4. Before/after sectioning & inventory evidence (VERIFIED, read-only, v79)
| | BEFORE | AFTER |
|---|---|---|
| `wardrobe-…606853` section | **Bedroom 1** (nearest-seed) | **Bedroom 3** (authoritative containment) |
| Bedroom 1 inventory gate | **MISMATCH** (phantom "missing wardrobe") | **MATCH** |
| Bedroom 3 inventory gate | MATCH | MATCH |
| canonical transforms (all items) | — | **byte-identical** (unchanged) |
| exactly-once across sections | — | no duplicates |
| section label list (`test_dynamic_rooms`) | — | unchanged |

The deterministic **scene** already placed the wardrobe in Bedroom 3 and is **unchanged** by this fix — only the PROMPT/MANIFEST/INVENTORY sectioning now agrees with it. So the Bedroom 1 prompt no longer lists a wardrobe it cannot show, and the gate no longer falsely blocks Bedroom 1.

## 5. Visual & AI validation status
- **Deterministic render:** unaffected by this change (the scene graph/geometry is untouched; the wardrobe was and remains in Bedroom 3's scene room). No new visual artifact is introduced, so no capture is required for this fix's correctness. (A separate Kitchen floor-patch visual check remains **UNVERIFIED** from Step 2N.2 — unchanged here.)
- **AI output fidelity:** **UNVERIFIED** — no real AI outputs available and no paid generation authorized; passing offline tests is not claimed as proof of AI-render correctness. The deterministic base is correct, so any AI add/remove would be an AI-fidelity failure to address at the provider/prompt layer.

## 6. Shared-database incident status
**No change this sprint** — I ran **no** generation-path tests (the full suite was deliberately not re-run; only write-free offline tests). The previously-identified 32 mock/tracking `ai_generations` rows on design version `85759b78…` remain; **not deleted** (awaiting authorization). Recommendation unchanged: re-point `DATABASE_URL` to an isolated DB for generation-path tests, then delete `provider IN ('mock','tracking')` rows for that design version.

## 7. Remaining issues, blockers, next action
- **Scope note (not a regression):** `build_section_containment_map` corrects any item whose proximity cluster disagrees with its CONFIRMED containing room. For v79 the only such item is this wardrobe (verified exactly-once, all others unchanged); for other designs it will similarly align sections to authoritative geometry. Low risk, aligned with the documented rule; 140 offline tests green.
- **Open-plan untouched:** combined `"… & …"` rooms are skipped (merge_map handles them); Kitchen render-inclusion (`render_room`) still works (test green).
- **Edge case:** an item inside a CONFIRMED room that has **no** seed cannot be re-sectioned by this map (rare; none in v79) — would need the explicit `render_room` mechanism instead.
- **Next concrete actions:** (1) run the generation-path + harness capture on an **isolated** DB to confirm end-to-end (incl. the Kitchen floor patch visual); (2) authorize the stray-record cleanup; (3) assess real AI outputs once a calibrated detector or authorized generation is available.

## 8. Git / working tree
App is not version-controlled (only `floorplan-parser/.git`, unchanged) → no `git diff`. Changed files: the 4 backend files above + this report. No frontend, canonical, schema, threshold, or provider change. Scratchpad trace scripts are outside the project tree.

**Not claiming the AI furniture problem is solved:** this fixes the deterministic **sectioning** defect (Bedroom 1 wardrobe) with evidence (gate MISMATCH→MATCH, transforms unchanged, 140 tests green); AI-output fidelity and the isolated-env visual capture remain UNVERIFIED.
