/**
 * WebGL capability-check regression (WebGL blocking fix).
 *
 * Verifies the pure `isWebGLAvailable()` detector (src/lib/scene.ts) that Scene3DModal
 * uses to show a clear "3D preview unavailable" message instead of letting the Three.js
 * <Canvas> throw when a browser/GPU blocks WebGL. Deterministic: globals are stubbed, so
 * no real GPU is needed. Covers no-DOM, context-null (blocked), context-present (works),
 * and getContext-throws (never crashes).
 */
import { test, expect } from '@playwright/test';
import { isWebGLAvailable } from '../src/lib/scene';

const g = globalThis as unknown as { window?: unknown; document?: unknown };

test.afterEach(() => {
  delete g.window;
  delete g.document;
});

test('no DOM (SSR / non-browser) -> false, never throws', () => {
  // In the Node test runtime there is no document.
  expect(isWebGLAvailable()).toBe(false);
});

test('WebGL blocked (getContext returns null) -> false', () => {
  g.window = { WebGLRenderingContext: function () {} };
  g.document = { createElement: () => ({ getContext: () => null }) };
  expect(isWebGLAvailable()).toBe(false);
});

test('WebGL available (a context is returned) -> true', () => {
  g.window = { WebGLRenderingContext: function () {} };
  g.document = { createElement: () => ({ getContext: (t: string) => (t === 'webgl2' ? {} : null) }) };
  expect(isWebGLAvailable()).toBe(true);
});

test('getContext throws (GPU policy) -> false, never propagates', () => {
  g.window = { WebGLRenderingContext: function () {} };
  g.document = {
    createElement: () => ({
      getContext: () => {
        throw new Error('WebGL blocked by policy');
      },
    }),
  };
  expect(isWebGLAvailable()).toBe(false);
});
