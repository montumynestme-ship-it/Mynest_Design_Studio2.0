# Phase 2H-3 — AI Furniture Preservation Audit (audit-only)

**Mode:** read-only. No source edits, no FAL/AI calls. Floor plan `f6b65d2b-4f96-4931-9f08-67dbd09776f6`.

## 1. Phase 2H-2 artifact integrity — CONSISTENT
Both files exist (`backend/output/p2h2_live_transform_audit/*.json|.md`). JSON checks:
- 22 items, **22 unique canonical uids, 22 captured, 0 dup**; totals **22 PASS / 0 MISMATCH / 0 INCONCLUSIVE / 0 NOT_CAPTURED**.
- All **8 room ids** present in coverage; `missing/unexpected/duplicate` all empty.
- Per-item identity, position, rotation, and dimension fields present for every item. ✔

## 2. `design_version_id` lifecycle finding — not a proven defect
- **Endpoint behavior:** `GET /scene` returns the **latest** `DesignVersion` id (read-only *select* via `floor_plan_service.get_latest_version_info` → `_latest_version` `ORDER BY version_number DESC`, wired at `floor_plans.py:114`). It does **not** create or mutate a version.
- **Versioning:** `save_layout` is append-only; a new version is minted only when `_furniture_fingerprint` differs — an identical layout is a **no-op**.
- **Observed:** `aa213074…` (2H-1, 2026-10-10) → `1831bf84…` (2H-2, 2026-10-12). **bedroom-1 furniture is identical across both reads** (5 uids + coords match).
- **Conclusion:** a new append-only version was created between the reads — either a real edit to some room, or a functionally-identical re-save the fingerprint treated as changed. **Cannot distinguish without DB version history/timestamps.** Not a proven defect.
- **Impact:** (a) *Reproducibility* — `/scene` "latest" is not a stable pin across time; pin a specific `design_version_id` to reproduce. (b) *AI pairing* — generations bind to a **frozen snapshot** (`capture_generation_snapshot` records the exact version), so a generation's furniture is pinned; but an audit reading "latest" at a different time may audit a **different version** than a given generation used.

## 3. Bedroom 1 base↔AI pair — UNVERIFIED (files purged)
- Requested pair `p2b2_ref_bedroom1.png` / `p2c_b1_output.png` (req `01a12526…`, prompt `bc254455…`): **not on disk**. Both prior session scratchpads (`87104d1f`, `82e0bbde`) are **purged**; the base PNG, AI output, and `p2c_fal_result.json` no longer exist.
- `frontend/tests/artifacts/furniture-missing/*-ai.png` are **not a substitute**: 1280×720 UI/preview screenshots (not the 1216×832 FAL output), no FAL request/seed/base-hash linkage, and they assert "faithful" (conflicts with the Phase 2C pixel analysis).
- **Status: UNVERIFIED** — no verified same-attempt base↔AI FAL pair survives on disk this phase. Prior-recorded metadata (model `flux-kontext/dev`, seed 1587969140, base `3a21d5bf…`/`1ada0117…`, out `c9b75286…`) is reported but **cannot be re-verified**.

## 4. Five-item Bedroom 1 comparison
| uid | type | canonical (live) | deterministic scene (2H-2) | base image | AI output | status this phase |
|---|---|---|---|---|---|---|
| bed `…1845` | bed | 504.3,671.8 155.5×281.3 −90.3 | **PASS** (dX=dZ=0, dRot=0) | visible (prior) | preserved (prior) | det PASS; base/AI **INCONCLUSIVE** (pair purged) |
| side-table `…7384` | side_table | 402.6,541.0 67.5×118.8 0 | **PASS** | visible (prior) | preserved + lamp added (prior) | det PASS; base/AI **INCONCLUSIVE** |
| side-table `…6014` | side_table | 402.6,822.1 67.5×113.8 0 | **PASS** | visible, not occluded (prior) | **absent** (prior) | det PASS; base/AI **INCONCLUSIVE** (prior: absent) |
| wardrobe `…2167` | wardrobe | 675.8,513.2 216.9×90.0 0 | **PASS** | visible (prior) | preserved (prior) | det PASS; base/AI **INCONCLUSIVE** |
| dressing-table `…2783` | dresser/dressing | 725.7,836.1 119.8×90.0 0 | **PASS** | visible as 3-drawer chest (prior) | **reads as bench** (prior) | det PASS; base/AI **INCONCLUSIVE** (prior: bench) |

Base/AI columns reflect **prior (now-unavailable) Phase 2C/2D evidence**, not re-verified here. Identity presence/absence only — no 3D position/scale/rotation is claimed from the AI image.

## 5. First proven divergence (per item)
- **Deterministic stages (canonical → scene):** **no divergence** — re-verified this phase (2H-2 PASS for all five).
- **Base render + FAL stages:** **not re-provable this phase** (verified pair purged). Prior evidence located a divergence at the **FAL image-to-image output** for `side-table-…6014` (absent) and `dressing-table-…2783` (bench), with the base showing both post-cutaway. This phase classifies that as **UNPROVEN-THIS-PHASE** (not guessing).

## 6. Confirmed facts vs hypotheses
**Confirmed:** 2H-2 JSON consistent (22/22 PASS, 8 rooms); deterministic 2D→3D transform faithful for all 5 BR1 items; `/scene` returns latest append-only version (read-only) and the dvid changed via a new appended version with bedroom-1 content unchanged; no verified FAL pair on disk.
**Hypotheses (not re-proven):** FAL drops low/front-corner furniture (`…6014`) and alters the dresser-form dressing table to a bench (Phase 2C/2D); the dvid change was a functionally-identical re-save not deduped by the fingerprint.
**Evidence needed:** a freshly generated, **persisted** verified base↔AI pair (base capture + 1 FAL call) stored under `backend/output` (not scratchpad); DB design-version history to resolve the dvid lifecycle; pixel-level per-item base-vs-FAL analysis on the fresh pair.

## 7. Limitations & recommended next investigation
- Purged scratchpads ⇒ Steps 3–5 preservation conclusions are **INCONCLUSIVE** this phase. No FAL call made (not approved). No DB version-history access.
- **Recommendation (needs approval):** regenerate **one** verified Bedroom 1 base↔AI pair with current production settings, persist it under `backend/output/` so it survives scratchpad purges, then re-run the pixel-level per-item base-vs-FAL comparison to re-prove (or refute) the FAL-stage divergence. Keep door/window and camera out of scope.

## Confirmation
No production source edits, no temporary edits, no FAL/AI calls; no changes to furniture coordinates/identity/dimensions/rotation/room assignment/canonical, room/wall geometry, camera/FOV/solver, `computeMpp`, prompts/models/params/thresholds, or render pipeline. Deterministic correctness is confirmed; AI-preservation conclusions are explicitly marked INCONCLUSIVE because the verified pair is unavailable.
