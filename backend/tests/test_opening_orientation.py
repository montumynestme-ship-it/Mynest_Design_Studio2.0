"""Door/Window 3D orientation must follow the SOURCE wall, not a bbox-aspect guess.

The 3D window opening is oriented by the opening's `rotation`, which already encodes
its wall direction (the editor stores it; the PDF extraction sets it to the wall
angle). The old renderer ADDED a bbox-aspect term (`w<h ? +90° : 0`), which
double-counts and flips a window perpendicular to its wall whenever the stored
bbox is tall (w<h) — exactly the case for PDF-sourced (supplemental) openings.

These tests assert the DATA contract the corrected `angle = rotation` render relies
on: every window's rotation aligns with its supporting wall, and the old aspect
formula demonstrably mis-orients the tall PDF window.
"""

import math

from app.services import scene_service

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
TOL_DEG = 12.0  # generous; editor/PDF rotations sit within ~0.5° of the wall


def _seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _wall_dir_deg(scene, cx, cy, supporting_wall_id=None):
    sw = {w["id"]: w for w in scene.get("structured_walls", [])}
    if supporting_wall_id and supporting_wall_id in sw:
        w = sw[supporting_wall_id]
        return math.degrees(math.atan2(w["y2"] - w["y1"], w["x2"] - w["x1"])) % 180
    best, bd = 1e9, 0.0
    for s in scene["walls"]:
        d = _seg_dist(cx, cy, *s)
        if d < best:
            best = d
            bd = math.degrees(math.atan2(s[3] - s[1], s[2] - s[0])) % 180
    return bd


def _ang_delta(a, b):
    d = abs((a % 180) - (b % 180))
    return min(d, 180 - d)


def _all_windows(scene):
    out = []
    for r in scene["rooms"]:
        for f in r["furniture"]:
            if "window" in str(f["item_id"]):
                out.append((r["label"], "editor", f))
        for o in r.get("supplemental_windows") or []:
            out.append((r["label"], "pdf", o))
    return out


def test_every_window_rotation_aligns_with_its_wall():
    scene = scene_service.build_scene(FID)
    wins = _all_windows(scene)
    assert wins, "expected windows on the reference plan"
    for label, src, o in wins:
        cx, cy, rot = float(o["cx"]), float(o["cy"]), float(o["rotation"])
        wall = _wall_dir_deg(scene, cx, cy, o.get("supporting_wall_id"))
        # Corrected render: angle == rotation.
        assert _ang_delta(rot, wall) <= TOL_DEG, (
            f"{label} {src} window rotation {rot} not aligned with wall {wall}")


def test_old_aspect_formula_misorients_the_tall_pdf_window():
    scene = scene_service.build_scene(FID)
    tall = [
        (lbl, o) for lbl, src, o in _all_windows(scene)
        if float(o["w"]) < float(o["h"])
    ]
    # The reference plan's supplemental (PDF) window is stored tall (w<h).
    assert tall, "expected at least one tall (w<h) PDF-sourced window"
    for lbl, o in tall:
        cx, cy, rot = float(o["cx"]), float(o["cy"]), float(o["rotation"])
        wall = _wall_dir_deg(scene, cx, cy, o.get("supporting_wall_id"))
        old_angle = (rot + 90.0) % 180  # old formula added +90 when w<h
        new_angle = rot % 180
        assert _ang_delta(new_angle, wall) <= TOL_DEG          # corrected: aligned
        assert _ang_delta(old_angle, wall) >= 90 - TOL_DEG     # old: ~perpendicular
