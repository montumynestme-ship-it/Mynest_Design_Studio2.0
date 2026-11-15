"""Phase B — metric scale calibration (coordinates math, API validation, persistence).

The persistence logic is tested with a monkeypatched session (no real DB write), so the
whole suite runs anywhere and never mutates Supabase. End-to-end persistence against a live
plan is validated separately (see the Phase-B report). The API-validation tests only exercise
the 422 branches, which raise BEFORE any DB access.
"""

import contextlib
import math

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import coordinates as C
from app.services import floor_plan_service as fps
from app.services.floor_plan_service import FloorPlanError

client = TestClient(app)
FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"  # used read-only / for routing only


# ── coordinates math (pure, no DB) ───────────────────────────────────────────
class TestCalibrationMath:
    def test_valid_factor(self) -> None:
        # 3000 mm over 500 world px → 6 mm/px
        assert C.scale_mm_per_px_from_measurement(3000.0, 500.0) == 6.0

    def test_pixel_distance(self) -> None:
        assert C.pixel_distance((0, 0), (300, 400)) == 500.0

    def test_mpp_conversion(self) -> None:
        assert C.mpp_from_scale_mm_per_px(6.0) == pytest.approx(0.006)

    def test_roundtrip_reads_back(self) -> None:
        # 3600 mm over 360 px → 10 mm/px → 0.01 m/px (== DEFAULT_MPP magnitude)
        smpp = C.scale_mm_per_px_from_measurement(3600.0, 360.0)
        assert C.mpp_from_scale_mm_per_px(smpp) == pytest.approx(0.01)
        assert 360.0 * smpp == pytest.approx(3600.0)  # the span reads back as its real length

    @pytest.mark.parametrize(
        "known,px",
        [(0, 10), (-5, 10), (10, 0), (10, -1), (math.inf, 10), (math.nan, 10), (10, math.inf)],
    )
    def test_rejects_invalid(self, known: float, px: float) -> None:
        with pytest.raises(ValueError):
            C.scale_mm_per_px_from_measurement(known, px)


# ── persistence logic (monkeypatched session — no real DB) ────────────────────
class _FakeFP:
    def __init__(self, scale: float | None = None) -> None:
        self.scale_mm_per_px = scale


@pytest.fixture
def fake_fp(monkeypatch: pytest.MonkeyPatch) -> _FakeFP:
    fp = _FakeFP()

    @contextlib.contextmanager
    def _scope():  # type: ignore[no-untyped-def]
        yield object()

    monkeypatch.setattr(fps, "session_scope", _scope)
    monkeypatch.setattr(fps, "_get_or_404", lambda db, fid: fp)
    return fp


class TestCalibrationPersistence:
    def test_uncalibrated_read(self, fake_fp: _FakeFP) -> None:
        got = fps.get_floor_plan_scale(FID)
        assert got == {"scale_mm_per_px": None, "mpp": None, "calibrated": False, "source": None}

    def test_set_then_read(self, fake_fp: _FakeFP) -> None:
        got = fps.set_floor_plan_scale(FID, 6.0)
        assert fake_fp.scale_mm_per_px == 6.0
        assert got["calibrated"] is True
        assert got["scale_mm_per_px"] == 6.0
        assert got["mpp"] == pytest.approx(0.006)
        assert got["source"] == "user_measurement"

    def test_no_overwrite_without_flag(self, fake_fp: _FakeFP) -> None:
        fps.set_floor_plan_scale(FID, 6.0)
        with pytest.raises(FloorPlanError) as exc:
            fps.set_floor_plan_scale(FID, 8.0)  # overwrite defaults to False
        assert exc.value.status_code == 409
        assert fake_fp.scale_mm_per_px == 6.0  # preserved — never silently replaced

    def test_overwrite_with_flag(self, fake_fp: _FakeFP) -> None:
        fps.set_floor_plan_scale(FID, 6.0)
        got = fps.set_floor_plan_scale(FID, 8.0, overwrite=True)
        assert fake_fp.scale_mm_per_px == 8.0
        assert got["scale_mm_per_px"] == 8.0

    @pytest.mark.parametrize("bad", [0, -1, math.inf, math.nan])
    def test_invalid_value_preserves_previous(self, fake_fp: _FakeFP, bad: float) -> None:
        fps.set_floor_plan_scale(FID, 6.0)
        with pytest.raises(FloorPlanError) as exc:
            fps.set_floor_plan_scale(FID, bad, overwrite=True)
        assert exc.value.status_code == 422
        assert fake_fp.scale_mm_per_px == 6.0  # prior value preserved on failure


# ── API validation (422 branches only — no DB access) ─────────────────────────
class TestCalibrationApiValidation:
    def test_missing_all_fields(self) -> None:
        r = client.put(f"/api/floor-plans/{FID}/calibration", json={})
        assert r.status_code == 422

    def test_negative_scale(self) -> None:
        r = client.put(f"/api/floor-plans/{FID}/calibration", json={"scale_mm_per_px": -1})
        assert r.status_code == 422

    def test_zero_length_measurement(self) -> None:
        r = client.put(
            f"/api/floor-plans/{FID}/calibration",
            json={"p1": [0, 0], "p2": [0, 0], "known_distance_mm": 1000},
        )
        assert r.status_code == 422

    def test_negative_known_distance(self) -> None:
        r = client.put(
            f"/api/floor-plans/{FID}/calibration",
            json={"p1": [0, 0], "p2": [3, 4], "known_distance_mm": -5},
        )
        assert r.status_code == 422
