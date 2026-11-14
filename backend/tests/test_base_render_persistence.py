"""Phase 4A — deterministic base-render persistence (evidence-only).

Tests ``generation_service._persist_base_render`` directly with synthetic bytes
(no paid AI calls). It writes the exact deterministic base PNG + a meta JSON (with a
SHA-256) into the PRIVATE per-room debug directory, bound to the generation + room +
immutable design version. A missing base is recorded honestly (never fabricated), and
each generation/room keeps its own artifact (no cross-reuse).

DEBUG_ARTIFACTS_DIR is monkeypatched to a tmp dir so the tests never touch real storage.
"""

import hashlib
import json

import pytest

from app.services import generation_service as gs


@pytest.fixture()
def debug_root(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "DEBUG_ARTIFACTS_DIR", tmp_path)
    return tmp_path


def _room_dir(root, gid, index, label):
    return root / gid / f"room_{index}_{label}"


def _persist(gid="gen-1", index=0, label="Bedroom 1", base=b"PNGBYTES-A",
             dvid="dv-1831", provider="fal", model="fal-ai/flux-kontext/dev",
             used=True, w=1216, h=832):
    gs._persist_base_render(
        gid, index, label, base,
        design_version_id=dvid, provider=provider, model=model,
        used_base_render=used, width=w, height=h,
    )


def test_successful_persist_stores_png_and_meta(debug_root):
    _persist(base=b"DETERMINISTIC-BASE")
    d = _room_dir(debug_root, "gen-1", 0, "Bedroom 1")
    assert (d / "base_render.png").read_bytes() == b"DETERMINISTIC-BASE"
    meta = json.loads((d / "base_render_meta.json").read_text(encoding="utf-8"))
    assert meta["base_render_persisted"] is True
    assert meta["base_render_bytes"] == len(b"DETERMINISTIC-BASE")


def test_stored_hash_matches_persisted_bytes(debug_root):
    base = b"base-bytes-for-hash-check"
    _persist(base=base)
    d = _room_dir(debug_root, "gen-1", 0, "Bedroom 1")
    meta = json.loads((d / "base_render_meta.json").read_text(encoding="utf-8"))
    on_disk = (d / "base_render.png").read_bytes()
    assert meta["base_render_sha256"] == hashlib.sha256(on_disk).hexdigest()
    assert meta["base_render_sha256"] == hashlib.sha256(base).hexdigest()


def test_bound_to_correct_generation_room_and_design_version(debug_root):
    _persist(gid="gen-X", index=2, label="Kitchen", dvid="dv-ABC", base=b"K")
    meta = json.loads(
        (_room_dir(debug_root, "gen-X", 2, "Kitchen") / "base_render_meta.json")
        .read_text(encoding="utf-8")
    )
    assert meta["generation_id"] == "gen-X"
    assert meta["room_index"] == 2 and meta["room_label"] == "Kitchen"
    assert meta["design_version_id"] == "dv-ABC"


def test_different_generations_and_rooms_do_not_reuse_wrong_base(debug_root):
    _persist(gid="gen-A", index=0, label="Bedroom 1", dvid="dv-1", base=b"BASE-A")
    _persist(gid="gen-B", index=0, label="Bedroom 1", dvid="dv-2", base=b"BASE-B")
    _persist(gid="gen-A", index=1, label="Kitchen", dvid="dv-1", base=b"BASE-A-KITCHEN")
    a = (_room_dir(debug_root, "gen-A", 0, "Bedroom 1") / "base_render.png").read_bytes()
    b = (_room_dir(debug_root, "gen-B", 0, "Bedroom 1") / "base_render.png").read_bytes()
    k = (_room_dir(debug_root, "gen-A", 1, "Kitchen") / "base_render.png").read_bytes()
    assert a == b"BASE-A" and b == b"BASE-B" and k == b"BASE-A-KITCHEN"
    assert len({a, b, k}) == 3  # no cross-contamination
    # design version is recorded per generation
    ma = json.loads((_room_dir(debug_root, "gen-A", 0, "Bedroom 1") / "base_render_meta.json").read_text())
    mb = json.loads((_room_dir(debug_root, "gen-B", 0, "Bedroom 1") / "base_render_meta.json").read_text())
    assert ma["design_version_id"] == "dv-1" and mb["design_version_id"] == "dv-2"


def test_missing_base_is_recorded_honestly_no_fabrication(debug_root):
    _persist(base=None)
    d = _room_dir(debug_root, "gen-1", 0, "Bedroom 1")
    assert not (d / "base_render.png").exists()          # no fabricated artifact
    meta = json.loads((d / "base_render_meta.json").read_text(encoding="utf-8"))
    assert meta["base_render_persisted"] is False
    assert meta["base_render_sha256"] is None            # no fabricated hash
    assert meta["base_render_bytes"] == 0


def test_text_to_image_records_captured_but_not_consumed(debug_root):
    # A base can be captured but NOT consumed (text-to-image). The meta must distinguish.
    _persist(base=b"CAPTURED", used=False)
    meta = json.loads(
        (_room_dir(debug_root, "gen-1", 0, "Bedroom 1") / "base_render_meta.json").read_text()
    )
    assert meta["base_render_persisted"] is True and meta["used_base_render"] is False


def test_persistence_is_best_effort_and_never_raises(debug_root, monkeypatch):
    # An unwritable path must NOT crash a render (evidence persistence is best-effort).
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(gs.Path, "mkdir", boom, raising=False)
    # Should swallow the error and return None, not raise.
    assert _persist(base=b"X") is None


def test_legacy_generation_without_base_artifact_has_no_base_files(debug_root):
    # A generation that never persisted a base simply has no base files; nothing errors.
    d = _room_dir(debug_root, "legacy-gen", 0, "Bedroom 1")
    assert not (d / "base_render.png").exists()
    assert not (d / "base_render_meta.json").exists()


# ── Phase 4A.1 — atomic writes + verification, failure injection ──────────────

def _is_valid_pair(d):
    """The documented validity contract: meta parses + persisted true + png exists +
    on-disk sha matches meta sha."""
    mp = d / "base_render_meta.json"
    pp = d / "base_render.png"
    if not mp.exists() or not pp.exists():
        return False
    meta = json.loads(mp.read_text(encoding="utf-8"))
    return (
        meta.get("base_render_persisted") is True
        and hashlib.sha256(pp.read_bytes()).hexdigest() == meta.get("base_render_sha256")
    )


def test_successful_atomic_persistence_is_a_valid_pair_with_no_temp_left(debug_root):
    _persist(base=b"ATOMIC-OK")
    d = _room_dir(debug_root, "gen-1", 0, "Bedroom 1")
    assert _is_valid_pair(d) is True
    assert list(d.glob("*.tmp")) == []  # temp consumed by os.replace


def test_png_replace_failure_writes_no_success_meta_and_cleans_temp(debug_root, monkeypatch):
    real_replace = gs.os.replace

    def fail_png(src, dst):
        if str(dst).endswith("base_render.png"):
            raise OSError("simulated PNG replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(gs.os, "replace", fail_png)
    assert _persist(base=b"DATA") is None  # never raises
    d = _room_dir(debug_root, "gen-1", 0, "Bedroom 1")
    assert not (d / "base_render.png").exists()         # no partial PNG
    assert not (d / "base_render_meta.json").exists()   # no success meta
    assert list(d.glob("*.tmp")) == []                  # temp cleaned up


def test_verification_failure_writes_no_success_meta(debug_root, monkeypatch):
    real_rb = gs.Path.read_bytes

    def corrupt_png_read(self):
        if self.name == "base_render.png":
            return b"CORRUPTED-DIFFERENT-BYTES"
        return real_rb(self)

    monkeypatch.setattr(gs.Path, "read_bytes", corrupt_png_read)
    assert _persist(base=b"GOOD-BYTES") is None
    d = _room_dir(debug_root, "gen-1", 0, "Bedroom 1")
    # verification (re-hash) fails -> no metadata claiming success is written
    assert not (d / "base_render_meta.json").exists()
    assert list(d.glob("*.tmp")) == []


def test_meta_replace_failure_leaves_no_falsely_valid_pair(debug_root, monkeypatch):
    real_replace = gs.os.replace

    def fail_meta(src, dst):
        if str(dst).endswith("base_render_meta.json"):
            raise OSError("simulated meta replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(gs.os, "replace", fail_meta)
    assert _persist(base=b"DATA") is None
    d = _room_dir(debug_root, "gen-1", 0, "Bedroom 1")
    # PNG persisted+verified, but meta failed -> pair is NOT valid (no meta), no temp left
    assert not (d / "base_render_meta.json").exists()
    assert _is_valid_pair(d) is False
    assert list(d.glob("*.tmp")) == []


def test_missing_base_still_honest_and_atomic(debug_root):
    _persist(base=None)
    d = _room_dir(debug_root, "gen-1", 0, "Bedroom 1")
    assert not (d / "base_render.png").exists()
    meta = json.loads((d / "base_render_meta.json").read_text(encoding="utf-8"))
    assert meta["base_render_persisted"] is False and meta["base_render_sha256"] is None
    assert list(d.glob("*.tmp")) == []
