"""Step 2S — fal edit-prompt preservation (offline, no external calls, no DB).

Locks the strengthened preservation prompt: the effective prompt leads with the exact
canonical inventory ("exactly once … no extra/duplicate/missing/substituted/invented
furniture, appliances, or decor"), carries the structural-preservation preamble and the
decor/accessory prohibition, keeps the user theme styling-only with the negatives LAST,
and never drops a mandatory constraint under truncation.
"""
from __future__ import annotations

import pytest

from app.services.ai import fal_flux_adapter as FA
from app.services.ai.base import AIProviderError

ROOM_PROMPT = (
    "Photorealistic render of a Kitchen that contains exactly: 2 Kitchen Base, 1 Chimney. "
    "USER THEME (styling only): warm minimalist with walnut cabinetry and marble tops."
)


def test_effective_prompt_leads_with_exact_inventory_and_forbids_decor():
    p = FA._build_fal_edit_prompt(ROOM_PROMPT)
    assert "ROOM: Kitchen." in p
    # inventory lead: exactly once, and forbids invented furniture/appliances/DECOR
    assert "EXACT EXISTING INVENTORY" in p
    assert "exactly once" in p
    assert "no extra, duplicate, missing, substituted, or invented furniture, appliances, or decor" in p
    assert "2 Kitchen Base, 1 Chimney" in p
    # decor/accessory prohibition present in the structural preamble + negatives
    assert "decor/accessories" in p
    assert "plants, artwork, rugs, cushions" in p


def test_theme_is_styling_only_and_negatives_are_last():
    p = FA._build_fal_edit_prompt(ROOM_PROMPT)
    assert "warm minimalist with walnut cabinetry and marble tops" in p  # theme carried
    assert "styling only" in p
    # the authoritative negative block (with decor) must be the FINAL instruction
    assert p.rstrip().endswith("generic showroom staging.")
    # theme sits BEFORE the negatives (cannot override them)
    assert p.index("warm minimalist") < p.index("Do NOT add, remove, move, resize")


def test_mandatory_constraints_never_dropped_fails_safe_on_overflow():
    # A pathological huge inventory that alone exceeds the budget must FAIL SAFELY,
    # never silently drop the inventory/preservation/negative constraints.
    huge = "of a Living Area that contains exactly: " + ", ".join(
        f"Item {i}" for i in range(600)
    ) + "."
    with pytest.raises(AIProviderError) as ei:
        FA._build_fal_edit_prompt(huge, max_len=2200)
    assert "FAL_PROMPT_TOO_LONG" in str(ei.value)


def test_long_theme_cannot_push_out_mandatory_sections():
    # A very long theme is trimmed; the mandatory inventory + negatives survive intact.
    long_theme = " ".join(["ultra premium glossy"] * 400)
    rp = (f"render of a Bedroom 1 that contains exactly: 1 Bed, 2 Side Table, 1 Wardrobe. "
          f"USER THEME (styling only): {long_theme}")
    p = FA._build_fal_edit_prompt(rp, max_len=2200)
    assert "1 Bed, 2 Side Table, 1 Wardrobe" in p          # inventory intact
    assert "or invented furniture, appliances, or decor" in p  # inventory prohibition intact
    assert p.rstrip().endswith("generic showroom staging.")    # negatives intact + last
    assert len(p) <= 2200
