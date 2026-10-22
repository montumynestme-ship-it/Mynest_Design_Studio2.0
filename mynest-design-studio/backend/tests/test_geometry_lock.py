"""Geometry lock — AI generation is a visual render ONLY and can never mutate the
canonical source-of-truth scene.

Enforces the five invariants:
  1. the original scene remains unchanged by generation,
  2. the AI image is treated only as a visual render (stored separately),
  3. no AI response can overwrite canonical scene geometry,
  4. a failed AI generation never modifies the original scene,
  5. no silent fallback to text-to-image.

Unit tests cover the fingerprint + guard + no-overwrite invariant directly; the
end-to-end tests reuse the real floor plan (DB) with the offline MockAdapter to
prove the canonical geometry hash is byte-identical before and after both a
successful and a fully-failed generation.
"""

import copy
from unittest import mock

import pytest

from app.services import floor_plan_service, generation_service as gs
from app.services.ai import registry
from app.services.ai.base import AIProviderError
from app.services.ai.mock_adapter import MockAdapter

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"

_CANON = {
    "furniture": [
        {"uid": "b", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
    ],
    "structured_walls": [{"id": "w1", "x1": 0, "y1": 0, "x2": 100, "y2": 0}],
    "doors": [{"id": "d1", "cx": 50, "cy": 0}],
    "windows": [{"id": "win1", "cx": 10, "cy": 0}],
    "room_boundaries": [[0, 0], [100, 0], [100, 100], [0, 100]],
}


# ── fingerprint covers every locked field ──────────────────────────────────────

def test_geometry_hash_is_stable_and_covers_all_locked_fields():
    h = gs._geometry_hash(_CANON)
    assert gs._geometry_hash(copy.deepcopy(_CANON)) == h  # identical geometry → identical hash
    mutations = {
        "furniture position": lambda c: c["furniture"][0].__setitem__("cx", 999),
        "furniture rotation": lambda c: c["furniture"][0].__setitem__("rotation", 90),
        "furniture dimension": lambda c: c["furniture"][0].__setitem__("w", 1),
        "wall": lambda c: c["structured_walls"].append({"id": "w2"}),
        "door": lambda c: c["doors"].append({"id": "d2"}),
        "window/opening": lambda c: c["windows"].append({"id": "win2"}),
        "room boundary/topology": lambda c: c["room_boundaries"].append([1, 1]),
    }
    for name, mutate in mutations.items():
        c = copy.deepcopy(_CANON)
        mutate(c)
        assert gs._geometry_hash(c) != h, f"{name} change must flip the geometry hash"


# ── the guard raises on any change, passes when unchanged ──────────────────────

def test_verify_geometry_unchanged_passes_when_identical():
    lock = gs._geometry_hash(_CANON)
    # A deep copy with identical content must pass (no exception).
    gs._verify_geometry_unchanged(copy.deepcopy(_CANON), lock)


def test_verify_geometry_unchanged_raises_on_mutation():
    lock = gs._geometry_hash(_CANON)
    mutated = copy.deepcopy(_CANON)
    mutated["furniture"][0]["cx"] = 12345  # AI/bug tried to move furniture
    with pytest.raises(floor_plan_service.FloorPlanError) as ei:
        gs._verify_geometry_unchanged(mutated, lock)
    assert ei.value.status_code == 500
    assert "GEOMETRY_LOCK_VIOLATION" in str(ei.value.detail)


# ── existing canonical is never overwritten by a generation ────────────────────

def test_get_or_create_version_never_overwrites_existing_canonical():
    existing = mock.Mock()
    existing.canonical_json = copy.deepcopy(_CANON)
    db = mock.Mock()
    db.query.return_value.filter_by.return_value.first.return_value = existing
    fp = mock.Mock()
    # A DIFFERENT canonical passed in must NOT overwrite the existing version.
    different = {"furniture": [{"uid": "x", "item_id": "sofa", "cx": 1, "cy": 1, "w": 1, "h": 1, "rotation": 0}]}
    dv = gs._get_or_create_version(db, fp, different)
    assert dv is existing
    assert dv.canonical_json == _CANON            # unchanged
    db.add.assert_not_called()                     # existing reused, nothing written


# ── end-to-end: canonical geometry is byte-identical before and after ───────────

def _canon_hash():
    return gs._geometry_hash(floor_plan_service.get_canonical(FID))


def test_failed_generation_does_not_change_canonical_and_no_fallback():
    before = _canon_hash()

    class AllFail(MockAdapter):
        # Provider fails on every room; must surface the real error, never fall back.
        def generate(self, request):
            raise AIProviderError("mock", "HTTP 500: Internal Server Error", 502)

    with mock.patch.object(registry, "get_adapter", return_value=AllFail()), \
         mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        resp = gs.generate(
            file_id=FID, provider="mock", count=1,
            design_intent={"style": "Modern Luxury"},
            requested_rooms=["Living Area", "Kitchen"], fresh_generation=True,
        )
    # No silent fallback: failed, no images, real provider error surfaced (not faked).
    assert resp.status == "failed"
    assert resp.images == []
    assert resp.error and "500" in resp.error
    # Failed generation left the source-of-truth scene byte-identical.
    assert _canon_hash() == before


def test_successful_generation_does_not_change_canonical():
    # Runs AFTER the failure test so the most-recent persisted generation is a
    # COMPLETED one with images — leaving shared DB state clean for other suites
    # (e.g. the Playwright evidence test that reads the latest generation).
    before = _canon_hash()
    with mock.patch.object(registry, "get_adapter", return_value=MockAdapter()):
        resp = gs.generate(
            file_id=FID, provider="mock", count=1,
            design_intent={"style": "Modern Luxury"},
            requested_rooms=["Living Area", "Kitchen"], fresh_generation=True,
        )
    assert resp.status == "completed"
    assert len(resp.images) >= 1               # AI images produced as visual renders
    assert _canon_hash() == before             # canonical geometry unchanged
