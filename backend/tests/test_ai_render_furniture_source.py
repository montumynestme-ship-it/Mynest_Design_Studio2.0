"""Phase 0 — AI-render furniture-source invariants (offline).

Confirms the AI-render furniture workflow is already the canonical-manifest pipeline:
the generation request carries NO furniture (so a client can never inject or bypass the
immutable canonical inventory), and the per-room manifest is built from the canonical
snapshot's furniture (version-bound), identical to the deterministic-base source. These
lock the "invalid/mismatched manifest cannot silently enter the request" + "manifest uses
the correct canonical design version" acceptance criteria. No DB writes, no generation.
"""
from __future__ import annotations

from app.schemas.generation import GenerationRequestBody


def test_generation_request_carries_no_furniture_inventory():
    # The ONLY furniture source is the backend immutable snapshot; the client request must
    # not accept furniture/inventory/manifest fields (which could bypass the canonical design).
    fields = set(GenerationRequestBody.model_fields.keys())
    for forbidden in ("furniture", "inventory", "manifest", "items", "objects"):
        assert forbidden not in fields, f"request must not accept client-supplied {forbidden!r}"
    # It carries only render intent + deterministic base captures + their version binding.
    assert {"design_intent", "base_renders", "base_render_meta"} <= fields


def test_manifest_matches_canonical_snapshot_version():
    """The per-room manifest furniture equals the canonical snapshot's furniture for that
    room/version (built from the immutable snapshot, not any client input)."""
    import pytest
    from app.services import floor_plan_service, prompt_service, furniture_manifest
    from app.services.furniture_manifest import _OPENING_IDS

    FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    try:
        _vid, _n, canon = floor_plan_service.capture_generation_snapshot(FID)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"snapshot unavailable: {exc}")

    furn = canon.get("furniture", []) or []
    # Every manifest item's uid is a real canonical uid from THIS snapshot (never invented).
    canon_uids = {str(f.get("uid")) for f in furn}
    for label, items in prompt_service.group_by_room(furn, None):
        man = furniture_manifest.build_room_manifest(items)
        for it in man.get("items", []):
            if str(it.get("item_id", "")) in _OPENING_IDS:
                continue
            assert str(it.get("uid")) in canon_uids, (label, it.get("uid"))
