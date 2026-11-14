# Phase 4C — Step 2N: Explicit Room-Assignment Implementation-Readiness Audit (READ-ONLY)

**Mode:** READ-ONLY audit. No source/test/schema/migration/config/data/app-state change. No generation, paid API, hosted inference, DB writes, or persisted-design mutation. Creating this report is the only file change.

**Primary case:** design version `85759b78-210e-4daf-a2d1-9e8ea906fee5` (FID `f6b65d2b-4f96-4931-9f08-67dbd09776f6`, v79); chimney `chimney-1787478686293`; two `kitchen-base` units `kitchen-base-1787478607029`, `kitchen-base-1787478608231`; intended target the CONFIRMED kitchen room (RR1).

---

## 1. Executive verdict: **UNVERIFIED**

B (cache/persistence) and C (API/schema/back-compat) are **PASS**; D (precedence) is **deterministic and sound as a design**; E has a concrete plan. The blocker is **A (capture correctness)**: the deterministic base render's **floor is clipped to the room boundary polygon**, so an explicitly-assigned item whose centroid is outside RR1's polygon would render **with no floor beneath it**. Clipping/transform/duplication aspects of A pass by code, but **visual correctness cannot be confirmed without a rendered image**, and no existing artifact exercises this case. Per the decision criteria, A must be established before READY — it is not a confirmed defect (NOT READY) but genuinely unverified. **Do not proceed to implementation until A is resolved** (a bounded floor-extent decision + a capture test).

---

## 2. Evidence classification

- **VERIFIED (code/tests this session):** root-cause trace (2K); `room_membership` scope/semantics; cache-hash and fingerprint composition; persistence round-trip; camera fit-distance expansion to furniture; floor = boundary polygon; exactly-once assignment; 41 pure unit tests pass.
- **AGENT-REPORTED → re-VERIFIED:** all five 2M/2K lead findings confirmed against the live code.
- **INFERRED (reasoned, not executed):** the proposed precedence matrix behavior; that the floor-coverage gap produces a visible "floating item" artifact.
- **UNVERIFIED (no evidence obtainable read-only):** the actual rendered appearance of an out-of-polygon assigned item; cross-display WebGL variance; corpus-wide effects.

---

## 3. Checkout & Git status

- **The audited app is NOT under version control.** `git rev-parse` fails in `backend/`, the project root, and the parent. The only `.git` under the tree is **`floorplan-parser/.git`** — a *separate* repo (branch `main`, clean working tree, HEAD `1aa7462`) containing only a `floorplan/` parser, **not** `backend/` or `frontend/`. So there is no branch/diff/working-tree state for the audited code; "pre-existing changes" cannot be enumerated via git. (The session's `git:true` environment flag refers to the other session root `D:\sample_python_project\TeleCRM_Private_Repo-main`, not this checkout.)
- **Active checkout path:** `D:\Latest_mynest_design_version\mynest-design-studio` (backend at `…\backend`, frontend at `…\frontend`). Confirmed same checkout + version: `capture_generation_snapshot(FID)` returns `design_version_id == 85759b78…` (v79).
- No reset/clean/stash/checkout performed. After the audit, the only change is this report file (§13).

---

## 4. Context & artifacts reviewed

- Docs: `README.md`, `docs/CORE_PIPELINE_DOCUMENTATION.md`, `PROJECT_CONTEXT.md`, `PHASE_4C_STEP_2K_KITCHEN_RECONSTRUCTION_AMBIGUITY.md`, `PHASE_4C_STEP_2M_EXPLICIT_ROOM_ASSIGNMENT_CONTRACT.md`, `PHASE_4C_STEP_2H/2I/2J`.
- Backend symbols: `schemas/floor_plan.LayoutItem.room_membership` (`:27-47`); `room_membership_service` (scope `_DINING_IDS`, `resolve_dining_memberships` `:205-209`, `resolve_authoritative_groups` `:259-288`, `blocked_dining_sections` `:291-323`); `architectural_service.reconstruct_rooms` assignment loop (`:306-321`), UNCERTAIN fallback (`:387-421`); `scene_service.build_scene` (`:255-374`), `_drop_merged_dining_twins`; `generation_service._geometry_payload` (`:372-382`), `_compute_room_hash` (`:408-432`), `room_eligibility` (`:220+`); `floor_plan_service.save_layout` (`:248-287`), `_furniture_fingerprint` (`:217-221`), `get_layout`/`get_canonical` (`:224-245`); `base_inventory_service.assess_section_base_inventory` (`:51-146`); `prompt_service` catalogs (`_DINING_SEEDS` `:202`, `_KITCHEN_IDS` `:205`, `_SOFAS` `:201`).
- Frontend symbols: `BaseRenderBatch.tsx` (capture loop, keying, `furniture.length>0` gate); `RoomScene3D.tsx` (`fitDist` `:364-388`, `floorShape` `:343-359`, boundary walls, furniture mapping); `lib/aiCamera.ts` (`solveAiCamera`, `solveEyeLevelCamera`); `components/design-studio/DiningMembershipControl.tsx`; `lib/roomMembership.ts` (`DINING_ITEM_IDS`).

---

## 5. A — Capture correctness & clipping → **UNVERIFIED**

**How the room's furniture set is selected (VERIFIED).** `BaseRenderBatch` renders one `SceneRoom` at a time via `RoomScene3D room={room}`, drawing **that room's `furniture` list** + `scene.walls`; it stores a capture only if `room.furniture.length > 0`, keyed by both `room.id` and `room.label` (`BaseRenderBatch.tsx:162-164`). So inclusion is driven entirely by which scene room's `furniture` the item lands in — exactly what an explicit assignment would change.

**Camera framing is furniture-aware, not polygon-only (VERIFIED → clipping PASS).** The dollhouse base camera (the path used here: `preset="perspective"`, `ceiling={false}`, `aiRenderMode={true}`) computes `fitDist` by **expanding to each furniture item's farthest reach from the room centre, rotation-safe** (`RoomScene3D.tsx:364-388`: `halfX=max(halfX, |f.cx-cx|·mpp + max(f.w,f.h)·mpp/2)`, `return max(fit, camDist)`), and `solveAiCamera` derives the look-at **target from the furniture centroid** and penalizes candidates that clip furniture (`aiCamera.ts:90-123`). ⇒ an out-of-polygon assigned item **extends the fit distance and is framed, not clipped**.

**Canonical transforms/identity/material preserved (VERIFIED).** Furniture meshes are placed from `f.cx/f.cy/f.w/f.h/rotation` and typed by `item_id` (`RoomScene3D.tsx:310-319, 392-420`). An assignment only changes **which room's `furniture` bucket** the item is in; it never edits a transform. `aiCamera.ts:10-13` states the solvers "NEVER mutate any furniture, wall, opening, or canonical transform."

**Duplicate render / omission from another room (VERIFIED PASS, contingent on exactly-once).** `reconstruct_rooms` assigns each item to **exactly one** bucket (containment → `proven_entries`; wall-owned → `proven_wallowned`; else → `leftover`, `:306-321`), and an empty leftover group is **not** emitted (`:387-389 if not items: continue`). So moving the base units into RR1 removes them from the UNCERTAIN twin (which then disappears if empty) ⇒ no duplicate, no double-count. The implementation must keep this exactly-once property.

**The blocker — floor coverage (VERIFIED code, UNVERIFIED visual).** The floor is a polygon built from `room.boundary` and is explicitly documented to **"never extend outside the authoritative boundary"** (`RoomScene3D.tsx:343-359`). RR1's boundary is the proven raster polygon, which by construction **does not contain** the base-unit centroids (2K root cause). So the assigned item would render **hovering beyond the floor's edge over empty space**. Contrast: in today's UNCERTAIN fallback the room boundary is a **furniture hull** padded around the items (`architectural_service.py:390-413`), so the floor *does* cover them — i.e. the assignment would trade "floor covers item" for "floor does not," a code-verified visual regression of unknown severity.

**Why UNVERIFIED (not PASS/FAIL):** clipping, transforms, and duplication pass by code, but the floor-coverage artifact's visual acceptability cannot be judged without a rendered image, and **no existing base-render artifact exercises the out-of-polygon-in-CONFIRMED-room case** (today's Kitchen bases render the base units inside their hull twin). Obtaining the evidence requires rendering the feature, which does not yet exist. I did not trigger any render.

**Bounded resolution options (for a later step, not implemented):** (i) extend the floor extent to the union of the boundary polygon and assigned-item footprints (floor-only, no geometry/transform change); or (ii) accept the artifact if product judges it tolerable; either way gated by a headless/offscreen capture test that produces direct visual evidence.

---

## 6. B — Cache invalidation & persistence → **PASS**

- **Membership is persisted into canonical furniture (VERIFIED).** `save_layout` keeps a **set** `room_membership` in the canonical dict (drops only `None`), and `_furniture_fingerprint` hashes the **entire furniture list** (`json.dumps(furniture, sort_keys=True)`, `:217-221`). ⇒ setting/changing a membership **creates a new immutable `DesignVersion`** (new version id). Untagged/legacy layouts serialize byte-identically (None dropped) ⇒ no spurious versions, fingerprints unchanged.
- **Render cache is busted by a membership change (VERIFIED).** `_compute_room_hash` includes `_geometry_payload(canonical)`, whose `"furniture"` is the **whole furniture list** (`:372-382`) — including `room_membership` when set. ⇒ a membership change changes the hash ⇒ a previously-cached incomplete Kitchen render is **not** served after assignment. This **closes the Step 2I caveat** (that caveat concerned a base-resolution change that did *not* alter canonical; a membership change *does* alter canonical).
- **No cross-room contamination (VERIFIED).** Cache keys include `room_label`, so rooms have distinct keys; the shared whole-plan `geometry` term means a membership change invalidates *all* rooms of that plan (over-invalidation = safe, mildly wasteful), never a stale cross-room serve.
- **Source identity sufficiency (VERIFIED).** The per-render record also carries `design_version_id` (`generation_service.py:729`), and each version is immutable append-only ⇒ an in-flight generation keeps its snapshot; history is unaffected.
- **Transactionality:** `save_layout` runs in a single `session_scope()` (`:258`); a changed layout adds exactly one new version. (Generation-time disk cache writes are separate, best-effort, keyed by content hash — a partial failure yields a cache miss, not a stale hit.)

---

## 7. C — API / schema / backward compatibility → **PASS (no migration needed)**

- **The dining-only restriction is in the resolver/editor, not the field.** `LayoutItem.room_membership: str | None` accepts any value for **any** item (`schemas/floor_plan.py:47`); the dining limitation lives only in `room_membership_service` (filters `_DINING_IDS`, `:205-209`) and the editor (`DiningMembershipControl` renders only for `isDiningItem`; `roomMembership.ts DINING_ITEM_IDS`). ⇒ a non-dining value can be **persisted and round-tripped with no schema migration**.
- **Round-trip (VERIFIED).** `get_layout` → `LayoutItem(**item)` and `get_canonical` → `dict(canonical_json)` return `room_membership` verbatim for any item (`:224-245`). Legacy items (no field) default to `None`.
- **No current consumer breaks (VERIFIED).** The only backend consumers (`resolve_authoritative_groups`, `blocked_dining_sections`, `room_eligibility`) are dining-scoped or generic-per-room; a non-dining `room_membership` is **silently ignored today** (no error, no effect). ⇒ setting it is inert until the resolver is extended — backward-compatible, but also means Option B requires extending the resolver + editor to *act* on it (implementation, not a schema change).
- **Malformed/stale handling (VERIFIED):** unknown value → `REVIEW_REQUIRED: INVALID_MEMBERSHIP`; the tag names a **category** (KITCHEN), not a room id, so it cannot dangle on re-reconstruction.
- **Referencing a room that does not contain the centroid:** permitted by the field, but the *current* contract would never resolve it (it requires CONFIRMED containment/shared region) — this is the new authoritative semantic Option B introduces (§8, case 4), and is the core product decision from 2M.

---

## 8. D — Assignment precedence / conflict matrix (8 cases)

Existing order in `reconstruct_rooms` (`:306-321`): **CONFIRMED containment → unambiguous wall-ownership → UNCERTAIN leftover**. Dining membership adds the `room_membership_service` semantics. Proposed Option-B policy evaluated (not implemented):

| # | Case | Existing behavior | Safe expected behavior (proposed) |
|---|---|---|---|
| 1 | Contained in exactly one CONFIRMED room, no tag | Assigned to that room | Unchanged — containment authoritative |
| 2 | Contained in one CONFIRMED room, tag names that same room | Containment assigns; tag ignored (non-dining) | RESOLVED to that room (tag agrees; no-op) |
| 3 | Contained in one CONFIRMED room, tag names a **different** room | Containment wins; tag ignored | **REVIEW_REQUIRED: CONFLICT** — never override firm geometry (mirrors dining "separating wall" conflict, `room_membership_service.py:179-186`) |
| 4 | **Not** in any CONFIRMED room, tag → exactly one valid CONFIRMED room | → UNCERTAIN leftover (the kitchen-base case today) | **RESOLVED** → item added to that CONFIRMED room's furniture (the Option-B rescue) |
| 5 | Outside all CONFIRMED rooms, no tag | → UNCERTAIN leftover → inventory MISMATCH → blocked | Unchanged — honest block (status quo) |
| 6 | Tag target missing / uncertain / unconfirmed / ambiguous | n/a (non-dining ignored) | **REVIEW_REQUIRED** (`INSUFFICIENT_EVIDENCE` if 0 confirmed targets; `AMBIGUOUS_DESTINATION` if ≥2) — never force |
| 7 | Multiple/conflicting membership records for one item | n/a | Single field per item ⇒ no multiplicity; an invalid value → REVIEW_REQUIRED |
| 8 | Tag becomes stale after geometry/room-id change | Category tag (not room id) re-resolved each build | Re-resolved against current CONFIRMED rooms; frozen snapshots immutable; no dangling id |

The proposed policy (containment authoritative; explicit tag rescues only unplaced items to a unique CONFIRMED target; conflicts/ambiguity/stale → REVIEW_REQUIRED; no nearest-room, no geometry movement) is **consistent with existing contracts** — it mirrors the dining service's "validate, never force" philosophy and the documented `reconstruct_rooms` "NO nearest-room reassignment" invariant (`:291-297`). **No conflict found.** The one genuinely new semantic is case 4 (authoritative placement of an out-of-CONFIRMED-room item) — the approved-pending product decision.

---

## 9. E — Minimum regression plan (existing vs proposed)

**Existing tests confirmed green this session (executed, §12):** `test_room_membership.py`, `test_authoritative_merge.py`, `test_dynamic_rooms.py`, `test_room_assignment.py`, `test_kitchen_scene_inventory.py` → **41 passed**. These lock current dining membership, grouping, room assignment, and kitchen scene-inventory behavior.

**Proposed new tests (offline, detector-free, no paid calls) — not written:**
1. Non-dining explicit KITCHEN on both base units (v79) → both in RR1's furniture; RR1 = {chimney, base-A, base-B}; `assess_section_base_inventory("Kitchen") == MATCH`; gate **permits**.
2. Untagged unchanged → base units UNCERTAIN; MISMATCH; gate **blocks** (back-compat lock).
3. Precedence case 3 (CONFLICT), case 6 (INSUFFICIENT_EVIDENCE / AMBIGUOUS_DESTINATION).
4. Exactly-once: tagged item appears in RR1 and **not** in any leftover; empty twin not emitted (no duplicate/double-count).
5. Canonical invariance: `cx/cy/w/h/rotation`, uids, counts, and all walls/openings/boundaries byte-identical before/after tagging.
6. Cache/persistence: setting a membership spawns a new `DesignVersion` and changes `_compute_room_hash`; clearing it restores the legacy fingerprint.
7. API/back-compat: a non-dining `room_membership` round-trips via `get_layout`/`get_canonical`; legacy payloads unchanged.
8. AIR-03 composition: dining→KITCHEN tag + base-unit→KITCHEN tag coexist; one decision per item.
9. **Capture (the blocker): a headless/offscreen render asserting the assigned out-of-polygon item is (a) within frame and (b) over floor** — this is the evidence area A lacks.

**Runnable now without AI/paid calls:** 1–8 (pure/offline). **Needs a render harness:** 9 (WebGL/offscreen; no provider, but a rendering context). I deliberately did **not** run any `generate()`-based test (e.g. `test_inventory_gate_generate`, `test_air03_gate_generate`) because `generate()` may write generation rows/cache to the live DB — out of bounds for this read-only audit.

---

## 10. Minimal implementation outline (evidence-supported; NOT implemented)

Only if Option B is approved and area A is resolved:
1. **Resolver:** extend `room_membership_service` with a non-dining path resolving `KITCHEN`/`LIVING_AREA` to the unique CONFIRMED room carrying that anchor (case 4/6 semantics); keep dining path untouched.
2. **Assignment:** in `reconstruct_rooms`, before the UNCERTAIN-leftover fallback, place an explicitly-tagged, not-contained item into the resolved CONFIRMED room's furniture (preserve exactly-once; CONFIRMED containment still wins → case 3 conflict).
3. **Floor (area-A fix):** extend `RoomScene3D` `floorShape` extent to cover assigned out-of-polygon items (floor-only; no geometry/transform/threshold change), verified by test §9.9.
4. **Editor:** show the assignment control for assignable non-dining items; surface REVIEW_REQUIRED reasons (reuse existing eligibility plumbing).
5. No schema migration (§7); no threshold/provider/gate change; inventory gate and deterministic fallback stay intact.

---

## 11. Risks, unresolved questions, stop conditions

- **Primary risk (A):** floating-item-over-void floor artifact for out-of-polygon assignments; unquantified without a render. **Blocks READY.**
- **Secondary (A):** camera correctness relies on the dollhouse path (`enclosed=false`, as `BaseRenderBatch` uses); the eye-level path (`solveEyeLevelCamera`) fits to **interior** extents (`interiorHalfX=bw·mpp/2`, `RoomScene3D.tsx:426`) and could clip an out-of-polygon item — not the active base path, but a constraint to preserve.
- **Unknowns:** rendered appearance (A); cross-display WebGL variance; corpus behavior if "assignable" = all furniture vs an allow-list.
- **Stop conditions honored:** canonical intent for case 4 is a product decision (unresolved); area-A evidence unobtainable read-only. ⇒ audit stops at UNVERIFIED; no implementation.

---

## 12. Commands run & exact results

- `git rev-parse --show-toplevel` in `backend/`, project root, parent → `fatal: not a git repository` (×3). `find … -name .git` → only `floorplan-parser/.git`. `git -C floorplan-parser status` → branch `main`, clean; HEAD `1aa7462`.
- Read-only trace (reused from 2K, re-run): `capture_generation_snapshot(FID)` → `design_version_id=85759b78… v79` (target confirmed). No writes.
- Tests (pure/offline, no DB writes, no paid calls):
  `PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q tests/test_room_membership.py tests/test_authoritative_merge.py tests/test_dynamic_rooms.py tests/test_room_assignment.py tests/test_kitchen_scene_inventory.py`
  → **`41 passed, 5 warnings in 9.78s`**.
- No `generate()`/`save_layout`/DB-write/paid-call commands were run.

---

## 13. Git status after audit & changed files

- The audited app is not a git repo (§3), so no git status applies to it. The nested `floorplan-parser` repo is **unchanged** (clean).
- **Files changed by this audit: exactly one** — this report, `PHASE_4C_STEP_2N_IMPLEMENTATION_READINESS_AUDIT.md` (new, at the project root beside the 2M report). No code/test/schema/data/config files were modified. Scratchpad trace scripts are outside the project tree.
