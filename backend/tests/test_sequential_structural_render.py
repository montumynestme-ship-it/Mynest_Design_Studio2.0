"""Path B regression — the SEQUENTIAL room loop (production default,
MAX_CONCURRENT_ROOM_GENERATIONS=1) must hand ``_render_room`` the same per-room structural
render as the concurrent worker path.

Drives the REAL ``generation_service.generate()``. Everything external is stubbed: the
snapshot, scene build, 2D→3D gate, provider validation and the DB session (the second
``session_scope`` — persistence — raises a sentinel, so nothing is written), and
``_render_room`` is replaced by a recorder. No provider call, no DB read/write, no .env change.
"""

from __future__ import annotations

import base64
import contextlib
import copy
import types
from io import BytesIO

import pytest
from PIL import Image

from app.services import floor_plan_service, prompt_service
from app.services import generation_service as gs
from app.services.ai import registry


def _f(uid, item, cx, cy, w=100, h=100, rot=0.0):
    return {"uid": uid, "item_id": item, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


CANON = {
    "furniture": [
        _f("bed-1", "bed", 300, 300, 200, 220),
        _f("st-1", "side-table", 450, 300, 60, 60),
        _f("sofa-1", "sofa-3", 1500, 300, 210, 90),
        _f("ct-1", "coffee-table", 1500, 420, 100, 60),
    ]
}
VID, VNUM = "v-struct-1", 7


def _png(color, w=64, h=64):
    img = Image.new("RGB", (w, h), color)
    for y in range(h // 3):
        for x in range(w):
            img.putpixel((x, y), (255 - color[0], 255 - color[1], 255 - color[2]))
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _uri(b: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(b).decode()


class _Stop(Exception):
    """Raised at the persistence step so the test never writes a generation record."""


class _Adapter:
    name = "fal"
    model = "recorder"
    supports_control_image = True

    def generate(self, request):  # never reached: _render_room is replaced
        raise AssertionError("provider must not be called")


@pytest.fixture
def harness(monkeypatch):
    calls: list[dict] = []
    sessions = {"n": 0}

    @contextlib.contextmanager
    def fake_session():
        sessions["n"] += 1
        if sessions["n"] > 1:
            raise _Stop()
        db = types.SimpleNamespace(
            get=lambda *a, **k: types.SimpleNamespace(project_id="proj-1", id="fp-1")
        )
        yield db

    def fake_render_room(adapter, provider, style, room, *a, **kw):
        calls.append({"label": room[0], **kw})
        raise RuntimeError("recorded")  # per-room error → generate continues to persistence

    scene = {
        "rooms": [],
        "structured_walls": [],
        "geometry_validation": {"geometry_faithful": True},
    }

    def snapshot(fid):
        sessions["n"] = 0  # a new generate() run: its 2nd session is the persistence step
        return VID, VNUM, copy.deepcopy(CANON)

    monkeypatch.setattr(floor_plan_service, "capture_generation_snapshot", snapshot)
    monkeypatch.setattr(gs.scene_service, "build_scene", lambda fid, canonical=None: scene)
    monkeypatch.setattr(
        gs.validation_service,
        "validate_scene_2d_to_3d",
        lambda c, s: {"passed": True, "mismatches": []},
    )
    monkeypatch.setattr(registry, "validate_provider", lambda name: {"status": "OK"})
    monkeypatch.setattr(registry, "get_adapter", lambda name=None: _Adapter())
    monkeypatch.setattr(gs, "session_scope", fake_session)
    monkeypatch.setattr(gs, "_render_room", fake_render_room)
    monkeypatch.setattr(gs, "AI_DEMO_MODE", False)
    monkeypatch.setattr(gs, "AI_ROOM_DELAY_SECONDS", 0.0)
    return calls


def _labels():
    return [lbl for lbl, items in prompt_service.group_by_room(CANON["furniture"]) if items]


def _run(monkeypatch, *, concurrency, flags_on, structural_for=None):
    monkeypatch.setenv("MAX_CONCURRENT_ROOM_GENERATIONS", str(concurrency))
    monkeypatch.setattr(gs, "FAL_USE_CONTROLNET", flags_on)
    monkeypatch.setattr(gs, "FAL_CONTROL_STRUCTURAL", flags_on)
    labels = _labels()
    base = {lbl: _png((20 + 40 * i, 60, 90)) for i, lbl in enumerate(labels)}
    struct = {lbl: _png((200, 10 + 50 * i, 30)) for i, lbl in enumerate(labels)}
    meta = {
        lbl: {"design_version_id": VID, "room_key": lbl, "width": 64, "height": 64}
        for lbl in labels
    }
    with_struct = labels if structural_for is None else structural_for
    with pytest.raises(_Stop):
        gs.generate(
            file_id="00000000-0000-0000-0000-000000000001",
            provider="fal",
            count=1,
            design_intent=None,
            requested_rooms=labels,
            base_renders={lbl: _uri(b) for lbl, b in base.items()},
            base_render_meta=meta,
            structural_renders={lbl: _uri(struct[lbl]) for lbl in with_struct},
            structural_render_meta={lbl: dict(meta[lbl]) for lbl in with_struct},
        )
    return labels, base, struct


@pytest.mark.parametrize("concurrency", [1, 2], ids=["sequential", "concurrent"])
def test_structural_render_reaches_render_room_in_both_paths(harness, monkeypatch, concurrency):
    labels, base, struct = _run(monkeypatch, concurrency=concurrency, flags_on=True)
    assert len(labels) >= 2 and sorted(c["label"] for c in harness) == sorted(labels)
    for c in harness:
        # The EXACT decoded artifact for THIS room (no regeneration/resize/other room's image).
        assert c["structural_render"] == struct[c["label"]]
        assert c["base_render"] == base[c["label"]]  # base render untouched
        assert c["structural_render"] != c["base_render"]


@pytest.mark.parametrize("concurrency", [1, 2], ids=["sequential", "concurrent"])
def test_flags_off_sends_no_structural_render(harness, monkeypatch, concurrency):
    _run(monkeypatch, concurrency=concurrency, flags_on=False)
    assert harness and all(c["structural_render"] is None for c in harness)


def test_sequential_and_concurrent_receive_identical_artifacts(harness, monkeypatch):
    _run(monkeypatch, concurrency=1, flags_on=True)
    seq = {c["label"]: c["structural_render"] for c in harness}
    harness.clear()
    _run(monkeypatch, concurrency=2, flags_on=True)
    con = {c["label"]: c["structural_render"] for c in harness}
    assert seq == con and all(v is not None for v in seq.values())


@pytest.mark.parametrize("concurrency", [1, 2], ids=["sequential", "concurrent"])
def test_missing_structural_artifact_fails_closed_never_fabricated(
    harness, monkeypatch, concurrency
):
    labels = _labels()
    _run(monkeypatch, concurrency=concurrency, flags_on=True, structural_for=labels[:1])
    # Only the room WITH a structural pair reaches _render_room; the other is refused by the
    # existing STRUCTURAL_PAIR gate before any render/provider call (no substitute image).
    assert [c["label"] for c in harness] == labels[:1]
    assert harness[0]["structural_render"] is not None


def test_canonical_snapshot_unchanged(harness, monkeypatch):
    before = copy.deepcopy(CANON)
    _run(monkeypatch, concurrency=1, flags_on=True)
    assert CANON == before
