import { describe, it, expect } from 'vitest';

import { splitWallWithOpenings, solidArea, type WallOpening } from './wallOpenings';

const door = (centerM: number, widthM: number, headM = 2.0): WallOpening => ({
  centerM, widthM, kind: 'door', sillM: 0, headM,
});
const win = (centerM: number, widthM: number, sillM = 0.9, headM = 2.1): WallOpening => ({
  centerM, widthM, kind: 'window', sillM, headM,
});

const inBounds = (sol: ReturnType<typeof splitWallWithOpenings>, L: number, H: number) =>
  sol.every((s) =>
    s.offStartM >= -1e-9 && s.offEndM <= L + 1e-9 && s.offStartM < s.offEndM &&
    s.yBottomM >= -1e-9 && s.yTopM <= H + 1e-9 && s.yBottomM < s.yTopM);

describe('splitWallWithOpenings', () => {
  it('no openings -> one full-height solid covering the whole wall', () => {
    const s = splitWallWithOpenings(4, 2.7, []);
    expect(s).toHaveLength(1);
    expect(s[0]).toMatchObject({ offStartM: 0, offEndM: 4, yBottomM: 0, yTopM: 2.7 });
    expect(solidArea(s)).toBeCloseTo(4 * 2.7, 9);
  });

  it('a door removes exactly a floor->head gap (no sill band)', () => {
    const L = 4, H = 2.7, w = 0.9, head = 2.0;
    const s = splitWallWithOpenings(L, H, [door(2, w, head)]);
    // two full-height side spans + one head band above the door
    expect(s.filter((x) => x.yBottomM === 0 && x.yTopM === H)).toHaveLength(2);
    expect(s.some((x) => Math.abs(x.yBottomM - head) < 1e-9 && Math.abs(x.yTopM - H) < 1e-9)).toBe(true);
    // NO sill band (nothing below the door)
    expect(s.some((x) => x.yBottomM === 0 && x.yTopM < head - 1e-9 && x.offStartM > 0)).toBe(false);
    // hole area = width x head
    expect(solidArea(s)).toBeCloseTo(L * H - w * head, 9);
    expect(inBounds(s, L, H)).toBe(true);
  });

  it('a window removes a hole and keeps a sill band below + head band above', () => {
    const L = 4, H = 2.7, w = 1.2, sill = 0.9, head = 2.1;
    const s = splitWallWithOpenings(L, H, [win(2, w, sill, head)]);
    expect(s.filter((x) => x.yBottomM === 0 && x.yTopM === H)).toHaveLength(2); // side spans
    expect(s.some((x) => Math.abs(x.yBottomM - 0) < 1e-9 && Math.abs(x.yTopM - sill) < 1e-9)).toBe(true); // sill
    expect(s.some((x) => Math.abs(x.yBottomM - head) < 1e-9 && Math.abs(x.yTopM - H) < 1e-9)).toBe(true); // head
    // hole area = width x (head - sill)
    expect(solidArea(s)).toBeCloseTo(L * H - w * (head - sill), 9);
    expect(inBounds(s, L, H)).toBe(true);
  });

  it('an opening at the wall start clips (no left span) and conserves hole area', () => {
    const L = 4, H = 2.7, head = 2.0;
    const s = splitWallWithOpenings(L, H, [door(0.2, 1.0, head)]); // spans [0, 0.7]
    expect(s.some((x) => x.offStartM < 1e-9 && x.yBottomM === 0 && x.yTopM === H)).toBe(false); // no left FULL-HEIGHT span
    expect(solidArea(s)).toBeCloseTo(L * H - 0.7 * head, 9); // clipped width 0.7
    expect(inBounds(s, L, H)).toBe(true);
  });

  it('an opening wider than the wall yields no side spans, only clipped bands', () => {
    const L = 2, H = 2.7, head = 2.0;
    const s = splitWallWithOpenings(L, H, [door(1, 10, head)]); // clips to [0, L]
    expect(s.some((x) => x.yBottomM === 0 && x.yTopM === H)).toBe(false); // no full-height solid
    expect(solidArea(s)).toBeCloseTo(L * (H - head), 9); // only the head band remains
    expect(inBounds(s, L, H)).toBe(true);
  });

  it('two openings produce three full-height side spans + their bands', () => {
    const L = 6, H = 2.7;
    const s = splitWallWithOpenings(L, H, [door(1.5, 0.9, 2.0), win(4.5, 1.2, 0.9, 2.1)]);
    expect(s.filter((x) => x.yBottomM === 0 && x.yTopM === H)).toHaveLength(3);
    expect(solidArea(s)).toBeCloseTo(L * H - 0.9 * 2.0 - 1.2 * (2.1 - 0.9), 9);
    expect(inBounds(s, L, H)).toBe(true);
  });

  it('overlapping openings are coalesced (no overlapping full-height side spans)', () => {
    const L = 5, H = 2.7;
    const s = splitWallWithOpenings(L, H, [door(2, 1.4, 2.0), door(2.6, 1.4, 2.0)]); // [1.3,2.7] & [1.9,3.3]
    const sides = s.filter((x) => x.yBottomM === 0 && x.yTopM === H).sort((a, b) => a.offStartM - b.offStartM);
    for (let i = 1; i < sides.length; i++) expect(sides[i].offStartM).toBeGreaterThanOrEqual(sides[i - 1].offEndM - 1e-9);
    expect(inBounds(s, L, H)).toBe(true);
  });

  it('degenerate walls return nothing', () => {
    expect(splitWallWithOpenings(0, 2.7, [door(0, 1)])).toHaveLength(0);
    expect(splitWallWithOpenings(4, 0, [door(2, 1)])).toHaveLength(0);
  });

  it('is deterministic (identical input -> identical output)', () => {
    const o = [win(2, 1.2), door(4, 0.9)];
    expect(splitWallWithOpenings(6, 2.7, o)).toEqual(splitWallWithOpenings(6, 2.7, o));
  });
});
