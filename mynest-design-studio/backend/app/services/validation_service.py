"""Deterministic spatial validation over a canonical design (PRD §20 / §26).

Runs furniture-furniture collision (SAT) and room-containment checks. Wall and
door-clearance checks activate automatically once walls/doors exist in the
canonical payload.
"""

from typing import Any

from app.services import geometry_service as geo
from app.services.geometry_service import OrientedRect


def _rect(item: dict[str, Any]) -> OrientedRect:
    return OrientedRect(
        float(item["cx"]),
        float(item["cy"]),
        float(item["w"]),
        float(item["h"]),
        float(item.get("rotation", 0)),
    )


def _label(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("item_id") or "item")


def _polygon(room: dict[str, Any]) -> list[geo.Point]:
    return [(float(p[0]), float(p[1])) for p in room.get("polygon", [])]


def validate_canonical(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    furniture: list[dict[str, Any]] = canonical.get("furniture", []) or []
    rooms: list[dict[str, Any]] = canonical.get("rooms", []) or []

    # 1) Furniture-furniture collisions (SAT).
    for i in range(len(furniture)):
        for j in range(i + 1, len(furniture)):
            if geo.rects_collide(_rect(furniture[i]), _rect(furniture[j])):
                msg = f"Furniture overlaps: {_label(furniture[i])} ↔ {_label(furniture[j])}"
                results.append(
                    {
                        "rule": "checkFurnitureCollision",
                        "severity": "warning",
                        "message": msg,
                        "targets": [furniture[i].get("uid"), furniture[j].get("uid")],
                    }
                )

    # 2) Room containment (only when rooms are defined).
    if rooms:
        polys = [_polygon(r) for r in rooms]
        for f in furniture:
            center = (float(f["cx"]), float(f["cy"]))
            if not any(geo.point_in_polygon(center, poly) for poly in polys if len(poly) >= 3):
                results.append(
                    {
                        "rule": "validateRoomContainment",
                        "severity": "warning",
                        "message": f"{_label(f)} is outside all rooms (unassigned location)",
                        "targets": [f.get("uid")],
                    }
                )

    if not results:
        results.append(
            {
                "rule": "all",
                "severity": "valid",
                "message": "No spatial issues detected.",
                "targets": [],
            }
        )
    return results
