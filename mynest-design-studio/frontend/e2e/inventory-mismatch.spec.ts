/**
 * Phase 4C Step 2K/2L regression — base inventory-mismatch badge.
 *
 * Exercises the ACTUAL helpers the gallery uses — `isBaseInventoryMismatch`,
 * `inventoryMismatchTypes`, and the extracted pure decision `buildInventoryBadge`
 * (src/lib/generations.ts) — proving the badge shows ONLY for an explicit "MISMATCH",
 * carries accurate limitation-aware wording, and never shows for MATCH / NOT_ASSESSABLE /
 * unknown / legacy responses. Pure logic: no page, no server, no new dependencies.
 *
 * DOM-render limitation: the gallery renders `buildInventoryBadge(...)` into a <span>
 * (GenerationGallery.tsx); there is no component-mount harness in this project, so the
 * actual <span> render is covered only indirectly through this pure decision function.
 */
import { test, expect } from '@playwright/test';
import {
  BASE_INVENTORY_MISMATCH_TOOLTIP,
  buildInventoryBadge,
  inventoryMismatchTypes,
  isBaseInventoryMismatch,
  type GenerationImage,
} from '../src/lib/generations';

// ── helper predicate ──
test('isBaseInventoryMismatch: MISMATCH only', () => {
  expect(isBaseInventoryMismatch('MISMATCH')).toBe(true);
  expect(isBaseInventoryMismatch('MATCH')).toBe(false);
  expect(isBaseInventoryMismatch('NOT_ASSESSABLE')).toBe(false);
  expect(isBaseInventoryMismatch(null)).toBe(false);
  expect(isBaseInventoryMismatch(undefined)).toBe(false);
  expect(isBaseInventoryMismatch('')).toBe(false);
  expect(isBaseInventoryMismatch('SOMETHING_NEW')).toBe(false);
});

test('inventoryMismatchTypes: safe for present / absent / malformed', () => {
  expect(inventoryMismatchTypes({ missing_types: ['Dining Table', 'Chimney'] })).toEqual([
    'Dining Table',
    'Chimney',
  ]);
  expect(inventoryMismatchTypes(null)).toEqual([]);
  expect(inventoryMismatchTypes(undefined)).toEqual([]);
  expect(inventoryMismatchTypes({})).toEqual([]);
  expect(inventoryMismatchTypes({ missing_types: 'Dining Table' })).toEqual([]);
  expect(inventoryMismatchTypes({ missing_types: ['Dining Table', 7, null] })).toEqual([
    'Dining Table',
  ]);
});

// ── buildInventoryBadge: the pure gallery decision ──
test('MISMATCH with missing_types -> badge with item detail', () => {
  const badge = buildInventoryBadge({
    inventory_status: 'MISMATCH',
    inventory_reason: { missing_types: ['Dining Table'] },
  });
  expect(badge).not.toBeNull();
  expect(badge!.label).toBe('Base inventory mismatch: Dining Table');
  expect(badge!.tone).toBe('warn');
});

test('MISMATCH without missing_types -> bare badge', () => {
  const badge = buildInventoryBadge({ inventory_status: 'MISMATCH', inventory_reason: null });
  expect(badge!.label).toBe('Base inventory mismatch');
});

test('MATCH / NOT_ASSESSABLE / unknown -> no badge', () => {
  expect(buildInventoryBadge({ inventory_status: 'MATCH', inventory_reason: null })).toBeNull();
  expect(buildInventoryBadge({ inventory_status: 'NOT_ASSESSABLE', inventory_reason: null })).toBeNull();
  expect(buildInventoryBadge({ inventory_status: 'WAT', inventory_reason: null })).toBeNull();
});

test('legacy response (no inventory fields) / null image -> no badge', () => {
  expect(buildInventoryBadge({ inventory_status: undefined, inventory_reason: undefined })).toBeNull();
  expect(buildInventoryBadge({} as GenerationImage)).toBeNull();
  expect(buildInventoryBadge(null)).toBeNull();
  expect(buildInventoryBadge(undefined)).toBeNull();
});

test('tooltip states the diagnostic does NOT verify the AI image furniture', () => {
  const badge = buildInventoryBadge({ inventory_status: 'MISMATCH', inventory_reason: {} });
  expect(badge!.title).toBe(BASE_INVENTORY_MISMATCH_TOOLTIP);
  expect(badge!.title).toContain('does not verify what furniture is actually visible');
  expect(badge!.title).toContain('base-selection limitation only');
});

// ── backend/frontend contract: fields named as the backend serializes them ──
test('contract: badge reads the backend response field names', () => {
  // Shape mirrors backend GenerationImageResponse (snake_case inventory_status /
  // inventory_reason.missing_types). A field rename on either side breaks this.
  const apiImage = {
    id: 'g1',
    url: '/x',
    design_index: 1,
    total_designs: 1,
    inventory_status: 'MISMATCH',
    inventory_reason: { missing_types: ['Dining Table'], base_room_id: 'dining-area' },
  } as unknown as GenerationImage;
  const badge = buildInventoryBadge(apiImage);
  expect(badge!.label).toBe('Base inventory mismatch: Dining Table');
});
