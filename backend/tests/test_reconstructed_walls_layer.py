"""Option 2 — additive, pixel-only reconstructed-walls (centerline) layer.

`wall_reconstruction.build_reconstructed_walls` derives wall CENTERLINES from the
extracted face strokes and attaches a per-wall thickness ONLY where a genuine double-line
face pair supports it (MEASURED_FROM_PAIRED_FACES); single-face/unpaired bands keep the
configured 10.0 px fallback (CONFIGURED_FALLBACK); an implausible separation is UNVERIFIED.
The layer is in WORLD PIXELS only (no mm — mpp is uncalibrated).

Invariant under test: this layer NEVER changes the authoritative 179 face-stroke
`structured_walls` (IDs, endpoints, count, thickness). Deterministic, offline, no AI.
"""

import math
import os

import pytest

from app.services import architectural_service as A
from app.services import geometry_extraction_service as G
from app.services import wall_reconstruction as W

PDF = os.path.join(
    "storage", "floor_plans", "unassigned", "unassigned",
    "f6b65d2b-4f96-4931-9f08-67dbd09776f6", "original.pdf",
)
ALLOWED_SOURCES = {"MEASURED_FROM_PAIRED_FACES", "CONFIGURED_FALLBACK", "UNVERIFIED"}


def test_paired_faces_measure_thickness_in_px():
    """Two parallel faces 20 px apart collapse to one centerline with a MEASURED thickness."""
    faces = [[0.0, 100.0, 200.0, 100.0], [0.0, 120.0, 200.0, 120.0]]
    out = W.build_reconstructed_walls(faces)
    assert len(out) == 1
    band = out[0]
    assert band["id"] == "rwall_001"
    assert band["thickness_source"] == "MEASURED_FROM_PAIRED_FACES"
    assert band["thickness_units"] == "px"
    assert band["thickness_px"] == pytest.approx(20.0, abs=0.01)
    assert set(band["source_wall_ids"]) == {"wall_001", "wall_002"}


def test_single_face_keeps_configured_fallback():
    """A lone face has no measurable thickness -> configured 10.0 px fallback."""
    out = W.build_reconstructed_walls([[0.0, 100.0, 200.0, 100.0]])
    assert len(out) == 1
    assert out[0]["thickness_source"] == "CONFIGURED_FALLBACK"
    assert out[0]["thickness_px"] == 10.0
    assert out[0]["thickness_confidence"] == "none"


def test_two_far_apart_walls_are_not_paired():
    """Two separate parallel walls (far apart) must NOT be fused into one measured wall."""
    faces = [[0.0, 100.0, 200.0, 100.0], [0.0, 400.0, 200.0, 400.0]]
    out = W.build_reconstructed_walls(faces)
    assert len(out) == 2
    assert all(b["thickness_source"] == "CONFIGURED_FALLBACK" for b in out)


def test_empty_and_degenerate_input():
    assert W.build_reconstructed_walls([]) == []
    assert W.build_reconstructed_walls([[5.0, 5.0, 5.0, 5.0]]) == []  # zero-length -> dropped


@pytest.mark.skipif(not os.path.exists(PDF), reason="plan f6b65d2b original.pdf not present")
def test_f6b65d2b_reconstructed_layer_and_face_invariant():
    geo = G.extract_walls(PDF)
    walls = geo["walls"]

    # INVARIANT: the authoritative face-stroke layer is untouched by Option 2.
    sw = geo["structured_walls"]
    assert len(sw) == 179
    assert all(w["thickness"] == 10.0 for w in sw)
    assert all(w["thickness_source"] == "CONFIGURED_FALLBACK" for w in sw)

    recon = W.build_reconstructed_walls(walls)
    # One derived centerline per repaired band; deterministic counts for this fixture.
    assert len(recon) == 56
    measured = [b for b in recon if b["thickness_source"] == "MEASURED_FROM_PAIRED_FACES"]
    fallback = [b for b in recon if b["thickness_source"] == "CONFIGURED_FALLBACK"]
    unverified = [b for b in recon if b["thickness_source"] == "UNVERIFIED"]
    assert len(measured) == 21        # genuine double-line pairs
    assert len(fallback) == 34        # thin / single-face walls -> honest fallback
    assert len(unverified) == 1       # a separation outside the plausible band, not trusted
    assert len(measured) + len(fallback) + len(unverified) == 56

    # Every band: px units, allowed classification, provenance to real face IDs.
    valid_ids = {f"wall_{i + 1:03d}" for i in range(179)}
    for b in recon:
        assert b["thickness_units"] == "px"
        assert b["thickness_source"] in ALLOWED_SOURCES
        assert b["source_wall_ids"] and set(b["source_wall_ids"]) <= valid_ids
        assert b["id"].startswith("rwall_")

    # Measured thicknesses are plausible (within the pairing band) — never noise/zero.
    tol = W.measure_tolerances([tuple(map(float, w)) for w in walls
                                if math.hypot(w[2] - w[0], w[3] - w[1]) > 0])
    th = tol["thickness"]
    lo, hi = th * 0.65, min(tol["pair_tol"], th * 1.35)
    for b in measured:
        assert lo <= b["thickness_px"] <= hi


def test_build_structured_walls_face_layer_unchanged_count():
    """The face builder still emits exactly one record per input edge (no collapse)."""
    walls = [[0.0, 0.0, 100.0, 0.0], [0.0, 10.0, 100.0, 10.0], [0.0, 0.0, 0.0, 80.0]]
    assert len(A.build_structured_walls(walls)) == len(walls)
