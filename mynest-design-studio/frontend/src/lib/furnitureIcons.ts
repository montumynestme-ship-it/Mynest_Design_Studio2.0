import { useEffect, useState } from 'react';

/**
 * Maps a furniture catalog item_id to a top-down (plan-view) SVG icon served
 * from /public/furniture. Icons are original, license-free line art — so they
 * can ship in a commercial build. To swap in licensed art later (e.g. purchased
 * Flaticon SVGs), just replace the file of the same name in /public/furniture.
 */
export const FURNITURE_ICON_NAME: Record<string, string> = {
  // Current library items
  bed: 'bed',
  'dressing-table': 'dressing-table',
  'bay-window-seat': 'bay-window-seat',
  'lounger-sofa': 'lounger',
  'center-table': 'coffee-table',
  'kitchen-base': 'kitchen-base',
  chimney: 'chimney',
  door: 'door',
  console: 'console',
  partition: 'partition',
  'shoe-rack': 'shoe-rack',
  // Retired items (kept so existing placements still show an icon)
  'sofa-3': 'sofa',
  'sofa-l': 'sofa-l',
  armchair: 'armchair',
  'coffee-table': 'coffee-table',
  'tv-unit': 'tv-unit',
  bookshelf: 'bookshelf',
  'queen-bed': 'bed',
  'king-bed': 'bed',
  wardrobe: 'wardrobe',
  'side-table': 'side-table',
  dresser: 'dresser',
  'dining-table': 'dining-table',
  'dining-chair': 'chair',
  bench: 'bench',
  refrigerator: 'fridge',
  cooktop: 'cooktop',
  sink: 'sink',
  bathtub: 'bathtub',
  shower: 'shower',
  washbasin: 'washbasin',
  'floor-lamp': 'floor-lamp',
  'desk-lamp': 'desk-lamp',
};

export function iconUrlForItem(itemId: string): string | undefined {
  const name = FURNITURE_ICON_NAME[itemId];
  return name ? `/furniture/${name}.svg` : undefined;
}

// Module-level cache so icons are fetched/decoded once for the whole session.
const cache = new Map<string, HTMLImageElement>();

/**
 * Preloads every furniture icon once and returns a url -> HTMLImageElement map.
 * Re-renders the caller as each icon finishes decoding (so Konva redraws it).
 */
export function useFurnitureIcons(): Record<string, HTMLImageElement> {
  const [loaded, setLoaded] = useState<Record<string, HTMLImageElement>>(() =>
    Object.fromEntries(cache),
  );

  useEffect(() => {
    const urls = Array.from(
      new Set(Object.values(FURNITURE_ICON_NAME).map((n) => `/furniture/${n}.svg`)),
    );
    let cancelled = false;
    urls.forEach((url) => {
      if (cache.has(url)) return;
      const img = new Image();
      img.onload = () => {
        cache.set(url, img);
        if (!cancelled) setLoaded(Object.fromEntries(cache));
      };
      img.src = url;
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return loaded;
}
