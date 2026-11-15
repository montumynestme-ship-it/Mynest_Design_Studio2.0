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
    # DEF-2: a measured paired centreline now spans ONLY the two faces' shared overlap; each
    # pair's unmatched TAILS are preserved as separate single-face CONFIGURED_FALLBACK bands
    # (no wall portion discarded, no measured claim over single-face regions). Geometrically
    # justified change vs the previous 56/21/34/1: the 21 genuine pairs are UNCHANGED (same
    # pairs, now trimmed to overlap); the 25 extra bands are the preserved tails, all fallback
    # — so fallback 34 -> 59 and total 56 -> 81, measured and unverified unchanged.
    measured = [b for b in recon if b["thickness_source"] == "MEASURED_FROM_PAIRED_FACES"]
    fallback = [b for b in recon if b["thickness_source"] == "CONFIGURED_FALLBACK"]
    unverified = [b for b in recon if b["thickness_source"] == "UNVERIFIED"]
    assert len(measured) == 21        # genuine double-line pairs (STABLE — overlap only)
    assert len(fallback) == 59        # single-face walls + preserved paired tails -> fallback
    assert len(unverified) == 1       # a separation outside the plausible band, not trusted
    assert len(recon) == 81
    assert len(measured) + len(fallback) + len(unverified) == 81

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


# ── DEF-2: paired-face OVERLAP (not union) + unmatched-tail preservation ───────────────
# Explicit tolerances make pairing deterministic (thickness 20 px → pairs at a 20 px gap,
# within [13, 27]); independent of the valley-detection heuristic.
TOL = {"thickness": 20.0, "pair_tol": 32.0, "merge_gap": 40.0, "snap_tol": 32.0}


def _by_source(recon):
    m = [b for b in recon if b["thickness_source"] == "MEASURED_FROM_PAIRED_FACES"]
    f = [b for b in recon if b["thickness_source"] == "CONFIGURED_FALLBACK"]
    u = [b for b in recon if b["thickness_source"] == "UNVERIFIED"]
    return m, f, u


def test_def2_partial_overlap_measures_overlap_and_keeps_tails():
    # A [0,200]@y100, B [80,280]@y120 → overlap [80,200]; tails [0,80]@100 and [200,280]@120.
    out = W.build_reconstructed_walls([[0, 100, 200, 100], [80, 120, 280, 120]], TOL)
    m, f, u = _by_source(out)
    assert len(m) == 1 and len(f) == 2 and len(u) == 0
    mb = m[0]
    assert mb["seg"][0] == pytest.approx(80.0) and mb["seg"][2] == pytest.approx(200.0)
    assert mb["seg"][1] == pytest.approx(110.0)  # centreline midway between the faces
    assert mb["thickness_px"] == pytest.approx(20.0)
    assert set(mb["source_wall_ids"]) == {"wall_001", "wall_002"}
    # Tails are single-face fallback at each face's OWN centreline.
    xs = sorted((b["seg"][0], b["seg"][2], b["seg"][1]) for b in f)
    assert xs[0] == pytest.approx((0.0, 80.0, 100.0))    # left tail on face A (y=100)
    assert xs[1] == pytest.approx((200.0, 280.0, 120.0))  # right tail on face B (y=120)
    assert all(len(b["source_wall_ids"]) == 1 for b in f)


def test_def2_full_overlap_no_tails():
    out = W.build_reconstructed_walls([[0, 100, 200, 100], [0, 120, 200, 120]], TOL)
    m, f, u = _by_source(out)
    assert len(m) == 1 and len(f) == 0 and len(u) == 0
    assert m[0]["seg"][0] == pytest.approx(0.0) and m[0]["seg"][2] == pytest.approx(200.0)


def test_def2_one_face_contained_two_tails_on_longer_face():
    # A [0,200]@100 contains B [50,150]@120 → overlap [50,150]; tails [0,50] and [150,200] of A.
    out = W.build_reconstructed_walls([[0, 100, 200, 100], [50, 120, 150, 120]], TOL)
    m, f, u = _by_source(out)
    assert len(m) == 1 and len(f) == 2
    assert m[0]["seg"][0] == pytest.approx(50.0) and m[0]["seg"][2] == pytest.approx(150.0)
    assert all(b["seg"][1] == pytest.approx(100.0) for b in f)  # both tails on face A


def test_def2_no_longitudinal_overlap_is_not_paired():
    # A [0,80]@100, B [120,200]@120 → no overlap → NOT a measured pair; both fallback.
    out = W.build_reconstructed_walls([[0, 100, 80, 100], [120, 120, 200, 120]], TOL)
    m, f, _ = _by_source(out)
    assert len(m) == 0 and len(f) == 2


def test_def2_reversed_endpoints_normalized():
    # Face A given reversed; must behave identically to the full-overlap case.
    out = W.build_reconstructed_walls([[200, 100, 0, 100], [0, 120, 200, 120]], TOL)
    m, f, _ = _by_source(out)
    assert len(m) == 1 and len(f) == 0
    assert m[0]["seg"][0] == pytest.approx(0.0) and m[0]["seg"][2] == pytest.approx(200.0)


def test_def2_incompatible_far_faces_not_measured():
    # 100 px apart → outside the pairing band [13,27] → not paired → two fallback bands.
    out = W.build_reconstructed_walls([[0, 100, 200, 100], [0, 200, 200, 200]], TOL)
    m, f, _ = _by_source(out)
    assert len(m) == 0 and len(f) == 2


def test_def2_collinear_fragments_merge_to_one_wall():
    # Three collinear fragments on one face → single merged band (repair_walls), single-face.
    out = W.build_reconstructed_walls(
        [[0, 100, 80, 100], [80, 100, 160, 100], [160, 100, 240, 100]], TOL
    )
    m, f, _ = _by_source(out)
    assert len(m) == 0 and len(f) == 1
    assert f[0]["seg"][0] == pytest.approx(0.0) and f[0]["seg"][2] == pytest.approx(240.0)


def test_def2_genuine_gap_is_not_bridged():
    # Gap 120 px >> merge_gap 40 → the two fragments stay separate (no fabricated continuity).
    out = W.build_reconstructed_walls([[0, 100, 80, 100], [200, 100, 280, 100]], TOL)
    _, f, _ = _by_source(out)
    assert len(f) == 2


def test_def2_source_provenance_paired_and_unpaired():
    out = W.build_reconstructed_walls([[0, 100, 200, 100], [80, 120, 280, 120]], TOL)
    m, f, _ = _by_source(out)
    assert set(m[0]["source_wall_ids"]) == {"wall_001", "wall_002"}  # paired → both faces
    tail_ids = {tuple(b["source_wall_ids"]) for b in f}
    assert tail_ids == {("wall_001",), ("wall_002",)}  # each tail → its single source face


def test_def2_deterministic_repeated_runs():
    faces = [[0, 100, 200, 100], [80, 120, 280, 120]]
    assert W.build_reconstructed_walls(faces, TOL) == W.build_reconstructed_walls(faces, TOL)


def test_def2_no_measured_claim_beyond_overlap_extent():
    # The measured band must never extend past the shared interval (the core DEF-2 invariant).
    out = W.build_reconstructed_walls([[0, 100, 200, 100], [80, 120, 280, 120]], TOL)
    m, _, _ = _by_source(out)
    assert m[0]["seg"][0] >= 80.0 - 1e-6 and m[0]["seg"][2] <= 200.0 + 1e-6
