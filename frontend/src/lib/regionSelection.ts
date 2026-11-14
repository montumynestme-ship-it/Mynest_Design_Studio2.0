/**
 * Pure, framework-free region-selection geometry for the Draw Area tool.
 *
 * Everything here operates in CANONICAL WORLD PIXELS — the same frame as
 * `PlacedItem` (center `x,y`, size `w,h`, `rotation` degrees) and the floor-plan
 * `Scene` (walls `[x1,y1,x2,y2]`, openings `cx,cy,w,h,rotation`). It NEVER mutates
 * or clips any input: it only classifies what the drawn rectangle selects, so the
 * canonical design stays authoritative (CLAUDE.md RULE #1). No DOM, no React — unit
 * testable in isolation.
 */
import type { PlacedItem } from '../types/design';
import type { Scene, SceneRoom, SceneOpening, OpeningPlacement } from './scene';

/** Axis-aligned selection rectangle in world px: top-left (`x,y`) + positive size. */
export interface Region {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type Containment = 'contained' | 'partial' | 'outside';

export interface RegionFurniture {
  uid: string;
  item_id: string;
  name: string;
  containment: Containment;
}

export interface RegionArchElement {
  /** Stable id (wall index as `wall-<n>`, or the opening's own id). */
  id: string;
  kind: 'wall' | 'door' | 'window';
  /** 'contained' when fully inside the region, else 'partial' (it only crosses). */
  containment: 'contained' | 'partial';
}

export interface RegionSelectionResult {
  region: Region;
  fullyContained: RegionFurniture[];
  partial: RegionFurniture[];
  outside: RegionFurniture[];
  walls: RegionArchElement[];
  doors: RegionArchElement[];
  windows: RegionArchElement[];
  warnings: string[];
}

/** Below this side length (world px) a selection is treated as too small / a stray click. */
export const MIN_REGION_SIDE_PX = 16;

/** Item ids that are STYLING-ONLY annotations, not real furniture: they carry no 3D
 * geometry and are deliberately excluded from room grouping/membership everywhere else.
 * A region render must never select or render them (they would have no mesh and would fail
 * the §L geometry contract). Mirror of the backend's ``_REGION_ANNOTATION_ITEM_IDS``. */
export const REGION_EXCLUDED_ITEM_IDS = new Set<string>(['room-tag']);

type Vec = [number, number];

/** Normalize two drag corners into a Region with a positive size (top-left origin). */
export function normalizeRegion(x0: number, y0: number, x1: number, y1: number): Region {
  const x = Math.min(x0, x1);
  const y = Math.min(y0, y1);
  return { x, y, w: Math.abs(x1 - x0), h: Math.abs(y1 - y0) };
}

/** The four rotated world-space corners of a center/size/rotation footprint. */
function footprintCorners(cx: number, cy: number, w: number, h: number, rotationDeg: number): Vec[] {
  const r = (rotationDeg * Math.PI) / 180;
  const c = Math.cos(r);
  const s = Math.sin(r);
  const hw = w / 2;
  const hh = h / 2;
  const local: Vec[] = [
    [-hw, -hh],
    [hw, -hh],
    [hw, hh],
    [-hw, hh],
  ];
  return local.map(([dx, dy]) => [cx + dx * c - dy * s, cy + dx * s + dy * c]);
}

function regionCorners(region: Region): Vec[] {
  const { x, y, w, h } = region;
  return [
    [x, y],
    [x + w, y],
    [x + w, y + h],
    [x, y + h],
  ];
}

function pointInRegion(px: number, py: number, region: Region): boolean {
  return px >= region.x && px <= region.x + region.w && py >= region.y && py <= region.y + region.h;
}

function projectOntoAxis(points: Vec[], axis: Vec): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (const [px, py] of points) {
    const d = px * axis[0] + py * axis[1];
    if (d < min) min = d;
    if (d > max) max = d;
  }
  return [min, max];
}

function intervalsOverlap(a: [number, number], b: [number, number]): boolean {
  return a[0] <= b[1] && b[0] <= a[1];
}

/**
 * Separating Axis Theorem test between an oriented footprint (its corners) and the
 * axis-aligned region. Axes tested: world X, world Y, and the footprint's own two edge
 * directions — sufficient for two convex quads. Returns true when they overlap at all.
 */
function footprintOverlapsRegion(corners: Vec[], region: Region): boolean {
  const rCorners = regionCorners(region);
  const edge1: Vec = [corners[1][0] - corners[0][0], corners[1][1] - corners[0][1]];
  const edge2: Vec = [corners[3][0] - corners[0][0], corners[3][1] - corners[0][1]];
  const axes: Vec[] = [
    [1, 0],
    [0, 1],
    edge1,
    edge2,
  ];
  for (const axis of axes) {
    const len = Math.hypot(axis[0], axis[1]);
    if (len === 0) continue;
    const a: Vec = [axis[0] / len, axis[1] / len];
    if (!intervalsOverlap(projectOntoAxis(corners, a), projectOntoAxis(rCorners, a))) {
      return false; // a separating axis → no overlap
    }
  }
  return true;
}

function classifyFootprint(
  cx: number,
  cy: number,
  w: number,
  h: number,
  rotationDeg: number,
  region: Region,
): Containment {
  const corners = footprintCorners(cx, cy, w, h, rotationDeg);
  const allInside = corners.every(([px, py]) => pointInRegion(px, py, region));
  if (allInside) return 'contained';
  return footprintOverlapsRegion(corners, region) ? 'partial' : 'outside';
}

/** Liang–Barsky: does segment (x1,y1)-(x2,y2) touch the axis-aligned region at all? */
function segmentIntersectsRegion(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  region: Region,
): boolean {
  if (pointInRegion(x1, y1, region) || pointInRegion(x2, y2, region)) return true;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const p = [-dx, dx, -dy, dy];
  const q = [x1 - region.x, region.x + region.w - x1, y1 - region.y, region.y + region.h - y1];
  let u1 = 0;
  let u2 = 1;
  for (let i = 0; i < 4; i++) {
    if (p[i] === 0) {
      if (q[i] < 0) return false; // parallel and outside this boundary
    } else {
      const t = q[i] / p[i];
      if (p[i] < 0) {
        if (t > u2) return false;
        if (t > u1) u1 = t;
      } else {
        if (t < u1) return false;
        if (t < u2) u2 = t;
      }
    }
  }
  return u1 <= u2;
}

function openingId(o: SceneOpening | OpeningPlacement, kind: 'door' | 'window', idx: number): string {
  const raw = (o as { id?: string | number }).id;
  return raw !== undefined && raw !== null ? `${kind}-${raw}` : `${kind}-idx-${idx}`;
}

/** Collect doors/windows across ALL rooms (region is label-independent), deduped by id. */
function collectOpenings(rooms: SceneRoom[], kind: 'door' | 'window'): Array<{ id: string; o: SceneOpening | OpeningPlacement }> {
  const out: Array<{ id: string; o: SceneOpening | OpeningPlacement }> = [];
  const seen = new Set<string>();
  const push = (o: SceneOpening | OpeningPlacement, idx: number) => {
    const id = openingId(o, kind, idx);
    if (seen.has(id)) return;
    seen.add(id);
    out.push({ id, o });
  };
  let i = 0;
  for (const r of rooms) {
    const primary = kind === 'door' ? r.doors : r.windows;
    const supplemental = kind === 'door' ? r.supplemental_doors : r.supplemental_windows;
    for (const o of primary ?? []) push(o, i++);
    for (const o of supplemental ?? []) push(o, i++);
    for (const pl of r.opening_placements ?? []) {
      if (pl.kind === kind) push(pl, i++);
    }
  }
  return out;
}

function classifyOpenings(
  rooms: SceneRoom[],
  kind: 'door' | 'window',
  region: Region,
): RegionArchElement[] {
  const result: RegionArchElement[] = [];
  for (const { id, o } of collectOpenings(rooms, kind)) {
    const c = classifyFootprint(o.cx, o.cy, o.w, o.h, o.rotation ?? 0, region);
    if (c !== 'outside') result.push({ id, kind, containment: c });
  }
  return result;
}

/**
 * Classify every placed furniture item and every intersecting architectural element
 * against the drawn region. Nothing is omitted: partially-intersecting items are reported
 * SEPARATELY from fully-contained ones (never silently dropped), and outside items are
 * listed too. Pure — inputs are never mutated or clipped.
 */
export function selectRegion(region: Region, placed: PlacedItem[], scene: Scene | null): RegionSelectionResult {
  const fullyContained: RegionFurniture[] = [];
  const partial: RegionFurniture[] = [];
  const outside: RegionFurniture[] = [];

  for (const p of placed) {
    // Skip styling-only annotations (room-tags): they have no 3D geometry, so they must
    // never enter a render set (they would fail §L / have no mesh). Grouping-only metadata.
    if (REGION_EXCLUDED_ITEM_IDS.has(p.item.id)) continue;
    const containment = classifyFootprint(p.x, p.y, p.w, p.h, p.rotation, region);
    const entry: RegionFurniture = {
      uid: p.uid,
      item_id: p.item.id,
      name: p.label ?? p.item.name,
      containment,
    };
    if (containment === 'contained') fullyContained.push(entry);
    else if (containment === 'partial') partial.push(entry);
    else outside.push(entry);
  }

  const walls: RegionArchElement[] = [];
  if (scene?.walls) {
    scene.walls.forEach(([x1, y1, x2, y2], idx) => {
      if (segmentIntersectsRegion(x1, y1, x2, y2, region)) {
        const contained =
          pointInRegion(x1, y1, region) && pointInRegion(x2, y2, region) ? 'contained' : 'partial';
        walls.push({ id: `wall-${idx}`, kind: 'wall', containment: contained });
      }
    });
  }

  const rooms = scene?.rooms ?? [];
  const doors = classifyOpenings(rooms, 'door', region);
  const windows = classifyOpenings(rooms, 'window', region);

  const warnings: string[] = [];
  if (region.w < MIN_REGION_SIDE_PX || region.h < MIN_REGION_SIDE_PX) {
    warnings.push('Selection is very small — draw a larger area to capture furniture.');
  }
  if (fullyContained.length === 0 && partial.length === 0) {
    warnings.push('No furniture falls inside the selected area.');
  }

  return { region, fullyContained, partial, outside, walls, doors, windows, warnings };
}

/**
 * The furniture uids this selection renders: always the fully-contained items, plus the
 * partially-intersecting ones when `includePartial` is true (the default). Deduped, stable
 * order (contained first). This is the exact set sent to the region base render + backend.
 */
export function regionSelectedUids(result: RegionSelectionResult, includePartial: boolean): string[] {
  const uids = result.fullyContained.map((f) => f.uid);
  if (includePartial) uids.push(...result.partial.map((f) => f.uid));
  return Array.from(new Set(uids));
}

/** A region is renderable when it is big enough AND selects at least one item. */
export function isRegionRenderable(result: RegionSelectionResult, includePartial: boolean): boolean {
  if (result.region.w < MIN_REGION_SIDE_PX || result.region.h < MIN_REGION_SIDE_PX) return false;
  return regionSelectedUids(result, includePartial).length > 0;
}
