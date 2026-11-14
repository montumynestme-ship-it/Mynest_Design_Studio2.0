"""Wall-thickness PROVENANCE is honest and additive.

Investigation established that `structured_walls` are individual face-strokes
(1:1 with raw PDF edges), that no validated per-wall thickness measurement exists,
and that `measure_tolerances` returns a plan-wide reconstruction TOLERANCE — never a
per-wall thickness. So every structured wall keeps its configured `thickness: 10.0`
and is explicitly tagged ``thickness_source="CONFIGURED_FALLBACK"`` / ``thickness_units="px"``.

These tests assert the provenance tags are present on BOTH builders, that the
configured fallback is preserved exactly, that the diagnostic tolerance is never
assigned to a wall, and that the wall inventory/IDs/endpoints are unchanged by the
additive metadata. Deterministic, offline, no AI, no network.
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


def test_build_structured_walls_tags_configured_fallback():
    """architectural_service.build_structured_walls: additive provenance, 1:1, 10.0 kept."""
    walls = [[0.0, 0.0, 100.0, 0.0], [0.0, 0.0, 0.0, 80.0]]
    out = A.build_structured_walls(walls, ["#141414", "#141414"])
    assert len(out) == len(walls)  # 1:1 with raw face-strokes — no collapse
    for sw in out:
        assert sw["thickness"] == 10.0                      # configured fallback preserved exactly
        assert sw["thickness_source"] == "CONFIGURED_FALLBACK"
        assert sw["thickness_units"] == "px"
    # Endpoints are untouched by the metadata.
    assert (out[0]["x1"], out[0]["y1"], out[0]["x2"], out[0]["y2"]) == (0.0, 0.0, 100.0, 0.0)


@pytest.mark.skipif(not os.path.exists(PDF), reason="plan f6b65d2b original.pdf not present")
def test_f6b65d2b_179_walls_all_configured_fallback():
    """Against the immutable original.pdf: 179 face-strokes, every one a tagged fallback."""
    geo = G.extract_walls(PDF)
    sw = geo["structured_walls"]
    # Inventory unchanged: exactly 179, 1:1 with the raw edges, contiguous IDs.
    assert len(sw) == 179
    assert len(sw) == len(geo["walls"])
    assert [w["id"] for w in sw] == [f"wall_{i + 1:03d}" for i in range(179)]
    # Every wall keeps the configured fallback and carries honest provenance.
    assert all(w["thickness"] == 10.0 for w in sw)
    assert all(w["thickness_source"] == "CONFIGURED_FALLBACK" for w in sw)
    assert all(w["thickness_units"] == "px" for w in sw)
    # Endpoints match the raw edges exactly (additive metadata moved nothing).
    for w, raw in zip(sw, geo["walls"], strict=True):
        assert (w["x1"], w["y1"], w["x2"], w["y2"]) == (
            round(raw[0], 2), round(raw[1], 2), round(raw[2], 2), round(raw[3], 2),
        )


@pytest.mark.skipif(not os.path.exists(PDF), reason="plan f6b65d2b original.pdf not present")
def test_diagnostic_tolerance_never_assigned_as_wall_thickness():
    """The plan-wide measure_tolerances value is a TOLERANCE, not a per-wall thickness."""
    geo = G.extract_walls(PDF)
    segs = [tuple(map(float, w)) for w in geo["walls"]
            if math.hypot(w[2] - w[0], w[3] - w[1]) > 0]
    tol = W.measure_tolerances(segs)["thickness"]
    assert tol > 10.0  # it is a different, larger scalar (~30px) — not the render thickness
    # No wall ever adopts the diagnostic tolerance as its thickness.
    assert all(w["thickness"] == 10.0 and w["thickness"] != tol
               for w in geo["structured_walls"])


def test_provenance_fields_are_additive_not_replacing():
    """Existing keys survive; only the two provenance keys are new."""
    out = A.build_structured_walls([[0.0, 0.0, 10.0, 0.0]], ["#141414"])[0]
    for required in ("id", "x1", "y1", "x2", "y2", "length", "angle_deg",
                     "thickness", "height", "color"):
        assert required in out, f"existing key dropped: {required}"
    assert out["thickness_source"] == "CONFIGURED_FALLBACK"
    assert out["thickness_units"] == "px"


def test_legacy_wall_record_without_provenance_still_consumed():
    """Backward-compat: a consumer must accept an OLD wall record lacking the new
    provenance keys (scene_bridge reads only `thickness`, with a default)."""
    from app.services.ml.scene_bridge import detections_to_3d_scene

    legacy_wall = {  # no thickness_source / thickness_units — a pre-change record
        "id": "wall_001", "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 0.0,
        "length": 100.0, "angle_deg": 0.0, "thickness": 10.0, "height": 2.7,
        "color": "#141414",
    }
    scene3d = detections_to_3d_scene([], structured_walls=[legacy_wall], mpp=0.01)
    walls3d = scene3d["walls"]
    assert len(walls3d) == 1 and walls3d[0]["id"] == "wall_001"
    # thickness still derived from the legacy field (10.0 px -> metres via mpp).
    assert walls3d[0]["thickness"] == pytest.approx(10.0 * 0.01, rel=1e-6)
