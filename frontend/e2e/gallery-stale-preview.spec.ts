/**
 * F-4 regression — stale gallery preview on generation switch.
 *
 * Exercises the ACTUAL scene-loading logic the gallery effect runs
 * (`loadSnapshotScene` in src/lib/scene.ts) — the React effect is a thin delegator —
 * driving real async ordering with injected spies. No `page`, no dev server, no
 * browser, no new dependencies. Runs with the existing Playwright runner.
 */
import { test, expect } from '@playwright/test';
import { loadSnapshotScene, type Scene } from '../src/lib/scene';

function makeScene(): Scene {
  return { page: { width: 10, height: 10 }, walls: [], rooms: [] };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

test('generation switch: the previous scene is cleared immediately, before the new one loads', () => {
  const calls: (Scene | null)[] = [];
  const d = deferred<Scene>();
  let fetchCalled = false;
  loadSnapshotScene('plan', 'v-new', {
    setScene: (s) => calls.push(s),
    fetchScene: () => {
      fetchCalled = true;
      return d.promise; // never resolves during this assertion
    },
  });
  // Synchronous clear happened first; the new scene has NOT been applied yet.
  expect(calls).toEqual([null]);
  expect(fetchCalled).toBe(true);
});

test('out-of-order: a slower earlier request cannot overwrite the newer selection', async () => {
  const calls: (Scene | null)[] = [];
  const setScene = (s: Scene | null) => calls.push(s);
  const dOld = deferred<Scene>();
  const dNew = deferred<Scene>();
  const sceneOld = makeScene();
  const sceneNew = makeScene();

  // Effect run for the first selection, then React cleanup (selection changed)...
  const cleanupOld = loadSnapshotScene('plan', 'v-old', { setScene, fetchScene: () => dOld.promise });
  cleanupOld();
  // ...then the effect run for the new selection.
  loadSnapshotScene('plan', 'v-new', { setScene, fetchScene: () => dNew.promise });

  // The OLD request resolves LAST, but it must be ignored (its run was cleaned up).
  dNew.resolve(sceneNew);
  dOld.resolve(sceneOld);
  await tick();

  const applied = calls.filter((c): c is Scene => c !== null);
  expect(applied).toEqual([sceneNew]); // only the newer scene was applied
  expect(applied).not.toContain(sceneOld); // the slower old request never overwrote it
});

test('missing version id: scene is cleared and NO current-scene request is made', () => {
  const calls: (Scene | null)[] = [];
  let fetchCalled = false;
  let warned = false;
  loadSnapshotScene('plan', undefined, {
    setScene: (s) => calls.push(s),
    fetchScene: () => {
      fetchCalled = true;
      return deferred<Scene>().promise;
    },
    onMissingVersion: () => {
      warned = true;
    },
  });
  expect(calls).toEqual([null]); // cleared, no stale scene retained
  expect(fetchCalled).toBe(false); // no fallback to the current/editable scene
  expect(warned).toBe(true);
});

test('request failure: the previous scene does not remain visible', async () => {
  const calls: (Scene | null)[] = [];
  const d = deferred<Scene>();
  let errored = false;
  loadSnapshotScene('plan', 'v-new', {
    setScene: (s) => calls.push(s),
    fetchScene: () => d.promise,
    onError: () => {
      errored = true;
    },
  });
  d.reject(new Error('boom'));
  await d.promise.catch(() => {});
  await tick();

  expect(errored).toBe(true);
  // Only null was ever applied — the view never showed (or kept) a scene on failure.
  expect(calls.every((c) => c === null)).toBe(true);
  expect(calls[calls.length - 1]).toBeNull();
});

test('missing plan id: stale scene state is cleared and no request is made', () => {
  const calls: (Scene | null)[] = [];
  let fetchCalled = false;
  loadSnapshotScene(undefined, 'v-new', {
    setScene: (s) => calls.push(s),
    fetchScene: () => {
      fetchCalled = true;
      return deferred<Scene>().promise;
    },
  });
  expect(calls).toEqual([null]);
  expect(fetchCalled).toBe(false);
});
