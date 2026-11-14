# Phase 4C — Step 2J: Inventory-Mismatch Status Feasibility (REPORT-ONLY)

**Mode:** REPORT-ONLY. No source/test/doc/DB/dataset/app-state changes. No generation, paid API, hosted inference, or image experiments. Evidence from code inspection + the Step 2I offline scene build (already run) for `1831bf84`.

**Headline:** A distinct inventory-mismatch status is **feasible, additive, and detector-free**. The required evidence — the section's expected inventory (manifest uids) and the **selected base's deterministic scene-room inventory** (scene-room uids) — is all available **server-side at generation time**, without any detector and without changing grouping, placement, labels, geometry, or generation behavior. No existing status represents this failure mode. **Recommended: proceed to a scoped implementation under separate approval** (surface-only, never a render gate).

> This status **communicates a detected limitation; it does not improve render fidelity.** The open-plan base renders remain inventory-incomplete until the partition itself is reconciled (a prohibited change per Steps 2H/2I).

---

## Evidence classification
- **VERIFIED (executed):** scene rooms + `group_by_room` + `_room_id_map` for `1831bf84` (Step 2I run); schema/service/frontend code read this step.
- **VERIFIED-MODEL:** base-key resolution and base-inventory derivation computed from cited code over VERIFIED inputs (`_lookup_base` is a nested closure — modeled line-for-line).
- **HYPOTHESIS / UNKNOWN:** flagged inline.

---

## 1. Existing post-generation status surface — VERIFIED

**Schema** (`app/schemas/generation.py`, `GenerationImageResponse`):
- `geometry_faithful: bool | None` — output-geometry preservation; True only when an output check confirms, else None/False.
- `geometry_status: str | None` — `"FAITHFUL" | "UNVERIFIED" | "FAIL"` (honest tri-state).
- `input_geometry_locked: bool | None` — base was §L-faithful AND consumed as the img2img control.
- `postgen_status: str | None` — `"OK" | "LOW_FIDELITY"` (image mean-abs-diff near-clone); independent of geometry.

**Computation:** `generation_service._compute_postgen_status` (image MAD < 4.0 → LOW_FIDELITY); the geometry tri-state via the validation services; all written to the authoritative per-render record `render_debug.json` and surfaced by `_image_response`.

**Serialization:** `_image_response(...)` maps `render_debug.json` → `GenerationImageResponse` (e.g. `postgen_status=dbg.get("postgen_status")`).

**Frontend types + badges** (`frontend/src/lib/generations.ts`, `GenerationGallery.tsx`):
- `GenerationImage.postgen_status?: string | null`.
- `resolveAiGeometryStatus(geometry_status, geometry_faithful)` → gallery "Not Verified / Faithful" badge (GenerationGallery.tsx:144).
- `isLowFidelityRestyle(postgen_status)` → "Low restyle fidelity" badge (`:166-168`).

**Tests:** `backend/tests/test_postgen_status_surfaced.py`; `frontend/e2e/postgen-low-fidelity.spec.ts`, `e2e/ai-fidelity-status.spec.ts`.

---

## 2. Does any existing status represent a prompt/base inventory mismatch? — VERIFIED: **No**

| Status / service | What it actually measures | Represents prompt↔base inventory mismatch? |
|---|---|---|
| `geometry_status` / `geometry_faithful` | OUTPUT vs base geometry preservation (walls/openings); `output_verified` is always False → usually UNVERIFIED | **No** — about output, and about geometry not inventory |
| `input_geometry_locked` | base was faithful + used as control | **No** — says nothing about which furniture the base contains |
| `postgen_status` (`LOW_FIDELITY`) | image mean-abs-diff base↔output (restyle-not-applied) | **No** — a different failure mode; **must not be overloaded** |
| `furniture_inventory_validation_service` | EXPECTED (canonical/`group_by_room`) vs **detector-found inventory in the AI OUTPUT** (uncalibrated → NOT_CALIBRATED) | **No** — detector-based + measures output, not the deterministic base |
| `validate_scene_2d_to_3d` | WHOLE-scene: every canonical uid maps to a 3D object, room count, walls/openings | **No** — whole-scene membership; a section's base can still be the wrong scene room and this passes |

**Conclusion:** the prompt-inventory vs selected-deterministic-base-inventory mismatch (the Step 2I defect) is **not represented** by any existing signal. A distinct status is warranted and must not reuse `LOW_FIDELITY`.

---

## 3. Evidence available at generation time — VERIFIED / VERIFIED-MODEL

All three inputs are available **server-side, deterministically, detector-free**:

1. **Requested section inventory** — `furniture_manifest.room_manifest(canonical, label)` → `build_room_manifest` → `items[*].uid` (and `counts`). Built from `group_by_room` (furniture_manifest.py:build_manifest), i.e. the same grouping as the prompt. The manifest is **already computed per room** in `_render_room` and recorded (`furniture_manifest.json`).
2. **Selected base's furniture inventory** — the backend builds `scene = scene_service.build_scene(file_id, canonical)` and has `scene.rooms[*].furniture[*].uid`. The base PNG for a key is a WebGL capture of exactly that scene room's furniture (BaseRenderBatch renders `room.furniture`), so **the scene room's uid set is a faithful, deterministic proxy for the base PNG contents** — no image analysis needed. The **selected** base's scene room is the one whose id/normalized-label equals the key `_lookup_base(label)` matched (reproducible via the cited candidate order).
3. **Room-membership / object-presence uncertainty** — each scene room carries `validation_status` (`CONFIRMED` / `UNCERTAIN`); the selected base may be an `UNCERTAIN` furniture-fallback twin (the `1831bf84` case). This distinguishes "object demonstrably absent from the base" from "membership uncertain".

**Base metadata caveat (VERIFIED):** `base_render_meta` sent by the client carries only `{design_version_id, room_key, width, height}` — **no furniture uids** (schemas/generation.py:23; DesignStudio.tsx:527). So the base inventory must come from the backend scene build, **not** from the client payload. (The client only logs `furniture_boxes` to the console; it does not POST them.)

**Worked example — `1831bf84` (VERIFIED inputs, VERIFIED-MODEL resolution):**
- Section `Dining Area` manifest uids ⊇ `{dining-table-1787478800756, …doors}`.
- `_lookup_base("Dining Area")` selects the `Dining Area`/`dining-area` **UNCERTAIN twin** base → scene-room uids `{door-1789635608770}`.
- `dining-table-… ∉ {door-…}` → **DEMONSTRABLE mismatch**, selected base is `UNCERTAIN`.
- Section `Kitchen` manifest ⊇ `{kitchen-base×2, chimney}`; selected `Kitchen` twin base uids `{kitchen-base×2}` → **chimney demonstrably absent**.

---

## 4. Demonstrable vs UNVERIFIED vs not_assessable — proposed semantics (detector-free)

- **`MISMATCH` (demonstrable):** a manifest **furniture** uid (openings excluded) for the section is **absent** from the selected base's scene-room furniture uid set, AND a base was actually selected/used for that section. Deterministic; names the missing uid(s)/type(s) and whether the base scene room was `UNCERTAIN`.
- **`MATCH`:** every manifest furniture uid for the section is present in the selected base's scene-room uid set.
- **`NOT_ASSESSABLE` / `None`:** no base selected for the section (BASE_RENDER_MISSING/BLANK — already failed honestly), text-to-image/demo path (no base), selected base key cannot be resolved to a scene room, or no manifest for an empty section. Legacy records → `None`.

**Constraint-4 compliance:** this compares the manifest against the **deterministic scene** that the base encodes — it **never** uses the uncalibrated furniture detector or the AI output as ground truth. Uncertainty (`UNCERTAIN` scene room, unresolved key) maps to `NOT_ASSESSABLE`, never to a false `MISMATCH` or a false `MATCH`.

---

## 5. Compatibility assessment — additive, no migration, no cache invalidation

- **Field:** add one nullable `inventory_status: str | None` (+ optional `inventory_reason`) to `GenerationImageResponse`, mirroring `postgen_status` exactly (Step 1F pattern). Legacy `render_debug.json` without it → `None` → no badge, no crash.
- **Historical generations:** unaffected — immutable stored PNGs; absent field → `None`.
- **Cache (important, and better than the 2I case):** the status is **derived from manifest + scene**, not from the image bytes, so it does **not** depend on `_compute_room_hash` and needs **no cache invalidation**. It must be recomputed and re-recorded on BOTH the fresh and the cache-hit paths (same place Step 1H added `_compute_postgen_status`), so a cache hit never serves a stale/absent inventory status.
- **API consumers:** additive optional field; existing clients ignore unknown fields.
- **Gallery:** one new badge gated on `inventory_status === 'MISMATCH'` (e.g. "Base missing items: dining table"), alongside the existing badges. Additive; no change to existing badge logic.
- **No change** to room grouping, furniture placement, labels, `requested_rooms`/`room_geometry` keys, geometry, or whether/what gets rendered. **Surface-only.**

---

## Minimal implementation scope (PROPOSAL — REQUIRES APPROVAL)

1. **Backend helper** (pure, deterministic): `assess_section_base_inventory(manifest, scene_rooms, selected_base_key) -> (status, reason)` returning `MATCH | MISMATCH | NOT_ASSESSABLE`. Needs the **selected base key**; the smallest supporting change is to have the base lookup also return the matched key (e.g. `_lookup_base` returns `(bytes, key)`), a behavior-preserving refactor.
2. **Record** it into `render_debug.json` in both fresh and cache-hit paths (mirror `postgen_status`).
3. **Serialize** via `_image_response` as `inventory_status` (+ `inventory_reason`).
4. **Frontend:** add `inventory_status?: string | null` to `GenerationImage`, an `isBaseInventoryMismatch(status)` helper, and one gallery badge.

Scope is comparable to Steps 1F/1H (small, additive). **It must remain surface-only — it must NOT gate, refuse, or alter any render.** Gating on it would change generation behavior → a separate approval.

---

## Minimal deterministic offline regression tests (`1831bf84`, no canonical change, no weakening)

**Backend** (`tests/test_inventory_mismatch_status.py`, offline — scene from `1831bf84` or the synthetic open-plan fixture):
1. `Dining Area`: assert `assess_section_base_inventory` → `MISMATCH` and the reason names `dining-table` absent from the selected base's uids (locks the Step 2I defect).
2. A clean section whose selected base covers its manifest → `MATCH`.
3. No-base path (empty `base_renders` / text-to-image) → `NOT_ASSESSABLE`.
4. Helper independence: a `MISMATCH` leaves `geometry_status` and `postgen_status` unchanged (never implies FAITHFUL/OK).

**Frontend** (`e2e/inventory-mismatch.spec.ts`, pure logic):
- `isBaseInventoryMismatch('MISMATCH') === true`; `'MATCH' | 'NOT_ASSESSABLE' | null | undefined | '' | 'SOMETHING_NEW'` → `false`.

**Existing gates to keep green (no edits):**
```bash
.venv/Scripts/python.exe -m pytest tests/test_postgen_status_surfaced.py \
  tests/test_dynamic_rooms.py tests/test_furniture_inventory_validation.py \
  tests/test_kitchen_scene_inventory.py tests/test_base_render_gate.py -q
cd ../frontend && npx playwright test e2e/postgen-low-fidelity.spec.ts e2e/ai-fidelity-status.spec.ts e2e/room-match.spec.ts
```

---

## Verified facts / hypotheses / unknowns

**Verified:** no existing status represents the prompt/base inventory mismatch (§2); manifest items carry uids and scene rooms carry furniture uids (deterministic, detector-free comparison possible); `base_render_meta` carries no furniture inventory; the mismatch is demonstrable for `1831bf84`; the status is image-independent so no cache invalidation is needed.

**Hypothesis:** the scene room's furniture uid set exactly equals the base PNG contents (true by construction — BaseRenderBatch renders `room.furniture` — but not pixel-verified this step).

**Unknowns:** (1) cleanest way to obtain the selected base key inside the render path without broadening scope — whether to return it from `_lookup_base` or recompute; (2) whether any API consumer already branches on the presence of unknown fields (expected none; not audited externally); (3) exact gallery badge copy/placement (UX decision).

---

## Stop conditions — NOT triggered

This is additive, surface-only, label-safe, record-safe, geometry-safe, placement-safe, grouping-safe, and detector-free; it does not change generation behavior. **No code/test/doc/DB/state change made.** It explicitly does **not** claim to improve render fidelity — only to communicate a detected limitation. **Await explicit approval before implementation.** If approval instead wants the mismatch to **gate** renders, that is a generation-behavior change requiring its own authorization.
