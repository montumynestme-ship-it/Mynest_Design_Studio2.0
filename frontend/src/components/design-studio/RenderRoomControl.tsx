import type { PlacedItem } from '../../types/design';
import { isDiningItem } from '../../lib/roomMembership';

/** AIR-03 Step 2M.1 explicit render-inclusion targets (anchor tokens resolved by the
 * backend to the unique CONFIRMED room carrying that anchor). */
export const RENDER_ROOM = {
  KITCHEN: 'KITCHEN',
  LIVING_AREA: 'LIVING_AREA',
} as const;
export type RenderRoom = (typeof RENDER_ROOM)[keyof typeof RENDER_ROOM];

const RENDER_ROOM_VALUES: readonly RenderRoom[] = [RENDER_ROOM.KITCHEN, RENDER_ROOM.LIVING_AREA];
const RENDER_ROOM_LABELS: Record<RenderRoom, string> = {
  KITCHEN: 'Render in Kitchen',
  LIVING_AREA: 'Render in Living Area',
};

/** Non-dining, non-opening, non-annotation furniture can carry an explicit render-inclusion
 * directive. Dining uses the separate DiningMembershipControl; openings/annotations never
 * carry one. */
function isAssignable(itemId: string | null | undefined): boolean {
  const id = String(itemId ?? '');
  if (!id) return false;
  if (isDiningItem(id)) return false;
  if (id.includes('door') || id.includes('window')) return false;
  if (id === 'room-tag') return false;
  return true;
}

function normalize(value: string | null | undefined): RenderRoom | null {
  return value && (RENDER_ROOM_VALUES as readonly string[]).includes(value)
    ? (value as RenderRoom)
    : null;
}

interface Props {
  /** The currently-selected placed item, or null. */
  selected: PlacedItem | null;
  /** Persist a new render-inclusion (undefined clears it). Caller saves + versions. */
  onChange: (uid: string, value: RenderRoom | undefined) => void;
}

/**
 * Explicit, auditable control to include a canonical NON-DINING item in a specific
 * CONFIRMED room's deterministic render even when its footprint lies outside that room's
 * floor polygon (e.g. a wall counter in an un-reconstructed alcove). Grouping/render
 * metadata only — it NEVER moves, resizes, rotates, or duplicates the item. Renders only
 * for an assignable selected item; the backend fails safe (REVIEW_REQUIRED, no move) when
 * the target is ambiguous or absent.
 */
export default function RenderRoomControl({ selected, onChange }: Props) {
  if (!selected || !isAssignable(selected.item.id)) return null;
  const current = normalize(selected.render_room);

  return (
    <div className="studio-membership" role="group" aria-label="Explicit render inclusion">
      <label className="studio-membership__label" htmlFor="render-room-select">
        Render this item in
      </label>
      <select
        id="render-room-select"
        className="studio-membership__select"
        value={current ?? ''}
        onChange={(e) => {
          const v = e.target.value;
          onChange(selected.uid, v === '' ? undefined : (v as RenderRoom));
        }}
      >
        <option value="">Automatic (by geometry)</option>
        {RENDER_ROOM_VALUES.map((v) => (
          <option key={v} value={v}>
            {RENDER_ROOM_LABELS[v]}
          </option>
        ))}
      </select>
      <p className="studio-membership__hint">
        {current
          ? 'Included in the room even if it sits outside its floor; a floor patch is drawn under it.'
          : 'Assigned automatically from the plan geometry.'}
      </p>
    </div>
  );
}
