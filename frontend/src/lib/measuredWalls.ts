/**
 * Phase 2 — pure selector that turns the backend's derived `reconstructed_walls` centerline
 * layer into the 3D wall-shell segments `RoomScene3D` extrudes.
 *
 * It returns ONE segment per reconstructed band — i.e. the COMPLETE, de-duplicated physical
 * wall set — so no wall is ever dropped. Per band:
 *   - `MEASURED_FROM_PAIRED_FACES` → `measured: true`, `thicknessM` = the measured face-pair
 *     separation × mpp (a genuine double-line pair collapsed to one wall).
 *   - `CONFIGURED_FALLBACK` / `UNVERIFIED` → `measured: false`, `thicknessM` = the configured
 *     fallback (≈10 px) × mpp. A single-face band's centerline IS its face, so rendering it
 *     is equivalent to the face stroke — never a fabricated or doubled wall.
 * The `measured` flag keeps fallback thickness clearly distinguished from a real measurement
 * (callers must never label a fallback dimension as measured). Pure + deterministic; it never
 * moves, resizes, merges, or invents geometry — it only reclassifies existing centerlines.
 *
 * Coordinates: the centerline `seg` is world px; this converts to the SAME room-metre frame
 * the renderer uses for `realWalls` — length/offsets × `mpp`, relative to the room centre —
 * and `thicknessM = thickness_px × mpp`. No separate scale factor is introduced.
 */
import type { ReconstructedWall } from './scene';

export interface RoomFrame {
  /** Room bbox (world px) and centre (world px). */
  bx: number;
  by: number;
  bw: number;
  bh: number;
  cx: number;
  cy: number;
}

export interface ShellWall {
  lenM: number;
  angle: number;
  midx: number;
  midz: number;
  /** Per-wall thickness in metres. Measured face-pair separation when `measured`, else the
   * configured fallback. The renderer uses this instead of its constant WALL_THICKNESS. */
  thicknessM: number;
  /** True ONLY for a high-confidence `MEASURED_FROM_PAIRED_FACES` band — never for a
   * configured-fallback / unverified band. Lets callers/diagnostics distinguish a real
   * measurement from a fallback dimension (never mislabel fallback as measured). */
  measured: boolean;
}

const MIN_LEN_M = 0.15; // same floor the renderer uses for realWalls/boundaryWalls
const MIN_THICK_M = 0.02; // never a zero-depth box

/**
 * Select + convert EVERY reconstructed centerline band whose midpoint lies in the room's
 * padded box (the SAME `pad = max(bw,bh)*0.35` the renderer's realWalls uses) into room-metre
 * shell segments. Returns the complete wall set (measured + fallback), one segment per band,
 * so the shell is never missing a wall. A band without a usable segment is skipped.
 */
export function selectReconstructedShell(
  reconstructed: ReconstructedWall[] | undefined | null,
  room: RoomFrame,
  mpp: number,
): ShellWall[] {
  if (!reconstructed || reconstructed.length === 0 || !(mpp > 0)) return [];
  const { bx, by, bw, bh, cx, cy } = room;
  const pad = Math.max(bw, bh) * 0.35;
  const inBox = (x: number, y: number) =>
    x >= bx - pad && x <= bx + bw + pad && y >= by - pad && y <= by + bh + pad;

  const out: ShellWall[] = [];
  for (const w of reconstructed) {
    const seg = w.seg;
    if (!Array.isArray(seg) || seg.length < 4) continue;
    const [x1, y1, x2, y2] = seg.map(Number) as [number, number, number, number];
    if (![x1, y1, x2, y2].every((n) => Number.isFinite(n))) continue;
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    if (!inBox(mx, my)) continue;
    const lenM = Math.hypot(x2 - x1, y2 - y1) * mpp;
    if (!(lenM > MIN_LEN_M)) continue;
    const measured = w.thickness_source === 'MEASURED_FROM_PAIRED_FACES';
    const thicknessM = Math.max(MIN_THICK_M, (Number(w.thickness_px) || 0) * mpp);
    out.push({
      lenM,
      angle: Math.atan2(y2 - y1, x2 - x1),
      midx: (mx - cx) * mpp,
      midz: (my - cy) * mpp,
      thicknessM,
      measured,
    });
  }
  return out;
}
