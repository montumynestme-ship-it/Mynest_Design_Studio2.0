"""Floor-plan TEXT extraction (audit stage 2) — deterministic core.

Feeds synthetic RAW OCR results into the deterministic builder/parser (no OCR engine
required) and checks classification, dimension parsing (feet/inches + metric),
rotated text, low-confidence handling, dedup of overlapping results, and the
source-of-truth invariants (raw text preserved verbatim, original pixel bbox kept,
parsed values separate, nothing invented).
"""

from app.services import text_extraction_service as tx


def _raw(text, bbox, conf=0.9, rot=0.0):
    return {"text": text, "bbox": bbox, "confidence": conf, "rotation": rot}


# ── Room labels ──────────────────────────────────────────────────────────────

def test_room_labels_classified_with_canonical_name():
    raw = [
        _raw("Kitchen", [10, 10, 90, 30]),
        _raw("Master Bedroom", [10, 60, 140, 80]),
        _raw("Living", [200, 10, 260, 30]),
        _raw("Toilet", [200, 60, 250, 80]),
        _raw("Dining", [200, 110, 260, 130]),
        _raw("Bedroom 2", [10, 110, 110, 130]),
    ]
    layer = tx.build_text_layer(raw)
    by_text = {e["text"]: e for e in layer["text"]}
    assert by_text["Kitchen"]["type"] == "room_label"
    assert by_text["Kitchen"]["parsed"]["canonical_room"] == "Kitchen"
    assert by_text["Master Bedroom"]["parsed"]["canonical_room"] == "Bedroom"
    assert by_text["Living"]["parsed"]["canonical_room"] == "Living Area"
    assert by_text["Toilet"]["parsed"]["canonical_room"] == "Toilet"
    assert by_text["Dining"]["parsed"]["canonical_room"] == "Dining Area"
    assert by_text["Bedroom 2"]["parsed"]["canonical_room"] == "Bedroom"
    assert layer["stats"]["room_label"] == 6


def test_non_room_word_is_not_a_room_label():
    # A word that merely contains no room keyword stays unknown (no false positive).
    layer = tx.build_text_layer([_raw("Notes:", [0, 0, 40, 12])])
    assert layer["text"][0]["type"] == "unknown"


# ── Feet / inches dimensions ─────────────────────────────────────────────────

def test_feet_inches_variants():
    for s, ft, inch in [("12'6\"", 12, 6), ("12' 6\"", 12, 6), ("12'-6\"", 12, 6),
                        ("12'", 12, 0), ("6\"", 0, 6), ("10 ft 3 in", 10, 3)]:
        d = tx.parse_dimension(s)
        assert d is not None and d["kind"] == "length", f"failed: {s}"
        assert d["system"] == "imperial"
        assert d["feet"] == ft and d["inches"] == inch, f"bad parse: {s} -> {d}"
    # 12'6" = 3810 mm
    assert abs(tx.parse_dimension("12'6\"")["value_mm"] - 3810.0) < 0.1


def test_feet_inches_pair():
    d = tx.parse_dimension("12'6\" x 10'0\"")
    assert d["kind"] == "pair"
    assert d["width"]["system"] == "imperial" and d["depth"]["system"] == "imperial"
    assert abs(d["width"]["value_mm"] - 3810.0) < 0.1
    assert abs(d["depth"]["value_mm"] - 3048.0) < 0.1


# ── Metric dimensions ────────────────────────────────────────────────────────

def test_metric_variants():
    assert abs(tx.parse_dimension("3600")["value_mm"] - 3600.0) < 0.1        # bare = mm
    assert abs(tx.parse_dimension("3600mm")["value_mm"] - 3600.0) < 0.1
    assert abs(tx.parse_dimension("3.6m")["value_mm"] - 3600.0) < 0.1
    assert abs(tx.parse_dimension("360 cm")["value_mm"] - 3600.0) < 0.1
    for s in ("3600", "3.6 m"):
        assert tx.parse_dimension(s)["system"] == "metric"


def test_metric_pair_area():
    d = tx.parse_dimension("2400 x 3000")
    assert d["kind"] == "pair"
    assert abs(d["area_sqm"] - 7.2) < 0.001  # 2.4m * 3.0m


def test_dimension_classified_as_dimension_type():
    layer = tx.build_text_layer([
        _raw("12'6\"", [0, 0, 50, 12]),
        _raw("3600", [0, 20, 40, 32]),
        _raw("2400 x 3000", [0, 40, 80, 52]),
    ])
    assert all(e["type"] == "dimension" for e in layer["text"])
    assert layer["stats"]["dimension"] == 3


# ── Rotated text ─────────────────────────────────────────────────────────────

def test_rotated_text_preserved_and_classified():
    layer = tx.build_text_layer([_raw("3600", [500, 100, 512, 180], rot=90.0)])
    e = layer["text"][0]
    assert e["rotation"] == 90.0
    assert e["type"] == "dimension"            # rotation doesn't break parsing
    assert e["bbox"] == [500.0, 100.0, 512.0, 180.0]  # original pixels preserved


# ── Low-confidence OCR ───────────────────────────────────────────────────────

def test_low_confidence_flagged_and_kept():
    layer = tx.build_text_layer([_raw("Kitchen", [0, 0, 80, 20], conf=0.30)])
    e = layer["text"][0]
    assert e["confidence"] == 0.30
    assert e["low_confidence"] is True
    assert e["type"] == "room_label"


def test_min_confidence_filter_drops_below_floor():
    raw = [_raw("Kitchen", [0, 0, 80, 20], conf=0.20),
           _raw("Bedroom", [0, 40, 80, 60], conf=0.80)]
    layer = tx.build_text_layer(raw, min_confidence=0.5)
    assert [e["text"] for e in layer["text"]] == ["Bedroom"]


# ── Duplicate / overlapping OCR results ──────────────────────────────────────

def test_overlapping_duplicates_deduped_keep_highest_confidence():
    raw = [
        _raw("Kitchen", [10, 10, 90, 30], conf=0.60),
        _raw("Kitchen", [12, 11, 92, 31], conf=0.95),   # overlaps first, higher conf
        _raw("Bedroom", [10, 100, 90, 120], conf=0.90),  # distinct
    ]
    layer = tx.build_text_layer(raw)
    kitchens = [e for e in layer["text"] if _norm(e["text"]) == "kitchen"]
    assert len(kitchens) == 1
    assert kitchens[0]["confidence"] == 0.95
    assert layer["stats"]["total"] == 2


def test_same_text_far_apart_not_deduped():
    raw = [_raw("Bedroom", [0, 0, 80, 20]), _raw("Bedroom", [0, 400, 80, 420])]
    layer = tx.build_text_layer(raw)
    assert layer["stats"]["total"] == 2  # two real, non-overlapping bedrooms


# ── Source-of-truth invariants ───────────────────────────────────────────────

def test_never_invents_text_and_skips_empty():
    layer = tx.build_text_layer([_raw("   ", [0, 0, 10, 10]), _raw("", [0, 0, 5, 5])])
    assert layer["text"] == []


def test_raw_text_kept_verbatim_separate_from_parsed():
    layer = tx.build_text_layer([_raw("12'6\"", [0, 0, 50, 12])])
    e = layer["text"][0]
    assert e["text"] == "12'6\""                  # raw verbatim
    assert e["parsed"]["value_mm"] == 3810.0      # semantic, separate


def test_normalization_only_when_image_size_given():
    raw = [_raw("Kitchen", [100, 50, 300, 90])]
    assert "bbox_normalized" not in tx.build_text_layer(raw)["text"][0]
    layer = tx.build_text_layer(raw, image_size=(1000, 500))
    e = layer["text"][0]
    assert e["bbox"] == [100.0, 50.0, 300.0, 90.0]           # pixels preserved
    assert e["bbox_normalized"] == [0.1, 0.1, 0.3, 0.18]     # 0..1 added after


def test_no_engine_raises_actionable_error():
    import pytest
    with pytest.raises(tx.TextExtractionUnavailable):
        tx.run_ocr(object(), engine="none")


def _norm(s):
    return tx._normalize_text(s)
