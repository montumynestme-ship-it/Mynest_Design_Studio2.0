/**
 * Regression tests for the HONEST AI geometry-fidelity presentation contract.
 *
 * These lock the pure functions that drive GenerationGallery's fidelity badges, so a
 * refactor can never silently turn a missing / unknown / legacy / technical-success
 * signal into a positive "Faithful" verdict. Component (DOM) rendering is NOT covered
 * here — the project has no jsdom/testing-library infrastructure and this task may not
 * add dependencies — but these functions are exactly what the gallery consumes:
 *   - `resolveAiGeometryStatus`  → the "AI furniture fidelity" badge (Faithful/Failed/Not Verified)
 *   - `aiOutputFidelityTitle`    → that badge's honest tooltip
 *   - `isLowFidelityRestyle`     → the postgen "Low restyle fidelity" warning (never a faithful claim)
 *   - `isBaseInventoryMismatch` / `buildInventoryBadge` → the base-inventory warning (never an output verdict)
 */
import { describe, it, expect } from 'vitest';
import {
  resolveAiGeometryStatus,
  aiOutputFidelityTitle,
  isLowFidelityRestyle,
  isBaseInventoryMismatch,
  buildInventoryBadge,
  AI_OUTPUT_INVENTORY_ADVISORY,
  type AiGeometryStatus,
} from './generations';

describe('resolveAiGeometryStatus — honest three-state mapping', () => {
  // Explicit backend status is authoritative.
  it('returns FAITHFUL only on an explicit FAITHFUL status', () => {
    expect(resolveAiGeometryStatus('FAITHFUL', true)).toBe('FAITHFUL');
  });
  it('an explicit FAITHFUL status wins even if the legacy flag is false', () => {
    expect(resolveAiGeometryStatus('FAITHFUL', false)).toBe('FAITHFUL'); // status is authoritative
  });
  it('returns UNVERIFIED for an explicit UNVERIFIED status', () => {
    expect(resolveAiGeometryStatus('UNVERIFIED', null)).toBe('UNVERIFIED');
  });
  it('returns FAIL for an explicit FAIL status', () => {
    expect(resolveAiGeometryStatus('FAIL', null)).toBe('FAIL');
  });

  // Missing / null / unknown status must never become verified.
  it('missing geometry_status (undefined) → UNVERIFIED', () => {
    expect(resolveAiGeometryStatus(undefined, undefined)).toBe('UNVERIFIED');
  });
  it('null geometry_status → UNVERIFIED', () => {
    expect(resolveAiGeometryStatus(null, undefined)).toBe('UNVERIFIED');
  });
  it('an unknown/unrecognised status string → UNVERIFIED (never verified)', () => {
    expect(resolveAiGeometryStatus('TOTALLY_FAITHFUL_TRUST_ME', true)).toBe('UNVERIFIED');
    expect(resolveAiGeometryStatus('ok', true)).toBe('UNVERIFIED');
  });

  // Legacy flag (no explicit status) — the flag predates the evidence-driven split.
  it('legacy geometry_faithful=true WITHOUT status → UNVERIFIED (input validity ≠ output fidelity)', () => {
    expect(resolveAiGeometryStatus(undefined, true)).toBe('UNVERIFIED');
    expect(resolveAiGeometryStatus(null, true)).toBe('UNVERIFIED');
  });
  it('legacy geometry_faithful=false WITHOUT status → FAIL', () => {
    expect(resolveAiGeometryStatus(undefined, false)).toBe('FAIL');
  });
  it('both fields missing → UNVERIFIED', () => {
    expect(resolveAiGeometryStatus(null, null)).toBe('UNVERIFIED');
  });
  it('empty-string status falls back to the legacy flag path (not treated as verified)', () => {
    expect(resolveAiGeometryStatus('', true)).toBe('UNVERIFIED');
    expect(resolveAiGeometryStatus('', false)).toBe('FAIL');
    expect(resolveAiGeometryStatus('', undefined)).toBe('UNVERIFIED');
  });

  // Contract guard: NO non-FAITHFUL-status input can ever resolve to FAITHFUL.
  it('only an explicit FAITHFUL status can ever yield FAITHFUL', () => {
    const statuses: Array<string | null | undefined> = [undefined, null, '', 'UNVERIFIED', 'FAIL', 'weird', 'faithful'];
    const flags: Array<boolean | null | undefined> = [undefined, null, true, false];
    for (const s of statuses) {
      for (const f of flags) {
        expect(resolveAiGeometryStatus(s, f)).not.toBe('FAITHFUL');
      }
    }
    expect(resolveAiGeometryStatus('FAITHFUL', undefined)).toBe('FAITHFUL');
  });
});

describe('aiOutputFidelityTitle — honest tooltip', () => {
  it('FAITHFUL confirms an output check and carries no "not verified" advisory', () => {
    const t = aiOutputFidelityTitle('FAITHFUL');
    expect(t).toMatch(/confirmed/i);
    expect(t).not.toContain(AI_OUTPUT_INVENTORY_ADVISORY);
  });
  it('UNVERIFIED states "NOT verified" and includes the inventory-drift advisory', () => {
    const t = aiOutputFidelityTitle('UNVERIFIED');
    expect(t).toMatch(/not verified/i);
    expect(t).toContain(AI_OUTPUT_INVENTORY_ADVISORY);
  });
  it('FAIL states the check failed and includes the inventory-drift advisory', () => {
    const t = aiOutputFidelityTitle('FAIL');
    expect(t).toMatch(/failed/i);
    expect(t).toContain(AI_OUTPUT_INVENTORY_ADVISORY);
  });
  it('the advisory tells the user to trust the deterministic 2D layout', () => {
    expect(AI_OUTPUT_INVENTORY_ADVISORY).toMatch(/not a verified inventory/i);
    expect(AI_OUTPUT_INVENTORY_ADVISORY).toMatch(/deterministic 2D layout/i);
  });
});

describe('technical success is NOT geometry fidelity', () => {
  // postgen_status=OK (or unknown) must NOT raise the low-fidelity warning, and is never
  // a positive fidelity claim — it is image-similarity only.
  it('postgen_status=OK does not flag a low-fidelity restyle (and is not a fidelity verdict)', () => {
    expect(isLowFidelityRestyle('OK')).toBe(false);
    expect(isLowFidelityRestyle(null)).toBe(false);
    expect(isLowFidelityRestyle(undefined)).toBe(false);
    expect(isLowFidelityRestyle('SOMETHING_ELSE')).toBe(false);
  });
  it('only LOW_FIDELITY raises the restyle warning', () => {
    expect(isLowFidelityRestyle('LOW_FIDELITY')).toBe(true);
  });
});

describe('base inventory status is NOT output-inventory fidelity', () => {
  it('inventory MATCH produces no badge (does not verify the generated image)', () => {
    expect(isBaseInventoryMismatch('MATCH')).toBe(false);
    expect(buildInventoryBadge({ inventory_status: 'MATCH', inventory_reason: null })).toBeNull();
  });
  it('NOT_ASSESSABLE / unknown / null produce no badge', () => {
    expect(buildInventoryBadge({ inventory_status: 'NOT_ASSESSABLE', inventory_reason: null })).toBeNull();
    expect(buildInventoryBadge({ inventory_status: null, inventory_reason: null })).toBeNull();
    expect(buildInventoryBadge(null)).toBeNull();
  });
  it('only an explicit MISMATCH yields a warn badge, with missing types when present', () => {
    expect(isBaseInventoryMismatch('MISMATCH')).toBe(true);
    const badge = buildInventoryBadge({
      inventory_status: 'MISMATCH',
      inventory_reason: { missing_types: ['Dining Table'] },
    });
    expect(badge).not.toBeNull();
    expect(badge!.tone).toBe('warn');
    expect(badge!.label).toMatch(/Dining Table/);
  });
});

// Type-level guard: the resolver's return type is the closed honest union.
const _typeGuard: AiGeometryStatus = resolveAiGeometryStatus('UNVERIFIED', null);
void _typeGuard;
