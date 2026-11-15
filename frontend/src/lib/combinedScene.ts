/**
 * DEF-3 (slice) — pure builder for the full-plan "combined" room shown in the 3D dollhouse
 * preview (Scene3DModal). It assembles ONE synthetic room spanning the whole plan so the
 * renderer draws the rooms joined into a single connected house.
 *
 * Fixes the furniture-derived full-plan path:
 *  - renders even with ZERO furniture (no early null return),
 *  - derives the scene EXTENT from the ARCHITECTURE (wall endpoints + room boundary vertices),
 *    plus furniture so placed items stay framed — never furniture-only, so walls/rooms outside
 *    the furniture bounds are included,
 *  - aggregates every room's verified/unverified `opening_placements` so doors & windows still
 *    render and carve in the combined view.
 *
 * NOT in this slice (larger follow-on): preserving each room's own boundary polygon / polygon
 * floor in the single combined room — RoomScene3D renders one room with one boundary, so the
 * combined room intentionally carries NO `boundary` (rectangular-floor fallback) for now.
 *
 * Pure + deterministic. Furniture is passed through UNCHANGED (identity/transforms/inventory
 * from the selected design version) — never inferred or reconstructed from architecture
 * (CLAUDE.md RULE #1).
 */
import type { Scene, SceneRoom, SceneFurniture, OpeningPlacement } from './scene';

export function buildCombinedRoom(scene: Scene | null | undefined): SceneRoom | null {
  if (!scene) return null;
  const rooms = scene.rooms ?? [];
  const furniture: SceneFurniture[] = rooms.flatMap((r) => r.furniture ?? []);
  const openingPlacements: OpeningPlacement[] = rooms.flatMap((r) => r.opening_placements ?? []);

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let has = false;
  const ext = (x: number, y: number) => {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    has = true;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  };

  for (const w of scene.walls ?? []) {
    if (Array.isArray(w) && w.length >= 4) {
      ext(Number(w[0]), Number(w[1]));
      ext(Number(w[2]), Number(w[3]));
    }
  }
  for (const r of rooms) {
    for (const p of r.boundary ?? []) {
      if (Array.isArray(p) && p.length >= 2) ext(Number(p[0]), Number(p[1]));
    }
  }
  for (const f of furniture) {
    ext(f.cx - f.w / 2, f.cy - f.h / 2);
    ext(f.cx + f.w / 2, f.cy + f.h / 2);
  }

  let bbox: [number, number, number, number];
  if (has) {
    bbox = [minX, minY, maxX - minX, maxY - minY];
  } else if (scene.page && scene.page.width > 0 && scene.page.height > 0) {
    // No architecture and no furniture — fall back to the page bounds so an empty plan still
    // has a frame (honest empty room), rather than returning nothing.
    bbox = [0, 0, scene.page.width, scene.page.height];
  } else {
    return null; // genuinely nothing to show
  }

  return {
    id: 'floor-plan',
    label: 'Floor Plan',
    bbox,
    furniture,
    opening_placements: openingPlacements,
  };
}

/**
 * DEF-3 follow-on — the per-room ARCHITECTURAL floor polygons (world px) for the combined
 * view. ONLY wall-proven architectural rooms with a real closed boundary are returned; a
 * furniture-hull / UNCERTAIN fallback room is excluded (never render fabricated room geometry
 * as a confirmed floor). Pure + deterministic; copies the vertices, never mutates the scene.
 */
export function collectRoomFloors(scene: Scene | null | undefined): Array<Array<[number, number]>> {
  if (!scene) return [];
  const out: Array<Array<[number, number]>> = [];
  for (const r of scene.rooms ?? []) {
    const poly = r.boundary;
    if (String(r.geometry_source) === 'architectural' && Array.isArray(poly) && poly.length >= 4) {
      out.push(poly.map((p) => [Number(p[0]), Number(p[1])] as [number, number]));
    }
  }
  return out;
}
