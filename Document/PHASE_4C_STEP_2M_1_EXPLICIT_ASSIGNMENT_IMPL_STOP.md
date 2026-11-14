# Phase 4C — Step 2M.1: Explicit Room-Assignment / Render-Inclusion — STOP + Alternatives

**Outcome:** **STOPPED before editing.** The capability is genuinely missing, but every viable implementation requires a decision the task reserves for a stop: it either **contradicts the documented validate-only room-membership model**, **introduces a new canonical/API contract**, or **ships a visual regression** (render inclusion without the deferred floor patch → floating furniture). Per §3 ("if a persistent assignment cannot be implemented safely within the current contract, stop and present the smallest viable alternatives") and the stop conditions, I am reporting the root cause, the discrepancy, and the smallest viable options + the exact minimum decision. No code/test/schema/canonical changed; this report is the only new file.

**Checkout:** `D:\Latest_mynest_design_version\mynest-design-studio` — **not** a git repo (only `floorplan-parser/.git`, a separate clean repo). Target re-verified: v79 of `85759b78…` (FID `f6b65d2b…`).

---

## 1. Verified root cause & current architecture (VERIFIED, read-only)

1. **Furniture→room association is purely geometric.** `architectural_service.reconstruct_rooms` assigns each canonical item by exactly three branches — CONFIRMED **polygon containment** → unambiguous **wall-ownership** → **UNCERTAIN `furniture_hull` leftover** (`:298-321`). It **never reads `room_membership`** and has **no explicit-assignment hook**.
2. **Explicit assignment exists only for dining, and only as validation.** `room_membership` (schema `LayoutItem.room_membership: str|None`, values KITCHEN/LIVING_AREA/INDEPENDENT_DINING) is read **only** by `room_membership_service` (dining seeds `_DINING_IDS={"dining-table"}`), consumed by `scene_service` solely to drop a redundant dining twin (`:367-374`). `reconstruct_rooms` ignores it.
3. **Membership is persisted canonically** (kept in `save_layout` when set; dropped when `None`; round-trips via `get_layout`/`get_canonical`) **and** re-derived geometrically during scene construction — i.e. both places, but the canonical field drives only the dining merge.
4. **Uncertain open-plan / `furniture_hull` rooms** are non-authoritative leftover rooms (`status=UNCERTAIN`, boundary = a padded hull around the items) created for furniture the walls could not prove (`:387-421`). The base units live here today; the hull floor covers them.
5. **Gates relying on CONFIRMED containment:** `room_eligibility` / `_room_faithful_map` (CONFIRMED→faithful); `base_inventory_service` (the selected base room's furniture set); the membership gate; `BASE_INVENTORY_MISMATCH`. All key off the geometric scene, not an explicit override.
6. **No render-only inclusion override can be passed through today** — there is **no such concept anywhere** (verified: no `render_inclusion`/`include_in_room`/`force_include`/`override` in scene/generation/architectural/membership services), and `reconstruct_rooms` (which builds each room's render set) has no hook to read one.

**Capability status: MISSING** for non-dining, out-of-polygon render inclusion. (Partial only in the narrow sense that a dining tag can disambiguate an *already-contained* open-plan dining table.)

**No contradiction with the 2N.1/2N.2 reports** — this corroborates them: base units are in the UNCERTAIN hull twin (not RR1); `reconstruct_rooms` is geometric-only.

---

## 2. The discrepancy that forces a decision (STOP condition 3)

The requested feature — include a canonical item in a CONFIRMED room's render **even though its footprint is 100% outside that room's polygon** — **directly contradicts the documented room-membership model.** `room_membership_service` guarantees (docstring `:15-25`): membership is *validated against CONFIRMED wall-topology evidence only*, *never uses proximity*, *never forces a merge to satisfy a check*, and *insufficient/conflicting evidence → REVIEW_REQUIRED, never a silent default*. A non-dining item outside all CONFIRMED rooms, tagged KITCHEN, resolves under this model to **REVIEW_REQUIRED (INSUFFICIENT_EVIDENCE)** — it must **not** be placed. Making it a render inclusion means *forcing* placement the model explicitly refuses. That is a new **authoritative-over-geometry** trust model, distinct from today's validate-only one.

The task itself requires distinguishing **canonical placement**, **canonical room assignment**, and **render inclusion** and says "do not conflate." Overloading the existing `room_membership` field for the new render-inclusion semantic would conflate a validate-only concept with an authoritative-override concept on one field — the exact conflation the task forbids.

---

## 3. Smallest viable alternatives (none implementable without a decision)

| | Carrier of the explicit signal | Schema/API/canonical change? | Contradicts validate-only model? | Needs frontend control? | Interim floating-render? |
|---|---|---|---|---|---|
| **A. New canonical field** `render_room` (or `render_inclusion`) on `LayoutItem`, + a NEW `resolve_render_inclusions` resolver + a 4th `reconstruct_rooms` branch (explicit) that places the item once in the named CONFIRMED room | **Yes** — new canonical JSON field (additive, nullable, drop-when-None like `room_membership`) | No (separate concept, cleanly distinguished) | Yes (new control for assignable non-dining items) | **Yes, unless 2N.2 floor patch ships in the same change** |
| **B. Overload `room_membership`** to non-dining + authoritative placement | No (field exists; persists already) | **Yes — contradicts the model's hard guarantees** (§2); conflates two concepts | Yes | Yes (same) |
| **C. Render-time override param** on `generate()` (`render_inclusions={uid:room}`), non-persistent | **Yes — public-ish API change**; not persistent/auditable across sessions | No | Yes (must send it) | Yes (same) |

Every row needs at least one thing the task gates behind approval: a new canonical field (A), a model contradiction (B), or an API change (C) — and **all three** need a user-facing control (frontend) to be "explicit and auditable," and **all three** produce a **floating-furniture base render** unless the deferred Step 2N.2 floor patch ships in the same change (because the item is 100% outside the room's floor — 2N.1/2N.2 verified). That last point is the sharpest: shipping render inclusion **without** the floor patch makes a tagged item render floating — a visual regression worse than today's honest `BASE_INVENTORY_MISMATCH` block — yet the task defers the floor patch to 2N.2.

---

## 4. The exact minimum decision required (product/architecture)

To proceed safely, one decision is needed, with three parts:
1. **Carrier:** approve a **new additive canonical field** (Alternative A — recommended: it keeps the validate-only `room_membership` model intact and does not conflate concepts), OR explicitly accept overloading `room_membership` (B), OR a render-time param (C). A persistent assignment cannot be added "within the current contract" without one of these — the field needed does not exist, and reusing `room_membership` means changing its documented meaning.
2. **Trust model:** explicitly approve the **authoritative-over-geometry render inclusion** (placing an explicitly-tagged item in a CONFIRMED room it is geometrically outside of), which the current model refuses by design.
3. **Sequencing vs the floating render:** approve **bundling the Step 2N.2 minimal per-item floor patch into the same change** (so a tagged item never renders floating), OR accept the documented interim where tagged designs render the item floating until 2N.2. (Bundling contradicts the task's "floor patch deferred" instruction, so this needs an explicit call.)

Plus: a **frontend assignment control** for assignable non-dining items (explicit, auditable) is required for the mechanism to be user-usable — a frontend change beyond the backend contract.

---

## 5. Why I did not implement a "contract-only" resolver now
A pure `resolve_render_inclusions` resolver with no scene wiring would be **dead code** and would still require choosing a carrier (§3) and reading `room_membership` for non-dining (begins the overload in B). It neither reduces the missing-furniture defect nor is consumed by anything until 2N.2, so it does not satisfy "implement only the minimum **required for downstream render inclusion**" without the decision above. I therefore stopped rather than add speculative, decision-presuming code.

---

## 6. Invariants honored / validation
- **No files edited.** No canonical, schema, API, membership, scene, gate, provider, prompt, or test change. This report is the only new file.
- Canonical inventory/transforms, walls/doors/windows, and all gates are untouched (nothing ran that could change them).
- **Visual validation: UNVERIFIED** — nothing new to render; a capture would require the unbuilt mechanism and/or shared-DB writes (prohibited).
- Tests: none added/changed (no implementation). Existing suites unaffected.

## 7. Deliverables summary
- **Root cause / architecture:** §1 (geometric-only assignment; dining-only validate-only membership; no render-inclusion concept).
- **Explicit assignment status:** **missing** for non-dining out-of-polygon render inclusion (partial for dining disambiguation).
- **Changed files:** this report only. Git: app not version-controlled; `floorplan-parser` unchanged; scratchpad scripts outside the tree.
- **Required product decision:** §4 (carrier + trust model + floor-patch sequencing + frontend control).
- **Next action to resume 2N.2:** make the §4 decision; implement Alternative A (new additive field + resolver + explicit `reconstruct_rooms` branch + frontend control) **bundled with** the 2N.2 minimal per-item footprint floor patch, so render inclusion and floor coverage land together and no tagged item ever renders floating; then run targeted tests on an **isolated** DB and perform the 2N.1 before/after capture review.

**Stop conditions met:** (2) persistent assignment cannot be added without an unapproved contract change; (3) the current validate-only room-membership model contradicts the requested authoritative out-of-polygon inclusion. Reporting for decision rather than choosing a new semantic unilaterally.
