import { describe, it, expect } from 'vitest';
import {
  calibrateScale,
  calibrateFromMeasurements,
  measurementMpp,
  worldPxToMetres,
  metresToWorldPx,
  uncalibrated,
  UNCALIBRATED_MPP,
  BED_LENGTH_M,
  SIDE_TABLE_M,
  type ScaleMeasurement,
} from './calibration';
import type { SceneRoom, SceneFurniture } from './scene';

function furn(p: Partial<SceneFurniture>): SceneFurniture {
  return { uid: 'f', item_id: 'bed', name: 'Bed', cx: 0, cy: 0, w: 200, h: 100, rotation: 0, ...p } as SceneFurniture;
}
function room(p: Partial<SceneRoom>): SceneRoom {
  return { id: 'r', label: 'R', bbox: [0, 0, 1, 1], furniture: [], ...p } as SceneRoom;
}
const km = (realM: number, px: number): ScaleMeasurement => ({ realM, px, source: 'known_dimension' });

describe('calibrateFromMeasurements (known dimensions)', () => {
  // §8 — known-dimension scale calibration: a 3.6 m wall spanning 360 px → 0.01 m/px.
  it('calibrates from a single known dimension (high confidence)', () => {
    const c = calibrateFromMeasurements([km(3.6, 360)]);
    expect(c.calibrated).toBe(true);
    expect(c.source).toBe('known_dimension');
    expect(c.confidence).toBe('high');
    expect(c.mpp).toBeCloseTo(0.01, 9);
    expect(c.count).toBe(1);
  });

  // §8 — multiple independent measurements that AGREE are averaged, high confidence.
  it('averages agreeing independent measurements', () => {
    const c = calibrateFromMeasurements([km(3.6, 360), km(2.4, 239)]); // ~0.01004 vs 0.01
    expect(c.calibrated).toBe(true);
    expect(c.confidence).toBe('high');
    expect(c.conflict).toBeUndefined();
    expect(c.count).toBe(2);
    expect(c.spread!).toBeLessThan(0.05);
    expect(c.mpp).toBeCloseTo((3.6 / 360 + 2.4 / 239) / 2, 9);
  });

  // §8 — CONFLICTING measurements are NOT silently averaged: flagged, median returned.
  // Asymmetric set so median ≠ mean, proving the median (not the average) is used.
  it('flags conflicting measurements and returns the median (not the mean)', () => {
    const ms = [km(3.6, 450), km(3.6, 360), km(3.6, 180)]; // 0.008, 0.01, 0.02 → spread 60%
    const c = calibrateFromMeasurements(ms);
    expect(c.conflict).toBe(true);
    expect(c.confidence).toBe('low');
    expect(c.spread!).toBeGreaterThan(0.05);
    const expectedMedian = 0.01; // median of {0.008, 0.01, 0.02}
    expect(c.mpp).toBeCloseTo(expectedMedian, 9);
    const mean = (0.008 + 0.01 + 0.02) / 3; // ≈ 0.012667 — distinct from the median
    expect(c.mpp).not.toBeCloseTo(mean, 6); // proves it did NOT average
  });

  // §8 — uncalibrated fallback handling: no usable measurement → explicit uncalibrated.
  it('returns the uncalibrated fallback when no measurement is usable', () => {
    const c = calibrateFromMeasurements([{ realM: 0, px: 0, source: 'known_dimension' }]);
    expect(c).toEqual(uncalibrated());
    expect(c.calibrated).toBe(false);
    expect(c.mpp).toBe(UNCALIBRATED_MPP);
  });

  it('measurementMpp rejects non-positive / non-finite input (never fabricates)', () => {
    expect(measurementMpp(km(0, 10))).toBeNull();
    expect(measurementMpp(km(10, 0))).toBeNull();
    expect(measurementMpp(km(Infinity, 10))).toBeNull();
    expect(measurementMpp(km(2, 200))).toBeCloseTo(0.01, 9);
  });
});

describe('calibrateScale (priority + provenance)', () => {
  // §8 — explicit known dimension wins over everything.
  it('prefers an explicit known dimension over furniture', () => {
    const c = calibrateScale([room({ furniture: [furn({ w: 300, h: 150 })] })], { measurements: [km(3.6, 360)] });
    expect(c.source).toBe('known_dimension');
    expect(c.mpp).toBeCloseTo(0.01, 9);
  });

  // §8 — a stored scale (future scale_mm_per_px) is used when present (no furniture needed).
  it('uses a stored mpp when no explicit dimension is given', () => {
    const c = calibrateScale([], { storedMpp: 0.004 });
    expect(c.source).toBe('stored_scale');
    expect(c.confidence).toBe('high');
    expect(c.mpp).toBe(0.004);
  });

  // §8 — furniture proxy reproduces the LEGACY computeMpp numbers exactly (bed first).
  it('reproduces the legacy bed proxy (2.0 m / longest side), medium confidence', () => {
    const c = calibrateScale([room({ furniture: [furn({ item_id: 'double-bed', w: 200, h: 100 })] })]);
    expect(c.source).toBe('furniture_bed');
    expect(c.confidence).toBe('medium');
    expect(c.calibrated).toBe(true);
    expect(c.mpp).toBeCloseTo(BED_LENGTH_M / 200, 9);
  });

  it('falls back to the side table when there is no bed', () => {
    const c = calibrateScale([room({ furniture: [furn({ item_id: 'side-table', w: 45, h: 45 })] })]);
    expect(c.source).toBe('furniture_side_table');
    expect(c.mpp).toBeCloseTo(SIDE_TABLE_M / 45, 9);
  });

  // §8 — the KEY empty-plan case: zero furniture, no stored scale, no dimension →
  // UNCALIBRATED (never invents a scale), but still a usable rendering factor.
  it('is UNCALIBRATED for an empty plan (zero furniture, no evidence)', () => {
    const c = calibrateScale([room({ furniture: [] })]);
    expect(c.calibrated).toBe(false);
    expect(c.source).toBe('uncalibrated');
    expect(c.confidence).toBe('none');
    expect(c.mpp).toBe(UNCALIBRATED_MPP);
  });

  it('is UNCALIBRATED for null/empty rooms', () => {
    expect(calibrateScale(null).calibrated).toBe(false);
    expect(calibrateScale([]).mpp).toBe(UNCALIBRATED_MPP);
  });

  it('is pure (stable across repeated calls)', () => {
    const rooms = [room({ furniture: [furn({ w: 260, h: 130 })] })];
    expect(calibrateScale(rooms)).toEqual(calibrateScale(rooms));
  });
});

describe('coordinate round-trip', () => {
  // §8 — world px → metres → world px is exact for any mpp > 0.
  it('round-trips world px ↔ metres exactly', () => {
    for (const mpp of [0.01, 0.004, 0.006667, 2 / 260]) {
      for (const px of [0, 1, 37.5, 1000, 2382]) {
        expect(metresToWorldPx(worldPxToMetres(px, mpp), mpp)).toBeCloseTo(px, 9);
      }
    }
  });
  it('maps a known dimension consistently with its calibration', () => {
    const c = calibrateFromMeasurements([km(3.6, 360)]);
    expect(worldPxToMetres(360, c.mpp)).toBeCloseTo(3.6, 9); // the calibrated span reads back as 3.6 m
  });
});
