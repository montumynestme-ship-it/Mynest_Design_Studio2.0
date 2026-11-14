# Phase 4C — Step 2N.2: Floor-Coverage Patch — STOP BEFORE EDITING (evidence-based)

**Outcome:** **STOPPED before any edit.** Current evidence no longer supports a safe, minimal, *targeted* floor-coverage patch, because the defect it would fix **does not exist in the current pipeline** and the only way to trigger it (an explicit room assignment) is unbuilt/unauthorized. No rendering code was changed. This report is the only new file.

**Target re-verified:** design version `85759b78-210e-4daf-a2d1-9e8ea906fee5` (FID `f6b65d2b…`, v79), active checkout (not a git repo; only `floorplan-parser/.git` exists).

---

## 1. Facts re-confirmed against current code (VERIFIED, read-only)

- Floor is a `THREE.Shape` from `room.boundary` ("never extends outside the authoritative boundary", `RoomScene3D.tsx:347-359`); furniture is placed at `position=[(f.cx-cx)·mpp, 0, (f.cy-cy)·mpp]` in the **same** room-centre metre frame (`:717-732`). (Same coordinate frame — 2N.1 confirmed.)
- Base units vs RR1 (`Kitchen & Dining Area`, area 188,870): chimney **0% outside**; `kitchen-base-…607029` and `…608231` each **100% outside** RR1's floor polygon.
- A naive convex-hull floor bridge **overlaps `Living Area` by 9,849 (3.7%)**; the exact per-item footprints overlap **no** other confirmed room. (All 2N.1 figures reproduce exactly.)

## 2. The decisive NEW finding (VERIFIED, read-only) — no current defect to patch

Scanning **every** CONFIRMED room's assigned furniture for footprint-vs-floor coverage (v79):

| room (CONFIRMED) | items outside their floor polygon | how far outside | assign method |
|---|---|---|---|
| Living Area | console | 13.0% | raster_contour |
| Bedroom 1 | bed 6.1%, side-table 20.7%, side-table 17.5%, wardrobe 7.9%, dressing-table 4.6% | **≤20.7%** | raster_contour |
| Bedroom 2 | bed 8.2%, side-table 24.6%, side-table 19.8%, wardrobe 1.1%, dressing-table 10.7% | **≤24.6%** | raster_contour |
| Bedroom 3 | wardrobe 18.4%, bed 5.1%, side-table 17.5%, side-table 14.7%, dressing-table 15.7% | **≤18.4%** | raster_contour |
| Kitchen & Dining Area | dining-table | 8.3% | raster_contour |

- **Every item assigned to a CONFIRMED room is only *partially* outside (max 24.6%).** This is **normal wall-adjacent furniture** — beds, side-tables, wardrobes, dressing-tables, consoles sit against walls, so their footprints overhang the *interior* floor contour by design. The current renderer handles these acceptably (walls hidden in `aiRenderMode`; overhang sits at the wall line). **These must NOT be patched.**
- The only ~100%-outside items are the two `kitchen-base` units — and in the **current** scene they are assigned to the **UNCERTAIN** `Kitchen` twin (`method=furniture_hull`), whose padded hull floor **covers** them (12% out of the hull, not floating). **They are not in RR1.**

⇒ **No furniture in the current pipeline is assigned to a CONFIRMED room while lying (near-)entirely outside its floor.** The "floating furniture" defect the patch targets **is not reproducible today.**

## 3. The precise contradiction

2N.1's floor-coverage risk assumed the base units would be **assigned to RR1** (via the explicit room-assignment feature, Step 2M / Workstream B) and then float. But:
- That explicit-assignment feature is **unbuilt and unauthorized** (Step 2N.1 verdict = *READY FOR PRODUCT DECISION*, not implemented). Until it exists, the base units stay in the UNCERTAIN hull twin (floor-covered), and **nothing** places a furniture item ~100% outside a CONFIRMED room's floor.
- Therefore a floor patch added now has **no safe trigger**:
  - Gating it on the explicit assignment → **inert dead code** (the trigger does not exist), with no current testable case.
  - Gating it on a geometric "% outside" threshold → **forbidden** ("avoid broad hulls, bounding rectangles"; no threshold tuning) **and** would wrongly patch the **many normal wall-adjacent items** above (extending floor under walls / toward adjacent rooms across all 6 rooms) — a broad, non-minimal change with real regression risk, exactly what the invariants prohibit.

A minimal *per-item footprint* patch is adjacency-safe (0% neighbour overlap) **only** when applied to a genuinely out-of-floor assigned item — i.e. the explicitly-assigned base units — which do not yet exist in the pipeline.

## 4. Required decision (before any floor-coverage patch)

Implement the floor-coverage patch **together with, and gated by, the explicit room-assignment feature** (Step 2M), so it fires **only** for furniture a user has explicitly assigned to a room it lies outside of — never for normal wall-adjacent overhang. Concretely, the product/engineering decision needed first is:

1. **Approve + implement the explicit room-assignment (presentation-only inclusion override)** from Steps 2M/2N.1. This both creates the base-units-in-RR1 case **and** provides the exact per-item signal (`room_membership` on a non-dining item) to scope the floor patch.
2. **Then** add the minimal per-item footprint floor patch in `RoomScene3D`, applied only to items flagged as explicit out-of-boundary assignments, verified by the 2N.1 capture (seam/adjacency review).

Doing (2) before (1) is unsafe or inert, as shown in §3.

## 5. Scope / invariants honored
- **No files edited** (no scene builder, floor generation, canonical, membership, versioning, API, schema, provider, or test change). This report is the only new file.
- Canonical inventory/transforms, walls/doors/windows/boundaries, and the inventory/membership gates are untouched.
- No render captured (no need — the defect is not reproducible in the current pipeline; and a `generate()`/capture run would require the shared DB / unbuilt feature). Visual validation: **UNVERIFIED** — there is nothing new to render.

## 6. Evidence labels
- **VERIFIED (this step):** same coordinate frame; base units 100% outside RR1; convex hull 3.7% Living overlap; per-item footprints 0% neighbour overlap; **all CONFIRMED-room assigned furniture is only ≤24.6% outside (normal overhang); base units currently in the UNCERTAIN hull twin, not RR1.**
- **AGENT-REPORTED → re-VERIFIED:** 2N.1 coverage/adjacency figures.
- **INFERRED:** that a threshold-based patch would visibly regress normal wall-adjacent furniture (follows from patching items at the wall line across all rooms; not pixel-tested).
- **UNVERIFIED:** rendered appearance of any patch (nothing safe to render without the unbuilt feature).

## 7. Changed files / git / next action
- **Changed files:** this report only. App is not version-controlled (no `git diff`); `floorplan-parser` repo unchanged. Scratchpad trace scripts are outside the project tree.
- **Next concrete action:** take the Step 2N.1 product decision to approve the explicit room-assignment (presentation-only override); implement it; **then** add the gated minimal floor patch + the 2N.1 capture review. Reopen 2N.2 at that point.
