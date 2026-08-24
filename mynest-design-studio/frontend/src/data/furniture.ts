import { Bed, Box, DoorOpen, Sofa, type LucideIcon } from 'lucide-react';

export interface FurnitureItem {
  id: string;
  name: string;
  /** Default dimensions in millimetres. */
  width: number;
  depth: number;
  height: number;
  icon: LucideIcon;
}

export interface FurnitureCategory {
  category: string;
  items: FurnitureItem[];
}

/**
 * Furniture library shown in the Design Studio — ONLY these placeable items.
 * (The previous catalog's pieces are retained as `legacyFurniture` below so any
 * already-placed items on existing plans still render; they are just no longer
 * offered for new placement.)
 */
export const furnitureCatalog: FurnitureCategory[] = [
  {
    category: 'Living Room',
    items: [
      { id: 'lounger-sofa', name: 'Loungers Sofa', width: 1900, depth: 900, height: 800, icon: Sofa },
      { id: 'center-table', name: 'Center Table', width: 1000, depth: 600, height: 400, icon: Box },
      { id: 'console', name: 'Console', width: 1100, depth: 350, height: 800, icon: Box },
      { id: 'partition', name: 'Partition', width: 1800, depth: 300, height: 1800, icon: Box },
    ],
  },
  {
    category: 'Bedroom',
    items: [
      { id: 'bed', name: 'Bed', width: 1800, depth: 2000, height: 1100, icon: Bed },
      { id: 'side-table', name: 'Side Table', width: 450, depth: 450, height: 550, icon: Box },
      { id: 'dressing-table', name: 'Dressing', width: 1200, depth: 600, height: 750, icon: Box },
    ],
  },
  {
    category: 'Dining & Kitchen',
    items: [
      { id: 'dining-table', name: 'Dining Table', width: 1500, depth: 900, height: 750, icon: Box },
      { id: 'dining-chair', name: 'Dining Chair', width: 450, depth: 500, height: 900, icon: Box },
      { id: 'kitchen-base', name: 'Kitchen Base', width: 2400, depth: 600, height: 900, icon: Box },
      { id: 'chimney', name: 'Chimney', width: 900, depth: 500, height: 600, icon: Box },
    ],
  },
  {
    category: 'Entry & Structure',
    items: [
      { id: 'bay-window-seat', name: 'Bay Window Seating', width: 1500, depth: 600, height: 450, icon: Box },
      { id: 'shoe-rack', name: 'Shoe Rack', width: 900, depth: 350, height: 600, icon: Box },
      { id: 'door', name: 'Doors', width: 900, depth: 900, height: 2100, icon: DoorOpen },
    ],
  },
];

/**
 * Retired catalog items — NOT shown in the library, but kept so existing saved
 * layouts that reference these ids still resolve and render. Do not add these to
 * `furnitureCatalog`.
 */
export const legacyFurniture: FurnitureItem[] = [
  { id: 'sofa-3', name: '3 Seater Sofa', width: 2100, depth: 900, height: 850, icon: Sofa },
  { id: 'sofa-l', name: 'L-Shaped Sofa', width: 2600, depth: 1800, height: 850, icon: Sofa },
  { id: 'armchair', name: 'Arm Chair', width: 800, depth: 850, height: 800, icon: Box },
  { id: 'coffee-table', name: 'Coffee Table', width: 1000, depth: 600, height: 450, icon: Box },
  { id: 'tv-unit', name: 'TV Unit', width: 1800, depth: 450, height: 500, icon: Box },
  { id: 'bookshelf', name: 'Bookshelf', width: 900, depth: 350, height: 2000, icon: Box },
  { id: 'queen-bed', name: 'Queen Bed', width: 1600, depth: 2000, height: 1100, icon: Bed },
  { id: 'king-bed', name: 'King Bed', width: 1800, depth: 2000, height: 1100, icon: Bed },
  { id: 'wardrobe', name: 'Wardrobe', width: 1200, depth: 600, height: 2100, icon: Box },
  { id: 'dresser', name: 'Dresser', width: 1000, depth: 450, height: 800, icon: Box },
  { id: 'bench', name: 'Bench', width: 1200, depth: 350, height: 450, icon: Box },
  { id: 'refrigerator', name: 'Refrigerator', width: 700, depth: 700, height: 1800, icon: Box },
  { id: 'cooktop', name: 'Cooktop', width: 600, depth: 520, height: 100, icon: Box },
  { id: 'sink', name: 'Sink', width: 800, depth: 500, height: 200, icon: Box },
  { id: 'bathtub', name: 'Bathtub', width: 1700, depth: 750, height: 600, icon: Box },
  { id: 'shower', name: 'Shower', width: 900, depth: 900, height: 2100, icon: Box },
  { id: 'washbasin', name: 'Washbasin', width: 600, depth: 450, height: 850, icon: Box },
  { id: 'floor-lamp', name: 'Floor Lamp', width: 400, depth: 400, height: 1600, icon: Box },
  { id: 'desk-lamp', name: 'Desk Lamp', width: 200, depth: 200, height: 450, icon: Box },
];

/** All items keyed by id (library + legacy) — used to resolve saved layouts. */
export const furnitureById: Map<string, FurnitureItem> = new Map(
  [...furnitureCatalog.flatMap((g) => g.items), ...legacyFurniture].map((item) => [item.id, item]),
);
