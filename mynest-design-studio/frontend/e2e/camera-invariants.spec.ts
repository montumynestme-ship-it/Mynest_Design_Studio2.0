/**
 * P1 — Camera consistency invariants (deterministic 3D capture camera).
 *
 * Locks the EXISTING behavior (no camera redesign): the base-capture camera solvers are
 * pure and deterministic, use a shared FOV/aspect (the capture aspect is the fixed
 * BASE_CAPTURE_W/H = 1216/832; RoomScene3D passes AI_FOV = 46), and fit DISTANCE per room
 * so larger rooms are framed from farther away (never one identical camera for all rooms).
 *
 * Limitations (NOT asserted here): a shared FOV/aspect does NOT guarantee identical framing
 * (position + room size still matter); furniture-coverage does NOT prove every door/window
 * is visible; the AI OUTPUT is a standalone image whose viewpoint is not controllable. The
 * solvers never touch canonical furniture/wall data — proven below.
 */
import { test, expect } from '@playwright/test';
import {
  solveAiCamera,
  solveEyeLevelCamera,
  AI_FOV,
  ENCLOSED_FOV,
  baseCaptureFov,
  type Pt,
  type WallSeg,
} from '../src/lib/aiCamera';
import { BASE_CAPTURE_W, BASE_CAPTURE_H } from '../src/lib/scene';

// AI_FOV is now imported from the SAME production module RoomScene3D uses (no local
// duplicate), so a production FOV change can no longer silently diverge from the tests.
const ASPECT = BASE_CAPTURE_W / BASE_CAPTURE_H;

const furn = (): Pt[] => [
  { x: 2, z: 4 }, { x: 4, z: 6 }, { x: 3, z: 2 },
];
const wins = (): WallSeg[] => [{ midx: -3, midz: 0 } as WallSeg];

test('shared capture aspect is a fixed constant (1216 / 832)', () => {
  expect(BASE_CAPTURE_W).toBe(1216);
  expect(BASE_CAPTURE_H).toBe(832);
});

test('production AI base-capture FOV is the documented contract (46 / 72)', () => {
  // Value-pins the PRODUCTION constants (imported from lib/aiCamera, the same module
  // RoomScene3D consumes). An intentional change must consciously update this test;
  // an unintended change is caught here instead of diverging unnoticed.
  expect(AI_FOV).toBe(46);
  expect(ENCLOSED_FOV).toBe(72);
});

test('base-capture path feeds the intended production FOV into the solver (enclosed → eye-level)', () => {
  // baseCaptureFov is the exact seam RoomScene3D uses to choose the FOV it passes to
  // the solver: enclosed rooms get ENCLOSED_FOV, every other capture gets AI_FOV.
  expect(baseCaptureFov(false)).toBe(AI_FOV);
  expect(baseCaptureFov(true)).toBe(ENCLOSED_FOV);
});

test('solveAiCamera does NOT mutate its furniture/window inputs (pure)', () => {
  const f = furn();
  const w = wins();
  const fBefore = JSON.stringify(f);
  const wBefore = JSON.stringify(w);
  solveAiCamera(w, f, 6, AI_FOV, ASPECT);
  expect(JSON.stringify(f)).toBe(fBefore);
  expect(JSON.stringify(w)).toBe(wBefore);
});

test('solveAiCamera is deterministic for identical inputs (repeatable preset)', () => {
  const a = solveAiCamera(wins(), furn(), 6, AI_FOV, ASPECT);
  const b = solveAiCamera(wins(), furn(), 6, AI_FOV, ASPECT);
  expect(a).toEqual(b);
});

test('target is the furniture centroid at fixed height 0.5', () => {
  // centroid of (2,4),(4,6),(3,2) = (3,4)
  const sol = solveAiCamera(wins(), furn(), 6, AI_FOV, ASPECT);
  expect(sol.target[0]).toBeCloseTo(3, 6);
  expect(sol.target[1]).toBeCloseTo(0.5, 6);
  expect(sol.target[2]).toBeCloseTo(4, 6);
});

test('camera DISTANCE is fitted per room — larger fitDist frames from farther away', () => {
  const near = solveAiCamera(wins(), furn(), 5, AI_FOV, ASPECT);
  const far = solveAiCamera(wins(), furn(), 10, AI_FOV, ASPECT);
  const mag = (p: [number, number, number]) => Math.hypot(p[0], p[1], p[2]);
  // position scales with fitDist (pos = coeff * fitDist), so the 10m fit is farther.
  expect(mag(far.position)).toBeGreaterThan(mag(near.position));
  // and it is NOT one identical camera across sizes
  expect(far.position).not.toEqual(near.position);
});

test('solveEyeLevelCamera is pure + deterministic', () => {
  const f = furn();
  const w = wins();
  const before = JSON.stringify([f, w]);
  const a = solveEyeLevelCamera(w, f, 4, 4, ENCLOSED_FOV, ASPECT);
  const b = solveEyeLevelCamera(wins(), furn(), 4, 4, ENCLOSED_FOV, ASPECT);
  expect(JSON.stringify([f, w])).toBe(before); // no mutation
  expect(a).toEqual(b);
});
