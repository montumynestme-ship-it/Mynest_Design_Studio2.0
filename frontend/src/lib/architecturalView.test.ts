import { describe, it, expect } from 'vitest';
import { buildArchitecturalView } from './architecturalView';
import type { Scene, SceneRoom, OpeningPlacement } from './scene';

function scene(partial: Partial<Scene>): Scene {
  return {
    page: { width: 1000, height: 750 },
    walls: [],
    rooms: [],
    ...partial,
  } as Scene;
}

function room(partial: Partial<SceneRoom>): SceneRoom {
  return {
    id: 'r1',
    label: 'Bedroom',
    bbox: [0, 0, 100, 100],
    furniture: [],
    ...partial,
  } as SceneRoom;
}

function opening(partial: Partial<OpeningPlacement>): OpeningPlacement {
  return {
    id: 'o1',
    kind: 'door',
    source: 'editor',
    cx: 50,
    cy: 10,
    w: 40,
    h: 8,
    rotation: 0,
    wall_id: 'wall_001',
    verified: true,
    ...partial,
  } as OpeningPlacement;
}

describe('buildArchitecturalView', () => {
  it('1. walls are carried at their exact world-px coordinates (no scale applied)', () => {
    const v = buildArchitecturalView(scene({ walls: [[10, 20, 310, 20]] }));
    expect(v.available).toBe(true);
    expect(v.walls).toEqual([{ x1: 10, y1: 20, x2: 310, y2: 20 }]);
  });

  it('2. multiple connected segments render individually — no fabricated connection/merge', () => {
    // Two collinear touching strokes stay TWO walls (face strokes preserved).
    const v = buildArchitecturalView(scene({ walls: [[0, 0, 100, 0], [100, 0, 200, 0]] }));
    expect(v.walls).toHaveLength(2);
    expect(v.walls[0]).toEqual({ x1: 0, y1: 0, x2: 100, y2: 0 });
    expect(v.walls[1]).toEqual({ x1: 100, y1: 0, x2: 200, y2: 0 });
  });

  it('3. room polygons keep their original vertices (closing duplicate dropped once)', () => {
    const v = buildArchitecturalView(
      scene({
        rooms: [room({ boundary: [[0, 0], [100, 0], [100, 80], [0, 80], [0, 0]], validation_status: 'CONFIRMED', geometry_source: 'architectural' })],
      }),
    );
    expect(v.rooms[0].points).toEqual([[0, 0], [100, 0], [100, 80], [0, 80]]);
    expect(v.rooms[0].confirmed).toBe(true);
  });

  it('4. concave boundary vertices are preserved unchanged', () => {
    const concave: Array<[number, number]> = [[0, 0], [100, 0], [100, 100], [60, 100], [60, 50], [0, 50]];
    const v = buildArchitecturalView(scene({ rooms: [room({ boundary: concave })] }));
    expect(v.rooms[0].points).toEqual(concave);
  });

  it('5. an incomplete (non-closed) boundary is NOT artificially closed', () => {
    const open: Array<[number, number]> = [[0, 0], [100, 0], [100, 80]];
    const v = buildArchitecturalView(scene({ rooms: [room({ boundary: open })] }));
    // No extra vertex is appended — the data is passed through as-is.
    expect(v.rooms[0].points).toEqual(open);
  });

  it('6+7. door verified vs uncertain are distinguishable', () => {
    const v = buildArchitecturalView(
      scene({
        rooms: [
          room({ opening_placements: [opening({ id: 'd1', kind: 'door', verified: true })] }),
          room({ id: 'r2', opening_placements: [opening({ id: 'd2', kind: 'door', verified: false })] }),
        ],
      }),
    );
    const d1 = v.openings.find((o) => o.id === 'd1')!;
    const d2 = v.openings.find((o) => o.id === 'd2')!;
    expect(d1.verified).toBe(true);
    expect(d2.verified).toBe(false);
    expect(d1.kind).toBe('door');
  });

  it('8+9. window verified vs uncertain are distinguishable', () => {
    const v = buildArchitecturalView(
      scene({
        rooms: [
          room({ opening_placements: [opening({ id: 'w1', kind: 'window', verified: true })] }),
          room({ id: 'r2', opening_placements: [opening({ id: 'w2', kind: 'window', verified: false })] }),
        ],
      }),
    );
    expect(v.openings.find((o) => o.id === 'w1')!.verified).toBe(true);
    expect(v.openings.find((o) => o.id === 'w2')!.verified).toBe(false);
    expect(v.openings.every((o) => o.kind === 'window')).toBe(true);
  });

  it('10. multiple openings on one wall retain their individual positions', () => {
    const v = buildArchitecturalView(
      scene({
        rooms: [
          room({
            opening_placements: [
              opening({ id: 'a', cx: 30, cy: 10 }),
              opening({ id: 'b', cx: 120, cy: 10 }),
            ],
          }),
        ],
      }),
    );
    expect(v.openings.map((o) => [o.id, o.cx])).toEqual([['a', 30], ['b', 120]]);
  });

  it('11. zero furniture does not prevent architectural rendering', () => {
    const v = buildArchitecturalView(
      scene({
        walls: [[0, 0, 100, 0]],
        rooms: [room({ furniture: [], boundary: [[0, 0], [100, 0], [100, 80], [0, 80]], opening_placements: [opening({})] })],
      }),
    );
    expect(v.available).toBe(true);
    expect(v.walls).toHaveLength(1);
    expect(v.rooms).toHaveLength(1);
    expect(v.openings).toHaveLength(1);
  });

  it('12. missing architectural data yields an honest empty state', () => {
    expect(buildArchitecturalView(null).available).toBe(false);
    expect(buildArchitecturalView(scene({ walls: [], rooms: [] })).available).toBe(false);
  });

  it('13. an UNCERTAIN furniture-hull fallback room is not marked confirmed', () => {
    const v = buildArchitecturalView(
      scene({ rooms: [room({ validation_status: 'UNCERTAIN', geometry_source: 'fallback', boundary: [[0, 0], [10, 0], [10, 10], [0, 10]] })] }),
    );
    expect(v.rooms[0].confirmed).toBe(false);
  });

  it('14. rooms with a blank label expose label=null (no fabricated label)', () => {
    const v = buildArchitecturalView(scene({ rooms: [room({ label: '  ', boundary: [[0, 0], [10, 0], [10, 10]] })] }));
    expect(v.rooms[0].label).toBeNull();
    expect(v.rooms[0].labelAt).toBeNull();
  });

  it('15. building twice from the same scene is pure (stable output)', () => {
    const s = scene({ walls: [[0, 0, 50, 0]], rooms: [room({ boundary: [[0, 0], [50, 0], [50, 50]] })] });
    expect(buildArchitecturalView(s)).toEqual(buildArchitecturalView(s));
  });
});
