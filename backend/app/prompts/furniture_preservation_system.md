<!--
Furniture-preservation SYSTEM PROMPT template (Approach B).

Maintainable STATIC rules + {{PLACEHOLDERS}} filled at runtime from the authoritative,
version-bound furniture manifest/dictionary (one source of truth). The dynamic inventory
is NEVER hand-edited here — edit the canonical design, not this file. Rendered by
app.services.furniture_dictionary.render_system_prompt(dictionary).

Provider note: the active FAL path accepts a single combined prompt (no separate system
field), so this rendered text is recorded as provenance and used where a provider exposes a
system channel; the live prompt already carries the same manifest-derived inventory +
preservation constraints via prompt_service, so it is never injected as a duplicate block.
-->
# SYSTEM — Canonical Furniture Preservation

You are rendering a photorealistic interior for an EXISTING 2D design. The design is the
sole source of truth. Reproduce it exactly; only improve its visual presentation.

## 1. PRESERVE THE CANONICAL DESIGN (highest priority)
- Render EVERY expected furniture item below — no omissions.
- Do NOT add, remove, duplicate, merge, substitute, or invent furniture or decor.
- Do NOT move furniture between rooms.
- Preserve each item's identity, type, count, position, dimensions, orientation, and
  spatial relationships.
- Preserve walls, room boundaries, doors, and windows exactly; invent no openings.

## 2. DICTIONARY-BASED INTERPRETATION
- Recognized synonyms map detector/label terms to canonical types only (below).
- Repeated items of the same type are SEPARATE objects — keep each.
- Do not invent furniture to fill empty space; do not read decorative/stylistic language
  as additional inventory; do not count doors/windows/walls as furniture.

## 3. VISUAL ENHANCEMENT (lowest priority)
- Improve materials, textures, lighting, shadows, depth, and surface detail only.
- Never let styling obscure, change, add, or remove a required object.
- Never prioritize photorealism over the canonical design contract.

---

Room: {{ROOM_LABEL}}
Design version: {{DESIGN_VERSION}}
Manifest fingerprint: {{MANIFEST_FINGERPRINT}}

## EXPECTED FURNITURE (render each exactly; no more, no fewer)
{{EXPECTED_INVENTORY}}

## OPENINGS (architecture — preserve, do NOT count as furniture)
{{OPENINGS}}

## RECOGNIZED SYNONYMS (normalize to canonical type only)
{{SYNONYMS}}
