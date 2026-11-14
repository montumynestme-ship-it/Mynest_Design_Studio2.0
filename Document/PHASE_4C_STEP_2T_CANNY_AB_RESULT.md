# Phase 4C — Step 2T: Canny A/B Furniture-Fidelity Experiment (executed, bounded)

**Result in one line:** On the v79 Living Area, the **Canny structural-conditioning path preserved the canonical inventory exactly (3/3 items, 0 added)** while the current **edit path reinterpreted the sofa, dropped the console, and added ~5 objects** — but Canny at the default strength (1.0) produced **almost no photorealism gain**. Canny is the right lever for fidelity; it needs strength tuning (further, separately authorized runs) to also deliver photorealism. **Overall furniture-fidelity issue NOT declared fixed** (one room, one design; photorealism tradeoff unresolved).

**Spend:** exactly **1 paid request, $0.08** (1216×832 → billed 2 MP × $0.04/MP) — within the $0.15 cap. No other paid calls; production defaults unchanged.

---

## 1. Phase 1 — offline work completed (evidence)
- **2S changes verified present + tested:** `fal_flux_adapter.py` (decor prohibition ×4, `last_effective_prompt`), `generation_service.py` (`effective_prompt` persistence), `tests/test_prompt_preservation.py` → the 2S test set re-ran **green (exit 0)**.
- **Labelled evaluation corpus** (from existing authorized gen `174503c2`, design version `85759b78`/v79):

| room | expected (id→count) | furniture_count | base inventory | base sha16 | assessable base? |
|---|---|---|---|---|---|
| Living Area | Loungers Sofa→2, Console→1 | 3 | **MATCH (complete)** | `b3b9315a564d8615` | **yes** |
| Kitchen | Kitchen Base→2, Chimney→1 | 3 | MISMATCH (incomplete) | `385fd86032e3e8f5` | no (base omits chimney) |
| Bedroom 1 | Bed→1, Side Table→2, Wardrobe→2, Dressing Table→1 | 6 | MISMATCH (pre‑2P mis‑section) | `c599d2eb5e135a2c` | no |
| Bedroom 3 | Bed→1, Side Table→2, Dressing Table→1 | 4 | **MATCH (complete)** | `40ac59845ef052a4` | yes |

- **Provenance / binding verified:** each room's `base_render_meta.json` binds `design_version_id=85759b78…` + room_index + `base_render_sha256` (matches the on‑disk base). Living Area base = `b3b9315a…`, bound to v79, `inventory_status=MATCH`. Effective‑prompt persistence (2S) is forward‑looking (not on this pre‑2S generation). No shared records modified; no test data removed.

## 2. Phase 2 — controlled experiment (all preconditions verified before paying)
- **Room:** Living Area — the room with an **independently‑verified complete base** (MATCH, 3 items). Kitchen/Bedroom 1 excluded (incomplete bases).
- **Control:** the **existing** edit‑path output `generations/174503c2/0.png` (no new cost) — same design version/room/base identity/seed.
- **Candidate:** fal `fal-ai/flux-control-lora-canny` on the **exact** Living Area base (`b3b9315a…`), same seed `1552711625`, same 1216×832, same room prompt.
- **Pricing verified:** fal page states **$0.04/MP, rounded up** → 1.01 MP → **2 MP → $0.08**.
- **Spend enforcement verified in code:** `FAL_SINGLE_ATTEMPT=true` → `max_attempts=1`; `_build_control_body` `num_images=1`; queue polled with free GETs → **exactly one billable image**. `FAL_KEY` present; `FAL_USE_CONTROLNET`/`FAL_SINGLE_ATTEMPT` set as **env for this run only** (production defaults `False` untouched).
- **Request contract confirmed:** base passed as `control_lora_image_url` (+ `image_url` init), model `fal-ai/flux-control-lora-canny`, `control_lora_strength=1.0`.
- **Entitlement:** not pre‑verifiable without a call; a failure would be $0 (no image) with no retry — the single attempt was the bounded test. It **succeeded** (entitlement confirmed).

## 3. Phase 3 — actual outputs & discrepancy table
Canonical Living Area inventory = **L‑sectional (2 Loungers Sofa) + 1 Console = 3 items.** Images delivered to the user (base, control, candidate).

| attribute | Base (deterministic) | Control — edit path (`0.png`) | Candidate — Canny (`livingarea_canny_output.png`) |
|---|---|---|---|
| sha256 (16) | `b3b9315a564d8615` | `b587d7f942b90426` | `dc489a8a99d530c0` |
| conditioning | — | `edit` (image_url) | `canny_controlnet` (control_lora, strength 1.0) |
| request id | — | (historical) | `01a17836-f38e-7da0-ba2e-076964857af4` |
| dims | 1216×832 | 1216×832 | 1216×832 |
| **L‑sectional (2 sofa)** | present | **CHANGED → single straight loveseat** | **PRESERVED (L‑sectional, same place)** |
| **Console** | present | **MISSING / replaced** (not visible) | **PRESERVED (same place)** |
| **Added furniture** | — | **armchair, round coffee table, tripod floor lamp** (VERIFIED) | **none** (VERIFIED) |
| Added decor | — | rug, plant/vase, curtains | none |
| Camera/composition | dollhouse 3/4 | **CHANGED** (eye‑level, re‑framed) | **PRESERVED** (same dollhouse 3/4) |
| Photorealism | low (flat clay) | **high** (realistic materials/lighting) | **low** — ≈ the base; minimal material/lighting gain |
| **Inventory fidelity vs canonical** | reference | **FAIL** — console missing, sofa reshaped, +3 furniture | **PASS** — 3/3 preserved, 0 added |
| Architectural (walls/opening) | reference | not_assessable (camera changed) | **preserved** (same shell/opening as base) |

**Camera note:** the control's camera changed, so some differences there are partly perspective — but *added* furniture (armchair/coffee table/lamp) and the *reshaped* sofa are furniture‑level and assessable regardless. Canny kept the **exact base camera**, so its comparison to the base is direct and unambiguous.

## 4. Did Canny improve inventory preservation? — **YES, decisively (this case)**
- **Extra furniture:** edit path **+3 furniture (+decor)**; Canny **0 added**.
- **Missing/changed:** edit path dropped the console and reshaped the sectional; Canny **preserved both**.
- **Geometry/camera:** Canny preserved them exactly; edit path changed the camera and shell framing.

## 5. Critical caveat — photorealism tradeoff (do not ship Canny as‑is)
At `control_lora_strength=1.0` the Canny output is **structurally perfect but visually almost identical to the flat deterministic base** — it did **not** deliver the photorealism that is the point of AI rendering. So Canny at this strength **fixes fidelity but defeats the visual objective**. A production solution needs a **strength sweep** (e.g. ~0.5–0.8) to balance structure‑lock vs photorealism — which requires **additional, separately‑authorized paid runs** (not permitted under this single‑experiment authorization).

## 6. Phase 4 — verified cost, request count, commands
- **Paid requests: 1. Total cost: $0.08** (≤ $0.15). Provider `fal`, model `fal-ai/flux-control-lora-canny`, request `01a17836…`, `conditioning_mode=canny_controlnet`, `effective_prompt_len=2200`.
- The experiment ran the adapter **directly** (standalone script) — it did **not** go through `generation_service`, so **no AIGeneration row / no shared‑DB record** was created by this run. No production default changed.
- Command (env set for the run only):
  `FAL_USE_CONTROLNET=true FAL_SINGLE_ATTEMPT=true PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe <scratch>/run_livingarea_canny.py`
  → `[OK] output_sha256=dc489a8a… dims=1216x832 conditioning_mode=canny_controlnet request_id=01a17836…`
- Offline tests (Phase 1): 2S set re‑ran green (exit 0).

## 7. Remaining defects & next evidence‑backed action
- **Confirmed:** structural conditioning (Canny) **eliminates extra/missing furniture** that the edit path produces — the fidelity root cause and its fix are now backed by **actual output evidence** (one pair).
- **Unresolved:** Canny at strength 1.0 sacrifices photorealism. **Next action (needs separate paid authorization):** a bounded `control_lora_strength` sweep (e.g. 0.5 / 0.65 / 0.8) on the same Living Area base to find a setting that keeps inventory fidelity *and* restores photorealism; then validate on ≥1 more complete‑base room (e.g. Bedroom 3) before any provider‑default change. Keep deterministic render as the trusted fallback and outputs `UNVERIFIED` until an output‑level detector is calibrated (corpus in §1 is the seed).
- **Not claimed:** production‑wide accuracy, or that the overall furniture‑fidelity issue is fixed — this is one room, one design, with an open photorealism tradeoff.
