/**
 * F-2 regression — Gallery Provenance stable room-id matching.
 *
 * Exercises the ACTUAL matching helper used by GenerationGallery
 * (`matchSceneRoom` in src/lib/scene.ts) — not a re-implementation — to prove the
 * selected 2D room corresponds to the generation snapshot's room identity, not a
 * coincidentally same-labelled room.
 *
 * Pure logic: no `page`, no dev server, no browser. Runs with the existing
 * Playwright runner (`playwright test e2e/room-match.spec.ts`).
 */
import { test, expect } from '@playwright/test';
import { matchSceneRoom, type SceneRoom } from '../src/lib/scene';

function room(id: string, label: string): SceneRoom {
  return { id, label, bbox: [0, 0, 1, 1], furniture: [] };
}

test('A — duplicate/normalization-equivalent labels: stable id selects the right room', () => {
  // Two rooms whose labels normalize to the same string but have distinct ids.
  const rooms = [room('room-a', 'Bedroom 3'), room('room-b', 'bedroom 3 ')];
  // The generation snapshot points at the SECOND room by id.
  const selected = matchSceneRoom(rooms, 'room-b', 'Bedroom 3');
  expect(selected?.id).toBe('room-b');
});

test('B — renamed label: same stable id, different label still matches by id', () => {
  const rooms = [room('room-x', 'Master Bedroom')];
  // Snapshot kept id room-x but the label was later renamed to "Primary Suite".
  const selected = matchSceneRoom(rooms, 'room-x', 'Primary Suite');
  expect(selected?.id).toBe('room-x');
});

test('C — legacy generation with no snapshot room id: normalized-label match preserved', () => {
  const rooms = [room('room-k', 'Kitchen')];
  // No stable id (legacy record) -> fall back to normalized-label match.
  const selected = matchSceneRoom(rooms, undefined, 'kitchen');
  expect(selected?.id).toBe('room-k');
  // null id behaves the same as undefined (legacy path).
  expect(matchSceneRoom(rooms, null, '  KITCHEN ')?.id).toBe('room-k');
});

test('D — stable id present but not in scene: does NOT fall back to a same-label room', () => {
  // Scene has a room whose label matches the requested label, but the snapshot's
  // stable id does not exist in the scene. The label-matching room must NOT be chosen.
  const rooms = [room('room-real', 'Living Room')];
  const selected = matchSceneRoom(rooms, 'room-ghost', 'Living Room');
  expect(selected).toBeUndefined();
});
