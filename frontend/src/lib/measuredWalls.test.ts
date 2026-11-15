import { describe, it, expect } from 'vitest';
import { selectReconstructedShell, type RoomFrame } from './measuredWalls';
import type { ReconstructedWall } from './scene';

const ROOM: RoomFrame = { bx: 0, by: 0, bw: 1000, bh: 1000, cx: 500, cy: 500 };
const MPP = 0.01; // 1 px = 1 cm → easy arithmetic

function rw(partial: Partial<ReconstructedWall>): ReconstructedWall {
  return {
    id: 'rwall_001',
    seg: [100, 500, 900, 500], // 800 px horizontal, mid at (500,500) = room centre
    thickness_px: 20,
    thickness_source: 'MEASURED_FROM_PAIRED_FACES',
    ...partial,
  } as ReconstructedWall;
}

describe('selectReconstructedShell', () => {
  it('converts a high-confidence band to a measured shell segment with measured thickness', () => {
    const [w] = selectReconstructedShell([rw({})], ROOM, MPP);
    expect(w.lenM).toBeCloseTo(8, 6); // 800 px × 0.01
    expect(w.thicknessM).toBeCloseTo(0.2, 6); // 20 px × 0.01
    expect(w.measured).toBe(true);
    expect(w.angle).toBeCloseTo(0, 6);
    expect(w.midx).toBeCloseTo(0, 6);
    expect(w.midz).toBeCloseTo(0, 6);
  });

  it('INCLUDES a CONFIGURED_FALLBACK band (completeness) as measured:false at its fallback thickness', () => {
    const [w] = selectReconstructedShell(
      [rw({ thickness_source: 'CONFIGURED_FALLBACK', thickness_px: 10 })],
      ROOM,
      MPP,
    );
    expect(w).toBeDefined();
    expect(w.measured).toBe(false);
    expect(w.thicknessM).toBeCloseTo(0.1, 6); // 10 px × 0.01 — fallback, not mislabelled measured
  });

  it('INCLUDES an UNVERIFIED band as measured:false', () => {
    const [w] = selectReconstructedShell([rw({ thickness_source: 'UNVERIFIED' })], ROOM, MPP);
    expect(w).toBeDefined();
    expect(w.measured).toBe(false);
  });

  it('returns EVERY band — a mixed set is never silently reduced to the measured subset', () => {
    const bands = [
      rw({ id: 'a', thickness_source: 'MEASURED_FROM_PAIRED_FACES' }),
      rw({ id: 'b', seg: [100, 300, 900, 300], thickness_source: 'CONFIGURED_FALLBACK', thickness_px: 10 }),
      rw({ id: 'c', seg: [100, 700, 900, 700], thickness_source: 'UNVERIFIED', thickness_px: 10 }),
    ];
    const out = selectReconstructedShell(bands, ROOM, MPP);
    expect(out).toHaveLength(3); // all three physical walls, not just the 1 measured
    expect(out.filter((w) => w.measured)).toHaveLength(1);
    expect(out.filter((w) => !w.measured)).toHaveLength(2);
  });

  it('excludes a band whose midpoint is outside the padded room box', () => {
    const far = rw({ seg: [1900, 2000, 2100, 2000] }); // pad=350 → box [-350,1350]; mid (2000,2000) outside
    expect(selectReconstructedShell([far], ROOM, MPP)).toHaveLength(0);
  });

  it('drops a sub-0.15 m sliver', () => {
    const tiny = rw({ seg: [500, 500, 510, 500] }); // 10 px = 0.10 m
    expect(selectReconstructedShell([tiny], ROOM, MPP)).toHaveLength(0);
  });

  it('floors zero/invalid thickness at a non-zero depth', () => {
    const [w] = selectReconstructedShell([rw({ thickness_px: 0 })], ROOM, MPP);
    expect(w.thicknessM).toBeCloseTo(0.02, 6);
  });

  it('returns [] for empty / undefined input and non-positive mpp', () => {
    expect(selectReconstructedShell([], ROOM, MPP)).toEqual([]);
    expect(selectReconstructedShell(undefined, ROOM, MPP)).toEqual([]);
    expect(selectReconstructedShell([rw({})], ROOM, 0)).toEqual([]);
  });

  it('is offset relative to the room centre (not absolute px)', () => {
    const offset = rw({ seg: [600, 700, 800, 700] }); // mid (700,700)
    const [w] = selectReconstructedShell([offset], ROOM, MPP);
    expect(w.midx).toBeCloseTo((700 - 500) * MPP, 6); // 2.0
    expect(w.midz).toBeCloseTo((700 - 500) * MPP, 6);
  });
});
