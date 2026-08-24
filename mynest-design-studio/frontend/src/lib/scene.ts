/**
 * Client model of the deterministic room scene (GET /api/floor-plans/:id/scene).
 * Every value is authoritative geometry from the 2D plan — the 3D renderer only
 * skins it; it never moves, adds, or removes anything (CLAUDE.md RULE #1).
 */
export interface SceneFurniture {
  uid: string;
  item_id: string;
  name: string;
  cx: number; // centre X, world px
  cy: number; // centre Y, world px
  w: number; // width, world px
  h: number; // depth on plan, world px
  rotation: number; // degrees
}

export interface SceneRoom {
  id: string;
  label: string;
  bbox: [number, number, number, number]; // [x, y, w, h] world px
  furniture: SceneFurniture[];
}

export interface Scene {
  page: { width: number; height: number; scale?: number };
  walls: [number, number, number, number][];
  /** Source colour of each wall (parallel to `walls`). Structural walls are
   * "#141414"; drafter-coloured lines (windows/features) keep their hue. */
  wall_colors?: string[];
  rooms: SceneRoom[];
}

export async function fetchScene(planId: string): Promise<Scene> {
  const res = await fetch(`/api/floor-plans/${planId}/scene`);
  if (!res.ok) throw new Error(`Failed to load 3D scene (${res.status})`);
  return (await res.json()) as Scene;
}

/**
 * Metres per plan pixel — calibrated from a bed's real length (~2.0 m), else a
 * side table (~0.45 m), else a sane constant. Keeps the whole scene at a real
 * human scale without needing the plan's absolute drawing scale.
 */
export function computeMpp(rooms: SceneRoom[]): number {
  for (const r of rooms) {
    const bed = r.furniture.find((f) => f.item_id.includes('bed'));
    if (bed) return 2.0 / Math.max(bed.w, bed.h);
  }
  for (const r of rooms) {
    const st = r.furniture.find((f) => f.item_id === 'side-table');
    if (st) return 0.45 / Math.max(st.w, st.h);
  }
  return 0.01;
}
