"""Approach A (JSON furniture dictionary + rules) and Approach B (Markdown system prompt),
both DERIVED from the one version-bound manifest. Offline; no provider/DB/network.

Locks: dictionary build/validate integrity, synonym normalization (reusing the matcher's
authoritative map), same-type distinct identities, opening exclusion, empty rooms,
version/fingerprint binding, deterministic rendering, style-cannot-override, and the
single-source consistency between manifest ↔ dictionary ↔ prompt inventory line.
"""
from __future__ import annotations

import json
from io import BytesIO
from unittest import mock

from PIL import Image

from app.services import furniture_dictionary as D
from app.services import furniture_manifest, generation_service, prompt_service
from app.services.ai.base import AIProviderAdapter, GenerationRequest


def _f(uid, item, cx, cy, w=100, h=100, rot=0):
    return {"uid": uid, "item_id": item, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


def _bedroom_canonical():
    return {"furniture": [
        _f("b", "bed", 500, 350, 1800, 2000),
        _f("s1", "side-table", 300, 350, 450, 450),
        _f("s2", "side-table", 700, 350, 450, 450),
        _f("w", "window", 500, 800, 1500, 200),
    ]}


def _manifest(version="v79"):
    return furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1", design_version_id=version)


# ── JSON dictionary: build & integrity ─────────────────────────────────────────

def test_dictionary_builds_bound_to_manifest():
    d = D.build_dictionary(_manifest("v79"))
    assert d["schema_version"] == D.SCHEMA_VERSION
    assert d["design_version_id"] == "v79"
    assert d["manifest_fingerprint"] == _manifest("v79")["manifest_fingerprint"]
    assert d["expected_furniture_count"] == 3
    assert d["counts"] == {"Bed": 1, "Side Table": 2}
    assert len(d["dictionary_fingerprint"]) == 16


def test_valid_dictionary_passes_validation():
    d = D.build_dictionary(_manifest("v79"))
    v = D.validate_dictionary(d, _manifest("v79"))
    assert v["valid"] is True and v["issues"] == []


def test_unsupported_schema_rejected():
    d = D.build_dictionary(_manifest())
    d["schema_version"] = "mynest.furniture_dictionary/999"
    assert "UNSUPPORTED_SCHEMA" in D.validate_dictionary(d)["issues"]


def test_duplicate_uid_rejected():
    d = D.build_dictionary(_manifest())
    d["items"].append({**d["items"][1], "uid": d["items"][1]["uid"]})  # repeat an existing uid
    assert "DUPLICATE_UID" in D.validate_dictionary(d)["issues"]


def test_invalid_dimensions_and_type_rejected():
    d = D.build_dictionary(_manifest())
    d["items"][0]["dimensions"]["w"] = 0
    d["items"][0]["item_id"] = ""
    res = D.validate_dictionary(d)
    assert "INVALID_DIMENSIONS" in res["issues"] and "INVALID_TYPE" in res["issues"]


def test_nan_and_infinite_dimensions_rejected():
    for bad in (float("nan"), float("inf"), float("-inf")):
        d = D.build_dictionary(_manifest())
        d["items"][0]["dimensions"]["w"] = bad
        assert "INVALID_DIMENSIONS" in D.validate_dictionary(d)["issues"], bad


def test_malformed_items_collection_is_safe_not_a_crash():
    # items is not a list
    res = D.validate_dictionary({"schema_version": D.SCHEMA_VERSION,
                                 "design_version_id": "v1", "items": "nope"})
    assert "MALFORMED_ITEMS" in res["issues"] and res["valid"] is False
    # a non-dict item among valid ones
    d = D.build_dictionary(_manifest())
    d["items"].append(None)
    res2 = D.validate_dictionary(d)
    assert "MALFORMED_ITEMS" in res2["issues"]


def test_missing_version_and_version_mismatch_and_fingerprint_mismatch():
    d_nov = D.build_dictionary(furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1"))
    assert "MISSING_VERSION" in D.validate_dictionary(d_nov)["issues"]

    d = D.build_dictionary(_manifest("v79"))
    assert "VERSION_MISMATCH" in D.validate_dictionary(d, _manifest("v80"))["issues"]

    d2 = D.build_dictionary(_manifest("v79"))
    d2["manifest_fingerprint"] = "deadbeefdeadbeef"
    assert "FINGERPRINT_MISMATCH" in D.validate_dictionary(d2, _manifest("v79"))["issues"]


def test_opening_miscategorization_detected():
    d = D.build_dictionary(_manifest())
    # flip the window's opening flag -> inconsistent with the authoritative opening set
    win = next(i for i in d["items"] if i["item_id"] == "window")
    win["is_opening"] = False
    assert "OPENING_MISCATEGORIZED" in D.validate_dictionary(d)["issues"]


def test_openings_excluded_from_furniture_and_counts():
    d = D.build_dictionary(_manifest())
    assert d["expected_furniture_count"] == 3                 # window excluded
    assert "Window" not in d["counts"]
    win = next(i for i in d["items"] if i["item_id"] == "window")
    assert win["category"] == "opening" and win["is_opening"] is True


def test_same_type_items_keep_distinct_identities():
    d = D.build_dictionary(_manifest())
    side = [i for i in d["items"] if i["item_id"] == "side-table"]
    assert len(side) == 2 and {i["uid"] for i in side} == {"s1", "s2"}


def test_empty_room_dictionary_has_no_furniture():
    d = D.build_dictionary(furniture_manifest.room_manifest({"furniture": []}, "Bedroom 1") or {})
    assert d["expected_furniture_count"] == 0 and d["counts"] == {}
    assert D.render_system_prompt(d).strip() != ""   # still renders, no crash


def test_dictionary_build_is_deterministic():
    assert D.build_dictionary(_manifest("v79")) == D.build_dictionary(_manifest("v79"))


# ── synonym normalization (reuses the authoritative matcher map) ───────────────

def test_synonyms_normalize_to_canonical_type():
    assert D.normalize_label("couch") == "lounger-sofa"
    assert D.normalize_label("nightstand") == "side-table"
    assert D.normalize_label("range hood") == "chimney"


def test_ambiguous_or_unknown_label_is_none():
    assert D.normalize_label("cabinet") is None       # wardrobe/console/kitchen-base — ambiguous
    assert D.normalize_label("unicorn") is None
    assert D.normalize_label("") is None and D.normalize_label(None) is None


def test_dictionary_synonyms_come_from_authoritative_map():
    from app.services.furniture_object_validation_service import _TYPE_SYNONYMS
    d = D.build_dictionary(_manifest())
    # only types present in this design appear, and verbatim from the matcher's map
    assert set(d["synonyms"]) <= {"bed", "side-table"}
    assert d["synonyms"]["side-table"] == list(_TYPE_SYNONYMS["side-table"])


# ── Markdown system prompt (Approach B) ────────────────────────────────────────

def test_system_prompt_lists_every_expected_item_and_no_invented_objects():
    md = D.render_system_prompt(D.build_dictionary(_manifest()))
    assert "Bedroom 1" in md
    assert "Bed" in md and "Side Table" in md
    for bogus in ("Dining Table", "Loungers Sofa", "Kitchen Base"):
        assert bogus not in md                        # nothing absent from the design


def test_system_prompt_has_preservation_and_no_extra_constraints():
    md = D.render_system_prompt(D.build_dictionary(_manifest()))
    low = md.lower()
    assert "do not add" in low and "duplicate" in low and "substitute" in low
    assert "no more, no fewer" in low


def test_system_prompt_repeated_type_shown_with_count():
    md = D.render_system_prompt(D.build_dictionary(_manifest()))
    assert "2× Side Table" in md


def test_system_prompt_style_cannot_override_preservation():
    md = D.render_system_prompt(D.build_dictionary(_manifest()))
    assert "PRESERVE THE CANONICAL DESIGN" in md and "VISUAL ENHANCEMENT" in md
    # preservation is stated before (higher priority than) visual enhancement
    assert md.index("PRESERVE THE CANONICAL DESIGN") < md.index("VISUAL ENHANCEMENT")
    assert "never prioritize photorealism over the canonical design contract" in md.lower()


def test_system_prompt_is_deterministic():
    d = D.build_dictionary(_manifest())
    assert D.render_system_prompt(d) == D.render_system_prompt(d)


def test_rendered_prompt_has_no_html_comment_or_unresolved_placeholder():
    md = D.render_system_prompt(D.build_dictionary(_manifest()))
    assert "<!--" not in md and "{{" not in md


def test_unknown_template_placeholder_is_stripped_not_leaked(tmp_path, monkeypatch):
    tpl = tmp_path / "tpl.md"
    tpl.write_text("Room: {{ROOM_LABEL}}\nExtra: {{UNKNOWN_X}}\n", encoding="utf-8")
    monkeypatch.setattr(D, "_TEMPLATE_PATH", tpl)
    out = D.render_system_prompt(D.build_dictionary(_manifest()))
    assert "Bedroom 1" in out                 # known placeholder filled
    assert "{{UNKNOWN_X}}" not in out and "{{" not in out  # unknown stripped, nothing leaks


# ── single source of truth: manifest ↔ dictionary ↔ prompt inventory line ──────

def test_dictionary_counts_match_manifest_and_prompt_line():
    m = _manifest()
    d = D.build_dictionary(m)
    assert d["counts"] == m["counts"]
    assert d["expected_furniture_count"] == m["furniture_count"]
    # the prompt's authoritative inventory line is the same manifest-derived source
    enriched = prompt_service.group_by_room(_bedroom_canonical()["furniture"])[0][1]
    line = prompt_service._counted_furniture(enriched)
    for name, n in d["counts"].items():
        assert f"{n}x {name}" in line


# ── integration: dictionary + system prompt persisted in provenance ───────────

class _SpyAdapter(AIProviderAdapter):
    name = "nvidia"
    model = "black-forest-labs/flux.1-dev"
    supports_control_image = True

    def generate(self, request: GenerationRequest):
        img = Image.new("RGB", (64, 64), (200, 180, 150))
        for y in range(32):
            for x in range(64):
                img.putpixel((x, y), (30, 40, 60))
        buf = BytesIO(); img.save(buf, "PNG"); return [buf.getvalue()]


def _base_png():
    img = Image.new("RGB", (64, 64), (10, 20, 30))
    for y in range(20):                       # a band so the base is not flagged blank
        for x in range(64):
            img.putpixel((x, y), (120, 90, 70))
    buf = BytesIO(); img.save(buf, "PNG"); return buf.getvalue()


def test_render_room_persists_version_bound_dictionary_and_system_prompt():
    canonical = _bedroom_canonical()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        generation_service._render_room(
            _SpyAdapter(), "nvidia", "Modern", ("Bedroom 1", "p", 64, 64),
            ("proj", "fp", canonical, None),
            generation_id="dict-prov", index=0, seed=1, fresh_generation=True,
            base_render=_base_png(), scene_geometry_faithful=True,
            design_version_id="v77",
        )
    p = generation_service.DEBUG_ARTIFACTS_DIR / "dict-prov" / "room_0_Bedroom 1" / "furniture_manifest.json"
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["dictionary_valid"] is True
    d = payload["furniture_dictionary"]
    assert d["design_version_id"] == "v77" and d["expected_furniture_count"] == 3
    assert d["manifest_fingerprint"] == payload["authoritative_manifest"]["manifest_fingerprint"]
    assert "Bed" in payload["system_prompt_md"] and "Bedroom 1" in payload["system_prompt_md"]
