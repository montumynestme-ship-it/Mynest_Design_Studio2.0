# Phase 4 — Init-Image Influence Experiment (executed, authorized)

**Result in one line:** The init-image hypothesis is **CONFIRMED** — removing the img2img init image (`FAL_CONTROL_USE_INIT=false`) **dramatically restored photorealism** in both rooms. **But** it **broke geometry/inventory**: the Canny control rendered the clay base's edges as a literal floating **white wireframe cage**, the rooms were reinterpreted/enlarged, and Living Area **hallucinated** furniture. Per the contract, **both init-off outputs are REJECTED** (geometry/inventory altered). The init image was doing double duty — seeding flat materials (the flatness cause) *and* anchoring the composition (the fidelity it provided). **Neither init-on (flat but faithful) nor init-off (realistic but broken) achieves both.**

**Spend:** owner-authorized **2 renders, $0.16**; **2 issued, 2 succeeded, no retries**; cap not exceeded. Provider/model/defaults unchanged (env-only).

---

## 1. Stage 1 — confirmed adapter behavior (VERIFIED from source)
`fal_flux_adapter._build_control_body` always sends the base render as the Canny `control_lora_image_url` + `control_lora_strength`, and **only when `FAL_CONTROL_USE_INIT=true` (the default, `config.py:111`) also** sends it as the img2img init `image_url`. Its own comment: the init "seeds real colors/materials (so a high structure-lock does not render as flat clay)." `image_size` is pinned to the base dims (output stays 1216×832). **Disabling the init is a pure env flag** — no provider/model/API/code change. Default (`true`) is untouched.

## 2. Stage 2 — executed renders (provenance VERIFIED)
`FAL_USE_CONTROLNET=true FAL_SINGLE_ATTEMPT=true FAL_CONTROL_USE_INIT=false FAL_CONTROL_STRENGTH=0.8` (env-only). Adapter confirmed `init=False` at runtime. Same base/prompt/seed/dims/model as Phase 3; only the init image removed.

| room | init | strength | base sha16 | output sha16 | request id | status |
|---|---|---|---|---|---|---|
| Living Area | **off** | 0.8 | `b3b9315a564d8615` | `700e413722db…` | `01a17be1-c64a-7ec0-9c41-56ce5665552e` | ok |
| Bedroom 3 | **off** | 0.8 | `40ac59845ef052a4` | `4a74c0d6171e…` | `01a17be4-9172-7780-b480-dcc6dcc3ed3a` | ok |

Paired baselines (no new cost): Phase 3 init-**on** @ 0.8 — Living `52c3c55e…`, Bedroom 3 `193e4a42…` (flat but faithful). Provenance: `…/scratchpad/init_off_provenance.json`.

## 3. Stage 3 — evaluation (human review; detector NOT_CALIBRATED)
| axis | init ON @0.8 (Phase 3) | init OFF @0.8 (Phase 4) |
|---|---|---|
| **Photorealism** | **none** (flat clay ≈ base) | **dramatically improved** (marble floor, recessed/cove lighting, realistic materials, textiles, art) |
| **Missing/extra furniture** | none (faithful) | **extra/hallucinated** (Living Area: ottomans, bench, plants, art, curtains not in canonical; Bedroom 3: closer — bed + 2 nightstands + dresser — but still reinterpreted) |
| **Geometry / structure** | preserved (same shell + camera) | **broken** — Canny edges render as a **floating white wireframe cage**; room reinterpreted/enlarged; camera changed |
| **Walls/openings** | preserved | reinterpreted (new doors/windows invented) |
| **Camera comparability** | same dollhouse | different (eye-level interior) |
| **Contract verdict** | faithful, not photorealistic | **photorealistic, NOT faithful → REJECTED** |

Position/orientation/exact dimensions: **not measurable** (the init-off output is a reinterpreted scene, not the base composition). Occlusion/cropping: the wireframe artifact obscures the center. The existing `assess_output_inventory` would return **NOT_VALIDATABLE** (no calibrated detector) — the conclusions above are **human review**.

## 4. Finding (hypothesis CONFIRMED, with a decisive caveat)
- **CONFIRMED:** the img2img **init image caused the flat clay appearance** — removing it restored photorealism dramatically in both rooms. (Phase 3's attribution is supported by direct evidence.)
- **Caveat (new, VERIFIED):** the init image was **also** anchoring the scene to the base composition. Without it, the **Canny `control_lora` on the clay base render does not hold structure** at strength 0.8 — it renders the base's edges as a literal **wireframe artifact** and lets the model reinterpret the room + invent furniture. So the base render is a **poor Canny control input** (a solid 3D massing, not clean line-art), and the init was masking that.
- **Conclusion:** the two levers conflict on this fal model — **init-on = faithful-but-flat; init-off = realistic-but-broken.** Neither is acceptable (one fails photorealism, the other fails the canonical contract).

## 5. Next smallest evidence-supported changes (hypotheses — bounded, separately authorized)
None of these is confirmed; each is a bounded next experiment:
1. **Partial init influence** — if the control model exposes an **init/denoise strength**, a *low* init (e.g. 0.2–0.4) might seed composition/anchor without flattening materials. (Check fal's `flux-control-lora-canny` schema for such a parameter first.)
2. **Better structure conditioning input** — feed a **clean line-art/edge or DEPTH map** (not the clay render) as the control, so structure is enforced without the wireframe artifact. May require a depth-control model (a provider-capability decision, out of current scope).
3. **Lower control strength, init off** — test init-off at strength ~0.4–0.5 to see if the wireframe artifact subsides while realism remains (likely weaker geometry hold).
Recommend evaluating (1) first (cheapest, no model change) after verifying the parameter exists.

## 6. Constraints honored / limitations
- No production-default/provider/model/code change (env-only run); no canonical mutation; deterministic fallback intact; Furniture Library untouched.
- **Detector NOT_CALIBRATED** (OWLv2 weights absent) — human review only; detector output certified nothing.
- **Scope:** 2 rooms, 2 renders, one design version, one strength. **Not production-wide.**
- **Objective NOT complete:** no output satisfies the canonical contract *and* shows meaningful photorealism.

## 7. Tests (offline; before/after; no code changed)
```
pre-experiment:  pytest -q <output_inventory_assessment + fal_flux_adapter + output_fidelity> → 57 passed
post-experiment: pytest -q <same + render_inclusion>                                          → 68 passed (exit 0)
```

## 8. Git / files & spend
Not a git repo → no diff. **No production code changed.** Artifacts: 2 init-off PNGs + `init_off_provenance.json` in the session scratchpad; this report is the only new project file. **Actual charges: 2 billed renders = $0.16** (fal $0.04/MP × 2 MP × 2), within the authorized cap. Request IDs in §2.

## 9. Recommendation & next action
- **Do not adopt init-off as-is** — it breaks the canonical contract (reject).
- **Next:** verify whether `flux-control-lora-canny` exposes a low **init/denoise strength**; if so, a bounded 2-render test of a *weak* init (anchor without flatten) is the smallest next step. Otherwise, the path forward is a **cleaner structure-conditioning input (edge/line-art or depth)**, which is a larger, separately-scoped conditioning/capability change. Keep the deterministic render as the trusted fallback and AI outputs `UNVERIFIED` until a faithful+photorealistic result is actually demonstrated.
