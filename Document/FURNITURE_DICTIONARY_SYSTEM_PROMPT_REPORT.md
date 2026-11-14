# JSON Furniture Dictionary + Markdown System Prompt — Implementation & Integration

**One line:** Added a version-bound **JSON furniture dictionary** (Approach A) and a maintainable **Markdown system-prompt template** (Approach B), both **derived from the one authoritative manifest** — reusing the existing catalog, synonym map, and opening set, with **no competing inventory source** — and wired them into the generation **provenance** path. **334 offline tests pass. No paid generation; no provider/model/default change; the live provider request is unchanged.**

Creating the files was not the goal — this integrates and tests them. It does **not** claim missing/extra furniture is solved; that needs the §8 live benchmark with output-level evidence.

---

## 1. Root-cause / baseline findings (verified in source)
- The canonical, version-bound **manifest** already exists and already drives the prompt's inventory line (single source), gating, reconciliation, and provenance (prior cycles — [FURNITURE_MANIFEST_PRESERVATION_PIPELINE.md](FURNITURE_MANIFEST_PRESERVATION_PIPELINE.md), [FURNITURE_ASSESSMENT_HARDENING.md](FURNITURE_ASSESSMENT_HARDENING.md), [FURNITURE_MISSING_EXTRA_FIX_REPORT.md](FURNITURE_MISSING_EXTRA_FIX_REPORT.md)).
- **Authoritative terminology already exists in code:** display names/appearance in `app/data/furniture_catalog.py`; **detector synonyms** in `furniture_object_validation_service._TYPE_SYNONYMS` (the map the output matcher already uses); **openings** in `furniture_manifest._OPENING_IDS`. A second static rules/dictionary file would be a competing source that can drift — so I **did not** create `config/furniture_dictionary.json` / `config/furniture_detection_rules.json`. The dictionary is **built at runtime from the manifest + these code-owned sources** and emitted as JSON in provenance. (The directive permits this: "reuse existing files… adapt to the smallest compatible implementation instead of forcing a new architecture.")
- **Provider contract (verified):** the active FAL path (`fal-ai/flux-kontext/dev`, `FAL_USE_CONTROLNET=false`, from source + `backend/.env`) builds a **single combined `prompt`** (`_build_fal_edit_prompt`) — **no separate system-prompt field**. So Approach B's system prompt is **not** injected as a duplicate block into the live request (which already carries the manifest-derived inventory + `_EDIT_PREAMBLE` preservation); it is rendered, recorded as provenance, and usable where a provider exposes a system channel.

## 2. Approach A — JSON furniture dictionary (new `furniture_dictionary.py`)
- `build_dictionary(manifest)` — a serializable, version-bound view **derived** from one room manifest: `schema_version`/`dictionary_version`, `design_version_id`, `room_label`, `units`, `coordinate_system`, `manifest_fingerprint`, `expected_furniture_count`, `counts`, per-item `{uid, item_id, type, name, category, dimensions{w,h,units}, position{cx,cy}, rotation, is_opening}`, `synonyms` (reused from `_TYPE_SYNONYMS`, only for types present), `opening_item_ids` (reused from `_OPENING_IDS`), `preservation_constraints`, and a deterministic `dictionary_fingerprint`. Invents no canonical values; openings kept and flagged (explicit categorization).
- `validate_dictionary(dictionary, manifest=None)` → `{valid, issues}` with codes: `UNSUPPORTED_SCHEMA`, `DUPLICATE_UID`, `INVALID_TYPE`, `INVALID_DIMENSIONS`, `MISSING_UID`, `MISSING_VERSION`, `VERSION_MISMATCH`, `FINGERPRINT_MISMATCH`, `OPENING_MISCATEGORIZED`. Inspect-only.
- `normalize_label(label)` → canonical `item_id` or `None`, using the **authoritative** `_TYPE_SYNONYMS`. Returns `None` when unknown **or ambiguous** (matches >1 canonical type, e.g. `"cabinet"`), never merges distinct ids, never guesses an instance.

**Real sample (fixture: bed + 2 side-tables + window, version `v79`):**
```json
{ "schema_version": "mynest.furniture_dictionary/1.0", "dictionary_version": "1.0",
  "design_version_id": "v79", "room_label": "Bedroom 1", "units": "plan_units",
  "manifest_fingerprint": "d715bf0953877156", "expected_furniture_count": 3,
  "counts": {"Bed": 1, "Side Table": 2},
  "synonyms": {"bed": ["bed"], "side-table": ["side table","bedside","nightstand","night stand","end table"]},
  "opening_item_ids": ["bay-window-seat","door","window"], "dictionary_fingerprint": "416e1674073a8d81",
  "items": [{"uid":"b","item_id":"bed","type":"bed","name":"Bed","category":"furniture",
             "dimensions":{"w":1800.0,"h":2000.0,"units":"plan_units"},
             "position":{"cx":500.0,"cy":350.0},"rotation":0.0,"is_opening":false}, … ] }
```
`validate_dictionary` on this: `{"valid": true, "issues": []}`. `window` is `category:"opening"`, excluded from `counts`/`expected_furniture_count`.

## 3. Approach B — Markdown system prompt (new `app/prompts/furniture_preservation_system.md`)
Maintainable **static** rules (priority: 1 preserve canonical > 2 dictionary interpretation > 3 visual enhancement) + `{{PLACEHOLDERS}}` filled at runtime by `furniture_dictionary.render_system_prompt(dictionary)` from the room's **actual** expected inventory/openings/synonyms. The dynamic inventory is never hand-edited (edit the canonical design, not the file). Rendered artifact begins at `# SYSTEM — Canonical Furniture Preservation`, lists `1× Bed` / `2× Side Table`, states "do not add/duplicate/substitute", "no more, no fewer", and "Never prioritize photorealism over the canonical design contract."

## 4. Integration (one pipeline, one source)
- `generation_service._write_room_manifest` now calls `furniture_dictionary.build_for_room(manifest)` and persists `furniture_dictionary`, `dictionary_valid`, `dictionary_issues`, and `system_prompt_md` alongside the manifest in the render's provenance (`furniture_manifest.json`). Additive, best-effort (never blocks/alters a render).
- The dictionary, the prompt's inventory line, and the assessment all resolve from the **same** version-bound manifest → no independent lists. The live provider request is unchanged (no second instruction block, no prompt-budget bloat, no provider-contract change).
- `normalize_label` reuses the exact `_TYPE_SYNONYMS` the output matcher uses, so detector-label normalization and match-time identity share one synonym source (no drift). The matcher itself is unchanged (no regression risk).

## 5. Files changed
- **NEW** `backend/app/services/furniture_dictionary.py` — Approach A + Approach B renderer.
- **NEW** `backend/app/prompts/furniture_preservation_system.md` — Approach B template.
- **`backend/app/services/generation_service.py`** — persist dictionary + validation + system prompt in provenance (additive; `_write_room_manifest`).
- **NEW tests** `backend/tests/test_furniture_dictionary.py`.
No change to canonical data, provider defaults/contracts, coordinate systems, persistence formats, the matcher, or the Furniture Library.

## 6. Regression tests — exact commands & results
Offline; no OWLv2/weights, no provider/network/paid calls, no DB writes.
```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q tests/test_furniture_dictionary.py
→ 21 passed   (exit 0)   [reproduced this cycle]

# broad offline regression (22 files: dictionary, acceptance, manifest, prompt, assessment,
#   object/geometry/inventory validation, 2D→3D, base-render/img2img/output-geometry gates,
#   render-input contract, fal + nvidia adapters):
→ 334 passed  (exit 0; only pre-existing Pillow `getdata` deprecation warnings)   [reproduced this cycle]
```
Coverage: valid build; unsupported schema / duplicate UID / invalid dims+type / missing+mismatched version / fingerprint mismatch / opening-miscategorization rejected; openings excluded from furniture & counts; same-type items keep distinct uids; empty room renders safely; deterministic build & render; synonyms normalize (`couch`→`lounger-sofa`, `nightstand`→`side-table`, `range hood`→`chimney`); ambiguous/unknown → `None`; synonyms come verbatim from the authoritative map; system prompt lists every expected item, carries preservation + no-extra constraints, shows repeated-type counts, preservation outranks visual, deterministic; **manifest↔dictionary↔prompt-line counts agree**; and the dictionary + system prompt are persisted version-bound via the real `_render_room`. Distinguished from prior-agent-reported results: the 334 total and 21 dictionary tests were **reproduced in this cycle** (not carried over).

## 7. Remaining risks & limitations
- **Prompt/dictionary alone cannot force the model.** On the FAL **edit path** (no structural lock) the model can still hallucinate/drop furniture; reliable *prevention* needs structural conditioning (separate authorization) — out of scope here.
- **Output-level detection stays advisory / `NOT_CALIBRATED`** (no detector weights). The dictionary improves label normalization and provenance but does not, by itself, prove output fidelity.
- Synonyms are limited to the project's authoritative `_TYPE_SYNONYMS`; labels outside it normalize to `None` (honest) rather than being guessed.

## 8. Live benchmark plan & cost (prepared — NOT executed)
Verified config: `DEFAULT_AI_PROVIDER=fal`, `fal-ai/flux-kontext/dev`, edit path (`FAL_USE_CONTROLNET=false`), `FAL_SINGLE_ATTEMPT=false` (plan sets it `true`). **Paired A/B** on identical inputs (canonical `v79`, Living Area + Bedroom 3, same base render/seed/dims): baseline prompt vs the dictionary-informed prompt. Per render record: design version + room; expected inventory + dictionary version + manifest/dictionary fingerprint; base-render sha; provider/model + conditioning params; template/prompt version; output sha + provider request id; missing/extra/duplicate criteria; human-review criteria; deterministic fallback/rejection policy.
**Cost (verified, ESTIMATE):** $0.04/MP; 1216×832 ≈ 2 MP ⇒ **$0.08/render**; smallest useful A/B = 2 rooms × 2 arms = **4 renders ⇒ $0.32** (or a 2-render single-arm baseline ⇒ $0.16). Billed on success only.
**Exact approval needed before any call:** (1) render count + hard max cost (e.g., 4/$0.32), and (2) running real paid FAL calls env-only (`FAL_SINGLE_ATTEMPT=true`) with no provider/model/default/production change. Nothing is submitted until approved.

## 9. Git status
`D:/Latest_mynest_design_version/mynest-design-studio` is **not** a git repository → no diff/commit; new/changed files are listed in §5. (The branch in the session header belongs to the separate TeleCRM working directory.)

## 10. Next action
Obtain approval for the §8 paired A/B benchmark to measure whether the dictionary-informed prompt reduces missing/extra furniture **at the output level**; until that evidence exists, the missing/extra problem is **not** declared resolved. In parallel (not implemented here): scope a structural-conditioning input as the real prevention lever.

**Compliance:** no paid provider calls; no provider/model/default/production change; no destructive/unrelated change; no weakened tests; no claim that unit tests prove visual fidelity; `FAITHFUL` still requires the existing output-level verification (never from input/inventory checks).
