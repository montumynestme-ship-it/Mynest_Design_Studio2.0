/**
 * Issue 1 regression — Dining Area 2D↔AI render mismatch.
 *
 * Reproduces the confirmed failure at the logic level using the ACTUAL helper the
 * gallery uses (`pickRoomForPreview` in src/lib/generations.ts). No `page`, no server,
 * no browser, no new dependencies.
 *
 * Confirmed scenario (live plan f6b65d2b, generation a203e958, design version
 * 1831bf84): the generation's "Dining Area" image carries an IMMUTABLE room_geometry
 * snapshot containing dining-table-1787478800756 (+ doors). Scene room reconstruction
 * later changed, so the CURRENT scene room with the SAME stable id "dining-area" holds
 * only a door (the dining-table moved to a new "Kitchen & Dining Area" room). The old
 * gallery preferred the live scene room by id and showed door-only geometry beside an
 * AI render containing the table. The preview must instead reflect the generation's
 * immutable snapshot.
 */
import { test, expect } from '@playwright/test';
import { pickRoomForPreview } from '../src/lib/generations';
import type { SceneRoom } from '../src/lib/scene';

const BBOX: [number, number, number, number] = [1000, 400, 500, 500];

// CURRENT live scene (version 1831bf84): id "dining-area" is now a DOOR-ONLY fallback;
// the dining-table lives in a separate "Kitchen & Dining Area" room.
const sceneRooms: SceneRoom[] = [
  {
    id: 'dining-area',
    label: 'Dining Area',
    bbox: [700, 600, 300, 300],
    furniture: [
      { uid: 'door-1789635608770', item_id: 'door', name: 'door', cx: 1059, cy: 719, w: 80, h: 20, rotation: 0 },
    ],
  },
  {
    id: 'kitchen-dining-area',
    label: 'Kitchen & Dining Area',
    bbox: BBOX,
    furniture: [
      { uid: 'dining-table-1787478800756', item_id: 'dining-table', name: 'dining table', cx: 1210, cy: 633, w: 200, h: 120, rotation: 0 },
      { uid: 'chimney-1787478686293', item_id: 'chimney', name: 'chimney', cx: 1229, cy: 368, w: 60, h: 40, rotation: 0 },
    ],
  },
];

// The generation's IMMUTABLE room_geometry snapshot for the "Dining Area" image: it
// DOES contain the dining-table (this is what the AI image was generated from).
const diningSnapshot = {
  id: 'dining-area',
  label: 'Dining Area',
  bbox: BBOX,
  furniture: [
    { uid: 'dining-table-1787478800756', item_id: 'dining-table', cx: 1210, cy: 633, w: 200, h: 120, rotation: 0 },
    { uid: 'door-1787479359667', item_id: 'door', cx: 900, cy: 700, w: 80, h: 20, rotation: 0 },
    { uid: 'door-1789215945981', item_id: 'door', cx: 950, cy: 700, w: 80, h: 20, rotation: 0 },
    { uid: 'door-1789635571944', item_id: 'door', cx: 1000, cy: 700, w: 80, h: 20, rotation: 0 },
    { uid: 'door-1789635608770', item_id: 'door', cx: 1059, cy: 719, w: 80, h: 20, rotation: 0 },
  ],
};

test('reproduces Issue 1: preview uses the immutable snapshot (dining-table), not the door-only scene room', () => {
  const room = pickRoomForPreview(sceneRooms, diningSnapshot, 'Dining Area');
  const ids = (room?.furniture ?? []).map((f) => f.item_id);
  // The fix: the dining-table from the frozen snapshot is shown (matches the AI render).
  expect(ids).toContain('dining-table');
  expect(room?.furniture.map((f) => f.uid)).toContain('dining-table-1787478800756');
  // It must NOT have collapsed to the current door-only scene room (the old bug).
  expect(room?.furniture.length).toBe(5);
  expect(ids).not.toEqual(['door']);
});

test('snapshot is used even when the live scene no longer contains that room id', () => {
  const onlyKitchenDining = [sceneRooms[1]]; // id "dining-area" absent from the scene
  const room = pickRoomForPreview(onlyKitchenDining, diningSnapshot, 'Dining Area');
  expect(room?.furniture.map((f) => f.item_id)).toContain('dining-table');
});

test('legacy image (no room_geometry snapshot): falls back to the scene room by id/label (F-2 preserved)', () => {
  const room = pickRoomForPreview(sceneRooms, null, 'Dining Area');
  // No snapshot -> the only truth available is the scene room; it is the door-only one.
  expect(room?.id).toBe('dining-area');
  expect(room?.furniture.map((f) => f.item_id)).toEqual(['door']);
});

test('non-dining rooms are unaffected: snapshot equals the scene room, table/beds preserved', () => {
  const snap = {
    id: 'kitchen-dining-area',
    label: 'Kitchen & Dining Area',
    bbox: BBOX,
    furniture: [
      { uid: 'dining-table-1787478800756', item_id: 'dining-table', cx: 1210, cy: 633, w: 200, h: 120, rotation: 0 },
      { uid: 'chimney-1787478686293', item_id: 'chimney', cx: 1229, cy: 368, w: 60, h: 40, rotation: 0 },
    ],
  };
  const room = pickRoomForPreview(sceneRooms, snap, 'Kitchen & Dining Area');
  expect(room?.furniture.map((f) => f.item_id).sort()).toEqual(['chimney', 'dining-table']);
});
