"""Shared test fixtures.

Hermetic NVIDIA config: adapter/generation tests must not depend on the
developer's backend/.env (which may point NVIDIA_API_BASE at a local NIM, enable
img2img, etc. for manual testing). This autouse fixture resets the NVIDIA image
config to safe, deterministic defaults — hosted endpoint, flux.1-dev,
text-to-image — before each test. Tests that exercise img2img / self-hosted NIM
patch these names explicitly inside their own `with mock.patch(...)` blocks, and
those patches take precedence for the duration of the test.
"""

from unittest import mock

import pytest

_ADAPTER = "app.services.ai.nvidia_flux_adapter"


def db_isolation_status() -> tuple[bool, str]:
    """Classify the EFFECTIVE DATABASE_URL as a safe, disposable test DB — or not.

    Returns ``(ok, reason)`` and NEVER returns or logs the URL/credentials. A
    DB-mutating test is only allowed when ALL hold:
      * the operator explicitly opted in (``MYNEST_ALLOW_DB_TESTS=1``), AND
      * the host is local (``localhost``/``127.0.0.1``/``::1``) — never remote/cloud, AND
      * the database name looks test-only (contains ``test``), unless the operator
        confirms an intentionally-named test DB with ``MYNEST_TEST_DB_NAME_OK=1``.
    Anything remote/shared/production/ambiguous → not ok (caller aborts/skips).
    """
    import os
    from urllib.parse import urlparse

    from app.core.config import DATABASE_URL as _u

    if not _u:
        return False, "DATABASE_URL not configured"
    if os.getenv("MYNEST_ALLOW_DB_TESTS") != "1":
        return False, "MYNEST_ALLOW_DB_TESTS!=1 - DB-mutating tests disabled by default"
    p = urlparse(_u)
    host = p.hostname or ""
    dbname = (p.path or "").lstrip("/")
    if host not in ("localhost", "127.0.0.1", "::1"):
        return False, "target host is remote/shared/cloud - not a disposable local test DB"
    if any(s in host for s in ("supabase", "pooler", "amazonaws", "rds", "neon", "render")):
        return False, "target host looks like a managed/cloud database"
    if "test" not in dbname.lower() and os.getenv("MYNEST_TEST_DB_NAME_OK") != "1":
        return False, "database name is not recognizably test-only (ambiguous)"
    return True, "local disposable test DB confirmed"


@pytest.fixture
def require_db_isolation():
    """Skip a DB-mutating test unless a disposable local test DB is confirmed.

    Operationalizes the safety rule: never run mutating tests against a remote/shared/
    production/ambiguous database. Opt in per run with an explicitly-designated test DB:
        MYNEST_ALLOW_DB_TESTS=1 DATABASE_URL=postgresql+psycopg://…@127.0.0.1:5433/mynest_test pytest …
    """
    ok, reason = db_isolation_status()
    if not ok:
        pytest.skip(f"DB-mutating test skipped — DB isolation not confirmed: {reason}")


@pytest.fixture(autouse=True)
def hermetic_nvidia_config():
    with mock.patch(f"{_ADAPTER}.NVIDIA_API_BASE", "https://ai.api.nvidia.com/v1/genai"), \
         mock.patch(f"{_ADAPTER}.NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.1-dev"), \
         mock.patch(f"{_ADAPTER}.NVIDIA_SUPPORTS_IMG2IMG", False), \
         mock.patch(f"{_ADAPTER}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", False), \
         mock.patch(f"{_ADAPTER}.NVIDIA_IMG2IMG_MODE", "canny"), \
         mock.patch(f"{_ADAPTER}.NVIDIA_NIM_INFER_PATH", "/v1/infer"):
        yield


# ── Frozen canonical baseline for invariant regression tests ─────────────────────
# The real floor-plan design (f6b65d2b) is a LIVE, append-only DesignVersion row that
# the 2D editor keeps mutating in the app. Invariant tests that pin hard-coded furniture
# / opening counts against the *live* ``get_canonical`` therefore break whenever the
# design is legitimately edited. DesignVersion **v31** (``1831bf84-…``, is_frozen=True,
# created 2026-10-11) is the explicitly-selected, immutable geometry baseline (22 real
# furniture, 8 doors, 4 windows, 0 ``room-tag`` annotations). Its canonical_json is
# committed verbatim at tests/fixtures/canonical_v31_1831bf84.json; the SHA below is the
# recorded provenance hash. Annotation-exclusion behaviour is covered separately in
# tests/test_annotation_exclusion.py (this baseline intentionally has no annotations).
import copy as _copy
import hashlib as _hashlib
import json as _json
import pathlib as _pathlib

FROZEN_FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
V31_DESIGN_VERSION_ID = "1831bf84-f9d6-4d4f-aedc-4ad95d6145fe"
V31_CANONICAL_SHA256 = "228aad99d20dbdbb96bfe8e3ed3e07817432caa353f357870bde44b0eaac3323"
_V31_FIXTURE = _pathlib.Path(__file__).parent / "fixtures" / "canonical_v31_1831bf84.json"


def load_frozen_v31_canonical() -> dict:
    """Load the committed v31 canonical and verify it reproduces the recorded hash."""
    cj = _json.loads(_V31_FIXTURE.read_text(encoding="utf-8"))
    digest = _hashlib.sha256(
        _json.dumps(cj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == V31_CANONICAL_SHA256, (
        f"v31 fixture hash mismatch: expected {V31_CANONICAL_SHA256}, got {digest}"
    )
    return cj


@pytest.fixture
def frozen_v31(monkeypatch):
    """Pin ``floor_plan_service.get_canonical(FROZEN_FID)`` to the immutable v31 snapshot.

    Walls/doors/windows always derive from the immutable floor-plan FILE inside
    ``build_scene`` / the audit scripts, so pinning only the (mutable) canonical makes
    every data-dependent invariant test deterministic against v31. Other file_ids are
    untouched. The fixture returns the loaded canonical for convenience.
    """
    cj = load_frozen_v31_canonical()
    from app.services import floor_plan_service

    _real = floor_plan_service.get_canonical

    def _patched(file_id):
        if str(file_id) == FROZEN_FID:
            return _copy.deepcopy(cj)
        return _real(file_id)

    monkeypatch.setattr(floor_plan_service, "get_canonical", _patched)
    return cj


# ── Frozen v76+ OPEN-PLAN baseline (Kitchen + Dining intentionally merged) ────────
# From DesignVersion **v76** (2026-10-23) the owner INTENTIONALLY merged the Kitchen and
# Dining into a single open-plan space: room reconstruction now yields ONE combined
# "Kitchen & Dining Area" (CONFIRMED, wall-proven) instead of the pre-v76 separate
# "Kitchen" + "Dining Area". This is the current, approved product contract. **v84**
# (``62ef3454-…``, is_frozen=True, created 2026-11-01) is the immutable snapshot of that
# intended open-plan layout (22 real furniture, 4 editor doors, 4 editor windows, 5
# ``room-tag`` annotations). Walls + supplemental PDF openings always derive from the
# immutable floor-plan FILE, so the geometry is identical either way — only the (mutable)
# furniture SOURCE is frozen. Committed verbatim at
# tests/fixtures/canonical_v84_62ef3454.json; the SHA below is the recorded provenance hash.
V84_DESIGN_VERSION_ID = "62ef3454-7c52-4760-9333-d40570bb6ded"
V84_VERSION_NUMBER = 84
V84_CANONICAL_SHA256 = "a3433acbe1de25822b9d89dfecccf090c588389568efe65590ab6d6f10a7aed7"
_V84_FIXTURE = _pathlib.Path(__file__).parent / "fixtures" / "canonical_v84_62ef3454.json"


def load_frozen_v84_canonical() -> dict:
    """Load the committed v84 (open-plan) canonical and verify its recorded hash."""
    cj = _json.loads(_V84_FIXTURE.read_text(encoding="utf-8"))
    digest = _hashlib.sha256(
        _json.dumps(cj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == V84_CANONICAL_SHA256, (
        f"v84 fixture hash mismatch: expected {V84_CANONICAL_SHA256}, got {digest}"
    )
    return cj


@pytest.fixture
def frozen_v84(monkeypatch):
    """Pin the LATEST-version reads for ``FROZEN_FID`` to the immutable v84 open-plan snapshot.

    Both ``get_canonical`` (furniture) and ``get_latest_version_info`` (design_version_id +
    version_number) are pinned, so room eligibility and the opening-geometry audit resolve
    the intended v76+ combined "Kitchen & Dining Area" contract DETERMINISTICALLY — never the
    live, still-mutating latest design version, and never affected by future 2D edits.
    Walls/doors/windows always derive from the immutable floor-plan FILE inside
    ``build_scene`` / the audit, so geometry is identical either way; only the furniture
    SOURCE is frozen. Other file_ids are untouched. Returns the loaded canonical.
    """
    cj = load_frozen_v84_canonical()
    from app.services import floor_plan_service

    _real_canon = floor_plan_service.get_canonical
    _real_info = floor_plan_service.get_latest_version_info

    def _patched_canon(file_id):
        if str(file_id) == FROZEN_FID:
            return _copy.deepcopy(cj)
        return _real_canon(file_id)

    def _patched_info(file_id):
        if str(file_id) == FROZEN_FID:
            return (V84_DESIGN_VERSION_ID, V84_VERSION_NUMBER)
        return _real_info(file_id)

    monkeypatch.setattr(floor_plan_service, "get_canonical", _patched_canon)
    monkeypatch.setattr(floor_plan_service, "get_latest_version_info", _patched_info)
    return cj
