# Phase 2 Step 2 — Shared-Wall Deduplication: Root-Cause Findings & Stop Decision

**Outcome:** STOPPED before implementation per directive §8 — the premise (a shared physical wall rendered once per room, producing duplicate geometry in the combined 3D scene) **does not hold in the current source**. No code was changed or committed.
**Branch:** `feature/phase-1-empty-architectural-plans` · **Date:** 2026-11-14
**Evidence classes:** `VERIFIED` · `AGENT-REPORTED` · `INFERRED` · `UNKNOWN` · `NOT_ASSESSABLE`

---

## 1. Verified root cause & exact source locations `VERIFIED`

There is **no shared-wall duplication in the combined 3D scene**. Two independent facts establish this:

**(a) The only single-scene consumer builds a boundary-less combined room.**
`Scene3DModal.tsx:57-67` — `combined` is:
```ts
{ id: 'floor-plan', label: 'Floor Plan', bbox: <furniture bbox>, furniture: <all furniture> }
```
It has **no `boundary`** and **no `geometry_source`**. In `RoomScene3D`, `boundaryWalls` requires `room.boundary.length >= 4 && geometry_source === 'architectural'` (`RoomScene3D.tsx:340-357`) → for the combined room it is **empty**. So the per-room boundary-edge path (the only mechanism that could draw a shared wall "once per room") is **never taken** in the combined scene.

**(b) The combined shell is selected from FLAT, scene-level wall lists — each physical wall is a single entry.**
`RoomScene3D` solid-shell selection (`RoomScene3D.tsx`, Step 1): `measuredWalls (reconstructed_walls) → boundaryWalls → realWalls (scene.walls)`. With `boundaryWalls = []`, the combined scene uses either:
- `reconstructed_walls` — a **scene-level, per-physical-wall centerline list** (`wall_reconstruction.build_reconstructed_walls`, collapsed scene-wide; one band per wall), or
- `scene.walls` — the flat face-stroke list.
Both are filtered by the room box and mapped 1:1. **Each physical wall therefore renders exactly once** in the combined scene. (`Scene3DModal.tsx:167`; `measuredWalls.ts`.)

**(c) The per-room consumer renders separate images, not a composited scene.**
`BaseRenderBatch.tsx:75` — it renders rooms **"one at a time and captures a PNG of the WebGL canvas."** A shared wall appearing in room A's image *and* room B's image is **two separate per-room renders**, each correctly showing that room's own enclosure — not duplicate geometry in one scene. (`BaseRenderBatch.tsx:258-259`.)

**Correction of a prior report (honest reconciliation):** `docs/audits/PHASE2_DETERMINISTIC_3D_INSPECTION.md §5` stated shared walls are "rendered once per room = duplicated geometry." On precise re-verification of the *actual* consumers, that per-room boundary-edge duplication **does not occur in any single composited 3D scene**: the combined view is boundary-less (flat list, one entry per wall), and per-room base renders are separate images. The earlier statement described a theoretical per-room composition that the code does not perform.

## 2. Was implementation safe / completed? `VERIFIED`
**Not implemented.** The duplication the task targets does not exist in the current renderer, so there is nothing to deduplicate. Implementing a dedup pass would (a) solve a non-existent problem and (b) risk **incorrectly merging two distinct nearby parallel walls or deleting a real wall** — exactly the unsafe behavior the directive forbids ("Do not merge walls based only on approximate proximity"; "Do not guess room ownership"). Directive §8 stop condition met: *"The current source differs materially from the assumptions in the prior reports."*

## 3. Changed files & diff summary `VERIFIED`
**None.** No files were modified, added (beyond this report), staged, or committed this task.

## 4. Deduplication/ownership strategy & limitations `VERIFIED`
N/A — no dedup was implemented. For the record, a safe strategy *would* require a stable per-physical-wall identity. One already exists upstream (`reconstructed_walls[].id` / `source_wall_ids`, `structured_walls` ids), and the combined scene already consumes the collapsed `reconstructed_walls` (one per wall). So the architecture that would make dedup safe is **already the de-facto behavior** of the combined scene — further dedup is unnecessary.

## 5. Likely real cause of any observed "doubled walls" `INFERRED`
If doubled walls are observed on a **real** plan's combined view, the cause is almost certainly **double-line face strokes (CD-A)**, not shared-room duplication: when `reconstructed_walls` has **no high-confidence (`MEASURED_FROM_PAIRED_FACES`) band** for a wall, Step 1 falls back to `scene.walls`, where a double-line wall is two face strokes → two thin boxes. The lever there is **reconstruction coverage/confidence** (backend `wall_reconstruction`), which is **out of scope** for this renderer task and explicitly prohibited here. This is a hypothesis pending a real multi-room plan (see §7).

## 6. Regression tests, commands & results `VERIFIED`
No tests were added (a safe regression test cannot assert deduplication of a defect that does not exist without fabricating a duplication path the code never produces). Existing suites re-run to confirm Step 1 remains green and nothing regressed:
```
cd frontend && npx tsc --noEmit        # → exit 0
cd frontend && npx vitest run src/lib  # → 7 files, 83 passed (incl. 8 measuredWalls, 13 architecturalView, 7 wallCarve); 0 failures
```

## 7. Live-plan validation status `NOT_ASSESSABLE`
The **backend is down** (Supabase "tenant not found"), so a real multi-room plan's combined 3D scene could not be rendered to visually confirm single-wall rendering end-to-end. The conclusion rests on **source analysis** (conclusive for the current code) plus the Step 1 synthetic harness (which already shows single measured walls). No real-plan evidence is available; no production claim is made.

## 8. Remaining risks & next logical Phase 2 task `VERIFIED`
- **Risk of forcing this task:** implementing proximity-based dedup would merge distinct parallel walls or delete real walls — correctly avoided.
- **The real residual (if any):** double-line faces where measured reconstruction is low/absent (CD-A tail), addressable only by improving backend reconstruction confidence — a **separate, backend task**, not renderer dedup.
- **Next logical Phase 2 tasks** (from the Phase 2 inspection), both currently **blocked on an owner decision**: CD-C **furniture-independent metric scale** (the combined scene's `mpp` is furniture-anchored; empty vs furnished plans scale differently) and CD-D **physical calibration**. Corner mitering (CD-E) is pending but explicitly out of scope here.
- **Recommended smallest next investigation:** once Supabase is restored, open the combined 3D view of a real multi-room plan and classify any doubled walls as (i) double-line faces without high-confidence reconstruction (→ backend reconstruction task) or (ii) something new (→ re-open). Until then, no renderer dedup is warranted.

## 9. Git status & no-commit confirmation `VERIFIED`
```
 M frontend/src/components/design-studio/BaseRenderBatch.tsx
 M frontend/src/components/design-studio/DesignCanvas.tsx
 M frontend/src/components/design-studio/RoomScene3D.tsx
 M frontend/src/components/design-studio/Scene3DModal.tsx
 M frontend/src/lib/scene.ts
 M frontend/src/pages/DesignStudio.tsx
?? docs/audits/PHASE1_ARCHITECTURAL_VIEW_IMPLEMENTATION.md
?? docs/audits/PHASE2_DETERMINISTIC_3D_INSPECTION.md
?? docs/audits/PHASE2_STEP2_SHARED_WALL_DEDUP_FINDINGS.md  (this file)
?? frontend/architectural-harness.html
?? frontend/measured-walls-harness.html
?? frontend/src/components/design-studio/ArchitecturalLayer.tsx
?? frontend/src/dev/architecturalHarness.tsx
?? frontend/src/dev/measuredWallsHarness.tsx
?? frontend/src/lib/architecturalView.test.ts
?? frontend/src/lib/architecturalView.ts
?? frontend/src/lib/measuredWalls.test.ts
?? frontend/src/lib/measuredWalls.ts
```
**Nothing was committed.** The Phase 1 and Phase 2 Step 1 changes remain intentionally uncommitted and unchanged; all harnesses preserved.

---

### Bottom line
Phase 2 Step 2 as specified is a **no-op on the current code**: the combined 3D scene already renders each physical wall exactly once (boundary-less combined room → flat `reconstructed_walls`/`scene.walls` list), and per-room base renders are separate images by design. Deduplicating would risk merging distinct walls for no benefit, so — per the directive's stop conditions — **no implementation was made**. The genuine open items are the backend double-line reconstruction tail (out of scope) and the blocked furniture-independent-scale / calibration decisions.

*Read-only outcome. No application code, canonical data, or Git state was changed.*
