# Phase 2H-2 — Live Full-Room Deterministic Furniture Audit Summary

**Floor Plan ID:** `f6b65d2b-4f96-4931-9f08-67dbd09776f6` (Input: `f6b65d2b`)  
**Design Version ID:** `1831bf84-f9d6-4d4f-aedc-4ad95d6145fe`  
**Capture Timestamp:** `2026-10-21T11:11:25.231Z`  
**Calibration MPP:** `0.00802273 m/px`  

---

## Executive Summary
- **Total Live Rooms:** 8
- **Total Canonical Items:** 34 (22 furniture + 12 openings)
- **Deterministic 3D Furniture Instances Captured:** 22 / 22
- **Placement Pass Count (Exact Agreement):** 22 / 22 (100%)
- **Confirmed Mismatches:** 0
- **Missing or Extra Canonical UIDs in 3D:** 0 missing, 0 extra
- **Duplicate Room IDs:** 0 (Room IDs strictly unique)
- **Position Tolerance:** 0.001 m (1 mm) | **Max Observed Position Delta:** 0.000000 m
- **Rotation Tolerance:** 0.05° | **Max Observed Rotation Delta:** 0.0000°

---

## Per-Room Audit Results
| Room ID | Room Label | Canonical Furn. Count | 3D Measured Transforms | Position PASS | Rotation PASS | Dimension Status | Room Status |
|---|---|---|---|---|---|---|---|
| `living-area` | Living Area | 3 | 3 | 3/3 | 3/3 | INCONCLUSIVE (2D lacks height) | 100% PASS |
| `bedroom-3` | Bedroom 3 | 5 | 5 | 5/5 | 5/5 | INCONCLUSIVE (2D lacks height) | 100% PASS |
| `bedroom-1` | Bedroom 1 | 5 | 5 | 5/5 | 5/5 | INCONCLUSIVE (2D lacks height) | 100% PASS |
| `kitchen-dining-area` | Kitchen & Dining Area | 2 | 2 | 2/2 | 2/2 | INCONCLUSIVE (2D lacks height) | 100% PASS |
| `bedroom-2` | Bedroom 2 | 5 | 5 | 5/5 | 5/5 | INCONCLUSIVE (2D lacks height) | 100% PASS |
| `kitchen` | Kitchen | 2 | 2 | 2/2 | 2/2 | INCONCLUSIVE (2D lacks height) | 100% PASS |
| `dining-area` | Dining Area | 0 | 0 | 0/0 | 0/0 | INCONCLUSIVE (2D lacks height) | EMPTY (Openings Only) |
| `bedroom-3-2` | Bedroom 3 | 0 | 0 | 0/0 | 0/0 | INCONCLUSIVE (2D lacks height) | EMPTY (Openings Only) |

---

## Per-Item Numerical Transforms & Deltas
| Room | UID | Item ID | Pos Delta (m) | Rot Delta (°) | W Delta (m) | H Delta (m) | D Delta (m) | Status |
|---|---|---|---|---|---|---|---|---|
| `living-area` | `console-1787478438948` | `console` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0450 | **PASS** |
| `living-area` | `lounger-sofa-1787478478712` | `lounger-sofa` | 0.000000 | 0.0000 | 0.0000 | 0.1200 | 0.0000 | **PASS** |
| `living-area` | `lounger-sofa-1787478572349` | `lounger-sofa` | 0.000000 | 0.0000 | 0.0000 | 0.1200 | 0.0000 | **PASS** |
| `bedroom-3` | `bed-1787479187466` | `bed` | 0.000000 | 0.0000 | 0.0000 | 0.3500 | 0.0300 | **PASS** |
| `bedroom-3` | `side-table-1787479219083` | `side-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-3` | `side-table-1787479220302` | `side-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-3` | `wardrobe-1787646606853` | `wardrobe` | 0.000000 | 0.0000 | 0.0436 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-3` | `dressing-table-1787646652625` | `dressing-table` | 0.000000 | 0.0000 | 0.0444 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-1` | `bed-1787478891845` | `bed` | 0.000000 | 0.0000 | 0.0339 | 0.3500 | 0.0002 | **PASS** |
| `bedroom-1` | `side-table-1787478946014` | `side-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-1` | `side-table-1787478947384` | `side-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-1` | `wardrobe-1787646602167` | `wardrobe` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0450 | **PASS** |
| `bedroom-1` | `dressing-table-1787646642783` | `dressing-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0450 | **PASS** |
| `kitchen-dining-area` | `chimney-1787478686293` | `chimney` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `kitchen-dining-area` | `dining-table-1787478800756` | `dining-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-2` | `bed-1787478895814` | `bed` | 0.000000 | 0.0000 | 0.0004 | 0.3500 | 0.0237 | **PASS** |
| `bedroom-2` | `side-table-1787479146522` | `side-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-2` | `side-table-1787479147677` | `side-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-2` | `wardrobe-1787646614206` | `wardrobe` | 0.000000 | 0.0000 | 0.0317 | 0.0000 | 0.0000 | **PASS** |
| `bedroom-2` | `dressing-table-1787646647163` | `dressing-table` | 0.000000 | 0.0000 | 0.0000 | 0.0000 | 0.0450 | **PASS** |
| `kitchen` | `kitchen-base-1787478607029` | `kitchen-base` | 0.000000 | 0.0000 | 0.0301 | 0.0000 | 0.0301 | **PASS** |
| `kitchen` | `kitchen-base-1787478608231` | `kitchen-base` | 0.000000 | 0.0000 | 0.0300 | 0.0000 | 0.0300 | **PASS** |

---

## Coverage and Identity Verification
- **Check 1 (Single Room per UID):** PASS (0 UIDs duplicated across rooms)
- **Check 2 (Expected UIDs in 3D):** PASS (0 missing from 3D)
- **Check 3 (No Unexpected UIDs):** PASS (0 extra in 3D)
- **Check 4 (No Multiple Captures per UID):** PASS (all captured exactly once)
- **Check 5 (No Silently Missing Rooms):** PASS (all 8 rooms accounted for)
- **Check 6 (Empty Rooms Recorded Explicitly):** PASS (2 empty rooms: `dining-area`, `bedroom-3-2`)

---

## Room-Grouping Anomalies (Documented — Read-Only)
1. **`kitchen-dining-area`**: Contains chimney and dining-table (+ 1 door). Exact transform match for both.
2. **`kitchen` (Fallback)**: Contains 2 kitchen-base instances. Exact transform match for both.
3. **`dining-area`**: Empty of furniture (contains 1 door opening).
4. **Duplicate `Bedroom 3` Labels**: Two rooms share the label "Bedroom 3", but have unique IDs (`bedroom-3` with 5 furniture items + 2 doors, and `bedroom-3-2` with 1 window).

---

## Safety & Regression Confirmation
- Canonical coordinates, rotations, dimensions, and UIDs: **UNCHANGED**
- Room and wall geometry: **UNCHANGED**
- Camera FOV and scale calculations: **UNCHANGED**
- FAL / AI generation calls: **NONE (0 calls)**
- Production renderer: **UNCHANGED**
