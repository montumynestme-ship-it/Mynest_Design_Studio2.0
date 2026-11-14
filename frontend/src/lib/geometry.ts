/**
 * Deterministic geometry engine (frontend mirror of the backend
 * `geometry_service.py`, PRD §20). Pure functions for real-time canvas
 * validation. All spatial units are the canvas world pixels/mm consistently.
 */

export type Point = [number, number];

export interface OrientedRect {
  cx: number;
  cy: number;
  w: number;
  h: number;
  rotation: number; // degrees
}

/** Shoelace formula. Vertices in mm → area in m². */
export function calculateRoomAreaM2(polygon: Point[]): number {
  const n = polygon.length;
  if (n < 3) return 0;
  let total = 0;
  for (let i = 0; i < n; i += 1) {
    const [x1, y1] = polygon[i];
    const [x2, y2] = polygon[(i + 1) % n];
    total += x1 * y2 - x2 * y1;
  }
  return Math.abs(total) / (2 * 1_000_000);
}

export function rectCorners(rect: OrientedRect): Point[] {
  const r = (rect.rotation * Math.PI) / 180;
  const cos = Math.cos(r);
  const sin = Math.sin(r);
  const hw = rect.w / 2;
  const hh = rect.h / 2;
  const local: Point[] = [
    [-hw, -hh],
    [hw, -hh],
    [hw, hh],
    [-hw, hh],
  ];
  return local.map(([lx, ly]) => [rect.cx + lx * cos - ly * sin, rect.cy + lx * sin + ly * cos]);
}

function project(corners: Point[], axis: Point): [number, number] {
  const dots = corners.map(([x, y]) => x * axis[0] + y * axis[1]);
  return [Math.min(...dots), Math.max(...dots)];
}

/** Separating Axis Theorem overlap test for two oriented rectangles. */
export function rectsCollide(a: OrientedRect, b: OrientedRect): boolean {
  const cornersA = rectCorners(a);
  const cornersB = rectCorners(b);
  for (const corners of [cornersA, cornersB]) {
    for (let i = 0; i < 4; i += 1) {
      const [x1, y1] = corners[i];
      const [x2, y2] = corners[(i + 1) % 4];
      const axis: Point = [-(y2 - y1), x2 - x1];
      const [aMin, aMax] = project(cornersA, axis);
      const [bMin, bMax] = project(cornersB, axis);
      if (aMax < bMin || bMax < aMin) return false; // separating axis found
    }
  }
  return true;
}

/** Ray-casting point-in-polygon test. */
export function pointInPolygon(point: Point, polygon: Point[]): boolean {
  const [x, y] = point;
  const n = polygon.length;
  let inside = false;
  let j = n - 1;
  for (let i = 0; i < n; i += 1) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
    j = i;
  }
  return inside;
}
