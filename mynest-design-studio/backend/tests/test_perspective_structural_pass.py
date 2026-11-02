"""DB-free tests for the PROTOTYPE perspective structural pass.

Expected values are independent of the renderer: projection is checked against hand-computed
pinhole math, the camera against the ported solver's documented behaviour, and geometry
inclusion against the synthetic scene's known counts. No DB, no fal.
"""

import math
from io import BytesIO

from PIL import Image

from app.services import perspective_structural_pass as psp


def _scene():
    room = {
        "id": "bedroom-1", "label": "Bedroom 1", "bbox": [200, 160, 800, 480],
        "boundary": [[200, 160], [1000, 160], [1000, 640], [200, 640]],
        "furniture": [
            {"uid": "bed-1", "item_id": "bed", "cx": 420, "cy": 300, "w": 360, "h": 400, "rotation": 0},
            {"uid": "wd-1", "item_id": "wardrobe", "cx": 850, "cy": 250, "w": 220, "h": 110, "rotation": 0},
            {"uid": "st-1", "item_id": "side-table", "cx": 650, "cy": 300, "w": 90, "h": 90, "rotation": 0},
            {"uid": "tag", "item_id": "room-tag", "cx": 0, "cy": 0, "w": 0, "h": 0, "rotation": 0},
        ],
    }
    return {"page": {"width": 1200, "height": 800, "scale": 2.0}, "walls": [], "rooms": [room]}, room


# ── projection math vs independent pinhole computation ─────────────────────────────
def test_projection_matches_hand_computed_pinhole():
    eye = (0.0, 0.0, 10.0)
    za = psp._norm(psp._sub(eye, (0.0, 0.0, 0.0)))   # (0,0,1)
    xa = psp._norm(psp._cross((0.0, 1.0, 0.0), za))  # (1,0,0)
    ya = psp._cross(za, xa)                          # (0,1,0)
    W, H = 1216, 832
    f = 1.0 / math.tan((psp.AI_FOV / 2) * psp._DEG)

    origin = psp._project((0, 0, 0), eye, (xa, ya, za), f, W / H, W, H)
    assert origin is not None
    assert abs(origin[0] - W / 2) < 0.5 and abs(origin[1] - H / 2) < 0.5

    right = psp._project((1, 0, 0), eye, (xa, ya, za), f, W / H, W, H)
    assert right is not None and right[0] > W / 2 and abs(right[1] - H / 2) < 0.5
    # independent expected x: ndc_x = (f/aspect)*1/10 → screen
    ndc_x = (f / (W / H)) * 1.0 / 10.0
    assert abs(right[0] - (ndc_x * 0.5 + 0.5) * W) < 0.5

    assert psp._project((0, 0, 11), eye, (xa, ya, za), f, W / H, W, H) is None  # behind camera


# ── camera port: deterministic 3/4 dollhouse ──────────────────────────────────────
def test_solve_ai_camera_is_deterministic_dollhouse():
    pts = [(-1, -1), (1, -1), (1, 1), (-1, 1)]  # symmetric → corner (1,1) wins by tie-order
    cam = psp.solve_ai_camera(pts, fit_dist=10.0, fov=psp.AI_FOV, aspect=1216 / 832)
    px, py, pz = cam["position"]
    assert px > 0 and py > 0 and pz > 0           # elevated +,+,+ corner
    assert abs(math.sqrt(px * px + py * py + pz * pz) - 10.0) < 1e-6  # magnitude == fit_dist
    assert psp.solve_ai_camera(pts, 10.0, psp.AI_FOV, 1216 / 832)["position"] == cam["position"]


# ── geometry inclusion + provenance ────────────────────────────────────────────────
def test_renders_walls_and_furniture_boxes():
    scene, room = _scene()
    png, prov = psp.render_structural_pass(scene, room)
    assert prov["walls_drawn"] == 4
    assert prov["furniture_total"] == 3            # room-tag excluded
    assert prov["furniture_drawn"] == 3
    assert prov["coordinate_frame"] == "perspective_structural_v1"
    assert (prov["width"], prov["height"]) == (1216, 832)
    assert prov["camera_position"][1] > 0          # elevated camera
    img = Image.open(BytesIO(png)).convert("RGB")
    nonwhite = sum(1 for p in img.getdata() if p != (255, 255, 255))
    assert nonwhite > 500                          # real line content


# ── canonical geometry is read-only ─────────────────────────────────────────────────
def test_canonical_not_mutated():
    scene, room = _scene()
    before = [dict(f) for f in room["furniture"]]
    psp.render_structural_pass(scene, room)
    assert room["furniture"] == before


# ── determinism + PNG contract ──────────────────────────────────────────────────────
def test_deterministic_png_bytes():
    scene, room = _scene()
    a, _ = psp.render_structural_pass(scene, room)
    b, _ = psp.render_structural_pass(scene, room)
    assert a == b
    assert a[:8] == b"\x89PNG\r\n\x1a\n"


# ── fail-safe: empty / incomplete geometry ─────────────────────────────────────────
def test_empty_room_renders_walls_only():
    room = {"id": "r", "label": "R", "bbox": [0, 0, 500, 400], "boundary": None, "furniture": []}
    scene = {"page": {"width": 500, "height": 400}, "walls": [], "rooms": [room]}
    png, prov = psp.render_structural_pass(scene, room)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert prov["furniture_total"] == 0 and prov["walls_drawn"] == 4  # bbox fallback walls


def test_incomplete_furniture_skipped_not_drawn():
    room = {"id": "r", "label": "R", "bbox": [0, 0, 500, 400], "boundary": None,
            "furniture": [{"uid": "x", "item_id": "bed", "cx": 250, "cy": 200, "rotation": 0}]}  # no w/h
    scene = {"page": {"width": 500, "height": 400}, "walls": [], "rooms": [room]}
    _png, prov = psp.render_structural_pass(scene, room)
    assert prov["furniture_total"] == 1 and prov["furniture_drawn"] == 0  # never drawn at a guess
