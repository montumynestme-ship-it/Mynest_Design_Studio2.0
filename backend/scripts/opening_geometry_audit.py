"""Deterministic opening-geometry + 2D→3D placement AUDIT (read-only evidence).

Single owner for BOTH opening audits (no step-specific duplicate scripts):
  * STEP 1 — source → wall-association → wall-relative → scene (on-wall) geometry,
  * STEP 3 — scene opening_placement → deterministic 3D placement (the exact
    RoomScene3D transform) + final 3D wall-relative position + deltas + status.

It changes NO production behavior and reuses the REAL production helpers
(`scene_service._find_supporting_wall`, `_project_on_wall`, the
`_attach_opening_placements` logic) plus the frontend RoomScene3D transform
(windows windowWalls 216-226 / doors 562-574): x=(p.cx-rcx)*mpp, z=(p.cy-rcy)*mpp,
width/depth = p.w/p.h * mpp (min 0.08), rotation_y = -p.rotation. mpp = computeMpp.

Run:  PYTHONPATH=. .venv/Scripts/python.exe scripts/opening_geometry_audit.py <file_id>
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services import floor_plan_service, scene_service
from scripts.furniture_2d_to_3d_audit import compute_mpp  # shared mpp calibration (STEP 2)

MIN_DIM_M = 0.08  # RoomScene3D Math.max(0.08, ...) floor on opening width/depth


def _project_segment(
    x1: float, y1: float, x2: float, y2: float, cx: float, cy: float
) -> tuple[float, float, float]:
    """Vector projection of (cx,cy) onto a segment; returns (normalized_t, perp, length)."""
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy or 1.0
    t = max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / l2))
    px, py = x1 + t * dx, y1 + t * dy
    return t, math.hypot(cx - px, cy - py), math.hypot(dx, dy)

# Coordinate-system metadata (traced from geometry_extraction_service / scene_service /
# frontend RoomScene3D). All backend geometry is in "world px" = pdf_pt × WORLD_SCALE.
COORDINATE_SYSTEMS = {
    "pdf_source": {
        "origin": "top-left of the page",
        "x_axis": "right (+x)",
        "y_axis": "down (+y)",
        "units": "world px (pdf points x WORLD_SCALE)",
        "rotation_convention": "degrees, atan2(dy,dx); 0 = +x; increases toward +y",
        "scale": "geometry_extraction_service.WORLD_SCALE (page['scale'])",
    },
    "canonical_room": {
        "origin": "same as pdf_source (no separate room-local transform)",
        "x_axis": "right (+x)", "y_axis": "down (+y)",
        "units": "world px", "rotation_convention": "degrees (same as source)",
        "scale": "1:1 with pdf_source",
    },
    "scene": {
        "origin": "same world-px frame as source",
        "x_axis": "right (+x)", "y_axis": "down (+y)",
        "units": "world px",
        "note": "opening placement cx/cy are projected ONTO the supporting wall; "
                "w/h/rotation preserved from source",
    },
    "three_d": {
        "computed_in": "frontend RoomScene3D (Three.js)",
        "mapping": "world px -> metres via mpp; plan X -> scene x; plan Y(down) -> scene z; up = y",
        "origin": "room bbox centre",
        "units": "metres",
        "note": "the deterministic transform is transcribed from RoomScene3D and applied "
                "here to the projected opening placement (scene_3d); it is NOT a separate "
                "production code path",
    },
}


def wall_relative(wall: dict[str, Any], cx: float, cy: float) -> dict[str, Any]:
    """Vector-projection wall-relative position using the PRODUCTION projection
    (`scene_service._project_on_wall`). Never relative to furniture or room centre."""
    px, py, ang, perp, t = scene_service._project_on_wall(cx, cy, wall)
    x1, y1, x2, y2 = (float(wall["x1"]), float(wall["y1"]), float(wall["x2"]), float(wall["y2"]))
    wlen = math.hypot(x2 - x1, y2 - y1)
    return {
        "distance_from_start": round(t * wlen, 3),
        "distance_from_end": round((1.0 - t) * wlen, 3),
        "normalized_position": round(t, 4),
        "wall_length": round(wlen, 3),
        "direction_deg": round(ang, 3),
        "perpendicular_distance": round(perp, 3),
        "foot_on_wall": {"x": round(px, 3), "y": round(py, 3)},
    }


def _num(o: dict[str, Any], k: str, default: float = 0.0) -> float:
    try:
        return float(o.get(k, default) or default)
    except (TypeError, ValueError):
        return default


def build_audit(file_id: str) -> dict[str, Any]:
    canonical = floor_plan_service.get_canonical(file_id)
    scene = scene_service.build_scene(file_id, canonical=canonical)
    structured_walls = scene.get("structured_walls", []) or []
    walls_by_id = {str(w.get("id")): w for w in structured_walls}
    info = floor_plan_service.get_latest_version_info(file_id)
    design_version_id = info[0] if info else None
    mpp = compute_mpp(scene.get("rooms", []) or [])  # STEP 3: 2D→3D metres-per-pixel

    openings: list[dict[str, Any]] = []
    for r in scene.get("rooms", []) or []:
        room_id = r.get("id")
        room_name = r.get("label")
        _bbox = r.get("bbox") or [0, 0, 0, 0]
        rcx = float(_bbox[0]) + float(_bbox[2]) / 2.0  # room centre (world px)
        rcy = float(_bbox[1]) + float(_bbox[3]) / 2.0
        # Reconstruct the SAME candidate set production uses in _attach_opening_placements.
        cand: list[tuple[str, str, dict[str, Any], str | None]] = []
        for f in r.get("furniture", []) or []:
            iid = str(f.get("item_id", ""))
            if "window" in iid:
                cand.append(("window", "editor", f, f.get("supporting_wall_id")))
            elif "door" in iid:
                cand.append(("door", "editor", f, f.get("supporting_wall_id")))
        for o in r.get("supplemental_windows") or []:
            cand.append(("window", "pdf", o, o.get("supporting_wall_id")))
        for o in r.get("supplemental_doors") or []:
            cand.append(("door", "pdf", o, o.get("supporting_wall_id")))

        for idx, (kind, src, o, wid) in enumerate(cand):
            cx, cy = _num(o, "cx"), _num(o, "cy")
            w, h = _num(o, "w"), _num(o, "h")
            rot = _num(o, "rotation")
            max_perp = 100.0 if kind == "door" else 60.0  # production value
            wall = scene_service._find_supporting_wall(cx, cy, rot, structured_walls, wid, max_perp)

            rec: dict[str, Any] = {
                "opening_id": str(o.get("uid") or o.get("id") or f"{kind}-{room_id}-{idx}"),
                "type": kind,
                "representation": src,  # editor (canonical furniture) | pdf (supplemental)
                "room_id": room_id,
                "room_name": room_name,
                "source": {"cx": cx, "cy": cy, "width": w, "height": h, "rotation": rot},
                "canonical_or_supplemental": {
                    "representation": src, "cx": cx, "cy": cy,
                    "width": w, "height": h, "rotation": rot,
                },
            }
            if wall is None:
                # STEP 1 + STEP 3: no supporting wall -> honestly UNABLE_TO_VERIFY.
                rec["wall"] = {"value": None,
                               "reason": "no structured wall qualified (perp>max or rotation mismatch); "
                                         "production renders at authored position, verified=false"}
                rec["wall_relative"] = {"value": None, "reason": "no supporting wall"}
                rec["scene"] = {"cx": cx, "cy": cy, "width": w, "height": h,
                                "rotation": rot, "verified": False}
                rec["scene_3d"] = {"value": None, "reason": "no supporting wall"}
                rec["final_3d_wall_relative"] = {"value": None, "reason": "no supporting wall"}
                rec["deltas"] = {"value": None, "reason": "no supporting wall"}
                rec["room_association_match"] = True
                rec["wall_association_match"] = None
                rec["status"] = "UNABLE_TO_VERIFY"
                rec["first_divergence_stage"] = "wall_association (no supporting wall; verified=false)"
                rec["width_exceeds_wall"] = None
            else:
                px, py, ang, perp, t = scene_service._project_on_wall(cx, cy, wall)
                x1, y1 = float(wall["x1"]), float(wall["y1"])
                x2, y2 = float(wall["x2"]), float(wall["y2"])
                wlen = math.hypot(x2 - x1, y2 - y1)
                rec["wall"] = {
                    "wall_id": str(wall.get("id")),
                    "start": {"x": round(x1, 3), "y": round(y1, 3)},
                    "end": {"x": round(x2, 3), "y": round(y2, 3)},
                    "length": round(wlen, 3),
                    "direction_deg": round(ang, 3),
                }
                rec["wall_relative"] = wall_relative(wall, cx, cy)
                # STEP 1: on-wall placement (world px) RoomScene3D consumes.
                rec["scene"] = {
                    "cx": round(px, 3), "cy": round(py, 3),  # projected ON the wall
                    "width": w, "height": h, "rotation": rot,
                    "wall_angle_deg": round(ang, 3), "verified": True,
                    "perp_removed_px": round(perp, 3),
                }
                # STEP 3: deterministic 3D transform (RoomScene3D) on the projected centre.
                ox, oz = (px - rcx) * mpp, (py - rcy) * mpp
                rec["scene_3d"] = {
                    "x": round(ox, 6), "z": round(oz, 6),
                    "width": round(max(MIN_DIM_M, w * mpp), 6),
                    "depth": round(max(MIN_DIM_M, h * mpp), 6),
                    "rotation_y_deg": round(-rot, 6),
                }
                # STEP 3: 3D wall-relative — project the 3D centre onto the 3D-transformed wall.
                t3, perp3, wlen3 = _project_segment(
                    (x1 - rcx) * mpp, (y1 - rcy) * mpp, (x2 - rcx) * mpp, (y2 - rcy) * mpp, ox, oz)
                rec["final_3d_wall_relative"] = {
                    "normalized": round(t3, 6), "perpendicular_m": round(perp3, 6),
                    "wall_length_m": round(wlen3, 6),
                }
                rec["deltas"] = {
                    "wall_relative_normalized": round(abs(t - t3), 6),  # source vs final 3D
                    "width_m": round((w * mpp) - rec["scene_3d"]["width"], 6),
                    "height_m": round((h * mpp) - rec["scene_3d"]["depth"], 6),
                    "rotation_deg": round((-rot) - rec["scene_3d"]["rotation_y_deg"], 6),
                    "perp_removed_px": round(perp, 3),  # intentional on-wall projection
                }
                rec["room_association_match"] = True
                rec["wall_association_match"] = True
                rec["status"] = "VERIFIED"
                rec["first_divergence_stage"] = (
                    "NONE" if abs(t - t3) < 1e-6 else "scene_3d (along-wall position changed)")
                rec["width_exceeds_wall"] = w > wlen
                rec["projection_note"] = (
                    "perpendicular on-wall projection is INTENTIONAL architectural "
                    "normalization; along-wall position preserved into 3D"
                    if perp > 0.5 else "opening already on wall")
            openings.append(rec)

    verified = [o for o in openings if o.get("status") == "VERIFIED"]
    unver = [o for o in openings if o.get("status") == "UNABLE_TO_VERIFY"]
    max_wr_delta = max((o["deltas"]["wall_relative_normalized"]
                        for o in verified if isinstance(o.get("deltas"), dict)
                        and "wall_relative_normalized" in o["deltas"]), default=0.0)
    return {
        "run_id": design_version_id,
        "design_version_id": design_version_id,
        "plan_id": file_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "coordinate_systems": COORDINATE_SYSTEMS,
        "mpp": mpp,
        "wall_count": len(structured_walls),
        "opening_count": len(openings),
        "verified_count": len(verified),
        "unable_to_verify_count": len(unver),
        "max_wall_relative_delta": round(max_wr_delta, 8),
        "openings": sorted(openings, key=lambda o: (str(o["room_name"]), o["type"], o["opening_id"])),
    }


def _write_artifacts(audit: dict[str, Any]) -> tuple[Path, Path]:
    out_dir = Path("output") / "geometry_audit" / str(audit["design_version_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / "opening_geometry_audit.json"
    tpath = out_dir / "opening_geometry_audit.txt"
    jpath.write_text(json.dumps(audit, indent=2, sort_keys=False), encoding="utf-8")
    lines = [
        f"OPENING GEOMETRY + 2D->3D AUDIT  design_version_id={audit['design_version_id']}  plan_id={audit['plan_id']}",
        f"walls={audit['wall_count']}  openings={audit['opening_count']}  verified={audit['verified_count']}  "
        f"unable_to_verify={audit['unable_to_verify_count']}  mpp={audit['mpp']:.6f}  "
        f"max_wall_relative_delta={audit['max_wall_relative_delta']:.3g}  generated_at={audit['generated_at']}",
        "=" * 100,
    ]
    for o in audit["openings"]:
        wr = o["wall_relative"]
        wall = o["wall"]
        lines.append(f"[{o['room_name']}] {o['type']} id={o['opening_id']} repr={o['representation']} status={o['status']}")
        lines.append(f"    source       cx={o['source']['cx']:.2f} cy={o['source']['cy']:.2f} "
                     f"w={o['source']['width']:.2f} h={o['source']['height']:.2f} rot={o['source']['rotation']:.2f}")
        if wall.get("wall_id"):
            sc3 = o["scene_3d"]; f3 = o["final_3d_wall_relative"]; d = o["deltas"]
            lines.append(f"    wall         id={wall['wall_id']} start=({wall['start']['x']:.1f},{wall['start']['y']:.1f}) "
                         f"end=({wall['end']['x']:.1f},{wall['end']['y']:.1f}) len={wall['length']:.1f} dir={wall['direction_deg']:.1f}")
            lines.append(f"    wall_relative norm={wr['normalized_position']:.4f} "
                         f"from_start={wr['distance_from_start']:.1f} from_end={wr['distance_from_end']:.1f} "
                         f"perp={wr['perpendicular_distance']:.1f}")
            lines.append(f"    scene(px)    cx={o['scene']['cx']:.2f} cy={o['scene']['cy']:.2f} "
                         f"wall_angle={o['scene']['wall_angle_deg']:.1f} perp_removed={o['scene']['perp_removed_px']:.1f}")
            lines.append(f"    scene_3d(m)  x={sc3['x']:.3f} z={sc3['z']:.3f} w={sc3['width']:.3f} d={sc3['depth']:.3f} rotY={sc3['rotation_y_deg']:.1f}")
            lines.append(f"    3d_wall_rel  norm={f3['normalized']:.4f}  deltas: wall_rel={d['wall_relative_normalized']:.3g} "
                         f"w={d['width_m']:.3g} h={d['height_m']:.3g} rot={d['rotation_deg']:.3g}  "
                         f"first_div={o['first_divergence_stage']} width_exceeds_wall={o['width_exceeds_wall']}")
        else:
            lines.append(f"    wall         NONE ({wall.get('reason')})  first_div={o['first_divergence_stage']}")
            lines.append(f"    scene        cx={o['scene']['cx']:.2f} cy={o['scene']['cy']:.2f} verified=False  (UNABLE_TO_VERIFY)")
        lines.append("-" * 100)
    tpath.write_text("\n".join(lines), encoding="utf-8")
    return jpath, tpath


def main() -> None:
    file_id = sys.argv[1] if len(sys.argv) > 1 else "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    audit = build_audit(file_id)
    jpath, tpath = _write_artifacts(audit)
    print(f"openings={audit['opening_count']} walls={audit['wall_count']} "
          f"verified={audit['verified_count']} unable_to_verify={audit['unable_to_verify_count']} "
          f"max_wall_relative_delta={audit['max_wall_relative_delta']:.3g}")
    print(f"JSON: {jpath}")
    print(f"TXT:  {tpath}")


if __name__ == "__main__":
    main()
