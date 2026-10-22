"""Phase 4C Step 1A — deterministic Kitchen scene inventory (drift-proof).

Proves that deterministic 3D scene construction (``scene_service.build_scene``) represents
EXACTLY the canonical furniture inventory and can NEVER introduce a non-canonical object
(e.g. the washing machine seen in a Kitchen AI render). The evidence is canonical data +
scene structures — never image pixels.

Isolation from mutable live design data: the furniture is a SYNTHETIC canonical passed via
``build_scene(FID, canonical=...)``, so the assertions do not depend on the live plan's
furniture counts (which drift when the plan is edited). Only the immutable PDF walls come
from ``FID``. This mirrors the existing production path (``build_scene`` reads furniture
from the passed canonical, architectural geometry from the immutable floor-plan file).

Confirmed context: the washing machine in the reported Kitchen AI render is NOT canonical
and NOT produced by deterministic scene construction; it is introduced at the AI generation
stage (separate, approval-gated finding — not changed here).
"""

from collections import Counter

from app.services import scene_service

# Immutable floor-plan file id — used ONLY for architectural walls; furniture is overridden.
FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"

# Synthetic, controlled Kitchen canonical: two DISTINCT kitchen-base units + one chimney.
def _item(uid, item_id, name, cx, cy, w, h):
    return {"uid": uid, "item_id": item_id, "name": name,
            "cx": cx, "cy": cy, "w": w, "h": h, "rotation": 0}


KITCHEN_CANONICAL = {
    "furniture": [
        _item("kb-A", "kitchen-base", "Kitchen Base", 1100, 300, 120, 60),
        _item("kb-B", "kitchen-base", "Kitchen Base", 1250, 300, 120, 60),
        _item("chim-A", "chimney", "Chimney", 1180, 260, 80, 40),
    ]
}

_APPLIANCE_TOKENS = ("wash", "washer", "dryer", "laundry", "fridge", "refriger",
                     "microwave", "oven", "stove", "dishwasher")


def _scene_items(canonical):
    scene = scene_service.build_scene(FID, canonical=canonical)
    return [f for r in scene.get("rooms", []) for f in r.get("furniture", [])]


def test_scene_represents_exactly_the_canonical_kitchen_inventory():
    items = _scene_items(KITCHEN_CANONICAL)
    uids = sorted(str(f["uid"]) for f in items)
    types = Counter(str(f["item_id"]) for f in items)
    # Exactly the 3 canonical objects — none dropped, duplicated, or invented.
    assert uids == ["chim-A", "kb-A", "kb-B"]
    # Two DISTINCT kitchen-base objects + one chimney.
    assert types == {"kitchen-base": 2, "chimney": 1}
    assert len({f["uid"] for f in items if f["item_id"] == "kitchen-base"}) == 2


def test_deterministic_scene_never_introduces_a_washing_machine_or_appliances():
    # The canonical has NO washing machine (or any appliance) -> the deterministic scene
    # must contain none. The hallucinated washer in the AI render is NOT from this stage.
    items = _scene_items(KITCHEN_CANONICAL)
    bad = [f["item_id"] for f in items
           if any(tok in f"{f['item_id']} {f.get('name','')}".lower() for tok in _APPLIANCE_TOKENS)]
    assert bad == [], f"deterministic scene introduced non-canonical appliance(s): {bad}"


def test_scene_reflects_canonical_exactly_when_a_washer_IS_present():
    # Guard-the-guard: the scene faithfully represents whatever IS in canonical. With a real
    # washing-machine canonical item it appears; without it (the real Kitchen) it does not —
    # proving the scene builder reflects canonical and never fabricates.
    with_washer = {"furniture": KITCHEN_CANONICAL["furniture"] + [
        _item("wm-1", "washing-machine", "Washing Machine", 1000, 400, 60, 60),
    ]}
    ids = [str(f["item_id"]) for f in _scene_items(with_washer)]
    assert "washing-machine" in ids
    assert Counter(ids) == {"kitchen-base": 2, "chimney": 1, "washing-machine": 1}
    # Control: without it in canonical, it is absent.
    assert "washing-machine" not in [str(f["item_id"]) for f in _scene_items(KITCHEN_CANONICAL)]


def test_inventory_assertion_is_independent_of_live_design_counts():
    # The assertions use the SYNTHETIC canonical (3 items), not the live plan's count, so a
    # future edit to the live plan cannot drift this test.
    assert len(KITCHEN_CANONICAL["furniture"]) == 3
    assert len(_scene_items(KITCHEN_CANONICAL)) == 3
