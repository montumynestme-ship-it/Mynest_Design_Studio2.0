# Phase 2 — Deterministic 3D Architecture: Read-Only Inspection Report

**Scope:** READ-ONLY. No file was modified, staged, committed, or deleted. No AI/paid calls, no DB writes.
**Branch:** `feature/phase-1-empty-architectural-plans` · **Date:** 2026-11-14
**Evidence classes:** `VERIFIED` · `AGENT-REPORTED` · `INFERRED` · `UNKNOWN` · `NOT_ASSESSABLE`
**Leverage:** builds on this session's prior audits (Phase 3A deterministic-3D accuracy, wall/door/window sync, Phase 1 inspection, Phase A carve implementation); every claim re-verified against current source.

---

## 1. Git state & Phase 1 preservation `VERIFIED`
- Branch `feature/phase-1-empty-architectural-plans`; `git log`: `5660f42` (Phase 1 inspection report) → `d1d65f7` (baseline). Matches the reported commits.
- `git status -s`: 2 modified (`DesignCanvas.tsx`, `DesignStudio.tsx`) + 5 untracked (`PHASE1_ARCHITECTURAL_VIEW_IMPLEMENTATION.md`, `architecturalView.ts`, `architecturalView.test.ts`, `ArchitecturalLayer.tsx`, and the throwaway `architectural-harness.html` / `architecturalHarness.tsx`). **Phase 1 feature remains uncommitted** (as the Phase 1 report stated).
- Both harnesses present: `wallcarve-harness.html` + `src/dev/wallCarveHarness.tsx` (Phase A) and `architectural-harness.html` + `src/dev/architecturalHarness.tsx` (Phase 1). **Not deleted.**
- No unexpected divergence from the Phase 1 report. Nothing was changed by this inspection.

## 2. Documentation reviewed `VERIFIED`
`README.md`, `docs/CORE_PIPELINE_DOCUMENTATION.md`, `Document/PROJECT_CONTEXT.md`, `docs/audits/PHASE1_EMPTY_ARCHITECTURE_INSPECTION.md`, `docs/audits/PHASE1_ARCHITECTURAL_VIEW_IMPLEMENTATION.md`, plus this session's Phase-3A / wall-door-window / Phase-A findings. Reconciled against source; the key prior findings (inert `reconstructed_walls`, furniture-anchored mpp, constant wall thickness) are **re-confirmed below with provenance**.

## 3. Actual 2D→3D data flow `VERIFIED`

```mermaid
flowchart LR
  PDF[PDF] --> EX[geometry_extraction_service.extract_walls]
  EX -->|walls world_px = pdf_pt x2.0| SW[structured_walls face strokes + reconstructed_walls derived]
  EX --> OP[openings PDF rects]
  SW --> SCENE[scene_service.build_scene]
  OP --> SCENE
  SCENE -->|scene.walls RAW FACE STROKES + rooms[boundary, opening_placements]| API[/scene JSON/]
  API --> MPP[computeMpp scene.rooms -> FURNITURE-anchored]
  API --> R3D[RoomScene3D]
  MPP --> R3D
  R3D -->|solidWalls = boundaryWalls>=3 ? room.boundary : scene.walls in-box| BOX[extrude each wall as a 0.1m box]
  R3D -->|carveWallSegment verified openings| CARVE[jambs + header + sill voids]
  R3D --> FLOOR[polygon floor from room.boundary]
```

**Runtime consumers (VERIFIED):** `RoomScene3D` is mounted by `Scene3DModal.tsx:167` and `BaseRenderBatch.tsx:258`, both passing `walls={scene.walls}` (raw face strokes) and `mpp={computeMpp(scene.rooms)}` (`Scene3DModal.tsx:71`, `BaseRenderBatch.tsx:89`). `structured_walls` and `reconstructed_walls` are **not passed to the renderer**.

## 4. Wall representation & thickness findings

| # | Question | Answer | Class | Evidence |
|---|---|---|---|---|
| 1 | Which wall collection does 3D consume? | `scene.walls` (raw face strokes) | `VERIFIED` | `Scene3DModal.tsx:167`, `BaseRenderBatch.tsx:260`; `RoomScene3D.tsx:317-334` (realWalls) |
| 2 | Centerlines or face strokes? | **Face strokes** (and, when architectural, the room's `boundary` edges) | `VERIFIED` | `RoomScene3D.tsx:317-357` |
| 3 | How are double-line walls interpreted? | As two independent face strokes (no pairing at render) | `VERIFIED` | `geometry_extraction_service.py:189-217`; renderer has no pairing |
| 4 | Rendered twice? | **Yes** — each face stroke becomes its own box | `VERIFIED` | `RoomScene3D.tsx:805-816` (map over solidWalls) |
| 5 | Actual thickness or constant? | **Constant `WALL_THICKNESS = 0.1 m`** | `VERIFIED` | `RoomScene3D.tsx:47`; box args `[len+0.1, 2.7, 0.1]` (`wallCarve.ts:83`, `RoomScene3D.tsx:611-612`) |
| 6 | Measured thickness calibrated? | Measured from face-pair **spacing in pixels**, **not calibrated** to mm | `VERIFIED` | `wall_reconstruction.py:45-106` (`measure_tolerances`) |
| 7 | Does `reconstructed_walls` preserve source geometry? | No — it is a **derived centerline layer** (collapsed pairs + snapped/merged fragments); additive, never replaces `structured_walls` | `VERIFIED` | `wall_reconstruction.py:110-338` (`_collapse`, `build_reconstructed_walls`) |
| 8 | Unavailable / low-confidence reconstruction? | `CONFIGURED_FALLBACK` (keep 10px) or `UNVERIFIED` (confidence "low"); `build_scene` wraps in try/except → `[]`. **Irrelevant to 3D — layer is inert** | `VERIFIED` | `wall_reconstruction.py:316-335`; `scene_service.py:487-494` |
| 9 | Corners/junctions continuous? | Each wall box is extended by `+WALL_THICKNESS` (corner fudge) to overlap at corners — crude, not mitered | `VERIFIED` | `wallCarve.ts:83` (`L = lenM + wallThickness`) |
| 10 | Gaps/overlaps/duplicates possible? | **Yes** — double faces = parallel duplicate boxes; corner fudge = overlaps; per-room rendering = shared-wall duplication | `VERIFIED` | §5 below |

**Root cause (thickness):** the renderer never consumes the **measured-thickness centerline** layer (`reconstructed_walls`) — it extrudes raw face strokes at a fixed 0.1 m. The measured data exists (`MEASURED_FROM_PAIRED_FACES`, `thickness_px`) but is inert.

## 5. Shared walls & room geometry findings `VERIFIED`
- `RoomScene3D` renders **per room**: `realWalls` keeps every `scene.walls` segment whose midpoint is inside a **padded room box** (`pad = max(bw,bh)*0.35`, `RoomScene3D.tsx:317-334`), or, when architectural, each **`room.boundary` edge** (`:340-357`).
- A wall **shared** by two adjacent rooms sits inside both padded boxes (and is an edge of both boundaries) → it is **rendered once per room = duplicated geometry**. (`VERIFIED`.)
- Combined with double-line face strokes, a single physical partition between two rooms can render as up to **four** thin boxes (two faces × two rooms).
- **Floor**: polygon floor from `room.boundary` when architectural (`THREE.Shape`, supports concave), else a rectangular bbox plane (`RoomScene3D.tsx:427-439,717-742`). Concave `VERIFIED` supported; open/incomplete boundaries render whatever points exist (no fabrication).
- The renderer therefore produces **two overlapping walls / duplicated shared walls**, not one continuous architectural wall.

## 6. Door/window carving findings `VERIFIED`
- Consumes `room.opening_placements` filtered to `verified` for carving (`RoomScene3D.tsx:398-417`); windows also drive the glass pane (`:380-393`).
- `verified` = projected onto a real supporting wall by `scene_service._attach_opening_placements`/`_find_supporting_wall` (projection within segment, rotation ≤25°, perp ≤100 door/60 window); unverified = authored position, `NEEDS_REVIEW` (`scene_service.py:224-331`).
- Carve (`wallCarve.ts`): matches an opening to a rendered segment (perp ≤ `CARVE_PERP_TOL 0.4 m`, angle ≤ 20°), subtracts the span → **jamb solid runs + header** (`+ sill` for windows); merges overlapping spans (multiple openings per wall OK); clamps the void to the segment (`[-halfL, halfL]`) so an opening **cannot cross the wall endpoints** (it is clamped, not extended). Wall **outside** the opening is preserved as solid runs. (`VERIFIED`.)
- **Unverified openings stay solid** (not passed to carve); the window group draws the legacy sill+header+glass overlay instead (`RoomScene3D.tsx:870-881`). (`VERIFIED`.)
- **Dimensions provenance:** opening `w/h` come from `opening_placements` (world px, from the PDF rect / editor item) — sourced. Door **head** height = Project-Setting lintel when `lintel_verified`, else `furniture3d('door').height` (art-directed default). Window `head = WIN_SILL_H(0.9)+WIN_GLASS_H(1.3)` and `sill = 0.9` are **renderer constants, not measured** (`RoomScene3D.tsx:52-53,402-414`). ⇒ window sill/head are art-directed defaults, **not architectural measurements** (must not be reported as measured).

## 7. Coordinate & scale findings `VERIFIED`

| Constant | Value | Runtime path that uses it | Class |
|---|---|---|---|
| `WORLD_SCALE` | 2.0 | PDF→world px for walls/openings (extraction) | `VERIFIED` |
| `SCALE` | 0.15 | catalog mm→world px for **furniture** (frontend editor) | `VERIFIED` |
| `DEFAULT_MPP` | 0.01 | backend **architectural mm** (`architectural_service` distance/size) + the YOLO/`scene_bridge` raster path | `VERIFIED` |
| `computeMpp` | ≈ `2.0/max(bed.w,bed.h)` ≈ 1/150 ≈ 0.006667 (else side-table 0.45, else **0.01**) | **the 3D renderer's metres-per-pixel** | `VERIFIED` |

- **The 3D path uses `computeMpp` (furniture-anchored)**; the backend `DEFAULT_MPP=0.01` is a *different* value used only on the architectural-mm/raster paths. The two are **not interchangeable** and disagree (0.006667 vs 0.01 — the 1.5× conflict from Phase 1 CD3). (`VERIFIED`.)
- **Every physical measurement's source:** wall px = PDF×2 (geometric, not physical); metres = px × `computeMpp` where `computeMpp` is anchored to an **assumed** bed length (~2.0 m) — i.e. a heuristic, **not a calibration**. No documented real-world calibration exists. ⇒ **Physical dimensions are `UNVERIFIED`.** Do not adopt a new authoritative scale without calibration evidence (none found).

## 8. Furniture-independence assessment `VERIFIED`
Furniture currently **does** influence architecture-adjacent outputs:

| Aspect | Furniture-dependent? | Evidence |
|---|---|---|
| **3D metric scale (mpp)** | **Yes** — `computeMpp` reads `room.furniture` (bed/side-table); **no anchor furniture → falls back to 0.01**, a *different* scale | `scene.ts:274-284` |
| Camera focus / fit | **Yes** — `aiFitDist`, `furniturePts`, target centroid from furniture | `RoomScene3D.tsx:492-551` |
| Scene bbox / room bbox | **Yes** for furniture-fallback rooms (hull of furniture); architectural rooms use wall polygon | `architectural_service.py:394-428` |
| Room label / assignment | **Yes** — majority vote over contained furniture | `architectural_service.py:296-354` |
| **Wall placement (px)** | **No** — wall endpoints are from the PDF | `geometry_extraction_service.py` |
| Architectural room **boundary (px)** | **No** — wall-proven polygon | `architectural_service.py:253-281` |

**Invariant check:** *"changing furniture inventory must not change architectural geometry."* **Partially VIOLATED.** The **pixel** topology (wall endpoints, architectural room polygons) is furniture-independent, but the **metric** scale (and thus every metre dimension, wall length in metres, floor size), the **camera**, **fallback-room geometry**, and **labels** change with furniture. Critically, the **same empty plan renders at a different metric scale (0.01) than when a bed is present (1/150)** — a deterministic-architecture concern. (`VERIFIED`.)

## 9. Existing test coverage `VERIFIED`
Backend (offline): `test_reconstructed_walls_layer`, `test_wall_thickness_provenance`, `test_furniture_placement_2d_to_3d`, `test_furniture_2d_to_3d_audit`, `test_opening_placement`, `test_opening_placement_fidelity`, `test_room_reconstruction_geometry`, `test_geometry*`. Frontend: `wallCarve.test.ts` (carve math), `architecturalView.test.ts`. These cover: face-stroke extraction, reconstructed-walls provenance/thickness, 2D→3D transform preservation, opening placement/projection, carve jamb/header/sill. **Not covered:** shared-wall de-duplication, corner-junction continuity, furniture-inventory-invariance of the rendered architecture, renderer consumption of measured thickness, empty-vs-furnished scale equality.

## 10. Missing regression tests (proposed) `VERIFIED`
Straight wall; double-face representation; L-shape; T/cross junction; angled (where supported); multiple rooms sharing a wall (assert **one** rendered wall, not duplicates — currently would FAIL); concave floor polygon; door/window opening; multiple openings on one wall; unverified opening stays solid; opening near wall endpoint (clamped, not crossing); missing/low-confidence `reconstructed_walls`; zero furniture renders; **same architecture + different furniture inventory ⇒ identical wall/room/floor geometry AND identical metric scale** (currently would FAIL on scale). Expected geometric behavior stated per case; no existing expected results altered.

## 11. Confirmed defects & root causes

| ID | Class | Defect | Root cause | Impact |
|---|---|---|---|---|
| CD-A | `VERIFIED` | 3D walls = raw face strokes at a fixed 0.1 m; measured-thickness `reconstructed_walls` inert | renderer consumes `scene.walls`, not the centerline layer (`RoomScene3D.tsx:47,805-816`; `scene_service.py:487-494`) | Double-line walls render as 2 thin boxes; thickness not faithful |
| CD-B | `VERIFIED` | Shared walls duplicated across adjacent rooms | per-room wall selection by padded box / boundary edge (`RoomScene3D.tsx:317-357`) | Overlapping/duplicate wall geometry |
| CD-C | `VERIFIED` | Architectural **metric scale is furniture-anchored** (empty vs furnished differ) | `computeMpp` reads furniture; fallback 0.01 (`scene.ts:274-284`) | Architecture not furniture-independent / not deterministic across inventories |
| CD-D | `VERIFIED` | Physical dimensions `UNVERIFIED`; dual scales (0.01 vs 0.006667) | no calibration; `DEFAULT_MPP` vs `computeMpp` | Any mm/real-size claim unreliable |
| CD-E | `VERIFIED` | Crude corners (+0.1 m box fudge), no miter | `wallCarve.ts:83` / box sizing | Corner overlaps/visual artifacts; not continuous |

## 12. Hypotheses & unverified issues
- `INFERRED` — `reconstructed_walls` on fragmented/offset real plans may mis-pair faces or leave `UNVERIFIED` bands (`WALL_RECONSTRUCTION_ENABLED` default OFF), so adopting it for CD-A needs per-plan validation.
- `INFERRED` — an opening whose authored centre projects near a shared wall's end could carve the wrong room's segment copy (interaction of CD-B with carve matching).
- `NOT_ASSESSABLE` — real-plan 3D fidelity (wall thickness/double walls/shared walls on an actual PDF): the **backend is down** (Supabase), so no live `/scene` could be rendered; only synthetic fixtures and source were used.

## 13. Visual / synthetic evidence `AGENT-REPORTED`
The Phase A harness (`/wallcarve-harness.html`) and the Phase 1 harness (`/architectural-harness.html`) render `RoomScene3D` / the overlay from **synthetic** scenes without a backend. The Phase A harness already demonstrated verified-opening carving (jambs/header/sill) and unverified-stays-solid. No real-plan visual evidence is available (backend down); synthetic evidence is **not** proof of production fidelity.

## 14. Smallest proposed implementation sequence (NOT implemented)
1. **Consume `reconstructed_walls` in `RoomScene3D`** where `thickness_source == MEASURED_FROM_PAIRED_FACES` (high confidence): render one centerline box at the measured thickness; **fall back** to the current face strokes when a band is `CONFIGURED_FALLBACK`/`UNVERIFIED` or reconstruction is empty. Additive; data already emitted. *(CD-A; reduces CD-B by collapsing paired faces.)*
2. **Render architecture scene-level & dedup by wall id** (or render shared walls once), instead of per-room, so a shared wall is a single box. *(CD-B.)*
3. **Make `mpp` furniture-independent**: derive the 3D scale from a plan-level source with a **deterministic furniture-free fallback**, so empty and furnished plans render identically. *(CD-C — but see blocker: needs a calibration/scale decision.)*
4. **Mitre corners** instead of the +0.1 fudge. *(CD-E.)*
Physical calibration *(CD-D)* stays **blocked** pending an owner decision with evidence.

## 15. Files likely to change (when authorized) `VERIFIED`
`frontend/src/components/design-studio/RoomScene3D.tsx` (consume reconstructed_walls, scene-level/dedup walls, mpp source, corners), `frontend/src/lib/scene.ts` (`computeMpp`/scale source), possibly a new pure `frontend/src/lib/wallRender.ts` helper (testable). **Renderer/frontend only** — no backend, schema, canonical, or `reconstructed_walls` algorithm change needed for steps 1–2, 4.

## 16. Risks & blockers `VERIFIED`
- **Physical scale calibration** has no documented evidence → CD-C/CD-D are blocked on an owner decision; must not invent a scale.
- Changing `mpp` or wall rendering **will shift existing base-render compositions** → regression risk for the AI base/control images (needs paired-capture regression before adopting).
- `reconstructed_walls` per-plan reliability unvalidated.
- **Backend down** → no live real-plan verification until Supabase restored.
- The directive forbids editing `RoomScene3D.tsx`/`wallCarve.ts`/`reconstructed_walls` *in this task*; the sequence above is for a **separately authorized** implementation.

## 17. Test commands & results `VERIFIED`
Offline, venv Python / vitest, no DB, no paid calls:
```
backend/.venv/Scripts/python.exe -m pytest tests/test_reconstructed_walls_layer.py \
  tests/test_wall_thickness_provenance.py tests/test_furniture_placement_2d_to_3d.py \
  tests/test_furniture_2d_to_3d_audit.py tests/test_opening_placement_fidelity.py \
  tests/test_opening_placement.py -q
# → 46 passed, 5 warnings in ~17s
cd frontend && npx vitest run src/lib/wallCarve.test.ts   # → 7 passed (carve jamb/header/sill math)
```
Warnings: Pydantic v2 class-config deprecation (library). Failures: 0. Nature: real production functions (extraction, reconstruction provenance, opening projection, carve math) against synthetic/fixture plans — not live `/scene`.

## 18. Git status & no-modification confirmation `VERIFIED`
Branch `feature/phase-1-empty-architectural-plans`; `git status` unchanged from §1 (2 modified + 5 untracked Phase 1 artifacts + this report once written). **This inspection modified, staged, committed, or deleted nothing.** `RoomScene3D.tsx`, `wallCarve.ts`, `reconstructed_walls`, coordinate conversions, canonical data, backend APIs, and both harnesses are untouched.

---

### Bottom line
Deterministic 3D architecture is **topologically honest but not thickness- or scale-faithful**: the renderer extrudes **raw face strokes at a constant 0.1 m**, **duplicates shared walls**, and anchors its **metric scale to furniture** (so an empty plan scales differently than a furnished one), while the **measured-thickness centerline layer it needs already exists but is inert**. The highest-leverage, lowest-risk Phase 2 step is to **consume `reconstructed_walls` (high-confidence) and dedup shared walls in the renderer** — additive and frontend-only. Furniture-independent metric scale and true physical calibration are the harder, **blocked** items (no calibration evidence) and must not be resolved by inventing a scale. Await authorization for the implementation.

*End of report. Read-only; no application code, canonical data, or Git state was changed.*
