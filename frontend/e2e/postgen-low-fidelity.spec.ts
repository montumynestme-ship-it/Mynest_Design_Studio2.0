/**
 * Phase 4C Step 1F regression — LOW_FIDELITY restyle warning gate.
 *
 * Exercises the ACTUAL helper the gallery uses (`isLowFidelityRestyle` in
 * src/lib/generations.ts) to prove the warning shows ONLY for the explicit
 * "LOW_FIDELITY" status and never for ordinary / unknown outputs. Pure logic:
 * no page, no server, no browser, no new dependencies.
 */
import { test, expect } from '@playwright/test';
import { isLowFidelityRestyle } from '../src/lib/generations';

test('LOW_FIDELITY -> warning shown', () => {
  expect(isLowFidelityRestyle('LOW_FIDELITY')).toBe(true);
});

test('ordinary output (OK) -> no warning', () => {
  expect(isLowFidelityRestyle('OK')).toBe(false);
});

test('missing / unknown status -> no warning (backward compatible)', () => {
  expect(isLowFidelityRestyle(null)).toBe(false);
  expect(isLowFidelityRestyle(undefined)).toBe(false);
  expect(isLowFidelityRestyle('')).toBe(false);
  expect(isLowFidelityRestyle('SOMETHING_NEW')).toBe(false);
});
