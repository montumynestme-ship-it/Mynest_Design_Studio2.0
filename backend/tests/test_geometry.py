import math
from typing import Any

from app.services import validation_service
from app.services.geometry_service import (
    OrientedRect,
    calculate_room_area_m2,
    point_in_polygon,
    rects_collide,
)


def test_room_area_rectangle() -> None:
    # 5000mm x 4000mm = 20 m²
    poly = [(1000, 1000), (6000, 1000), (6000, 5000), (1000, 5000)]
    assert math.isclose(calculate_room_area_m2(poly), 20.0, rel_tol=1e-9)


def test_room_area_degenerate() -> None:
    assert calculate_room_area_m2([(0, 0), (1, 1)]) == 0.0


def test_collision_overlapping() -> None:
    a = OrientedRect(0, 0, 1000, 1000, 0)
    b = OrientedRect(500, 0, 1000, 1000, 0)  # overlaps a
    assert rects_collide(a, b) is True


def test_collision_separated() -> None:
    a = OrientedRect(0, 0, 1000, 1000, 0)
    b = OrientedRect(3000, 0, 1000, 1000, 0)  # far apart
    assert rects_collide(a, b) is False


def test_collision_rotated_touch() -> None:
    a = OrientedRect(0, 0, 1000, 200, 0)
    b = OrientedRect(0, 0, 1000, 200, 90)  # cross shape -> overlap
    assert rects_collide(a, b) is True


def test_point_in_polygon() -> None:
    square = [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert point_in_polygon((50, 50), square) is True
    assert point_in_polygon((150, 50), square) is False


def test_validate_reports_collision_and_containment() -> None:
    canonical: dict[str, Any] = {
        "rooms": [
            {"id": "r1", "name": "Living", "polygon": [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]}
        ],
        "furniture": [
            {
                "uid": "a",
                "item_id": "sofa",
                "cx": 400,
                "cy": 400,
                "w": 300,
                "h": 200,
                "rotation": 0,
            },
            {
                "uid": "b",
                "item_id": "table",
                "cx": 450,
                "cy": 400,
                "w": 300,
                "h": 200,
                "rotation": 0,
            },
            {
                "uid": "c",
                "item_id": "lamp",
                "cx": 5000,
                "cy": 5000,
                "w": 100,
                "h": 100,
                "rotation": 0,
            },
        ],
    }
    results = validation_service.validate_canonical(canonical)
    rules = {r["rule"] for r in results}
    assert "checkFurnitureCollision" in rules  # a and b overlap
    assert "validateRoomContainment" in rules  # c is outside the room


def test_validate_clean_layout() -> None:
    canonical: dict[str, Any] = {"furniture": []}
    results = validation_service.validate_canonical(canonical)
    assert results == [
        {
            "rule": "all",
            "severity": "valid",
            "message": "No spatial issues detected.",
            "targets": [],
        }
    ]
