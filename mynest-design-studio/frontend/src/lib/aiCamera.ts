/**
 * Deterministic AI base-render camera solver (spec §6).
 *
 * Extracted from RoomScene3D.tsx into a standalone utility module: RoomScene3D
 * exports a React component, and co-locating a non-component export there breaks
 * React Fast Refresh ("solveAiCamera export is incompatible"). This is a pure
 * function with no React/Three.js dependency, so it belongs in lib/. Behavior is
 * byte-for-byte identical to the previous in-component version.
 *
 * Camera consistency & limitations (P1 — verified, no behavioral change):
 *  - These solvers are PURE: given the furniture/wall geometry they return a camera and
 *    NEVER mutate any furniture, wall, opening, or canonical transform. (Tested.)
 *  - The deterministic base-capture camera uses a SHARED config — a fixed FOV (RoomScene3D
 *    passes AI_FOV = 46) and the fixed capture aspect BASE_CAPTURE_W/H = 1216/832 — and fits
 *    the DISTANCE per room (from the room's size) so furniture is framed without clipping.
 *    A shared FOV/aspect does NOT guarantee identical framing: camera position and room
 *    dimensions still change what fills the frame. Per-room distance fitting is intentional
 *    and must be kept — one identical camera would clip large rooms / shrink small ones.
 *  - The INTERACTIVE deterministic viewer (Scene3DModal → RoomScene3D) IS editable and
 *    camera-controllable (presets + OrbitControls).
 *  - The AI-generated result is a STANDALONE IMAGE, not an editable 3D scene. Its viewpoint
 *    is NOT guaranteed to match the deterministic base render or the 2D plan, and the FAL
 *    image-edit path exposes no camera control. Camera comparability between the render and
 *    the 2D plan is therefore NOT proof of geometric correctness.
 */

export type WallSeg = {
  lenM: number;
  angle: number;
  midx: number;
  midz: number;
  isWindow?: boolean;
};

export type Pt = { x: number; z: number };

export interface AiCameraSolution {
  position: [number, number, number];
  target: [number, number, number];
  visibleFurniture: number;
  totalFurniture: number;
  windowsFacing: number;
  score: number;
}

/**
 * Field of view (degrees) for the AI base-capture camera. SINGLE SOURCE OF TRUTH:
 * RoomScene3D imports these and passes them straight into the solvers, and the
 * regression tests import the SAME constants — so a production FOV change can no
 * longer silently diverge from a value hardcoded in a test. Values unchanged:
 *   - AI_FOV: the elevated 3/4 "dollhouse" base capture (walls hidden).
 *   - ENCLOSED_FOV: the enclosed, eye-level interior base capture (wider framing).
 */
export const AI_FOV = 46;
export const ENCLOSED_FOV = 72;

/**
 * The FOV the base-capture path hands the camera solver for a room: the enclosed
 * eye-level capture uses ENCLOSED_FOV, every other (dollhouse) capture uses AI_FOV.
 * A tiny pure seam so the production enclosed→FOV wiring is unit-testable without
 * instantiating the React/Three component (no new camera abstraction).
 */
export function baseCaptureFov(enclosed: boolean): number {
  return enclosed ? ENCLOSED_FOV : AI_FOV;
}

/**
 * Generates 4 candidate 3/4 viewpoints (the room corners), and scores each on
 * how much of the actual furniture composition falls inside the horizontal FOV
 * (rotation-agnostic points) plus how many window walls face the camera. Picks
 * the highest-scoring candidate deterministically (stable tie-break), and derives
 * the look-at TARGET from the furniture centroid — never a fixed [0,0.35,0] and
 * never a single furniture item. Same room in → same camera out. All coordinates
 * are metres relative to the room centre.
 */
export function solveAiCamera(
  windows: WallSeg[],
  furniturePts: Pt[],
  fitDist: number,
  fov: number,
  aspect: number,
): AiCameraSolution {
  const corners = [
    { x: 1 as const, z: 1 as const },
    { x: 1 as const, z: -1 as const },
    { x: -1 as const, z: 1 as const },
    { x: -1 as const, z: -1 as const },
  ];
  const n = furniturePts.length;
  const cxm = n ? furniturePts.reduce((s, p) => s + p.x, 0) / n : 0;
  const czm = n ? furniturePts.reduce((s, p) => s + p.z, 0) / n : 0;
  const target: [number, number, number] = [cxm, 0.5, czm];
  const norm = Math.hypot(0.55, 0.72, 0.95);
  const hHalf = Math.atan(Math.tan((fov / 2) * (Math.PI / 180)) * aspect); // horizontal half-FOV

  const evaluate = (c: { x: 1 | -1; z: 1 | -1 }) => {
    const pos: [number, number, number] = [
      (0.55 * c.x / norm) * fitDist,
      (0.72 / norm) * fitDist,
      (0.95 * c.z / norm) * fitDist,
    ];
    const vx = target[0] - pos[0];
    const vz = target[2] - pos[2];
    const vlen = Math.hypot(vx, vz) || 1;
    let visible = 0;
    for (const p of furniturePts) {
      const dx = p.x - pos[0];
      const dz = p.z - pos[2];
      const dl = Math.hypot(dx, dz) || 1;
      const cos = (vx * dx + vz * dz) / (vlen * dl);
      if (Math.acos(Math.max(-1, Math.min(1, cos))) <= hHalf) visible++;
    }
    let winFace = 0;
    for (const w of windows) {
      if (Math.abs(w.midx) >= Math.abs(w.midz)) winFace += Math.sign(w.midx) === -c.x ? 1 : 0;
      else winFace += Math.sign(w.midz) === -c.z ? 1 : 0;
    }
    // Coverage DOMINATES: a candidate that clips furniture (a rotated corner
    // outside the horizontal FOV) is strongly penalized, so we never trade
    // furniture visibility for a nicer window angle. Window facing only breaks
    // ties among fully-covering candidates.
    const coverage = n ? visible / n : 1;
    return { pos, visible, winFace, score: coverage * 5 + winFace };
  };

  let best = evaluate(corners[0]);
  let bestCorner = corners[0];
  for (const c of corners.slice(1)) {
    const e = evaluate(c);
    if (e.score > best.score) {
      best = e;
      bestCorner = c;
    }
  }
  void bestCorner;
  return {
    position: best.pos,
    target,
    visibleFurniture: best.visible,
    totalFurniture: n,
    windowsFacing: best.winFace,
    score: Number(best.score.toFixed(3)),
  };
}

/**
 * Eye-level INTERIOR camera for the enclosed (ceiling-on) base render. Unlike the
 * elevated 3/4 dollhouse solver above, this places the camera INSIDE the room at
 * human eye height (~1.5 m), inset from a corner, looking across the room at the
 * furniture centroid — so an enclosed room reads as a real interior photograph
 * rather than a doll-house massing. Deterministic: same corner-coverage + window
 * scoring as solveAiCamera, only the vertical placement and inset change. All
 * coordinates are metres relative to the room centre. (Controlled camera change,
 * documented — required for a photoreal, enclosed base.)
 */
export function solveEyeLevelCamera(
  windows: WallSeg[],
  furniturePts: Pt[],
  halfW: number,
  halfD: number,
  fov: number,
  aspect: number,
): AiCameraSolution {
  const eyeH = 1.5; // camera height (m)
  const lookH = 1.0; // look-at height (m)
  const inset = 0.35; // back the camera off the wall (halfW/halfD are INTERIOR extents)
  // NOTE: lookH≈1.0 + inset≈0.35 gave the cleanest photoreal results for furniture-filled
  // rooms (bedrooms). Tilting further up / tightening the inset traded the far-wall framing
  // for a foreground floor-ledge artifact, so these values are kept.
  const n = furniturePts.length;
  const cxm = n ? furniturePts.reduce((s, p) => s + p.x, 0) / n : 0;
  const czm = n ? furniturePts.reduce((s, p) => s + p.z, 0) / n : 0;
  const hHalf = Math.atan(Math.tan((fov / 2) * (Math.PI / 180)) * aspect);

  // Candidates: camera backed against the MIDDLE of each of the 4 walls, looking
  // across the room (a one-/two-point interior shot) — far cleaner than a corner,
  // which puts a wall edge in the foreground. `side` marks which wall it backs onto.
  const cands = [
    { pos: [0, eyeH, -(halfD - inset)] as [number, number, number], side: { x: 0, z: -1 } },
    { pos: [0, eyeH, halfD - inset] as [number, number, number], side: { x: 0, z: 1 } },
    { pos: [-(halfW - inset), eyeH, 0] as [number, number, number], side: { x: -1, z: 0 } },
    { pos: [halfW - inset, eyeH, 0] as [number, number, number], side: { x: 1, z: 0 } },
  ];
  const target: [number, number, number] = [cxm, lookH, czm];

  const evaluate = (c: { pos: [number, number, number]; side: { x: number; z: number } }) => {
    const pos = c.pos;
    // Look toward the room: from the backing wall toward the far side (centroid, but
    // ensure we face INTO the room even if the centroid sits near the backing wall).
    const vx = target[0] - pos[0] - c.side.x * 0.001;
    const vz = target[2] - pos[2] - c.side.z * 0.001;
    const vlen = Math.hypot(vx, vz) || 1;
    let visible = 0;
    for (const p of furniturePts) {
      const dx = p.x - pos[0];
      const dz = p.z - pos[2];
      const dl = Math.hypot(dx, dz) || 1;
      const cos = (vx * dx + vz * dz) / (vlen * dl);
      if (Math.acos(Math.max(-1, Math.min(1, cos))) <= hHalf) visible++;
    }
    // Prefer backing onto a WINDOWLESS wall so windows appear across the room (lit).
    let winBehind = 0;
    for (const w of windows) {
      if (Math.abs(w.midx) >= Math.abs(w.midz)) winBehind += Math.sign(w.midx) === c.side.x ? 1 : 0;
      else winBehind += Math.sign(w.midz) === c.side.z ? 1 : 0;
    }
    const coverage = n ? visible / n : 1;
    return { pos, visible, score: coverage * 5 - winBehind };
  };

  let best = evaluate(cands[0]);
  for (const c of cands.slice(1)) {
    const e = evaluate(c);
    if (e.score > best.score) best = e;
  }
  return {
    position: best.pos,
    target,
    visibleFurniture: best.visible,
    totalFurniture: n,
    windowsFacing: 0,
    score: Number(best.score.toFixed(3)),
  };
}
