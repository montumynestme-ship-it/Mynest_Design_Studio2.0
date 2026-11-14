# Kitchen/Dining "Topology" Fix — STOP & Report (Precondition #4)

**Outcome: STOPPED before editing.** Independent re-confirmation in source + read-only reproduction shows the confirmed Kitchen/Dining defect is **NOT in the topology component** (`wall_reconstruction.reconstruct_rooms_topology`). Modifying topology would fix nothing and would be a change without a proven defect — which this task explicitly forbids ("only if the investigation proves that specific mechanism is responsible"; "do not force a room loop … to make the result appear complete"). **No files were changed. No TeleCRM access. No paid calls. DB read-only.**

## Preconditions
1. **Repo:** `mynest-design-studio/` (MyNest). Confirmed; TeleCRM never touched.
2. **Root cause independently re-confirmed in source + reproduced** (below).
3. **Git:** not a git repository → no branch/diff/commit. No pre-existing changes altered.
4. **Stop condition met:** the topology mechanism is not responsible → stop and report what's missing (this document).

## Independent re-confirmation (source + read-only reproduction)
Design `85759b78` (v79), floor `f6b65d2b`. Canonical: **`structured_walls = 0`**, furniture 35, doors 0, windows 0.

- `reconstruct_rooms_topology` is a **vector-wall** function; with `structured_walls = 0` it is **not invoked** — rooms are proven from the **PDF raster** reconstruction. The open-plan area is a **CONFIRMED "Kitchen & Dining Area"** polygon (closed, proven). → **the wall cycle already closes.**
- `architectural_service.reconstruct_rooms` assigns furniture by: polygon **containment** (`poly.covers(centre)`) → else **wall-ownership** (`furniture.nearest_wall_id` ∈ a proven room's `supporting_wall_ids`, exactly one owner) → else **UNCERTAIN leftover** (source lines ~282–321, read this cycle).
- Reproduced (read-only): the CONFIRMED room **has** `supporting_wall_ids` (41: `wall_023 … wall_174`), **but** the two `kitchen-base` items have **`nearest_wall_id = None`** and their centres (1605,389), (1396,244) are **not covered** by the room polygon. So wall-ownership cannot match → `kitchen-base` → UNCERTAIN leftover. The Kitchen section's base resolves to the CONFIRMED room (which lacks the cabinets) → `assess_section_base_inventory` = **MISMATCH** (`missing kitchen-base ×2`) → section refused pre-provider.
- Dining is refused by the **AIR-03 membership gate** (`resolve_authoritative_groups` → `REVIEW_REQUIRED`, `merge_map = {}`; SPEC §5 Case D) — intentional, not a geometry defect.

**Refined precise cause (Kitchen):** `enrich_furniture_relationships` computes `nearest_wall_id` from the **canonical `structured_walls`** (empty here); the raster-derived wall ids the proven room references (`wall_0XX`) are a **different set** and are not fed to furniture enrichment. So wall-mounted furniture outside the eroded interior polygon has `nearest_wall_id = None` and cannot be wall-owned. **This is a furniture↔wall-enrichment / containment gap, not a topology-cycle gap.**

## Why no topology change was made
The task scopes to "the topology component" and only "if the investigation proves that specific mechanism is responsible." The enumerated topology mechanisms are **not** responsible:
| Topology mechanism | Responsible? |
|---|---|
| Endpoint normalization / segment connectivity | **No** — no vector wall segments exist (`structured_walls=0`); topology path unused |
| Opening-aware topology | **No** — `doors=0, windows=0` |
| Duplicate-segment treatment | **No** — no segments |
| Loop-selection / cycle closing | **No** — the room loop already closes (CONFIRMED polygon) |

Changing `reconstruct_rooms_topology` would alter an unused (for this plan) component and fix nothing — and could regress other plans. Per the directive, I stopped.

## What is missing / needed to proceed (the real minimal fix — needs re-scope or approval)
The confirmed Kitchen defect lives **outside** topology; the smallest source-supported options are:
1. **Feed the room's wall segments to furniture enrichment (recommended, generic).** Enrich `nearest_wall_id` using the same wall geometry that produced the proven rooms' `supporting_wall_ids` (raster boundary edges), so wall-ownership assigns the wall-mounted `kitchen-base` to its CONFIRMED room. *Component:* `scene_service` / enrichment wiring — **not** `reconstruct_rooms_topology`.
2. **Bounded near-boundary containment.** Assign furniture whose centre is within **one measured wall-thickness** of exactly one CONFIRMED room's boundary to that room. *Component:* `reconstruct_rooms` assignment — must reuse measured tolerances, never force an ambiguous item (prior cycles 2K/2N deliberately avoided forcing).
3. **Dining membership — product decision.** Keep the review gate (user assigns membership) or, with approval, auto-RESOLVE a single-anchor open-plan dining. *Component:* `room_membership_service` — behavior/spec change, needs sign-off.

None of these is "the topology component," so implementing one requires either re-scoping this task to the furniture-enrichment/containment component (options 1/2) or a product decision (option 3). I did not implement any, to avoid an out-of-scope or unapproved change and to honor "do not create synthetic wall segments / force assignment."

## Regression tests that would accompany the chosen fix (not added — no fix made)
- Kitchen: with the fix, the two `kitchen-base` join "Kitchen & Dining Area" and `assess_section_base_inventory(Kitchen)` == MATCH; a genuinely-outside item is **not** pulled in.
- Existing valid room loops unchanged; walls/openings/furniture transforms/ids/room-assignments unchanged (reuse `validate_2d_to_3d`).
- Ambiguous geometry reported honestly (UNCERTAIN), not silently repaired.
- The real-scene fixture (`test_real_scene_is_faithful`) still passes.

## Validation run this cycle
No code changed, so no new tests were run. The re-confirmation used **read-only** DB reads + offline reconstruction (no provider calls, no writes). (Last cycle's offline geometry/coordinate suites — 72 passed — remain the standing baseline.)

## Deliverables summary
- **Root cause (implementation-confirmed):** Kitchen = furniture `nearest_wall_id=None` + out-of-polygon containment + no wall-ownership (enrichment/containment gap); Dining = AIR-03 membership gate. **Not topology.**
- **Changed files:** none.
- **Before/after topology evidence:** the topology/room loop is **already correct** (CONFIRMED "Kitchen & Dining Area"); there is no topology before/after because there is no topology defect.
- **Git status:** not a git repo; working tree unchanged.
- **Remaining risks / unresolved:** the real fix (options 1/2) touches furniture-wall enrichment/containment with cross-plan regression risk and must be tolerance-derived and tested; the Dining gate is a product decision. Both are outside the stated "topology" scope.

## Next action
Re-scope to the **furniture-wall enrichment / containment** component (option 1 recommended) for the Kitchen defect, and obtain a **product decision** on Dining membership (option 3). On confirmation I will implement the smallest change with the regression tests above. **Stopping here, no edits, per Precondition #4.**
