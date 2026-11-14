"""Hybrid AI-render furniture detector (Issue #1B): COCO YOLOv8 + OWLv2, merged with
PROVENANCE and deterministic cross-source de-duplication.

Evidence (benchmark on real AI outputs, 2026-10):
  * The project's CUSTOM YOLO (`storage/models/floorplan_detector`) is a 2D FLOOR-PLAN
    SYMBOL detector (14 plan classes, trained on synthetic plan images). On photorealistic
    3D renders it returns ZERO detections — a domain mismatch — so it is NOT used here.
  * COCO `yolov8n` detects real-world furniture/appliances it was trained on (bed, couch,
    chair, dining table, refrigerator, oven, sink, microwave, tv, bench, …) and is CONFIDENT
    where those objects are visibly rendered (e.g. Kitchen appliances 0.26–0.75) — far less
    noisy than OWLv2 there. It has no wardrobe/nightstand/dressing-table class.
  * OWLv2 is open-vocabulary (covers the types YOLO lacks) but weak/noisy on these renders.

The hybrid uses each where it is strong and keeps every candidate's SOURCE + original class,
so the validator's identity logic (type-consistent label required for a FAIL) still applies.
It NEVER invents detections: YOLO classes come from the model, OWLv2 from its vocabulary.

This is a detector only — it changes no canonical data, geometry, camera, FAL, or validator
thresholds. The validator can be called with `detector=detect_hybrid` (audit-only).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable

from app.services.furniture_geometry_validation_service import detect_owlv2, iou, nms_dedup

logger = logging.getLogger("app.services.furniture_detector_hybrid")


def _normalize_image(image: Any) -> Any:
    """Validate AND normalize any supported image input to a form BOTH detectors accept —
    a path ``str`` or a ``PIL.Image`` (YOLO and OWLv2 both take either). Encoded bytes are
    decoded via ``io.BytesIO``; array-likes (numpy) via ``PIL.fromarray``; ``os.PathLike`` is
    coerced to ``str``. Unsupported inputs raise ``TypeError`` so malformed input is a CLEAR
    error, never a silent zero-detection."""
    import io as _io

    from PIL import Image as _Image

    if isinstance(image, _Image.Image):
        return image
    if isinstance(image, str):
        return image
    if isinstance(image, os.PathLike):
        return os.fspath(image)
    if isinstance(image, (bytes, bytearray)):
        return _Image.open(_io.BytesIO(bytes(image))).convert("RGB")
    if hasattr(image, "__array__") or hasattr(image, "__array_interface__"):
        import numpy as _np
        arr = _np.asarray(image)
        return _Image.fromarray(arr if arr.dtype == _np.uint8 else arr.astype("uint8"))
    raise TypeError(f"unsupported image input for detection: {type(image).__name__}")

# COCO class -> the open-vocab-style label our validator's identity synonyms understand.
# Only furniture/appliance classes that can appear in an interior render are mapped; all
# other COCO classes (person, car, …) are ignored so we never fabricate furniture.
COCO_FURNITURE_TO_LABEL: dict[str, str] = {
    "bed": "bed",
    "couch": "sofa",
    "chair": "chair",
    "dining table": "dining table",
    "bench": "bench",
    "tv": "tv",
    "refrigerator": "refrigerator",
    "oven": "oven",
    "sink": "sink",
    "microwave": "microwave",
    "toilet": "toilet",
    "potted plant": "potted plant",
    "vase": "vase",
}

_YOLO_MODEL: Any = None  # lazy singleton


def _yolo(model_path: str = "yolov8n.pt") -> Any:
    global _YOLO_MODEL
    if _YOLO_MODEL is None:
        from ultralytics import YOLO
        _YOLO_MODEL = YOLO(model_path)
    return _YOLO_MODEL


def detect_yolo_coco(image: Any, *, conf: float = 0.25, iou: float = 0.5, imgsz: int = 960,
                     model_path: str = "yolov8n.pt") -> list[dict[str, Any]]:
    """COCO YOLOv8 detections for furniture/appliance classes only, in the image's own pixel
    frame. Boxes carry source='yolo-coco' + the original COCO class. conf is a real detection
    threshold (not lowered to inflate recall). Returns the standard detector-box contract."""
    src = _normalize_image(image)   # str path or PIL.Image — both accepted by ultralytics
    model = _yolo(model_path)
    res = model.predict(src, conf=conf, iou=iou, imgsz=imgsz, verbose=False)[0]
    out: list[dict[str, Any]] = []
    for b in res.boxes:
        cls = model.names[int(b.cls)]
        label = COCO_FURNITURE_TO_LABEL.get(cls)
        if label is None:
            continue  # ignore non-furniture COCO classes (never fabricate furniture)
        x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
        out.append({"query": label, "coco_class": cls, "source": "yolo-coco",
                    "score": round(float(b.conf), 4),
                    "x": round(x1, 1), "y": round(y1, 1), "width": round(x2 - x1, 1), "height": round(y2 - y1, 1),
                    "center_x": round((x1 + x2) / 2, 1), "center_y": round((y1 + y2) / 2, 1)})
    return out


# Explicit CLASS-COMPATIBILITY groups for CROSS-SOURCE dedup. Two detections are only treated
# as duplicates of the SAME object (suppressed on overlap) when they fall in the SAME group;
# different groups that overlap are BOTH kept (competing identity hypotheses for the validator).
# Each entry lists TIGHT aliases (near-synonyms only — distinct furniture types are kept in
# separate groups). Aliases are matched as WHOLE words/phrases (word-boundary), so e.g. "oven"
# never matches "woven", "door" never matches "outdoor", and "bed" never matches "bedside".
# The first group with a whole-phrase hit wins (most specific phrases are listed first).
_CLASS_FAMILIES: list[tuple[str, tuple[str, ...]]] = [
    ("side_table", ("side table", "bedside table", "bedside", "nightstand", "night stand", "end table")),
    ("coffee_table", ("coffee table", "center table", "centre table")),
    ("dining_table", ("dining table",)),
    ("dining_chair", ("dining chair",)),
    ("chair", ("chair", "armchair")),
    ("bed", ("bed",)),
    ("sofa", ("sofa", "couch", "lounger", "settee")),
    ("wardrobe", ("wardrobe", "closet", "armoire")),
    ("dresser", ("dressing table", "chest of drawers", "dresser", "vanity")),
    ("console", ("console", "sideboard")),
    ("shoe_rack", ("shoe rack",)),
    ("kitchen_cabinet", ("kitchen cabinet", "base cabinet", "lower cabinet", "tall cabinet",
                         "cabinet", "cupboard", "countertop", "counter", "worktop")),
    ("refrigerator", ("refrigerator", "fridge")),
    ("oven", ("oven", "stove", "cooktop")),
    ("microwave", ("microwave",)),
    ("sink", ("sink", "washbasin", "basin")),
    ("chimney", ("chimney", "range hood", "hood", "extractor")),
    ("tv", ("tv", "television")),
    # "bay window seating" is FURNITURE (a bench); a plain architectural "bay window" is NOT
    # — it falls through to the `window` group below. So they are kept SEPARATE.
    ("bench", ("bench", "bay window seating")),
    ("door", ("door",)),
    ("window", ("window",)),
    # vase and plant are distinct objects, not aliases — kept in SEPARATE groups.
    ("plant", ("potted plant", "plant")),
    ("vase", ("vase",)),
    ("table", ("table",)),  # generic fallback AFTER the specific *_table groups
]

# Precompiled whole-word/phrase patterns (word boundaries), built once.
_FAMILY_PATTERNS: list[tuple[str, tuple[re.Pattern[str], ...]]] = [
    (fam, tuple(re.compile(r"\b" + re.escape(t) + r"\b") for t in toks)) for fam, toks in _CLASS_FAMILIES
]


def _class_family(query: str | None) -> str:
    """Normalize a detector label to its compatibility group via WHOLE-word/phrase matching
    (no broad substring hits). Unknown labels map to their own normalized token (so two
    unrelated unknown classes never share a family)."""
    q = (query or "").lower()
    for fam, pats in _FAMILY_PATTERNS:
        if any(p.search(q) for p in pats):
            return fam
    return " ".join(q.split()) or "unknown"


def merge_candidates(yolo: list[dict[str, Any]], owl: list[dict[str, Any]], *,
                     cross_iou: float = 0.6, max_candidates: int = 40) -> list[dict[str, Any]]:
    """Deterministically merge two provenance-tagged candidate lists WITHOUT mutating the
    inputs. A candidate is suppressed only by an already-kept candidate of the SAME class
    family that overlaps it by >= cross_iou (a true duplicate of the same visible object);
    overlapping candidates of DIFFERENT classes are both kept, and distinct nearby items
    (low IoU) are preserved. Deterministic: ordered by (-score, class_family, center) so
    equal-confidence ties break the same way every run. Returns NEW dicts (shallow copies)."""
    import math
    if (isinstance(cross_iou, bool) or not isinstance(cross_iou, (int, float))
            or not math.isfinite(cross_iou) or not (0.0 <= cross_iou <= 1.0)):
        raise ValueError(f"cross_iou must be a finite number in [0, 1], got {cross_iou!r}")
    if not (isinstance(max_candidates, int) and not isinstance(max_candidates, bool) and max_candidates >= 0):
        raise ValueError(f"max_candidates must be a non-negative int, got {max_candidates!r}")
    cand = [dict(d, source=d.get("source", "yolo-coco")) for d in yolo] + \
           [dict(d, source=d.get("source", "owlv2")) for d in owl]
    # Complete, stable ordering: highest confidence first, then a total tie-break over
    # normalized family, source, box geometry and label — so permuting equal-confidence
    # candidates yields byte-identical output every run.
    cand.sort(key=lambda d: (-float(d.get("score", 0.0)), _class_family(d.get("query")),
                             str(d.get("source", "")),
                             float(d.get("center_x", 0.0)), float(d.get("center_y", 0.0)),
                             float(d.get("x", 0.0)), float(d.get("y", 0.0)),
                             float(d.get("width", 0.0)), float(d.get("height", 0.0)),
                             str(d.get("query", ""))))
    kept: list[dict[str, Any]] = []
    for d in cand:
        fam = _class_family(d.get("query"))
        if any(_class_family(k.get("query")) == fam and iou(d, k) >= cross_iou for k in kept):
            continue   # same-class duplicate of an already-kept (higher-score) object
        kept.append(d)
    return kept[:max_candidates]


def detect_hybrid_with_status(
    image: Any, *, owl_detector: Callable[[Any], list[dict[str, Any]]] | None = None,
    yolo_conf: float = 0.25,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the hybrid detector and return (detections, status). Status DISTINGUISHES a YOLO
    inference FAILURE / model UNAVAILABLE from a genuine SUCCESS-with-zero-detections, and
    reports OWLv2 success/failure + merge completion. A YOLO problem degrades to OWLv2-only
    (fallback preserved); an OWLv2 failure RE-RAISES so the caller treats it as a genuine
    detector outage (NOT_VALIDATABLE), never as a real zero-detection. No secrets/paths logged."""
    # Normalize ONCE (rejects malformed input up front, never a silent zero result) so both
    # detectors receive a form they accept (str path or PIL.Image), incl. bytes/arrays.
    image = _normalize_image(image)
    status: dict[str, Any] = {"yolo_status": "SUCCESS_ZERO", "yolo_count": 0,
                              "owlv2_status": None, "owlv2_count": 0, "merge": "NOT_RUN",
                              "merged_count": 0}
    y: list[dict[str, Any]] = []
    try:
        y = detect_yolo_coco(image, conf=yolo_conf)
        status["yolo_status"] = "SUCCESS_WITH_DETECTIONS" if y else "SUCCESS_ZERO"
        status["yolo_count"] = len(y)
    except (ImportError, FileNotFoundError, OSError) as exc:
        status["yolo_status"] = "UNAVAILABLE"; status["yolo_error"] = type(exc).__name__
        logger.warning("hybrid: YOLO unavailable (%s) — falling back to OWLv2-only", type(exc).__name__)
    except Exception as exc:  # noqa: BLE001 — model loaded but inference failed
        status["yolo_status"] = "INFERENCE_FAILURE"; status["yolo_error"] = type(exc).__name__
        logger.warning("hybrid: YOLO inference failed (%s) — falling back to OWLv2-only", type(exc).__name__)
    try:
        o = (owl_detector or detect_owlv2)(image)
        status["owlv2_status"] = "SUCCESS"; status["owlv2_count"] = len(o)
    except Exception as exc:  # noqa: BLE001 — OWLv2 is the primary open-vocab source
        status["owlv2_status"] = "FAILURE"; status["owlv2_error"] = type(exc).__name__
        logger.warning("hybrid: OWLv2 failed (%s) — re-raising (detector outage, NOT a zero result)",
                       type(exc).__name__)
        raise
    merged = merge_candidates(y, o)
    status["merge"] = "COMPLETED"; status["merged_count"] = len(merged)
    logger.info("hybrid detect: yolo=%s(%d) owlv2=%s(%d) merged=%d",
                status["yolo_status"], status["yolo_count"], status["owlv2_status"],
                status["owlv2_count"], status["merged_count"])
    return merged, status


def detect_hybrid(image: Any, *, owl_detector: Callable[[Any], list[dict[str, Any]]] | None = None,
                  yolo_conf: float = 0.25) -> list[dict[str, Any]]:
    """COCO YOLO ∪ OWLv2 (schema-compatible list return). YOLO problems degrade to OWLv2-only;
    an OWLv2 outage propagates. See ``detect_hybrid_with_status`` for the structured status."""
    merged, _ = detect_hybrid_with_status(image, owl_detector=owl_detector, yolo_conf=yolo_conf)
    return merged
