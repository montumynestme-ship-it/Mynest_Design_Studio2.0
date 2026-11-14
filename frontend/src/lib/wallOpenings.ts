/**
 * Deterministic wall-splitting for REAL structural openings (no CSG dependency).
 *
 * Given a wall's length + height and the openings that sit on it, compute the SOLID
 * sub-pieces that remain once each opening is a genuine geometric gap — the side spans
 * either side of an opening (full height), the sill band BELOW a window, and the
 * lintel/head band ABOVE every opening. A door leaves a floor→head gap (no sill band).
 *
 * Pure + unit-tested; no Three.js here. All lengths in METRES, measured along the wall's
 * own axis from its start (0) to its end (lenM); heights from the floor (0) to heightM.
 * The caller (StructuralScene3D) places each returned piece along the wall in world space,
 * so this module never touches canonical data or coordinates — it only subdivides a span.
 */

export interface WallOpening {
  /** Along-wall centre position, metres from the wall start. */
  centerM: number;
  /** Opening width along the wall, metres. */
  widthM: number;
  kind: 'door' | 'window';
  /** Sill height (window). Ignored for a door (treated as 0 → floor-level gap). */
  sillM: number;
  /** Head/lintel height = top of the opening, metres from floor. */
  headM: number;
}

/** A solid rectangular piece of wall in wall-local coords: a span [offStartM, offEndM]
 *  along the wall and a vertical band [yBottomM, yTopM]. */
export interface WallSolid {
  offStartM: number;
  offEndM: number;
  yBottomM: number;
  yTopM: number;
}

const EPS = 1e-6;

/** Clamp a value to [lo, hi]. */
function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}

/**
 * Subdivide one wall of length `lenM` and height `heightM` around its `openings`.
 * Returns the solid pieces to render (never overlapping along a given band). An opening
 * is clipped to the wall span and to the wall height; a zero-area piece is dropped so a
 * full-width or full-height opening simply yields fewer solids (never a degenerate box).
 */
export function splitWallWithOpenings(
  lenM: number,
  heightM: number,
  openings: WallOpening[],
): WallSolid[] {
  const solids: WallSolid[] = [];
  if (lenM <= EPS || heightM <= EPS) return solids;

  // Normalise + clip openings to the wall span; drop ones fully outside or zero-width.
  const ops = openings
    .map((o) => {
      const start = clamp(o.centerM - o.widthM / 2, 0, lenM);
      const end = clamp(o.centerM + o.widthM / 2, 0, lenM);
      const head = clamp(o.headM, 0, heightM);
      const sill = o.kind === 'door' ? 0 : clamp(o.sillM, 0, head);
      return { start, end, head, sill, kind: o.kind };
    })
    .filter((o) => o.end - o.start > EPS && o.head - o.sill > EPS)
    .sort((a, b) => a.start - b.start);

  if (ops.length === 0) {
    // No (effective) opening → one solid wall.
    solids.push({ offStartM: 0, offEndM: lenM, yBottomM: 0, yTopM: heightM });
    return solids;
  }

  // FULL-HEIGHT side spans: the gaps between consecutive opening ranges (and the wall
  // ends). Overlapping openings are coalesced by walking a running cursor.
  let cursor = 0;
  let coalesceEnd = -Infinity;
  for (const o of ops) {
    const gapStart = Math.max(cursor, coalesceEnd);
    if (o.start - gapStart > EPS) {
      solids.push({ offStartM: gapStart, offEndM: o.start, yBottomM: 0, yTopM: heightM });
    }
    cursor = Math.max(cursor, o.end);
    coalesceEnd = Math.max(coalesceEnd, o.end);
  }
  if (lenM - cursor > EPS) {
    solids.push({ offStartM: cursor, offEndM: lenM, yBottomM: 0, yTopM: heightM });
  }

  // Per-opening vertical bands: a HEAD band above every opening, plus a SILL band below a
  // window. These span exactly the opening's own width so the gap is a real hole.
  for (const o of ops) {
    if (heightM - o.head > EPS) {
      solids.push({ offStartM: o.start, offEndM: o.end, yBottomM: o.head, yTopM: heightM });
    }
    if (o.kind === 'window' && o.sill > EPS) {
      solids.push({ offStartM: o.start, offEndM: o.end, yBottomM: 0, yTopM: o.sill });
    }
  }

  return solids;
}

/** Total solid face area (m²) of the returned pieces — used by tests to prove that the
 *  openings removed exactly the expected hole area (wall area − Σ opening holes). */
export function solidArea(solids: WallSolid[]): number {
  return solids.reduce(
    (a, s) => a + (s.offEndM - s.offStartM) * (s.yTopM - s.yBottomM),
    0,
  );
}
