# Phase 4C — Step 2Q: Execute, Validate, Repair — Completion Report

**Headline:** The deterministic pipeline is **verified faithful** (inventory exactly-once, Bedroom-1 containment fix, Kitchen inclusion mechanism), but a **real fal AI output was inspected and FAILS furniture fidelity** — it hallucinates an entire stock kitchen. Deterministic success does not equal AI-render success. No shared-DB writes/deletes; no paid calls.

---

## 1. Implementation verified (read-only)
2P changes intact: `prompt_service.py` (14 `containment_map` refs + `build_section_containment_map`), `furniture_manifest.py` (5), `generation_service.py` (11); `tests/test_containment_sectioning.py` present. Layout PUT (`put_layout`→`save_layout`) persists `render_room`; the scene endpoint binds `design_version_id`. App not under git (only `floorplan-parser/.git`).

## 2. Isolated/offline integration validation — ALL PASS (read-only; no DB writes)
`validate_2q.py` over the full offline path (canonical → scene → containment → sections → manifests → gates → binding), v79:
```
(1) exactly-once in scene: dupes=none  missing=none
(2) no unexpected (scene ⊆ canonical): extra=none
(3) wardrobe section: nearest=Bedroom 1  containment=Bedroom 3
(4) tagged Kitchen bases: both in confirmed kitchen=True  exactly_once=True  render_inclusion=True
(5) canonical transforms unchanged by tag+move: True
(6) untagged legacy: bases in confirmed kitchen=False  any render_inclusion=False
(7) current design_version_id=85759b78… v79 (scene binds this)
[gate] Bedroom1 containment=MATCH   Kitchen tagged=MATCH
```
Every Step-2 requirement is met: each canonical item accounted **exactly once**; **no unexpected items**; Bedroom-1 wardrobe consistent with **authoritative containment** (Bedroom 3); both Kitchen base units included **exactly once** when tagged; **canonical transforms/geometry unchanged**; legacy (no `render_room`) unchanged; base render bound to the correct version/room.

## 3. Test totals / commands / exit codes (offline; NO generation-path/shared-DB tests)
```
pytest -q test_containment_sectioning test_render_inclusion test_inventory_reconciliation
         test_dynamic_rooms test_room_assignment test_kitchen_scene_inventory
         test_room_membership test_authoritative_merge test_prompt_geometry
         test_furniture_inventory_validation test_base_render_gate test_furniture_manifest
   → 140 passed, 0 failed (exit 0)
python validate_2q.py            → all checks pass (exit 0)
imports (generation/prompt/manifest services) → OK
```

## 4. Canonical→scene inventory reconciliation
22 real furniture items (openings + 5 room-tag annotations excluded): **22/22 present exactly once** in the deterministic scene; **no missing, duplicated, or extra**. The deterministic scene preserves the canonical inventory and architecture.

## 5. Bedroom & Kitchen gate results
| section | gate | note |
|---|---|---|
| Bedroom 1 (containment) | **MATCH** | wardrobe correctly sectioned to Bedroom 3 (was MISMATCH) |
| Bedroom 3 | MATCH | unchanged |
| Kitchen (untagged) | MISMATCH (blocked) | out-of-polygon base units — honest block |
| Kitchen (tagged `render_room=KITCHEN`) | **MATCH** | both base units included once |

## 6. Kitchen correction (Step 3) — PREPARED, blocked on persistence
The two intended units are confirmed against canonical v79: `kitchen-base-1787478607029` and `kitchen-base-1787478608231` (both `item_id=kitchen-base`, currently in the UNCERTAIN Kitchen twin). Applying the fix = set `render_room="KITCHEN"` on these two via the editor's `RenderRoomControl` (or the layout API), which `save_layout` persists **append-only as a NEW design version (v80)** — it never rewrites the v79 snapshot or alters transforms.
- **Exact operation (prepared, NOT executed):** `PUT /api/floor-plans/f6b65d2b-4f96-4931-9f08-67dbd09776f6/layout` with the full current layout where those two items carry `"render_room": "KITCHEN"` (equivalently: select each in the editor → "Render in Kitchen").
- **Blocker / dependency:** the only database is the **shared Postgres**; persisting this is a shared-DB write, which this sprint prohibits, and no isolated environment seeded with v79 is available. **Required minimum dependency:** explicit authorization to write to the shared DB, **or** an isolated DB seeded with the v79 design. I did not modify production/shared data.

## 7. Deterministic render capture (Step 4) — not newly captured; existing real artifacts inspected instead
No new before/after capture was produced: the capture harness (`frontend/src/harness.tsx`) has **no npm script** and needs a dev server + a save server (`127.0.0.1:8899`) + a WebGL browser, and the *tagged* Kitchen render additionally depends on the §6 persistence blocker. Rather than fabricate, I inspected a **real existing** fal render (below).

## 8. AI-output fidelity (Step 6) — **FAILS (verified by direct inspection)**
Real generation `174503c2-e046-4c1a-a57c-025ba12c1e15` (provider **fal**, model **fal-ai/flux-kontext/dev**, completed, bound to design_version **85759b78 / Kitchen / room_index 1**):

| artifact | sha256 (16) | dims | content |
|---|---|---|---|
| `…/room_1_Kitchen/base_render.png` | `385fd86032e3e8f5` | 1216×832 | deterministic base: wood floor, one wall, the **2 kitchen-base** boxes, **no chimney** (`inventory_status: MISMATCH`, base_room UNCERTAIN — pre-fix) |
| `storage/generations/174503c2…/1.png` | `2977dcfc1f389ef9` | 1216×832 | **fal AI output: a full stock kitchen** — rows of upper/lower cabinets, refrigerator, wall oven, microwave, dishwasher, two sinks, island + 2 bar stools, potted plant, coffee maker, knife block |

**Finding:** against a canonical Kitchen inventory of **2 kitchen-base + 1 chimney**, the fal output **invents extensive furniture/appliances not in the canonical design** and does not preserve the base — a severe **extra-furniture AI-fidelity failure**. Provenance recorded it honestly: `geometry_status: UNVERIFIED` (never FAITHFUL), `inventory_status: MISMATCH`. This is an **AI-output failure at the provider/conditioning layer, not a deterministic scene-builder defect** (the base render is faithful to canonical minus the out-of-room chimney). It must NOT be masked with a scene patch.
- **Scope of evidence:** one Kitchen output inspected in full; `geometry_status` is `UNVERIFIED` across production (the sole caller passes `output_verified=False`), and there is no calibrated detector, so a corpus-wide pass/fail rate is **not** established. AI fidelity overall = **FAILS on the inspected sample; UNVERIFIED at scale**.

## 9. Repairs this step (Step 5)
**No new deterministic defect was demonstrated** beyond those already handled (Bedroom-1 fixed in 2P; Kitchen inclusion mechanism in 2M/2N.2). The deterministic scene is faithful (§2–§4). Therefore **no code change** was made in 2Q — the right fix for the demonstrated problem (§8) is at the AI/conditioning layer, which is out of safe scope here (no provider change / paid calls without authorization). No validation gate weakened; no canonical geometry/threshold change; no scene patch to hide the AI hallucination.

## 10. Shared data (Step 7)
No deletion of the 32 mock/tracking records; **no new shared-DB records introduced** (this step performed only DB reads). The broader generation history on v79 (demo 110, fal 37, nvidia 18, mock 18, tracking 14) is pre-existing and untouched.

## 11. Files changed
**None** (code/tests/canonical unchanged this step; 2P/2M fixes already landed). Only this report is new. Scratchpad validation scripts are outside the project tree.

## 12. Remaining defects, blockers, next concrete action
1. **AI-output furniture hallucination (the dominant unsolved problem, §8):** the fal `flux-kontext/dev` EDIT path (current default, `FAL_USE_CONTROLNET=false`) does not preserve furniture. **Not** fixable by scene/section changes. Minimum dependencies: either (a) **structural conditioning** (depth/Canny/mask ControlNet — previously blocked on provider entitlement/approval), or (b) a **provider/model change** (needs authorization), or (c) keep the deterministic render as the accepted output and continue rejecting unfaithful AI via the honest `UNVERIFIED` status. Paid generations require explicit authorization.
2. **Kitchen inclusion not applied to live v79 (§6):** needs shared-DB write authorization or an isolated DB seeded with v79.
3. **New before/after deterministic capture (§7):** needs the harness wired to a script + dev/save servers (isolated), plus the §6 persistence for the tagged variant.
4. **Shared-DB test records:** cleanup still pending authorization; re-point generation-path tests to an isolated DB.

**Not claiming success:** the deterministic pipeline is verified correct and 140 offline tests pass, but the **real AI render fails furniture fidelity** (inspected evidence), and that is the next thing to fix — at the AI/conditioning layer, under explicit authorization.
