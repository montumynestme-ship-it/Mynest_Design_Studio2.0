# Furniture Fidelity Repair Sprint — Findings & Fix Status (v79)

**Scope done in priority order:** confirmed deterministic defects → regression coverage → visual verification → AI-only → shared-DB incident. Target v79 of `85759b78…` (FID `f6b65d2b…`). No paid AI calls; no shared-DB writes/deletes performed in this sprint (only reads).

---

## 0. Baseline (VERIFIED)
- Render-inclusion implementation from the prior step is present and intact: `room_membership_service.resolve_render_inclusions`, `scene_service._apply_render_inclusions`, `schemas.floor_plan.render_room`, `RoomScene3D` floor patch, `RenderRoomControl`, `tests/test_render_inclusion.py`.
- App is **not** a git repo (only `floorplan-parser/.git`, unchanged) → no `git diff`.

## 1. Item-level reconciliation (VERIFIED, read-only) — the deterministic SCENE is faithful
For all **22** real furniture items (openings + room-tags excluded): **every item is present exactly once** in the scene; **no missing, no duplicate, no extra**. So no furniture is lost or invented in the deterministic scene. The reported "missing/extra" are **section↔scene partition disagreements**, not scene inventory errors:

| item | `group_by_room` SECTION | SCENE room (authoritative geometry) | classification |
|---|---|---|---|
| `kitchen-base-…607029`, `…608231` | Kitchen | **UNCERTAIN** "Kitchen" hull twin (100% outside the CONFIRMED Kitchen floor polygon) | out-of-polygon → not in CONFIRMED base |
| `wardrobe-…606853` | **Bedroom 1** | **Bedroom 3** CONFIRMED (covers=True, 23px inside; 83px *outside* Bedroom 1) | **mis-sectioned** by proximity clustering |
| `dining-table-…800756` | Dining Area | Kitchen & Dining Area CONFIRMED | correctly merged (intended) |
| all others | matches | matches | OK |

## 2. Confirmed root causes

### 2a. Kitchen base units — out-of-polygon (FIX IMPLEMENTED + TESTED)
Both units sit in small wall-enclosed alcoves dropped by the raster `min_area_px` filter → no containing CONFIRMED polygon → UNCERTAIN hull twin → the CONFIRMED Kitchen base omits them → `Kitchen` inventory gate MISMATCH (honest block). **Fix = explicit render inclusion** (`render_room=KITCHEN`): the prior step's `resolve_render_inclusions` + `_apply_render_inclusions` move each tagged unit into the CONFIRMED Kitchen room exactly once, and `RoomScene3D` draws a minimal per-item floor patch so it is not floating. **Verified** by `test_render_inclusion.py` incl. the real v79 case: both units land in the CONFIRMED room exactly once, transforms byte-identical, and the **Kitchen gate flips MISMATCH→MATCH**.
- **Status:** mechanism done + tested. It is **opt-in by design** (explicit, never automatic — per Steps 2M/2N.1). Applying it to the live v79 requires the designer to assign the two units (UI `RenderRoomControl`) or a layout save — **not performed** here (that is a `save_layout` write to the shared Postgres, which this sprint must not do). No further code change needed for this defect.

### 2b. Bedroom 1 wardrobe — `group_by_room` mis-sectioning (ROOT CAUSE CONFIRMED; FIX PRODUCT-GATED)
`group_by_room` assigns each non-anchor item to its **nearest bed seed** by distance (`prompt_service.py` anchor-clustering, deliberately wall-geometry-free). `wardrobe-…606853` (802,958) is nearest Bedroom 1's bed but is **geometrically inside Bedroom 3's CONFIRMED polygon** (VERIFIED: covers=True, 23px inside Bedroom 3; 83px outside Bedroom 1). So it is **sectioned to Bedroom 1 but reconstructed/rendered in Bedroom 3** (correctly, once). The `Bedroom 1` gate MISMATCH is therefore **protective and correct**: it blocks Bedroom 1 from prompting for a wardrobe its base does not contain (which would invite the AI to **invent** a phantom wardrobe = extra furniture).
- **Why not fixed in this sprint:** the correct fix is to make `group_by_room`'s bedroom sectioning **defer to authoritative CONFIRMED-room containment** when they disagree. That is the **dual-partition reconciliation** flagged in Steps 2H/2I as a **product decision** (it touches the section-label/membership contract consumed by prompts, manifest, inventory, eligibility, and is asserted by `test_dynamic_rooms`), with corpus-wide regression risk if applied by proximity/threshold. Per the sprint rules ("minimal changes only where proven"; "no arbitrary containment thresholds / weakened gates"; "if a defect depends on a product decision … identify the exact blocker"), I did **not** force a broad grouping change under the deadline.
- **Exact blocker / minimal supported fix:** adopt the 2H/2I reconciliation — thread a containment map (uid → CONFIRMED room) into `group_by_room` (mirroring the existing `merge_map` seam) so an item inside a CONFIRMED room is sectioned to that room; gate it behind the product decision + a `test_dynamic_rooms` membership review + a representative-corpus regression run. This does not change canonical geometry or transforms.

### 2c. Dining — not a defect
The dining table is validly merged into `Kitchen & Dining Area` (AIR-03), as intended. No action.

## 3. Regression coverage & results (offline; no shared-DB writes this sprint)
```
pytest -q tests/test_render_inclusion.py                     → 11 passed (exit 0)   [re-confirmed]
# (prior step also ran a 70-test offline batch green; NOT re-run here to avoid the
#  generation-path tests that write to the shared DB — see §5)
```
Deterministic scene reconciliation (read-only script): **22/22 present exactly once; missing=none; duplicated=none.**

## 4. Visual verification — **UNVERIFIED** (exact prerequisite)
No before/after deterministic render was captured. A capture needs `frontend/src/harness.tsx` driven against the tagged scene with a dev + save server, i.e. an **isolated** environment whose scene fetch/capture does not touch the shared Postgres. None is available in this sprint, so per the rules I did not run it. The Kitchen floor patch covers the footprint and is adjacency-safe **by construction** (patch = the item's own rotated footprint; per-item footprints overlap no other CONFIRMED room — re-confirmed), but the **rendered pixels (seam/floating) remain UNVERIFIED**.

## 5. Shared-database incident (IDENTIFIED; NOT cleaned — awaiting authorization)
- **What wrote:** the generation-path test `test_air03_merge_integration` calls `generate()` (provider `mock`) against the **real v79** design version and has no teardown → its rows persist. The other flagged test, `test_air03_membership_persistence`, uploads a throwaway project and **deletes it on teardown** (cascade) → **no residue**. My v79 `test_render_inclusion` cases are read-only (`build_scene`/snapshot) → no writes.
- **Exact records (read-only query):** `ai_generations` rows on `design_version_id = 85759b78-210e-4daf-a2d1-9e8ea906fee5` with `provider IN ('mock','tracking')` = **32 rows**, `created_at` 2026‑10‑23 → 2026‑10‑25, from several test runs (mine on 10‑25 added the `provider='mock'` `status=failed` rows ~08:54–08:56; `provider='tracking'` rows are from earlier `test_inventory_gate_generate`-style runs in prior sessions). **All 32 are test-adapter records** — `provider` is only `mock`/`tracking`, never a real/paid provider (`fal`/`nvidia`); mock rows are `status=failed, images=0`, tracking rows are synthetic 2–3 image mocks.
- **Ownership:** the project/floor owning FID `f6b65d2b…` (the established test design). These pollute that design's gallery but are harmless test data; no real user generation is affected.
- **Recommended cleanup (authorization required, NOT performed):** delete `ai_generations` where `design_version_id = 85759b78…` AND `provider IN ('mock','tracking')` (cascades to `ai_generation_images`) — run on the shared DB only with explicit approval, or re-point `DATABASE_URL` to an isolated DB for all future generation-path tests. I did **not** delete anything.

## 6. AI-only discrepancies — NOT assessable here (blocker stated)
The only generation outputs on v79 are **mock/tracking synthetic images** (§5), not real AI renders, so they are meaningless for furniture-fidelity comparison. Assessing real AI outputs requires either (a) a **calibrated post-generation detector** (the blocked Workstream C — no representative-output corpus) or (b) new **paid generations** (not authorized). The deterministic base is verified correct (§1), so any real AI add/remove/change would be an **AI-fidelity failure** to be corrected at the provider/prompt layer (deterministic fallback preserved) — **not** a scene-builder patch. Classification left **UNVERIFIED** pending the detector or authorized generation.

## 7. Acceptance check
- Canonical inventory/transforms unchanged ✓ (no canonical write this sprint; render-inclusion is a scene-side move of a single object, transforms byte-identical — tested).
- Each expected object present exactly once in the deterministic scene ✓ (22/22).
- No unintended extra furniture ✓.
- Room assignment/geometry faithful ✓ (scene authoritative; Bedroom-1 issue is section-label only).
- Validation gates intact ✓ (gates unchanged; Kitchen gate flips to MATCH only because the items are genuinely included).
- Targeted regression tests pass ✓ (`test_render_inclusion` 11/11).
- Visual validation: **UNVERIFIED** (§4).
- All claims backed by actual outputs ✓.

## 8. Files changed this sprint
**None** (no code/test/canonical edits — the Kitchen fix was implemented in the prior step; the Bedroom-1 fix is product-gated). Only this report is new. Scratchpad trace scripts are outside the project tree.

## 9. Unresolved issues & next actions
1. **Bedroom 1 wardrobe** — needs the 2H/2I dual-partition product decision, then the scoped containment-aware sectioning fix (§2b) with `test_dynamic_rooms` + corpus review.
2. **Kitchen v79 render** — apply `render_room=KITCHEN` to the two base units via the UI (or an isolated-DB layout save) to realise the implemented fix on the live design.
3. **Visual verification** — run the harness capture on an isolated environment (§4).
4. **Shared-DB cleanup** — on authorization, delete the 32 mock/tracking test rows (§5), and re-point generation-path tests to an isolated DB.

**Not claiming all furniture issues are fixed:** the deterministic scene is faithful and the Kitchen fix is implemented+unit-verified, but (a) the Kitchen fix is not yet applied to live v79 data, (b) the Bedroom-1 reconciliation is product-gated, and (c) visual + AI-output fidelity remain UNVERIFIED.
