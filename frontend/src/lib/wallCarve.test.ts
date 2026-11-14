import { describe, it, expect } from 'vitest';
import { carveWallSegment, type CarveSeg, type CarveOpening, type CarveOpts } from './wallCarve';

const OPTS: CarveOpts = {
  wallHeight: 2.7,
  wallThickness: 0.1,
  perpTol: 0.4,
  angleTol: (20 * Math.PI) / 180,
};

// A 4 m horizontal wall centred at the room origin.
const SEG: CarveSeg = { lenM: 4, angle: 0, midx: 0, midz: 0 };
const WINDOW: CarveOpening = { mx: 0, mz: 0, angle: 0, half: 0.5, head: 2.2, sill: 0.9 };
const DOOR: CarveOpening = { mx: 0, mz: 0, angle: 0, half: 0.45, head: 2.1, sill: 0 };

describe('carveWallSegment', () => {
  it('no openings → a single full-length solid run, no header/sill', () => {
    const r = carveWallSegment(SEG, [], OPTS);
    expect(r.solids).toHaveLength(1);
    expect(r.solids[0].offset).toBeCloseTo(0, 6);
    expect(r.solids[0].length).toBeCloseTo(4.1, 6); // lenM + wallThickness (corner fudge kept)
    expect(r.headers).toHaveLength(0);
    expect(r.sills).toHaveLength(0);
  });

  it('centred window → two jambs, one header, one sill; void equals the opening', () => {
    const r = carveWallSegment(SEG, [WINDOW], OPTS);
    expect(r.solids).toHaveLength(2);
    // Jambs are symmetric: from ±0.5 (opening edge) out to ±2.05 (half of 4.1).
    const lens = r.solids.map((s) => s.length).sort();
    expect(lens[0]).toBeCloseTo(1.55, 6);
    expect(lens[1]).toBeCloseTo(1.55, 6);
    expect(r.headers).toHaveLength(1);
    expect(r.headers[0].length).toBeCloseTo(1.0, 6); // opening span = 2·half
    expect(r.headers[0].height).toBeCloseTo(0.5, 6); // 2.7 - 2.2
    expect(r.headers[0].yCenter).toBeCloseTo(2.45, 6);
    expect(r.sills).toHaveLength(1);
    expect(r.sills[0].height).toBeCloseTo(0.9, 6);
  });

  it('door → two jambs + header, NO sill, header preserves wall above the lintel', () => {
    const r = carveWallSegment(SEG, [DOOR], OPTS);
    expect(r.solids).toHaveLength(2);
    expect(r.headers).toHaveLength(1);
    expect(r.headers[0].height).toBeCloseTo(0.6, 6); // 2.7 - 2.1 lintel
    expect(r.sills).toHaveLength(0);
  });

  it('opening too far perpendicular (different wall) is ignored', () => {
    const far: CarveOpening = { ...WINDOW, mz: 1.0 }; // 1 m off a wall at z=0, > perpTol
    const r = carveWallSegment(SEG, [far], OPTS);
    expect(r.solids).toHaveLength(1);
    expect(r.solids[0].length).toBeCloseTo(4.1, 6);
    expect(r.headers).toHaveLength(0);
  });

  it('opening whose orientation disagrees with the wall is ignored', () => {
    const perp: CarveOpening = { ...WINDOW, angle: Math.PI / 2 };
    const r = carveWallSegment(SEG, [perp], OPTS);
    expect(r.solids).toHaveLength(1);
    expect(r.headers).toHaveLength(0);
  });

  it('two openings on one wall → three solid runs', () => {
    const left: CarveOpening = { ...DOOR, mx: -1.2 };
    const right: CarveOpening = { ...WINDOW, mx: 1.2 };
    const r = carveWallSegment(SEG, [left, right], OPTS);
    expect(r.solids).toHaveLength(3);
    expect(r.headers).toHaveLength(2);
    expect(r.sills).toHaveLength(1); // only the window has a sill
  });

  it('a verified opening off the end of the segment does not carve it', () => {
    const offEnd: CarveOpening = { ...WINDOW, mx: 5.0 }; // beyond +2.05
    const r = carveWallSegment(SEG, [offEnd], OPTS);
    expect(r.solids).toHaveLength(1);
    expect(r.solids[0].length).toBeCloseTo(4.1, 6);
  });
});
