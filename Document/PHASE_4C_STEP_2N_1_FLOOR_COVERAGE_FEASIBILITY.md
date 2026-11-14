# Phase 4C — Step 2N.1: Kitchen Floor-Coverage & Capture Feasibility (READ-ONLY)

**Mode:** READ-ONLY feasibility investigation. No app code/test/schema/migration/config/data change; no commit/branch/PR; no AI/paid calls; no threshold/heuristic/geometry change; `BASE_INVENTORY_MISMATCH` untouched; no persistent-cache writes. Creating this report is the only file change.

**Target:** design version `85759b78-210e-4daf-a2d1-9e8ea906fee5` (FID `f6b65d2b-4f96-4931-9f08-67dbd09776f6`, v79) — re-confirmed in the active checkout. Objects: chimney `chimney-1787478686293`; `kitchen-base-1787478607029`, `kitchen-base-1787478608231`; proposed target CONFIRMED `Kitchen & Dining Area` (RR1).

---

## 9. FINAL VERDICT: **READY FOR PRODUCT DECISION**

The floor-coverage uncertainty from Step 2N is **resolved and quantified**. Assigning the base units to RR1 **as-is** produces a confirmed defect (each unit is **100% outside** RR1's rendered floor → floating furniture over void). A **rendering-only, minimal per-item floor patch** (Option B-minimal) can cover them **without changing canonical geometry or furniture transforms** and is **adjacency-safe** (the footprints overlap no other room), whereas a naive bounding/convex-hull extension is **not** safe (it clips `Living Area` by 3.7%). The remaining item is a **product choice (A vs B-minimal)** plus **one bounded human visual-review** of the B-minimal seam/island appearance — not an open technical unknown. A safe pixel capture of the Option-B case **could not be run** within this audit's no-write restrictions (documented, §4) and is the single gate before implementing B-minimal. **This verdict is not authorization to implement.**

---

## 1. Verified rendering-path findings (file / symbol / lines)

**Coordinate frames — floor and furniture share ONE frame (VERIFIED, not assumed).** In `frontend/src/components/design-studio/RoomScene3D.tsx`:
- Room centre: `cx = bx + bw/2`, `cy = by + bh/2` from `room.bbox` (`:238-243`) — the **proven-polygon bbox**, not recomputed from furniture.
- **Floor** (`floorShape`, `:347-359`): each `room.boundary` vertex → `mx=(px-cx)·mpp`, `mz=(py-cy)·mpp`; built as a `THREE.Shape`, rendered as `shapeGeometry` rotated flat (`:544-547`). Comment: "never extends outside the authoritative boundary."
- **Furniture** (`:712-732`): each item → `position=[(f.cx-cx)·mpp, 0, (f.cy-cy)·mpp]`, `rotation=[0,-f.rotation·DEG,0]`, size `f.w·mpp × f.h·mpp`, at **y=0**. Identical room-centre/metre frame, same `mpp`, same `cx,cy`.
⇒ The floor-coverage gap is a **real same-frame geometric fact**, not a transform mismatch.

**Camera / clipping (VERIFIED — not the problem).** `fitDist` (`:364-388`) expands to each furniture item's farthest reach (`halfX=max(halfX,|f.cx-cx|·mpp + max(f.w,f.h)·mpp/2)`, `return max(fit,camDist)`); `solveAiCamera` (`lib/aiCamera.ts:76-144`) targets the furniture centroid and penalizes clipping. ⇒ an out-of-polygon item is **framed, not clipped**.

**Walls / occlusion (VERIFIED).** The base capture runs `aiRenderMode={true}` with walls hidden (`BaseRenderBatch.tsx:240-251`; RoomScene3D hides the wall meshes), so no wall occludes the item; floor is `receiveShadow` only. No depth/occlusion defect — the item simply has **no floor under it**.

**Scene furniture selection + exactly-once (VERIFIED).** `BaseRenderBatch` renders each `SceneRoom`'s own `furniture` (`:244`, keyed by id+label, captured only if `furniture.length>0`). `architectural_service.reconstruct_rooms` assigns each item to exactly one bucket (`:306-321`) and drops an empty leftover (`:387-389`) ⇒ moving the units into RR1 removes them from the UNCERTAIN twin (no duplicate, no double-count).

**Quantified floor coverage (VERIFIED, offline, §7).** Against RR1's actual boundary polygon (`Kitchen & Dining Area`, 6 pts, area 188,870):

| item | footprint area | inside RR1 floor | **outside** |
|---|---|---|---|
| chimney (sanity) | 9,773 | 9,773 | **0.0%** |
| kitchen-base-A `…607029` | 20,200 | 0 | **100.0%** |
| kitchen-base-B `…608231` | 47,313 | 0 | **100.0%** |

⇒ **Both base units lie entirely outside RR1's rendered floor.** Classification: this is an **expected consequence of authoritative room boundaries** (floor deliberately clipped to the proven polygon) that, applied to an out-of-boundary assignment, becomes a **confirmed rendering artifact** (floating furniture). The *pixel appearance* remains the only part needing visual evidence.

**Contrast with today (VERIFIED).** The units currently live in an UNCERTAIN **furniture-hull** room whose boundary is padded *around* the items (`architectural_service.py:390-413`) — so today their floor covers them. Moving them to RR1's proven polygon is precisely what removes the floor beneath them.

---

## 2. Evidence classification

- **VERIFIED (code + offline computation this session):** shared coordinate frame; floor = boundary polygon at y=0; furniture at y=0 same frame; camera expands to furniture; walls hidden in capture; exactly-once assignment; **both units 100% outside RR1**; individual footprints overlap no other room; a convex-hull bridge overlaps `Living Area` by 9,849 (3.7%); 41 prior unit tests green (Step 2N).
- **PRIOR-AGENT-REPORTED → re-VERIFIED:** Step 2N's "fitDist accounts for furniture reach" and "floor constrained to room.boundary."
- **INFERRED:** that the as-is render shows a visibly floating item; that B-minimal yields a disconnected floor island with a seam (both follow directly from the 100%-outside + gap geometry, but are not pixel-confirmed).
- **UNVERIFIED (not obtainable read-only):** the rendered pixels of either the as-is artifact or the B-minimal patch; cross-GPU/display variance.

---

## 3. Alternatives A–D

| Criterion | **A: reject/review out-of-boundary assignment** | **B-minimal: per-item floor patch under each assigned unit** | **B-bridge: extend floor to furniture bounds / convex hull** | **C: existing mechanism covering furniture** | **D: other existing-architecture** |
|---|---|---|---|---|---|
| Preserves canonical room geometry & transforms | **Yes** | **Yes** (render-only; canonical boundary + transforms untouched) | Yes (render-only) but… | Yes | — |
| Presentation-only vs room semantics | n/a (no render) | **Presentation-only** | Presentation-only | mixed | — |
| Risks covering wall/door/window/other room | No | **No** — footprints overlap no other confirmed room (§7) | **YES** — convex hull overlaps `Living Area` 3.7% (§7) | n/a | — |
| Disconnected patches / seams / occlusion | none | **Yes** — patches are detached islands (units 100% outside, gap between) | bridges the gap (no island) but covers neighbour | n/a | — |
| Affects other rooms / existing designs | No | No (only rooms with an explicit out-of-boundary assignment) | **Yes** (neighbour overlap) | No | — |
| Backward-compatible & testable | Yes | Yes (offline geo tests + one visual review) | Testable but unsafe | — | — |
| Achieves complete Kitchen base render | **No** (stays blocked) | **Yes** | Yes-but-wrong | **No** (see below) | — |

- **A** is fully safe and is today's behavior (honest block); it simply does not render the units.
- **B-minimal** is the only option that completes the render *and* preserves canonical geometry *and* is adjacency-safe; its cost is a disconnected floor island / seam whose visual acceptability needs one review.
- **B-bridge is rejected** by evidence: it extends the floor into `Living Area`.
- **C (existing mechanism):** the only existing furniture-covering floor is the **UNCERTAIN furniture-hull room** (today) or the **rectangular bbox fallback floor** (`RoomScene3D.tsx:558-560`, used only when no architectural boundary). Neither covers out-of-polygon furniture *within RR1*; and the capture renders **one** scene room at a time (no composite multi-room base), so there is no existing mechanism that renders RR1's chimney and the hull-twin units in one base. **No clean Option C exists.**
- **D:** none found that applies to a room with an architectural boundary.

---

## 4. Was a safe deterministic capture possible?

**No — not within this audit's restrictions.** Capture infrastructure exists: `frontend/src/BaseRenderBatch.tsx` (offscreen 1216×832 WebGL capture) and `frontend/src/harness.tsx` (standalone offscreen renderer that fetches a scene from `sceneUrl` and POSTs PNGs to a local save server `127.0.0.1:8899/save`), driven by e2e specs (`e2e/live-furniture-audit.spec.ts`, `e2e/camera-invariants.spec.ts`). But capturing the **Option-B case** requires a scene in which the base units are in RR1 **with** a floor patch — which does not exist today and would require **either** implementing the assignment (prohibited) **or** crafting a scene fixture + running the harness/dev+save servers (file creation + state writes, prohibited here). Per the mandate ("if a safe capture cannot be performed without changing state, stop and document"), **no capture was run**; no PNG was produced or written. The offline geometric measurement (§7, 100% outside) stands in as objective evidence; the pixel appearance remains the one human-review item.

**Proposed capture setup (describe-only, for a later authorized step):** run `harness.tsx` against a crafted in-memory scene JSON where `RR1.furniture` includes both base units and a B-minimal floor patch (or a build with the feature behind a flag), render at 1216×832, save to a scratch path (not the render cache), and visually inspect (a) each unit present once, (b) floor under each unit, (c) no floor intrusion into `Living Area`, (d) seam/island appearance.

---

## 5. Objective acceptance criteria

**Automatically testable (offline, no AI/paid/writes):**
1. **Count/identity:** both base-unit uids appear **exactly once** in the captured room's furniture set; present in RR1, absent from any UNCERTAIN twin; twin not emitted if empty.
2. **Transforms:** each unit's `cx/cy/w/h/rotation` equals canonical byte-for-byte (assignment changes only the room bucket).
3. **Room geometry unchanged:** RR1's `boundary`, `bbox`, walls, openings identical before/after tagging.
4. **Adjacency safety:** the floor-patch polygon(s) have **0 area intersection** with any other CONFIRMED room's polygon and with wall/opening bands (this audit measured the raw footprints at 0 overlap; the patch must preserve that).
5. **No duplicate geometry / no cross-room omission:** the units render in RR1 only.
6. **Back-compat:** designs without explicit membership build an identical scene (fingerprint/geometry-hash unchanged).

**Requires human visual review (one capture):**
7. The floor **visibly covers each unit's footprint** in the rendered base.
8. **No visible floor intrusion** into `Living Area` or through a wall/doorway/window.
9. The **seam/disconnected-island** appearance between the patch and RR1's main floor is acceptable (or the patch is shaped to minimize it without bridging into neighbours).

---

## 6. Remaining product decisions & risks

- **Product decision (unchanged from 2M, now sharper):** choose **A** (keep honest block for out-of-boundary furniture) **or** **B-minimal** (presentation-only floor patch so an explicitly-assigned unit renders on floor within RR1). This is the smallest decision needed to proceed.
- **Risk R1 (seam/island):** B-minimal floor patches are disconnected from RR1's main floor (units 100% outside, with a gap); visual acceptability needs the §4 capture.
- **Risk R2 (adjacency):** any extension beyond the exact footprints risks the `Living Area` overlap (3.7% measured for convex hull) — the patch must be bounded to the footprints (+ small margin verified against neighbours), never a bounding/convex extension.
- **Risk R3 (semantics):** see §(semantics) below — the override must be presentation-only, not a canonical room-geometry change.
- **Non-risk (resolved):** camera clipping, transform preservation, duplicate render, cache invalidation, API/back-compat (Steps 2N §A/B/C).

---

## Assignment semantics (no product decision made here)

Assigning the base units to RR1 is **not** one thing until the product chooses its meaning:
- **Presentation-only inclusion override** — the item is *rendered and inventory-counted* within RR1 (furniture bucket + a render-only floor patch), while canonical room geometry and the item's transform are untouched. **This is the minimal, lowest-risk meaning and the only one B-minimal needs.**
- **Authoritative room-membership override** — a durable "this item belongs to KITCHEN" fact that all consumers honor (the 2M contract). Implies the presentation-only effect plus persisted intent.
- **Canonical room-semantics change** — altering RR1's boundary/geometry to include the units. **Out of scope and prohibited** (changes authoritative geometry).

**Smallest product decision to proceed safely:** approve a **presentation-only inclusion override** for explicitly-assigned, out-of-boundary assignable furniture, rendered via a **minimal per-item floor patch**, gated by the §4 visual review — leaving canonical geometry and transforms unchanged, and keeping `BASE_INVENTORY_MISMATCH` as the default for everything untagged.

---

## 7. Exact commands & results

- `git rev-parse --show-toplevel` (backend/root/parent) → `fatal: not a git repository` ×3; only `floorplan-parser/.git` exists (separate repo, branch `main`, clean) — the audited app is **not** version-controlled.
- `capture_generation_snapshot(FID)` → `design_version_id=85759b78… v79` (target confirmed), read-only.
- Floor-coverage quantification (read-only, no writes), scratchpad `trace_floor_coverage.py`:
  - RR1 = `Kitchen & Dining Area`, CONFIRMED, boundary 6 pts, area 188,870.
  - chimney **0.0% outside**; kitchen-base-A **100.0% outside** (fp 20,200); kitchen-base-B **100.0% outside** (fp 47,313).
  - per-footprint overlap with other CONFIRMED rooms: **none**.
  - `union(RR1+bases)` 256,382; `convex_hull` 336,520; **convex-hull overlaps `Living Area` by 9,849 (3.7%)**.
- No `generate()`, `save_layout`, DB-write, harness/dev-server, or paid-call command was run.

---

## 8. Before/after Git status & changed files

- The audited app has **no git repo** (§7), so no before/after git diff applies to it; the nested `floorplan-parser` repo is **unchanged** (clean).
- **Files changed by this audit: exactly one** — this report, `PHASE_4C_STEP_2N_1_FLOOR_COVERAGE_FEASIBILITY.md` (new, project root beside 2M/2N). No code/test/schema/data/config/cache modified. Read-only trace scripts live in the session scratchpad, outside the project tree.
