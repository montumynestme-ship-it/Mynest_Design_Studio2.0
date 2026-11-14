# MyNest Design Studio — AI Render Issue Triage & Investigation Plan

**Context:** You upload a 2D floor plan, manually place furniture SVG icons on it, then click **AI Render**. The expected result is a realistic 3D interior render that **follows the original floor plan and furniture layout** — not a newly imagined room.

**Working rule:** Preserving the original 2D layout and furniture placement takes priority over visual realism. *A photorealistic result that silently changes the design is NOT a successful render.*

**Mode:** Investigation & recommendations only. No code changes unless you approve them. No FAL calls unless approved.

> Status legend — **[VERIFIED]** backed by source/evidence from the prior investigation (Phases 2–2L); **[HYPOTHESIS]** likely cause, not yet proven; **[PRELIMINARY]** visual observation only.

---

## 1. Initial analysis of the screenshots

### Issue A — Living Area: room geometry & furniture layout
**Observed:** The 2D plan shows the room boundary, door, sofa, and other furniture. The render looks like a **cut-away 3D model**, with walls/furniture that don't clearly match the full layout.
- **[VERIFIED]** The cut-away look is **by design**: the base render uses an *open-top dollhouse* mode (`RoomScene3D.tsx`, `aiRenderMode`) with a **near-wall cutaway** that hides the walls between the camera and the room so low furniture is visible. The AI output faithfully follows that base composition.
- **[VERIFIED]** The deterministic 3D scene places every canonical furniture item exactly (Phase 2H-2: 22/22 items, 0 position/rotation delta). Living Area canonical = `console` + 2× `lounger-sofa`.
- **[HYPOTHESIS]** Any "furniture doesn't match" in the *final image* is the **AI image-to-image stage** recomposing the scene (see Issue D / root cause F1), not the deterministic scene.
- **Investigate:** room-boundary reconstruction (`scene_service.build_scene`), wall generation, furniture-to-room association (`group_by_room`), camera framing (`aiCamera.solveAiCamera`).

### Issue B — Kitchen: incorrect framing & grey background
**Observed:** The rendered kitchen occupies only a small part of the output, surrounded by a large grey background. The 2D plan shows an **L-shaped** kitchen.
- **[VERIFIED]** The grey is the scene background (`#eceef1`); the room is an open-top dollhouse that fits-to-content, so it can sit small within the 1216×832 frame. Observed directly in the Phase 2B Kitchen base capture (L-shaped counter + a **detached wall panel** on the left).
- **[VERIFIED]** The L-shaped kitchen maps to an **overlapping room representation** — the live scene emits both a combined `kitchen-dining-area` (architectural) and separate fallback `kitchen`/`dining-area` rooms (Phase 2F-1). This fragments walls and splits furniture/openings.
- **[VERIFIED]** No furniture *clipping* was found in any room (Phase 2H-2) — so this is **framing/composition + background padding**, not objects falling outside the frame.
- **Investigate:** base-image scene bounds & camera fit (`aiCamera` fit distance), the overlapping-room geometry (F6), output padding/aspect ratio, whether the room footprint is preserved.

### Issue C — Dining Area: uncertain geometry / missing structural evidence
**Observed:** The result looks attractive, but the image alone doesn't prove the original boundaries, openings, and object positions were preserved.
- **[VERIFIED]** Correct — the image alone cannot prove 3D geometry preservation. The model receives **only a base PNG + prompt text, no structured geometry** (F1), so there is no geometric lock to verify against.
- **[VERIFIED]** The "Dining Area" section can be **empty** while the dining table is grouped under `kitchen-dining-area` (Phase 2F-1) — a room-grouping discrepancy.
- **Investigate:** geometry conditioning (F1), base-image fidelity, opening reconstruction (`_attach_opening_placements`), output validation (F7).

### Issue D — Bedrooms: furniture identity & placement
**Observed:** Bedrooms look realistic, but some furniture/architecture differs from the 2D layout.
- **[VERIFIED]** On the one auditable same-attempt pair (Bedroom 1, Phase 2K): **3 of 5 items preserved** (bed, wardrobe, dressing-table-with-mirror); **2 side tables AMBIGUOUS** (only 4 distinct objects vs 5 canonical); positions **recomposed**. The deterministic base showed all 5; the divergence is at the **AI output stage**.
- **[VERIFIED]** The AI is partly *redesigning* rather than strictly *reconstructing*, because it has creative freedom under image-to-image with no structural conditioning (F1).
- **Investigate:** furniture identity/position tracking, object visibility/saliency in the base (small items <0.5% of frame), room-specific conditioning, reconstruct-vs-redesign behavior.

> These are preliminary visual observations plus prior evidence — not a complete per-screenshot root-cause proof. The screenshots alone don't expose the exact generation inputs or which objects were lost/moved/resized; a **verified same-attempt base+output+metadata pair** is required per issue.

---

## 2. Architecture areas under investigation
1. **Canonical design & furniture data** — each placed SVG icon → correct furniture ID, position, rotation, dimensions, room. *(`data/furniture.ts`, `DesignStudio.tsx` placement, `DesignVersion.canonical_json`.)* **[VERIFIED sound]**
2. **2D→3D scene construction** — walls, room dims, openings, furniture transforms, units, actual generated scene. *(`scene_service`, `RoomScene3D`, `computeMpp`.)* **[VERIFIED exact transforms; room-overlap + opening gaps noted]**
3. **Base rendering & camera** — correct framing + small-object visibility before AI. *(`BaseRenderBatch`, `aiCamera`, cutaway.)* **[framing/saliency open]**
4. **AI conditioning & generation** — does the model get only image+text, or also depth/edges/masks? *(`fal_flux_adapter`, `FAL_USE_CONTROLNET`.)* **[VERIFIED: image+text only; controlnet path exists but disabled]**
5. **Output validation & version isolation** — detect missing furniture, changed geometry, wrong room, stale results. *(`furniture_object_validation_service`, `fidelity_service`, `AIGeneration` + frozen snapshot, `render_input_contract`.)* **[validators exist but audit-only; status not evidence-driven]**

---

## 3. How each new issue will be handled
For every issue you send, I will provide:
- **Observed problem** — what the screenshot/test actually shows.
- **Likely root causes** — ranked hypotheses, clearly separated from verified defects.
- **Evidence required** — exact source files, functions, logs, or reproducible tests to confirm.
- **Recommended changes** — specific architecture/pipeline/code-logic changes + which existing files.
- **Priority** — **P0** correctness · **P1** render quality/reliability · **P2** optimization.
- **Acceptance criteria** — how we prove the fix works without breaking the original design.

**To trace a real root cause (not guess), include for the issue:** the **Debug Info**, the **base render**, and the **generated output** for the same attempt (same generation ID / design version). If a base↔output pair can't be linked by IDs/hashes/dimensions, it's marked **NOT_AUDITABLE**.

---

## 4. Root-cause reference (from the prior investigation)
| ID | Root cause | Relates to | Severity |
|---|---|---|---|
| F1 | AI model gets only base PNG + prompt text — **no structured conditioning** (depth/edge/mask) | A, C, D | P1 (biggest lever) |
| F2 | AI image-to-image recomposes/drops furniture (high variance) | A, D | P1 |
| F3 | Base visibility of low furniture — cutaway added; small items still <0.5% frame | B, D | P2 |
| F4 | No base-PNG hash in production metadata; design_version drift | C, validation | P0 (provenance) |
| F5 | Openings with `wall_id=None` (NEEDS_REVIEW); verify count drift | C | P1 (door/window phase deferred) |
| F6 | Overlapping/duplicate rooms (kitchen-dining-area vs kitchen/dining) | B, C | P1 |
| F7 | `ai_geometry_faithful` status not evidence-driven (overconfident) | all | P1 |
| F8 | Global `mpp` anchored to first bed → absolute-scale depends on room order | geometry | P2 |
| F9 | Camera — no clipping found; **not a defect** (framing/background is the B symptom) | B | — |

**Primary conclusion:** the deterministic pipeline is faithful; the dominant quality limitation is **lack of structured conditioning + no evidence-based output validation**, not the AI model size. The highest-value next step is a controlled depth/canny **conditioning experiment** (needs FAL-cost approval) plus wiring the existing validators into an honest status.

*(Full detail: `backend/output/p2l_architecture_investigation/p2l_core_architecture_investigation.md`.)*

---

**Send your first specific issue** (missing furniture, wrong walls/doors, the grey background around the kitchen, or the 2D↔3D mismatch). Include the Debug Info, base render, and generated output for that attempt so we trace the actual inputs instead of guessing.
