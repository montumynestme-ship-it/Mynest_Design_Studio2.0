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


def test_canonical_sections_never_fabricate_furniture_when_empty() -> None:
    """all_sections=True must never invent furniture for a section with none placed.

    _kitchen_canonical() only has a dining table/chairs/wardrobe, which the
    anchor heuristic groups entirely under "Dining Area" — the other 5
    canonical sections have zero real furniture and must be skipped outright
    (no synthetic layout sent to the renderer), not filled in with
    `_default_items_for_section`.
    """
    _, rooms = prompt_service.build_room_prompts(_kitchen_canonical(), None, all_sections=True)
    labels = [lbl for lbl, _p, _w, _h in rooms]
    assert labels == ["Dining Area"]


def _two_adjacent_rooms_walls() -> list[dict]:
    """Two 1000x1000 closed rectangles sharing the wall at x=1000."""
    segments = [
        (0, 0, 1000, 0), (1000, 0, 2000, 0), (2000, 0, 2000, 1000),
        (2000, 1000, 1000, 1000), (1000, 1000, 0, 1000), (0, 1000, 0, 0),
        (1000, 0, 1000, 1000),
    ]
    return [
        {"id": f"wall_{i}", "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        for i, (x1, y1, x2, y2) in enumerate(segments)
    ]


def test_room_prompt_only_references_its_own_door_not_a_neighbours() -> None:
    """Each room's camera/geometry text must come from ITS OWN reconstructed
    doors, never the floor plan's global door list (previously every room's
    prompt was built from canonical["doors"] unfiltered, so a room could
    describe a neighbouring room's entrance)."""
    canonical = {
        "furniture": [
            _f("sofa", "lounger-sofa", 500, 500, 1200, 800),
            _f("bed", "bed", 1500, 500, 900, 1000),
        ],
        "structured_walls": _two_adjacent_rooms_walls(),
        "doors": [
            {"id": "door_living", "x": 500, "y": 950},  # south wall of Room A
            {"id": "door_bed", "x": 1500, "y": 50},      # north wall of Room B
        ],
        "windows": [],
    }
    _, rooms = prompt_service.build_room_prompts(canonical, {"style": "Modern"})
    by_label = {lbl: p for lbl, p, _w, _h in rooms}

    living_prompt = by_label["Living Area"]
    bedroom_prompt = by_label["Bedroom 1"]

    assert "South (front) entrance threshold" in living_prompt
    assert "North entrance threshold" not in living_prompt

    assert "North entrance threshold" in bedroom_prompt
    assert "South (front) entrance threshold" not in bedroom_prompt


def test_spatial_lines_state_measured_wall_distance_when_actually_adjacent() -> None:
    """An item genuinely flush against a real extracted wall gets an exact
    measured distance; a centrally-placed item gets no invented distance
    claim (it would be equally '500px from every wall' and thus meaningless)."""
    canonical = {
        "furniture": [
            _f("sofa", "lounger-sofa", 200, 500, 1200, 800),  # hard against the left wall
            _f("bed", "bed", 1500, 500, 900, 1000),  # centered, not against any one wall
        ],
        "structured_walls": _two_adjacent_rooms_walls(),
    }
    _, rooms = prompt_service.build_room_prompts(canonical, {"style": "Modern"})
    by_label = {lbl: p for lbl, p, _w, _h in rooms}

    assert "measured" in by_label["Living Area"]
    assert "mm from wall" in by_label["Living Area"]
    assert "measured" not in by_label["Bedroom 1"]


def test_bedroom_never_claims_a_wardrobe_but_forbids_adding_one() -> None:
    """A bedroom with no wardrobe must never describe one as present, but SHOULD
    explicitly forbid the model from adding one (the anti-hallucination negative)."""
    plan = {
        "furniture": [
            _f("bed", "bed", 500, 300, 1800, 2000),
            _f("st1", "side-table", 300, 300, 450, 450),
        ]
    }
    _, rooms = prompt_service.build_room_prompts(plan, None)
    prompt = rooms[0][1]
    assert "BEDROOM SPECIFICATION" in prompt
    assert "nightstand placement" in prompt
    # It must not CLAIM a wardrobe / dressing unit is present or to be preserved...
    assert "wardrobe placement" not in prompt
    assert "dressing unit placement" not in prompt
    # ...but it MUST forbid the model from adding one (anti-hallucination).
    assert "do NOT add a wardrobe" in prompt


def test_sofa_does_not_get_an_unverified_tv_facing_claim() -> None:
    """A sofa/TV pair with no geometric basis for 'facing' must not get that claim."""
    plan = {
        "furniture": [
            _f("sofa", "lounger-sofa", 500, 600, 1900, 900),
            _f("tv", "tv-unit", 500, 180, 1100, 350),
        ]
    }
    _, rooms = prompt_service.build_room_prompts(plan, None)
    prompt = rooms[0][1]
    assert "faces the TV" not in prompt


def test_window_position_and_modern_luxury_tokens_present() -> None:
    """Window wall position, sheer curtains, and modern luxury design tokens are injected."""
    plan = {
        "furniture": [
            _f("bed1", "bed", 500, 300, 1800, 2000),
            _f("win1", "window", 500, 800, 1500, 200),
        ]
    }
    _, rooms = prompt_service.build_room_prompts(plan, {"style": "Modern Luxury"})
    prompt = rooms[0][1]
    assert "WINDOW SPECIFICATION" in prompt
    assert "floor-to-ceiling sheer linen curtains" in prompt
    # Bedroom 1 -> cycling palette A (warm walnut): distinct, named finishes.
    assert "MATERIAL & LIGHTING PALETTE" in prompt
    assert "warm walnut headboard" in prompt
    assert "fluted oak paneling" in prompt
    assert "plush neutral beige carpet" in prompt


def _four_bedroom_plan() -> dict:
    # Four separate bedrooms, well spaced so the anchor heuristic keeps them distinct.
    return {
        "furniture": [
            _f("b1", "bed", 500, 500, 1800, 2000),
            _f("b2", "bed", 5000, 500, 1800, 2000),
            _f("b3", "bed", 500, 5000, 1800, 2000),
            _f("b4", "bed", 5000, 5000, 1800, 2000),
        ]
    }


def test_primary_inventory_is_front_loaded() -> None:
    """The exact furniture inventory must lead the prompt (first ~2 sentences)
    so the text-to-image condenser can never truncate it away."""
    _, rooms = prompt_service.build_room_prompts(_kitchen_canonical(), {"style": "Modern"})
    prompt = rooms[0][1]
    head = prompt[:200]
    assert "contains exactly:" in head
    assert "Dining Table" in head


def test_bedrooms_cycle_three_distinct_material_palettes() -> None:
    """Bedroom 1/2/3 must get palette A/B/C (no two adjacent bedrooms identical);
    Bedroom 4 cycles back to palette A."""
    _, rooms = prompt_service.build_room_prompts(_four_bedroom_plan(), None)
    by_label = {lbl: p for lbl, p, _w, _h in rooms}
    assert "Palette A (warm walnut)" in by_label["Bedroom 1"]
    assert "Palette B (light natural ash)" in by_label["Bedroom 2"]
    assert "Palette C (charcoal evening)" in by_label["Bedroom 3"]
    # 4th bedroom cycles back to A via (4-1) % 3 == 0
    assert "Palette A (warm walnut)" in by_label["Bedroom 4"]


def test_zero_window_room_uses_ambient_lighting_not_daylight() -> None:
    """A room with no reconstructed windows must be told to use ambient interior
    lighting rather than claiming window daylight."""
    plan = {
        "furniture": [
            _f("bed", "bed", 500, 500, 1800, 2000),
            _f("st", "side-table", 200, 500, 450, 450),
        ]
    }
    _, rooms = prompt_service.build_room_prompts(plan, None)
    prompt = rooms[0][1]
    assert "no exterior window" in prompt
    assert "warm ambient interior lighting" in prompt
    # And it must NOT contradict itself with sheer-curtain / daylight styling.
    assert "floor-to-ceiling sheer linen curtains" not in prompt
    assert "WINDOWLESS ROOM" in prompt


def test_windowless_kitchen_forbids_phantom_window() -> None:
    """A kitchen with no window in the plan must be strongly told not to render one
    (the reported failure: 2D kitchen has no window, AI render invented one), and
    that lock must survive the Flux condenser."""
    from app.services.ai.nvidia_flux_adapter import _clean_prompt

    plan = {"furniture": [
        _f("kb", "kitchen-base", 1800, 300, 2400, 600),
        _f("ck", "cooktop", 1800, 300, 600, 400),
    ]}
    _, rooms = prompt_service.build_room_prompts(plan, {"style": "Modern"})
    prompt = next(p for lbl, p, _w, _h in rooms if lbl == "Kitchen")
    assert "WINDOWLESS ROOM" in prompt
    assert "no exterior window" in prompt
    assert "floor-to-ceiling sheer linen curtains" not in prompt
    # The windowless lock is front-loaded, so it reaches the condensed Flux prompt.
    cleaned = _clean_prompt(prompt)
    assert "WINDOWLESS ROOM" in cleaned


def test_room_with_window_keeps_it_in_frame() -> None:
    """A room that DOES have a window must instruct the camera to keep it visible
    (the reported failure: bedroom window behind the bed dropped from the render)."""
    plan = {"furniture": [
        _f("bed", "bed", 500, 300, 1800, 2000),
        _f("win", "window", 500, 800, 1500, 200),
    ]}
    _, rooms = prompt_service.build_room_prompts(plan, {"style": "Modern Luxury"})
    prompt = rooms[0][1]
    assert "stays visible" in prompt
    assert "floor-to-ceiling sheer linen curtains" in prompt  # has_window -> curtains kept
    assert "WINDOWLESS ROOM" not in prompt


def test_living_without_media_unit_does_not_invent_a_tv_wall() -> None:
    """A living area with a sofa but no console/TV unit must not aim the camera at
    a 'TV / media wall' the plan never had."""
    plan = {"furniture": [
        _f("sofa", "lounger-sofa", 500, 600, 1900, 900),
        _f("win", "window", 500, 850, 1800, 200),
    ]}
    _, rooms = prompt_service.build_room_prompts(plan, {"style": "Modern"})
    prompt = next(p for lbl, p, _w, _h in rooms if lbl == "Living Area")
    assert "focal TV / media console wall" not in prompt
    assert "feature wall behind the seating" in prompt


def test_living_with_console_still_aims_at_media_wall() -> None:
    """A living area that DOES have a media console keeps the TV/media focal wall."""
    plan = {"furniture": [
        _f("sofa", "lounger-sofa", 500, 600, 1900, 900),
        _f("con", "console", 500, 180, 1100, 350),
    ]}
    _, rooms = prompt_service.build_room_prompts(plan, {"style": "Modern"})
    prompt = next(p for lbl, p, _w, _h in rooms if lbl == "Living Area")
    assert "TV / media console wall" in prompt


def test_clean_prompt_embeds_negatives_and_photorealism_triggers() -> None:
    """The Flux condenser must append photorealism triggers and the negative
    steering list (no separate negative field exists on the URL API)."""
    from app.services.ai.nvidia_flux_adapter import _clean_prompt

    _, rooms = prompt_service.build_room_prompts(_kitchen_canonical(), {"style": "Modern"})
    cleaned = _clean_prompt(rooms[0][1])
    assert len(cleaned) <= 1500
    assert "8k photorealistic interior render" in cleaned
    assert "Architectural Digest photography" in cleaned
    assert "Avoid:" in cleaned
    assert "CGI look" in cleaned
    assert "fisheye lens" in cleaned
    # Geometry/inventory survives the condenser's truncation because it leads.
    assert "Dining Table" in cleaned


def test_kitchen_negative_forbids_island_and_survives_condenser() -> None:
    """The kitchen must be told NO island/peninsula, and that instruction must
    survive the Flux condenser (which strips MASTER_CONSTRAINT + isolation line)."""
    from app.services.ai.nvidia_flux_adapter import _clean_prompt

    plan = {"furniture": [_f("kb", "kitchen-base", 1800, 300, 2400, 600),
                          _f("ck", "cooktop", 1800, 300, 600, 400)]}
    _, rooms = prompt_service.build_room_prompts(plan, {"style": "Modern"})
    prompt = next(p for lbl, p, _w, _h in rooms if lbl == "Kitchen")
    assert "NO central kitchen island" in prompt
    cleaned = _clean_prompt(prompt)
    assert "island" in cleaned.lower()  # the anti-island instruction reached Flux
    assert "KITCHEN LAYOUT LOCK" in cleaned


def test_dining_negative_forbids_kitchen_and_survives_condenser() -> None:
    """A dining area must be told it is NOT a kitchen, reaching the Flux prompt."""
    from app.services.ai.nvidia_flux_adapter import _clean_prompt

    plan = {"furniture": [
        _f("t", "dining-table", 1000, 800, 1500, 900),
        _f("c1", "dining-chair", 800, 700, 450, 500),
        _f("c2", "dining-chair", 1200, 700, 450, 500),
    ]}
    _, rooms = prompt_service.build_room_prompts(plan, {"style": "Modern"})
    prompt = next(p for lbl, p, _w, _h in rooms if lbl == "Dining Area")
    assert "DINING-ONLY LOCK" in prompt
    assert "NOT a kitchen" in prompt
    cleaned = _clean_prompt(prompt)
    assert "not a kitchen" in cleaned.lower()


def test_room_isolation_reaches_flux_prompt() -> None:
    """The strict room-isolation clause must reach the condensed Flux prompt
    (the old 'This is STRICTLY' line was stripped by the condenser)."""
    from app.services.ai.nvidia_flux_adapter import _clean_prompt

    _, rooms = prompt_service.build_room_prompts(_kitchen_canonical(), {"style": "Modern"})
    cleaned = _clean_prompt(rooms[0][1])
    assert "STRICT ROOM ISOLATION" in cleaned
