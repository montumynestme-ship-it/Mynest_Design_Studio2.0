import { test, expect } from '@playwright/test';
import {
  AI_OUTPUT_INVENTORY_ADVISORY,
  aiOutputFidelityTitle,
} from '../src/lib/generations';

// AIR-01/AIR-12 (Option C — honest surfacing only): the "AI furniture fidelity" badge
// tooltip must explicitly warn that a non-faithful render may ADD/alter décor not in the
// canonical design. This is surface copy only — it changes no generation/provider/gate.

test('advisory names the inventory-drift limitation explicitly', () => {
  expect(AI_OUTPUT_INVENTORY_ADVISORY).toContain('add');
  expect(AI_OUTPUT_INVENTORY_ADVISORY).toContain('NOT in your canonical');
  expect(AI_OUTPUT_INVENTORY_ADVISORY).toContain('NOT a verified inventory');
});

test('UNVERIFIED tooltip carries the inventory-drift advisory', () => {
  const title = aiOutputFidelityTitle('UNVERIFIED');
  expect(title).toContain('NOT verified');
  expect(title).toContain(AI_OUTPUT_INVENTORY_ADVISORY);
});

test('FAIL tooltip also carries the advisory (never faithful)', () => {
  expect(aiOutputFidelityTitle('FAIL')).toContain(AI_OUTPUT_INVENTORY_ADVISORY);
});

test('FAITHFUL tooltip does NOT include the drift advisory', () => {
  const title = aiOutputFidelityTitle('FAITHFUL');
  expect(title).not.toContain(AI_OUTPUT_INVENTORY_ADVISORY);
  expect(title).toContain('confirmed');
});
