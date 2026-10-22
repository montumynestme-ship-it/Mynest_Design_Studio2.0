"""AI-render furniture fidelity must NOT be conflated with deterministic fidelity.

Reporting-correction contract (no pipeline/AI change): the deterministic
canonical -> scene fidelity can legitimately be 100%, but the FINAL AI image's
furniture fidelity is only trustworthy when the render was an image-to-image pass
over a geometry-faithful base (backend `assess_ai_render`). In the current
text-to-image mode no base render is consumed, so AI fidelity is "Not Verified"
even when the deterministic scene is perfect. These tests lock that separation.
"""

import base64
import io
import unittest.mock as mock

from PIL import Image

from app.services import generation_service, validation_service
from app.services.ai import registry
from app.services.ai.mock_adapter import MockAdapter

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


def _base_render_dataurl() -> str:
    img = Image.new("RGB", (64, 64), (20, 20, 20))
    for x in range(64):
        img.putpixel((x, 0), (230, 200, 160))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _canonical() -> dict:
    return {
        "furniture": [
            {"uid": "bed", "item_id": "bed", "cx": 500, "cy": 300, "w": 1800, "h": 2000, "rotation": 0},
            {"uid": "st", "item_id": "side-table", "cx": 300, "cy": 300, "w": 450, "h": 450, "rotation": 0},
        ]
    }


def _faithful_scene(c: dict) -> dict:
    furn = [{**f, "type": f["item_id"]} for f in c["furniture"]]
    return {
        "walls": [[0, 0, 2000, 0], [2000, 0, 2000, 2000]],
        "structured_walls": [{"id": "w1"}, {"id": "w2"}],
        "doors": [], "windows": [],
        "rooms": [{
            "label": "Bedroom 1",
            "geometry_source": "architectural",
            "boundary": [[0, 0], [2000, 0], [2000, 2000], [0, 2000], [0, 0]],
            "doors": [], "windows": [], "furniture": furn,
        }],
    }


# Test 1 — deterministic canonical -> scene is 100% faithful.
def test_deterministic_fidelity_is_full():
    c = _canonical()
    report = validation_service.validate_scene_against_canonical(c, _faithful_scene(c))
    assert report["geometry_faithful"] is True
    assert report["checks"]["furniture_transforms"]["passed"] is True
    assert report["checks"]["furniture_count"]["passed"] is True


# Test 2 — AI-render fidelity is NOT verified in text-to-image mode (no base render),
# EVEN when the deterministic scene is perfectly faithful.
def test_ai_fidelity_not_verified_without_base_render():
    faithful_scene_report = {"geometry_faithful": True}
    ai = validation_service.assess_ai_render(
        used_base_render=False, scene_report=faithful_scene_report
    )
    assert ai["geometry_faithful"] is False  # -> UI shows "AI furniture fidelity: Not Verified"
    assert ai["used_base_render"] is False
    assert "no deterministic base render" in ai["reason"]


# The two concepts must not be equal in text-to-image mode: deterministic can be
# faithful while AI-render fidelity is not verified.
def test_deterministic_and_ai_fidelity_are_separate_concepts():
    c = _canonical()
    det = validation_service.validate_scene_against_canonical(c, _faithful_scene(c))
    ai = validation_service.assess_ai_render(
        used_base_render=False, scene_report={"geometry_faithful": det["geometry_faithful"]}
    )
    assert det["geometry_faithful"] is True and ai["geometry_faithful"] is False


# P0 (evidence-driven): an img2img render of a faithful base LOCKS THE INPUT but the
# OUTPUT is UNVERIFIED unless an output check ran. geometry_faithful must NOT be True
# merely because a valid base was used.
def test_ai_fidelity_unverified_for_img2img_without_output_check():
    r = validation_service.assess_ai_render(
        used_base_render=True, scene_report={"geometry_faithful": True}
    )
    assert r["geometry_faithful"] is None          # NOT True — output not checked
    assert r["geometry_status"] == "UNVERIFIED"
    assert r["input_geometry_locked"] is True
    assert r["output_geometry_verified"] is False
    assert "NOT verified" in r["reason"]


# FAIL when the base scene itself was not geometry-faithful (geometry never locked).
def test_ai_fidelity_fail_when_scene_not_faithful():
    r = validation_service.assess_ai_render(
        used_base_render=True, scene_report={"geometry_faithful": False}
    )
    assert r["geometry_faithful"] is False
    assert r["geometry_status"] == "FAIL"
    assert r["input_geometry_locked"] is False


# FAITHFUL only when the input is locked AND an output check confirmed it.
def test_ai_fidelity_faithful_only_with_output_verification():
    r = validation_service.assess_ai_render(
        used_base_render=True, scene_report={"geometry_faithful": True}, output_verified=True
    )
    assert r["geometry_faithful"] is True
    assert r["geometry_status"] == "FAITHFUL"


# End-to-end (mocked provider, no network): a text-to-image adapter that does NOT
# consume control images must report geometry_faithful=False on the response EVEN
# when a base render is supplied — the exact bug this task fixed. Deterministic
# fidelity stays high. Uses MockAdapter (supports_control_image=False).
def test_text_to_image_response_reports_ai_fidelity_not_verified():
    assert MockAdapter().supports_control_image is False  # text-to-image
    with mock.patch.object(registry, "get_adapter", return_value=MockAdapter()), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False), \
         mock.patch.object(generation_service, "AI_ROOM_DELAY_SECONDS", 0.0):
        resp = generation_service.generate(
            file_id=FID, provider="nvidia", count=1,
            design_intent={"style": "modern"},
            requested_rooms=["Living Area"], fresh_generation=True,
            base_renders={"Living Area": _base_render_dataurl(),
                          "living-area": _base_render_dataurl()},
        )
    im = resp.images[0]
    # AI-render fidelity is honestly NOT verified (base render not consumed)...
    assert im.geometry_faithful is not True
    # ...while the deterministic canonical->scene fidelity remains full.
    fid = im.fidelity if isinstance(im.fidelity, dict) else None
    if fid is not None:
        assert fid.get("overall_fidelity") == 1.0
