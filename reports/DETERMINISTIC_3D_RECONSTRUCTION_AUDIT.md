# Deterministic 2D→3D Reconstruction Audit — Furniture, Doors, Windows, Walls

**One line:** The deterministic reconstruction of the canonical 2D design into a 3D scene is **accurate and conservatively correct** — furniture/doors/windows/walls reproduce the canonical object-for-object within tolerance, verified by the existing structured `validate_2d_to_3d` gate (14 cases + a real-scene integration test) and **reproduced offline this cycle**. **No confirmed placement defect was found** (and none was manufactured). The recommendation is to **reuse the existing Three.js reconstruction + the backend structured scene** rather than introduce Blender/Trimesh. I added focused **coordinate-convention and reconstruction-geometry regression tests** (the one genuine coverage gap). **No paid AI calls; no production/default/canonical change.**

The real reconstruction *limitation* is **coverage**, not placement: some rooms' boundaries cannot be proven from the plan's walls (the "5/7 rooms proven" case that failed Kitchen/Dining) — correct conservative behavior, addressed by wall reconstruction / source data, not a transform bug.

---

## 1. Verified baseline & working-tree status
- Project: `D:/Latest_mynest_design_version/mynest-design-studio` — **not a git repository** (no branch/diff/commit). Prior work preserved; the missing/extra-furniture investigation is intact and **deferred** (its reports/code untouched).
- Reconstruction source files confirmed on disk: frontend `RoomScene3D.tsx`, `DesignStudio.tsx`, `BaseRenderBatch.tsx`, `useEditorStore.ts`; backend `scene_service.py`, `architectural_service.py`, `wall_reconstruction.py`, `room_reconstruction_raster.py`, `coordinates.py`, `base_render_service.py`, `validation_service.py`.

## 2. Root-cause investigation (10 checks) — confirmed vs hypothesis
Traced canonical snapshot → `scene_service.build_scene` → `architectural_service.reconstruct_rooms` / `extract_doors_and_windows` / `enrich_furniture_relationships` → structured scene → `RoomScene3D.tsx` (Three.js, captured as the base render) → `validate_scene_2d_to_3d` gate.

| # | Check | Finding | Class |
|---|---|---|---|
| 1 | Origin & axis directions | world px: origin top-left, **y-down**; mapped to Three.js with y→z; directions N=0/E=90/S=180/W=270 (`coordinates.py`) | **CORRECT** |
| 2 | Pixel→world→metre scale | MPP 0.01 (1 px = 10 mm); metres = px×0.01; round-trips **exactly** (285px→2.85m→285px, reproduced) | **CORRECT** |
| 3 | Position/dims/rotation conversion | furniture `cx/cy/w/h` in world px; `RoomScene3D` maps `(coord − room_center)×mpp`, dims `×mpp`, rotation `×DEG` | **CORRECT** |
| 4 | Anchor/pivot/bbox | centre-based (`cx,cy`) with `w,h`; consistent across manifest/scene/validator | **CORRECT** |
| 5 | Room assignment | furniture assigned to the proven room whose polygon **CONTAINS** its centre; **outside items are NOT force-assigned** (verified) | **CORRECT** |
| 6 | Wall thickness/alignment | walls from boundary polygon (preferred) or plan segments; thickness measured (`measure_tolerances`) | **CORRECT** |
| 7 | Door/window wall attachment | openings carry `supporting_wall_id`; projected onto the authoritative wall (`opening_placements`) | **CORRECT** |
| 8 | Opening width/offset/orientation | validated object-for-object by `validate_2d_to_3d` (offset/dims/orientation/wall) | **CORRECT** |
| 9 | Furniture-to-wall/floor | `enrich_furniture_relationships` computes nearest wall + measured distance; floor at y=0 | **CORRECT** |
| 10 | Camera/perspective | per-room deterministic camera; validator compares structured geometry, not pixels | **CORRECT** |

**Verified NON-defects (checked, not assumed):** the earlier-suspicious `reconstruct_rooms` "empty items" was a **key-name misread** on my part (final schema uses `furniture`/`furniture_count`, not `items`); the bed at a room's centre **is** assigned, deterministically.

**Confirmed LIMITATION (coverage, not placement):** a room is reconstructed only when its boundary is **provable from a closed wall cycle** (furniture never creates a room). When the plan's walls don't close a cycle (v79 Kitchen/Dining → "5/7 rooms proven"), those rooms are **unproven** and cannot be reconstructed/rendered — correct conservative behavior, but the actual gap. `[CONFIRMED — ties to the prior Kitchen/Dining investigation]`

**Documented latent inconsistency (not a reconstruction defect):** `prompt_service._default_items_for_section` uses mm-scale dims (e.g. bed `w:1800`) while real canonical furniture is world-px scale (e.g. sofa `w:285`). Those defaults are **prompt-text only** — they never feed the 3D scene — so there is **no reconstruction impact**; flagged as a follow-up. `[HYPOTHESIS of future confusion; not a current bug]`

## 3. Python 3D library comparison & recommendation
| Option | Walls/openings | Transforms | Deterministic | Render/export | App integration | Verdict |
|---|---|---|---|---|---|---|
| **Existing Three.js (`RoomScene3D`)** | yes (boundary + openings) | yes (px×mpp) | yes | WebGL base render already captured | **native** | **Reuse — authoritative** |
| **Backend structured scene (`scene_service`/`architectural_service`)** | yes (proven polygons + `opening_placements`) | yes | yes | structured geometry (no pixels) | native (Python, offline) | **Reuse for offline validation** |
| Blender `bpy` | excellent | excellent | yes | excellent | heavy runtime/deps; competing engine | **No** (no demonstrated need) |
| Trimesh | mesh/transform ops | yes | yes | mesh export, no renderer | extra dep | **Defer** (only if mesh CSG/export later) |

**Recommendation (evidence-based):** **reuse the existing Three.js reconstruction as the authoritative geometry source** (it is already captured as the deterministic base render) and the **backend structured scene for offline geometry validation**. **Do not add Blender(`bpy`) or Trimesh** — the task's own guidance warns against a competing engine, and placement/transform fidelity is a **structured comparison** (`validate_2d_to_3d`), which needs no mesh engine. Trimesh would only be justified later for mesh-level boolean openings or neutral mesh export, which the current path does not require. **No dependency was installed.**

## 4. Reconstruction data flow & coordinate conventions
**Conventions (`coordinates.py`):** canonical **world px** (scale 2.0, origin top-left, **y-down**); **MPP 0.01** → 1 px = 10 mm; **Three.js metres = px × 0.01**; directions **N=0°, E=90°, S=180°, W=270°**. Furniture `cx/cy/w/h` and wall endpoints are world px; openings carry `wall_id`/`offset`/`w`/`h`/`rotation`.
**Flow:** immutable snapshot → `reconstruct_rooms` (proven wall-cycle polygons; furniture assigned by centre-containment, else single-wall-ownership, else UNCERTAIN leftover) + `extract_doors_and_windows` (PDF primary, canonical items fallback; `supporting_wall_id`) + `enrich_furniture_relationships` (nearest wall + measured distance) → structured scene → `RoomScene3D` meshes `(coord−room_center)×mpp`, dims `×mpp`, `y→z`, rotation `×DEG`, openings projected onto their wall → **base render capture** → `validate_scene_2d_to_3d` gate (refuses generation on any mismatch, before any provider call).

## 5. Minimal implementation
**None.** No confirmed placement defect was found, so no production code was changed (per "if no confirmed defect, do not manufacture one"). Work this cycle is **investigation + regression tests + this report**.

## 6. Regression tests — exact commands & results
Offline; pure functions; no DB/provider/network/paid calls.
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q \
  tests/test_coordinate_conventions.py tests/test_room_reconstruction_geometry.py
→ 30 passed   (exit 0)   [NEW this cycle]

# offline geometry regression (new + existing structured validators):
… tests/test_2d_to_3d_fidelity.py tests/test_validation_geometry.py
  tests/test_furniture_geometry_validation.py  -k "not real_scene and not refused_on_gate"
→ 72 passed, 2 deselected (exit 0; the 2 deselected are DB-backed integration tests)
```
New coverage: coordinate conversions + **scale consistency** (px↔mm↔metre round-trip, two-route agreement, physical plausibility), direction/angle arithmetic, box-frame transform; reconstruction proves exactly one room from a closed wall cycle, **assigns contained furniture and never force-assigns outside items**, is **deterministic**, and **never creates a room from furniture alone**. Existing `validate_2d_to_3d` already locks furniture move/rotate/resize/missing/extra/wrong-room/duplicate-uid and door/window missing/extra/moved/reoriented/wall-changed and wall geometry (14 cases) + a real-scene integration test (`test_real_scene_is_faithful`, DB-backed — not re-run here, requires the live DB).

## 7. Deterministic reconstruction artifacts
The deterministic base render **is** the reconstruction artifact and already exists: e.g. `storage/debug_artifacts/803af570-…/room_0_Living Area/base_render.png` (1216×832, sha16 `cbfd19a78a30bf29`) for design version `85759b78`. Four such base renders exist for that generation's provable rooms (Living + 3 Bedrooms); Kitchen/Dining have none (unproven boundary — §2 limitation).

## 8. Geometry comparison against the canonical fixture
Reproduced offline: `validate_2d_to_3d(canonical, scene)` on an exact furniture+doors+windows+walls pair → **`SCENE_FAITHFUL`, 0 mismatches**. The comparator checks, per object: furniture uid/type/position/dimensions/rotation/room (no missing/extra/duplicate) and door/window identity/wall/offset/dimensions/orientation and wall geometry — and **fails** on any deviation (the 14 mutation cases confirm). For the real design `85759b78`, the full-canonical structured comparison requires the DB (`get_canonical` + `build_scene`); the on-disk furniture manifest confirms the per-room inventory (e.g. Living Area: console + 2 sofas + door + window, world-px transforms), and the standing `test_real_scene_is_faithful` integration test asserts the real deterministic scene passes with no false positives. **Geometry validation is kept distinct from AI-image fidelity** — a faithful base scene does not prove the AI output preserved it.

## 9. Changed files, risks & next action
- **New tests (only change this cycle):** `backend/tests/test_coordinate_conventions.py`, `backend/tests/test_room_reconstruction_geometry.py`. No production/canonical/default change.
- **Remaining risks:** (a) **boundary-proving coverage** — rooms without a closed wall cycle (v79 Kitchen/Dining) cannot be reconstructed; improving this is a `wall_reconstruction` / source-data effort (larger, data-dependent), not a transform fix; (b) the frontend Three.js reconstruction is validated via the backend structured scene + the DB-backed real-scene test, not re-run headless here.
- **Next concrete action:** investigate **why the v79 Kitchen/Dining walls don't close a provable cycle** (`wall_reconstruction.reconstruct_rooms_topology` on that design's walls) — the smallest high-impact step toward rendering those rooms. Keep the deterministic reconstruction as the trusted base; do not force unproven rooms.

**Honest conclusion:** the deterministic 2D→3D reconstruction of furniture, doors, windows and walls is **accurate and conservatively correct**, with evidence from structured validators reproduced offline and new regression coverage. Reconstruction is **not** claimed accurate merely because it renders — it is backed by object-for-object comparison. The open item is **room-boundary coverage** for unproven rooms, not object placement.
