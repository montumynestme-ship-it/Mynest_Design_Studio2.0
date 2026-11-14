"""User-written theme description -> AI prompt styling context.

The free-text theme the user types in the AI Render dialog rides the existing
`design_intent` dict (no schema change) and is appended to EVERY room's prompt as a
clearly-labelled styling-only block that never authorises a layout/geometry change.
"""

from app.services import prompt_service as P


def _plan():
    return {"furniture": [
        {"uid": "b1", "item_id": "bed", "cx": 100, "cy": 100, "w": 150, "h": 200, "rotation": 0},
        {"uid": "b2", "item_id": "bed", "cx": 600, "cy": 100, "w": 150, "h": 200, "rotation": 0},
        {"uid": "tag1", "item_id": "room-tag", "cx": 120, "cy": 110, "w": 10, "h": 10,
         "rotation": 0, "label": "Master Bedroom"},
    ]}


def _prompts(theme=None, extra=None):
    intent = {"style": "Modern"}
    if theme is not None:
        intent["theme"] = theme
    if extra:
        intent.update(extra)
    _s, prompts = P.build_room_prompts(_plan(), design_intent=intent, all_sections=False)
    return {lbl: text for lbl, text, _w, _h in prompts}


def test_theme_reaches_every_room_prompt():
    by = _prompts("Warm oak finishes, beige textures, indirect lighting.")
    for lbl, text in by.items():
        assert "USER THEME" in text, lbl
        assert "Warm oak finishes" in text, lbl


def test_theme_is_styling_only_geometry_rules_present():
    text = _prompts("Cozy rustic timber and stone.")["Bedroom 1"]
    # the styling block explicitly forbids layout/geometry changes
    assert "ONLY to materials" in text
    assert "does NOT permit adding, removing, moving" in text
    assert "authoritative" in text


def test_two_themes_do_not_leak_between_requests():
    a = _prompts("Warm oak and brass, golden evening light.")["Bedroom 1"]
    b = _prompts("Cool minimalist concrete and glass, cold daylight.")["Bedroom 1"]
    assert "Warm oak" in a and "Cool minimalist" not in a
    assert "Cool minimalist" in b and "Warm oak" not in b


def test_absent_theme_is_backward_compatible():
    by = _prompts(theme=None)
    assert all("USER THEME" not in t for t in by.values())


def test_whitespace_only_theme_injects_nothing():
    by = _prompts("   \n  \t ")
    assert all("USER THEME" not in t for t in by.values())


def test_theme_and_room_tag_coexist():
    by = _prompts("Luxury contemporary, warm neutrals.")
    assert "USER THEME" in by["Bedroom 1"] and "Master Bedroom" in by["Bedroom 1"]
    assert "USER THEME" in by["Bedroom 2"] and "Master Bedroom" not in by["Bedroom 2"]


def test_theme_length_is_capped():
    long = "oak " * 1000  # 4000 chars
    text = _prompts(long)["Bedroom 1"]
    # the injected theme is capped (<= 1200 chars of theme content), never the whole 4000
    start = text.index("USER THEME (styling only): ") + len("USER THEME (styling only): ")
    end = text.index("\n", start)
    assert (end - start) <= 1200
