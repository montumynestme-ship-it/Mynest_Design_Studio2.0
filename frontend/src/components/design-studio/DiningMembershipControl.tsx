import type { PlacedItem } from '../../types/design';
import {
  ROOM_MEMBERSHIP_LABELS,
  ROOM_MEMBERSHIP_VALUES,
  isDiningItem,
  normalizeMembership,
  type MembershipReviewState,
  type RoomMembership,
} from '../../lib/roomMembership';

export type MembershipSaveStatus = 'idle' | 'saving' | 'saved' | 'error';

interface Props {
  /** The currently-selected placed item, or null. */
  selected: PlacedItem | null;
  /** Persist a new membership (undefined clears it). Caller saves + versions. */
  onChange: (uid: string, membership: RoomMembership | undefined) => void;
  /** Reflects the real save state so we never imply persistence before it succeeds. */
  saveStatus?: MembershipSaveStatus;
  /** The backend's live review state for this item (derived from /room-eligibility). */
  reviewState?: MembershipReviewState;
  /** The backend review/resolution reason, when available. */
  reviewReason?: string | null;
}

/**
 * AIR-03 editor control: assign an open-plan Dining item to one authoritative group.
 * Renders ONLY for a selected Dining item. Grouping metadata only — it never moves
 * furniture. The selection is not shown as persisted until the save succeeds.
 */
export default function DiningMembershipControl({
  selected,
  onChange,
  saveStatus = 'idle',
  reviewState,
  reviewReason,
}: Props) {
  if (!selected || !isDiningItem(selected.item.id)) return null;

  const current = normalizeMembership(selected.room_membership);

  const statusText =
    saveStatus === 'saving'
      ? 'Saving…'
      : saveStatus === 'error'
        ? 'Not saved — try again'
        : saveStatus === 'saved'
          ? 'Saved'
          : current
            ? 'Assigned'
            : 'Needs assignment';

  // The live backend verdict (stale-safe: 'unsaved' while a change hasn't been
  // re-evaluated; 'loading'/'error' when eligibility isn't available).
  const reviewText: string | null =
    reviewState === 'loading'
      ? 'Checking membership…'
      : reviewState === 'error'
        ? 'Could not check membership right now.'
        : reviewState === 'unsaved'
          ? 'Not yet saved/checked — AI Render stays blocked until this is confirmed.'
          : reviewState === 'review-required'
            ? `Review needed${reviewReason ? `: ${reviewReason}` : ''}. AI Render is blocked for this grouping until resolved.`
            : reviewState === 'resolved'
              ? 'Confirmed — this grouping is valid for AI Render.'
              : null;
  const reviewTone =
    reviewState === 'review-required' || reviewState === 'unsaved'
      ? 'var(--warn, #b45309)'
      : reviewState === 'error'
        ? 'var(--warn, #b45309)'
        : 'inherit';

  return (
    <div
      className="dining-membership"
      role="group"
      aria-label="Dining room membership"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        padding: '8px 10px',
        borderRadius: 8,
        background: 'var(--surface-2, rgba(0,0,0,0.04))',
        fontSize: 13,
      }}
    >
      <label htmlFor="dining-membership-select" style={{ fontWeight: 600 }}>
        Dining belongs to
      </label>
      <select
        id="dining-membership-select"
        value={current ?? ''}
        onChange={(e) => {
          const v = e.target.value;
          onChange(selected.uid, v === '' ? undefined : (v as RoomMembership));
        }}
      >
        <option value="">Not set (needs assignment)</option>
        {ROOM_MEMBERSHIP_VALUES.map((v) => (
          <option key={v} value={v}>
            {ROOM_MEMBERSHIP_LABELS[v]}
          </option>
        ))}
      </select>
      <span className="dining-membership__status" aria-live="polite" style={{ opacity: 0.8 }}>
        {statusText}
      </span>
      {reviewText ? (
        <span
          className="dining-membership__review"
          role={reviewState === 'review-required' ? 'alert' : 'status'}
          aria-live="polite"
          style={{ color: reviewTone }}
        >
          {reviewText}
        </span>
      ) : !current ? (
        <span style={{ opacity: 0.7 }}>
          Open-plan Dining must be assigned before AI Render. This only changes grouping — it never
          moves your furniture.
        </span>
      ) : null}
    </div>
  );
}
