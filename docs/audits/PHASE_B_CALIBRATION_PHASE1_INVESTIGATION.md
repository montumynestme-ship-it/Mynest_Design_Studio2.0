# Phase B — Backend Metric Calibration: Phase 1 Investigation (READ-ONLY)

**Date:** 2026-11-15 · **Branch:** `feature/phase-1-empty-architectural-plans` · **HEAD:** `f279932`
**Status:** Phase 1 complete — **STOP for implementation approval. No code changed.**
**Evidence:** `VERIFIED` (checked now) · `AGENT-REPORTED` (prior turn) · `INFERRED` · `UNKNOWN`

---

## 0. Baseline `VERIFIED`
Branch `feature/phase-1-empty-architectural-plans`, HEAD `f279932` (nothing committed since).
Working tree preserved: modified `scene.ts`, `Scene3DModal.tsx`; untracked `calibration.ts(+test)`,
`deterministicScene.test.ts`, two audit reports, six dev harnesses. No reset/clean/stash done.

## 1. Coordinate chain & exact units `VERIFIED`
```
 PDF points            ──(× page.scale = DEFAULT_WORLD_SCALE = 2.0)──►  WORLD px      [canonical scene frame]
 (72-DPI, y-down)                                                       (walls, rooms, openings, furniture)
 WORLD px              ──(× mpp  [metres per world px])──────────────►  Three.js metres   world_to_three()
 WORLD px              ──(× mpp × 1000)───────────────────────────────►  millimetres        world_to_mm()
 Three.js metres       ──(÷ 1000)  ◄── mm ──(× 1000)──────────────────  (mm ⇄ m)
```
- `page.scale` (= 2.0) is the **pdf→world-px** scale, NOT a physical scale. `VERIFIED` (`coordinates.DEFAULT_WORLD_SCALE`, `scene_service` page).
- `mpp` is **metres per WORLD px**. Backend `coordinates.DEFAULT_MPP = 0.01` (an **uncalibrated** assumption). `VERIFIED`.
- The 3D renderer and the 2D modal canvas both operate in **world px** (`Scene3DModal` passes `scene.walls` to both `RoomScene3D` and `RoomSection2D`). `VERIFIED` — so two points picked on the 2D plan are world-px.

## 2. `scale_mm_per_px` semantics (§2.1,2,7)
- **Units:** millimetres per pixel (`Numeric(12,4)`, `models.py:77`). `VERIFIED`.
- **Which pixel space:** **UNKNOWN in code** — the field is never written/read, so no code defines whether "px"
  means pdf-pt, page px or world px. **INFERRED** it must mean **mm per WORLD px** (the only frame the scene,
  3D renderer and 2D calibration canvas share). ⚠ This is a §10 ambiguity that MUST be fixed by definition
  before use — mis-defining it (e.g. as pdf-pt) would mis-scale the whole model by 2×.
- `0.01 m/px` ≡ `10 mm/px`: numerically equal, both **uncalibrated**. `VERIFIED`.
- **Reconciliation:** frontend `mpp = scale_mm_per_px / 1000`. `calibration.ts` already accepts this via
  `storedMpp` (`source: 'stored_scale'`). `VERIFIED`.

## 3. Database / API contract (§2.3,4,5)
- **Column exists in the LIVE DB** (`information_schema`): `floor_plans.scale_mm_per_px` present; **0 / 3 rows
  non-null**. `VERIFIED`. Schema is created by `Base.metadata.create_all` (`db/base.py:70`) — **no Alembic
  migrations in the repo**, and the column is already provisioned → **using it needs NO migration.** `VERIFIED`.
- **Not exposed anywhere:** absent from `FloorPlanResponse` (schema), not in the `/scene` payload, and **no
  endpoint reads or writes it**. Endpoints that exist: `GET/POST floor-plans`, `GET/PUT /{id}/layout`,
  `GET /{id}/scene`, `/validate`, `/generate`, `DELETE`, … — none touch scale. `VERIFIED` (fully dormant).
- **Reusable write path?** `PUT /{id}/layout` writes the **canonical/DesignVersion** (furniture layout), not
  a floor-plan-level field. There is **no** floor-plan update endpoint/service for scale. `VERIFIED` → a **new
  (additive) endpoint** is required to persist calibration.
- **Provenance/confidence:** the single `Numeric` column holds only the **scalar**. Source / confidence /
  multiple measurements / conflict state **cannot** be represented in it. `VERIFIED`.

## 4. Kitchen & room completeness (§2.9) `VERIFIED` / `NOT_ASSESSABLE`
- Room labels come from `_majority(text_entries, "Room {i+1}")` (`architectural_service.py:371`) — i.e. OCR
  text votes, else a generic name. The empty plan has **no embedded text and no OCR engine**, so rooms are
  **"Room 1…5"**. `VERIFIED`.
- `f6b65d2b`: **5 architectural rooms, all CONFIRMED, all rendered** (incl. 1 concave). The kitchen is present
  **geometrically** as one of them; its **name** is `NOT_ASSESSABLE` (no text/furniture-tag source). The
  `KITCHEN` anchor (`render_room`/`room_membership`) is a **user furniture tag** — none exist on an empty plan.

## 5. Wall-height source (§2.10) `VERIFIED`
Wall height is a **configured 2.7 m default** (`architectural_service.py:54,553`; frontend `RoomScene3D
WALL_HEIGHT = 2.7`) — **never measured**. Horizontal-scale calibration must stay **separate** from height; a
measured wall height must never be claimed from this default.

## 6. Existing physical reference (§2.8) `VERIFIED`
**None.** Both plan PDFs have 0 embedded chars; no OCR engine; no scale-bar/dimension annotation the system
can read. (Confirmed prior turn and consistent here.)

## 7. Root cause of the dormant field
`scale_mm_per_px` was added to the model (and provisioned by `create_all`) as a placeholder but **never wired**:
no setter (API/UI), no reader (scene/renderer), no unit definition. The frontend independently calibrates from
furniture or falls back to `0.01` — so the field has stayed NULL and unused.

## 8. Minimal recommended implementation (ONLY if approved)
1. **Define** `scale_mm_per_px` := **mm per WORLD px** (resolve the ambiguity; document it in `coordinates.py`).
2. **New additive endpoint** `PUT /floor-plans/{id}/calibration` accepting either a precomputed
   `{scale_mm_per_px}` or `{p1, p2 (world px), known_distance_mm}` → compute
   `scale_mm_per_world_px = known_distance_mm / hypot(p2 − p1)`; **persist to the existing column**. Reject
   zero/negative/non-finite; **never overwrite** an existing value without an explicit `overwrite` flag;
   **preserve** the prior value if the write fails.
3. **Expose** `scale_mm_per_px` (+ derived `mpp` + `calibrated: bool`) in `build_scene(...)` output (additive).
4. **Frontend:** feed `storedMpp = scale_mm_per_px / 1000` into the existing `calibrateScale` (already
   supported); add a two-point "measure a known distance" calibration UI on the 2D plan (additive).
5. **Provenance/confidence:** minimal = scalar-only (presence ⇒ `source: 'user_measurement'`, `confidence:
   'high'`). Richer provenance / multi-measurement / conflict persistence **needs a new JSONB column
   `calibration_meta`** → **propose separately (schema change, own approval)**. The frontend conflict logic
   (median, flagged) already exists for the in-session case.
6. **Wall height** stays the 2.7 m default (out of scope unless separately requested).

## 9. Risks & backward compatibility
- All changes **additive**; legacy plans keep `scale_mm_per_px = NULL` → `SCALE_UNCALIBRATED` fallback
  **unchanged**. Low regression risk.
- The **"px" ambiguity** is the main correctness risk — must be pinned to world px.
- `Numeric(12,4)` gives 4-dp precision on mm/px (~0.1–10 typical) — adequate.
- **Writing scale to the shared Supabase DB is a production mutation** → gated by approval.

## 10. Required regression tests (on approval)
Valid measurement; zero-length; negative / non-finite; multiple consistent; conflicting (median, flagged, not
averaged); persistence + reload; legacy uncalibrated plans; legacy API compatibility; pdf↔world-px↔mm
conversions; mm↔3D round-trips; Kitchen inclusion (count); zero-furniture complete shell; **no mutation of
canonical geometry**; calibrated-vs-uncalibrated scene labelling.

## 11. Stop conditions triggered (→ awaiting approval)
- A **new API endpoint** (additive, but an API-surface change) is required to persist calibration.
- **Richer provenance** may need a **schema column** (`calibration_meta`) — separate approval.
- Saving a calibration **mutates the shared production DB**.
No schema migration is needed for the *existing* `scale_mm_per_px` column itself.

---

### Bottom line
The calibration field `scale_mm_per_px` **already exists in the DB** (no migration needed) but is **fully
dormant and unit-undefined**. A minimal, additive, backward-compatible workflow — define it as **mm per world
px**, add a `PUT /{id}/calibration` endpoint, expose it in `/scene`, and feed the existing frontend
`storedMpp` — would enable user-measured metric scale while keeping the honest `SCALE_UNCALIBRATED` fallback.
The kitchen is present **geometrically** (5/5 rooms) but **unnamed** (no text source); wall height remains a
**2.7 m default** (never measured). **Awaiting explicit approval before any implementation** (new endpoint,
production DB write, and possibly a `calibration_meta` schema addition).
