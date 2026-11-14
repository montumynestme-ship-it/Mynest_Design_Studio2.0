# Phase 4C — Step 2H: Room-Grouping Reconciliation Plan (REPORT-ONLY)

**Status:** PROPOSAL — REQUIRES APPROVAL. No implementation, test, or prompt changes were made in this step.
**Scope:** The confirmed grouping mismatch between `prompt_service.group_by_room()` (furniture-cluster sections, feeds prompts/manifest/inventory) and `architectural_service.reconstruct_rooms()` (wall-topology scene rooms, feeds the base render + scene).
**Reproduction anchor:** design version `1831bf84` — the dining table is listed in the "Dining Area" section/prompt but is absent from that section's base render.

> **STOP CONDITION TRIGGERED — see §6.** Every reconciliation direction that does *not* violate a hard prohibition (no artificial open-plan split, no furniture reassignment, no prompt-only workaround) changes an **externally observable contract**: either the eligible-sections labels (API + frozen historical records + F-2 matching) or the base-render resolution semantics (which base a section renders against, altering the historical door-only "Dining Area" behavior). I am therefore reporting and awaiting explicit approval before any implementation.

---

## 1. Exact source references and call flow

### 1.1 The two grouping systems

| System | Entry point | Groups by | Open-plan result | Feeds |
|---|---|---|---|---|
| **Section grouping** | `prompt_service.group_by_room(furniture)` | furniture clustering, anchor-seeded (largest kitchen appliance seeds KITCHEN separately from the dining table's DINING) | **SPLITS** → `"Kitchen"` + `"Dining Area"` | sections, prompts, bboxes, manifest, inventory validation |
| **Scene grouping** | `architectural_service.reconstruct_rooms(...)` | wall cycles (topology); calls `group_by_room` only to *label furniture and group unproven leftovers* | **MERGES** → one CONFIRMED `"Kitchen & Dining Area"` + an UNCERTAIN furniture-fallback `"Dining Area"` twin | `scene_service.build_scene` → base render, 2D→3D gate, validation |

### 1.2 Callers (from grep, verbatim)

`group_by_room` consumers:
- `prompt_service.py:1339` — `get_eligible_sections` (section list)
- `prompt_service.py:1406` — `room_bboxes` (per-room crop/base keying)
- `prompt_service.py:1441` — `build_room_prompts` (per-room prompts + the `rooms` list returned to `generate()`)
- `architectural_service.py:286` — inside `reconstruct_rooms` (labels furniture + groups unproven leftovers)
- `furniture_inventory_validation_service.py:96` — inventory validation
- `furniture_manifest.py:80` — the manifest (consequently manifest ≡ prompt)

`reconstruct_rooms` consumers:
- `scene_service.py:321` — `build_scene` (authoritative scene → base render)
- `generation_service.py:608` — reconstruct meta
- `prompt_service.py:1364 / 1390 / 1466` — **fallback only** (when no furniture, reconstruct sections from walls)

`get_eligible_sections` consumers:
- `generation_service.py:1142` — chooses `target_rooms` for a full-plan generation
- `prompt_service.py:1496`

### 1.3 The precise seam (where the mismatch becomes a missing table)

In `generation_service.generate()`:

1. `target_rooms = prompt_service.get_eligible_sections(canonical)` → `["... , "Kitchen", "Dining Area", ...]` (group_by_room; table lives in **"Dining Area"**). — `:1142`
2. `style, rooms = prompt_service.build_room_prompts(..., requested_rooms=target_rooms)` → the "Dining Area" prompt lists the dining table. — `:1144`
3. `scene = scene_service.build_scene(file_id, canonical=canonical)` → scene rooms from `reconstruct_rooms`: a CONFIRMED **"Kitchen & Dining Area"** (contains the table) **plus** an UNCERTAIN furniture-fallback **"Dining Area"** twin (door-only, no table). — `:1179`
4. `label_to_id = _room_id_map(scene.rooms)` — keys the **whole** normalized label only; it does **not** split `"Kitchen & Dining Area"` on `&`. — `:1185`, builder at `:218`
5. Base renders arrive from the frontend keyed by scene-room label; `base_map` holds `"kitchen & dining area"` (base **with** the table) and `"dining area"` (fallback twin, **door-only**). — `:1076`
6. `_lookup_base("Dining Area")` tries `("Dining Area", "dining area", label_to_id.get("dining area"))` → matches the **door-only fallback twin**. The combined room's base (with the table) is keyed `"kitchen & dining area"`, which is **not** a requested section → never selected for the "Dining Area" render. — `:1213`

Contrast: `_room_faithful_map` (`:170`) **already** splits combined labels on `&` (`:190`), so the *faithfulness gate* treats `kitchen` and `dining area` as faithful from the combined room. The **id resolver** (`_room_id_map`) does not mirror that convention — that asymmetry is the mechanical fault line.

---

## 2. Confirmed facts vs hypotheses vs unknowns

### Confirmed (read directly from code / frozen artifacts)
- `group_by_room` splits the open-plan into `Kitchen` + `Dining Area`; `reconstruct_rooms` merges it into `Kitchen & Dining Area` (+ fallback twins). (code)
- The dining table's canonical record has **no room field** (`room=None`); each system derives its membership independently. (established in Step 2F/2G)
- `get_eligible_sections`, `build_room_prompts`, `room_bboxes`, `furniture_manifest`, and `furniture_inventory_validation` **all** consume `group_by_room` → prompt, manifest, and inventory are mutually consistent but **disagree with the scene**. (grep §1.2)
- `_room_faithful_map` splits on `&`; `_room_id_map` does not. (code `:190` vs `:218`)
- `test_dynamic_rooms.py:29,34` **asserts** the split labels verbatim: `== ["Living Area", "Kitchen", "Dining Area", ...]`. Any label-merging reconciliation breaks these assertions. (test)

### Hypotheses (strongly supported, not yet proven end-to-end on `1831bf84`)
- For `1831bf84`, section "Dining Area" resolves to the door-only fallback twin's base, which is why the rendered room omits the table. (consistent with Step 2F door-only finding; not re-run live this step)
- Making `_room_id_map` split on `&` (mirroring `_room_faithful_map`) would make `_lookup_base("Dining Area")` resolve to the combined room id — **but** a literal `"dining area"` fallback-twin base may still shadow it depending on `base_map` key precedence. (needs the regression test in §5 to confirm)

### Unknowns (must be resolved before implementation)
- Key precedence in `base_map` when **both** `"dining area"` (fallback twin) and a `&`-derived `"dining area"→combined-id` entry exist — which wins in `_lookup_base`'s candidate order?
- Whether the frontend emits a base for the UNCERTAIN fallback twin at all, or only for CONFIRMED scene rooms (determines whether the door-only twin base even exists in `base_map`).
- Whether any consumer downstream of `requested_rooms`/`room_geometry` in the API or stored generation records relies on the **split** labels as stable identifiers.

---

## 3. Minimal proposed change (PROPOSAL — REQUIRES APPROVAL)

Two candidate directions. **Both preserve canonical** (no split, no reassignment, no prompt rewrite). I recommend **Candidate A** as the smallest and most faithful, but it is still contract-touching.

### Candidate A — mirror the existing `&`-split in the id resolver (recommended, smallest)
**Change:** In `_room_id_map` (`generation_service.py:218`), register sub-section names for combined rooms exactly as `_room_faithful_map` already does — split the label on `&` and map each sub-section's normalized name to the combined room's stable id (combined/CONFIRMED room wins over a fallback twin).

**Effect:** `_lookup_base("Dining Area")` resolves to the combined `"Kitchen & Dining Area"` base, which contains the dining table. "Kitchen" and "Dining Area" then share the combined open-plan base — correct for a single physical open-plan room.

**Why this is the reconciliation point:** it aligns the *base-render resolution* with the faithfulness gate's already-established `&`-splitting convention, so a sub-section inherits the base of the wall-proven room that actually contains its furniture. It does **not** change section labels, prompts, the manifest, inventory counts, or canonical. Scope: **one function**, mirroring a proven in-repo pattern.

**Residual concern:** two sections resolving to one base changes the historical door-only "Dining Area" behavior (contract impact — see §4). Must confirm fallback-twin key precedence (§2 unknown) so the combined base wins deterministically.

### Candidate B — derive sections from the authoritative scene (larger, label-changing)
**Change:** Make `get_eligible_sections` / `build_room_prompts` / `room_bboxes` derive renderable sections from `scene_service.build_scene` reconstruction so prompt-inventory ≡ base-render-inventory, unifying on scene labels (`"Kitchen & Dining Area"`).

**Effect:** fully consistent, but section **labels change** → breaks `test_dynamic_rooms`, the eligible-sections API response, F-2 matching, and frozen `room_geometry`/`requested_rooms` labels. This is a **contract-breaking** change and the larger of the two.

**Recommendation:** Do **not** pursue B unless A is shown insufficient; A is the minimal honest fix.

---

## 4. Expected API / historical-data compatibility impact

| Surface | Candidate A | Candidate B |
|---|---|---|
| Eligible-sections API labels | unchanged | **changed** (merged) |
| `build_room_prompts` output labels | unchanged | **changed** |
| Base-render resolution for a sub-section | **changed** (now resolves to combined base; prior behavior = door-only twin) | changed |
| Frozen `requested_rooms` / `room_geometry` labels | unchanged | **changed** → breaks replay/F-2 |
| F-2 `matchSceneRoom` (id-first) | needs verification that combined id is matchable from a sub-section row | **breaks** (label drift) |
| `test_dynamic_rooms.py:29,34` | unaffected (asserts section labels only) | **FAILS** (expects split labels) |
| Canonical invariant (walls/openings/furniture/room assignment) | **preserved** | preserved |

**Candidate A is additive at the label level but changes which base a sub-section renders against.** That is an observable behavior change for open-plan plans and for any stored generation whose "Dining Area" was previously rendered door-only. This is the reason approval is required rather than proceeding.

---

## 5. Proposed deterministic offline regression test

**New test** (offline, no provider, no paid call), e.g. `tests/test_room_grouping_reconciliation.py`:

- Build the scene from `1831bf84` (or the equivalent synthetic open-plan fixture already used in `test_kitchen_scene_inventory.py`): `scene = scene_service.build_scene(FID, canonical=<frozen/synthetic>)`.
- Compute section inventory via `prompt_service.group_by_room(canonical["furniture"])` and the scene-room inventory via `reconstruct_rooms`/`build_scene`.
- **Assert the dining table is reachable from the section that owns it:** the stable scene-room id that `_room_id_map` maps `"Dining Area"` to contains the dining-table uid. **This assertion fails today** (door-only twin) and passes under Candidate A.
- Add a focused unit test on `_room_id_map`: a room labelled `"Kitchen & Dining Area"` registers both `kitchen` and `dining area` → the combined room id (mirror of the existing `_room_faithful_map` behavior, which can be asserted side-by-side as the reference contract).

Write it as a **failing (xfail→fail) guard first** so the defect is locked before any fix, consistent with prior steps. Do not weaken or edit existing assertions.

**Existing tests to run as the regression gate (must stay green):**
```bash
.venv/Scripts/python.exe -m pytest tests/test_dynamic_rooms.py tests/test_room_assignment.py \
  tests/test_furniture_inventory_validation.py tests/test_furniture_placement_2d_to_3d.py \
  tests/test_generation_pipeline_fix.py tests/test_prompt_geometry.py \
  tests/test_kitchen_scene_inventory.py tests/test_base_render_gate.py \
  tests/test_base_render_persistence.py tests/test_postgen_status_surfaced.py -q
```
Frontend (F-2 / fidelity logic unaffected by A, run to prove no drift):
```bash
cd ../frontend && npx playwright test e2e/room-match.spec.ts e2e/ai-fidelity-status.spec.ts \
  e2e/gallery-stale-preview.spec.ts e2e/dining-area-preview.spec.ts e2e/postgen-low-fidelity.spec.ts
```

---

## 6. Risks, unresolved questions, stop conditions

**Risks**
- **Base-sharing side effect (A):** "Kitchen" and "Dining Area" sections render against the same open-plan base. Correct for one physical room, but if the two prompts list disjoint inventories (table vs appliances), each render shows *more* furniture than its own prompt lists — a prompt↔base inventory asymmetry in the opposite direction. Must decide whether that is acceptable (it reflects reality) or whether open-plan should be surfaced as a single section to the user.
- **Fallback-twin shadowing:** if a literal `"dining area"` door-only base is present in `base_map`, candidate order in `_lookup_base` must be defined so the combined base wins; otherwise A has no effect.
- **F-2 matching:** confirm a gallery row keyed by the sub-section label can still match the combined scene room by id.

**Unresolved questions (block implementation until answered)** — see §2 "Unknowns": base_map key precedence, whether the fallback twin base is emitted at all, and whether any stored record keys off split labels.

**Stop conditions (per the Step 2H mandate)**
- Both viable directions change an external contract (base-render resolution semantics in A; section labels in B). Per the mandate — *"Stop and report if the reconciliation would require a contract-breaking change… Await explicit approval before implementation"* — I am stopping here.
- No open-plan split, no furniture reassignment, no prompt-only workaround, and no weakened assertions are proposed; if approval steers toward any of those, that is out of scope and would need a new mandate.

**Recommended decision for the user:**
1. Approve **Candidate A** (mirror `&`-split in `_room_id_map`) + the failing-first regression test, accepting the base-sharing semantics for open-plan rooms; **or**
2. Request the open-plan to be surfaced as a single `"Kitchen & Dining Area"` section end-to-end (Candidate B — contract/historical migration, larger); **or**
3. Keep as-is and only *surface* the open-plan truth in the gallery (no render change).

Awaiting explicit approval before any code or test is written.
