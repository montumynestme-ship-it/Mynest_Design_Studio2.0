"""AUDIT-ONLY prototype: AI-output furniture spatial-preservation check (Step 2 family).

Detects generic furniture candidates in the photoreal FAL AI output with OWLv2
(open-vocabulary, via transformers), then matches those boxes to the DETERMINISTIC
base-render furniture boxes by SPATIAL assignment (identity comes from the base boxes,
never from the detector's class names). Produces numerical evidence of GROSS spatial
preservation (moved / missing / duplicated / resized) — NOT pixel-perfect proof.

Not wired into production. Never modifies canonical/geometry/camera/FAL/inventory.
Run: python scripts/ai_output_localization_audit.py <base_boxes.json> <ai_image.png>
"""

from __future__ import annotations

import itertools
import json
import os
import sys

# Keep the (large) model cache off the nearly-full C: drive.
os.environ.setdefault("HF_HOME", r"D:\hf_cache")

# Generic furniture vocabulary — DETECTION ONLY. These labels are NOT used as MyNest
# identity; identity is assigned later by spatial match to the base boxes.
QUERIES = [
    "a bed", "a wardrobe", "a tall cabinet with doors", "a chest of drawers",
    "a dresser", "a bedside table", "a nightstand", "a side table",
    "a dressing table", "a desk", "a chair",
]
SCORE_THRESHOLD = 0.08
NMS_IOU = 0.5
MAX_AI_CANDIDATES = 15
GATE_FRACTION = 0.20  # max matchable center distance as a fraction of the image diagonal


def _iou(a: dict, b: dict) -> float:
    ax1, ay1, ax2, ay2 = a["x"], a["y"], a["x"] + a["width"], a["y"] + a["height"]
    bx1, by1, bx2, by2 = b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]
    ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def detect_owlv2(image_path: str) -> list[dict]:
    import torch
    from PIL import Image
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    model_id = "google/owlv2-base-patch16-ensemble"
    proc = Owlv2Processor.from_pretrained(model_id)
    model = Owlv2ForObjectDetection.from_pretrained(model_id)
    model.eval()
    img = Image.open(image_path).convert("RGB")
    inputs = proc(text=[QUERIES], images=img, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    target_sizes = torch.tensor([img.size[::-1]])  # (h, w)
    # transformers renamed this; OWLv2 uses the "grounded" post-processor.
    if hasattr(proc, "post_process_grounded_object_detection"):
        res = proc.post_process_grounded_object_detection(
            outputs, threshold=SCORE_THRESHOLD, target_sizes=target_sizes)[0]
    else:  # older transformers fallback
        res = proc.post_process_object_detection(
            outputs, threshold=SCORE_THRESHOLD, target_sizes=target_sizes)[0]
    labels = res.get("labels")
    text_labels = res.get("text_labels")
    dets: list[dict] = []
    for i, (box, score) in enumerate(zip(res["boxes"].tolist(), res["scores"].tolist())):
        if text_labels is not None:
            q = str(text_labels[i])
        else:
            li = int(labels[i]) if labels is not None else -1
            q = QUERIES[li] if 0 <= li < len(QUERIES) else "furniture"
        x1, y1, x2, y2 = box
        dets.append({"query": q, "score": round(float(score), 4),
                     "x": round(x1, 1), "y": round(y1, 1),
                     "width": round(x2 - x1, 1), "height": round(y2 - y1, 1),
                     "center_x": round((x1 + x2) / 2, 1), "center_y": round((y1 + y2) / 2, 1)})
    # Greedy NMS across ALL queries (distinct physical boxes; class name ignored).
    dets.sort(key=lambda d: -d["score"])
    kept: list[dict] = []
    for d in dets:
        if all(_iou(d, k) < NMS_IOU for k in kept):
            kept.append(d)
    return kept[:MAX_AI_CANDIDATES]


def _center_dist(a: dict, b: dict) -> float:
    return ((a["center_x"] - b["center_x"]) ** 2 + (a["center_y"] - b["center_y"]) ** 2) ** 0.5


def optimal_assignment(base: list[dict], ai: list[dict], gate: float) -> dict[int, int]:
    """Injective base->ai assignment minimizing total center distance, with a hard gate
    (a pair beyond `gate` px can never be matched). Brute-force optimal (small n) — the
    Hungarian result for these sizes. Returns {base_idx: ai_idx}."""
    INF = float("inf")
    cost = [[_center_dist(b, a) if _center_dist(b, a) <= gate else INF for a in ai] for b in base]
    nb = len(base)
    best = {"total": INF, "assign": {}}
    ai_idxs = list(range(len(ai)))
    # choose an ordered selection of nb ai candidates (one per base), allowing "unmatched"
    # by padding with a sentinel -1.
    padded = ai_idxs + [-1] * nb
    seen = set()
    for perm in itertools.permutations(padded, nb):
        if perm in seen:
            continue
        seen.add(perm)
        total = 0.0
        ok = True
        for bi, aj in enumerate(perm):
            if aj == -1:
                total += gate  # penalty for leaving a base object unmatched
                continue
            c = cost[bi][aj]
            if c == INF:
                ok = False
                break
            total += c
        if ok and total < best["total"]:
            best = {"total": total, "assign": {bi: aj for bi, aj in enumerate(perm) if aj != -1}}
    return best["assign"]


def build_report(base_path: str, image_path: str) -> dict:
    data = json.load(open(base_path))
    base = data["base_boxes"]
    W, H = data.get("width", 1216), data.get("height", 832)
    gate = GATE_FRACTION * (W ** 2 + H ** 2) ** 0.5
    ai = detect_owlv2(image_path)
    assign = optimal_assignment(base, ai, gate)

    objects = []
    matched_ai = set(assign.values())
    for bi, b in enumerate(base):
        aj = assign.get(bi)
        if aj is None:
            objects.append({"uid": b["uid"], "item_id": b["item_id"],
                            "base_center": [b["center_x"], b["center_y"]],
                            "base_bbox": [b["x"], b["y"], b["width"], b["height"]],
                            "ai_center": None, "ai_bbox": None,
                            "center_delta_x": None, "center_delta_y": None,
                            "iou": 0.0, "scale_ratio": None, "status": "UNCERTAIN"})
            continue
        a = ai[aj]
        base_area = max(1.0, b["width"] * b["height"])
        ai_area = a["width"] * a["height"]
        objects.append({
            "uid": b["uid"], "item_id": b["item_id"],
            "base_center": [b["center_x"], b["center_y"]],
            "ai_center": [a["center_x"], a["center_y"]],
            "center_delta_x": round(a["center_x"] - b["center_x"], 1),
            "center_delta_y": round(a["center_y"] - b["center_y"], 1),
            "base_bbox": [b["x"], b["y"], b["width"], b["height"]],
            "ai_bbox": [a["x"], a["y"], a["width"], a["height"]],
            "iou": round(_iou(b, a), 3),
            "scale_ratio": round((ai_area / base_area) ** 0.5, 3),
            "detector_query": a["query"], "detector_score": a["score"],
            "status": "MATCHED",
        })
    extra = [ai[j] for j in range(len(ai)) if j not in matched_ai]
    missing = [o for o in objects if o["status"] == "UNCERTAIN"]
    overall = "UNCERTAIN" if missing else "MATCHED_PENDING_TOLERANCE"
    return {"detector": "OWLv2 (google/owlv2-base-patch16-ensemble)",
            "image": data.get("image"), "gate_px": round(gate, 1),
            "ai_detections": ai, "objects": objects,
            "extra_ai_boxes": extra, "missing_count": len(missing),
            "overall": overall}


if __name__ == "__main__":
    bp = sys.argv[1]
    ip = sys.argv[2]
    rep = build_report(bp, ip)
    print(json.dumps(rep, indent=2))
