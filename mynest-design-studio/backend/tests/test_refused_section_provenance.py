"""A section refused BEFORE any provider call (2D→3D hard refusal / base / membership /
inventory gate) must leave a traceable FAILED provenance breadcrumb on disk — otherwise a
post-hoc investigation (as happened for the Kitchen/Dining failure) cannot recover WHY it
failed. Offline; no DB/provider/network.
"""
from __future__ import annotations

import json

from app.services import generation_service as GS


def test_refused_section_writes_failed_provenance_with_code_and_reason():
    gen = "refused-prov-test"
    room = ("Kitchen", "render a kitchen that contains exactly: 1x Kitchen Base.", 1216, 832)
    GS._save_refused_section_artifact(
        gen, 1, room, "BASE_INVENTORY_MISMATCH",
        "the deterministic base selected for 'Kitchen' omits Kitchen Base",
        provider="fal", model="fal-ai/flux-kontext/dev", seed=123, geometry_hash="abcd1234")

    d = GS.DEBUG_ARTIFACTS_DIR / gen / "room_1_Kitchen"
    resp = json.loads((d / "provider_response_metadata.json").read_text(encoding="utf-8"))
    assert resp["status"] == "failed"
    assert "BASE_INVENTORY_MISMATCH" in resp["error"]
    assert "Kitchen Base" in resp["error"]

    req = json.loads((d / "render_debug.json").read_text(encoding="utf-8"))
    assert req["room_label"] == "Kitchen"
    assert req["geometry_hash"] == "abcd1234"


def test_refused_section_artifact_is_best_effort_never_raises():
    # a bad generation id path component must not raise (provenance is non-critical)
    GS._save_refused_section_artifact(
        "x/y\\z:bad", 2, ("Dining Area", "p", 1216, 832), "SCENE_2D_3D_MISMATCH", "reason",
        provider="fal", model=None, seed=1, geometry_hash="deadbeef")
    # no assertion needed: the call returning without raising is the contract
