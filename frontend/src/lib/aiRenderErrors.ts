/**
 * Map a raw AI-generation error (from any configured provider) to a clear, user-facing
 * message. PROVIDER-AGNOSTIC: the active provider is a backend configuration
 * (DEFAULT_AI_PROVIDER — currently `fal`, with `nvidia` and a demo mock also supported),
 * so these messages must never hard-code one provider. Previously the inline mapping
 * assumed NVIDIA, which mislabeled real `fal` errors — e.g. a fal `HTTP 403
 * {"detail":"User is locked. Reason: TOP_UP."}` surfaced as "Invalid NVIDIA API key".
 *
 * Pure function (no React/DOM) so it is unit-testable. Behaviour: ordering matters — the
 * account-lock/top-up case is checked before the generic auth case because fal's lock
 * response is an HTTP 403 whose body also contains "authorization".
 */
export function mapAiRenderError(raw: string): string {
  const d = raw || 'AI generation failed.';
  const low = d.toLowerCase();

  // fal account lock pending a top-up (HTTP 403 {"detail":"User is locked. Reason: TOP_UP."}).
  if (low.includes('top_up') || low.includes('user is locked') || low.includes('locked. reason')) {
    return 'AI provider account is locked pending a top-up — add funds on the provider dashboard (fal.ai / build.nvidia.com), then retry.';
  }
  // Authentication / authorization (invalid or missing key, inactive account).
  if (d.includes('401') || d.includes('403') || low.includes('authentication') || low.includes('authorization')) {
    return 'AI provider authentication/authorization failed — check the configured provider API key and that the account is active and funded (backend .env).';
  }
  // Credits / quota / rate limit.
  if (d.includes('402') || d.includes('429') || low.includes('rate') || low.includes('credit') || low.includes('quota')) {
    return 'AI provider quota, credits, or rate limit exceeded — top up the provider balance or wait, then retry.';
  }
  // Model unavailable / not supported for this account.
  if (d.includes('404') || low.includes('model')) {
    return 'AI provider model unavailable — check the configured image model is supported by your account.';
  }
  // Long-running generation whose HTTP request dropped (the render may still finish).
  if (low.includes('timed out') || d.includes('504') || low.includes('failed to fetch')) {
    return 'AI Render is taking longer than usual. Check "View AI Render" in a moment — your renders may already be ready.';
  }
  return d.length > 220 ? d.slice(0, 220) + '… (click to dismiss)' : d;
}
