# AI Render — Latest Output Investigation (`Latest_Main_2.0.zip`)

*Investigation and report only. No code changed, no AI images generated, no paid API calls. The archive and all files were preserved; screenshots were extracted to an isolated scratch directory.*

---

## 1. Executive summary
`Latest_Main_2.0.zip` contains **only 4 UI screenshots** (no code, canonical snapshots, prompts, logs, base-render files, or generation metadata). From the visible UI badges + direct visual inspection of the four 2D‑plan↔AI‑render pairs (one design: project `dc6773e1…`, floor `1528a0b1…`, "MR.MATHUR", **not** the v79 design):

- The pipeline is the **fal · `fal-ai/flux-kontext/dev` image‑EDIT path** ("AI base path: image‑to‑image"). **No structural conditioning.**
- The system is **honest**: every output is labelled **AI furniture fidelity: Not Verified**, **AI geometry: NOT PROVEN**, and **Kitchen + Dining Area FAILED** to render ("Incomplete Generation: 4 of 6") — the inventory gate correctly blocking the sections whose deterministic base is inventory‑incomplete.
- The AI renders are **photorealistic and attractive** but **do not reliably preserve the canonical inventory**: they add decor/accessories in every room, add real **furniture/appliances** in Bedroom 2 (TV, ottoman, sofa, coffee table) and reinterpret its composition, and Living Area adds a pouf + coffee table.
- **Root cause (VERIFIED by source): the existing prompts are already strong** (explicit "render every one of these items and nothing else — no extra, duplicate, missing, or invented furniture", full structural‑preservation preamble, negatives last, theme can't override). The hallucination therefore is **not primarily prompt‑related** — it is the **edit model ignoring textual constraints without structural image conditioning** (Canny/depth), exactly the Step‑2R finding. **Prompt tweaks will not fix geometry; structural conditioning (a separate, provider/config change) is required.**

**Scope caveat:** conclusions rest on **one design's four screenshots** and their on‑screen badges. No embedded generation metadata/hashes were present in the archive, so AI‑output→base‑render pairing is **UI‑reported, not provenance‑verified**. This does not establish production‑wide accuracy.

## 2. Archive inventory and inspection scope
`Latest_Main_2.0.zip` (6,729,554 bytes) — opened with `unzip`, integrity OK, **4 files**:

| file | sha256 (16) | dims | bytes |
|---|---|---|---|
| `Screenshot (1712).png` | `d6aa5389b8d94518` | 3200×2000 | 1,916,110 |
| `Screenshot (1713).png` | `398f467e92192487` | 3200×2000 | 2,009,790 |
| `Screenshot (1714).png` | `082ccc1287d3f8d3` | 3200×2000 | 1,978,360 |
| `Screenshot (1715).png` | `abf6333bb6ddfe94` | 3200×2000 | 976,923 |

Extracted to an isolated scratch dir (archive untouched). **No** code, README, canonical JSON, prompt templates, config, logs, base‑render PNGs, or generation metadata are in the archive — those were cross‑referenced from the live repository source (`backend/app/services/ai/fal_flux_adapter.py`, `prompt_service.py`, `generation_service.py`, `validation_service.py`).

## 3. Evidence and artifact mapping
Each screenshot is the **"AI Render — Photorealistic Visualization"** modal showing a **2D floor plan (left)** vs **photorealistic render (right)** for one section. Shared header badges (identical across all four):
`Provider: fal · fal-ai/flux-kontext/dev · Extraction: 179 walls · Topology: 5/7 rooms proven · Geometry: uncertain · Deterministic furniture fidelity: 100% · AI furniture fidelity: Not Verified · AI geometry: NOT PROVEN · Incomplete Generation: 4 of 6 sections rendered. Failed sections: Kitchen, Dining Area.`

| screenshot | section | AI base path badge | render pane shows |
|---|---|---|---|
| 1712 | Living Area (1/4) | image‑to‑image **on faithful base** | photoreal living room |
| 1713 | Bedroom 1 (2/4) | image‑to‑image **(base not §L‑verified)** | photoreal bedroom |
| 1714 | Bedroom 2 (3/4) | image‑to‑image **(base not §L‑verified)** | photoreal room (reinterpreted) |
| 1715 | Bedroom 3 (4/4) | image‑to‑image **(base not §L‑verified)** | **deterministic 3D base massing** (not a photoreal output) |

**Pairing confidence:** the left/right panes are shown as a pair by the UI itself (same section tab). No generation ID, base‑render hash, or canonical version is printed in the screenshots, so the AI output cannot be independently tied to a specific base PNG/version from the archive — **AGENT‑REPORTED via UI, not provenance‑verified.** The design is project `dc6773e1-07f9-419f-9bb0-6fc4919bd9fa`, floor `1528a0b1-7eeb-414a-a0eb-d0c8a5950913` (from the browser URL).

## 4. Latest AI render versus deterministic baseline
- **Camera comparability:** the left pane is a **top‑down 2D plan**; the right pane is a **perspective interior**. Furniture **identity/count/added‑object** comparisons are defensible; exact **position/orientation** comparisons are **not** (different projections) and are marked UNVERIFIED unless blatant.
- **Suitability:** 1712/1713/1714 are suitable AI‑vs‑plan pairs. **1715 is not an AI‑vs‑plan fidelity pair** — its "render" pane is the bare deterministic 3D base (gray massing), so no photoreal AI output is available to assess there.
- The system distinguishes **deterministic furniture fidelity: 100%** (the base reproduces canonical) from **AI furniture fidelity: Not Verified** (the AI output is not checked) — the correct separation.

## 5. Furniture and object discrepancy table
"Added furniture/appliance" = a violation of the inventory contract; "added decor" = accessories (plants/art/vases/cushions) not in the furniture plan (softer — arguably styling, but still beyond "render … nothing else").

| section | canonical (from 2D plan) | render — preserved | render — ADDED | render — changed/missing | confidence |
|---|---|---|---|---|---|
| Living Area (1712) | sectional sofa, console/sideboard, armchair (+ wall TV unit likely) | sectional sofa, console, armchair, TV | **pouf, round coffee table** (furniture); potted plant, floor vase/pampas, framed art, rug (decor) | none clearly missing | ADDED furniture **VERIFIED**; decor **VERIFIED**; positions **UNVERIFIED** |
| Bedroom 1 (1713) | bed, 2 side‑tables+lamps, dressing table, 2 wardrobes | bed, 2 nightstands+lamps, dressing table+chair, wardrobes | framed art, decorative wall medallion, small round side table, cup (decor/minor) | none clearly missing | preserved **VERIFIED**; added decor **VERIFIED** |
| Bedroom 2 (1714) | double bed (centered), 2 side‑tables, wardrobe, dressing table | wardrobe; a bed | **TV, large ottoman/bench, sofa, coffee table** (furniture) | bed appears **single & moved to wall** (double→single); composition reinterpreted | added furniture **VERIFIED**; bed change **INFERRED** (camera could contribute); side‑tables/dressing **not_assessable** |
| Bedroom 3 (1715) | double bed, 2 side‑tables, wardrobe | (base shows wardrobe + a small desk) | — | bed + side‑tables **not visible** in the base view | **not_assessable** — pane is the deterministic base, not an AI output; absence likely camera/framing or a base‑inventory gap |

**Pattern (VERIFIED):** additions scale with base trust — Living Area (**faithful base**) keeps the furniture and only adds decor + 2 soft furniture pieces; the three bedrooms (**base not §L‑verified**) drift more, with Bedroom 2 the worst. Less input geometry lock → more model freedom → more hallucination.

## 6. Architectural fidelity assessment
- Walls/room shell: the renders present plausible single rooms; **wall count/true proportions cannot be verified** from a perspective crop vs a top‑down plan (UNVERIFIED). Header says **Geometry: uncertain / Topology 5/7 rooms proven / AI geometry: NOT PROVEN** — the system does not assert architectural preservation.
- Doors/windows: renders show windows and a doorway (e.g., 1713 doorway, 1714 door + 2 windows) broadly consistent with plan openings, but exact placement is **UNVERIFIED** (perspective).
- **Conclusion:** no *confirmed* architectural violation from these crops, but none *proven* either — correctly labelled NOT PROVEN.

## 7. Photorealism assessment (separate from fidelity)
- **Materials/textures:** high — walnut cabinetry, boucle/linen upholstery, stone/quartz tops, oak flooring read convincingly (1712/1713/1714).
- **Lighting/shadows/reflections:** natural, soft, plausible; good ambient occlusion and contact shadows.
- **Depth/perspective:** coherent single‑point interiors; no obvious fisheye.
- **Artifacts:** minor; no gross distortion/oversaturation observed.
- **Verdict:** the AI output is a **clear photorealism improvement** over the deterministic base — **but a more attractive image is not higher fidelity.** 1715 (base massing) has no photoreal quality to assess.

## 8. Current prompt and conditioning pipeline (VERIFIED from source)
- **Prompt assembly:** `backend/app/services/ai/fal_flux_adapter.py::_build_fal_edit_prompt`. A single **combined** prompt (fal `flux-kontext/dev` has **no separate system‑prompt field**). Order: `_FAL_AUTHORITY` → `ROOM:` → **`EXACT EXISTING INVENTORY (render every one of these items and nothing else - no extra, duplicate, missing, or invented furniture)`** → `_EDIT_PREAMBLE` (structural preservation + allowed visual changes) → optional **theme** (styling‑only, *replaces* the house style) → `_FAL_NEGATIVES` (**last**, overriding).
- **Truncation (handled well):** mandatory sections are **reserved first and never truncated**; only the theme is trimmed to the remaining budget (`max_len=2200`); if the mandatory text alone exceeds the limit it **fails safely** (`FAL_PROMPT_TOO_LONG`) rather than drop a constraint.
- **Reference image:** the deterministic base render, sent as `image_url` — an **image‑EDIT** op, **not** structural conditioning.
- **Structural conditioning enabled?** **No.** `config.FAL_USE_CONTROLNET=false` (default) → `fal_flux_adapter.generate` takes the edit path (`conditioning_mode="edit"`). The Canny Control‑LoRA structural path (`_build_control_body` → `control_lora_image_url`, model `fal-ai/flux-control-lora-canny`) exists but is **off**.
- **Provider/model match:** runtime request = `fal` / `fal-ai/flux-kontext/dev` (matches config + the UI badge).
- **Version/room binding:** the base render is bound to `design_version_id` + room in `base_render_meta` (verified in prior steps) — the selected base belongs to the same canonical design/room.
- **Output validation:** **input‑based only** — `validation_service.assess_ai_render(output_verified=False)` → `geometry_status=UNVERIFIED` (never FAITHFUL). No output‑level furniture detector runs; the UI's "Not Verified / NOT PROVEN" reflects this honestly. (Step 2R added a guard so an edit‑path render can never be reported geometry‑FAITHFUL, plus `conditioning_mode` in provenance.)

## 9. Root‑cause analysis with confidence labels
| # | observation | evidence | confidence | stage | category | smallest corrective action | how to validate |
|---|---|---|---|---|---|---|---|
| R1 | AI output adds furniture/appliances & decor not in canonical (esp. Bedroom 2; all rooms add decor) | screenshots 1712/1714 | **VERIFIED** (added objects); bed change INFERRED | provider/model + conditioning | **model + conditioning‑related** (not prompt) | enable **structural conditioning** (Canny/depth ControlNet) — provider/config change | A/B benchmark edit vs canny on one room |
| R2 | Strong preservation prompt already present, yet ignored | `fal_flux_adapter.py` `_EDIT_PREAMBLE/_FAL_AUTHORITY/_FAL_NEGATIVES/EXACT INVENTORY` | **VERIFIED** | prompt builder | **not prompt‑related** (prompt is adequate) | no prompt change can *guarantee* geometry; refine only for marginal gains | compare furniture‑add rate before/after a prompt refinement (needs generations) |
| R3 | Fidelity worse where "base not §L‑verified" (bedrooms) vs "faithful base" (living) | per‑section badges + visuals | **VERIFIED** (correlation) | scene/base verification | input‑related | improve wall topology so more rooms are §L‑verified (geometry pipeline) | re‑render after more rooms proven |
| R4 | Kitchen + Dining Area did not render | "Incomplete Generation" badge | **VERIFIED** | inventory gate | validation (working as intended) | none — honest block; the render‑inclusion fix (separate work) addresses the Kitchen base | gate flips to MATCH when base is inventory‑complete |
| R5 | Bedroom 3 pane shows deterministic base, not a photoreal output | screenshot 1715 | **VERIFIED** | result display / generation | indeterminate (failed AI output → base fallback, or capture of base) | confirm whether the AI output for that room failed or the UI fell back | inspect that generation's provenance/logs |
| R6 | No output‑level fidelity check; status is input‑based | `assess_ai_render(output_verified=False)` | **VERIFIED** | output validation | validation‑related | add a calibrated output furniture detector (separate, blocked on corpus) | measured precision/recall on labelled outputs |

**Not attributable to prompting alone:** the inventory/structural instructions are explicit and survive truncation; the edit model simply does not obey them without structural conditioning.

## 10. Recommended structural‑preservation system prompt (Prompt A)
*Reusable, combined‑prompt system block. At least as strong as the current `_EDIT_PREAMBLE`+`_FAL_NEGATIVES`, tightened to also forbid invented **decor/accessories** (observed as the main residual add on faithful bases). Note: this is a refinement — it cannot by itself guarantee geometry on an edit model without structural conditioning.*

```
This is a photorealistic image-to-image EDIT. The provided image (the deterministic
base render of the canonical design) is the SINGLE AUTHORITATIVE SOURCE OF TRUTH for
geometry, layout and contents. Reproduce it EXACTLY; treat every pixel of structure
and every object as fixed.

PRESERVE, without any change:
- room geometry: every wall, door, window, opening, room boundary and proportion;
- the camera: same viewpoint, framing, focal length and crop — do not zoom, pan, re-angle,
  or crop out any object;
- every furniture object's identity, type, count, position, rotation, dimensions and
  room assignment, exactly as shown.

DO NOT, under any circumstances:
- add, remove, duplicate, replace, move, resize, rotate or re-arrange any wall, door,
  window, opening, room or furniture object;
- invent anything not visible in the image — no extra furniture, appliances, cabinets,
  shelving, rugs, lighting fixtures, plants, art, mirrors, cushions, curtains, or other
  decor/accessories;
- "complete", "stage", "furnish" or "improve" the room by adding typical items;
- change the number or placement of objects to make a more appealing composition.

YOU MAY ONLY change surface appearance: materials, textures, colours, finishes,
lighting, shadows, reflections, ambient occlusion and surface realism — applied to the
objects and surfaces already present, in place.

The canonical design and this base render OVERRIDE any stylistic preference. If a style
instruction would require adding, removing or moving anything, IGNORE that part of the
style and keep the structure and inventory exact. The output must be structurally,
spatially and inventory-identical to the input, same objects in the same places from the
same camera — only more photorealistic.
```

## 11. Recommended photorealistic theme prompt (Prompt B)
*Reusable default for premium contemporary interiors. Styling‑only; must not add objects/materials absent from the source. Drops in where the current `_FAL_STYLE` is used; the user's own theme still replaces it when provided.*

```
STYLE (styling only — apply to the materials, colours, textures, finishes, lighting and
mood of the objects and surfaces ALREADY present; never add, remove, move, resize, rotate
or re-type any furniture, wall, door, window or decor):

Premium contemporary residential interior. Physically plausible, high-end materials used
only where appropriate to the existing objects: natural walnut/oak wood with visible grain,
honed natural stone or quartz surfaces, brushed or matte metal accents, clear glass, and
soft boucle/linen/wool upholstery. Balanced lighting — soft natural daylight from existing
windows plus warm ~3000K ambient artificial light; realistic soft shadows, subtle
reflections and accurate surface roughness. Architectural-digest-quality interior
photography: clean, calm, well-exposed, true-to-life colour, fine material detail, no CGI
or plastic look, no fisheye, no dark unlit areas, no generic showroom staging.

Preserve the original camera, composition, furniture and architecture exactly; this style
affects appearance only and must never override the structural-preservation rules.
```

## 12. Minimal implementation recommendations (no change made)
Separated into **prompt‑only** (marginal) and **conditioning/capability** (the real fix).

**Prompt‑only (low effort, marginal gain; files verified):**
1. In `fal_flux_adapter.py`, extend the prohibition in `_EDIT_PREAMBLE`/`_FAL_NEGATIVES` to explicitly include **decor/accessories** (plants, art, rugs, cushions, curtains, mirrors), not only "furniture" — targets the observed residual additions on faithful bases (R1 on Living/Bedroom 1). *Expected effect: small; will not stop a non‑structural edit model from drifting.*
2. Persist the **final effective fal edit prompt** (post‑assembly/trim) per render alongside the existing room `prompt.txt`, so the exact text sent is auditable. *(Prompt hash already recorded; full effective text is not.)*
3. (Already done in Step 2R) record `conditioning_mode` in provenance and forbid geometry‑FAITHFUL without structural conditioning.

**Conditioning / capability (the actual fix — NOT prompt, NOT in scope here):**
4. Enable **structural conditioning** (Canny/depth ControlNet): `FAL_USE_CONTROLNET=true` → `fal-ai/flux-control-lora-canny` with the base as `control_lora_image_url`. This is a **production‑config + provider‑capability change requiring a paid A/B validation** (and fal entitlement) — a **product decision**, out of this investigation's scope.
5. Improve wall‑topology reconstruction so more rooms become §L‑verified (R3) — the faithful‑base rooms drift least.
6. Add an **output‑level furniture detector** to ever reach a true FAITHFUL status (R6) — blocked on a labelled‑output calibration corpus.

Centralization/versioning, structural‑vs‑theme separation, version‑bound base, theme‑can't‑override, and effective‑metadata recording are **already implemented** (§8) — no defect found there.

## 13. Validation checklist and acceptance criteria
- [x] Archive opened; 4 files enumerated with sizes + sha256.
- [x] Image dimensions compared (all 3200×2000 UI captures).
- [x] Images visually inspected (not filenames/logs alone).
- [x] Structural fidelity, photorealism and provenance kept as **separate** assessments.
- [x] Perspective‑vs‑plan limits respected; uncertain cases marked UNVERIFIED/not_assessable.
- [x] No render marked FAITHFUL (none has output‑level evidence).
- [ ] AI‑output→base‑render→canonical‑version mapping by embedded metadata — **not possible** from this archive (no metadata/hashes inside).
- **Acceptance for a real fix (future, authorized):** on a controlled A/B (edit vs Canny) for one room, the Canny output shows **zero added furniture/appliances** and preserved count vs the base, judged on the actual images.

## 14. Unresolved questions, risks, missing evidence
- **Single design, 4 UI screenshots** → conclusions are **illustrative, not production‑wide**.
- **No embedded provenance** in the archive (no generation IDs, base‑render hashes, prompts, or canonical versions) → AI↔base pairing is UI‑reported only.
- **Bedroom 2 bed "double→single/moved"** is **INFERRED** — camera/framing could contribute; cannot be proven from a perspective crop.
- **Bedroom 3** pane is the deterministic base, not an AI output → whether that room's AI render failed or the UI fell back is **indeterminate** without that generation's logs.
- Architectural (wall/opening) preservation is **NOT PROVEN** (not necessarily violated) — perspective limits.

## 15. Prioritized next steps
1. **(Product decision, authorized)** Run ONE Canny‑conditioned A/B vs the current edit path on a faithful‑base room (e.g. Living Area); compare furniture additions on the actual images. *This, not prompting, is the lever.*
2. **(Prompt‑only, low risk)** Tighten the preservation prompt to forbid invented **decor/accessories** and persist the effective fal prompt per render.
3. **(Geometry)** Increase §L‑verified room coverage so fewer renders run on an unverified base.
4. **(Validation)** Scope a calibrated output furniture detector to enable a real FAITHFUL status.
5. Re‑inspect Kitchen/Dining once the render‑inclusion fix is applied (their failure here is the honest gate, not an AI defect).

---
*Report created at `AI_RENDER_LATEST_OUTPUT_INVESTIGATION.md`. Files inspected: the 4 PNGs above (visually) + repository sources `fal_flux_adapter.py`, `config.py`, `prompt_service.py`, `generation_service.py`, `validation_service.py`. No paid calls, no image generation, no code/data/Git changes.*
