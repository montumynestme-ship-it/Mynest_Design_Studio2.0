/**
 * Deterministic metric-scale calibration for the 3D scene.
 *
 * The 3D renderer converts world pixels → metres with a single factor `mpp`
 * (metres per world pixel). This module decides that factor HONESTLY, with explicit
 * provenance and confidence, and — critically — it NEVER invents a physical
 * dimension:
 *
 *   - A real drawing dimension (a known length + its pixel span) → `source:
 *     'known_dimension'`, `confidence: 'high'`, `calibrated: true`.
 *   - A furniture proxy (a bed ≈ 2.0 m, a side table ≈ 0.45 m — the existing
 *     heuristic) → `source: 'furniture_*'`, `confidence: 'medium'`, `calibrated:
 *     true`. This is a real-world ASSUMPTION about a catalogue item, not a measured
 *     drawing dimension, so it is deliberately a rung below a known dimension.
 *   - No evidence at all (e.g. an empty plan with no furniture and no stored scale)
 *     → `source: 'uncalibrated'`, `confidence: 'none'`, `calibrated: false`, and
 *     `mpp` falls back to {@link UNCALIBRATED_MPP} (which equals the backend's
 *     documented `coordinates.DEFAULT_MPP`). The scene still renders — every element
 *     scales by the same factor, so proportions are correct — but NO metric accuracy
 *     is claimed.
 *
 * Multiple independent known dimensions are cross-checked: when they AGREE (within
 * `tol`) the calibration averages them and reports `confidence: 'high'`; when they
 * CONFLICT the module does NOT silently average incompatible evidence — it flags
 * `conflict: true`, drops to `confidence: 'low'`, and returns the median factor so a
 * caller can surface the discrepancy. Pure + deterministic; no I/O, no mutation.
 */
import type { SceneRoom } from './scene';

/** metres per world pixel when nothing calibrates the scene — the backend's
 * `coordinates.DEFAULT_MPP` (1 px = 10 mm). An UNCALIBRATED assumption, never a
 * measured value: `calibrated` is false whenever this is used. */
export const UNCALIBRATED_MPP = 0.01;

/** Real-world lengths (metres) of the furniture items used as scale proxies. A bed's
 * longest side ≈ 2.0 m; a side table ≈ 0.45 m. These are catalogue assumptions, not
 * drawing dimensions — hence `confidence: 'medium'`. */
export const BED_LENGTH_M = 2.0;
export const SIDE_TABLE_M = 0.45;

/** World pixels → metres (the renderer's world→metre map). Mirrors the backend
 * `coordinates.world_to_three`. Pure. */
export function worldPxToMetres(px: number, mpp: number): number {
  return px * mpp;
}

/** Metres → world pixels. Mirrors the backend `coordinates.three_to_world`. Exact
 * inverse of {@link worldPxToMetres} for any `mpp > 0`. Pure. */
export function metresToWorldPx(m: number, mpp: number): number {
  return m / mpp;
}

export type CalibrationSource =
  | 'known_dimension'
  | 'furniture_bed'
  | 'furniture_side_table'
  | 'stored_scale'
  | 'uncalibrated';

export type CalibrationConfidence = 'high' | 'medium' | 'low' | 'none';

/** One scale observation: a real-world length and the world-pixel distance that
 * represents it. `realM / px` is the implied metres-per-pixel. */
export interface ScaleMeasurement {
  /** Real-world length in metres (> 0). */
  realM: number;
  /** The same length measured in world pixels (> 0). */
  px: number;
  source: CalibrationSource;
  /** Optional human label for diagnostics (e.g. the dimension text, or 'bed'). */
  label?: string;
}

export interface Calibration {
  /** Metres per world pixel. Always finite and > 0 (falls back to UNCALIBRATED_MPP). */
  mpp: number;
  source: CalibrationSource;
  confidence: CalibrationConfidence;
  /** True ONLY when `mpp` came from real evidence (a known dimension, a stored scale,
   * or a furniture proxy). False for the uncalibrated fallback — never claim metric
   * accuracy when this is false. */
  calibrated: boolean;
  /** Max relative disagreement across the measurements used (0 = identical). Present
   * only when more than one measurement was combined. */
  spread?: number;
  /** True when independent known dimensions disagreed beyond tolerance (the factor is
   * then the MEDIAN, not an average, and confidence is 'low'). */
  conflict?: boolean;
  /** How many measurements were combined. */
  count: number;
}

/** metres-per-pixel implied by one measurement. Returns null for a non-positive or
 * non-finite measurement (never fabricate a factor from junk input). */
export function measurementMpp(m: ScaleMeasurement): number | null {
  if (!(m.realM > 0) || !(m.px > 0) || !Number.isFinite(m.realM) || !Number.isFinite(m.px)) {
    return null;
  }
  return m.realM / m.px;
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** The uncalibrated fallback calibration — a stable singleton value. */
export function uncalibrated(): Calibration {
  return { mpp: UNCALIBRATED_MPP, source: 'uncalibrated', confidence: 'none', calibrated: false, count: 0 };
}

/**
 * Calibrate from one or more independent KNOWN-DIMENSION measurements (each a real
 * length + its pixel span). Agreement within `tol` (relative) → averaged, high
 * confidence. Disagreement → conflict flagged, median returned, low confidence. No
 * valid measurement → uncalibrated fallback. `tol` defaults to 5% (typical of
 * hand-measured plan dimensions). Pure.
 */
export function calibrateFromMeasurements(measurements: ScaleMeasurement[], tol = 0.05): Calibration {
  const mpps: number[] = [];
  let src: CalibrationSource = 'known_dimension';
  for (const m of measurements) {
    const v = measurementMpp(m);
    if (v !== null) {
      mpps.push(v);
      src = m.source; // last valid source (all expected to share a source here)
    }
  }
  if (mpps.length === 0) return uncalibrated();

  const lo = Math.min(...mpps);
  const hi = Math.max(...mpps);
  const spread = hi > 0 ? (hi - lo) / hi : 0;

  if (mpps.length === 1) {
    return { mpp: mpps[0], source: src, confidence: 'high', calibrated: true, count: 1 };
  }
  if (spread <= tol) {
    const avg = mpps.reduce((a, b) => a + b, 0) / mpps.length;
    return { mpp: avg, source: src, confidence: 'high', calibrated: true, spread, count: mpps.length };
  }
  // Independent measurements conflict — do NOT average incompatible evidence.
  return {
    mpp: median(mpps),
    source: src,
    confidence: 'low',
    calibrated: true,
    spread,
    conflict: true,
    count: mpps.length,
  };
}

/** The longest-side pixel span of the first matching furniture item, as a proxy
 * measurement — or null when no such item exists. */
function furnitureMeasurement(
  rooms: SceneRoom[],
  match: (itemId: string) => boolean,
  realM: number,
  source: CalibrationSource,
): ScaleMeasurement | null {
  for (const r of rooms) {
    const f = r.furniture.find((it) => match(String(it.item_id)));
    if (f) return { realM, px: Math.max(f.w, f.h), source, label: String(f.item_id) };
  }
  return null;
}

export interface CalibrateOptions {
  /** Explicit known-dimension measurements (e.g. a parsed plan dimension mapped to
   * its wall-edge pixel span, or a stored scale). Highest priority when present. */
  measurements?: ScaleMeasurement[];
  /** A stored metres-per-pixel (e.g. the backend `scale_mm_per_px` once populated),
   * used when no explicit measurements are given. */
  storedMpp?: number | null;
  /** Relative agreement tolerance for multiple measurements. */
  tol?: number;
}

/**
 * Resolve the scene's calibration with explicit provenance. Priority:
 *   1. explicit known-dimension `measurements` (cross-checked),
 *   2. a `storedMpp` (e.g. the backend scale field once populated),
 *   3. the furniture proxy — a bed (≈2.0 m), else a side table (≈0.45 m),
 *   4. the uncalibrated fallback (0.01, `calibrated: false`).
 *
 * The furniture branch reproduces the legacy `computeMpp` numbers EXACTLY (bed first
 * across all rooms, then side table), so existing renders are unchanged — this only
 * ADDS provenance/confidence. Never invents a dimension.
 */
export function calibrateScale(rooms: SceneRoom[] | null | undefined, opts: CalibrateOptions = {}): Calibration {
  const list = rooms ?? [];

  if (opts.measurements && opts.measurements.length > 0) {
    const c = calibrateFromMeasurements(opts.measurements, opts.tol);
    if (c.calibrated) return c;
  }

  if (opts.storedMpp != null && opts.storedMpp > 0 && Number.isFinite(opts.storedMpp)) {
    return { mpp: opts.storedMpp, source: 'stored_scale', confidence: 'high', calibrated: true, count: 1 };
  }

  const bed = furnitureMeasurement(list, (id) => id.includes('bed'), BED_LENGTH_M, 'furniture_bed');
  if (bed) {
    const v = measurementMpp(bed)!;
    return { mpp: v, source: 'furniture_bed', confidence: 'medium', calibrated: true, count: 1 };
  }
  const st = furnitureMeasurement(list, (id) => id === 'side-table', SIDE_TABLE_M, 'furniture_side_table');
  if (st) {
    const v = measurementMpp(st)!;
    return { mpp: v, source: 'furniture_side_table', confidence: 'medium', calibrated: true, count: 1 };
  }

  return uncalibrated();
}
