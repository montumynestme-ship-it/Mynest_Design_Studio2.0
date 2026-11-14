// Geometry regression tests for the Draw Area region-selection service. Pure world-coordinate
// math — no DOM, no zoom/pan (the canvas converts screen→world BEFORE calling this, so selection
// is pan/zoom invariant by construction). Covers spec §10 geometry: contained / partial / outside,
// rotated footprints, wall + door/window intersection, empty + zero-area, and duplicate prevention.

import { describe, expect, it } from 'vitest';

import {
  isRegionRenderable,
  normalizeRegion,
  regionSelectedUids,
  selectRegion,
  type Region,
} from './regionSelection';
import type { PlacedItem } from '../types/design';
import type { Scene, SceneRoom } from './scene';

function item(id: string, name: string) {
  // Minimal FurnitureItem — selection only reads id + name.
  return { id, name } as PlacedItem['item'];
}

function pi(
  uid: string,
  x: number,
  y: number,
  w: number,
  h: number,
  rotation = 0,
  itemId = 'chair',
): PlacedItem {
  return { uid, item: item(itemId, itemId), x, y, w, h, rotation };
}

function scene(partial: Partial<Scene> = {}): Scene {
  return {
    page: { width: 2000, height: 2000 },
    walls: [],
    rooms: [],
    ...partial,
  };
}

function room(partial: Partial<SceneRoom> = {}): SceneRoom {
  return {
    id: 'r1',
    label: 'Room 1',
    bbox: [0, 0, 1000, 1000],
    furniture: [],
    ...partial,
  };
}

// Region: top-left (100,100), 300×200 → spans x[100,400], y[100,300].
const REGION: Region = { x: 100, y: 100, w: 300, h: 200 };

describe('selectRegion — furniture containment', () => {
  it('fully contains an item well inside the region', () => {
    const r = selectRegion(REGION, [pi('a', 200, 180, 40, 40)], null);
    expect(r.fullyContained.map((f) => f.uid)).toEqual(['a']);
    expect(r.partial).toHaveLength(0);
    expect(r.outside).toHaveLength(0);
  });

  it('marks an item straddling the region edge as PARTIAL (never dropped, never contained)', () => {
    // Centered on the left edge x=100 → half in, half out.
    const r = selectRegion(REGION, [pi('a', 100, 180, 60, 40)], null);
    expect(r.partial.map((f) => f.uid)).toEqual(['a']);
    expect(r.fullyContained).toHaveLength(0);
    expect(r.outside).toHaveLength(0);
  });

  it('marks a far item as OUTSIDE', () => {
    const r = selectRegion(REGION, [pi('a', 900, 900, 40, 40)], null);
    expect(r.outside.map((f) => f.uid)).toEqual(['a']);
    expect(r.fullyContained).toHaveLength(0);
    expect(r.partial).toHaveLength(0);
  });

  it('a region fully inside a large item counts as PARTIAL (they still intersect)', () => {
    const r = selectRegion(REGION, [pi('big', 250, 200, 2000, 2000)], null);
    expect(r.partial.map((f) => f.uid)).toEqual(['big']);
  });
});

describe('selectRegion — rotated footprints', () => {
  it('detects a rotated corner entering the region (AABB would miss)', () => {
    // Center (450,290): unrotated 80×80 spans x[410,490] → misses x≤400 entirely (OUTSIDE).
    // Rotated 45°, its left corner reaches (~393,290) → pokes into the region (PARTIAL).
    const outside0 = selectRegion(REGION, [pi('a', 450, 290, 80, 80, 0)], null);
    expect(outside0.outside.map((f) => f.uid)).toEqual(['a']);
    const rotated = selectRegion(REGION, [pi('a', 450, 290, 80, 80, 45)], null);
    expect(rotated.partial.map((f) => f.uid)).toEqual(['a']);
  });

  it('a rotated item wholly inside is still fully contained', () => {
    const r = selectRegion(REGION, [pi('a', 250, 200, 50, 50, 30)], null);
    expect(r.fullyContained.map((f) => f.uid)).toEqual(['a']);
  });
});

describe('selectRegion — architectural intersections', () => {
  it('reports a wall segment crossing the region, and ignores one outside it', () => {
    const s = scene({
      walls: [
        [0, 180, 1000, 180], // horizontal line through the region
        [0, 900, 1000, 900], // well below the region
      ],
    });
    const r = selectRegion(REGION, [], s);
    expect(r.walls.map((w) => w.id)).toEqual(['wall-0']);
    expect(r.walls[0].containment).toBe('partial'); // crosses, not fully inside
  });

  it('classifies doors/windows across rooms and dedupes shared ids', () => {
    const s = scene({
      rooms: [
        room({
          id: 'r1',
          doors: [{ id: 'd1', cx: 200, cy: 100, w: 40, h: 10, rotation: 0 }],
          windows: [{ id: 'w1', cx: 900, cy: 900, w: 40, h: 10, rotation: 0 }],
        }),
        // Same door id appears again (shared opening) → must not double-count.
        room({ id: 'r2', doors: [{ id: 'd1', cx: 200, cy: 100, w: 40, h: 10, rotation: 0 }] }),
      ],
    });
    const r = selectRegion(REGION, [], s);
    expect(r.doors.map((d) => d.id)).toEqual(['door-d1']); // deduped, inside region
    expect(r.windows).toHaveLength(0); // the window is far outside
  });
});

describe('selectRegion — excludes styling-only annotations', () => {
  it('never selects a room-tag annotation (no geometry), even when inside the box', () => {
    const r = selectRegion(
      REGION,
      [pi('real', 200, 180, 40, 40, 0, 'chair'), pi('tag', 210, 190, 40, 20, 0, 'room-tag')],
      null,
    );
    const all = [...r.fullyContained, ...r.partial, ...r.outside].map((f) => f.uid);
    expect(all).toEqual(['real']); // the room-tag is omitted entirely
    expect(regionSelectedUids(r, true)).toEqual(['real']);
  });
});

describe('selectRegion — warnings', () => {
  it('warns when the selection contains no furniture', () => {
    const r = selectRegion(REGION, [pi('a', 900, 900, 40, 40)], null);
    expect(r.warnings.some((w) => /no furniture/i.test(w))).toBe(true);
  });

  it('warns when the region is too small', () => {
    const tiny: Region = { x: 100, y: 100, w: 4, h: 4 };
    const r = selectRegion(tiny, [pi('a', 101, 101, 2, 2)], null);
    expect(r.warnings.some((w) => /small/i.test(w))).toBe(true);
    expect(isRegionRenderable(r, true)).toBe(false);
  });
});

describe('regionSelectedUids + normalizeRegion', () => {
  it('includes partials by default and excludes them on request, with dedup', () => {
    const r = selectRegion(REGION, [pi('a', 200, 180, 40, 40), pi('b', 100, 180, 60, 40)], null);
    expect(regionSelectedUids(r, true)).toEqual(['a', 'b']); // a contained, b partial
    expect(regionSelectedUids(r, false)).toEqual(['a']);
  });

  it('renderable only when big enough AND at least one item selected', () => {
    const r = selectRegion(REGION, [pi('a', 200, 180, 40, 40)], null);
    expect(isRegionRenderable(r, true)).toBe(true);
    const empty = selectRegion(REGION, [], null);
    expect(isRegionRenderable(empty, true)).toBe(false);
  });

  it('normalizeRegion yields a positive-size top-left rect from any drag direction', () => {
    expect(normalizeRegion(400, 300, 100, 100)).toEqual({ x: 100, y: 100, w: 300, h: 200 });
    expect(normalizeRegion(100, 100, 400, 300)).toEqual({ x: 100, y: 100, w: 300, h: 200 });
  });
});
