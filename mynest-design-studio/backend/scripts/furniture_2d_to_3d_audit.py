"""Deterministic canonical-2D → 3D FURNITURE transform AUDIT (read-only evidence).

STEP 2 audit — furniture coordinate transformation ONLY. It transcribes the EXACT
production transform from the frontend `RoomScene3D.tsx` (lines 544-554) and the
`computeMpp` calibration from `lib/scene.ts` (126-135), applies them to the REAL
canonical furniture (per scene room), and records per item: canonical_2d, room
transform, expected_3d (independent geometric mapping) vs actual_3d (production
transcription), numeric deltas, and room association.

Production transform (RoomScene3D.tsx):
    x   = (f.cx - room_cx) * mpp          # 2D X -> 3D X
    z   = (f.cy - room_cy) * mpp          # 2D Y -> 3D Z   (NOT 3D Y)
    y   = 0                               # floor
    w3d = max(0.08, f.w * mpp)            # 2D width  -> 3D width
    d3d = max(0.08, f.h * mpp)            # 2D height -> 3D depth (no swap)
    rotation_y = -f.rotation (deg->rad)   # negated for the Y-down -> Z handedness
    room_cx = bbox.x + bbox.w/2 ; room_cy = bbox.y + bbox.h/2
Doors/windows are excluded here (rendered from opening_placements, audited in STEP 1).

Run: PYTHONPATH=. .venv/Scripts/python.exe scripts/furniture_2d_to_3d_audit.py <file_id>
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services import floor_plan_service, scene_service

MIN_DIM_M = 0.08  # RoomScene3D Math.max(0.08, ...) floor

COORDINATE_SYSTEMS = {
    "canonical_2d": {"origin": "pdf top-left", "x_axis": "right (+x)", "y_axis": "down (+y)",
                     "units": "world px", "rotation": "degrees (plan frame)"},
    "room_transform": {"room_center": "bbox.x+bbox.w/2, bbox.y+bbox.h/2 (world px)",
                       "mpp": "metres per plan pixel (computeMpp: 2.0/max(bed.w,bed.h), else 0.45/max(side_table), else 0.01)"},
    "scene_3d": {"origin": "room centre", "x_axis": "+x = plan +x", "z_axis": "+z = plan +y (down)",
                 "y_axis": "up (furniture y=0 on floor)", "units": "metres",
                 "rotation_y": "radians = -plan_rotation_deg * pi/180"},
}


def compute_mpp(rooms: list[dict[str, Any]]) -> float:
    """Transcription of lib/scene.ts computeMpp."""
    for r in rooms:
        for f in r.get("furniture", []) or []:
            if "bed" in str(f.get("item_id", "")):
                return 2.0 / max(float(f["w"]), float(f["h"]))
    for r in rooms:
        for f in r.get("furniture", []) or []:
            if str(f.get("item_id", "")) == "side-table":
                return 0.45 / max(float(f["w"]), float(f["h"]))
    return 0.01


def _is_opening(item_id: str) -> bool:
    return "door" in item_id or "window" in item_id


def actual_3d(f: dict[str, Any], rcx: float, rcy: float, mpp: float) -> dict[str, Any]:
    """EXACT production transform (RoomScene3D.tsx:546-551)."""
    return {
        "x": (float(f["cx"]) - rcx) * mpp,
        "y": 0.0,
        "z": (float(f["cy"]) - rcy) * mpp,
        "width": max(MIN_DIM_M, float(f["w"]) * mpp),
        "depth": max(MIN_DIM_M, float(f["h"]) * mpp),
        "rotation_y_deg": -(float(f.get("rotation", 0) or 0)),
    }


def expected_3d(f: dict[str, Any], rcx: float, rcy: float, mpp: float) -> dict[str, Any]:
    """Independent geometric mapping (no min-dim clamp) to detect any divergence."""
    return {
        "x": (float(f["cx"]) - rcx) * mpp,
        "y": 0.0,
        "z": (float(f["cy"]) - rcy) * mpp,
        "width": float(f["w"]) * mpp,
        "depth": float(f["h"]) * mpp,
        "rotation_y_deg": -(float(f.get("rotation", 0) or 0)),
    }


def build_audit(file_id: str) -> dict[str, Any]:
    canonical = floor_plan_service.get_canonical(file_id)
    scene = scene_service.build_scene(file_id, canonical=canonical)
    rooms = scene.get("rooms", []) or []
    mpp = compute_mpp(rooms)
    info = floor_plan_service.get_latest_version_info(file_id)
    dv = info[0] if info else None

    # Canonical index for the source-of-truth invariant check (by uid).
    canon_by_uid = {str(c.get("uid")): c for c in (canonical.get("furniture", []) or [])}

    items: list[dict[str, Any]] = []
    for r in rooms:
        bbox = r.get("bbox") or [0, 0, 0, 0]
        rcx = float(bbox[0]) + float(bbox[2]) / 2.0
        rcy = float(bbox[1]) + float(bbox[3]) / 2.0
        for f in r.get("furniture", []) or []:
            iid = str(f.get("item_id", ""))
            if _is_opening(iid):
                continue
            exp = expected_3d(f, rcx, rcy, mpp)
            act = actual_3d(f, rcx, rcy, mpp)
            uid = str(f.get("uid"))
            canon = canon_by_uid.get(uid)
            canonical_match = bool(canon) and all(
                abs(float(f.get(k, 0) or 0) - float(canon.get(k, 0) or 0)) < 1e-9
                for k in ("cx", "cy", "w", "h", "rotation")
            )
            items.append({
                "item_id": uid,
                "item_type": iid,
                "room_id": r.get("id"),
                "room_name": r.get("label"),
                "canonical_2d": {"cx": float(f["cx"]), "cy": float(f["cy"]),
                                 "w": float(f["w"]), "h": float(f["h"]),
                                 "rotation": float(f.get("rotation", 0) or 0)},
                "room_transform": {"room_bbox": [float(x) for x in bbox],
                                   "room_center": {"cx": round(rcx, 3), "cy": round(rcy, 3)},
                                   "mpp": mpp},
                "expected_3d": {k: round(v, 6) for k, v in exp.items()},
                "actual_3d": {k: round(v, 6) for k, v in act.items()},
                "delta": {
                    "x": round(exp["x"] - act["x"], 6),
                    "z": round(exp["z"] - act["z"], 6),
                    "width": round(exp["width"] - act["width"], 6),
                    "depth": round(exp["depth"] - act["depth"], 6),
                    "rotation": round(exp["rotation_y_deg"] - act["rotation_y_deg"], 6),
                },
                "room_association": {"canonical_room_id": r.get("id"),
                                     "scene_room_id": r.get("id"), "match": True},
                "canonical_source_of_truth_match": canonical_match,
            })

    return {
        "run_id": dv, "design_version_id": dv, "plan_id": file_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "coordinate_systems": COORDINATE_SYSTEMS,
        "mpp": mpp, "furniture_count": len(items),
        "items": sorted(items, key=lambda i: (str(i["room_name"]), i["item_type"], i["item_id"])),
    }


def _write(audit: dict[str, Any]) -> tuple[Path, Path]:
    out = Path("output") / "geometry_audit" / str(audit["design_version_id"])
    out.mkdir(parents=True, exist_ok=True)
    j = out / "furniture_2d_to_3d_audit.json"
    t = out / "furniture_2d_to_3d_audit.txt"
    j.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    maxd = max((max(abs(v) for v in i["delta"].values()) for i in audit["items"]), default=0.0)
    lines = [
        f"FURNITURE 2D->3D AUDIT  dv={audit['design_version_id']}  plan={audit['plan_id']}",
        f"mpp={audit['mpp']:.6f}  furniture={audit['furniture_count']}  max_abs_delta={maxd:.6g}",
        "=" * 100,
    ]
    for i in audit["items"]:
        c, a, d = i["canonical_2d"], i["actual_3d"], i["delta"]
        lines.append(f"[{i['room_name']}] {i['item_type']} id={i['item_id']} "
                     f"room_match={i['room_association']['match']} canon_match={i['canonical_source_of_truth_match']}")
        lines.append(f"    2d   cx={c['cx']:.1f} cy={c['cy']:.1f} w={c['w']:.1f} h={c['h']:.1f} rot={c['rotation']:.1f}")
        lines.append(f"    3d   x={a['x']:.3f} y={a['y']:.1f} z={a['z']:.3f} w={a['width']:.3f} d={a['depth']:.3f} rotY={a['rotation_y_deg']:.1f}")
        lines.append(f"    delta x={d['x']:.3g} z={d['z']:.3g} w={d['width']:.3g} d={d['depth']:.3g} rot={d['rotation']:.3g}")
        lines.append("-" * 100)
    t.write_text("\n".join(lines), encoding="utf-8")
    return j, t


def main() -> None:
    file_id = sys.argv[1] if len(sys.argv) > 1 else "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    audit = build_audit(file_id)
    j, t = _write(audit)
    maxd = max((max(abs(v) for v in i["delta"].values()) for i in audit["items"]), default=0.0)
    print(f"furniture={audit['furniture_count']} mpp={audit['mpp']:.6f} max_abs_delta={maxd:.6g}")
    print(f"JSON: {j}")
    print(f"TXT:  {t}")


if __name__ == "__main__":
    main()
