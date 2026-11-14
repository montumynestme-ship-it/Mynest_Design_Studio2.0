# Phase 2K — AI Render Output vs Canonical Furniture Preservation Audit

**Audit only. No FAL calls, no code changes.** Scope: furniture preservation; doors/windows + camera recorded separately (not modified).

## 1. Artifact inventory & verified generation pairs
| Pair | Linkage | Status |
|---|---|---|
| **Bedroom 1** (`p2h4_bedroom1_preservation/`) | base `04ea7854` → submitted `9e670a46` (pixel-identical) → output `b6c9580e`; req `01a133ca`, model flux-kontext/dev, seed 1558158484, prompt `7fe63b11`, dvid `1831bf84`; **contract provenance = PASS (version + byte match)** | **AUDITABLE** |
| Production `storage/generations/*` | AI outputs present, **no persisted base image** | NOT_AUDITABLE |
| `frontend/tests/artifacts/furniture-missing/*-ai.png` | 1280×720 UI screenshots, no FAL linkage | NOT production evidence |
| Phase 2C `p2c` pair | prior scratchpad **purged** | its "bench"/"round" findings NOT re-verifiable |

Only **Bedroom 1** has a verified same-attempt pair. (UID note: Phase 3 listed `…496014`/`…497384` — the actual uids are `side-table-1787478946014` / `…947384`.)

## 2–3. Per-item comparison & classification (Bedroom 1, verified pair)
| uid | type | base identifiable | AI identifiable | classification | conf | geometry proven |
|---|---|---|---|---|---|---|
| bed `…1845` | bed | yes | yes (bed) | **PRESERVED** | HIGH | No |
| wardrobe `…2167` | wardrobe | yes | yes (2-door) | **PRESERVED** | HIGH | No |
| dressing-table `…2783` | dressing | yes (3-drawer chest) | yes (**table + drawer + wall mirror** = dressing table) | **PRESERVED** | MED-HIGH | No |
| side-table `…6014` | side_table | yes | no | **AMBIGUOUS** | LOW | No |
| side-table `…7384` | side_table | yes | no | **AMBIGUOUS** | LOW | No |

**Count:** 5 canonical → **4 distinct output objects** (bed, wardrobe, dressing-table, one bench) ⇒ **≥1 side table not distinctly identifiable**.

Phase 3 re-checks against the verified pair:
- `…6014`: prior "not identifiable" → **CONFIRMED AMBIGUOUS** (a bench is at front-left; can't prove missing vs merged vs repositioned under the recomposition).
- `…7384`: prior "appears round" → that was the **purged p2c run**; in this verified pair `…7384` is **AMBIGUOUS** (no table at its box; recomposition prevents binding).
- `…2783` dressing: prior "bench / not preserved" → **REVISED to PRESERVED** — this run rendered it as a table **with a mirror**, matching the canonical dressing-table identity.
- bed / wardrobe: **PRESERVED identity**, exact geometry **NOT PROVEN** (image-space only).

**AI-added decor:** none proven non-canonical this run (the mirror is the canonical dressing-table feature; bed pillows are canonical; no lamp/plant). The front-left bench is AMBIGUOUS (altered side table vs addition) — not auto-classified as a replacement.

## 4. Earliest proven divergence stage
- Canonical → scene: **PASS** (2H-2 exact transforms; 2J contract: furniture 22/22, identity match).
- Scene → base image: **PASS** (base shows all 5 identifiable items).
- Base → submitted FAL input: **PASS** (pixel-identical re-encode).
- **Submitted → raw FAL output: DIVERGENCE (the earliest proven)** for `…6014`/`…7384` (base-identifiable → output not-identifiable) and a **strong recomposition** of positions (base→output diff 15.47).
- **Mechanism UNPROVEN** — image-space cannot distinguish drop vs merge vs reposition. The Phase 2J input-contract PASS is **not** treated as output-preservation proof.
- bed/wardrobe/dressing: **no proven divergence** (identity preserved; geometry unprovable).

## 5. Camera & door/window issue register (RECORD ONLY — not modified)
**Openings**
1. `bedroom-3` editor door — `wall_id=None, verified=False` (NEEDS_REVIEW). Evidence: live `/scene` opening_placements.
2. `kitchen-dining-area` editor door — `wall_id=None` NEEDS_REVIEW.
3. `bedroom-3-2` (duplicate room) editor window — `wall_id=None` NEEDS_REVIEW.
4. `bedroom-1` door+window — **PLACED/verified**; base shows window on left wall + door right; AI output shows a left-wall window. (No defect observed for BR1.)

**Camera**
1. All audited rooms — **no furniture clipping**, all boxes in-frame (0.42%–1.55% of frame). Evidence: Phase 2H-2 captures.
2. `bedroom-1` — AI output **recomposed furniture positions** (model behavior, not the camera); camera solver unchanged, no clipping. Evidence: `output_with_base_boxes.png`.

## 6. Confirmed vs ambiguous/unauditable
- **Confirmed:** base has all 5 identifiable; pair is same-attempt (provenance PASS); output has 4 distinct objects (≥1 side table not identifiable); bed/wardrobe/dressing identity preserved; dressing preserved with mirror this run; positions strongly recomposed.
- **Ambiguous/unauditable:** which specific side-table uid is lost/merged/repositioned; exact 3D pose of any item; all non-Bedroom-1 rooms (no verified pair); the FAL mechanism.

## 7. Minimal proposed fixes — RECOMMENDATIONS ONLY (await approval)
1. **Structured conditioning experiment** (depth/canny via the existing `FAL_USE_CONTROLNET` path) to give the model a geometric lock — a *separate approved* experiment, not a prompt/param change to the current path.
2. **Seed-variance study** — 2–3 linked single-room FAL calls on the persisted base, varying only the seed, to quantify per-item preservation and recomposition frequency (needs FAL approval).
3. **Persist base PNG sha256 in production generation metadata** (`render_debug.json` currently records `geometry_hash`/`prompt_hash` but no base image sha) so future pairs are auditable without re-capture.

## 8. Tests/validation available & results
- `render_input_contract` (Phase 2J): input integrity + provenance — **18 tests pass**; live BR1 = furniture PASS, provenance PASS, openings UNCERTAIN (3 NEEDS_REVIEW). This validates **inputs/provenance only — not AI-output preservation**.
- The pair hashes re-verified on disk (base/output match recorded metadata).

## 9. Confirmation
Production code, canonical furniture/geometry, AI model/prompt/seed/parameters/thresholds, `render_input_contract.py`, and FAL usage were **unchanged**. **No FAL calls.** No furniture/opening/camera/wall/room modifications. This is an evidence-backed diagnosis — the furniture issue is **not** claimed fixed.
