"""Furniture / fixture detection — CANDIDATE layer (audit stage 6, reinforced).

Wraps the existing YOLO object-detection pipeline (``app.services.ml``) and turns
its raw detections into a NORMALIZED CANDIDATE structure. Candidates are proposals
only — NEVER canonical truth. This service never writes canonical, never moves an
object to fit a room, never invents or duplicates furniture, and never silently
merges two objects.

    {
      "candidates": [
        {"id","item_id","class_name","bbox":[x1,y1,x2,y2],"cx","cy","w","h",
         "rotation","confidence","low_confidence","status":"CANDIDATE"|"UNCERTAIN",
         "overlaps":[...ids], "source":"yolo"}
      ],
      "image_size":[w,h]|null, "source":"yolo|none",
      "note": "candidates are proposals, NOT canonical truth",
      "stats": {...}
    }

Deterministic rules:
- Exact duplicate (same class AND boxes overlap ≥ dedup_iou) → keep the
  higher-confidence one (never a fabricated duplicate). Distinct instances of the
  same class at different positions are ALL kept (multiple identical objects).
- Two DIFFERENT-class boxes overlapping ≥ ambiguous_iou are both kept and marked
  UNCERTAIN with cross-references — never merged into one.
- Confidence is preserved verbatim; below ``min_confidence`` → UNCERTAIN (kept, not
  deleted); below ``drop_below`` → dropped as noise.
- bbox/centre/size are preserved from the detector; rotation is preserved when the
  detector supplies it (OBB models) and defaults to 0 otherwise.
No FLUX / no img2img / no image generation anywhere.
"""

from __future__ import annotations

from typing import Any

from app.data.classes import CLASS_BY_NAME, ml_class_to_item_id

_NOTE = "candidates are proposals, NOT canonical truth"
_LOW_CONF = 0.5


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


def _bbox_of(raw: dict[str, Any]) -> list[float] | None:
    """Extract [x1,y1,x2,y2] from a raw detection (accepts bbox or centre+w/h)."""
    b = raw.get("bbox")
    if isinstance(b, dict):
        if all(k in b for k in ("x1", "y1", "x2", "y2")):
            return [float(b["x1"]), float(b["y1"]), float(b["x2"]), float(b["y2"])]
        if all(k in b for k in ("cx", "cy", "w", "h")):
            cx, cy, w, h = float(b["cx"]), float(b["cy"]), float(b["w"]), float(b["h"])
            return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
    if isinstance(b, (list | tuple)) and len(b) >= 4:
        return [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
    if all(k in raw for k in ("cx", "cy", "w", "h")):
        cx, cy, w, h = float(raw["cx"]), float(raw["cy"]), float(raw["w"]), float(raw["h"])
        return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
    return None


def build_candidates(
    raw_detections: list[dict[str, Any]],
    image_size: tuple[int, int] | None = None,
    min_confidence: float = 0.25,
    drop_below: float = 0.05,
    dedup_iou: float = 0.85,
    ambiguous_iou: float = 0.5,
    source: str = "yolo",
) -> dict[str, Any]:
    """Normalize raw detector output into candidate objects. Deterministic; invents
    nothing; preserves detector coordinates/confidence/rotation."""
    prelim: list[dict[str, Any]] = []
    for k, raw in enumerate(raw_detections):
        cls = str(raw.get("class_name") or raw.get("class") or raw.get("cls") or "").strip()
        if not cls:
            continue
        conf = float(raw.get("confidence", raw.get("conf", 0.0)))
        if conf < drop_below:
            continue  # detector noise
        bbox = _bbox_of(raw)
        if bbox is None:
            continue
        x1, y1, x2, y2 = bbox
        w, h = abs(x2 - x1), abs(y2 - y1)
        if w <= 0 or h <= 0:
            continue
        item_id = raw.get("item_id") or ml_class_to_item_id(cls)
        prelim.append({
            "id": raw.get("id") or f"cand_{k}",
            "class_name": cls,
            "item_id": item_id,
            "known_class": cls in CLASS_BY_NAME,
            "bbox": [round(v, 2) for v in bbox],
            "cx": round((x1 + x2) / 2, 2),
            "cy": round((y1 + y2) / 2, 2),
            "w": round(w, 2),
            "h": round(h, 2),
            "rotation": round(float(raw.get("rotation", raw.get("rotation_deg", 0.0)) or 0.0), 2),
            "confidence": round(conf, 4),
            "low_confidence": conf < _LOW_CONF,
            "status": "CANDIDATE",
            "overlaps": [],
            "source": source,
        })

    # 1) Drop EXACT duplicates: same class + near-identical box → keep highest conf.
    prelim.sort(key=lambda c: (-c["confidence"], c["id"]))
    kept: list[dict[str, Any]] = []
    for c in prelim:
        dup = any(
            k["class_name"] == c["class_name"] and _iou(c["bbox"], k["bbox"]) >= dedup_iou
            for k in kept
        )
        if not dup:
            kept.append(c)

    # 2) Flag ambiguous overlaps (any class pair) — mark UNCERTAIN, never merge.
    for i in range(len(kept)):
        for j in range(i + 1, len(kept)):
            if _iou(kept[i]["bbox"], kept[j]["bbox"]) >= ambiguous_iou:
                kept[i]["status"] = kept[j]["status"] = "UNCERTAIN"
                kept[i]["overlaps"].append(kept[j]["id"])
                kept[j]["overlaps"].append(kept[i]["id"])

    # 3) Low confidence → UNCERTAIN (kept, honest), and normalized bbox if size known.
    for c in kept:
        if c["confidence"] < min_confidence:
            c["status"] = "UNCERTAIN"
        if image_size and image_size[0] and image_size[1]:
            x1, y1, x2, y2 = c["bbox"]
            c["bbox_normalized"] = [round(x1 / image_size[0], 5), round(y1 / image_size[1], 5),
                                    round(x2 / image_size[0], 5), round(y2 / image_size[1], 5)]

    kept.sort(key=lambda c: (round(c["cy"], 1), round(c["cx"], 1)))

    from collections import Counter
    by_class = dict(Counter(c["class_name"] for c in kept))
    return {
        "candidates": kept,
        "image_size": list(image_size) if image_size else None,
        "source": source if kept else source,
        "note": _NOTE,
        "stats": {
            "total": len(kept),
            "candidate": sum(1 for c in kept if c["status"] == "CANDIDATE"),
            "uncertain": sum(1 for c in kept if c["status"] == "UNCERTAIN"),
            "low_confidence": sum(1 for c in kept if c["low_confidence"]),
            "by_class": by_class,
        },
    }


def detect_candidates(
    pil_image,
    min_confidence: float = 0.25,
    dedup_iou: float = 0.85,
    ambiguous_iou: float = 0.5,
) -> dict[str, Any]:
    """Run the existing YOLO pipeline on an image and return candidate objects.

    Uses ``FloorPlanInferenceService`` where the model is available. If ML is
    disabled or no model/detections are present, returns an empty candidate set
    (never fabricates furniture). Candidates are proposals, not canonical.
    """
    size = getattr(pil_image, "size", None)
    try:
        from app.services.ml.inference import FloorPlanInferenceService
        service = FloorPlanInferenceService()
        raw = service.detect_objects(pil_image, confidence_threshold=min_confidence)
    except Exception:  # noqa: BLE001 — no model / ML disabled → no candidates (honest)
        return {
            "candidates": [], "image_size": list(size) if size else None,
            "source": "none", "note": _NOTE,
            "stats": {"total": 0, "candidate": 0, "uncertain": 0,
                      "low_confidence": 0, "by_class": {}},
        }
    # Normalize inference dicts → the raw shape build_candidates expects.
    normed: list[dict[str, Any]] = []
    for d in raw:
        pos = d.get("position") or {}
        normed.append({
            "id": d.get("id"),
            "class_name": d.get("class") or d.get("class_name"),
            "item_id": d.get("item_id"),
            "cx": pos.get("cx"), "cy": pos.get("cy"), "w": pos.get("w"), "h": pos.get("h"),
            "bbox": d.get("bbox"),
            "confidence": d.get("confidence", 0.0),
            "rotation": d.get("rotation_deg", d.get("rotation", 0.0)),
        })
    return build_candidates(
        normed, image_size=size, min_confidence=min_confidence,
        dedup_iou=dedup_iou, ambiguous_iou=ambiguous_iou, source="yolo",
    )
