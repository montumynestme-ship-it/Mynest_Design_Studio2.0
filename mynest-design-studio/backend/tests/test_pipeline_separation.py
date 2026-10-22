"""Architectural separation: floor-plan UNDERSTANDING (extraction) must contain no
image-generation model, and a missing/failed Vision response must never fabricate
geometry. The deterministic Three.js/scene path stays independent of the AI render.

Required chain: Floor Plan → OCR → CV Geometry → Object Detection →
Vision Semantic Validation → Canonical JSON → Deterministic 3D.
"""

import subprocess
import sys
from unittest import mock

from app.services import canonical_assembly_service as ca

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"

# Modules that belong to the image-GENERATION stage and must NOT be pulled in by
# importing the extraction / deterministic-3D entrypoints.
_FORBIDDEN = ("nvidia_flux", "generation_service", "ai.registry", "ai.mock_adapter",
              "ai.base", "flux")


def test_extraction_entrypoints_do_not_import_generation():
    """Fresh interpreter: importing the extraction + deterministic-3D entrypoints
    must not load any image-generation module (no FLUX/img2img/provider adapters)."""
    code = (
        "import sys;"
        "import app.services.canonical_assembly_service;"
        "import app.services.scene_service;"
        "import app.services.text_extraction_service;"
        "import app.services.shape_extraction_service;"
        "import app.services.furniture_detection_service;"
        "import app.services.vision_validation_service;"
        "bad=[m for m in sys.modules if any(x in m for x in "
        "('nvidia_flux','generation_service','ai.registry','ai.mock_adapter'))];"
        "print('BAD:'+ ','.join(sorted(bad)))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("BAD:")][0]
    assert line == "BAD:", f"extraction imported generation modules: {line}"


def test_no_image_gen_calls_in_extraction_sources():
    """The extraction modules never call an image-generation provider."""
    import inspect

    from app.services import (
        canonical_assembly_service,
        furniture_detection_service,
        shape_extraction_service,
        text_extraction_service,
        vision_validation_service,
    )
    # Real code identifiers for the generation stage / other providers. (Prose like
    # "no FLUX / no img2img" in docstrings is intentionally NOT matched.)
    for mod in (text_extraction_service, shape_extraction_service,
                furniture_detection_service, vision_validation_service,
                canonical_assembly_service):
        low = inspect.getsource(mod).lower()
        for needle in ("nvidia_flux_adapter", "generation_service", "registry.get_adapter",
                       "pollinations", "bfl_adapter", "import gemini", "google.generativeai"):
            assert needle not in low, f"{mod.__name__} references {needle!r}"


def test_vision_failure_does_not_change_geometry():
    """A failed/raising Vision call must NOT alter furniture or architecture — the
    geometry is deterministic CV/OCR only; vision is advisory."""
    baseline = ca.assemble(FID, include_vision=False)
    with mock.patch(
        "app.services.vision_validation_service.run_vision_validation",
        side_effect=RuntimeError("vision provider down"),
    ):
        degraded = ca.assemble(FID, include_vision=True)
    assert degraded["content_hash"] == baseline["content_hash"]
    assert degraded["furniture"] == baseline["furniture"]
    assert degraded["architecture"] == baseline["architecture"]
    assert str(degraded["vision_validation"]["status"]).startswith("error")


def test_vision_disabled_yields_no_geometry_and_no_fabrication():
    out = ca.assemble(FID, include_vision=False)
    assert out["vision_validation"]["status"] == "skipped"
    # vision produced nothing that could become geometry
    assert out["furniture_candidates"] == []


def test_deterministic_3d_scene_independent_of_generation():
    """scene_service (deterministic 3D) imported alone must not load the AI render."""
    code = (
        "import sys; import app.services.scene_service;"
        "bad=[m for m in sys.modules if 'nvidia_flux' in m or 'generation_service' in m];"
        "print('BAD:'+ ','.join(sorted(bad)))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert [ln for ln in out.stdout.splitlines() if ln.startswith("BAD:")][0] == "BAD:"
