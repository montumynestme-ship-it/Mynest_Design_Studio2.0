/**
 * Phase 1 — pure data transform for the additive 2D ARCHITECTURAL VIEW.
 *
 * Maps an existing `/scene` payload (walls + rooms + opening placements, all already
 * in WORLD PX — the same frame as the plan image and furniture) into flat render
 * primitives the Konva overlay draws. This file performs NO geometry correction:
 * it never moves, merges, snaps, closes, resizes, rotates, or fabricates anything.
 * It only SELECTS and CLASSIFIES existing values, and carries their verified/uncertain
 * state through faithfully (CLAUDE.md RULE #1).
 *
 * Coordinate note: every coordinate here is world px exactly as the backend emitted it.
 * No mpp / SCALE / DEFAULT_MPP is applied — physical millimetres are NOT claimed. The
 * canvas Stage transform (pan/zoom) is what maps world px to screen, identically to the
 * plan image, so vector architecture stays aligned with the raster without any new scale.
 */
import type { Scene, SceneRoom, OpeningPlacement } from './scene';

export interface ArchWall {
  /** World-px endpoints of ONE extracted face stroke — never merged with its pair. */
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface ArchRoom {
  id: string;
  /** Non-empty display label, or null when the room has no valid label. */
  label: string | null;
  /** Closed boundary polygon in world px (first point NOT auto-repeated here). */
  points: Array<[number, number]>;
  /** True only for a wall-proven architectural room (validation_status CONFIRMED).
   * A furniture-hull UNCERTAIN fallback is false and MUST be drawn distinctly — never
   * as a confirmed architectural room. */
  confirmed: boolean;
  /** Label anchor (polygon vertex average) in world px, or null when no label. */
  labelAt: [number, number] | null;
}

export interface ArchOpening {
  id: string;
  kind: 'door' | 'window';
  /** World-px centre (ON the supporting wall when verified; authored position when not). */
  cx: number;
  cy: number;
  w: number;
  h: number;
  rotation: number;
  /** True when the opening was confidently projected onto its real supporting wall.
   * False = authored position, needs review (rendered distinctly). */
  verified: boolean;
}

export interface ArchitecturalView {
  /** False when there is no architectural geometry to show (honest empty state). */
  available: boolean;
  walls: ArchWall[];
  rooms: ArchRoom[];
  openings: ArchOpening[];
}

const EMPTY: ArchitecturalView = { available: false, walls: [], rooms: [], openings: [] };

function _num(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** A room is a CONFIRMED architectural room only when its proven state says so. */
function _confirmed(room: SceneRoom): boolean {
  const status = String(room.validation_status ?? '').toUpperCase();
  const src = String(room.geometry_source ?? '');
  return status === 'CONFIRMED' && src.startsWith('architectural');
}

function _roomLabel(room: SceneRoom): string | null {
  const raw = (room.label ?? '').trim();
  return raw.length > 0 ? raw : null;
}

function _labelAnchor(points: Array<[number, number]>): [number, number] | null {
  if (points.length === 0) return null;
  let sx = 0;
  let sy = 0;
  for (const [x, y] of points) {
    sx += x;
    sy += y;
  }
  return [sx / points.length, sy / points.length];
}

function _wall(seg: unknown): ArchWall | null {
  if (!Array.isArray(seg) || seg.length < 4) return null;
  const x1 = _num(seg[0]);
  const y1 = _num(seg[1]);
  const x2 = _num(seg[2]);
  const y2 = _num(seg[3]);
  if (x1 === null || y1 === null || x2 === null || y2 === null) return null;
  // Drop only a degenerate zero-length segment; never merge or snap real strokes.
  if (x1 === x2 && y1 === y2) return null;
  return { x1, y1, x2, y2 };
}

function _boundary(room: SceneRoom): Array<[number, number]> {
  const poly = room.boundary;
  if (!Array.isArray(poly) || poly.length < 3) return [];
  const out: Array<[number, number]> = [];
  for (const p of poly) {
    const x = _num(p?.[0]);
    const y = _num(p?.[1]);
    if (x !== null && y !== null) out.push([x, y]);
  }
  // A backend boundary repeats the first vertex to close the ring; drop that duplicate
  // tail so the renderer's `closed` flag draws it once (no fabricated/omitted edge).
  if (out.length >= 2) {
    const [fx, fy] = out[0];
    const [lx, ly] = out[out.length - 1];
    if (fx === lx && fy === ly) out.pop();
  }
  return out;
}

function _opening(p: OpeningPlacement): ArchOpening | null {
  const cx = _num(p.cx);
  const cy = _num(p.cy);
  const w = _num(p.w);
  const h = _num(p.h);
  if (cx === null || cy === null || w === null || h === null) return null;
  const kind = p.kind === 'door' ? 'door' : 'window';
  return {
    id: String(p.id ?? `${kind}-${cx}-${cy}`),
    kind,
    cx,
    cy,
    w,
    h,
    rotation: _num(p.rotation) ?? 0,
    verified: !!p.verified,
  };
}

/**
 * Build the architectural render view from a scene. Pure + deterministic.
 * Returns `available: false` (and empty arrays) when `scene` is null or carries no
 * walls, room boundaries, or openings — the caller shows an honest empty state.
 * Works with ZERO furniture: walls/rooms/openings come from the scene, never furniture.
 */
export function buildArchitecturalView(scene: Scene | null | undefined): ArchitecturalView {
  if (!scene) return EMPTY;

  const walls: ArchWall[] = [];
  for (const seg of scene.walls ?? []) {
    const w = _wall(seg);
    if (w) walls.push(w);
  }

  const rooms: ArchRoom[] = [];
  const openings: ArchOpening[] = [];
  for (const room of scene.rooms ?? []) {
    const points = _boundary(room);
    if (points.length >= 3) {
      const label = _roomLabel(room);
      rooms.push({
        id: String(room.id ?? label ?? 'room'),
        label,
        points,
        confirmed: _confirmed(room),
        labelAt: label ? _labelAnchor(points) : null,
      });
    }
    for (const p of room.opening_placements ?? []) {
      const o = _opening(p);
      if (o) openings.push(o);
    }
  }

  const available = walls.length > 0 || rooms.length > 0 || openings.length > 0;
  return { available, walls, rooms, openings };
}
