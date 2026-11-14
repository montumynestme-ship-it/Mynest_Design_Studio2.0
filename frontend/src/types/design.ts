import type { FurnitureItem } from '../data/furniture';

/**
 * A placed furniture instance in **world (plan) pixel** coordinates — the same
 * coordinate space as the rendered floor-plan image, so items stay locked to the
 * plan through any pan/zoom. Persisted per floor plan.
 */
export interface PlacedItem {
  uid: string;
  item: FurnitureItem;
  x: number; // center X, world px
  y: number; // center Y, world px
  w: number; // width, world px
  h: number; // height (depth on plan), world px
  rotation: number; // degrees
  label?: string; // custom display name; falls back to item.name when empty
  /**
   * AIR-03 authoritative room membership (grouping metadata only — NOT a transform).
   * Set by the designer on open-plan Dining furniture to route it into one group:
   * 'KITCHEN' | 'LIVING_AREA' | 'INDEPENDENT_DINING'. Undefined = untagged (legacy /
   * resolver decides). Distinct from the styling-only room-tag annotation.
   */
  room_membership?: string;
  /**
   * AIR-03 Step 2M.1 explicit RENDER INCLUSION (NOT a transform). Set by the designer on a
   * non-dining item to include it in a specific CONFIRMED room's render even when its
   * footprint is outside that room's floor polygon: 'KITCHEN' | 'LIVING_AREA'. Undefined =
   * no override. Distinct from both the canonical transform and the dining `room_membership`.
   */
  render_room?: string;
}
