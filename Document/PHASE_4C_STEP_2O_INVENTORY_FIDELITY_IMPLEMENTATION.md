# Phase 4C — Step 2O: Inventory & AI-Render Fidelity — Implementation + Blocked Work

**Mode:** Implementation of the **safe, in-scope** portion; the rest is blocked and documented. No provider/default/dependency change; no paid generation; no canonical/threshold/gate change; no DB writes performed. Target design re-verified: version `85759b78-210e-4daf-a2d1-9e8ea906fee5` (FID `f6b65d2b…`, v79).

---

## 0. Checkout & environment (VERIFIED)
- The app (`backend/`, `frontend/`) is **not** a git repo (`git rev-parse` fails; only `floorplan-parser/.git`, a separate clean repo, exists). No branch/diff for the app; changed files listed explicitly in §6.
- `DATABASE_URL` = **remote/shared PostgreSQL** (scheme `postgresql+psycopg`). ⇒ `generate()` writes generation rows to a shared DB, so `generate()`-path integration tests were **deliberately not run** (mandate: no shared-DB writes). Pure/offline tests were run.
- Docs read: `README.md`, `docs/CORE_PIPELINE_DOCUMENTATION.md`, `PROJECT_CONTEXT.md`, `docs/AI_RENDER_ACCURACY_ISSUES.md`, `docs/AI_RENDER_FIDELITY_WORKFLOW.md`, `docs/PIPELINE_AUDIT_REPORT.md`, and prior Phase-4C reports (2H/2I/2J/2K/2M/2N/2N.1).

---

## 1. Root-cause findings (evidence-based)

**A1 — The deterministic inventory contract is already implemented and working (VERIFIED).** A full-design reconciliation of v79 (executed, read-only) shows **every real furniture item is accounted for exactly once**:
- 35 canonical items → 22 real furniture + 8 openings + 5 `room-tag` annotations. Openings (`_OPENING_IDS`) and annotations (`furniture_catalog.is_annotation`) are correctly **excluded**, not dropped.
- **No duplicate uids; no unmapped types** (all 12 item_ids resolve in `furniture_catalog.FURNITURE` and the frontend `furniture3d` catalog; only `room-tag` is unmapped and is a styling annotation, stripped by `prompt_service.group_by_room` via `furniture_catalog.strip_annotations`, `:355-356`).
- Every real item appears in exactly one `group_by_room` section **and** one scene room (`reconstruct_rooms` assigns each item once, `architectural_service.py:306-321`).

**A2 — The per-section inventory gate already surfaces the real defects (VERIFIED, executed).** Per-section `base_inventory_service.assess_section_base_inventory` for v79:

| section | gate | base room (status) | missing |
|---|---|---|---|
| Living Area | MATCH | Living Area (CONFIRMED) | — |
| **Kitchen** | **MISMATCH** | Kitchen & Dining Area (CONFIRMED) | **Kitchen Base** |
| Dining Area | NOT_ASSESSABLE | (none — merged twin) | — |
| **Bedroom 1** | **MISMATCH** | Bedroom 1 (CONFIRMED) | **Wardrobe** |
| Bedroom 2 | MATCH | Bedroom 2 (CONFIRMED) | — |
| Bedroom 3 | MATCH | Bedroom 3 (CONFIRMED) | — |

So the real "missing furniture" defects are **two instances of the same root cause** (`kitchen-base` ×2 and a `wardrobe` lie outside their room's proven raster polygon → UNCERTAIN → not in the selected CONFIRMED base) — the out-of-polygon reconstruction issue documented in Steps 2K/2M/2N/2N.1. **These are honestly gated (MISMATCH blocks dispatch), not silently dropped.**

**A3 — The only safe fix for the actual missing-furniture defect is blocked.** Completing the Kitchen/Bedroom-1 base render requires the **explicit room-assignment + minimal floor-patch** feature, which Step 2N.1 concluded is **READY FOR PRODUCT DECISION** but not yet authorized to implement (it needs a product decision + a visual-review capture). It is **out of scope** here (no canonical/geometry change, no un-approved feature).

**A4 — Gap actually closed by this step (VERIFIED):** the contract enforced per-section correctness but had **no explicit full-design accounting** — an item that reached *no* section or *no* scene room, a duplicate uid, or an unknown type would have been invisible (no diagnostic). This step adds that explicit diagnostic (§2). (No such item exists in v79; the diagnostic is a loud-failure guard for future/edge designs — exactly Workstream A's "no silent drops / explicit diagnostics for missing mappings and duplicate IDs".)

---

## 2. Minimal code changes (each file explained)

1. **NEW `backend/app/services/inventory_reconciliation_service.py`** — pure, offline, read-only `reconcile_design_inventory(furniture, scene_rooms, sections)` + `reconciliation_warnings(result)`. Accounts for every canonical furniture uid across sections and scene rooms; returns explicit diagnostics for `duplicate_uids`, `unmapped_types`, `uidless`, `unaccounted_in_sections`, `unaccounted_in_scene`, and records the correctly-excluded openings/annotations. Reuses `furniture_catalog` + `_OPENING_IDS` so exclusions never drift. **Never** modifies canonical, reassigns, re-groups, changes geometry, or gates.
2. **NEW `backend/tests/test_inventory_reconciliation.py`** — 8 offline tests (synthetic fixtures + the real v79 snapshot, read-only).
3. **EDIT `backend/app/services/generation_service.py`** — (a) add `inventory_reconciliation_service` to the service imports; (b) after the AIR-03 merge-map scene build, a **log-only, try/except-guarded** diagnostic that emits `[INVENTORY RECON]` warnings for any reconciliation issue. **Observability only** — it reuses the scene already built for the merge map (no extra `build_scene`), never gates, never alters outputs; the `BASE_INVENTORY_MISMATCH` gate remains the authoritative refusal.

No API, schema, provider, default, threshold, or gate was changed. No new runtime dependency.

---

## 3. Regression tests & exact results (executed)

```
cd backend && PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q \
  tests/test_inventory_reconciliation.py
→ 8 passed, 5 warnings in 6.28s   (exit 0)
```
Covers the required cases: dropped-before-scene (`unaccounted_in_scene`), omitted-from-section (`unaccounted_in_sections`), duplicate uid, unknown type, uidless real furniture, openings/annotations excluded (no false positive), all-accounted happy path, and **the real v79 design reconciles cleanly (`ok=True`)**.

Re-ran with the surrounding suite (import + no-regression):
```
pytest -q tests/test_inventory_reconciliation.py tests/test_room_membership.py \
  tests/test_authoritative_merge.py tests/test_kitchen_scene_inventory.py
→ 41 passed, 5 warnings in 14.02s   (exit 0)
```
Import check: `import app.services.generation_service` + `inventory_reconciliation_service` → **OK** (no syntax/name/circular-import error).

**NOT run (justified):** `tests/test_inventory_gate_generate.py`, `tests/test_air03_gate_generate.py` and other `generate()`-path tests — `generate()` writes generation rows to the **shared** Postgres (`DATABASE_URL`), which the mandate forbids. The log-only wiring is safe-by-construction (import verified, try/except, reconciliation unit-tested on real data); validating it end-to-end needs an isolated test DB (see §7).

---

## 4. Benchmark — contract validity vs visual fidelity (executed, offline)

Using the v79 snapshot (read-only), separating the two axes the task requires:

- **Contract validity (deterministic, available now):** reconciliation `ok=True` (all real items accounted once); per-section inventory gate = §1/A2 table (2 MISMATCH correctly blocked, 3 MATCH, 1 NOT_ASSESSABLE). Design-version id `85759b78… v79`; base-render = deterministic WebGL capture per scene room.
- **Visual fidelity (BLOCKED / UNVERIFIED):** geometry fidelity of an *AI output* (`validation_service.assess_ai_render`) is deliberately `UNVERIFIED` in production (`output_verified=False`), and a calibrated post-generation detector is **not** available (no representative-output corpus, no paid generation). Per the mandate, visual fidelity is **not claimed** — it is `UNVERIFIED` until evidenced. Contract validity and visual fidelity are kept strictly separate (confirmed, consistent with AIR-07).

---

## 5. Example missing/ambiguous-object reports (from the real fixture)
- **Kitchen → MISMATCH**, missing `Kitchen Base` (uids `kitchen-base-1787478607029`, `…608231`) — present in the scene but in the UNCERTAIN kitchen twin, absent from the selected CONFIRMED base.
- **Bedroom 1 → MISMATCH**, missing `Wardrobe` — same out-of-polygon class.
- **Dining Area → NOT_ASSESSABLE** — no base room resolved (AIR-03 merged/twin-dropped); correctly not asserted as a match or mismatch.
These are produced by the existing gate; the new reconciliation additionally confirms **no item is unaccounted** design-wide.

---

## 6. Changed files & working-tree status
App is not version-controlled, so no `git diff`. Exact changes this step:
- **A** `backend/app/services/inventory_reconciliation_service.py` (new, ~150 lines)
- **A** `backend/tests/test_inventory_reconciliation.py` (new, 8 tests)
- **M** `backend/app/services/generation_service.py` (1 import line; 1 log-only try/except diagnostic block after the merge-map build)
- **A** `PHASE_4C_STEP_2O_INVENTORY_FIDELITY_IMPLEMENTATION.md` (this report)
No other files touched. Scratchpad trace scripts live outside the project tree. The nested `floorplan-parser` repo is unchanged.

---

## 7. Remaining risks, blocked work, next concrete action
**Blocked (need authorization / inputs):**
- **Workstream B (structural conditioning / provider):** no provider/default/dependency change without approval; the deterministic render remains the trusted fallback (preserved). The Canny opt-in path exists behind a flag (prior work) but is not enabled.
- **Workstream C (calibrated post-gen detector):** needs a representative AI-output corpus + calibration; honest tri-state already separates contract from visual fidelity and defaults to `UNVERIFIED`. No uncalibrated IoU threshold introduced.
- **Workstream D (paid benchmark + bounded retry):** needs explicit paid-generation authorization; offline contract benchmark delivered (§4).
- **The actual missing-furniture fix (Kitchen Base / Wardrobe):** the explicit-assignment + floor-patch feature is **READY FOR PRODUCT DECISION** (Step 2N.1); awaiting the product decision + a visual-review capture before implementation.

**Risks:** the reconciliation wiring in `generate()` is log-only and unit-tested but was not executed through `generate()` here (shared-DB constraint) — low risk by construction, verify on an isolated DB.

**Next concrete action:** run the `generate()`-path tests against an **isolated test database** (`DATABASE_URL` → a disposable local Postgres/sqlite) to confirm the `[INVENTORY RECON]` diagnostic fires cleanly end-to-end; then take the Step 2N.1 product decision to unblock the real missing-furniture fix.

**Objective status:** NOT marked complete. The geometry contract is preserved and the *contract* validator is reliable and now has explicit full-design accounting; the *visual-fidelity* validator remains `UNVERIFIED` pending a calibrated detector and real output evidence — which the mandate requires before any fidelity claim.
