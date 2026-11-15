import { describe, it, expect } from 'vitest';
import { buildCombinedRoom, collectRoomFloors } from './combinedScene';
import type { Scene, SceneRoom, SceneFurniture, OpeningPlacement } from './scene';

function furn(p: Partial<SceneFurniture>): SceneFurniture {
  return { uid: 'f1', item_id: 'bed', name: 'Bed', cx: 100, cy: 100, w: 40, h: 60, rotation: 0, ...p } as SceneFurniture;
}
function op(p: Partial<OpeningPlacement>): OpeningPlacement {
  return { id: 'o1', kind: 'door', source: 'editor', cx: 10, cy: 10, w: 40, h: 8, rotation: 0, wall_id: 'w1', verified: true, ...p } as OpeningPlacement;
}
function room(p: Partial<SceneRoom>): SceneRoom {
  return { id: 'r1', label: 'Room', bbox: [0, 0, 1, 1], furniture: [], ...p } as SceneRoom;
}
function scene(p: Partial<Scene>): Scene {
  return { page: { width: 1000, height: 750 }, walls: [], rooms: [], ...p } as Scene;
}

describe('buildCombinedRoom', () => {
  it('returns null for a null scene', () => {
    expect(buildCombinedRoom(null)).toBeNull();
  });

  it('renders with ZERO furniture when walls exist (the key DEF-3 fix)', () => {
    const c = buildCombinedRoom(scene({ walls: [[100, 100, 500, 100], [500, 100, 500, 400]], rooms: [room({})] }));
    expect(c).not.toBeNull();
    expect(c!.furniture).toHaveLength(0);
    // bbox spans the walls: [100,100] .. [500,400]
    expect(c!.bbox).toEqual([100, 100, 400, 300]);
  });

  it('derives extent from walls OUTSIDE the furniture bbox (walls not omitted)', () => {
    const c = buildCombinedRoom(
      scene({
        walls: [[0, 0, 900, 0], [900, 0, 900, 600]], // span far beyond furniture
        rooms: [room({ furniture: [furn({ cx: 450, cy: 300, w: 40, h: 60 })] })],
      }),
    );
    // bbox must reach the wall extent (0,0)..(900,600), not just the furniture box.
    expect(c!.bbox[0]).toBe(0);
    expect(c!.bbox[1]).toBe(0);
    expect(c!.bbox[2]).toBe(900);
    expect(c!.bbox[3]).toBe(600);
  });

  it('passes furniture through unchanged (no inference, aggregated across rooms)', () => {
    const f1 = furn({ uid: 'a', cx: 50, cy: 50 });
    const f2 = furn({ uid: 'b', cx: 200, cy: 200, item_id: 'sofa' });
    const c = buildCombinedRoom(scene({ walls: [[0, 0, 300, 0]], rooms: [room({ furniture: [f1] }), room({ id: 'r2', furniture: [f2] })] }));
    expect(c!.furniture).toEqual([f1, f2]); // exact identity/transforms, both rooms, nothing added
  });

  it('aggregates opening_placements from every room', () => {
    const c = buildCombinedRoom(
      scene({
        walls: [[0, 0, 300, 0]],
        rooms: [
          room({ opening_placements: [op({ id: 'd1', kind: 'door' })] }),
          room({ id: 'r2', opening_placements: [op({ id: 'w1', kind: 'window' })] }),
        ],
      }),
    );
    expect(c!.opening_placements!.map((o) => o.id).sort()).toEqual(['d1', 'w1']);
  });

  it('falls back to page bounds when there is no geometry or furniture', () => {
    const c = buildCombinedRoom(scene({ walls: [], rooms: [] }));
    expect(c!.bbox).toEqual([0, 0, 1000, 750]);
    expect(c!.furniture).toHaveLength(0);
  });

  it('returns null when there is no geometry, no furniture, and no page', () => {
    const c = buildCombinedRoom({ walls: [], rooms: [] } as unknown as Scene);
    expect(c).toBeNull();
  });

  it('carries no per-room boundary (follow-on) and a stable id', () => {
    const c = buildCombinedRoom(scene({ walls: [[0, 0, 100, 0]], rooms: [room({ boundary: [[0, 0], [100, 0], [100, 100]] })] }));
    expect(c!.id).toBe('floor-plan');
    expect(c!.boundary).toBeUndefined();
    // boundary vertices still contribute to the extent
    expect(c!.bbox[3]).toBe(100);
  });

  it('is pure (stable output across repeated calls)', () => {
    const s = scene({ walls: [[0, 0, 100, 0]], rooms: [room({ furniture: [furn({})] })] });
    expect(buildCombinedRoom(s)).toEqual(buildCombinedRoom(s));
  });
});

describe('collectRoomFloors', () => {
  const B: Array<[number, number]> = [[0, 0], [100, 0], [100, 80], [0, 80], [0, 0]];

  it('returns [] for null scene', () => {
    expect(collectRoomFloors(null)).toEqual([]);
  });

  it('includes a wall-proven architectural room boundary (vertices copied)', () => {
    const out = collectRoomFloors(scene({ rooms: [room({ geometry_source: 'architectural', boundary: B })] }));
    expect(out).toHaveLength(1);
    expect(out[0]).toEqual(B);
  });

  it('excludes a furniture-hull / UNCERTAIN fallback room', () => {
    const out = collectRoomFloors(scene({ rooms: [room({ geometry_source: 'fallback', boundary: B })] }));
    expect(out).toHaveLength(0);
  });

  it('excludes a room with no or too-short boundary', () => {
    const out = collectRoomFloors(
      scene({
        rooms: [
          room({ geometry_source: 'architectural' }), // no boundary
          room({ id: 'r2', geometry_source: 'architectural', boundary: [[0, 0], [1, 0]] as Array<[number, number]> }),
        ],
      }),
    );
    expect(out).toHaveLength(0);
  });

  it('includes every architectural room (and only those)', () => {
    const out = collectRoomFloors(
      scene({
        rooms: [
          room({ geometry_source: 'architectural', boundary: B }),
          room({ id: 'r2', geometry_source: 'fallback', boundary: B }),
          room({ id: 'r3', geometry_source: 'architectural', boundary: B }),
        ],
      }),
    );
    expect(out).toHaveLength(2);
  });
});
