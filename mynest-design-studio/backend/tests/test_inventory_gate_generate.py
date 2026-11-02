"""Task 2 — pre-dispatch inventory gate through the REAL generate().

A section whose SELECTED deterministic base DEMONSTRABLY omits required canonical furniture
(inventory_status == MISMATCH) must be refused BEFORE any provider call, while MATCH /
NOT_ASSESSABLE sections dispatch normally (partial-batch). Detector-free, no paid call.

Reproduced case (VERIFIED earlier): for the live design, the "Kitchen" section's base is the
UNCERTAIN kitchen twin that omits the Chimney (which lives in the CONFIRMED combined room),
so assess_section_base_inventory -> MISMATCH, missing=["Chimney"].
"""
from __future__ import annotations

import base64
from io import BytesIO
from unittest import mock

from PIL import Image, ImageDraw

from app.services import floor_plan_service, generation_service, prompt_service
from app.services.ai import registry
from app.services.ai.mock_adapter import MockAdapter

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


class TrackingAdapter(MockAdapter):
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


def test_inventory_mismatch_section_blocked_before_provider(monkeypatch):
    # Use the real (untagged) snapshot; base renders for every eligible section so the gate,
    # not a missing base, is what refuses the MISMATCH section.
    real_snap = floor_plan_service.capture_generation_snapshot
    vid, vnum, canon = real_snap(FID)
    monkeypatch.setattr(floor_plan_service, "capture_generation_snapshot",
                        lambda fid: real_snap(fid))

    sections = prompt_service.get_eligible_sections(canon)
    assert any(s.lower() == "kitchen" for s in sections), sections
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

    # 1) Kitchen (base omits the Chimney) is refused with the structured inventory code ...
    assert "Kitchen" in (resp.failed_rooms or []), resp.failed_rooms
    kitchen_err = " ".join(
        (e.get("detail") or "") for e in (resp.room_errors or []) if e.get("room") == "Kitchen"
    )
    assert "BASE_INVENTORY_MISMATCH" in kitchen_err, resp.room_errors
    # ... and the provider was NEVER invoked for it.
    assert "Kitchen" not in adapter.rooms, adapter.rooms
    # 2) No success image for the blocked section.
    assert not any(img.label == "Kitchen" for img in resp.images)
    # 3) Partial batch: a non-MISMATCH section still reached the provider.
    assert adapter.rooms, "expected at least one unaffected section to dispatch"
    assert any(r != "Kitchen" for r in adapter.rooms), adapter.rooms


def test_match_section_is_not_blocked_by_inventory_gate(monkeypatch):
    # Synthetic MATCH: the selected base scene room contains the only expected furniture uid.
    # (Gate logic is exercised directly to prove MATCH / NOT_ASSESSABLE never block.)
    from app.services import base_inventory_service as B

    def _f(uid, iid):
        return {"uid": uid, "item_id": iid, "name": iid}

    manifest = {"items": [_f("sofa-1", "lounger-sofa")]}
    base_room = {"id": "living", "label": "Living Area", "validation_status": "CONFIRMED",
                 "furniture": [_f("sofa-1", "lounger-sofa")]}
    st, _ = B.assess_section_base_inventory(manifest, base_room, [base_room])
    assert st == "MATCH"  # -> the gate's `if _inv_st == "MISMATCH"` is False -> not blocked

    # NOT_ASSESSABLE (no resolved base room) must NOT be a MISMATCH either.
    st2, _ = B.assess_section_base_inventory(manifest, None, [base_room])
    assert st2 == "NOT_ASSESSABLE"
