/**
 * Maps a plan item_id to how it's drawn in 3D: a procedural "kind" (recognisable
 * shape), a real-ish height, and a colour. Footprint (width/depth), position and
 * rotation always come from the plan — this only supplies the vertical dimension
 * and the shape/material the 2D plan can't encode. Heights are in scene units
 * where 1 unit ≈ 1 metre and walls are ~2.7.
 */
export type FurnitureKind =
  | 'bed'
  | 'wardrobe'
  | 'sofa'
  | 'armchair'
  | 'coffee_table'
  | 'side_table'
  | 'dining_table'
  | 'dining_chair'
  | 'tv_unit'
  | 'fridge'
  | 'cooktop'
  | 'sink'
  | 'dresser'
  | 'counter'
  | 'bookshelf'
  | 'bench'
  | 'door'
  | 'window'
  | 'generic';

export interface Furniture3DSpec {
  height: number;
  color: string;
  kind: FurnitureKind;
  name: string;
}

const SPECS: Record<string, Furniture3DSpec> = {
  // --- Current library items ---
  bed: { height: 0.5, color: '#d8d2c8', kind: 'bed', name: 'Bed' },
  'lounger-sofa': { height: 0.75, color: '#c8b79e', kind: 'sofa', name: 'Loungers Sofa' },
  'center-table': { height: 0.4, color: '#9c7a52', kind: 'coffee_table', name: 'Center Table' },
  console: { height: 0.8, color: '#9c7a52', kind: 'dresser', name: 'Console' },
  partition: { height: 1.8, color: '#8a6a45', kind: 'generic', name: 'Partition' },
  'dressing-table': { height: 0.8, color: '#9c7a52', kind: 'dresser', name: 'Dressing Table' },
  // Kitchen base cabinet run — a RECOGNISABLE counter (cabinet body + stone
  // worktop + toe-kick), not a chest-of-drawers. Footprint/position/rotation stay
  // the plan's; this only makes the L-shaped kitchen read as a kitchen in 3D/base.
  'kitchen-base': { height: 0.9, color: '#cfc6b6', kind: 'counter', name: 'Kitchen Base' },
  chimney: { height: 0.7, color: '#b8bcc0', kind: 'generic', name: 'Chimney' },
  'bay-window-seat': { height: 0.45, color: '#c8b79e', kind: 'bench', name: 'Bay Window Seating' },
  'shoe-rack': { height: 0.6, color: '#8a6a45', kind: 'dresser', name: 'Shoe Rack' },
  door: { height: 2.1, color: '#7a5c3b', kind: 'door', name: 'Door' },
  window: { height: 1.2, color: '#00e5ff', kind: 'window', name: 'Window' },
  // --- Retired items (kept so existing plans still render in 3D) ---
  'sofa-3': { height: 0.75, color: '#c8b79e', kind: 'sofa', name: '3 Seater Sofa' },
  'sofa-l': { height: 0.75, color: '#c8b79e', kind: 'sofa', name: 'L-Shaped Sofa' },
  armchair: { height: 0.78, color: '#c8b79e', kind: 'armchair', name: 'Arm Chair' },
  'coffee-table': { height: 0.4, color: '#9c7a52', kind: 'coffee_table', name: 'Coffee Table' },
  'tv-unit': { height: 0.5, color: '#6f5637', kind: 'tv_unit', name: 'TV Unit' },
  bookshelf: { height: 2.0, color: '#8a6a45', kind: 'bookshelf', name: 'Bookshelf' },
  'queen-bed': { height: 0.5, color: '#d8d2c8', kind: 'bed', name: 'Queen Bed' },
  'king-bed': { height: 0.5, color: '#d8d2c8', kind: 'bed', name: 'King Bed' },
  wardrobe: { height: 2.1, color: '#8a6a45', kind: 'wardrobe', name: 'Wardrobe' },
  'side-table': { height: 0.55, color: '#9c7a52', kind: 'side_table', name: 'Side Table' },
  dresser: { height: 0.82, color: '#9c7a52', kind: 'dresser', name: 'Dresser' },
  'dining-table': { height: 0.75, color: '#9c7a52', kind: 'dining_table', name: 'Dining Table' },
  'dining-chair': { height: 0.9, color: '#b09a7a', kind: 'dining_chair', name: 'Dining Chair' },
  bench: { height: 0.45, color: '#9c7a52', kind: 'bench', name: 'Bench' },
  refrigerator: { height: 1.8, color: '#b8bcc0', kind: 'fridge', name: 'Refrigerator' },
  cooktop: { height: 0.9, color: '#9aa0a6', kind: 'cooktop', name: 'Cooktop' },
  sink: { height: 0.9, color: '#aab0b6', kind: 'sink', name: 'Sink' },
  bathtub: { height: 0.6, color: '#cdd4d8', kind: 'generic', name: 'Bathtub' },
  shower: { height: 2.0, color: '#cdd4d8', kind: 'generic', name: 'Shower' },
  washbasin: { height: 0.9, color: '#cdd4d8', kind: 'sink', name: 'Washbasin' },
  'floor-lamp': { height: 1.6, color: '#e8d9a0', kind: 'generic', name: 'Floor Lamp' },
  'desk-lamp': { height: 0.5, color: '#e8d9a0', kind: 'generic', name: 'Desk Lamp' },
};

export function furniture3d(itemId: string): Furniture3DSpec {
  return (
    SPECS[itemId] ?? {
      height: 0.6,
      color: '#b0805a',
      kind: 'generic',
      name: itemId.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    }
  );
}
