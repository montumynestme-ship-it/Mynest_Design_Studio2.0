/**
 * AIR-11 (local, offline part): every canonical furniture type in the frozen v31 design
 * must have an EXPLICIT 3D model (a curated SPECS entry), not fall through to the generic
 * brown-box fallback. A type with no 3D representation would render as an unlabelled box
 * and let the AI stage invent décor. This does NOT assess base-render visual richness
 * (that needs a real render artifact) — it locks the deterministic 2D→3D model mapping.
 *
 * Source of truth = the committed frozen fixture backend/tests/fixtures/canonical_v31_1831bf84.json.
 */
import { readFileSync } from 'fs';
import { join } from 'path';
import { test, expect } from '@playwright/test';
import { furniture3d, hasExplicit3DModel } from '../src/lib/furniture3d';

// Playwright runs from the frontend project root; the committed fixture lives one level
// up under backend/. (ESM test context — __dirname is not available, so use cwd.)
const FIXTURE = join(
  process.cwd(),
  '..',
  'backend',
  'tests',
  'fixtures',
  'canonical_v31_1831bf84.json',
);

function v31ItemIds(): string[] {
  const cj = JSON.parse(readFileSync(FIXTURE, 'utf-8')) as { furniture: { item_id: string }[] };
  return Array.from(new Set(cj.furniture.map((f) => String(f.item_id))));
}

test('frozen v31 fixture loads and has the expected canonical types', () => {
  const ids = v31ItemIds();
  // 11 distinct types (22 furniture + openings): bed, side-table, wardrobe, dressing-table,
  // console, lounger-sofa, kitchen-base, chimney, dining-table, door, window.
  expect(ids.length).toBe(11);
  for (const t of ['bed', 'wardrobe', 'side-table', 'dining-table', 'kitchen-base', 'door', 'window']) {
    expect(ids).toContain(t);
  }
});

test('every v31 canonical furniture type has an EXPLICIT 3D model (no generic fallback)', () => {
  const unmapped = v31ItemIds().filter((id) => !hasExplicit3DModel(id));
  expect(unmapped, `canonical types with no explicit 3D model: ${unmapped.join(', ')}`).toEqual([]);
});

test('an unknown item type is detected as NOT explicitly mapped (fallback is honest)', () => {
  expect(hasExplicit3DModel('totally-unknown-item')).toBe(false);
  // furniture3d still returns a usable generic spec so rendering never crashes.
  expect(furniture3d('totally-unknown-item').kind).toBe('generic');
});
