# Kitchen & Dining Topology Wall-Ownership — Result (no change made)

**Outcome:** The capability to associate enclosing walls with a room **already exists** in the data model (`supporting_wall_ids`, independent of the floor polygon — **no schema change needed**). **But the source topology does NOT prove** that `wall_036`/`wall_162` enclose the **Kitchen & Dining** room: the vector wall topology closes them as **separate counter cells** (the cabinet/counter footprints), each containing one `kitchen-base`, distinct from the main kitchen floor. There is **no topological cycle** enclosing floor + counters as one room. Per the explicit stop condition ("if source topology does not prove the association, make no geometry change"), **no geometry/code was changed.** The real resolution is an **owner decision** (room-grouping policy for cabinet cells), not a topology-proven wall fact. **No files changed. No TeleCRM. No paid calls. DB read-only.**

## Phase 1 — Evidence (independently verified)
- Repo: `mynest-design-studio/` (MyNest); **not a git repository** → no branch/commit/diff; tree unchanged. TeleCRM untouched.
- Canonical: v79 `85759b78`, floor `f6b65d2b`. **Source PDF** `storage/floor_plans/.../f6b65d2b/original.pdf` — **4179 bytes, sha256(16) `e440a2184e9196ad`** (matches the prior report).
- Validators reproduced: `validate_scene_2d_to_3d` → **SCENE_FAITHFUL, 0 mismatches**; `validate_scene_against_canonical` → Kitchen + Bedroom 3 not proven from walls.

## Phase 2 — Data-contract trace (answered)
- **Floor-surface polygon:** `room["boundary"]` (and `bbox`) — the raster floor contour.
- **Room↔wall ownership:** `room["supporting_wall_ids"]` — **this already represents wall association independent of the floor polygon** (K&D has 41 such walls that are not its boundary vertices). `wall_owner[wall_id] = {rooms listing it}`; furniture whose `nearest_wall_id` is owned by exactly one room is assigned there (`architectural_service.reconstruct_rooms`).
- **Openings:** `doors`/`windows` with `supporting_wall_id`.
- **Furniture assignment / uncertainty:** containment → single-owner wall-ownership → else UNCERTAIN leftover.

**Key question — can the model represent a verified enclosure independent of the floor polygon without a contract change?** **YES.** `supporting_wall_ids` is exactly that mechanism; adding `wall_036`/`wall_162` to K&D's list (if proven) needs **no schema/contract/geometry change**. The blocker is **not** the data model — it is whether topology *proves* the association.

## Phase 3 — Topology verdict: association NOT proven → no change
Ran `wall_reconstruction.reconstruct_rooms_topology` on the **179 structural wall segments** (the same walls the scene uses), checked which cycles contain the two `kitchen-base` centres (1605,389) and (1396,244):
```
vector-topology rooms: 3
 room 0  wall_supported=True  bbox x[1264-1502] y[203-310]  holds TOP kitchen-base (1396,244)
 room 1  wall_supported=True  bbox x[1528-1658] y[203-233]  holds none
 room 2  wall_supported=True  bbox x[1528-1658] y[233-511]  holds RIGHT kitchen-base (1605,389)
```
- The counters are inside **their own separate closed cycles** (small cells at the counter footprints), **not** a single kitchen enclosure.
- `wall_036` (y=214) is **112 px above** the K&D floor top (y=326); `wall_162` (x=1647) is **161 px right** of the K&D floor right (x=1486). They bound the **counter cells**, not the ~188,870 px² K&D floor room.
- **This contradicts the earlier "open to the kitchen" hypothesis** — the cells are closed and distinct. Associating `wall_036`/`wall_162` with Kitchen & Dining would therefore be an **unproven/forced** assignment, and would effectively treat **cabinet/counter footprints as the room's structural enclosure** — prohibited ("do not convert non-structural cabinetry into walls", "keep genuinely ambiguous room relationships uncertain").

**Conclusion:** source topology establishes the **opposite** of the required relationship. No safe, source-proven association exists → **no geometry change made** (Phase 3 gate fails; stop condition triggered).

Independent note on **Bedroom 3** (unchanged): its CONFIRMED room holds all furniture and renders; the only UNCERTAIN item is a window opening ~27 px outside the eroded interior (normal for a wall-mounted opening) — no defect, left unchanged.

## Phase 4 — Validation (read-only; no code changed)
```
validate_scene_2d_to_3d(v79)          -> passed=True, SCENE_FAITHFUL, 0 mismatches
validate_scene_against_canonical(v79) -> geometry_faithful=False (Kitchen, Bedroom 3 not proven) — unchanged
reconstruct_rooms_topology(179 walls) -> 3 separate counter-cell cycles (above)
```
No source changed → no tests added/modified; standing offline geometry suites (72 passed previously) unaffected. Canonical furniture/wall/door/window transforms unchanged (nothing was edited).

## Phase 5 — Files, risk, next action
- **Files changed:** **none.** Git diff: empty (not a repo).
- **Before/after:** no "after" — floor polygon x[1094–1486] y[326–875] unchanged; wall associations unchanged; counters remain in their own cells / UNCERTAIN, honestly.
- **Remaining uncertainty & the smallest decision needed:** whether the deterministic **room for rendering** should **absorb adjacent cabinet cells** (so perimeter counters render inside the kitchen). This is a **room-grouping / rendering policy owner decision**, not a wall-ownership fact the source proves. If the owner decides "yes, absorb adjacent same-kitchen cabinet cells," the smallest implementation would merge a small cabinet-footprint cell into the neighbouring CONFIRMED room **only** when it is (a) wall-adjacent to that room and (b) occupied solely by that room's catalogued fixtures (e.g. `kitchen-base`), with a regression test on this v79 fixture and a broad reconstruction run to prove no cross-plan regression — **without** moving furniture, inventing walls, or expanding the floor polygon. Until that decision, behavior is preserved.

**Honest note:** structured + topology evidence only; no AI renders generated or visually compared. Transforms are faithful; the open item is a room-grouping policy decision, and the source does not prove the wall association requested, so nothing was changed.
