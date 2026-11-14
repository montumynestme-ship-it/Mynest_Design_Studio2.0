# Kitchen/Dining Reconstruction — Root-Cause Investigation (inspection only)

**Repository:** worked only in `mynest-design-studio/` (MyNest). **No TeleCRM access.** **No edits made** — read-only inspection + offline read-only probes. **No paid API calls.**

## Verdict (evidence-backed)
**The Kitchen/Dining failure is NOT a wall-cycle / `reconstruct_rooms_topology` failure.** The walls close fine — the open-plan area reconstructs as a **CONFIRMED "Kitchen & Dining Area"** room — and for this plan `reconstruct_rooms_topology` is **not even invoked** (the canonical has `walls=0`; rooms are proven from the **PDF raster** reconstruction). The two sections fail **downstream**, for two distinct, reproduced reasons:

1. **Kitchen → `BASE_INVENTORY_MISMATCH`** (furniture containment, not topology).
2. **Dining → `MEMBERSHIP_REVIEW_REQUIRED`** (AIR-03 open-plan membership gate — intentional).

## Fixture / version (verified)
- Design version **`85759b78-210e-4daf-a2d1-9e8ea906fee5`** (v79), floor plan **`f6b65d2b-4f96-4931-9f08-67dbd09776f6`** — the standard test fixture, **same floor** the prior `26afe847` audit used. Retrieved **read-only** from the DB.
- Canonical: **`walls=0`, `structured_walls=0`, furniture=35, doors=0, windows=0**. Kitchen/Dining items: `kitchen-base`×2, `chimney`×1, `dining-table`×1.
- This is the generation shown in `main_zip_222.zip` / generation `803af570` (both bind to `85759b78`): UI banner "4 of 6 rendered; Failed: Kitchen, Dining Area".

## Reconstructed vs expected (verified, reproduced offline)
`scene_service.build_scene(f6b65d2b, canonical=v79)` → **7 rooms, 5 CONFIRMED**:
`Living Area, Bedroom 3, Bedroom 1, Kitchen & Dining Area, Bedroom 2` (all `geometry_source=architectural`) + 2 UNCERTAIN fallbacks (`Kitchen` items=2, `Bedroom 3` items=1).
- `room_faithful_map`: **Kitchen=True, Dining Area=True** (both faithful via the merged CONFIRMED polygon). → **the boundary/cycle is proven; geometry is correct.**
- The prior-audit labeling bug (`_majority` dropping the open-plan co-label) is **already fixed** in current code (`architectural_service.py:342` `inclusion = min(top, max(2, top*0.5))`; `dining_area_fix_proof.json` = PASS) — which is exactly why the shared room is now the CONFIRMED "Kitchen & Dining Area".

## Root cause A — Kitchen (`BASE_INVENTORY_MISMATCH`) `[CONFIRMED]`
`base_inventory_service.assess_section_base_inventory` for the **Kitchen** section returns **MISMATCH**:
```
expected_count: 3   (kitchen-base-…029, kitchen-base-…231, chimney-…293)
base_room: "Kitchen & Dining Area" (CONFIRMED) — furniture = [chimney, dining-table]
missing_uids: [kitchen-base-…029, kitchen-base-…231]   missing_types: ["Kitchen Base"]
reason: "the selected deterministic base omits furniture the section's prompt expects; the item(s) exist elsewhere in the scene"
```
**Why:** the 2 `kitchen-base` cabinets are **wall-mounted** — their centres sit in the eroded wall band, **outside** the CONFIRMED room's interior polygon, so `reconstruct_rooms` does not contain-assign them to "Kitchen & Dining Area". They would normally be rescued by **wall-ownership** (an item whose nearest supporting wall belongs to exactly one proven room), **but the canonical has `walls=0`** — there are **no structured wall segments/ids**, so `wall_owner` is empty and no wall-ownership assignment can fire. The cabinets therefore fall to the UNCERTAIN `Kitchen` fallback. The Kitchen section's deterministic base is resolved to the CONFIRMED room (which lacks the cabinets) → the inventory gate refuses the section before any provider call.
**Source locations:** `architectural_service.reconstruct_rooms` lines ~274–321 (containment via `poly.covers(pt)`; wall-ownership via `wall_owner`, empty when `walls=0`); `base_inventory_service.assess_section_base_inventory`; gate in `generation_service.generate` (pre-dispatch `BASE_INVENTORY_MISMATCH`).

## Root cause B — Dining (`MEMBERSHIP_REVIEW_REQUIRED`) `[CONFIRMED]`
`room_membership_service.resolve_authoritative_groups` → `merge_map = {}` and a decision:
```
status: REVIEW_REQUIRED
reason: "MISSING_MEMBERSHIP: open-plan dining shares a CONFIRMED room with a kitchen/living
         anchor but has no explicit membership; automatic rendering blocked (SPEC §5 Case D)"
```
`blocked_dining_sections` → `{"Dining Area": "MEMBERSHIP_REVIEW_REQUIRED"}`. **Why:** the `dining-table` sits inside the CONFIRMED "Kitchen & Dining Area" polygon (genuinely open-plan) and shares it with the kitchen anchor, but no explicit membership was assigned, so auto-render is **intentionally** blocked pending user review. **This is by-design conservative behavior, not a bug.**
**Source:** `room_membership_service.resolve_authoritative_groups` / `blocked_dining_sections`; gate folded into `generation_service.generate` (`membership_review_errors`).

## Hypotheses tested
| Hypothesis | Result |
|---|---|
| Disconnected endpoints / gap > snap_tol in `reconstruct_rooms_topology` | **Rejected** — `walls=0`; topology path not used; rooms proven from PDF raster; the room IS CONFIRMED |
| Loop filtering / cycle not closing | **Rejected** — "Kitchen & Dining Area" is a CONFIRMED closed polygon |
| Opening handling splitting walls | **Rejected** — `doors=0, windows=0` in canonical |
| Duplicate segments / tolerance inconsistency | **N/A** — no vector wall segments present |
| Open-plan labeling (`_majority`) dropping Dining | **Previously true, now FIXED** (`architectural_service.py:342`) |
| Furniture containment (wall-mounted item outside interior polygon) + no wall-ownership | **CONFIRMED (Kitchen)** |
| Open-plan membership gate | **CONFIRMED (Dining)** |

## Verified vs inferred
- **Verified (reproduced offline):** design/floor ids, `walls=0`, scene rooms + CONFIRMED set, `room_faithful` True for both, Kitchen `BASE_INVENTORY_MISMATCH` with the 2 missing `kitchen-base` uids, Dining `MEMBERSHIP_REVIEW_REQUIRED`, `merge_map={}`.
- **Inferred:** that the 803af570 UI banner's two failures correspond to exactly these two gates (the on-disk artifacts for Kitchen/Dining were absent — the new failed-section breadcrumb lands only for future runs). The gate reproduction on the exact snapshot makes this a strong inference.

## Exact reproduction (read-only)
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe   # (DB read-only)
# DesignVersion 85759b78 -> canonical; scene_service.build_scene(f6b65d2b, canonical)
# resolve_authoritative_groups -> merge_map={}, Dining REVIEW_REQUIRED
# assess_section_base_inventory(Kitchen manifest, base_room) -> MISMATCH, missing kitchen-base x2
```
(Full probe commands are in this session's transcript; no files were written to the repo.)

## Minimal fix proposals (NOT implemented — inspection only)
1. **Kitchen containment (the real reconstruction gap).** Smallest options, in order of safety:
   - **(a) Populate `structured_walls` for raster-reconstructed plans** (emit the proven room-boundary edges as wall segments with ids). This restores **wall-ownership**, which would assign the wall-mounted `kitchen-base` to its CONFIRMED room — fixing the mismatch generically. *Scope:* `room_reconstruction_raster` / `scene_service` output; moderate.
   - **(b) Bounded near-boundary containment** for wall-mounted furniture: assign an item whose centre is within **one measured wall-thickness** of exactly one CONFIRMED room's boundary to that room. *Scope:* `reconstruct_rooms` assignment; must reuse measured tolerances, never a fixed pixel slack, and never force an ambiguous item (matches prior 2K/2N guidance).
   - Both need a regression test proving the `kitchen-base` joins "Kitchen & Dining Area" and that no other item is pulled in.
2. **Dining membership (product decision, not a bug).** Either keep the review gate (surface it in the editor so the user assigns membership — current intended flow) **or**, if product approves, have `resolve_authoritative_groups` **RESOLVE** (merge) an open-plan dining into the anchor when **exactly one** kitchen/living anchor shares the room (unambiguous), instead of `REVIEW_REQUIRED`. This is a behavior/spec change requiring approval.

## Risks
- **(1a/1b)** altering containment/wall-ownership can mis-assign furniture in other plans — must be tolerance-derived, bounded, and regression-tested; never force an ambiguous item (prior cycles deliberately avoided forcing).
- **(2)** auto-merging dining changes documented §5 Case D behavior and the section list the UI offers; needs product sign-off.
- Neither should touch canonical data, the §L/2D→3D gate, or provider defaults.

## Proposed regression tests (to add WITH an approved fix)
- Containment: a wall-mounted `kitchen-base` whose centre is just outside a CONFIRMED room's eroded interior is assigned to that room (and a genuinely-outside item is NOT).
- `structured_walls` populated for a raster plan → wall-ownership assigns the cabinet → `assess_section_base_inventory(Kitchen)` == MATCH.
- Membership: single-anchor open-plan dining RESOLVES (if option 2 chosen) vs stays REVIEW_REQUIRED (if not) — explicit, no silent change.
- All offline, fixture-driven, no provider calls.

## Next action
Decide between **1a** (populate structured walls — generic, recommended) and **1b** (bounded near-boundary containment) for Kitchen, and get a **product decision** on Dining membership (keep review vs auto-merge single-anchor). Then implement the chosen minimal fix with the regression tests above. **Stopping here before any edit, per the directive.**
