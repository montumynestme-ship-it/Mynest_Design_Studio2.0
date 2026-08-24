"""Geometry-fidelity tests for the prompt layer (spec Phase 22).

These prove the canonical scene is carried into the renderer input *correctly* —
exact furniture counts and per-item positions/rotations reach the prompt. Any
mismatch in the final image is therefore the text-to-image renderer's limitation
(it cannot obey counts/coordinates), NOT a coordinate-loss bug in our pipeline.
"""

from app.services import prompt_service


def _f(uid: str, item: str, cx: int, cy: int, w: int, h: int, rot: int = 0) -> dict:
    return {"uid": uid, "item_id": item, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


def _kitchen_canonical() -> dict:
    # 1 dining table + exactly 4 dining chairs + a wardrobe rotated 90°.
    return {
        "furniture": [
            _f("t", "dining-table", 1000, 800, 120, 220),
            _f("c1", "dining-chair", 900, 700, 60, 60),
            _f("c2", "dining-chair", 1100, 700, 60, 60),
            _f("c3", "dining-chair", 900, 900, 60, 60),
            _f("c4", "dining-chair", 1100, 900, 60, 60),
            _f("w", "wardrobe", 1200, 650, 90, 350, 90),
        ]
    }


def test_dining_chair_count_preserved_in_prompt() -> None:
    """Phase 22 TEST 1: 4 chairs in → prompt must say '4x Dining Chair', never 6x."""
    _, rooms = prompt_service.build_room_prompts(_kitchen_canonical(), {"style": "Modern"})
    prompt = next(p for label, p, _w, _h in rooms if "Dining Chair" in p)
    assert "4x Dining Chair" in prompt
    assert "6x Dining Chair" not in prompt
    assert "5x Dining Chair" not in prompt


def test_wardrobe_rotation_described() -> None:
    """Phase 22 TEST 6: a 90° wardrobe must be described as rotated in the prompt."""
    _, rooms = prompt_service.build_room_prompts(_kitchen_canonical(), None)
    prompt = next(p for label, p, _w, _h in rooms if "Wardrobe" in p)
    assert "90" in prompt


def test_strict_inventory_constraint_present() -> None:
    """Phase 5/6: the non-negotiable 'only these, no extras/omissions' rule is injected."""
    _, rooms = prompt_service.build_room_prompts(_kitchen_canonical(), None)
    prompt = rooms[0][1]
    assert "STRICT INVENTORY" in prompt
    assert "Do NOT omit" in prompt


def test_piece_appearance_descriptors_present_and_deduped() -> None:
    """Each distinct item type gets one appearance descriptor so the text-to-image
    model renders recognizable objects — deduped (4 chairs -> one description line)."""
    _, rooms = prompt_service.build_room_prompts(_kitchen_canonical(), None)
    prompt = next(p for _label, p, _w, _h in rooms if "Dining Chair" in p)
    assert "PIECE APPEARANCE" in prompt
    assert "upholstered dining chair" in prompt
    # deduped: the descriptor line for the chair appears exactly once despite 4 chairs
    assert prompt.count("upholstered dining chair with a backrest") == 1
