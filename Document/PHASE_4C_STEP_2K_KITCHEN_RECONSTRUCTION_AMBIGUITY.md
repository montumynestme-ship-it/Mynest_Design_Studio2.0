# Phase 4C — Step 2K: Kitchen Room-Reconstruction & Furniture-Assignment Ambiguity (REPORT-ONLY)

**Mode:** INVESTIGATION / RECOMMENDATION ONLY. No source, test, data, schema, threshold, prompt, provider, or app-state change. No paid API / hosted inference / image generation. Read-only DB reads via `capture_generation_snapshot` and deterministic offline scene builds only.

**Target:** design version `85759b78-210e-4daf-a2d1-9e8ea906fee5` (FID `f6b65d2b-4f96-4931-9f08-67dbd09776f6`), v79 — **VERIFIED to be the exact version the task names** (`matches_task_target=True`).

> **STOP CONDITION TRIGGERED (see §7).** Canonical room intent for the affected furniture is **absent** (`room=None`, `room_membership=None`), and the geometry evidence supports **multiple materially different interpretations** of what the un-reconstructed cells are (legitimate small alcoves vs. counter/cabinet outlines mis-read as walls). Per the mandate I am reporting the root cause and candidate directions and **not** proposing any implementation as established fact.

---

## 0. Preflight (VERIFIED)

- **Not a git repository.** `git rev-parse` fails in `backend/`, the project root, and the parent. The session's `git: true` environment flag reflects the *other* session root, not this checkout. No branch/diff/working-tree state is available from git; I did not create or alter any VCS state.
- Docs read: `PROJECT_CONTEXT.md` area, `PHASE_4C_STEP_2H` (grouping reconciliation), `PHASE_4C_STEP_2I` (Candidate A feasibility — headline: Candidate A unsafe/insufficient, recommend Candidate C), `PHASE_4C_STEP_2J` (inventory-mismatch status — additive, detector-free, surface-only, never a render gate).
- Code inspected (active checkout): `room_reconstruction_raster.py`, `architectural_service.reconstruct_rooms`, `scene_service.build_scene`, `prompt_service.group_by_room`, `base_inventory_service`, the pre-dispatch inventory gate in `generation_service`.
- Confirmed same checkout + version: the trace loaded canonical for the task's FID and the returned `design_version_id` equals the task's target version.

---

## 1. Earliest confirmed divergence (VERIFIED)

**`app/services/room_reconstruction_raster.py:259-260`** — in `_extract_rooms`:

```python
min_area_px = max((Ww * Hh) * 0.006, (th_r ** 2) * 40)        # :239
...
for i in range(1, ncomp):
    if i in border or stats[i, cv2.CC_STAT_AREA] < min_area_px: # :260  <-- earliest drop
        continue
```

For this plan the two kitchen-base units sit in **separate small wall-enclosed connected components that this filter discards**, so they are never emitted as proven rooms. Every downstream symptom (UNCERTAIN fallback → prompt↔base inventory mismatch → gate block) follows mechanically from this single point.

Canvas/threshold for this design (VERIFIED by replicating the exact mask build):
`render 1923×1610, th_r=32, min_area_px = max(18,576, 40,960) = 40,960` — **bound by the `th_r²·40` term**, not the 0.6%-of-canvas term.

---

## 2. UID-level trace (VERIFIED)

Canonical (snapshot v79) — three kitchen items, **all with `room=None`, `room_membership=None`**:

| uid | item_id | centre (world px) | w×h |
|---|---|---|---|
| `kitchen-base-1787478607029` | kitchen-base | (1604.8, 389.2) | 191×106 |
| `kitchen-base-1787478608231` | kitchen-base | (1395.6, 243.9) | 526×90 |
| `chimney-1787478686293` | chimney | (1229.6, 368.3) | 137×71 |

Raster → **5 CONFIRMED proven rooms** (RR1..RR5). Connected-component classification at each centre:

| item | lands in component | comp area px | threshold | result |
|---|---|---|---|---|
| chimney | comp#5 | **210,457** | 40,960 | **KEPT → RR1 (CONFIRMED)** |
| kitchen-base-A (1604.8, 389.2) | comp#4 | **26,114** | 40,960 | dropped (area < min) |
| kitchen-base-B (1395.6, 243.9) | comp#3 | **16,640** | 40,960 | dropped (area < min) |

Assignment in `architectural_service.reconstruct_rooms` (`:306-321`) — priority = **polygon containment** → **unambiguous wall-ownership** → **UNCERTAIN fallback**:

| item | `poly.covers(centre)` | nearest_wall_id | wall owners | branch taken |
|---|---|---|---|---|
| chimney | **RR1** | wall_037 | {RR1} | **CONFIRMED (contained)** |
| kitchen-base-A | none | wall_162 | **{} (zero)** | **UNCERTAIN leftover** |
| kitchen-base-B | none | wall_036 | **{} (zero)** | **UNCERTAIN leftover** |

> Refinement vs the agent-reported lead: the base units are **not** "shared by two rooms." Their nearest walls (wall_162, wall_036) are support walls of **no** proven room (owners = ∅), because the cells those walls bound were dropped at §1. So wall-ownership cannot rescue them, and they fall to the furniture-hull UNCERTAIN fallback (`architectural_service.py:387-421`).

Scene result: chimney in CONFIRMED `kitchen…` (RR1); both base units in an UNCERTAIN `kitchen` furniture-hull twin. No single scene room holds all three → `base_inventory_service.assess_section_base_inventory` → **MISMATCH** → the pre-dispatch gate (`generation_service`, `BASE_INVENTORY_MISMATCH`) refuses the Kitchen section before any provider call. **This is the already-approved honest containment (Steps 2I/2J, Candidate C), working as designed.**

---

## 3. Why the "counter alcove" is not a proven room (VERIFIED facts + INFERRED reading)

**VERIFIED (mechanical):** comp#3 (16,640 px) and comp#4 (26,114 px) are **genuinely wall-enclosed** (neither touches the canvas border) but both are **below `min_area_px` (40,960)**. comp#4 would clear the 0.6%-canvas term (18,576) but fails the `th_r²·40` term; comp#3 fails both.

**VERIFIED (geometry of the cells):** the top/east band is subdivided by many short segments — wall_096 (len 97), wall_097 (len 79), wall_161 (158), wall_130/131 (~42 each), wall_160 (18), wall_099 (22) — forming thin compartments. The single 526-wide `kitchen-base-B` footprint **crosses several of these segments**. No validated opening bridges this band to the main kitchen (the only openings near the band — door_002, window_004 — are on the far-left exterior wall at x≈1128, support walls wall_030/wall_032).

**INFERRED (two materially different readings — unresolved):**
- **Reading X — counter/cabinet outlines mis-classified as walls (upstream extraction).** The thin compartment segments have the size/shape/arrangement of kitchen base-cabinet drawings, and a canonical counter spans across them. If `geometry_extraction_service` admitted counter graphics into the wall set, the raster faithfully drew them and produced tiny spurious cells. Fix would be **upstream in extraction/classification** — out of this mandate's scope and higher-risk. Color (#141414) matches real walls, so extraction cannot separate them by color alone.
- **Reading Y — legitimate small alcoves that `min_area` is too strict to keep.** If the cells are real architecture, lowering `min_area` would reconstruct them. But see §4: this is both **insufficient** and **risky**.

I cannot decide X vs Y from the available artifacts without the source PDF's authored intent / a wall-vs-furniture ground-truth label, which is not present in canonical.

---

## 4. Candidate approaches — assessed, NOT implemented

| Option | Would it make the Kitchen base complete? | Risk / blocker |
|---|---|---|
| **(a) Better reconstruction of the alcove** (lower/revise `min_area_px`) | **No, not by itself.** comp#3/comp#4 are **separate components** from comp#5 (RR1) with no bridged opening between them. Reconstructing them yields **two new tiny CONFIRMED rooms**, each labeled "Kitchen" by `group_by_room` — i.e. *more* kitchen fragments, not a single room holding base+chimney. Inventory would still be MISMATCH per section. | To catch base-B you must admit a 16,640-px cell; noise comp#9 (14,473) sits just below it — a few-thousand-px tuning window. **This is single-case tuning, which the mandate forbids**, and I have **no representative ground-truth corpus** to measure regression across plans. |
| **(b) Explicit user-confirmed assignment** for ambiguous furniture (e.g. extend `room_membership` to a general room tag → force base units into KITCHEN/RR1) | **Yes** — RR1 already contains the chimney; adding the base units makes it complete → MATCH. This is the **only** path that does not touch extraction, thresholds, or labels. | **No such contract exists today.** `room_membership` (room_membership_service) carries only KITCHEN / LIVING_AREA / INDEPENDENT_DINING for **dining disambiguation** — not general furniture→room assignment. Adding one is a **schema + editor + resolver contract change** requiring its own approval and tests; not an established fix. |
| **(c) Documented automatic assignment rule** (e.g. nearest-CONFIRMED-room for out-of-polygon furniture) | Possibly | `reconstruct_rooms` **deliberately forbids** broad nearest-room reassignment (`:291-297`, `:320-321`). Adding it reverses a documented invariant and risks mis-assigning genuinely ambiguous items across the whole corpus. Prohibited by the mandate ("do not force ambiguous furniture into a room"). |
| **(d) Retain uncertainty + block incomplete AI generation** | n/a (does not render it) | **Already implemented and approved** (Steps 2I/2J Candidate C: inventory-MISMATCH status + pre-dispatch `BASE_INVENTORY_MISMATCH` gate). Honest, reversible, label-safe. **This is the current correct behavior.** |

**Net:** the only option that would actually produce a complete Kitchen base render **without** a prohibited change is **(b)**, and (b) needs a new canonical room-assignment contract that does not yet exist. (a) is both insufficient (fragments persist) and a mandate-violating single-case tune. (c) is explicitly prohibited. (d) is already in place.

---

## 5. Required evidence before any implementation

1. **Canonical/product intent:** a decision on whether `kitchen-base` counters are meant to belong to the Kitchen room, expressed as a **durable contract** (schema field + editor affordance), not inferred by geometry.
2. **X vs Y determination:** inspect the source PDF to confirm whether the thin compartment segments are authored walls or cabinet/counter graphics — i.e. whether the defect is in `geometry_extraction_service` classification or in `min_area`.
3. **Ground-truth corpus** (≥ a handful of representative plans with labeled rooms) to measure false-room / missed-room rates of any `min_area` or classification change. The mandate forbids tuning against this one design.

---

## 6. Required regression coverage (for whichever direction is later approved)

- An **offline, detector-free** scene-build assertion on this fixture: the three kitchen uids' assignment (chimney→CONFIRMED RR1; base units→UNCERTAIN) — locks today's behavior so a future change is observable.
- If **(b)**: a test that an explicit KITCHEN assignment places both base units in RR1 → `assess_section_base_inventory` returns **MATCH** and the pre-dispatch gate permits dispatch.
- If **(a)/extraction**: per-plan room-count assertions across the ground-truth corpus (no new false rooms; previously-proven rooms unchanged), plus the existing `tests/test_dynamic_rooms.py`, `test_room_assignment.py`, `test_kitchen_scene_inventory.py`, `test_inventory_gate_generate.py` kept green.
- Keep the current honest-containment tests (`test_inventory_gate_generate.py`) green regardless.

---

## 7. Stop conditions — TRIGGERED

- **Canonical room intent is missing** for the affected furniture (VERIFIED: `room=None`, `room_membership=None`).
- **Reconstruction semantics are ambiguous / multiple interpretations** (VERIFIED §3: counter-outline-as-wall vs legitimate-small-alcove; cannot be resolved from canonical alone).
- **Required artifacts for safe tuning are unavailable** (no ground-truth corpus; mandate forbids single-case tuning).

Therefore I stop at recommendation. **Recommended next step:** treat this as a **product-contract decision** (Option b — explicit room assignment for wall-mounted/ambiguous counters) scoped under its own approval, while keeping the already-approved honest containment (Option d) as the safe default. Do **not** change `min_area_px`, furniture→room partitioning, automatic assignment, geometry extraction, labels, or provider behavior on the strength of this single case.

---

## 8. Commands run / changed-file status

- **Changed files:** none (code/tests/data/schema/config all untouched). This report is the only new file.
- **Read-only diagnostics** (scratchpad, deleted-safe): `trace_kitchen_assignment.py`, `trace_raster_rejection.py`, `trace_alcove_walls.py` — each run with `PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe <script>`; DB reads via `capture_generation_snapshot`; no mutation, no network/paid calls.
- **Git:** not a repository — no commit/branch/PR performed or possible.

## 9. Evidence labels

- **VERIFIED:** version match; the three items' centres/room fields; `min_area_px=40,960` and its binding term; comp#3=16,640 / comp#4=26,114 / comp#5=210,457 and their keep/drop; chimney contained in RR1; base units' nearest walls owned by zero proven rooms; no opening bridging the band; the inventory MISMATCH + pre-dispatch gate behavior.
- **INFERRED:** that comp#3/comp#4 are kitchen counter/cabinet outlines (shape/size/arrangement + counter footprint crossing them) vs. legitimate alcoves — unresolved.
- **UNVERIFIED:** corpus-wide regression impact of any `min_area`/extraction change (no ground-truth available); whether the source PDF authored those segments as walls.
