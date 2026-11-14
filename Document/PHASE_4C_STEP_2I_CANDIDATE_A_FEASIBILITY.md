# Phase 4C — Step 2I: Candidate A Feasibility Verification (REPORT-ONLY)

**Mode:** REPORT-ONLY. No source/test/doc/DB/app-state changes. No AI/hosted inference/paid calls. One read-only `SELECT` of `design_versions.canonical_json` for `1831bf84` and a deterministic offline scene build were performed for verification.

**Headline verdict:** **Candidate A is UNSAFE / insufficient as specified.** It does not address the root cause and cannot by itself restore prompt↔base inventory fidelity. The root cause is a **furniture-partition mismatch** between `group_by_room` (anchor clusters) and `reconstruct_rooms` (wall cycles + UNCERTAIN fallbacks), not a missing id alias. A correct fix would require changing furniture→room partitioning and/or public section labels — both hit the Step 2I stop conditions. **Recommended direction: Candidate C** (surface the mismatch honestly), which is label-safe, record-safe, and reuses machinery already built in Steps 1F/1H.

> **Correction to Step 2H:** 2H stated `_room_id_map` "does not split on `&`". That was a misread (I had read `room_eligibility`'s `by_label` loop, not `_room_id_map`). The real `_room_id_map` (generation_service.py:273) **already** splits on `&` with CONFIRMED precedence. So "Candidate A" as written in 2H is already implemented — and, as shown below, is shadowed and insufficient.

---

## Evidence classification

- **VERIFIED (executed):** scene rooms via `scene_service.build_scene("…f6b65d2b…", canonical=<1831bf84 from DB>)`; `prompt_service.group_by_room`; `generation_service._room_id_map`. Run offline against the real canonical (34 furniture items).
- **VERIFIED-MODEL (faithful re-implementation of cited code):** the `base_map` emission set (BaseRenderBatch gate) and `_lookup_base` candidate resolution were computed by re-implementing the exact, cited logic over the VERIFIED scene/id-map outputs. `_lookup_base` is a nested closure inside `generate()`, so it was modeled, not called; the model mirrors generation_service.py:1213-1233 line-for-line.
- **AGENT-REPORTED HISTORICAL:** gen `5d97cc43` (prior session) showed a "Dining Area" base render captured + used (`used_base_render=True`, SHA-verified) and the dining table absent from its output — consistent with the mechanism below.
- **HYPOTHESIS / UNKNOWN:** flagged inline.

---

## 1. Base-map construction and precedence — VERIFIED (+ VERIFIED-MODEL)

**Construction** (`generation_service.generate`, :1076-1082): `base_map[lbl] = decoded` and `base_map[_normalize_section_name(lbl)] = decoded` for each key the frontend sends in `base_renders`. **base_map is keyed only by what the frontend emits (room id and room label) plus normalized forms — it has no synthesized id keys of its own.**

**`_room_id_map`** (:273-296) maps normalized label → stable scene id, splitting combined labels on `&`, CONFIRMED wins:
```
'Kitchen'      -> 'kitchen-dining-area'
'Dining Area'  -> 'kitchen-dining-area'   # via the & split
```

**`_lookup_base(label)`** (:1213-1233) candidate order: `(label, _normalize_section_name(label), label_to_id.get(norm))` — **exact label first, normalized second, `&`-aware scene id last.**

**Resolution on `1831bf84` (VERIFIED-MODEL over VERIFIED inputs):**
| Requested section | candidates | base_map has | **resolves to** |
|---|---|---|---|
| `Kitchen` | `Kitchen`, `kitchen`, `kitchen-dining-area` | `Kitchen` (UNCERTAIN twin) present | **`Kitchen` twin** (2 base units) |
| `Dining Area` | `Dining Area`, `dining area`, `kitchen-dining-area` | `Dining Area` (UNCERTAIN twin) present | **`Dining Area` twin** (door only — **no table**) |

The `&`-derived `kitchen-dining-area` id (candidate[3], the base that **does** contain the table) is **never reached**, because the UNCERTAIN twin's **exact label** matches at candidate[1]. **This is the mechanical root of the missing-table symptom.**

---

## 2. Frontend base-render emission — VERIFIED

- `DesignStudio.tsx:873` passes `rooms={baseCaptureScene.rooms}` — the full `fetchScene` result, **no `validation_status` filter**; `baseCaptureExpectedRef` expects every room (`:432`).
- `BaseRenderBatch.tsx:162` gate: `valid && room.furniture.length > 0`; keyed by **both** `room.id` and `room.label` (`:163-164`).
- Doors/windows are canonical items named `door`/`window` and live **inside** `room.furniture` (scene_service.py:72-81). So the door-only `dining-area` twin has `furniture.length == 1 > 0` → **it passes the gate and is emitted** (keyed `dining-area` + `Dining Area`).
- **Conclusion:** UNCERTAIN fallback twins are **rendered and included**, not filtered — on the frontend or the backend. Corroborated by historical gen `5d97cc43` (a "Dining Area" base was captured + used). The only honest exclusion is a blank/failed WebGL capture (`valid=false`), not room status.

---

## 3. Shared-base inventory consequences — VERIFIED (decisive)

Inventories for `1831bf84` (uids abbreviated):

| Source | Kitchen-side | Dining-side |
|---|---|---|
| **group_by_room prompt** `Kitchen` | kitchen-base, kitchen-base, **chimney** | — |
| **group_by_room prompt** `Dining Area` | — | **dining-table**, 4× door |
| **scene `kitchen-dining-area`** (CONFIRMED) | **chimney**, door | **dining-table** |
| **scene `kitchen` twin** (UNCERTAIN) | kitchen-base, kitchen-base | — |
| **scene `dining-area` twin** (UNCERTAIN) | — | door |
| **base actually selected (today)** | `Kitchen` twin → base units only (**no chimney**) | `Dining Area` twin → door only (**no table**) |

**The two groupings partition the same furniture differently:** the kitchen base units fall **outside** the proven wall polygon → UNCERTAIN `kitchen` twin; the chimney + table fall **inside** → CONFIRMED combined room. Therefore:

- **No existing base render matches any section's prompt inventory.**
- Even if Candidate A were un-shadowed so `Dining Area` → `kitchen-dining-area`: that base shows **chimney + table** (chimney is **not** in the Dining prompt → asymmetry), and `Kitchen` → the same combined base would show **table** (not in the Kitchen prompt) while **still omitting its own base units** (they live in the separate UNCERTAIN twin). So Candidate A **introduces new prompt↔base asymmetries in both directions and still fails to deliver the base units.**
- **Implications:** inventory-validation and furniture-manifest are built from `group_by_room` and would keep asserting the section inventory the base cannot satisfy; the 2D→3D geometry gate validates the whole scene (not per-section membership), so it does not catch this; user-visible result = a section render whose furniture set disagrees with its own prompt.

---

## 4. Gallery matching (F-2) — VERIFIED

`matchSceneRoom(rooms, roomId, roomLabel)` (scene.ts): **if `roomId` is present, trust ONLY `r.id === roomId`**; otherwise normalized-label match. A section row can match the combined scene room **without any public-label change** iff the row carries `roomId == "kitchen-dining-area"`. Today the rows are produced per section label; whether they already carry the combined scene id is an **UNKNOWN** (depends on how the gallery row's `roomId` is populated from the generation record — not confirmed this step).

**Smallest deterministic regression test (pure logic, no DOM):**
`expect(matchSceneRoom(sceneRooms, 'kitchen-dining-area', 'Dining Area')?.id).toBe('kitchen-dining-area')` plus the negative `matchSceneRoom(sceneRooms, 'dining-area', 'Dining Area')` returns the door-only twin — locking the id-vs-label behavior before any change.

---

## 5. Historical compatibility — VERIFIED, with a cache caveat

- `requested_rooms` (generation_service.py:735) and `room_geometry` (`:754`, keyed by `img.label`) are **label-keyed**. A change that only alters **which base bytes** a section resolves to leaves these record keys and their interpretation **unchanged** — no silent record migration.
- Stored output PNGs are immutable on disk; only **future** renders would differ. (So this does not rewrite history — but it does mean the gallery would show a different image for the same labelled section going forward.)
- **Cache caveat (important):** `_compute_room_hash` (`:~900`) hashes `room_label + whole-plan geometry payload + design_intent + provider + model` — it does **not** include the selected base render. So a base-resolution change **does not bust the cache**: existing cached "Dining Area" renders (made from the door-only base) would keep being served on a HIT. Any resolution fix would need explicit cache invalidation to take effect — otherwise it is silently inert for cached rooms. **Do not claim compatibility from unchanged labels alone** — confirmed here that the observable render would change for new generations while cached ones stay stale.

---

## 6. Candidate comparison

| | **A — `&` aliases in `_room_id_map`** | **B — expose merged room as one section** | **C — surface mismatch as unverified/invalid** |
|---|---|---|---|
| Already present? | **Yes** (and shadowed by exact-label precedence) | No | Partially (1F/1H LOW_FIDELITY + honest tri-state already exist) |
| Would it fix the table? | Only if `_lookup_base` order also changed to prefer the CONFIRMED combined id over the UNCERTAIN twin label — a cross-room precedence change | Yes (section == scene room) | No render change; marks the render not-faithful |
| Inventory fidelity | **Still broken** (base units in a separate UNCERTAIN twin; adds chimney/table across sections) | Consistent for the open-plan, but merges Kitchen+Dining UX | Honest: no false "faithful" claim |
| Public labels | unchanged | **changed** ("Kitchen"/"Dining Area" → "Kitchen & Dining Area") | unchanged |
| Breaks `test_dynamic_rooms.py:29,34` | no | **yes** | no |
| API / frozen records (`requested_rooms`, `room_geometry`, F-2) | unchanged keys; cache stays stale | **label drift → breaks replay/F-2** | unchanged |
| Furniture assignment / geometry | untouched | untouched | untouched |
| Scope | small code, but semantically risky + insufficient | large + contract-breaking | small, additive, truthful |
| **Stop condition hit?** | partial (precedence change + still-wrong result) | **yes** (labels/records) | **no** |

---

## Recommendation (explicit trade-offs)

**Adopt Candidate C** as the only label-safe, record-safe, non-prohibited option: detect per-section that the selected base's inventory does not cover the section's `group_by_room`/manifest inventory, and surface that section as **UNVERIFIED / not-faithful** (reusing the honest tri-state and the LOW_FIDELITY surfacing already built in Steps 1F/1H) rather than presenting a mismatched base as faithful. This does not "repair" the render, but it stops the system from making a false fidelity claim, and it is fully reversible.

- **Trade-off:** C improves honesty, not pixels — the open-plan section renders remain inventory-incomplete until the partition itself is reconciled.
- **A** should not be pursued as specified: the aliases already exist, un-shadowing them is a risky precedence change, and it still cannot place the base units. **B** is contract-breaking (stop condition) and should only be considered under a new mandate that explicitly accepts label/record migration.
- The genuine root-cause fix (one authoritative furniture→room partition feeding both prompts and scene) is a furniture-assignment/open-plan change — **explicitly prohibited** by the Step 2H/2I mandates — so it must not be undertaken without a new, explicit authorization.

---

## Minimal regression tests + existing gates

**New (offline, deterministic, no provider):**
1. Backend `tests/test_room_grouping_reconciliation.py`: build scene from `1831bf84` (or the synthetic open-plan fixture); assert the **current** fact as a guard — `_lookup_base`-equivalent resolution for `"Dining Area"` selects the door-only twin whose furniture excludes `dining-table`, while `kitchen-dining-area` contains it. This locks the defect and will flip only under an approved fix.
2. Backend: assert the **partition mismatch** directly — the union of base-render inventories for the Kitchen/Dining sections ≠ the `group_by_room` inventory for those sections (base units unreachable).
3. Frontend `e2e/`: the `matchSceneRoom` id-vs-label test in §4.

**Existing gates to keep green (no edits, no weakening):**
```bash
# backend
.venv/Scripts/python.exe -m pytest tests/test_dynamic_rooms.py tests/test_room_assignment.py \
  tests/test_furniture_inventory_validation.py tests/test_generation_pipeline_fix.py \
  tests/test_prompt_geometry.py tests/test_kitchen_scene_inventory.py \
  tests/test_base_render_gate.py tests/test_base_render_persistence.py \
  tests/test_postgen_status_surfaced.py -q
# frontend
cd ../frontend && npx playwright test e2e/room-match.spec.ts e2e/ai-fidelity-status.spec.ts \
  e2e/gallery-stale-preview.spec.ts e2e/dining-area-preview.spec.ts e2e/postgen-low-fidelity.spec.ts
```

---

## Is Candidate A safe? — **UNSAFE / insufficient (verified).**

The `&` aliases already exist and are shadowed; un-shadowing them requires a cross-room `_lookup_base` precedence change, would not place the kitchen base units (separate UNCERTAIN twin), and would introduce new prompt↔base asymmetries — all without busting the stale cache. The correct reconciliation requires changing furniture partitioning or public labels, which hits the stop conditions.

## Stop conditions — TRIGGERED

Correct behavior requires either changing **public room labels** (Candidate B) or **furniture→room partitioning / open-plan handling** (the true root cause) — both prohibited by the mandate. No records migrated, no expected results changed, no tests weakened. **Awaiting explicit approval** before any implementation; if the goal is only to stop false fidelity claims, Candidate C can be scoped next under its own approval.

## Unknowns to resolve before any implementation
1. How the gallery row's `roomId` is populated from the generation record — whether an open-plan section row can already carry the combined scene id for F-2.
2. Whether the frontend `SceneRoom.furniture` type mirrors the backend (doors included) in all code paths, or only the serialized scene (checked for the scene endpoint; not audited for every caller).
3. Exact cache-invalidation surface if any render-changing fix is later approved.
