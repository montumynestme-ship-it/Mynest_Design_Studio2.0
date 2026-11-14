"""Raster room reconstruction core — enclosed-region extraction from a wall mask."""

import cv2
import numpy as np

from app.services import room_reconstruction_raster as rr


def _two_room_mask() -> np.ndarray:
    """A 400x400 wall mask: outer box + one middle wall => two enclosed rooms."""
    m = np.zeros((400, 400), np.uint8)
    cv2.rectangle(m, (20, 20), (380, 380), 255, 8)   # outer walls
    cv2.line(m, (200, 20), (200, 380), 255, 8)        # dividing wall
    return m


def test_extract_two_rooms_from_mask() -> None:
    res = rr._extract_rooms(_two_room_mask(), segs=[], openings=[], thickness=8.0, k=1.0)
    assert len(res["rooms"]) == 2
    for room in res["rooms"]:
        assert room["validation_status"] == "CONFIRMED"
        assert room["wall_supported"] is True
        assert len(room["polygon"]) >= 4


def test_open_room_not_enclosed_until_opening_bridged() -> None:
    # Same layout but with a 60px gap (doorway) in the dividing wall: the two
    # rooms merge into one enclosed region until the opening is bridged.
    m = np.zeros((400, 400), np.uint8)
    cv2.rectangle(m, (20, 20), (380, 380), 255, 8)
    cv2.line(m, (200, 20), (200, 170), 255, 8)   # dividing wall, upper part
    cv2.line(m, (200, 230), (200, 380), 255, 8)  # dividing wall, lower part (gap 170-230)
    open_res = rr._extract_rooms(m.copy(), segs=[], openings=[], thickness=8.0, k=1.0)
    assert len(open_res["rooms"]) == 1  # gap leaves them connected

    bridged = rr._extract_rooms(
        m.copy(), segs=[],
        openings=[{"id": "door", "cx": 200, "cy": 200, "w": 12, "h": 70}],
        thickness=8.0, k=1.0,
    )
    assert len(bridged["rooms"]) == 2  # bridging the real opening separates them


def test_no_walls_no_rooms() -> None:
    res = rr._extract_rooms(
        np.zeros((300, 300), np.uint8), segs=[], openings=[], thickness=8.0, k=1.0)
    assert res["rooms"] == []


# --- Goal §1: the wall mask is built from VECTOR walls, never PDF pixels --------

def test_reconstruct_from_vector_walls_ignores_pdf_pixels() -> None:
    """reconstruct_rooms_raster builds the mask ONLY from the extracted vector wall
    segments — it no longer reads the PDF, so a nonexistent path still yields the
    room. Text/furniture/annotation pixels can therefore never become fake walls."""
    walls = [  # a closed rectangular room, world px
        [100, 100, 500, 100], [500, 100, 500, 400],
        [500, 400, 100, 400], [100, 400, 100, 100],
    ]
    res = rr.reconstruct_rooms_raster("/does/not/exist.pdf", walls, [], thickness=10.0)
    assert len(res["rooms"]) == 1
    assert res["rooms"][0]["supporting_wall_count"] >= 4
    assert res["rooms"][0]["wall_supported"] is True
    assert res["stats"]["openings_bridged"] == 0


def test_vector_walls_two_rooms_only_after_validated_opening_bridged() -> None:
    """Extracted vector walls create the mask; a dividing wall with a doorway gap
    leaves one region until the (validated) opening is bridged."""
    walls = [
        [0, 0, 400, 0], [400, 0, 400, 400], [400, 400, 0, 400], [0, 400, 0, 0],
        [200, 0, 200, 150], [200, 250, 200, 400],  # divider with a 100px doorway gap
    ]
    merged = rr.reconstruct_rooms_raster("x.pdf", walls, [], thickness=8.0)
    assert len(merged["rooms"]) == 1  # doorway leaves the two halves connected

    door = {"id": "door_001", "cx": 200, "cy": 200, "w": 16, "h": 110,
            "validation_status": "VALID", "uncertain": False}
    bridged = rr.reconstruct_rooms_raster("x.pdf", walls, [door], thickness=8.0)
    assert len(bridged["rooms"]) == 2
    assert bridged["stats"]["openings_bridged"] == 1
    for room in bridged["rooms"]:
        assert room["supporting_wall_ids"], "every room maps to extracted walls"


def test_raster_reports_deterministic_wall_repair() -> None:
    """§3: reconstruct_rooms_raster repairs the vector walls before rasterization and
    reports raw vs repaired counts (double-line faces collapse to one centreline)."""
    # A rectangular room drawn as DOUBLE lines (two faces per side, 6px apart).
    walls = []
    for off in (0, 6):
        walls += [
            [100 + off, 100 + off, 500 - off, 100 + off],
            [500 - off, 100 + off, 500 - off, 400 - off],
            [500 - off, 400 - off, 100 + off, 400 - off],
            [100 + off, 400 - off, 100 + off, 100 + off],
        ]
    res = rr.reconstruct_rooms_raster("x.pdf", walls, [], thickness=6.0)
    assert res["stats"]["raw_wall_count"] == 8
    assert res["stats"]["repaired_wall_count"] < 8
    assert len(res["rooms"]) == 1


def test_absence_of_morphological_closing() -> None:
    """Verify that global cv2.MORPH_CLOSE is completely absent from reconstruct_rooms_raster."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(rr.reconstruct_rooms_raster))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "MORPH_CLOSE":
            msg = "Found cv2.MORPH_CLOSE attribute access in reconstruct_rooms_raster"
            raise AssertionError(msg)
        if isinstance(node, ast.Name) and node.id == "MORPH_CLOSE":
            msg = "Found MORPH_CLOSE name in reconstruct_rooms_raster"
            raise AssertionError(msg)


def test_opening_bridge_requires_real_geometric_intersection() -> None:
    """Opening bridges must geometrically intersect supporting walls to bridge gaps.
    A door offset away from the wall line must NOT bridge."""
    walls = [
        [0, 0, 400, 0], [400, 0, 400, 400], [400, 400, 0, 400], [0, 400, 0, 0],
        [200, 0, 200, 150], [200, 250, 200, 400],  # divider with gap (150 to 250) at x=200
    ]
    # Door far from the wall line (x=300 instead of x=200)
    displaced_door = {
        "id": "door_displaced", "kind": "door",
        "cx": 300.0, "cy": 200.0, "w": 16.0, "h": 110.0,
        "validation_status": "VALID", "uncertain": False,
    }
    res = rr.reconstruct_rooms_raster("x.pdf", walls, [displaced_door], thickness=8.0)
    # The displaced door must not bridge the doorway at x=200 -> only 1 merged room
    assert res["stats"]["openings_bridged"] == 0
    assert len(res["rooms"]) == 1


def test_room_provenance_derives_from_boundary_edge_coverage() -> None:
    """Every room's supporting_wall_ids and confirmation status derive from boundary edge coverage
    by repaired walls, requiring high coverage (>=70%)."""
    walls = [
        [100, 100, 400, 100],
        [400, 100, 400, 400],
        [400, 400, 100, 400],
        [100, 400, 100, 100],
    ]
    res = rr.reconstruct_rooms_raster("x.pdf", walls, [], thickness=10.0)
    assert len(res["rooms"]) == 1
    room = res["rooms"][0]
    assert room["validation_status"] == "CONFIRMED"
    assert room["geom_source"] == "architectural"
    assert room["assign_method"] == "raster_contour"
    assert room["edge_coverage_avg"] >= 0.70
    assert room["edge_coverage_min"] >= 0.70
    assert len(room["supporting_wall_ids"]) >= 4
    # All supporting walls must be valid wall IDs
    assert all(w.startswith("wall_") for w in room["supporting_wall_ids"])

