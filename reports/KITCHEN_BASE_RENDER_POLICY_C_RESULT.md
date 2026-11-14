# Policy C — Kitchen & Dining Base-Render / Counter-Assignment: Result

**Outcome: no code change — legitimately unresolved room ownership (Case 4) + an owner merge/split decision, now VERIFIED with live v79 runtime evidence.** The MISMATCH gate is working correctly and honestly; the deterministic design is complete (the counters ARE rendered). A safe fix is not available without **inventing counter→room ownership** or **weakening the gate** (both prohibited, both explicit stop conditions). This independently confirms the repo's own `AIR-03 = DEFERRED_WITH_REASON`. **No files changed. TeleCRM never touched. No paid calls. DB read-only.**

Labels: **[VERIFIED]** = reproduced here; **[AGENT-REPORTED]** = prior report; **[INFERRED]**; **[UNKNOWN]**.

## 1. Safety / scope [VERIFIED]
- Worked only in `D:\Latest_mynest_design_version\mynest-design-studio` (MyNest). The session cwd is a TeleCRM git repo — **not read, edited, run, or committed**.
- MyNest is **not a git repository** → no branch/commit/diff; working tree unchanged.
- Canonical v79 `85759b78` / floor `f6b65d2b`; source `original.pdf` 4179 B, sha16 `e440a2184e9196ad` [VERIFIED earlier].

## 2. Root cause — the Kitchen section is split across two rooms [VERIFIED runtime]
Deterministic scene rooms (v79):
| Room | Status | Furniture |
|---|---|---|
| Kitchen & Dining Area | CONFIRMED | **chimney**, dining-table |
| Kitchen | **UNCERTAIN** | **kitchen-base, kitchen-base** |

- `group_by_room` → **"Kitchen" section expects `[kitchen-base, kitchen-base, chimney]`**.
- `merge_map = {}` (membership **REVIEW_REQUIRED**); `containment_map` has **no kitchen/dining entries**.
- **No single base room contains the whole Kitchen inventory:** the UNCERTAIN "Kitchen" twin (base actually selected) has the counters but **omits the chimney** → `MISMATCH missing=[Chimney]`; the CONFIRMED combined room has the chimney but omits the counters → `MISMATCH missing=[Kitchen Base]`.
- Affected functions: `architectural_service.reconstruct_rooms` (counters → UNCERTAIN leftover: centres outside the floor polygon, `nearest_wall_id` owned by zero confirmed rooms [AGENT-REPORTED, consistent]); `prompt_service.group_by_room` / `build_section_containment_map`; `room_membership_service.resolve_authoritative_groups` (returns REVIEW_REQUIRED → empty merge_map); `generation_service._resolve_base_scene_room` / `_match_base_key` (selects the exact-label UNCERTAIN twin); `base_inventory_service.assess_section_base_inventory` (reports the honest MISMATCH).

## 3. Downstream impact of MISMATCH [VERIFIED]
Two consumers of `assess_section_base_inventory`:
- `generation_service.py:1075` — **advisory only** ("NEVER gates, reroutes, or alters the render").
- `generation_service.py:~1756` — the **pre-dispatch gate**: `if _inv_st == "MISMATCH"` → `base_contract_errors[label] = ("BASE_INVENTORY_MISMATCH", …)` → the section is **blocked before any provider call**; unaffected sections render normally; the deterministic design remains the trusted result. Confirmed by `storage/debug_artifacts/refused-prov-test/.../provider_response_metadata.json` (`status: failed`, `BASE_INVENTORY_MISMATCH`) and `test_inventory_gate_generate.py`.

## 4. Assignment trace (the two counters) [VERIFIED]
| Item | canonical centre | nearest_wall_id | proven-room owners of that wall | final room | status | rendered? |
|---|---|---|---|---|---|---|
| kitchen-base #1 | (1605, 389) | wall_162 | **0** | "Kitchen" (fallback) | UNCERTAIN | **yes** (in the "Kitchen" twin capture) |
| kitchen-base #2 | (1396, 244) | wall_036 | **0** | "Kitchen" (fallback) | UNCERTAIN | **yes** |

`kitchen-base rendered in rooms: ['Kitchen']` → **the counters are present in the deterministic scene and captured.** This is **not** a Case 3 rendering defect. Their transforms are canonical-faithful (`validate_scene_2d_to_3d` = SCENE_FAITHFUL, 0 mismatches [VERIFIED earlier]).

## 5. Case classification [VERIFIED]
- **Not Case 1** (inventory-selection only): no room holds the full Kitchen inventory, so re-selecting a base room cannot MATCH.
- **Not Case 2** (capture-selection only): selecting the combined room drops the counters; selecting the twin drops the chimney. No existing **authoritative** relationship links the UNCERTAIN twin to the combined room — `merge_map` is empty and label-matching is explicitly disallowed.
- **Not Case 3** (rendering): the counters render.
- **Case 4 (legitimately unresolved ownership) + owner merge/split decision.** The counters cannot be proven into the combined room (outside the floor polygon; nearest walls owned by zero rooms; vector topology closes them as separate counter cells [AGENT-REPORTED, consistent]). The system **honestly** keeps them UNCERTAIN and refuses the AI render rather than show a base that lacks expected furniture.

## 6. Why no code change (stop conditions) [VERIFIED]
Every candidate "fix" hits a prohibition:
- Assign the counters to the combined room → **invents room ownership** (no containment, no single-owner wall, no topological cycle). ✗
- Merge the base **inventory** across the combined room + twin so the gate passes → the **base IMAGE** still lacks furniture (counters are a separate capture); this makes the gate assert a match that the shown base does not support → **weakens the contract**. ✗
- Proximity/distance threshold or label merge → explicitly forbidden ("do not infer ownership from proximity"; "do not force a counter into Kitchen & Dining because its label suggests it"). ✗
Both failing routes are named stop conditions ("would require inventing room ownership"; "the only way to pass validation is to weaken the contract").

## 7. Tests / validation [VERIFIED]
No code changed, so the contract is unchanged; I ran the governing suites to document the green baseline:
```
python -m pytest tests/test_inventory_mismatch_status.py tests/test_inventory_gate_generate.py \
                 tests/test_containment_sectioning.py -q
=> 34 passed, 43 warnings in 15.10s   (exit 0)
```
These lock: MATCH/MISMATCH/NOT_ASSESSABLE semantics; MISMATCH blocks before the provider; NOT_ASSESSABLE/MATCH never block; containment-map section mapping. No test was weakened or modified.

## 8. Invariant assessment [VERIFIED]
Nothing was edited → canonical furniture identity/uids/transforms, walls, doors, windows, room boundaries, and the versioned snapshot are untouched. `validate_scene_2d_to_3d` remains SCENE_FAITHFUL. The deterministic render remains the trusted, complete fallback (it includes the counters).

## 9. Remaining risks / unknowns
- **Owner product decision pending:** whether the open-plan Kitchen+Dining should be one merged section whose base capture composites the combined room + adjacent counter cells (so a single AI base shows every item), or whether the AI Kitchen render stays deferred with the deterministic design as the result. Enabling the merge also needs the **base-capture compositing** for the merged area — otherwise the base image still lacks the counters [INFERRED].
- No AI renders were generated or visually compared this cycle (no paid calls); visual fidelity of an AI Kitchen output is **UNKNOWN** and out of scope.

## 10. Next concrete action
Make the **membership/merge owner decision** for the open-plan Kitchen & Dining (resolve `room_membership_service` REVIEW_REQUIRED → a real `merge_map`, and confirm `MERGE_SUPPORTED`). If "merge" is chosen, the smallest safe implementation is a **base-capture that composites the merged open-plan area** (combined room + its co-located UNCERTAIN counter cells) into one Kitchen base image, then the gate MATCHes naturally — **without** moving furniture, inventing ownership, or weakening `assess_section_base_inventory`; ship with a v79 regression test (Kitchen MATCH after merge; other rooms unchanged) and the existing 34 tests still green. Until that decision, current behavior is correct and is preserved.
