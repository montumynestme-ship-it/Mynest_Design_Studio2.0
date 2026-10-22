"""Advisory object-level AI GEOMETRY validation (SEPARATE from inventory validation).

Inventory validation answers: "is the expected furniture TYPE/COUNT present?".
This module answers a DIFFERENT question: "is the SAME object in the SAME place?".

Identity comes from the DETERMINISTIC base-render boxes (uid/item_id), never from the
detector's labels. The AI output is localized by an open-vocabulary detector (OWLv2
first; GroundingDINO is a possible fallback), then matched one-to-one to the base boxes
by spatial assignment (Hungarian / center-distance + IoU + a max-distance gate).

It proves only GROSS spatial preservation (moved / missing / duplicated / grossly
resized) — never pixel-exact position, scale, or orientation. It NEVER renders, never
calls FAL, never edits canonical/geometry/inventory, and NEVER converts uncertainty into
PASS. Statuses: PASS / FAIL / UNCERTAIN / NOT_VALIDATABLE.

Thresholds below are conservative DEFAULTS that MUST be calibrated empirically on a
labeled render set before any gating use; they are not tuned to make a case pass.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable

# ── calibration thresholds (defaults — require empirical calibration) ─────────
# NOTE: GATE must exceed FAIL so a matched-but-displaced object is a provable FAIL
# (a displacement beyond the gate cannot be associated and stays UNCERTAIN/missing).
GATE_FRACTION = 0.28          # max matchable center distance, as a fraction of the diagonal
PASS_CENTER_FRACTION = 0.06   # center delta <= 6% of the diagonal → positionally preserved
FAIL_CENTER_FRACTION = 0.20   # matched but center delta > 20% of the diagonal (confident) → displaced
PASS_IOU = 0.30               # supporting overlap for a PASS
MIN_DET_CONF = 0.25           # below this a detection cannot confirm a match
STRONG_DET_CONF = 0.50        # confidence required to assert a FAIL (proven defect)

_OBJ_STATUSES = {"PASS", "FAIL", "UNCERTAIN", "NOT_VALIDATABLE"}


# ── geometry helpers ──────────────────────────────────────────────────────────

def _xywh(b: dict[str, Any]) -> tuple[float, float, float, float]:
    return float(b["x"]), float(b["y"]), float(b["width"]), float(b["height"])


def iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax, ay, aw, ah = _xywh(a); bx, by, bw, bh = _xywh(b)
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _center(b: dict[str, Any]) -> tuple[float, float]:
    if "center_x" in b and "center_y" in b:
        return float(b["center_x"]), float(b["center_y"])
    x, y, w, h = _xywh(b)
    return x + w / 2, y + h / 2


def center_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax, ay = _center(a); bx, by = _center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def optimal_assignment(base: list[dict[str, Any]], ai: list[dict[str, Any]],
                       gate: float) -> dict[int, int]:
    """Injective base->ai assignment minimizing total (center_distance + IoU penalty),
    with a hard gate (a pair beyond ``gate`` px is never matched). Brute-force optimal
    (small n) — equivalent to Hungarian at these sizes. Returns {base_idx: ai_idx}."""
    INF = float("inf")
    cost = [[(center_distance(b, a) + (1.0 - iou(b, a)) * gate * 0.25)
             if center_distance(b, a) <= gate else INF
             for a in ai] for b in base]
    nb = len(base)
    if nb == 0:
        return {}
    padded = list(range(len(ai))) + [-1] * nb   # -1 = leave this base unmatched
    best = {"total": INF, "assign": {}}
    seen: set[tuple[int, ...]] = set()
    for perm in itertools.permutations(padded, nb):
        if perm in seen:
            continue
        seen.add(perm)
        total = 0.0
        ok = True
        for bi, aj in enumerate(perm):
            if aj == -1:
                # Unmatched penalty must exceed the worst in-gate match cost
                # (gate + IoU penalty = gate*1.25), so a detection within the gate is
                # always matched (even if displaced → FAIL) rather than dropped.
                total += gate * 1.5
                continue
            c = cost[bi][aj]
            if c == INF:
                ok = False
                break
            total += c
        if ok and total < best["total"]:
            best = {"total": total, "assign": {bi: aj for bi, aj in enumerate(perm) if aj != -1}}
    return best["assign"]


# ── core comparison (deterministic; detector output is the input) ────────────

def compare_geometry(
    base_boxes: list[dict[str, Any]],
    ai_boxes: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    gate_fraction: float = GATE_FRACTION,
    pass_center_fraction: float = PASS_CENTER_FRACTION,
    fail_center_fraction: float = FAIL_CENTER_FRACTION,
    pass_iou: float = PASS_IOU,
    min_det_conf: float = MIN_DET_CONF,
    strong_det_conf: float = STRONG_DET_CONF,
) -> dict[str, Any]:
    """Compare deterministic base boxes to detected AI boxes. Each base object (identity
    from uid/item_id) gets a per-object geometry result. Gross-only."""
    diag = (image_width ** 2 + image_height ** 2) ** 0.5
    gate = gate_fraction * diag
    pass_tol = pass_center_fraction * diag
    fail_tol = fail_center_fraction * diag

    assign = optimal_assignment(base_boxes, ai_boxes, gate)
    matched_ai = set(assign.values())
    objects: list[dict[str, Any]] = []
    for bi, b in enumerate(base_boxes):
        bc = _center(b)
        rec: dict[str, Any] = {
            "uid": b.get("uid"), "item_id": b.get("item_id"),
            "base_bbox": [round(v, 1) for v in _xywh(b)], "base_center": [round(bc[0], 1), round(bc[1], 1)],
            "ai_bbox": None, "ai_center": None,
            "center_delta_x": None, "center_delta_y": None, "iou": 0.0,
            "scale_ratio": None, "detection_confidence": None, "match_status": "NOT_VALIDATABLE",
        }
        aj = assign.get(bi)
        if aj is None:
            rec["match_status"] = "UNCERTAIN"   # not localized → cannot prove moved OR absent
            rec["reason"] = "no AI detection matched within the gate (under-detection)"
            objects.append(rec)
            continue
        a = ai_boxes[aj]
        ac = _center(a)
        cd = center_distance(b, a)
        base_area = max(1.0, float(b["width"]) * float(b["height"]))
        ai_area = float(a["width"]) * float(a["height"])
        det_conf = float(a.get("score", a.get("confidence", 0.0) or 0.0))
        iou_v = iou(b, a)
        rec.update({
            "ai_bbox": [round(v, 1) for v in _xywh(a)], "ai_center": [round(ac[0], 1), round(ac[1], 1)],
            "center_delta_x": round(ac[0] - bc[0], 1), "center_delta_y": round(ac[1] - bc[1], 1),
            "iou": round(iou_v, 3), "scale_ratio": round((ai_area / base_area) ** 0.5, 3),
            "detection_confidence": round(det_conf, 3),
        })
        if cd <= pass_tol and iou_v >= pass_iou and det_conf >= min_det_conf:
            rec["match_status"] = "PASS"
        elif cd > fail_tol and det_conf >= strong_det_conf:
            rec["match_status"] = "FAIL"   # confidently localized far from base → displaced
            rec["reason"] = f"center displaced {round(cd,1)}px (> {round(fail_tol,1)}) at conf {round(det_conf,2)}"
        else:
            rec["match_status"] = "UNCERTAIN"
            rec["reason"] = "matched but delta/IoU/confidence insufficient to confirm preservation"
        objects.append(rec)

    extra = [{"index": j, **{k: ai_boxes[j].get(k) for k in ("query", "score", "center_x", "center_y")}}
             for j in range(len(ai_boxes)) if j not in matched_ai]

    statuses = {o["match_status"] for o in objects}
    if not base_boxes:
        overall = "NOT_VALIDATABLE"
    elif "FAIL" in statuses:
        overall = "FAIL"
    elif statuses <= {"PASS"}:
        overall = "PASS"
    else:
        overall = "UNCERTAIN"
    return {
        "overall_status": overall,
        "image_width": image_width, "image_height": image_height,
        "gate_px": round(gate, 1), "pass_center_px": round(pass_tol, 1), "fail_center_px": round(fail_tol, 1),
        "objects": objects, "extra_ai_boxes": extra,
        "matched": sum(1 for o in objects if o["match_status"] == "PASS"),
        "uncertain": sum(1 for o in objects if o["match_status"] == "UNCERTAIN"),
        "failed": sum(1 for o in objects if o["match_status"] == "FAIL"),
    }


def compare_openings(
    base_openings: list[dict[str, Any]],
    ai_boxes: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    **kw: Any,
) -> dict[str, Any]:
    """Opening geometry: same spatial match, plus room/wall/wall-relative carried from the
    AUTHORITATIVE base opening boxes. AI-side wall association is NOT inferred — it stays
    NOT_VALIDATABLE unless a reliable AI wall measurement is supplied."""
    rep = compare_geometry(base_openings, ai_boxes, image_width=image_width,
                           image_height=image_height, **kw)
    by_uid = {str(b.get("uid")): b for b in base_openings}
    for o in rep["objects"]:
        src = by_uid.get(str(o["uid"]), {})
        o["opening_id"] = o["uid"]
        o["type"] = src.get("item_id")
        o["room"] = src.get("room")
        o["wall"] = src.get("wall")
        o["wall_relative_position"] = src.get("wall_relative_position")
        o["normalized_wall_position"] = src.get("normalized_wall_position")
        o["ai_wall_association"] = "NOT_VALIDATABLE"   # never inferred from furniture/pixels
    return rep


# ── optional OWLv2 detector (gated; not required for the matcher or CI) ───────

OWLV2_QUERIES = [
    "a bed", "a wardrobe", "a tall cabinet", "a chest of drawers", "a dresser",
    "a bedside table", "a side table", "a dressing table", "a desk", "a chair",
    "a sofa", "a couch", "a coffee table", "a tv unit", "a dining table",
    "a dining chair", "a kitchen cabinet", "a door", "a window",
]


def detect_owlv2(image: Any, queries: list[str] | None = None, *,
                 score_threshold: float = 0.08, nms_iou: float = 0.5,
                 max_candidates: int = 25) -> list[dict[str, Any]]:
    """Open-vocabulary detection on the AI image with OWLv2 (transformers). Returns boxes
    {query, score, x, y, width, height, center_x, center_y}. Labels are NOT identity."""
    import torch
    from PIL import Image as PILImage
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    q = queries or OWLV2_QUERIES
    mid = "google/owlv2-base-patch16-ensemble"
    proc = Owlv2Processor.from_pretrained(mid)
    model = Owlv2ForObjectDetection.from_pretrained(mid)
    model.eval()
    img = image if isinstance(image, PILImage.Image) else PILImage.open(image).convert("RGB")
    inputs = proc(text=[q], images=img, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    ts = torch.tensor([img.size[::-1]])
    if hasattr(proc, "post_process_grounded_object_detection"):
        res = proc.post_process_grounded_object_detection(outputs, threshold=score_threshold, target_sizes=ts)[0]
    else:
        res = proc.post_process_object_detection(outputs, threshold=score_threshold, target_sizes=ts)[0]
    tl = res.get("text_labels"); labs = res.get("labels")
    dets: list[dict[str, Any]] = []
    for i, (box, score) in enumerate(zip(res["boxes"].tolist(), res["scores"].tolist())):
        lbl = str(tl[i]) if tl is not None else (q[int(labs[i])] if labs is not None else "furniture")
        x1, y1, x2, y2 = box
        dets.append({"query": lbl, "score": round(float(score), 4),
                     "x": round(x1, 1), "y": round(y1, 1), "width": round(x2 - x1, 1), "height": round(y2 - y1, 1),
                     "center_x": round((x1 + x2) / 2, 1), "center_y": round((y1 + y2) / 2, 1)})
    return nms_dedup(dets, nms_iou=nms_iou, max_candidates=max_candidates)


def nms_dedup(dets: list[dict[str, Any]], *, nms_iou: float = 0.5,
              max_candidates: int = 25) -> list[dict[str, Any]]:
    """Deterministic greedy non-max suppression for detector boxes. Boxes are ordered by score
    (desc, stable) and a box is kept unless it overlaps an already-kept box by >= nms_iou; the
    result is capped at max_candidates. Pure and ORDER-INDEPENDENT (the sort makes the output
    independent of the input order), so repeated/duplicate detections are suppressed the same
    way every run. Extracted so the suppression is unit-testable without loading OWLv2."""
    ordered = sorted(dets, key=lambda d: -float(d.get("score", 0.0)))
    kept: list[dict[str, Any]] = []
    for d in ordered:
        if all(iou(d, k) < nms_iou for k in kept):
            kept.append(d)
    return kept[:max_candidates]


def run_geometry_validation(
    base_boxes: list[dict[str, Any]],
    ai_image: Any | None,
    *,
    base_openings: list[dict[str, Any]] | None = None,
    image_width: int = 1216,
    image_height: int = 832,
    detector: Callable[[Any], list[dict[str, Any]]] | None = None,
    **kw: Any,
) -> dict[str, Any]:
    """Orchestrate AI geometry validation. ``detector`` defaults to OWLv2; inject a stub in
    tests. NOT_VALIDATABLE when the base boxes or the AI image/detector are unavailable."""
    if not base_boxes and not (base_openings or []):
        return {"overall_status": "NOT_VALIDATABLE", "reason": "no deterministic base boxes available"}
    if ai_image is None:
        return {"overall_status": "NOT_VALIDATABLE", "reason": "no AI output image available"}
    det = detector or detect_owlv2
    try:
        ai_boxes = det(ai_image)
    except Exception as exc:  # noqa: BLE001 — detector unavailable → not validatable, never PASS
        return {"overall_status": "NOT_VALIDATABLE", "reason": f"detector unavailable: {type(exc).__name__}"}

    furn = compare_geometry(base_boxes, ai_boxes, image_width=image_width, image_height=image_height, **kw)
    openings = (compare_openings(base_openings, ai_boxes, image_width=image_width, image_height=image_height, **kw)
                if base_openings else None)
    overalls = [furn["overall_status"]] + ([openings["overall_status"]] if openings else [])
    if "FAIL" in overalls:
        overall = "FAIL"
    elif all(o == "PASS" for o in overalls):
        overall = "PASS"
    elif all(o == "NOT_VALIDATABLE" for o in overalls):
        overall = "NOT_VALIDATABLE"
    else:
        overall = "UNCERTAIN"
    return {"overall_status": overall, "furniture": furn, "openings": openings,
            "detector": "owlv2" if detector is None else "injected",
            "ai_detection_count": len(ai_boxes)}
