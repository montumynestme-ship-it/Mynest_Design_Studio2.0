/**
 * F-3 regression — honest legacy AI geometry-fidelity status.
 *
 * Exercises the ACTUAL status-mapping helper the gallery uses
 * (`resolveAiGeometryStatus` in src/lib/generations.ts) — not a re-implementation —
 * to prove a legacy record with no `geometry_status` is never presented as verified
 * fidelity merely because `geometry_faithful === true`.
 *
 * Pure logic: no `page`, no dev server, no browser. Runs with the existing
 * Playwright runner (`playwright test e2e/ai-fidelity-status.spec.ts`).
 */
import { test, expect } from '@playwright/test';
import { resolveAiGeometryStatus } from '../src/lib/generations';

// The gallery renders FAITHFUL->"Faithful", FAIL->"Failed", UNVERIFIED->"Not Verified".
// We assert the status the helper resolves (what drives that label); only FAITHFUL is
// ever shown as verified.
test('legacy record: no status + geometry_faithful true -> UNVERIFIED (not verified)', () => {
  expect(resolveAiGeometryStatus(undefined, true)).toBe('UNVERIFIED');
  expect(resolveAiGeometryStatus(null, true)).toBe('UNVERIFIED');
});

test('legacy record: no status + geometry_faithful false -> FAIL (documented failure)', () => {
  expect(resolveAiGeometryStatus(undefined, false)).toBe('FAIL');
  expect(resolveAiGeometryStatus(null, false)).toBe('FAIL');
});

test('explicit FAITHFUL -> FAITHFUL', () => {
  // Explicit evidence-driven status is authoritative even if the legacy flag disagrees.
  expect(resolveAiGeometryStatus('FAITHFUL', null)).toBe('FAITHFUL');
  expect(resolveAiGeometryStatus('FAITHFUL', false)).toBe('FAITHFUL');
});

test('explicit FAIL -> FAIL', () => {
  expect(resolveAiGeometryStatus('FAIL', true)).toBe('FAIL');
});

test('explicit UNVERIFIED -> UNVERIFIED (even if legacy flag is true)', () => {
  expect(resolveAiGeometryStatus('UNVERIFIED', true)).toBe('UNVERIFIED');
});

test('missing status + no legacy flag -> UNVERIFIED', () => {
  expect(resolveAiGeometryStatus(undefined, undefined)).toBe('UNVERIFIED');
  expect(resolveAiGeometryStatus(null, null)).toBe('UNVERIFIED');
});

test('unknown status string is never presented as verified -> UNVERIFIED', () => {
  const unknown = resolveAiGeometryStatus('SOMETHING_NEW', true);
  expect(unknown).not.toBe('FAITHFUL');
  expect(unknown).toBe('UNVERIFIED');
  // empty string is treated as absent -> legacy path
  expect(resolveAiGeometryStatus('', true)).toBe('UNVERIFIED');
});
