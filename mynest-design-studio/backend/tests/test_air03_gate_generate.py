"""AIR-03 Task A — generation-level membership blocking through the REAL generate().

A conflicting membership (Dining tagged INDEPENDENT_DINING while geometry shows it shares
the open-plan CONFIRMED room with the kitchen anchor) must be REVIEW_REQUIRED-blocked
BEFORE any provider call, while unrelated rooms proceed (valid base renders supplied).
Uses a tracking control-image adapter (supports_control_image=True) so a provider call
for the blocked group would be observed. No paid API, no real generation.
"""
from __future__ import annotations

import base64
import copy
from io import BytesIO
from unittest import mock

from PIL import Image, ImageDraw

from app.services import floor_plan_service, generation_service, prompt_service
from app.services.ai import registry
from app.services.ai.mock_adapter import MockAdapter

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


class TrackingAdapter(MockAdapter):
    """A control-image adapter that records which rooms reached the provider."""

    name = "tracking"
    model = "tracking-render"
    supports_control_image = True

    def __init__(self):
        self.rooms: list[str] = []

    def generate(self, request):
        self.rooms.append(request.room_label or "")
        return super().generate(request)


def _png_dataurl(w=1216, h=832) -> str:
    img = Image.new("RGB", (w, h), (180, 160, 140))
    ImageDraw.Draw(img).rectangle([0, 0, w, h // 2], fill=(40, 60, 90))  # non-blank
    buf = BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _tag_independent(canon):
    canon = copy.deepcopy(canon)
    for f in canon.get("furniture", []) or []:
        if str(f.get("item_id")) == "dining-table":
            f["room_membership"] = "INDEPENDENT_DINING"  # conflicts with open-plan geometry
    return canon


def test_conflicting_membership_blocks_dining_before_provider(monkeypatch):
    real_snap = floor_plan_service.capture_generation_snapshot
    vid, vnum, canon = real_snap(FID)
    tagged = _tag_independent(canon)
    before = {f["uid"]: (f["cx"], f["cy"], f["w"], f["h"], f["rotation"])
              for f in tagged["furniture"]}

    monkeypatch.setattr(floor_plan_service, "capture_generation_snapshot",
                        lambda fid: (vid, vnum, copy.deepcopy(tagged)))

    # Valid base renders + meta for EVERY eligible section, so unrelated rooms proceed and
    # only the Dining group is refused by the membership gate (not by a missing base).
    sections = prompt_service.get_eligible_sections(tagged)
    base_renders = {s: _png_dataurl() for s in sections}
    base_render_meta = {
        s: {"design_version_id": vid, "room_key": s, "width": 1216, "height": 832}
        for s in sections
    }

    adapter = TrackingAdapter()
    with mock.patch.object(registry, "get_adapter", return_value=adapter), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False):
        resp = generation_service.generate(
            file_id=FID, provider="tracking", count=1,
            design_intent={"style": "Modern"}, all_sections=False,
            fresh_generation=True,
            base_renders=base_renders, base_render_meta=base_render_meta,
        )

    # 1) The Dining group is rejected (not successful) ...
    assert "Dining Area" not in (resp.successful_rooms or [])
    assert "Dining Area" in (resp.failed_rooms or [])
    # ... with a MEMBERSHIP review reason (not a base-render error)
    dining_err = " ".join(
        (e.get("detail") or "") for e in (resp.room_errors or [])
        if e.get("room") == "Dining Area"
    )
    assert "MEMBERSHIP_REVIEW_REQUIRED" in dining_err, resp.room_errors

    # 2) The tracking adapter was NEVER invoked for the blocked Dining group
    assert "Dining Area" not in adapter.rooms, adapter.rooms

    # 3) No success-looking image record for the blocked group
    assert not any(img.label == "Dining Area" for img in resp.images)

    # 4) Unrelated groups still reached the provider (partial execution / isolation) —
    #    the refusal of the Dining group did not prevent other rooms from being rendered.
    assert adapter.rooms, "expected unrelated rooms to reach the provider"
    assert any(r != "Dining Area" for r in adapter.rooms), adapter.rooms

    # 5) Canonical furniture transforms unchanged (no geometry-lock violation raised)
    after = {f["uid"]: (f["cx"], f["cy"], f["w"], f["h"], f["rotation"])
             for f in floor_plan_service.capture_generation_snapshot(FID)[2]["furniture"]}
    assert after == before


def test_membership_block_holds_with_controlnet_enabled(monkeypatch):
    """The AIR-03 membership gate is UPSTREAM of the adapter, so enabling structural
    conditioning (FAL_USE_CONTROLNET=true) cannot let a blocked group reach the provider
    through either path."""
    from app.services.ai import fal_flux_adapter
    monkeypatch.setattr(fal_flux_adapter, "FAL_USE_CONTROLNET", True, raising=False)

    real_snap = floor_plan_service.capture_generation_snapshot
    vid, vnum, canon = real_snap(FID)
    tagged = _tag_independent(canon)
    monkeypatch.setattr(floor_plan_service, "capture_generation_snapshot",
                        lambda fid: (vid, vnum, copy.deepcopy(tagged)))
    sections = prompt_service.get_eligible_sections(tagged)
    base_renders = {s: _png_dataurl() for s in sections}
    base_render_meta = {s: {"design_version_id": vid, "room_key": s, "width": 1216, "height": 832}
                        for s in sections}

    adapter = TrackingAdapter()
    with mock.patch.object(registry, "get_adapter", return_value=adapter), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False):
        resp = generation_service.generate(
            file_id=FID, provider="tracking", count=1,
            design_intent={"style": "Modern"}, all_sections=False, fresh_generation=True,
            base_renders=base_renders, base_render_meta=base_render_meta,
        )
    assert "Dining Area" in (resp.failed_rooms or [])
    assert "Dining Area" not in adapter.rooms  # blocked before the provider, controlnet on
