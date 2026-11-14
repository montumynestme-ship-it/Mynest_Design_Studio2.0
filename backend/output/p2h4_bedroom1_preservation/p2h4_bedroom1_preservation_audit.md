# Phase 2H-4 — Persisted Base-vs-AI Furniture Preservation (Bedroom 1)

**Floor plan:** `f6b65d2b-4f96-4931-9f08-67dbd09776f6` · **design_version_id (at capture):** `1831bf84-f9d6-4d4f-aedc-4ad95d6145fe` · **room:** `bedroom-1`.

## 1. Source snapshot & inputs (verified before generating)
- BR1 live source confirmed to contain the **5 expected UIDs**: bed `…1845`, side-table `…7384`, side-table `…6014`, wardrobe `…2167`, dressing-table `…2783`.
- Base is the **actual deterministic render** (RoomScene3D `aiRenderMode`, same component as production `BaseRenderBatch`, from live `/scene`) — **not** a screenshot/fixture/stale cache.
- Model/params recorded from production config (not altered): `fal-ai/flux-kontext/dev`, edit/img2img, controlnet off, random per-generation seed policy.

## 2. Hashes
- **Base** `base_render.png`: SHA-256 `04ea7854…`, 1216×832. Submitted to FAL = pixel-identical re-encode, SHA-256 `9e670a46…` (bytes differ, pixels identical — production `_to_png`).
- **AI output** `ai_output.png`: SHA-256 `b6c9580e…`, 1216×832.

## 3. FAL generation metadata
- **Request ID:** `01a133ca-ae45-70b2-a3ed-95dcf5a04daa` · **HTTP 200** · model `fal-ai/flux-kontext/dev` (edit).
- **Seed:** 1558158484 (returned = submitted). **Prompt SHA-256:** `7fe63b11…` (11040 chars, production builder). Elapsed 11.2 s. **One** FAL call (approved).
- **base→output mean abs diff: 15.47** — a *strong* restyle; the room was **recomposed** (furniture not at base screen positions).

## 4. Five-item preservation table (identity/presence only — no 3D position claimed)
| UID | type | base | AI output | status | conf |
|---|---|---|---|---|---|
| bed `…1845` | bed | visible (frame/mattress/pillows/headboard) | visible as a bed | **PRESERVED** | HIGH |
| wardrobe `…2167` | wardrobe | visible 2-door cabinet | visible 2-door wardrobe | **PRESERVED** | HIGH |
| dressing-table `…2783` | dressing | visible as 3-drawer chest (`dresser` mesh) | visible as a **table + 2 drawers + wall mirror** = dressing table | **PRESERVED** | MED-HIGH |
| side-table `…7384` | side_table | visible (top+legs) near bed head | no distinct side table bindable to this uid | **AMBIGUOUS** | LOW |
| side-table `…6014` | side_table | visible (top+legs) front-left | a **bench** appears front-left (altered side table vs added bench unresolved) | **AMBIGUOUS** | LOW |

**Count:** 5 canonical → **4 distinct output objects** (bed, wardrobe, dressing-table, one bench) ⇒ **at least one of the two side tables is not preserved as a distinct identifiable object.** No duplicates. **Decor:** none non-canonical this run (the mirror is the canonical dressing-table feature; bed pillows are canonical; no lamp/plant unlike Phase 2C).

## 5. First proven divergence (per stage)
`canonical → scene` **PASS** (2H-2 exact) → `scene → base render` **PASS** (all 5 identifiable) → `base → submitted FAL input` **PASS** (pixel-identical) → **`submitted → raw FAL output` DIVERGENCE (PROVEN)**.
- **First divergence stage: the FAL raw output (image-to-image).** The base contains 5 identifiable items; the raw output contains 4 distinct canonical objects (≥1 side table not preserved) and strongly **recomposed positions**.
- **Mechanism UNPROVEN** — a visual difference does not establish the internal model behaviour (drop vs merge vs reposition).

## 6. Confirmed facts vs hypotheses
**Confirmed:** base has all 5 identifiable items; submitted input pixel-identical to base; output preserves bed, wardrobe, dressing-table (table+mirror); output has only 4 distinct canonical objects (≥1 side table lost); positions strongly recomposed (diff 15.47).
**Hypotheses (not proven):** the front-left bench is a side-table-altered-to-bench (vs addition + missing side table); FAL preservation is **high-variance** across seed/prompt — Phase 2C (seed 1587969140) dropped a side table **and** made dressing→bench, while this run (seed 1558158484) preserved dressing-with-mirror but lost a side table and recomposed. One run is not conclusive per item.
**Evidence needed:** 2–3 more linked runs (vary only seed) to quantify per-item preservation variance; independent object-detection to count side tables.

## 7. Limitations & recommended next investigation
- Single FAL run, one seed → not a universal result; strong recomposition prevents per-uid binding of the two side tables from one image; image-space supports identity/presence only (no 3D).
- **Recommended (needs approval):** a small **seed-variance study** — 2–3 more single-room FAL calls on this exact persisted base/prompt, varying only the seed, to measure how often each canonical item is preserved. This would establish whether the side-table loss and the recomposition are systematic or seed-dependent. **No fix is implemented or proposed to production in this phase.**

## 8. Files changed
- **No production source edits.** New evidence artifacts under `backend/output/p2h4_bedroom1_preservation/`: `base_render.png`, `base_render_metadata.json`, `canonical_furniture.json`, `production_prompt.txt`, `prompt_hash.txt`, `generation_parameters.json`, `manifest.json`, `ai_output.png`, `ai_output_metadata.json`, `p2h4_bedroom1_preservation_audit.{json,md}`, and per-item comparison crops.

## Confirmation
One approved FAL call made. No changes to canonical data/identity/coordinates/dimensions/rotations/room assignments, wall/room geometry, door/window logic, camera/FOV/solver/cutaway classifier/`computeMpp`, production prompts/model defaults/parameters/thresholds, the AI-render pipeline, or production UI. No fix implemented. Furniture preservation is **not** claimed fixed; the evidence shows a proven FAL-output divergence (≥1 side table + positions) with an unproven mechanism.
