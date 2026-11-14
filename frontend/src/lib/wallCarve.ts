/**
 * Phase A — deterministic REAL wall openings for the 3D shell.
 *
 * Pure geometry: given one wall segment (room-metre frame) and the VERIFIED openings
 * on the plan, subtract each opening's span from the wall and return the solid runs
 * (jambs), the header above each opening (so the wall above a door lintel is preserved),
 * and the sill below each window. The renderer turns these into boxes.
 *
 * This NEVER changes any canonical geometry, furniture, or opening data — it only
 * decides how the existing wall shell is split for rendering. Unverified openings are
 * NOT passed here (the renderer keeps a solid wall for them), so an uncertain opening
 * can never carve a hole. Offsets are measured ALONG the wall axis relative to the
 * segment centre; the renderer places each box at
 * `(midx + offset·cosθ, y, midz + offset·sinθ)` with the wall's own rotation.
 */

export interface CarveSeg {
  /** Segment length in metres (before the corner-fudge extension). */
  lenM: number;
  /** Wall direction angle in radians (atan2(dy, dx) in plan coords). */
  angle: number;
  /** Segment centre in the room-metre frame. */
  midx: number;
  midz: number;
}

export interface CarveOpening {
  /** Opening centre in the room-metre frame. */
  mx: number;
  mz: number;
  /** Opening orientation in radians. */
  angle: number;
  /** Half the opening span ALONG its wall, in metres. */
  half: number;
  /** Opening head height in metres (door lintel, or window sill+glass top). */
  head: number;
  /** Sill height in metres (windows); 0 for doors. */
  sill: number;
}

export interface CarveOpts {
  wallHeight: number;
  wallThickness: number;
  /** Max perpendicular gap (m) for an opening to count as ON this segment. */
  perpTol: number;
  /** Max angle disagreement (radians) between opening and wall. */
  angleTol: number;
}

export interface WallRun {
  offset: number;
  length: number;
}
export interface WallHeader {
  offset: number;
  length: number;
  yCenter: number;
  height: number;
}
export interface WallSill {
  offset: number;
  length: number;
  height: number;
}
export interface CarveResult {
  /** Full-height solid wall runs (jambs + unopened spans). */
  solids: WallRun[];
  /** Wall above each opening (head → ceiling). */
  headers: WallHeader[];
  /** Wall below each window (floor → sill). */
  sills: WallSill[];
}

const EPS = 0.02; // m — ignore sub-2cm slivers

/** Subtract the verified openings on `seg` from the wall, returning the solid runs,
 * headers and sills (all in the segment-local along-axis frame). Pure + deterministic. */
export function carveWallSegment(
  seg: CarveSeg,
  openings: CarveOpening[],
  opts: CarveOpts,
): CarveResult {
  const L = seg.lenM + opts.wallThickness; // full drawn length (keeps the corner fudge)
  const halfL = L / 2;
  const dirx = Math.cos(seg.angle);
  const dirz = Math.sin(seg.angle);

  // Openings that actually lie on THIS segment (angle + perpendicular + span overlap).
  const ivs: { a: number; b: number; head: number; sill: number }[] = [];
  for (const o of openings) {
    let da = Math.abs((o.angle - seg.angle) % Math.PI);
    da = Math.min(da, Math.PI - da);
    if (da > opts.angleTol) continue;
    const relx = o.mx - seg.midx;
    const relz = o.mz - seg.midz;
    const s = relx * dirx + relz * dirz; // along-axis offset from the segment centre
    const perp = Math.abs(-relx * dirz + relz * dirx);
    if (perp > opts.perpTol) continue;
    const a = s - o.half;
    const b = s + o.half;
    if (b <= -halfL || a >= halfL) continue; // opening projects off this segment
    ivs.push({ a: Math.max(a, -halfL), b: Math.min(b, halfL), head: o.head, sill: o.sill });
  }

  if (ivs.length === 0) {
    return { solids: [{ offset: 0, length: L }], headers: [], sills: [] };
  }

  // Merge overlapping carve spans so jambs never get negative length.
  const sorted = [...ivs].sort((p, q) => p.a - q.a);
  const merged: { a: number; b: number }[] = [];
  for (const iv of sorted) {
    const last = merged[merged.length - 1];
    if (last && iv.a <= last.b) last.b = Math.max(last.b, iv.b);
    else merged.push({ a: iv.a, b: iv.b });
  }

  const solids: WallRun[] = [];
  let cursor = -halfL;
  for (const m of merged) {
    if (m.a > cursor + EPS) {
      solids.push({ offset: (cursor + m.a) / 2, length: m.a - cursor });
    }
    cursor = Math.max(cursor, m.b);
  }
  if (cursor < halfL - EPS) {
    solids.push({ offset: (cursor + halfL) / 2, length: halfL - cursor });
  }

  const headers: WallHeader[] = [];
  const sills: WallSill[] = [];
  for (const iv of ivs) {
    const length = iv.b - iv.a;
    if (length <= EPS) continue;
    const offset = (iv.a + iv.b) / 2;
    const headH = opts.wallHeight - iv.head;
    if (headH > EPS) {
      headers.push({ offset, length, yCenter: (iv.head + opts.wallHeight) / 2, height: headH });
    }
    if (iv.sill > EPS) {
      sills.push({ offset, length, height: iv.sill });
    }
  }

  return { solids, headers, sills };
}
