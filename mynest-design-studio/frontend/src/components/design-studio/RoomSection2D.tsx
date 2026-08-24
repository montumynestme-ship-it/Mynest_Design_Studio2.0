import { iconUrlForItem } from '../../lib/furnitureIcons';
import type { SceneRoom } from '../../lib/scene';

/**
 * Clean architectural top-down of ONE room, drawn deterministically from the
 * plan geometry: only this room's walls (each wall clipped to the room's own
 * boundary) + this room's furniture as line-art symbols, at their exact
 * position, size and rotation. This is the "confirm the 2D layout" step before
 * the 3D model — one isolated section, nothing AI-decided (CLAUDE.md RULE #1).
 */
interface RoomSection2DProps {
  room: SceneRoom;
  walls: [number, number, number, number][];
  /** Source colour per wall (parallel to `walls`); windows/features keep their hue. */
  wallColors?: string[];
}

const WALL_COLOR = '#141414';

/** Liang–Barsky: clip a segment to a rectangle, or null if fully outside. */
function clipToRect(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  xmin: number,
  ymin: number,
  xmax: number,
  ymax: number,
): [number, number, number, number] | null {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const p = [-dx, dx, -dy, dy];
  const q = [x1 - xmin, xmax - x1, y1 - ymin, ymax - y1];
  let t0 = 0;
  let t1 = 1;
  for (let i = 0; i < 4; i++) {
    if (p[i] === 0) {
      if (q[i] < 0) return null; // parallel and outside
    } else {
      const r = q[i] / p[i];
      if (p[i] < 0) {
        if (r > t1) return null;
        if (r > t0) t0 = r;
      } else {
        if (r < t0) return null;
        if (r < t1) t1 = r;
      }
    }
  }
  return [x1 + t0 * dx, y1 + t0 * dy, x1 + t1 * dx, y1 + t1 * dy];
}

/** Coloured, top-down furniture palette matching a printed architectural plan
 * (beige floors, wood tables, mauve sofas, teal kitchen, white bathroom …). */
function furnitureStyle(itemId: string, name: string): { fill: string; stroke: string; kind: string } | null {
  const s = `${itemId} ${name}`.toLowerCase();
  const has = (...k: string[]) => k.some((w) => s.includes(w));
  if (has('door')) return null; // doors are drawn as their line-art swing, no colour box
  if (has('bed')) return { fill: '#efe7d2', stroke: '#8a7f63', kind: 'bed' };
  if (has('sofa', 'lounger', 'couch', 'armchair', 'settee')) return { fill: '#cbb2ac', stroke: '#9c837d', kind: 'sofa' };
  if (has('kitchen', 'cooktop', 'stove', 'sink', 'fridge', 'refriger', 'chimney', 'base', 'hob'))
    return { fill: '#a9d6c9', stroke: '#6fae9d', kind: 'kitchen' };
  if (has('bath', 'tub', 'shower', 'washbasin', 'toilet', 'wc', 'basin', 'lavatory'))
    return { fill: '#ffffff', stroke: '#9fbcd0', kind: 'bath' };
  if (has('wardrobe', 'dresser', 'shoe', 'partition', 'tv', 'bookshelf', 'console', 'rack', 'cabinet', 'storage'))
    return { fill: '#b6935f', stroke: '#856a3f', kind: 'storage' };
  if (has('dining', 'table', 'desk', 'coffee', 'center', 'centre', 'dressing'))
    return { fill: '#d3ad74', stroke: '#a07d45', kind: 'table' };
  if (has('chair', 'bench', 'stool')) return { fill: '#dcc69c', stroke: '#a88f5f', kind: 'chair' };
  return { fill: '#e6dcc3', stroke: '#b0a482', kind: 'default' };
}

export default function RoomSection2D({ room, walls, wallColors }: RoomSection2DProps) {
  const [bx, by, bw, bh] = room.bbox;
  const pad = Math.max(bw, bh) * 0.12;
  const vb = { x: bx - pad, y: by - pad, w: bw + pad * 2, h: bh + pad * 2 };
  const rx1 = vb.x + vb.w;
  const ry1 = vb.y + vb.h;

  // Only the portions of walls that fall inside THIS room's crop — one section.
  // Carry each wall's source colour through the clip so windows/features keep it.
  const minLen = Math.max(bw, bh) * 0.02;
  const roomWalls = walls
    .map((w, i) => {
      const seg = clipToRect(w[0], w[1], w[2], w[3], vb.x, vb.y, rx1, ry1);
      return seg ? { seg, color: wallColors?.[i] || WALL_COLOR } : null;
    })
    .filter((w): w is { seg: [number, number, number, number]; color: string } => w !== null)
    .filter(({ seg: [x1, y1, x2, y2] }) => Math.hypot(x2 - x1, y2 - y1) > minLen);

  // Structural walls stay black; anything the drafter coloured is a window/feature.
  const structuralWalls = roomWalls.filter((w) => w.color === WALL_COLOR);
  const windows = roomWalls.filter((w) => w.color !== WALL_COLOR);

  // Slim architectural walls — the reference uses thin black lines, not bold blobs.
  const wallW = Math.max(1.5, Math.min(bw, bh) * 0.006);

  return (
    <svg
      className="section2d"
      viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`Exact 2D layout of ${room.label}`}
    >
      {/* Warm floor tone (reference is a printed colour plan, not line art) */}
      <rect x={vb.x} y={vb.y} width={vb.w} height={vb.h} fill="#f6f2e8" />

      {/* Furniture — coloured top-down symbols at exact position / size / rotation */}
      {room.furniture.map((f) => {
        const url = iconUrlForItem(f.item_id);
        const x = f.cx - f.w / 2;
        const y = f.cy - f.h / 2;
        const style = furnitureStyle(f.item_id, f.name);
        const r = Math.min(f.w, f.h) * 0.08;
        return (
          <g key={f.uid} transform={`rotate(${f.rotation} ${f.cx} ${f.cy})`}>
            {style && (
              <rect
                x={x}
                y={y}
                width={f.w}
                height={f.h}
                rx={r}
                ry={r}
                fill={style.fill}
                stroke={style.stroke}
                strokeWidth={Math.max(1.5, wallW * 0.35)}
              />
            )}
            {/* Bed pillows at the head edge */}
            {style?.kind === 'bed' && (
              <>
                <rect x={x + f.w * 0.08} y={y + f.h * 0.06} width={f.w * 0.38} height={f.h * 0.2} rx={r * 0.8} fill="#e7cccc" stroke="#c9a9a9" strokeWidth={1} />
                <rect x={x + f.w * 0.54} y={y + f.h * 0.06} width={f.w * 0.38} height={f.h * 0.2} rx={r * 0.8} fill="#e7cccc" stroke="#c9a9a9" strokeWidth={1} />
              </>
            )}
            {/* Line-art icon overlaid for recognisable detail (hidden if missing) */}
            {url && (
              <image
                className="section2d__icon"
                href={url}
                x={x}
                y={y}
                width={f.w}
                height={f.h}
                preserveAspectRatio="none"
                opacity={0.85}
              />
            )}
          </g>
        );
      })}

      {/* Structural walls — slim black architectural lines */}
      {structuralWalls.map(({ seg: [x1, y1, x2, y2] }, i) => (
        <line
          key={`w${i}`}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke={WALL_COLOR}
          strokeWidth={wallW}
          strokeLinecap="square"
        />
      ))}

      {/* Windows / drafter-coloured features — drawn on top in their own colour,
          a touch heavier so the opening reads clearly against the wall. */}
      {windows.map(({ seg: [x1, y1, x2, y2], color }, i) => (
        <line
          key={`win${i}`}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke={color}
          strokeWidth={wallW * 1.5}
          strokeLinecap="butt"
        />
      ))}
    </svg>
  );
}
