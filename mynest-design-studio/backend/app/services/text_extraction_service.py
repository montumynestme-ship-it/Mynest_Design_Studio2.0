"""Floor-plan TEXT extraction (audit stage 2).

Turns a high-resolution rendered floor-plan image into a structured text layer:

    {
      "text": [
        {"text": "...", "bbox": [x1,y1,x2,y2], "confidence": 0.0,
         "type": "room_label|dimension|annotation|unknown",
         "rotation": 0.0, "low_confidence": false, "parsed": {...}|null}
      ],
      "image_size": [w, h] | null,
      "engine": "pytesseract|easyocr|none",
      "stats": {...}
    }

Design principles (per goal / source-of-truth rule):
- The DETERMINISTIC CORE (`build_text_layer`, `parse_dimension`, `classify_text`,
  dedup, normalization) processes ONLY the raw OCR results it is given — it never
  invents text. It is unit-testable with synthetic OCR results, no engine required.
- The OCR ENGINE is a thin, optional adapter (`run_ocr`). pytesseract or easyocr is
  used when installed; if neither is present, `extract_text_from_image` raises
  `TextExtractionUnavailable` with actionable guidance rather than faking output.
- Original PIXEL coordinates are preserved on every element; normalization to 0..1
  is added ONLY afterwards (and only when the image size is known).
- Raw OCR ``text`` is kept verbatim and SEPARATE from the parsed ``parsed`` values.
- No FLUX / no image generation is used anywhere here.
"""

from __future__ import annotations

import re
from typing import Any

# ── Vocabulary ───────────────────────────────────────────────────────────────

# Canonical room label keywords (lower-cased match against normalized OCR text).
# Values map an OCR token to a canonical room name.
_ROOM_LABELS: dict[str, str] = {
    "living": "Living Area", "living room": "Living Area", "hall": "Living Area",
    "drawing": "Living Area", "lounge": "Living Area", "family": "Living Area",
    "kitchen": "Kitchen", "kit": "Kitchen", "pantry": "Kitchen",
    "dining": "Dining Area", "dinning": "Dining Area",
    "bedroom": "Bedroom", "bed room": "Bedroom", "master bedroom": "Bedroom",
    "master": "Bedroom", "guest room": "Bedroom", "child": "Bedroom",
    "toilet": "Toilet", "bath": "Bathroom", "bathroom": "Bathroom",
    "wc": "Toilet", "washroom": "Toilet", "powder": "Toilet",
    "balcony": "Balcony", "terrace": "Terrace", "deck": "Balcony",
    "study": "Study", "office": "Study", "pooja": "Pooja", "puja": "Pooja",
    "utility": "Utility", "store": "Store", "storage": "Store",
    "foyer": "Foyer", "lobby": "Lobby", "passage": "Passage", "corridor": "Passage",
    "wardrobe": "Wardrobe", "closet": "Wardrobe", "dress": "Wardrobe",
    "stair": "Staircase", "staircase": "Staircase", "lift": "Lift",
    "porch": "Porch", "garage": "Garage", "parking": "Parking",
    "verandah": "Verandah", "veranda": "Verandah", "sit out": "Balcony",
}

# Architectural annotation tokens that relate to geometry but are not room labels
# or dimensions (kept, never invented). Matched as whole normalized tokens.
_ANNOTATION_TOKENS: frozenset[str] = frozenset({
    "up", "dn", "down", "door", "window", "d", "w", "typ", "slab", "loft",
    "ledge", "sill", "lintel", "cupboard", "shelf", "counter", "platform",
    "duct", "shaft", "open to below", "open to sky", "ref", "fridge",
    "sink", "wm", "washing machine", "wall", "opening", "railing", "parapet",
})

# ── Dimension parsing (deterministic) ────────────────────────────────────────

_MM_PER_FOOT = 304.8
_MM_PER_INCH = 25.4

# 12'6"  12' 6"  12'-6"  12'  6"  (feet and/or inches, straight or curly quotes)
_FEET_IN = re.compile(
    r"^\s*(?:(?P<ft>\d+(?:\.\d+)?)\s*(?:'|’|ft|feet)\s*)?"
    r"(?:[-\s]*(?P<inch>\d+(?:\.\d+)?)\s*(?:\"|”|''|in|inch|inches))?\s*$"
)
# "12 ft 6 in" style
_FEET_IN_WORDS = re.compile(
    r"^\s*(?P<ft>\d+(?:\.\d+)?)\s*(?:ft|feet)\s*(?P<inch>\d+(?:\.\d+)?)?\s*(?:in|inch|inches)?\s*$",
    re.IGNORECASE,
)
# metric: 3600mm / 3600 mm / 3.6m / 3.60 m  (a bare integer is treated as mm)
_METRIC = re.compile(
    r"^\s*(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|m)?\s*$", re.IGNORECASE
)
# a dimension PAIR: A x B  (x / × / X), each side any single-length form
_PAIR = re.compile(r"^\s*(?P<a>.+?)\s*[x×X]\s*(?P<b>.+?)\s*$")


def _num(s: str | None) -> float | None:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_single_length(text: str) -> dict[str, Any] | None:
    """Parse ONE length token into a normalized mm value. Returns None if not a length."""
    t = text.strip()
    if not t:
        return None

    m = _FEET_IN.match(t)
    if m and (m.group("ft") or m.group("inch")):
        ft = _num(m.group("ft")) or 0.0
        inch = _num(m.group("inch")) or 0.0
        mm = ft * _MM_PER_FOOT + inch * _MM_PER_INCH
        return {"system": "imperial", "feet": ft, "inches": inch,
                "value_mm": round(mm, 1), "value_m": round(mm / 1000.0, 3)}

    m = _FEET_IN_WORDS.match(t)
    if m:
        ft = _num(m.group("ft")) or 0.0
        inch = _num(m.group("inch")) or 0.0
        mm = ft * _MM_PER_FOOT + inch * _MM_PER_INCH
        return {"system": "imperial", "feet": ft, "inches": inch,
                "value_mm": round(mm, 1), "value_m": round(mm / 1000.0, 3)}

    m = _METRIC.match(t)
    if m:
        val = _num(m.group("val"))
        if val is None:
            return None
        unit = (m.group("unit") or "").lower()
        if unit == "m":
            mm = val * 1000.0
        elif unit == "cm":
            mm = val * 10.0
        else:  # "mm" or bare number → millimetres (plan dimensions are mm)
            mm = val
        return {"system": "metric", "value_mm": round(mm, 1),
                "value_m": round(mm / 1000.0, 3), "unit": unit or "mm"}
    return None


def parse_dimension(text: str) -> dict[str, Any] | None:
    """Deterministically parse an architectural dimension string.

    Handles single lengths (imperial feet/inches or metric mm/cm/m) and dimension
    PAIRS ("A x B"). Returns a structured dict or None when the text is not a
    dimension. Never guesses beyond what the characters encode.
    """
    if text is None:
        return None
    t = text.strip()
    if not t:
        return None

    pair = _PAIR.match(t)
    if pair:
        a = _parse_single_length(pair.group("a"))
        b = _parse_single_length(pair.group("b"))
        if a and b:
            return {"kind": "pair", "width": a, "depth": b,
                    "area_sqm": round((a["value_m"] * b["value_m"]), 3)}
        return None

    single = _parse_single_length(t)
    if single:
        return {"kind": "length", **single}
    return None


# ── Classification ───────────────────────────────────────────────────────────

def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _room_label(norm: str) -> str | None:
    """Return the canonical room name if the normalized text denotes a room.

    Matches a keyword as a whole word (optionally followed by a number/qualifier,
    e.g. 'bedroom 2', 'master bed'), never as a loose substring of another word.
    """
    stripped = re.sub(r"[^a-z ]", "", norm).strip()
    if not stripped:
        return None
    if stripped in _ROOM_LABELS:
        return _ROOM_LABELS[stripped]
    # keyword + trailing qualifier at a word boundary: "bedroom 2", "kitchen area".
    for kw, canon in _ROOM_LABELS.items():
        if re.match(rf"^{re.escape(kw)}\b", stripped):
            return canon
    return None


def classify_text(raw_text: str) -> tuple[str, dict[str, Any] | None]:
    """Classify an OCR string → (type, parsed). type ∈ {room_label, dimension,
    annotation, unknown}. parsed carries the SEMANTIC value (kept separate from the
    raw text); it is None for annotation/unknown/plain room labels except that a
    room label carries its canonical name."""
    norm = _normalize_text(raw_text)
    if not norm:
        return "unknown", None

    dim = parse_dimension(raw_text)
    if dim is not None:
        return "dimension", dim

    room = _room_label(norm)
    if room is not None:
        return "room_label", {"canonical_room": room}

    token = re.sub(r"[^a-z ]", "", norm).strip()
    if token in _ANNOTATION_TOKENS:
        return "annotation", None

    return "unknown", None


# ── Geometry helpers ─────────────────────────────────────────────────────────

def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _dedup(elements: list[dict[str, Any]], iou_threshold: float) -> list[dict[str, Any]]:
    """Drop duplicate/overlapping OCR results deterministically.

    Two elements collide when their boxes overlap (IoU >= threshold) AND their
    normalized text matches. The higher-confidence element wins; ties break on the
    larger box then earlier position, so the result is order-stable.
    """
    def _area(b: list[float]) -> float:
        return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])

    ordered = sorted(
        enumerate(elements),
        key=lambda it: (-it[1]["confidence"], -_area(it[1]["bbox"]), it[0]),
    )
    kept: list[dict[str, Any]] = []
    for _, el in ordered:
        norm = _normalize_text(el["text"])
        dup = any(
            _normalize_text(k["text"]) == norm and _iou(el["bbox"], k["bbox"]) >= iou_threshold
            for k in kept
        )
        if not dup:
            kept.append(el)
    # restore original reading order (top-to-bottom, left-to-right)
    kept.sort(key=lambda e: (round(e["bbox"][1], 1), round(e["bbox"][0], 1)))
    return kept


def normalize_bbox(bbox: list[float], width: float, height: float) -> list[float]:
    """Normalize a pixel bbox to 0..1 (done ONLY after extraction)."""
    if not width or not height:
        return list(bbox)
    x1, y1, x2, y2 = bbox
    return [round(x1 / width, 5), round(y1 / height, 5),
            round(x2 / width, 5), round(y2 / height, 5)]


# ── Deterministic builder ────────────────────────────────────────────────────

_LOW_CONF = 0.5


def build_text_layer(
    raw_results: list[dict[str, Any]],
    image_size: tuple[int, int] | None = None,
    min_confidence: float = 0.0,
    dedup_iou: float = 0.6,
    engine: str = "none",
) -> dict[str, Any]:
    """Build the structured text layer from RAW OCR results.

    ``raw_results`` items: ``{"text": str, "bbox": [x1,y1,x2,y2],
    "confidence": float(0..1), "rotation": float=0}``. This function invents
    nothing — it only classifies, parses, dedups and (optionally) normalizes what
    OCR produced. Original pixel bboxes are preserved on every element.
    """
    elements: list[dict[str, Any]] = []
    for r in raw_results:
        raw_text = str(r.get("text", ""))
        if raw_text.strip() == "":
            continue  # never emit empty text
        conf = float(r.get("confidence", 0.0))
        if conf < min_confidence:
            continue
        bbox = [float(v) for v in r.get("bbox", [0, 0, 0, 0])]
        rotation = float(r.get("rotation", 0.0) or 0.0)
        el_type, parsed = classify_text(raw_text)
        el: dict[str, Any] = {
            "text": raw_text,               # verbatim, separate from parsed
            "bbox": bbox,                   # ORIGINAL pixel coords, preserved
            "confidence": round(conf, 4),
            "type": el_type,
            "rotation": rotation,
            "low_confidence": conf < _LOW_CONF,
            "parsed": parsed,               # semantic value, or None
        }
        if image_size:
            el["bbox_normalized"] = normalize_bbox(bbox, image_size[0], image_size[1])
        elements.append(el)

    elements = _dedup(elements, dedup_iou)

    stats: dict[str, int] = {"total": len(elements)}
    for t in ("room_label", "dimension", "annotation", "unknown"):
        stats[t] = sum(1 for e in elements if e["type"] == t)
    stats["low_confidence"] = sum(1 for e in elements if e["low_confidence"])

    return {
        "text": elements,
        "image_size": list(image_size) if image_size else None,
        "engine": engine,
        "stats": stats,
    }


# ── OCR engine adapter (optional) ────────────────────────────────────────────

class TextExtractionUnavailable(RuntimeError):
    """Raised when no OCR engine is installed. The deterministic core still works
    on supplied raw OCR results; only live image OCR needs an engine."""


def _ocr_engine_available() -> str:
    import importlib.util as u
    if u.find_spec("pytesseract"):
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return "pytesseract"
        except Exception:  # noqa: BLE001 — wrapper present but binary missing
            pass
    if u.find_spec("easyocr"):
        return "easyocr"
    return "none"


def _run_pytesseract(pil_image) -> list[dict[str, Any]]:
    import pytesseract
    data = pytesseract.image_to_data(pil_image, output_type=pytesseract.Output.DICT)
    out: list[dict[str, Any]] = []
    n = len(data.get("text", []))
    for i in range(n):
        txt = data["text"][i]
        if not txt or not txt.strip():
            continue
        conf = float(data["conf"][i])
        conf = 0.0 if conf < 0 else conf / 100.0  # tesseract conf is 0..100 (-1 = none)
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        out.append({"text": txt, "bbox": [float(x), float(y), float(x + w), float(y + h)],
                    "confidence": conf, "rotation": 0.0})
    return out


def _run_easyocr(pil_image) -> list[dict[str, Any]]:
    import math

    import easyocr
    import numpy as np
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    # rotation_info lets easyocr read 90°/270° text (common on vertical walls).
    results = reader.readtext(np.array(pil_image), rotation_info=[90, 180, 270])
    out: list[dict[str, Any]] = []
    for poly, txt, conf in results:
        if not txt or not txt.strip():
            continue
        xs = [float(p[0]) for p in poly]
        ys = [float(p[1]) for p in poly]
        # rotation from the polygon's top edge (p0 -> p1)
        (x0, y0), (x1, y1) = poly[0], poly[1]
        rot = round(math.degrees(math.atan2(float(y1) - float(y0), float(x1) - float(x0))), 1)
        out.append({"text": txt, "bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "confidence": float(conf), "rotation": rot})
    return out


def run_ocr(pil_image, engine: str = "auto") -> tuple[list[dict[str, Any]], str]:
    """Run the OCR engine and return (raw_results, engine_name). Raises
    TextExtractionUnavailable if no engine is installed."""
    chosen = _ocr_engine_available() if engine == "auto" else engine
    if chosen == "pytesseract":
        return _run_pytesseract(pil_image), "pytesseract"
    if chosen == "easyocr":
        return _run_easyocr(pil_image), "easyocr"
    raise TextExtractionUnavailable(
        "No OCR engine available. Install one of: (1) Tesseract binary + "
        "`pip install pytesseract`, or (2) `pip install easyocr`. The deterministic "
        "text-layer core (build_text_layer/parse_dimension/classify_text) works "
        "without an engine when given raw OCR results."
    )


def extract_text_from_image(
    pil_image,
    min_confidence: float = 0.0,
    dedup_iou: float = 0.6,
    engine: str = "auto",
) -> dict[str, Any]:
    """Full stage 2: OCR a rendered floor-plan image → structured text layer.

    Requires an OCR engine (see run_ocr). Original pixel coordinates are preserved;
    normalization is added because the image size is known here.
    """
    raw, engine_name = run_ocr(pil_image, engine=engine)
    size = getattr(pil_image, "size", None)
    return build_text_layer(
        raw, image_size=size, min_confidence=min_confidence,
        dedup_iou=dedup_iou, engine=engine_name,
    )
