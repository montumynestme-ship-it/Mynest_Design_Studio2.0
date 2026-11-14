# Phase 4C — Step 2M: Explicit Room-Assignment Contract for Ambiguous Furniture (DESIGN / REPORT-ONLY)

**Mode:** DESIGN + REPORT ONLY. No source, test, schema, persisted-design, threshold, room-assignment, prompt, provider, or app-state change. No paid API / hosted inference / image generation. Read-only DB reads via `capture_generation_snapshot` and deterministic offline scene builds only.

**Builds on:** `PHASE_4C_STEP_2K_KITCHEN_RECONSTRUCTION_AMBIGUITY.md` (this session). Investigation example: design version `85759b78-210e-4daf-a2d1-9e8ea906fee5` (FID `f6b65d2b-4f96-4931-9f08-67dbd09776f6`, v79), **re-verified in the active checkout** (`matches_task_target=True`).

> **Numbering note:** the code's internal "Step 2K / 2L" labels (e.g. `base_inventory_service` docstrings) refer to the **inventory-gate** work. The reconstruction-ambiguity report earlier this session reused "2K" in its title; this document is numbered 2M to avoid collision. Content, not the label, is authoritative.

> **STOP CONDITION STANDING (see §8).** The core question has a definitive answer: under the **existing** domain contract, explicitly tagging the two `kitchen-base` units `KITCHEN` would **NOT** place them in the same renderable room as the chimney. Making that work requires a **new product decision** — whether a user assignment may be *authoritative over* reconstruction geometry — which is not implied by any current contract. No implementation; awaiting explicit approval of a chosen approach.

---

## 0. Preflight (VERIFIED)

- **Not a git repository** (`git rev-parse` fails in `backend/`, project root, parent). The session's `git:true` flag is the other session root. No branch/diff; no VCS state created or changed.
- Read: `README.md` area, `CORE_PIPELINE_DOCUMENTATION.md`, `PROJECT_CONTEXT.md`, `PHASE_4C_STEP_2H/2I/2J`, the 2K ambiguity report, and the inventory-gate code/tests.
- Inspected in the live checkout: `schemas/floor_plan.LayoutItem`, `room_membership_service`, `architectural_service.reconstruct_rooms`, `scene_service.build_scene` + `_drop_merged_dining_twins`, `prompt_service` seed/anchor catalogs, `base_inventory_service`, frontend `DiningMembershipControl.tsx` + `lib/roomMembership.ts`, `floor_plan_service.save_layout` serialization note.

---

## 1. Evidence-backed root cause + exact code references (VERIFIED)

(Full trace in the 2K report; re-confirmed here.) The two `kitchen-base` units sit in small wall-enclosed raster components **dropped by the minimum-area filter** at `room_reconstruction_raster.py:239,260` (`min_area_px = max(ww·hh·0.006=18,576, th_r²·40=40,960) = 40,960`; comp#4=26,114 and comp#3=16,640 are below it; the chimney's comp#5=210,457 is kept as RR1). With no containing proven polygon and nearest walls owned by **zero** proven rooms, `architectural_service.reconstruct_rooms` (`:306-321`) routes both base units to the **UNCERTAIN furniture-hull fallback** (`:387-421`); the chimney is contained in CONFIRMED RR1. `base_inventory_service.assess_section_base_inventory` therefore returns **MISMATCH** for "Kitchen" and the pre-dispatch gate refuses the section (`generation_service`, `BASE_INVENTORY_MISMATCH`).

**Key mechanical fact for this design decision** (VERIFIED, `base_inventory_service.py:5-9`): *"A deterministic base render is a WebGL capture of exactly one scene room's furniture."* ⇒ to make the Kitchen base **actually complete**, both base units must end up in **RR1's `furniture` list** at `build_scene` time. A prompt/section-only change can never achieve this.

---

## 2. Existing `room_membership` contract + limitations (VERIFIED)

**Schema** (`schemas/floor_plan.py:27-47`): `LayoutItem.room_membership: str | None = None` — additive, nullable, **dropped from serialization when None** (so legacy canonical fingerprints/caches are unchanged).

**Values** (`room_membership_service.py:37-40`): `VALID_MEMBERSHIPS = {KITCHEN, LIVING_AREA, INDEPENDENT_DINING}`.

**Semantics — three hard limitations that each independently block the kitchen-base case:**

1. **Scope = dining seeds only.** `resolve_dining_memberships` (`:205-209`) processes only `item_id ∈ _DINING_IDS = prompt_service._DINING_SEEDS = {"dining-table"}`. `kitchen-base` is **never considered**. The editor mirrors this: `DiningMembershipControl` renders only for `isDiningItem` (`roomMembership.ts: DINING_ITEM_IDS = {'dining-table'}`).
2. **Validate-only trust model (never authoritative over geometry).** A tag is `RESOLVED` **only if** the item is already inside a **CONFIRMED** room that *shares the connected region* with the destination anchor (`_confirmed_room_of` + `_shares_confirmed_room_with_anchor`, `:61-90`, `:172-177`). Design-guarantee lines `:15-25`: it "NEVER uses visual proximity… and never forces a merge to satisfy a check." If the item is **not** inside a CONFIRMED room → `REVIEW_REQUIRED: INSUFFICIENT_EVIDENCE` (`:167-170`). The base units are in dropped/UNCERTAIN regions **by construction**, so even if the scope were widened, a `KITCHEN` tag on them resolves to **REVIEW_REQUIRED**, never a merge.
3. **Merge mechanism is dining-twin removal only.** The only scene-side action is `scene_service._drop_merged_dining_twins` (drops a redundant **UNCERTAIN "dining"** twin when the dining is validly in its destination). It does **not** move non-dining furniture, does not add an item to a CONFIRMED room's `furniture`, and does not alter the base-render capture set. `resolve_authoritative_groups` emits `merge_map` entries only for dining uids (`:280-287`).

**Anchor catalog note** (`prompt_service.py:205`): `_KITCHEN_IDS = {"kitchen-base","cooktop","sink","refrigerator","chimney"}`. So `kitchen-base` already counts as a KITCHEN *anchor* for labeling and (via `_ANCHOR_IDS[KITCHEN]`) for validating a *dining* tag — but it is not itself a membership-bearing item.

### Decisive answer to the task's core question (VERIFIED)

> *Would assigning both kitchen-base units explicitly to KITCHEN legitimately place them in the same renderable room as the chimney under the existing domain contract?*

**No.** Three independent reasons: (1) base units are outside the membership scope; (2) they are not inside any CONFIRMED room, so the validate-only contract yields REVIEW_REQUIRED, not RESOLVED; (3) the merge path only removes dining twins — it never inserts a non-dining item into RR1's capture set. The existing contract cannot establish this placement.

**Product decision required:** whether a user room-assignment may be **authoritative over reconstruction geometry** — i.e. place an item in a named CONFIRMED room *even though reconstruction did not geometrically place it there* — and whether that authority may reach the **base-render capture set** (RR1's `furniture`). Today's `room_membership` is explicitly *not* that; it only disambiguates which side of an **already-shared** CONFIRMED open-plan region a dining table belongs to.

---

## 3. Candidate approaches — comparison + risks

| | Approach | Completes Kitchen base? | Risk / blocker |
|---|---|---|---|
| **A** | Keep uncertainty; block incomplete inventory (status quo) | No (does not render it) | **None** — already implemented + approved (2I/2J Candidate C). Honest, reversible, label-safe. The safe default. |
| **B** | Explicit user-confirmed room assignment for ambiguous furniture (authoritative-over-geometry) | **Yes, if** the assignment reaches RR1's capture set | Requires the **new trust model** above. Over-assignment risk (user pulls an item into a wrong room); base-capture **framing** risk (item sits outside RR1's polygon — §5). Needs schema-scope + resolver + editor + capture changes, all approval-gated. |
| **C** | Improve raster reconstruction via a representative ground-truth corpus | Partially / indirectly | Even reconstructed, comp#3/comp#4 are **separate components** from RR1 (no bridged opening) → extra tiny "Kitchen" rooms, not a merge → inventory still MISMATCH. Also single-case-tuning risk; needs a corpus we do not have (2K §4). Not sufficient alone. |
| **D** | Automatic spatial assignment rule (nearest CONFIRMED room, etc.) | Maybe | **Contradicts** `reconstruct_rooms`'s documented invariant: "There is NO broad nearest-room reassignment" (`:291-297`). Not supported by product semantics; corpus-wide mis-assignment risk. Prohibited by the mandate. |

**Only B can make the render complete without a prohibited change, and only if the new authoritative trust model is approved.** A is the correct interim default. C/D are insufficient or prohibited.

---

## 4. Recommended minimal contract (Approach B) — DESIGN, pending approval

A minimal, additive extension that **reuses the existing `room_membership` field and its persistence discipline**, adds one explicit authoritative-placement path for furniture that reconstruction left in no CONFIRMED room, and keeps every current dining behavior intact.

### 4.1 Data representation & validation
- **Reuse** `LayoutItem.room_membership` (no new field); keep `str | None`, dropped-when-None. Reuse values `KITCHEN` / `LIVING_AREA`; `INDEPENDENT_DINING` stays dining-only.
- **Widen processing scope** from `_DINING_SEEDS` to an explicit **assignable-furniture** set (e.g. any non-opening furniture item, or an allow-list that includes `kitchen-base`). The dining path is unchanged; the new path handles non-dining assignables.
- **Validation:** an unknown value → REVIEW_REQUIRED (already the behavior). A membership on an item type that cannot be an anchor of the target group → REVIEW_REQUIRED with a typed reason.

### 4.2 Resolution semantics (the new authoritative path)
For a **non-dining** item tagged `KITCHEN`/`LIVING_AREA`, resolve a **target CONFIRMED room** = the single CONFIRMED room containing a `KITCHEN`/`LIVING_AREA` anchor:
- **0 such rooms** → REVIEW_REQUIRED (`INSUFFICIENT_EVIDENCE`: no confirmed destination).
- **≥2 such rooms** → REVIEW_REQUIRED (`AMBIGUOUS_DESTINATION`: user cannot disambiguate between two confirmed kitchens from a category tag alone).
- **exactly 1** → RESOLVED → the item is **added to that room's `furniture` list** for rendering/inventory (never moved in space).
For this design: RR1 is the unique CONFIRMED room carrying a KITCHEN anchor (the chimney) ⇒ both base units resolve to RR1 ⇒ RR1 = {chimney, base-A, base-B} ⇒ Kitchen base inventory **MATCH**.

### 4.3 Precedence (relative to containment & wall-ownership)
Proposed order in `reconstruct_rooms` assignment:
1. **CONFIRMED polygon containment** wins over an explicit tag. If an item is demonstrably inside a *different* CONFIRMED room than its tag names → **REVIEW_REQUIRED: CONFLICT** (mirror the existing dining "separating wall" conflict; never override geometry that already firmly placed the item).
2. **Explicit assignment** applies when the item is **not** contained in any CONFIRMED room — it takes precedence over wall-ownership and over the UNCERTAIN fallback.
3. **Wall-ownership**, then **UNCERTAIN fallback**, unchanged, for untagged items.
This keeps the authoritative tag strictly *additive to* geometry (it only rescues items geometry left unplaced), never *against* firm geometry.

### 4.4 Conflicting / stale references
- The tag names a **category** (`KITCHEN`), not a room id ⇒ **re-reconstruction-safe** (no stale room id to dangle).
- Conflict (tag vs CONFIRMED containment elsewhere) and ambiguity (≥2 confirmed destinations) → REVIEW_REQUIRED, surfaced in the editor; never a silent default (consistent with the current contract's philosophy).
- A tag whose destination anchor disappears in a later version → REVIEW_REQUIRED next resolve; the frozen snapshot of each prior version is immutable and unaffected.

### 4.5 Interaction with AIR-03 open-plan merges
- Disjoint item sets (dining seeds vs non-dining assignables) and disjoint mechanisms (section `merge_map`/twin-drop vs CONFIRMED-room `furniture` insertion) ⇒ they **compose** without conflict.
- Apply the non-dining assignment **inside `reconstruct_rooms`** (so it exists before both the dining merge and inventory assessment). Ensure it does **not** spawn a second "kitchen" UNCERTAIN twin (the item is now in RR1, so no leftover group is created for it).

### 4.6 Persistence, versioning, backward compatibility
- Reuses the proven additive/nullable/dropped-when-None discipline ⇒ **legacy fingerprints unchanged**; untagged designs behave exactly as today (base units stay UNCERTAIN → MISMATCH → blocked).
- Each design version is an immutable snapshot ⇒ historical renders unaffected; new behavior only on versions that carry the new tags.
- **Cache caveat (from 2I):** `_compute_room_hash` does not include the selected base; a resolution change may need explicit cache invalidation to take effect for already-cached rooms. Must be confirmed before implementation.

### 4.7 Effects on scene membership / render-section capture / inventory
- **Scene membership:** the tagged item appears in RR1's `furniture` (CONFIRMED), not in an UNCERTAIN twin.
- **Render-section capture:** RR1's WebGL base capture now encodes the base units ⇒ the Kitchen base image shows them. **Framing risk (§5):** the base-unit centres lie *outside* RR1's polygon, so the capture must frame the **union of the room polygon + assigned items**, or they will be clipped. This must be verified against the actual capture-framing code before implementation.
- **Inventory checks:** `assess_section_base_inventory` → MATCH (all expected uids now in the selected base room) ⇒ the pre-dispatch gate permits dispatch.

### 4.8 No transform / geometry change
The assignment changes only **which room's `furniture` bucket** the item is rendered/counted in. It never alters `cx/cy/w/h/rotation` or any wall/opening/polygon/threshold. The item renders at its exact canonical transform.

---

## 5. Focused regression-test plan (offline, detector-free, no paid calls)

1. **Explicit assignment → complete inventory (the example):** v79 fixture; tag both `kitchen-base` `KITCHEN`; assert both land in RR1's `furniture`, RR1 = {chimney, base-A, base-B}, `assess_section_base_inventory("Kitchen") == MATCH`, and the pre-dispatch gate **permits** dispatch.
2. **Untagged unchanged (back-compat):** same fixture, no tags → base units UNCERTAIN, inventory **MISMATCH**, gate **blocks** (locks today's behavior).
3. **Conflict precedence:** tag an item that CONFIRMED-containment places in a *different* room → **REVIEW_REQUIRED: CONFLICT**; never moved.
4. **Ambiguous destination:** synthetic scene with two CONFIRMED kitchens → **REVIEW_REQUIRED: AMBIGUOUS_DESTINATION**.
5. **No destination anchor:** tag KITCHEN with no CONFIRMED kitchen room → **REVIEW_REQUIRED: INSUFFICIENT_EVIDENCE**.
6. **AIR-03 composition:** a design with both a dining→KITCHEN tag and a base-unit→KITCHEN tag → dining twin dropped AND base units in RR1; neither interferes with the other; exactly one decision per item.
7. **Canonical invariance:** assert every item's `cx/cy/w/h/rotation` and all walls/openings/polygons are byte-identical before/after tagging (only bucket membership differs).
8. **Capture framing:** a rendering-level test (or explicit manual verification) that RR1's base capture frames assigned out-of-polygon items without clipping.
9. **Keep green:** `test_dynamic_rooms`, `test_room_assignment`, `test_kitchen_scene_inventory`, `test_inventory_gate_generate`, `test_air03_*`, and the frontend membership/eligibility e2e specs.

---

## 6. Inspection & test evidence / changed-file status / unknowns

- **Evidence:** §1-§2 code refs re-read in the active checkout; the 2K traces (`capture_generation_snapshot` → reconstruction → assignment → inventory) reproduced this session with the target version confirmed. No new tests were run for this design task (design-only); no generation, no paid calls.
- **Changed files:** none (code/tests/schema/data/config untouched). This report is the only new file.
- **Git:** not a repository — no commit/branch/PR.
- **Remaining unknowns (UNVERIFIED):** (a) exactly how the base-render capture frames a room (whether it would clip out-of-polygon assigned items) — must be inspected before B; (b) whether any API consumer treats `room_membership` as dining-only and would need updating when the scope widens; (c) cache-invalidation requirement for already-cached rooms; (d) corpus-wide behavior if the assignable scope is "all furniture" vs an allow-list.

---

## 7. Approaches vs this evidence — summary
- **A (status quo):** correct, safe, already shipped — keep as default.
- **B (explicit authoritative assignment):** the only path that completes the render without a prohibited change; needs the new trust-model product decision + the §4 design + the §6 unknowns resolved.
- **C / D:** insufficient (C) or prohibited (D).

## 8. Stop conditions — STANDING
- **Canonical intent:** the base units have no room assignment today (`room=None`, `room_membership=None`) and the existing contract cannot grant one (validate-only, dining-scoped). The required intent is a **new product decision** (authoritative-over-geometry assignment), not derivable from the current contract.
- **Assignment precedence / persistence / back-compat:** a coherent minimal design exists (§4), but it **changes the trust model** and depends on unresolved unknowns (§6: capture framing, cache invalidation, API scope).

Therefore: **do not implement.** Recommended for the user to decide: approve **B** with the §4 contract (and authorize resolving the §6 unknowns), or keep **A** as the permanent behavior for this class of out-of-room furniture. No code, schema, data, thresholds, prompts, provider settings, or app state were changed.

## 9. Evidence labels
- **VERIFIED:** version match; the root-cause trace; `room_membership` scope (dining seeds), values, validate-only CONFIRMED-room semantics, REVIEW_REQUIRED on not-in-CONFIRMED-room, dining-twin-only merge; editor dining-only gating; base-capture = one scene room's furniture; the decisive "No" answer to the core question.
- **AGENT-REPORTED (now VERIFIED):** the 2K findings re-confirmed in this checkout.
- **INFERRED:** the §4 contract design and its precedence/compose behavior (reasoned from code, not executed).
- **UNVERIFIED:** capture framing of out-of-polygon assigned items; API-consumer scope assumptions; cache-invalidation need; corpus-wide effect of a widened assignable scope.
