// Focused regression tests for Path B (opt-in perspective structural conditioning) request
// construction + snapshot-bound pairing. Pure functions only — no DOM, no backend, no fal call.
// Covers the frontend half of the structural contract; the backend pair gate is covered by
// backend/tests/test_structural_conditioning.py, and the gallery/loading/error UI by the
// unchanged Playwright e2e suite under frontend/e2e/.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildStructuralRequestFields,
  fetchAiConfig,
  requireStructuralMode,
  StructuralPairError,
  validateStructuralPair,
  withStructuralFields,
  type BaseRenderMeta,
  type GenerateBody,
  type StructuralRenderMeta,
} from './generations';

const W = 1216;
const H = 832;
const ASPECT = W / H;
const DV = 'dv-1';

const camera = { fov: 46, aspect: ASPECT, position: [1, 2, 3] as [number, number, number], target: [0, 0, 0] as [number, number, number] };

function baseMeta(roomKey: string, over: Partial<BaseRenderMeta> = {}): BaseRenderMeta {
  return { design_version_id: DV, room_key: roomKey, width: W, height: H, ...over };
}
function structMeta(roomKey: string, over: Partial<StructuralRenderMeta> = {}): StructuralRenderMeta {
  return { design_version_id: DV, room_key: roomKey, width: W, height: H, ...over };
}

// Two rooms keyed by BOTH stable id and display label, exactly like base_renders.
const ROOMS = [
  { id: 'living-area', label: 'Living Area' },
  { id: 'bedroom-1', label: 'Bedroom 1' },
];

function baseRenderMetaMap(): Record<string, BaseRenderMeta> {
  const m: Record<string, BaseRenderMeta> = {};
  for (const r of ROOMS) {
    m[r.id] = baseMeta(r.id);
    m[r.label] = baseMeta(r.label);
  }
  return m;
}
function structuralRendersMap(): Record<string, string> {
  const m: Record<string, string> = {};
  for (const r of ROOMS) {
    const url = `data:image/png;base64,STRUCT-${r.id}`;
    m[r.id] = url;
    m[r.label] = url;
  }
  return m;
}
function structuralCamerasMap(): Record<string, typeof camera> {
  const m: Record<string, typeof camera> = {};
  for (const r of ROOMS) {
    m[r.id] = camera;
    m[r.label] = camera;
  }
  return m;
}

// ── validateStructuralPair — mirrors backend structural_pair.validate_structural_pair ──
describe('validateStructuralPair', () => {
  it('(case 6) rejects a design-version mismatch', () => {
    const { ok, reason } = validateStructuralPair(baseMeta('Living Area'), structMeta('Living Area', { design_version_id: 'dv-2' }));
    expect(ok).toBe(false);
    expect(reason).toContain('STRUCTURAL_WRONG_VERSION');
  });

  it('(case 7) rejects a room-id / room-key mismatch', () => {
    const { ok, reason } = validateStructuralPair(baseMeta('Living Area'), structMeta('Kitchen'));
    expect(ok).toBe(false);
    expect(reason).toContain('STRUCTURAL_WRONG_ROOM');
  });

  it('(case 8) rejects a dimension mismatch', () => {
    const { ok, reason } = validateStructuralPair(baseMeta('Living Area'), structMeta('Living Area', { width: 64, height: 64 }));
    expect(ok).toBe(false);
    expect(reason).toContain('STRUCTURAL_WRONG_SIZE');
  });

  it('(case 9) rejects a camera mismatch when BOTH sides carry a camera', () => {
    const { ok, reason } = validateStructuralPair(
      baseMeta('Living Area', { camera }),
      structMeta('Living Area', { camera: { ...camera, fov: 72 } }),
    );
    expect(ok).toBe(false);
    expect(reason).toContain('STRUCTURAL_CAMERA_MISMATCH');
  });

  it('skips the camera check when the base has no camera (the real pipeline), so a true pair is OK', () => {
    const { ok } = validateStructuralPair(baseMeta('Living Area'), structMeta('Living Area', { camera }));
    expect(ok).toBe(true);
  });

  it('accepts a matching version/room/dims pair', () => {
    expect(validateStructuralPair(baseMeta('Living Area'), structMeta('Living Area')).ok).toBe(true);
  });

  it('rejects a missing structural meta', () => {
    const { ok, reason } = validateStructuralPair(baseMeta('Living Area'), null);
    expect(ok).toBe(false);
    expect(reason).toContain('STRUCTURAL_MISSING');
  });
});

// ── buildStructuralRequestFields — pairing + assembly ───────────────────────────────────
describe('buildStructuralRequestFields', () => {
  it('(case 2/3) includes each room\'s own structural image, keyed by stable id AND label', () => {
    const fields = buildStructuralRequestFields({
      rooms: ROOMS,
      baseRenderMeta: baseRenderMetaMap(),
      structuralRenders: structuralRendersMap(),
      structuralCameras: structuralCamerasMap(),
      designVersionId: DV,
      width: W,
      height: H,
    });
    // Each room's image is paired to ITS OWN id and label — never borrowed/cross-paired.
    expect(fields.structural_renders['living-area']).toBe('data:image/png;base64,STRUCT-living-area');
    expect(fields.structural_renders['Living Area']).toBe('data:image/png;base64,STRUCT-living-area');
    expect(fields.structural_renders['bedroom-1']).toBe('data:image/png;base64,STRUCT-bedroom-1');
    expect(fields.structural_renders['Bedroom 1']).toBe('data:image/png;base64,STRUCT-bedroom-1');
    expect(fields.structural_render_meta['living-area'].room_key).toBe('living-area');
    expect(fields.structural_render_meta['Bedroom 1'].room_key).toBe('Bedroom 1');
    expect(fields.structural_render_meta['living-area'].camera?.fov).toBe(46);
  });

  it('(case 4) pairs by room identity regardless of ordering', () => {
    // Reverse the room order AND rebuild the maps in reverse insertion order.
    const reversed = [...ROOMS].reverse();
    const sr: Record<string, string> = {};
    for (const r of reversed) {
      const url = `data:image/png;base64,STRUCT-${r.id}`;
      sr[r.id] = url;
      sr[r.label] = url;
    }
    const fields = buildStructuralRequestFields({
      rooms: reversed,
      baseRenderMeta: baseRenderMetaMap(),
      structuralRenders: sr,
      structuralCameras: structuralCamerasMap(),
      designVersionId: DV,
      width: W,
      height: H,
    });
    // Still each room → its OWN image, proving no array-index pairing.
    expect(fields.structural_renders['living-area']).toBe('data:image/png;base64,STRUCT-living-area');
    expect(fields.structural_renders['bedroom-1']).toBe('data:image/png;base64,STRUCT-bedroom-1');
  });

  it('(case 5) throws STRUCTURAL_MISSING when one room has no structural render', () => {
    const sr = structuralRendersMap();
    delete sr['bedroom-1'];
    delete sr['Bedroom 1'];
    expect(() =>
      buildStructuralRequestFields({
        rooms: ROOMS,
        baseRenderMeta: baseRenderMetaMap(),
        structuralRenders: sr,
        structuralCameras: structuralCamerasMap(),
        designVersionId: DV,
        width: W,
        height: H,
      }),
    ).toThrow(StructuralPairError);
  });

  it('(case 6) throws on a design-version mismatch between base meta and the capture version', () => {
    // base meta says dv-1, but the capture claims dv-2 → the pair is invalid.
    let err: unknown;
    try {
      buildStructuralRequestFields({
        rooms: ROOMS,
        baseRenderMeta: baseRenderMetaMap(),
        structuralRenders: structuralRendersMap(),
        structuralCameras: structuralCamerasMap(),
        designVersionId: 'dv-2',
        width: W,
        height: H,
      });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(StructuralPairError);
    expect((err as StructuralPairError).code).toBe('STRUCTURAL_WRONG_VERSION');
  });

  it('(case 8) throws on a dimension mismatch vs the base meta', () => {
    const bm = baseRenderMetaMap();
    for (const k of Object.keys(bm)) bm[k] = { ...bm[k], width: 800, height: 600 };
    expect(() =>
      buildStructuralRequestFields({
        rooms: ROOMS,
        baseRenderMeta: bm,
        structuralRenders: structuralRendersMap(),
        structuralCameras: structuralCamerasMap(),
        designVersionId: DV,
        width: W,
        height: H,
      }),
    ).toThrow(/STRUCTURAL_WRONG_SIZE/);
  });

  it('(case 10) throws (no partial result) when the capture produced nothing', () => {
    expect(() =>
      buildStructuralRequestFields({
        rooms: ROOMS,
        baseRenderMeta: baseRenderMetaMap(),
        structuralRenders: {}, // capture failure / hard timeout
        structuralCameras: {},
        designVersionId: DV,
        width: W,
        height: H,
      }),
    ).toThrow(StructuralPairError);
  });
});

// ── withStructuralFields — disabled behaviour is byte-identical base-only ────────────────
describe('withStructuralFields', () => {
  const base: GenerateBody = {
    design_intent: { style: 'Modern Luxury' },
    all_sections: false,
    fresh_generation: true,
    base_renders: { 'living-area': 'data:image/png;base64,BASE' },
    base_render_meta: { 'living-area': { design_version_id: DV, room_key: 'living-area', width: W, height: H } },
    base_boxes: { 'living-area': [] },
  };

  it('(case 1/12) adds NO structural fields when disabled — body unchanged', () => {
    const out = withStructuralFields(base, false, {
      structural_renders: { 'living-area': 'x' },
      structural_render_meta: { 'living-area': structMeta('living-area') },
    });
    expect('structural_renders' in out).toBe(false);
    expect('structural_render_meta' in out).toBe(false);
    // (case 11) existing base-only fields are preserved exactly.
    expect(out.base_renders).toBe(base.base_renders);
    expect(out.base_render_meta).toBe(base.base_render_meta);
    expect(out.base_boxes).toBe(base.base_boxes);
  });

  it('(case 2) attaches structural fields when enabled', () => {
    const fields = {
      structural_renders: { 'living-area': 'data:image/png;base64,STRUCT' },
      structural_render_meta: { 'living-area': structMeta('living-area') },
    };
    const out = withStructuralFields(base, true, fields);
    expect(out.structural_renders).toEqual(fields.structural_renders);
    expect(out.structural_render_meta).toEqual(fields.structural_render_meta);
    expect(out.base_renders).toEqual(base.base_renders);
  });

  it('adds nothing when enabled but no fields were produced (defensive)', () => {
    const out = withStructuralFields(base, true, null);
    expect('structural_renders' in out).toBe(false);
  });
});

// ── fetchAiConfig — single, fail-safe flag source ────────────────────────────────────────
describe('fetchAiConfig', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
  });
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('reports true + resolved when the backend flag is exactly true', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ structural_conditioning: true }),
    }) as unknown as typeof fetch;
    expect(await fetchAiConfig()).toEqual({ structuralConditioning: true, resolved: true });
  });

  it('reports false + resolved when the backend flag is false (definitive disabled)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ structural_conditioning: false }),
    }) as unknown as typeof fetch;
    expect(await fetchAiConfig()).toEqual({ structuralConditioning: false, resolved: true });
  });

  it('a 200 with the field absent is a definitive disabled (older/non-fal backend)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }) as unknown as typeof fetch;
    expect(await fetchAiConfig()).toEqual({ structuralConditioning: false, resolved: true });
  });

  it('is UNRESOLVED (not a definitive disabled) on a non-OK response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }) as unknown as typeof fetch;
    expect(await fetchAiConfig()).toEqual({ structuralConditioning: false, resolved: false });
  });

  it('is UNRESOLVED when the backend is unreachable', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch;
    expect(await fetchAiConfig()).toEqual({ structuralConditioning: false, resolved: false });
  });
});

// ── requireStructuralMode — fails CLOSED on an unknown render mode ───────────────────────
describe('requireStructuralMode', () => {
  it('returns true when structural is resolved + enabled', () => {
    expect(requireStructuralMode({ structuralConditioning: true, resolved: true })).toBe(true);
  });

  it('returns false when structural is resolved + disabled (base-only)', () => {
    expect(requireStructuralMode({ structuralConditioning: false, resolved: true })).toBe(false);
  });

  it('throws AI_CONFIG_UNAVAILABLE when the mode is unresolved (no silent downgrade)', () => {
    let err: unknown;
    try {
      requireStructuralMode({ structuralConditioning: false, resolved: false });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(StructuralPairError);
    expect((err as StructuralPairError).code).toBe('AI_CONFIG_UNAVAILABLE');
  });
});

// ── camera in base_render_meta (AIR camera-gap fix) — pairing verifies the shared camera ──
describe('buildStructuralRequestFields with base camera', () => {
  it('accepts a pair whose base and structural cameras match', () => {
    const bm: Record<string, BaseRenderMeta> = {};
    for (const r of ROOMS) {
      bm[r.id] = baseMeta(r.id, { camera });
      bm[r.label] = baseMeta(r.label, { camera });
    }
    const fields = buildStructuralRequestFields({
      rooms: ROOMS,
      baseRenderMeta: bm,
      structuralRenders: structuralRendersMap(),
      structuralCameras: structuralCamerasMap(),
      designVersionId: DV,
      width: W,
      height: H,
    });
    expect(fields.structural_render_meta['living-area'].camera?.fov).toBe(46);
  });

  it('rejects a pair whose base camera disagrees with the structural camera', () => {
    const bm: Record<string, BaseRenderMeta> = {};
    for (const r of ROOMS) {
      bm[r.id] = baseMeta(r.id, { camera: { ...camera, fov: 72 } });
      bm[r.label] = baseMeta(r.label, { camera: { ...camera, fov: 72 } });
    }
    let err: unknown;
    try {
      buildStructuralRequestFields({
        rooms: ROOMS,
        baseRenderMeta: bm,
        structuralRenders: structuralRendersMap(),
        structuralCameras: structuralCamerasMap(),
        designVersionId: DV,
        width: W,
        height: H,
      });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(StructuralPairError);
    expect((err as StructuralPairError).code).toBe('STRUCTURAL_CAMERA_MISMATCH');
  });
});
