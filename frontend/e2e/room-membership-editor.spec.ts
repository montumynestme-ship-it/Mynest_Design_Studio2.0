import { test, expect } from '@playwright/test';
import {
  ROOM_MEMBERSHIP,
  ROOM_MEMBERSHIP_VALUES,
  ROOM_MEMBERSHIP_LABELS,
  isDiningItem,
  isValidMembership,
  normalizeMembership,
  membershipDecisionFor,
  deriveReviewState,
} from '../src/lib/roomMembership';

// AIR-03 editor membership contract — values must match the backend exactly and never
// coerce an unknown/unsaved value into a valid one.

test('membership values match the backend contract exactly', () => {
  expect([...ROOM_MEMBERSHIP_VALUES]).toEqual(['KITCHEN', 'LIVING_AREA', 'INDEPENDENT_DINING']);
  expect(ROOM_MEMBERSHIP.KITCHEN).toBe('KITCHEN');
  expect(ROOM_MEMBERSHIP.LIVING_AREA).toBe('LIVING_AREA');
  expect(ROOM_MEMBERSHIP.INDEPENDENT_DINING).toBe('INDEPENDENT_DINING');
  for (const v of ROOM_MEMBERSHIP_VALUES) expect(ROOM_MEMBERSHIP_LABELS[v]).toBeTruthy();
});

test('only dining items can carry a membership', () => {
  expect(isDiningItem('dining-table')).toBe(true);
  expect(isDiningItem('sofa-3')).toBe(false);
  expect(isDiningItem(undefined)).toBe(false);
  expect(isDiningItem(null)).toBe(false);
});

test('membership validation never coerces unknown/unset to valid', () => {
  expect(isValidMembership('KITCHEN')).toBe(true);
  expect(isValidMembership('GARAGE')).toBe(false);
  expect(isValidMembership('')).toBe(false);
  expect(isValidMembership(null)).toBe(false);
  expect(isValidMembership(undefined)).toBe(false);
});

test('normalizeMembership returns a valid value or null (never a bogus string)', () => {
  expect(normalizeMembership('LIVING_AREA')).toBe('LIVING_AREA');
  expect(normalizeMembership('nonsense')).toBeNull();
  expect(normalizeMembership(null)).toBeNull();
  expect(normalizeMembership(undefined)).toBeNull();
});

// Live review feedback helpers (Task B)
const DECISIONS = [
  { uid: 'dt-1', membership: 'KITCHEN', status: 'RESOLVED', reason: 'SUPPORTED: …' },
  { uid: 'dt-2', membership: 'INDEPENDENT_DINING', status: 'REVIEW_REQUIRED', reason: 'CONFLICT: …' },
];

test('membershipDecisionFor matches by uid', () => {
  expect(membershipDecisionFor(DECISIONS, 'dt-2')?.status).toBe('REVIEW_REQUIRED');
  expect(membershipDecisionFor(DECISIONS, 'missing')).toBeNull();
  expect(membershipDecisionFor(DECISIONS, null)).toBeNull();
  expect(membershipDecisionFor(null, 'dt-1')).toBeNull();
});

test('deriveReviewState reflects backend verdict and never shows stale', () => {
  // loading / error take precedence
  expect(deriveReviewState({ loading: true, localMembership: 'KITCHEN', decision: null })).toBe('loading');
  expect(deriveReviewState({ error: true, localMembership: 'KITCHEN', decision: null })).toBe('error');
  // resolved when local matches a RESOLVED decision
  expect(
    deriveReviewState({ localMembership: 'KITCHEN', decision: DECISIONS[0] }),
  ).toBe('resolved');
  // review-required when local matches a REVIEW_REQUIRED decision
  expect(
    deriveReviewState({ localMembership: 'INDEPENDENT_DINING', decision: DECISIONS[1] }),
  ).toBe('review-required');
  // STALE: local value changed but backend decision still reflects the old value -> unsaved
  expect(
    deriveReviewState({ localMembership: 'LIVING_AREA', decision: DECISIONS[0] }),
  ).toBe('unsaved');
  // unset: no local value and no decision
  expect(deriveReviewState({ localMembership: undefined, decision: null })).toBe('unset');
  // local set but no decision yet -> unsaved (not falsely resolved)
  expect(deriveReviewState({ localMembership: 'KITCHEN', decision: null })).toBe('unsaved');
});
