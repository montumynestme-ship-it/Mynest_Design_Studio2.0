/**
 * Furniture Missing Items — evidence-first investigation (NO production changes).
 *
 * Deterministic stages are asserted STRICTLY from the app's own authoritative API
 * (canonical layout vs. reconstructed scene). The AI render is treated as visual
 * output only: screenshots are captured as evidence, never asserted pixel-by-pixel.
 *
 * Requires the dev servers running: frontend :5173, backend :8001.
 */
import { test, expect, request as pwRequest } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8001';
const FID = process.env.FLOOR_PLAN_ID || 'f6b65d2b-4f96-4931-9f08-67dbd09776f6';
// Playwright runs from the frontend root (config testDir ./e2e), so resolve
// artifacts against cwd (this project is ESM; __dirname is unavailable).
const ART = path.join(process.cwd(), 'tests', 'artifacts', 'furniture-missing');

type Item = { uid: string; item_id: string };
const count = (xs: string[]) =>
  xs.reduce<Record<string, number>>((m, x) => ((m[x] = (m[x] || 0) + 1), m), {});

async function getJson(url: string) {
  const ctx = await pwRequest.newContext();
  const res = await ctx.get(url);
  expect(res.ok(), `GET ${url} -> ${res.status()}`).toBeTruthy();
  const body = await res.json();
  await ctx.dispose();
  return body;
}

test.beforeAll(() => {
  fs.mkdirSync(ART, { recursive: true });
});

test('deterministic: canonical layout inventory == 3D scene inventory (strict)', async () => {
  // Authoritative canonical furniture (the 2D editor writes this via save_layout).
  const layout = await getJson(`${BACKEND}/api/floor-plans/${FID}/layout`);
  const canonical: Item[] = (layout.items || []).map((i: any) => ({ uid: String(i.uid), item_id: String(i.item_id) }));

  // Deterministic reconstructed scene consumed by the 3D renderer.
  const scene = await getJson(`${BACKEND}/api/floor-plans/${FID}/scene`);
  const sceneItems: Item[] = (scene.rooms || []).flatMap((r: any) =>
    (r.furniture || []).map((f: any) => ({ uid: String(f.uid), item_id: String(f.item_id) })),
  );

  // 1. Total count preserved.
  expect(sceneItems.length, 'scene furniture count != canonical count').toBe(canonical.length);

  // 2. Every canonical uid present exactly once (none dropped/duplicated), none extra.
  const canonUids = canonical.map((i) => i.uid);
  const sceneUids = sceneItems.map((i) => i.uid);
  const dropped = canonUids.filter((u) => !sceneUids.includes(u));
  const extra = sceneUids.filter((u) => !canonUids.includes(u));
  const dup = Object.entries(count(sceneUids)).filter(([, n]) => n > 1).map(([u]) => u);
  expect(dropped, `canonical uids missing from scene: ${dropped}`).toEqual([]);
  expect(extra, `scene uids not in canonical: ${extra}`).toEqual([]);
  expect(dup, `uids duplicated across rooms: ${dup}`).toEqual([]);

  // 3. Per-type inventory identical (detects same-count-but-wrong-inventory).
  expect(count(sceneItems.map((i) => i.item_id))).toEqual(count(canonical.map((i) => i.item_id)));
});

test('deterministic: UID-level per-room assignment + base-render visibility invariants', async () => {
  const layout = await getJson(`${BACKEND}/api/floor-plans/${FID}/layout`);
  const canonUids: string[] = (layout.items || []).map((i: any) => String(i.uid));
  const scene = await getJson(`${BACKEND}/api/floor-plans/${FID}/scene`);

  // Per-room UID assignment: every canonical uid lands in EXACTLY one room, the
  // union equals canonical, and no uid is shared across rooms (mandatory UID-level).
  const seen: Record<string, number> = {};
  const invisible: string[] = [];
  for (const r of scene.rooms || []) {
    for (const f of r.furniture || []) {
      const uid = String(f.uid);
      seen[uid] = (seen[uid] || 0) + 1;
      // Base-render visibility invariant: an item with non-positive/NaN size or
      // NaN center would mount but be invisible. Assert none exist.
      const w = Number(f.w), h = Number(f.h), cx = Number(f.cx), cy = Number(f.cy);
      if (!(w > 0) || !(h > 0) || !Number.isFinite(cx) || !Number.isFinite(cy)) invisible.push(uid);
    }
  }
  const assignedUids = Object.keys(seen);
  const sharedAcrossRooms = Object.entries(seen).filter(([, n]) => n > 1).map(([u]) => u);
  const unassigned = canonUids.filter((u) => !assignedUids.includes(u));

  expect(unassigned, `canonical uids not assigned to any room: ${unassigned}`).toEqual([]);
  expect(sharedAcrossRooms, `uids in more than one room: ${sharedAcrossRooms}`).toEqual([]);
  expect(new Set(assignedUids), 'assigned uid set != canonical uid set').toEqual(new Set(canonUids));
  // Base-render inventory == scene inventory: every assigned item is renderable.
  expect(invisible, `items with invisible-causing geometry (base-render loss): ${invisible}`).toEqual([]);
  expect(assignedUids.length, 'base-render renderable count != canonical count').toBe(canonUids.length);
});

test('evidence: capture AI renders per room (visual only, no pixel assertions)', async ({ page }) => {
  const gens = await getJson(`${BACKEND}/api/floor-plans/${FID}/generations`);
  const list = Array.isArray(gens) ? gens : gens.items || [];
  const latest = list[0];
  test.skip(!latest, 'no generation available to evidence');

  const roomsEvidence: any[] = [];
  for (const img of latest.images || []) {
    const slug = String(img.label || `room-${img.design_index}`).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    // The image URL is relative (/api/generations/.../images/N); resolve to backend.
    const url = img.url?.startsWith('http') ? img.url : `${BACKEND}${img.url}`;
    await page.goto(url);
    await page.screenshot({ path: path.join(ART, `${slug}-ai.png`), fullPage: true });
    roomsEvidence.push({
      room: img.label,
      ai_render_screenshot: `${slug}-ai.png`,
      // Truthful, separate signal from the backend (never deterministic fidelity):
      ai_geometry_faithful: img.geometry_faithful ?? null,
      deterministic_overall_fidelity: img.fidelity?.overall_fidelity ?? null,
    });
  }
  fs.writeFileSync(path.join(ART, 'ai-render-evidence.json'), JSON.stringify({ floor_plan_id: FID, generation_id: latest.id, rooms: roomsEvidence }, null, 2));
  expect(roomsEvidence.length).toBeGreaterThan(0);
});

test('the machine-readable furniture comparison artifact exists', async () => {
  const p = path.join(ART, 'furniture-comparison.json');
  expect(fs.existsSync(p), `${p} missing`).toBeTruthy();
  const data = JSON.parse(fs.readFileSync(p, 'utf-8'));
  expect(data.totals.canonical).toBe(data.totals.scene); // deterministic 100%
  expect(data.totals.missing_from_3d).toEqual([]);
});
