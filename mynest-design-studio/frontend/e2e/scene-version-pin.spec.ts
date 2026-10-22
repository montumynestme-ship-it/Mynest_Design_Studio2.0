/**
 * Step 3B regression — deterministic-capture harness version pinning.
 *
 * Proves the pure `sceneUrl` helper (src/lib/scene.ts) that the audit harness uses:
 *   - passes an explicitly requested design version through as `?version=…` (URL-encoded);
 *   - leaves the DEFAULT behaviour unchanged (no query string) when no version is given,
 *     including null / undefined / empty string.
 * Pure logic: no page, no server, no browser, no new dependencies.
 */
import { test, expect } from '@playwright/test';
import { sceneUrl } from '../src/lib/scene';

const FID = 'f6b65d2b-4f96-4931-9f08-67dbd09776f6';

test('explicit version is passed through as ?version=', () => {
  expect(sceneUrl(FID, '1831bf84-f9d6-4d4f-aedc-4ad95d6145fe')).toBe(
    `/api/floor-plans/${FID}/scene?version=1831bf84-f9d6-4d4f-aedc-4ad95d6145fe`,
  );
});

test('version values are URL-encoded', () => {
  expect(sceneUrl(FID, 'a b/c')).toBe(`/api/floor-plans/${FID}/scene?version=a%20b%2Fc`);
});

test('default behaviour unchanged when no version supplied', () => {
  const base = `/api/floor-plans/${FID}/scene`;
  expect(sceneUrl(FID)).toBe(base);
  expect(sceneUrl(FID, null)).toBe(base);
  expect(sceneUrl(FID, undefined)).toBe(base);
  expect(sceneUrl(FID, '')).toBe(base); // empty string is falsy → no version pin
});
