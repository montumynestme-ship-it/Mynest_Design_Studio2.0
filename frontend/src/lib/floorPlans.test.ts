// Regression tests for the layout save contract (AIR-03 dining-membership persistence).
// Root cause fixed here: saveLayout used to fire-and-forget the PUT and never inspect
// response.ok, so a non-2xx — a backend validation error, or (the observed case) a Vite
// dev-proxy HTTP 500 when the backend/target port was unreachable — resolved WITHOUT
// rejecting. The caller's `.then()` then reported "Saved" while nothing persisted, so a
// Kitchen membership selection was silently lost. These tests pin: (a) the outgoing PUT
// carries room_membership: "KITCHEN" on the correct item with the others preserved, and
// (b) any non-OK response REJECTS (so the UI shows "Not saved — try again", never "Saved").
// Pure fetch-mock tests — no DOM, no backend, no real network.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getLayout, saveLayout, type LayoutItem } from './floorPlans';

const PLAN = 'f6b65d2b-4f96-4931-9f08-67dbd09776f6';
const DINING_UID = 'dining-table-1787478800756';

function layout(): LayoutItem[] {
  return [
    { uid: 'bed-1', item_id: 'bed', cx: 100, cy: 100, w: 200, h: 150, rotation: 0, room_membership: null },
    { uid: DINING_UID, item_id: 'dining-table', cx: 400, cy: 300, w: 180, h: 90, rotation: 0, room_membership: 'KITCHEN' },
  ];
}

describe('saveLayout', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
  });
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('PUTs the layout to the plan endpoint with room_membership: "KITCHEN" on the dining item, others preserved', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: layout() }) });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(saveLayout(PLAN, layout())).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/floor-plans/${PLAN}/layout`);
    expect(init.method).toBe('PUT');
    expect(init.headers['Content-Type']).toBe('application/json');
    const body = JSON.parse(init.body as string) as { items: LayoutItem[] };
    const dining = body.items.find((i) => i.uid === DINING_UID);
    expect(dining?.room_membership).toBe('KITCHEN');
    // The other furniture item is carried through unchanged (no accidental drop/mutation).
    expect(body.items.find((i) => i.uid === 'bed-1')?.room_membership).toBeNull();
    expect(body.items).toHaveLength(2);
  });

  it('REJECTS on a backend validation error (422) — a failed save never resolves as success', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: 'bad' }) }) as unknown as typeof fetch;
    await expect(saveLayout(PLAN, layout())).rejects.toThrow();
  });

  it('REJECTS on a dev-proxy 500 (backend/target port unreachable) — the exact silent-success case', async () => {
    // Vite returns an HTTP 500 (not a network rejection) when its proxy target refuses the
    // connection; fetch RESOLVES with ok=false. This must still reject so the UI shows error.
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }) as unknown as typeof fetch;
    await expect(saveLayout(PLAN, layout())).rejects.toThrow('Failed to save layout.');
  });

  it('REJECTS on a true network failure (fetch rejects)', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch;
    await expect(saveLayout(PLAN, layout())).rejects.toThrow();
  });
});

describe('getLayout (guard: the read path already checks ok — keep it that way)', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
  });

  it('returns the persisted items (membership round-trips back)', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ items: layout() }) }) as unknown as typeof fetch;
    const items = await getLayout(PLAN);
    expect(items.find((i) => i.uid === DINING_UID)?.room_membership).toBe('KITCHEN');
  });

  it('throws (never returns []) on a non-OK read, so a failed load is never saved back as empty', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }) as unknown as typeof fetch;
    await expect(getLayout(PLAN)).rejects.toThrow();
  });
});
