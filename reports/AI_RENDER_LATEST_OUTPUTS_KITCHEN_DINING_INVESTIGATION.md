# AI Render — Latest Outputs & Kitchen/Dining Failure Investigation

## 1. Executive summary
`main_zip_222.zip` (today's newest zip) contains **4 full-screen UI screenshots only** — no render files, manifests, prompts, logs, or provenance. The screenshots capture the MyNest **AI Render** modal for design version **`85759b78` (v79)**, provider **fal/flux-kontext/dev (image-to-image edit path)**, with the banner **"Incomplete Generation: 4 of 6 sections rendered successfully. Failed sections: Kitchen, Dining Area."**

Cross-referencing the backend, the screenshots match generation **`803af570-e2b2-47c7-85c0-c1c71002b06e`** (created 17:40; screenshots 17:41). Its on-disk debug artifacts contain **only rooms 0/3/4/5** (Living Area, Bedroom 1/2/3) — **Kitchen (index 1) and Dining Area (index 2) have no folder, no base render, and no image.** → **CONFIRMED:** Kitchen and Dining were **refused by a deterministic gate BEFORE any FAL call** (`_render_room` never ran). This is a **failed generation request, not an unfaithful image**, and the deterministic design remained the trusted fallback (as designed). The 4 rendered rooms are all **edit path, `UNVERIFIED`** (AI furniture fidelity "Not Verified", AI geometry "NOT PROVEN"); **Bedroom 2's render is flat/clay (low-fidelity)**.

**One confirmed code gap was fixed:** pre-provider section refusals left **no provenance on disk** (which is exactly what blocked recovering the Kitchen/Dining reason) — now they persist a `failed` breadcrumb (additive, best-effort, no behavior change). **No AI generation was performed.**

## 2. Scope & archive identity
- **Archive:** `D:/Latest_mynest_design_version/mynest-design-studio/main_zip_222.zip` · sha256(16) `dab8af499d6cda6d` · 7,147,129 bytes · mtime 2026-10-27 17:44 · **4 entries, all PNG screenshots** · no nested archives · no path-traversal/absolute entries (safe).
- **Extracted to:** `reports/ai_render_investigation/latest_outputs/raw_extract/` (originals preserved).
- **Missing vs expected:** no JSON metadata, prompts, manifests, logs, validation results, base renders, or canonical designs are in the archive.

## 3. Artifact inventory & output folder
**Folder:** `reports/ai_render_investigation/latest_outputs/` → `raw_extract/` (originals), `successful/` (renamed copies), `failed/kitchen|dining/` (+`FAILURE_NOTE.md`), `metadata/` (`artifact_inventory.json` + the matched generation's real on-disk provenance). Full machine-readable inventory: `metadata/artifact_inventory.json`.

| Screenshot | sha256(16) | Depicts | Class |
|---|---|---|---|
| (1720) → `successful/01_living_area.png` | `39923bef44538413` | Living Area photoreal render + 2D plan; failure banner | UI_SCREENSHOT |
| (1721) → `successful/02_bedroom_1.png` | `39ed5d39424f48c9` | Bedroom 1 photoreal; chip "base not §L-verified" | UI_SCREENSHOT |
| (1722) → `successful/03_bedroom_2_FLAT_lowfidelity.png` | `cc40fe3ba7015d6b` | Bedroom 2 — **flat/clay, not photorealistic** | UI_SCREENSHOT |
| (1723) → `successful/04_bedroom_3.png` | `2773af61af42ce91` | Bedroom 3 photoreal | UI_SCREENSHOT |

All four are **UI captures, not raw per-room render files** — classified by provenance, not assumed to be AI outputs.

## 4. "Latest" selection method
By **timestamp + provenance**, not filenames: the archive is the newest zip (17:44); screenshot capture times 17:41:42–48 bracket backend generation `803af570` (17:40) for design version `85759b78`; the UI content (sections, provider, banner) matches that generation. Linkage confidence: **LIKELY** (time + version align; not DB-confirmed by generation id, which the screenshots don't show).

## 5. Kitchen failure analysis
- **Expected:** a Kitchen section render (it was among the 6 requested).
- **Observed:** **no image, no base render, no debug folder** (index 1 absent). Refused **pre-provider**. `[CONFIRMED` from disk].
- **Exact gate code:** **UNKNOWN from available evidence** — pre-provider refusals wrote no breadcrumb for this run, and the screenshots don't expand "Debug Info". `[UNKNOWN]`
- **Root cause (LIKELY):** the chips show **Topology 5/7 rooms proven · Geometry uncertain** → 2 of 7 reconstructed rooms were not wall-proven; Kitchen being one is consistent with its architecture not verifying, so **no valid deterministic base render was available** to condition the edit → the §L/base-render gate refuses it. This matches the documented v79 **Kitchen-reconstruction ambiguity** from prior cycles [INHERITED]. `[LIKELY]`
- **Impact:** architectural-coverage limitation; furniture fidelity N/A (nothing rendered). **Reproducible offline:** partially (the absence is on disk; the exact code needs the generation's `room_errors` or the Debug Info panel).

## 6. Dining Area failure analysis
- **Expected:** a Dining Area section render.
- **Observed:** identical pattern — **no image/base/folder** (index 2 absent); refused pre-provider. `[CONFIRMED]`
- **Exact gate code:** **UNKNOWN from available evidence** (same breadcrumb gap). `[UNKNOWN]`
- **Root cause (LIKELY, investigated independently):** Dining is the classic **open-plan membership** case — a dining zone that must be assigned to Kitchen/Living (AIR-03) or whose boundary isn't independently wall-proven; either leaves no valid standalone Dining base and refuses the section. Also consistent with "2 of 7 rooms unproven". `[LIKELY]` — **not assumed identical to Kitchen's cause**; both resolve to "no valid deterministic base for that section", but via potentially different gates (Kitchen=reconstruction ambiguity, Dining=membership/open-plan).
- **Impact & reproducibility:** as Kitchen.

## 7. Comparison with successful rooms
| Room | Rendered | Path | Status (disk) | Inventory gate | Photorealism (visual) | Contract |
|---|---|---|---|---|---|---|
| Living Area | yes | edit | `UNVERIFIED` | MATCH | photorealistic | CONTRACT_VALID, output UNVERIFIED |
| Bedroom 1 | yes | edit | `UNVERIFIED` | MATCH | photorealistic | CONTRACT_VALID, output UNVERIFIED |
| Bedroom 2 | yes | edit | `UNVERIFIED` | MATCH | **flat/clay (low-fidelity)** | CONTRACT_VALID, output UNVERIFIED |
| Bedroom 3 | yes | edit | `UNVERIFIED` | MATCH | photorealistic | CONTRACT_VALID, output UNVERIFIED |
| **Kitchen** | **no** | — | **FAILED_PRE_PROVIDER** | n/a | n/a | refused (no base) |
| **Dining Area** | **no** | **—** | **FAILED_PRE_PROVIDER** | n/a | n/a | refused (no base) |
**The decisive difference (evidence-backed):** the 4 successful rooms each had a **valid deterministic base render** (`used_base_render: true`, `inventory_status: MATCH`); Kitchen/Dining had **none captured**. **`CONTRACT_VALID` (input gates) is explicitly NOT output-level fidelity evidence** — all 4 outputs are `UNVERIFIED`.

## 8. Furniture inventory & geometry findings
- **Deterministic furniture fidelity 100%** is an **INPUT-side** metric (canonical→scene), **not** proof the AI image preserved furniture. [CONFIRMED from UI + the honest reporting contract.]
- **Possible EXTRA furniture in the photoreal rooms** (Living Area: a row of ~3–4 armchairs; Bedrooms 1/3: wardrobe/desk/chair/TV/clock not obviously in the 2D plan). These are **HYPOTHESIS** only — visual impression without a calibrated detector; the AI furniture fidelity is honestly "Not Verified". No measurement is asserted.
- **Bedroom 2 flat/clay output** is **CONFIRMED visually** (screenshot 1722) — a low-fidelity/near-base restyle, consistent with the known edit-path realism variance.

## 9. Provider, prompt, conditioning & provenance findings
- **Provider/model/path [CONFIRMED]:** fal · `fal-ai/flux-kontext/dev` · image-to-image **edit** (`FAL_USE_CONTROLNET=false`) — no structural geometry lock (matches the current runtime verified earlier this session).
- **Effective prompt:** not archived; not recoverable for the failed sections (no request was made). For the rendered rooms, `effective_prompt` is captured in their on-disk provenance (copied under `metadata/`).
- **Provenance gap [CONFIRMED DEFECT]:** a section refused before the provider call left **no on-disk artifact**, so the failure reason was unrecoverable post-hoc — the root cause of why this investigation could not name the exact gate code.

## 10. Confirmed root causes vs hypotheses
| ID | Finding | Confidence |
|---|---|---|
| K/D-1 | Kitchen & Dining refused **pre-provider** (no artifact/base/image; indices 1,2 absent) | **CONFIRMED** |
| K/D-2 | Failure = **generation-gate refusal**, not an unfaithful image; deterministic fallback preserved | **CONFIRMED** |
| K/D-3 | Pre-provider refusals persisted **no failure provenance** (observability defect) | **CONFIRMED** (fixed) |
| K/D-4 | Cause = no valid **deterministic base** for Kitchen/Dining (architecture not wall-proven: "5/7 proven") | **LIKELY** |
| K/D-5 | Kitchen = reconstruction ambiguity; Dining = open-plan/membership — distinct gates | **HYPOTHESIS** |
| OUT-1 | Bedroom 2 output is flat/low-fidelity | **CONFIRMED** (visual) |
| OUT-2 | Extra furniture in Living/Bed1/Bed3 photoreal outputs | **HYPOTHESIS** (no calibrated detector) |
| OUT-3 | All 4 outputs `UNVERIFIED`; deterministic 100% is input-side only | **CONFIRMED** |

## 11. Files changed & why
- **`backend/app/services/generation_service.py`** — added `_save_refused_section_artifact` (module-level) and a pre-dispatch loop in `generate()` that writes a `failed` provenance breadcrumb (code + reason) for every section refused before a provider call (2D→3D hard refusal or per-section base/membership/inventory gate). **Reason:** the confirmed observability gap (K/D-3). Additive, best-effort, never raises; **no generation/gate behavior change**; writes nothing a real render would overwrite.
- **`backend/tests/test_refused_section_provenance.py`** — new; asserts the breadcrumb records status/code/reason and is crash-safe.
- **`reports/ai_render_investigation/…`** — organized outputs + `artifact_inventory.json` + `FAILURE_NOTE.md` + this report. No canonical/provider/default change.

## 12. Regression tests & exact results
Offline; no OWLv2/weights, no provider/network/paid calls, no DB writes.
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q tests/test_refused_section_provenance.py
→ 2 passed   (exit 0)

# broad 23-file offline regression (incl. the new provenance test):
→ 346 passed (exit 0; only pre-existing Pillow `getdata` deprecation warnings — not new)
```
Prior cycle was 344; +2 new → 346. No assertion weakened; no paid generation invoked.

## 13. Remaining uncertainties & blockers
- **Exact Kitchen/Dining gate code** is not in the archive or on disk for this historical run (the breadcrumb fix applies to *future* runs). To name it now requires the generation's `room_errors` (API/DB, read-only) or re-running the design and expanding the UI "Debug Info" panel.
- **Output-level furniture fidelity** (the extra-furniture hypotheses, Bedroom 2 flatness) cannot be verified without a calibrated detector and/or human review of actual outputs.

## 14. Next actions (prioritized by impact)
1. **Re-run the same design** (`85759b78`) and read the new on-disk `failed` breadcrumb (or expand Debug Info) to obtain the **exact** Kitchen/Dining gate code — now cheap and offline-traceable. *(No code change needed; the fix landed this cycle.)*
2. If the cause is unproven architecture, address it in the **deterministic reconstruction** (Kitchen out-of-polygon / open-plan Dining membership) — a geometry/data fix, not an AI-render fix; prior cycles scoped this (Steps 2K/2M/2N, AIR-03).
3. For output fidelity, run the prepared **paired benchmark** (authorization required) and/or calibrate the detector with labeled outputs.

## 15. Is another AI generation required to verify a correction?
- **To confirm the exact gate code:** one **non-paid** re-run of the deterministic path would surface it (the gates run before any FAL call); no paid generation is strictly required to read the gate reason.
- **To verify output-level fidelity / the extra-furniture hypotheses / Bedroom 2 flatness:** **yes — an authorized paid AI generation is required** (the §8 benchmark). None was performed here.

---
**Honest conclusion:** the latest outputs are organized and traced; Kitchen/Dining failures are **confirmed as pre-provider gate refusals** (exact code pending the now-added provenance or a re-run); one real observability defect was fixed and regression-tested; and **missing/extra furniture is NOT declared resolved** — that needs output-level evidence from an authorized run. **No AI generation was performed in this investigation.**
