/**
 * Door/Window MERGE (union, dedup) regression — deterministic, no pixel assertions.
 *
 * The backend attaches globally-deduped room.supplemental_doors / supplemental_windows
 * (PDF-detected openings the editor did NOT place). The renderer draws editor
 * openings PLUS these supplements, so no real opening is missing. Furniture is
 * untouched. Requires backend :8001.
 */
import { test, expect, request as pwRequest } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8001';
const FID = process.env.FLOOR_PLAN_ID || 'f6b65d2b-4f96-4931-9f08-67dbd09776f6';
const ART = path.join(process.cwd(), 'tests', 'artifacts', 'furniture-detection');

async function getJson(url: string) {
  const ctx = await pwRequest.newContext();
  const res = await ctx.get(url);
  expect(res.ok(), `GET ${url} -> ${res.status()}`).toBeTruthy();
  const body = await res.json();
  await ctx.dispose();
  return body;
}

test('real plan: merged (editor ∪ PDF-supplemental) covers every PDF-detected opening', async () => {
  const scene = await getJson(`${BACKEND}/api/floor-plans/${FID}/scene`);
  let editorDoors = 0, editorWindows = 0;
  let pdfDoors = 0, pdfWindows = 0;
  let suppDoors = 0, suppWindows = 0;

  for (const r of scene.rooms || []) {
    const furn = r.furniture || [];
    editorWindows += furn.filter((f: any) => String(f.item_id).includes('window')).length;
    editorDoors += furn.filter((f: any) => { const id = String(f.item_id); return id.includes('door') && !id.includes('window'); }).length;
    pdfDoors += (r.doors || []).length;
    pdfWindows += (r.windows || []).length;
    suppDoors += (r.supplemental_doors || []).length;
    suppWindows += (r.supplemental_windows || []).length;
  }

  const renderedDoors = editorDoors + suppDoors;
  const renderedWindows = editorWindows + suppWindows;

  // Editor placements retained + every PDF-detected opening covered, no over-count.
  expect(renderedDoors).toBeGreaterThanOrEqual(editorDoors);
  expect(renderedWindows).toBeGreaterThanOrEqual(editorWindows);
  expect(renderedDoors).toBeGreaterThanOrEqual(pdfDoors);
  expect(renderedWindows).toBeGreaterThanOrEqual(pdfWindows);
  expect(renderedDoors).toBeLessThanOrEqual(editorDoors + pdfDoors);
  expect(renderedWindows).toBeLessThanOrEqual(editorWindows + pdfWindows);

  // Supplements carry real geometry (renderable), never empty placeholders.
  for (const r of scene.rooms || []) {
    for (const o of [...(r.supplemental_doors || []), ...(r.supplemental_windows || [])]) {
      expect(Number(o.w)).toBeGreaterThan(0);
      expect(Number(o.h)).toBeGreaterThan(0);
      expect(Number.isFinite(Number(o.cx)) && Number.isFinite(Number(o.cy))).toBeTruthy();
    }
  }

  // This plan specifically: editor 7 doors + 4 windows; PDF 8 doors + 5 windows;
  // exactly 1 door + 1 window supplemented → 8 doors + 5 windows rendered.
  expect({ editorDoors, editorWindows, suppDoors, suppWindows, renderedDoors, renderedWindows })
    .toEqual({ editorDoors: 7, editorWindows: 4, suppDoors: 1, suppWindows: 1, renderedDoors: 8, renderedWindows: 5 });

  fs.mkdirSync(ART, { recursive: true });
  fs.writeFileSync(path.join(ART, 'door-window-merge.json'), JSON.stringify({
    floor_plan_id: FID,
    editor: { doors: editorDoors, windows: editorWindows },
    pdf_detected: { doors: pdfDoors, windows: pdfWindows },
    supplemental_added: { doors: suppDoors, windows: suppWindows },
    rendered_after_merge: { doors: renderedDoors, windows: renderedWindows },
  }, null, 2));
});
