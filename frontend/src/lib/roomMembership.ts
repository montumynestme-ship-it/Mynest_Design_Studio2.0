/**
 * AIR-03 — authoritative room-membership values for open-plan Dining furniture.
 *
 * These strings must match the backend contract EXACTLY
 * (`room_membership_service.VALID_MEMBERSHIPS`: KITCHEN / LIVING_AREA /
 * INDEPENDENT_DINING). This is grouping metadata only — it never moves furniture or
 * changes any canonical transform, and it is distinct from the styling-only room-tag.
 */
export const ROOM_MEMBERSHIP = {
  KITCHEN: 'KITCHEN',
  LIVING_AREA: 'LIVING_AREA',
  INDEPENDENT_DINING: 'INDEPENDENT_DINING',
} as const;

export type RoomMembership = (typeof ROOM_MEMBERSHIP)[keyof typeof ROOM_MEMBERSHIP];

export const ROOM_MEMBERSHIP_VALUES: readonly RoomMembership[] = [
  ROOM_MEMBERSHIP.KITCHEN,
  ROOM_MEMBERSHIP.LIVING_AREA,
  ROOM_MEMBERSHIP.INDEPENDENT_DINING,
];

/** Human-readable option labels for the editor control. */
export const ROOM_MEMBERSHIP_LABELS: Record<RoomMembership, string> = {
  KITCHEN: 'Part of Kitchen',
  LIVING_AREA: 'Part of Living Area',
  INDEPENDENT_DINING: 'Separate Dining room',
};

/** Catalog item ids that can carry a Dining membership (matches backend _DINING_SEEDS). */
export const DINING_ITEM_IDS: ReadonlySet<string> = new Set(['dining-table']);

export function isDiningItem(itemId: string | null | undefined): boolean {
  return !!itemId && DINING_ITEM_IDS.has(itemId);
}

/** True only for an exact supported value (never coerces an unknown string to valid). */
export function isValidMembership(value: string | null | undefined): value is RoomMembership {
  return !!value && (ROOM_MEMBERSHIP_VALUES as readonly string[]).includes(value);
}

/** The membership to display for an item: a valid stored value, else null (unset). */
export function normalizeMembership(value: string | null | undefined): RoomMembership | null {
  return isValidMembership(value) ? value : null;
}

/** Minimal shape of a backend membership decision (see floorPlans.MembershipDecision). */
export interface MembershipDecisionLike {
  uid: string | null;
  membership: string | null;
  status: string;
  reason: string;
}

/** The backend decision for a specific item uid, or null when none applies. */
export function membershipDecisionFor(
  decisions: readonly MembershipDecisionLike[] | null | undefined,
  uid: string | null | undefined,
): MembershipDecisionLike | null {
  if (!uid) return null;
  return (decisions ?? []).find((d) => d.uid === uid) ?? null;
}

export type MembershipReviewState =
  | 'loading'
  | 'error'
  | 'unsaved'
  | 'review-required'
  | 'resolved'
  | 'unset';

/**
 * Derive the display state for the editor. Crucially, if the locally-selected value does
 * not match the value the backend last evaluated, the decision is treated as STALE and
 * reported as 'unsaved' — never presenting an out-of-date verdict as current.
 */
export function deriveReviewState(opts: {
  loading?: boolean;
  error?: boolean;
  localMembership: string | null | undefined;
  decision: MembershipDecisionLike | null;
}): MembershipReviewState {
  if (opts.loading) return 'loading';
  if (opts.error) return 'error';
  const local = normalizeMembership(opts.localMembership);
  const backend = opts.decision ? normalizeMembership(opts.decision.membership) : null;
  if (local !== backend) return 'unsaved'; // local change not yet saved+re-evaluated
  if (!opts.decision) return local ? 'unsaved' : 'unset';
  if (opts.decision.status === 'REVIEW_REQUIRED') return 'review-required';
  if (opts.decision.status === 'RESOLVED') return 'resolved';
  return 'unset';
}
