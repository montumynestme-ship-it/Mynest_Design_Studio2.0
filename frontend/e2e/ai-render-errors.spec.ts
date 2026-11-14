/**
 * Regression: AI Render failure messages must be PROVIDER-AGNOSTIC.
 *
 * The active provider is a backend config (DEFAULT_AI_PROVIDER, currently `fal`). The old
 * inline mapping hard-coded NVIDIA, so a real fal error — notably the HTTP 403 account
 * lock `{"detail":"User is locked. Reason: TOP_UP."}` — surfaced to the user as
 * "Invalid NVIDIA API key". These tests lock the corrected mapping.
 */
import { test, expect } from '@playwright/test';
import { mapAiRenderError } from '../src/lib/aiRenderErrors';

// The exact shapes the fal adapter raises (see backend fal_flux_adapter.py).
const FAL_403_TOPUP =
  'fal authentication/authorization failed (HTTP 403): {"detail":"User is locked. Reason: TOP_UP."}. Check FAL_KEY and that the fal account is active/funded.';
const FAL_401 =
  'fal authentication/authorization failed (HTTP 401): unauthorized. Check FAL_KEY and that the fal account is active/funded.';
const FAL_CREDITS =
  'fal credits/rate-limit (HTTP 402): insufficient balance. Top up the fal account balance or wait.';

test('fal 403 TOP_UP lock maps to a top-up message, never an NVIDIA key message', () => {
  const msg = mapAiRenderError(FAL_403_TOPUP);
  expect(msg.toLowerCase()).toContain('locked pending a top-up');
  expect(msg).not.toContain('NVIDIA');
  expect(msg).not.toContain('NVIDIA_API_KEY');
});

test('fal auth error is provider-agnostic (no NVIDIA wording)', () => {
  const msg = mapAiRenderError(FAL_401);
  expect(msg.toLowerCase()).toContain('authentication');
  expect(msg).not.toContain('NVIDIA');
});

test('fal credits/rate-limit maps to a quota/credits message, not an NVIDIA quota message', () => {
  const msg = mapAiRenderError(FAL_CREDITS);
  expect(msg.toLowerCase()).toMatch(/quota|credit|rate limit/);
  expect(msg).not.toContain('NVIDIA');
});

test('model-unavailable and timeout cases stay provider-agnostic', () => {
  expect(mapAiRenderError('HTTP 404: model not found').toLowerCase()).toContain('model unavailable');
  expect(mapAiRenderError('HTTP 404: model not found')).not.toContain('NVIDIA');
  expect(mapAiRenderError('Failed to fetch').toLowerCase()).toContain('taking longer');
});

test('generic short error passes through; very long error is truncated', () => {
  expect(mapAiRenderError('weird provider glitch')).toBe('weird provider glitch');
  const long = 'x'.repeat(400);
  const out = mapAiRenderError(long);
  expect(out.length).toBeLessThanOrEqual(240);
  expect(out).toContain('… (click to dismiss)');
});
