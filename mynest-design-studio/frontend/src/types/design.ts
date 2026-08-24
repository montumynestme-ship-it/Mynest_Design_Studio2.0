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
}
