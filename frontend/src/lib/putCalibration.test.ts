import { describe, it, expect, vi, afterEach } from 'vitest';
import { putCalibration } from './scene';

afterEach(() => vi.restoreAllMocks());

describe('putCalibration', () => {
  it('PUTs p1/p2/known_distance_mm to the calibration endpoint and returns the result', async () => {
    const result = { file_id: 'f6', scale_mm_per_px: 6, mpp: 0.006, calibrated: true, source: 'user_measurement' };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => result });
    vi.stubGlobal('fetch', fetchMock);

    const out = await putCalibration('f6', { p1: [0, 0], p2: [300, 400], known_distance_mm: 3000 });

    expect(out).toEqual(result);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/floor-plans/f6/calibration');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toMatchObject({ p1: [0, 0], p2: [300, 400], known_distance_mm: 3000 });
  });

  it('passes the overwrite flag through', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    await putCalibration('f6', { p1: [0, 0], p2: [1, 0], known_distance_mm: 1000, overwrite: true });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).overwrite).toBe(true);
  });

  it('throws with the backend detail message on a non-2xx response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: 'Floor plan is already calibrated; pass overwrite=true to replace it' }),
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(
      putCalibration('f6', { p1: [0, 0], p2: [1, 0], known_distance_mm: 1000 }),
    ).rejects.toThrow(/already calibrated/);
  });

  it('throws a generic message when the error body is not JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error('not json');
      },
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(
      putCalibration('f6', { p1: [0, 0], p2: [1, 0], known_distance_mm: 1000 }),
    ).rejects.toThrow(/Calibration failed \(500\)/);
  });
});
