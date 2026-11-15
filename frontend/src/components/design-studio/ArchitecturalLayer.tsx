import { Group, Layer, Line, Rect, Text } from 'react-konva';
import type { ArchitecturalView } from '../../lib/architecturalView';

/**
 * Phase 1 — additive, READ-ONLY 2D architectural overlay.
 *
 * Draws the extracted empty-plan architecture (walls, room boundaries + labels, door /
 * window opening placements) from existing `/scene` data, in WORLD PX, inside the canvas
 * Stage transform — so it stays aligned with the plan image and furniture at any zoom/pan
 * with NO extra scale factor. The layer is non-interactive (`listening={false}`): pointer
 * events fall through to the furniture layer below, so selection/drag/rotate are untouched.
 * It renders whether or not furniture exists. Nothing here edits geometry (CLAUDE.md RULE #1).
 *
 * Verified vs. uncertain is shown honestly:
 *  - Rooms: CONFIRMED (wall-proven) = solid blue; UNCERTAIN fallback = dashed amber.
 *  - Openings: verified (on its real wall) = solid, door green / window blue;
 *    unverified (authored position, needs review) = dashed amber outline.
 *
 * `scale` is the Stage zoom; stroke widths and font sizes are divided by it so they stay a
 * constant size on screen (the same technique the furniture layer uses).
 */
interface Props {
  view: ArchitecturalView;
  scale: number;
}

const WALL = '#111827';
const ROOM_OK = '#2563eb';
const ROOM_UNSURE = '#d97706';
const DOOR_OK = '#15803d';
const WIN_OK = '#0369a1';
const REVIEW = '#ea580c';

export default function ArchitecturalLayer({ view, scale }: Props) {
  const s = scale > 0 ? scale : 1;
  const px = (n: number) => n / s; // constant on-screen size regardless of zoom
  const fs = px(13);

  return (
    <Layer listening={false}>
      {/* Room boundary polygons (drawn first, under walls/openings). */}
      {view.rooms.map((r) => {
        const flat = r.points.flatMap(([x, y]) => [x, y]);
        const color = r.confirmed ? ROOM_OK : ROOM_UNSURE;
        return (
          <Line
            key={`room-${r.id}`}
            points={flat}
            closed
            stroke={color}
            strokeWidth={px(2)}
            dash={r.confirmed ? undefined : [px(9), px(6)]}
            fill={r.confirmed ? 'rgba(37,99,235,0.06)' : 'rgba(217,119,6,0.05)'}
          />
        );
      })}

      {/* Extracted wall face strokes — each segment exactly as extracted (never merged). */}
      {view.walls.map((w, i) => (
        <Line
          key={`wall-${i}`}
          points={[w.x1, w.y1, w.x2, w.y2]}
          stroke={WALL}
          strokeWidth={px(3)}
          lineCap="round"
        />
      ))}

      {/* Door / window opening placements, rotated about their centre (same convention as
          furniture). Verified = solid; unverified (needs review) = dashed amber. */}
      {view.openings.map((o) => {
        const verifiedStroke = o.kind === 'door' ? DOOR_OK : WIN_OK;
        const stroke = o.verified ? verifiedStroke : REVIEW;
        const fill = o.verified
          ? o.kind === 'door'
            ? 'rgba(22,163,74,0.40)'
            : 'rgba(2,132,199,0.40)'
          : 'rgba(234,88,12,0.28)';
        return (
          <Group key={`op-${o.id}`} x={o.cx} y={o.cy} offsetX={o.w / 2} offsetY={o.h / 2} rotation={o.rotation}>
            <Rect
              width={o.w}
              height={o.h}
              fill={fill}
              stroke={stroke}
              strokeWidth={px(1.5)}
              dash={o.verified ? undefined : [px(5), px(4)]}
            />
          </Group>
        );
      })}

      {/* Room labels (only when a valid label exists), roughly centred on the polygon. */}
      {view.rooms.map((r) =>
        r.label && r.labelAt ? (
          <Text
            key={`label-${r.id}`}
            x={r.labelAt[0]}
            y={r.labelAt[1]}
            text={r.confirmed ? r.label : `${r.label} (uncertain)`}
            fontSize={fs}
            fontStyle="600"
            fill={r.confirmed ? '#1e3a8a' : '#92400e'}
            offsetX={(r.confirmed ? r.label.length : r.label.length + 12) * fs * 0.27}
            offsetY={fs * 0.5}
          />
        ) : null,
      )}
    </Layer>
  );
}
