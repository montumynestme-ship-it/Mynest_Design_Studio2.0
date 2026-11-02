"""Coordinate-system conventions for the deterministic 2D→3D reconstruction.

Locks the canonical world-px ↔ millimetre ↔ Three.js-metre conversions, their scale
consistency, and the direction/angle arithmetic. Tolerances are EXACT where the maths is
exact (linear scaling of floats) — no arbitrary epsilons. Pure; no DB/provider/network.

Reference (coordinates.py): canonical world px (scale 2.0, origin top-left, y-down),
MPP = 0.01 (1 px = 10 mm = 0.01 m); Three.js metres = px × MPP.
"""
from __future__ import annotations

import pytest

from app.services import coordinates as C


def test_default_scale_and_mpp():
    assert C.DEFAULT_WORLD_SCALE == 2.0
    assert C.DEFAULT_MPP == 0.01  # 1 world px = 10 mm


@pytest.mark.parametrize("px", [0.0, 1.0, 180.0, 285.0, 1000.0, 1216.0])
def test_world_px_to_three_and_back_roundtrips_exactly(px):
    m = C.world_to_three(px)
    assert m == pytest.approx(px * 0.01, rel=0, abs=1e-12)
    assert C.three_to_world(m) == pytest.approx(px, rel=0, abs=1e-9)


@pytest.mark.parametrize("px", [1.0, 180.0, 285.0, 1000.0])
def test_world_px_to_mm_and_back_roundtrips(px):
    mm = C.world_to_mm(px)            # px * 0.01 * 1000 = px * 10
    assert mm == pytest.approx(px * 10.0, rel=0, abs=1e-9)
    assert C.mm_to_world(mm) == pytest.approx(px, rel=0, abs=1e-9)


@pytest.mark.parametrize("mm", [10.0, 1800.0, 2850.0])
def test_mm_to_three_and_back(mm):
    m = C.mm_to_three(mm)
    assert m == pytest.approx(mm / 1000.0, rel=0, abs=1e-12)
    assert C.three_to_mm(m) == pytest.approx(mm, rel=0, abs=1e-9)


@pytest.mark.parametrize("px", [1.0, 180.0, 285.0, 1000.0])
def test_scale_consistency_px_to_metres_is_the_same_via_mm(px):
    # The two routes to metres must agree: world_to_three(px) == world_to_mm(px) mm / 1000.
    assert C.world_to_three(px) == pytest.approx(C.world_to_mm(px) / 1000.0, rel=0, abs=1e-12)


def test_real_sofa_width_is_physically_plausible():
    # a real canonical sofa width (285 world px, from design 85759b78) → 2.85 m, not 0.285/28.5
    assert C.world_to_mm(285.0) == pytest.approx(2850.0)        # 2.85 m — plausible
    assert C.world_to_three(285.0) == pytest.approx(2.85)


# ── direction / angle arithmetic (door/window + furniture orientation) ──────────

@pytest.mark.parametrize("d,deg", [("N", 0.0), ("E", 90.0), ("S", 180.0), ("W", 270.0)])
def test_direction_rotation_roundtrip(d, deg):
    assert C.direction_to_rotation(d) == deg
    assert C.rotation_to_direction(deg) == d


def test_rotation_to_direction_quadrants():
    assert C.rotation_to_direction(44.9) == "N"
    assert C.rotation_to_direction(45.0) == "E"
    assert C.rotation_to_direction(134.9) == "E"
    assert C.rotation_to_direction(135.0) == "S"
    assert C.rotation_to_direction(315.0) == "N"


def test_circular_angle_diff_wraps():
    assert C.circular_angle_diff(359.0, 1.0) == pytest.approx(2.0)
    assert C.circular_angle_diff(90.0, 270.0) == pytest.approx(180.0)
    assert C.circular_angle_diff(0.0, 0.0) == 0.0


def test_transform_box_three_frame_to_canonical_px():
    box = {"cx": 2.85, "cy": 5.0, "w": 2.85, "h": 1.35}     # metres (three frame)
    out = C.transform_box_to_canonical(box, "three")
    assert out["coordinate_frame"] == "canonical_world_px"
    assert out["cx"] == pytest.approx(285.0)                 # 2.85 m → 285 world px
    assert out["w"] == pytest.approx(285.0)
