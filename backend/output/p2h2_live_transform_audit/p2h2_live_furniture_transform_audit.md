# Phase 2H-2 — Live Scene Furniture Transform Audit

**Floor plan id:** `f6b65d2b-4f96-4931-9f08-67dbd09776f6` (MR.MATHUR BASIC LAYOUT.pdf)  
**Design version id:** `1831bf84-f9d6-4d4f-aedc-4ad95d6145fe`  
**Scene source:** live `GET /api/floor-plans/f6b65d2b-4f96-4931-9f08-67dbd09776f6/scene` (backend :8001)  
**mpp:** 0.008023 m/px — first bed in scene order (bedroom-3) (computeMpp unchanged)  
**Capture:** read-only `onFurnitureTransforms` (Three.js world matrices), harness multi-room run.

## Tolerances
- Position: |dX|,|dZ| ≤ 0.005 m (5 mm)
- Rotation: |dRotY| ≤ 0.5°
- Dimensions (world AABB horizontal vs footprint w·mpp×h·mpp, rotation-sorted): overhang in [-0.01, 0.08] m (mesh detail: door/drawer fronts, rounded-box radius; vertical extent excluded)

## Totals
- Canonical instances: **22** | Captured uids: **22**
- **PASS 22 · MISMATCH 0 · INCONCLUSIVE 0 · NOT_CAPTURED 0**
- Missing canonical uids: none | Unexpected scene uids: none | Duplicate captured: none
- Max observed deltas: |dX|≤0.0000 m, |dZ|≤0.0000 m, |dRotY|≤0.0000°, dim overhang 0.0000…0.0447 m

## Room coverage
| room_id | label | canonical | captured | missing | unexpected | dup | status |
|---|---|---|---|---|---|---|---|
| living-area | Living Area | 3 | 3 | 0 | 0 | 0 | PASS |
| bedroom-3 | Bedroom 3 | 5 | 5 | 0 | 0 | 0 | PASS |
| bedroom-1 | Bedroom 1 | 5 | 5 | 0 | 0 | 0 | PASS |
| kitchen-dining-area | Kitchen & Dining Area | 2 | 2 | 0 | 0 | 0 | PASS |
| bedroom-2 | Bedroom 2 | 5 | 5 | 0 | 0 | 0 | PASS |
| kitchen | Kitchen | 2 | 2 | 0 | 0 | 0 | PASS |
| dining-area | Dining Area | 0 | 0 | 0 | 0 | 0 | PASS |
| bedroom-3-2 | Bedroom 3 | 0 | 0 | 0 | 0 | 0 | PASS |

## Per-item deltas (measured world − expected world)
| room | uid | type | id✓ | dX(m) | dZ(m) | dRotY(°) | dim overhang lo,hi (m) | status |
|---|---|---|---|---|---|---|---|---|
| living-area | …438948 | console | Y | +0.0000 | +0.0000 | +0.000 | +0.0450, +0.0000 | PASS |
| living-area | …478712 | lounger-sofa | Y | +0.0000 | +0.0000 | +0.000 | +0.0054, +0.0025 | PASS |
| living-area | …572349 | lounger-sofa | Y | +0.0000 | +0.0000 | +0.000 | +0.0000, +0.0000 | PASS |
| bedroom-3 | …187466 | bed | Y | +0.0000 | +0.0000 | +0.000 | +0.0000, +0.0300 | PASS |
| bedroom-3 | …219083 | side-table | Y | +0.0000 | +0.0000 | +0.000 | +0.0000, +0.0000 | PASS |
| bedroom-3 | …220302 | side-table | Y | +0.0000 | +0.0000 | +0.000 | +0.0000, +0.0000 | PASS |
| bedroom-3 | …606853 | wardrobe | Y | +0.0000 | +0.0000 | +0.000 | +0.0466, +0.0009 | PASS |
| bedroom-3 | …652625 | dressing-table | Y | +0.0000 | +0.0000 | -0.000 | +0.0459, +0.0010 | PASS |
| bedroom-1 | …891845 | bed | Y | +0.0000 | +0.0000 | +0.000 | +0.0127, +0.0407 | PASS |
| bedroom-1 | …946014 | side-table | Y | +0.0000 | +0.0000 | +0.000 | +0.0000, +0.0000 | PASS |
| bedroom-1 | …947384 | side-table | Y | +0.0000 | +0.0000 | +0.000 | +0.0000, +0.0000 | PASS |
| bedroom-1 | …602167 | wardrobe | Y | +0.0000 | +0.0000 | +0.000 | +0.0450, +0.0000 | PASS |
| bedroom-1 | …642783 | dressing-table | Y | +0.0000 | +0.0000 | +0.000 | +0.0450, +0.0000 | PASS |
| kitchen-dining-area | …686293 | chimney | Y | +0.0000 | +0.0000 | +0.000 | -0.0000, +0.0000 | PASS |
| kitchen-dining-area | …800756 | dining-table | Y | +0.0000 | +0.0000 | +0.000 | +0.0029, +0.0018 | PASS |
| bedroom-2 | …895814 | bed | Y | +0.0000 | +0.0000 | +0.000 | +0.0291, +0.0447 | PASS |
| bedroom-2 | …146522 | side-table | Y | +0.0000 | +0.0000 | +0.000 | -0.0000, +0.0000 | PASS |
| bedroom-2 | …147677 | side-table | Y | +0.0000 | +0.0000 | +0.000 | +0.0000, +0.0000 | PASS |
| bedroom-2 | …614206 | wardrobe | Y | +0.0000 | +0.0000 | +0.000 | +0.0603, +0.0127 | PASS |
| bedroom-2 | …647163 | dressing-table | Y | +0.0000 | +0.0000 | +0.000 | +0.0450, +0.0000 | PASS |
| kitchen | …607029 | kitchen-base | Y | +0.0000 | +0.0000 | +0.000 | +0.0352, +0.0329 | PASS |
| kitchen | …608231 | kitchen-base | Y | +0.0000 | +0.0000 | +0.000 | +0.0300, +0.0300 | PASS |

## Scope / limitations
- Deterministic transform only. This does NOT prove AI image-to-image preservation (see Phase 2C: AI drops/alters furniture). No FAL calls.
- `design_version_id` differs across reads (2H-1 `aa213074…` → 2H-2 `1831bf84…`) despite identical furniture — version id is not stable per read; flagged.
- Room association is from scene structure (per-room capture), not proximity/label. Room ids are unique; labels are not (duplicate 'Bedroom 3').
- Dimension deltas compare the world AABB (includes mesh overhang) to the footprint; vertical extent is excluded from the horizontal check.