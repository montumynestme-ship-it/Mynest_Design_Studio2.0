/**
 * Window authoritative wall-placement regression — deterministic, no pixel checks.
 *
 * The backend attaches room.opening_placements: each opening PROJECTED onto its real
 * supporting wall (structured geometry), NOT the furniture-bbox room boundary. The
 * renderer consumes these on-wall positions for windows. This verifies windows are
 * placed on their authoritative wall (perpendicular drift removed) — e.g. Bedroom 1's
 * left-wall window lands on wall_086 at the same height, not on the furniture bbox.
 * Requires backend :8001.
 */
import { test, expect, request as pwRequest } from '@playwright/test';

const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8001';
const FID = process.env.FLOOR_PLAN_ID || 'f6b65d2b-4f96-4931-9f08-67dbd09776f6';

async function getScene() {
  const ctx = await pwRequest.newContext();
  const res = await ctx.get(`${BACKEND}/api/floor-plans/${FID}/scene`);
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  await ctx.dispose();
  return body;
}

test('every window has an opening_placement; verified ones carry a real supporting wall', async () => {
  const scene = await getScene();
  let windows = 0;
  let verified = 0;
  for (const r of scene.rooms || []) {
    const winFurn = (r.furniture || []).filter((f: any) => String(f.item_id).includes('window')).length;
    const suppWin = (r.supplemental_windows || []).length;
    const placements = (r.opening_placements || []).filter((p: any) => p.kind === 'window');
    // every editor + supplemental window is represented by a placement
    expect(placements.length).toBe(winFurn + suppWin);
    for (const p of placements) {
      windows++;
      if (p.verified) {
        verified++;
        expect(p.wall_id, 'verified window must name its supporting wall').toBeTruthy();
        expect(p.wall_relative.perp_removed_px).toBeLessThanOrEqual(60); // capped
        expect(p.wall_relative.normalized).toBeGreaterThanOrEqual(0);
        expect(p.wall_relative.normalized).toBeLessThanOrEqual(1);
      }
    }
  }
  expect(windows).toBeGreaterThan(0);
  expect(verified).toBeGreaterThan(0);
});

test('Bedroom 1 window is placed on its real LEFT wall (not the furniture bbox)', async () => {
  const scene = await getScene();
  const br1 = (scene.rooms || []).find((r: any) => String(r.label).includes('Bedroom 1'));
  expect(br1).toBeTruthy();
  const win = (br1.opening_placements || []).find((p: any) => p.kind === 'window');
  expect(win, 'Bedroom 1 window placement present').toBeTruthy();
  expect(win.verified).toBe(true);
  expect(win.wall_id).toBeTruthy(); // real structured wall (e.g. wall_086)
  // furniture-bbox left edge (the OLD wrong snap target) — the window must NOT be there
  const bx = Math.min(...(br1.boundary || []).map((p: number[]) => p[0]));
  expect(Math.abs(win.cx - bx)).toBeGreaterThan(5); // on the real wall, not the bbox edge
  // along-wall height preserved (~window's authored cy)
  const rawWin = (br1.furniture || []).find((f: any) => String(f.item_id).includes('window'));
  expect(Math.abs(win.cy - Number(rawWin.cy))).toBeLessThan(30);
});
