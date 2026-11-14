"""Object-level AI GEOMETRY validation (Task 8) — a STRONGER, deterministic layer on top
of ``furniture_geometry_validation_service``.

It answers, per canonical object: "is the SAME object in the SAME place, scale and relative
ordering in the AI render?" using a DETERMINISTIC one-to-one assignment whose cost combines
center distance + IoU + scale + relative-ordering (not center distance alone), and emits the
Task-8 object-level report schema.

Hard invariants (enforced by tests):
  * Identity comes ONLY from the deterministic base registry (uid/item_id/room/wall) — never
    from the detector's labels, and the AI output NEVER overwrites the registry.
  * This module NEVER renders, calls FAL, or mutates canonical/scene/wall/room/opening data.
  * Missing / low-confidence / ambiguous detection => UNCERTAIN, never FAIL. A FAIL requires
    a RELIABLE detection that proves displacement / gross rescale / impossible ordering.
  * Rotation is NOT_VALIDATABLE (axis-aligned OWLv2 boxes cannot prove orientation).
  * Opening AI-side wall association is NOT_VALIDATABLE (OWLv2 cannot prove a wall).
  * Thresholds are documented first-principles DEFAULTS, NOT tuned to any single render; until
    calibrated on a multi-room set the gating status is reported as NOT_CALIBRATED.

Audit-only: it is not a production render gate.
"""

from __future__ import annotations

from typing import Any, Callable

# Reuse the Task-7 geometry primitives + OWLv2 detector (do NOT duplicate them).
from app.services.furniture_geometry_validation_service import (
    _center, _xywh, center_distance, detect_owlv2, iou,
)

# ── documented matching cost weights (constants; not tuned to any one render) ──
# The cost blends four orthogonal geometric signals. Weights are chosen by relative
# importance, NOT fitted to a case: center distance dominates (it is the strongest
# "moved" signal), IoU reinforces it, scale is secondary (perspective changes apparent
# size a lot), ordering is a light tie-breaker so a swap is preferred-against.
W_CENTER = 1.0    # normalized center distance (0..~1 within the gate)
W_IOU = 0.6       # 1 - IoU
W_SCALE = 0.4     # |log area-ratio| clipped (scale disagreement)
W_ORDER = 0.3     # ordering penalty (0 or 1) relative to the scene anchor

# ── acceptance tolerances (documented DEFAULTS — require calibration before gating) ──
GATE_FRACTION = 0.28          # max matchable center distance / image diagonal
PASS_CENTER_FRACTION = 0.06   # center delta <= 6% diagonal => positionally preserved
FAIL_CENTER_FRACTION = 0.20   # matched + center delta > 20% diagonal (confident) => displaced
PASS_IOU = 0.30               # supporting overlap for PASS
PASS_SCALE_LO, PASS_SCALE_HI = 0.60, 1.70   # linear-scale (sqrt area) ratio band for PASS
FAIL_SCALE_LO, FAIL_SCALE_HI = 0.35, 3.00   # beyond this (confident) => gross rescale FAIL
MIN_DET_CONF = 0.25           # below this a detection cannot CONFIRM a match (=> UNCERTAIN)
STRONG_DET_CONF = 0.50        # confidence required to ASSERT a FAIL (proven defect)
ORDER_DEADZONE_FRAC = 0.03    # |dx|/|dy| below 3% diagonal from the anchor => "center" (no side)
# Match ACCEPTANCE bar — SEPARATE from the (wide) assignment gate. The Hungarian step picks
# the globally-cheapest injective pairing within the gate, but "within the gate" is NOT proof
# the pair is the SAME object. A pairing is accepted as a real match only when it carries
# POSITIVE same-object evidence: a type-consistent label, OR a non-trivial overlap, OR a
# center within the displacement bound (fail_tol). Otherwise it is DISSOLVED — the base object
# becomes an explicit MISSING candidate (UNCERTAIN, never FAIL) and the detection returns to
# the EXTRA pool, so a nearby-but-unrelated detection can no longer silently satisfy a base
# object (which hid the Dining hallucination / dropped furniture).
MATCH_MIN_IOU = 0.05          # minimal overlap that counts as spatial same-object evidence

# Identity corroboration: OWLv2 LABELS are not authoritative identity, but a FAIL (which
# claims a real geometry defect) must not rest on a spatial match + confidence ALONE — the
# matched detection must also be TYPE-CONSISTENT with the base object's item_id. Without
# that, a confident-but-displaced match is treated as a probable MIS-ASSIGNMENT => UNCERTAIN,
# never FAIL. These synonym sets map a canonical item_id to acceptable open-vocab tokens.
_TYPE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "bed": ("bed",),
    "side-table": ("side table", "bedside", "nightstand", "night stand", "end table"),
    "wardrobe": ("wardrobe", "armoire", "closet", "tall cabinet", "cabinet"),
    "dressing-table": ("dressing table", "dresser", "chest of drawers", "vanity", "console"),
    "dining-table": ("dining table", "table"),
    "lounger-sofa": ("sofa", "couch", "lounger", "settee"),
    "console": ("console", "cabinet", "sideboard"),
    "kitchen-base": ("kitchen cabinet", "counter", "cabinet", "worktop"),
    "chimney": ("range hood", "hood", "chimney"),
    "door": ("door",),
    "window": ("window",),
}


def _identity_supported(item_id: str | None, query: str | None) -> bool:
    """True when the detection's open-vocab label is TYPE-CONSISTENT with the canonical
    item_id, i.e. the detector saw the SAME KIND of object. Required before a FAIL is
    allowed. Unknown item_id or missing query => not supported (=> cannot assert FAIL)."""
    if not item_id or not query:
        return False
    q = str(query).lower()
    syns = _TYPE_SYNONYMS.get(str(item_id).lower())
    if syns is None:
        # fall back to the normalized item_id token itself (e.g. "bench")
        syns = (str(item_id).lower().replace("-", " "),)
    return any(s in q for s in syns)


# ── base object registry (authoritative; AI never overwrites it) ───────────────

def _ordering_tokens(cx: float, cy: float, ax: float, ay: float, diag: float) -> dict[str, str]:
    """Discrete ordering of a point relative to the anchor (screen space). A small dead
    zone avoids flagging near-coincident objects as left/right or above/below."""
    dz = ORDER_DEADZONE_FRAC * diag
    horiz = "center" if abs(cx - ax) <= dz else ("right" if cx > ax else "left")
    vert = "center" if abs(cy - ay) <= dz else ("below" if cy > ay else "above")
    return {"horizontal": horiz, "vertical": vert}


def build_object_registry(
    base_furniture: list[dict[str, Any]],
    base_openings: list[dict[str, Any]] | None = None,
    *,
    image_width: int = 1216,
    image_height: int = 832,
) -> dict[str, Any]:
    """Deterministic, authoritative registry from the base-render boxes. Furniture gets a
    scene ANCHOR (the largest-area object) and each object's position/ordering RELATIVE to
    it. Openings carry room/wall/normalized position. Nothing here depends on the AI output."""
    diag = (image_width ** 2 + image_height ** 2) ** 0.5
    furn = list(base_furniture or [])
    anchor_idx = max(range(len(furn)), key=lambda i: float(furn[i]["width"]) * float(furn[i]["height"])) if furn else None
    anchor_center = _center(furn[anchor_idx]) if anchor_idx is not None else (0.0, 0.0)
    anchor_uid = furn[anchor_idx].get("uid") if anchor_idx is not None else None

    objects = []
    for i, b in enumerate(furn):
        cx, cy = _center(b)
        objects.append({
            "uid": b.get("uid"), "item_id": b.get("item_id"), "room": b.get("room"),
            "base_bbox": [round(v, 2) for v in _xywh(b)], "base_center": [round(cx, 2), round(cy, 2)],
            "base_width": round(float(b["width"]), 2), "base_height": round(float(b["height"]), 2),
            "rotation": b.get("rotation"),
            "is_anchor": (i == anchor_idx),
            "relative_position": {"dx": round(cx - anchor_center[0], 2), "dy": round(cy - anchor_center[1], 2),
                                  **_ordering_tokens(cx, cy, anchor_center[0], anchor_center[1], diag)},
            "ordering": i,
        })
    openings = []
    for o in (base_openings or []):
        cx, cy = _center(o)
        openings.append({
            "opening_id": o.get("uid") or o.get("opening_id"), "type": o.get("item_id") or o.get("type"),
            "room": o.get("room"), "wall": o.get("wall"),
            "base_bbox": [round(v, 2) for v in _xywh(o)], "base_center": [round(cx, 2), round(cy, 2)],
            "width": round(float(o["width"]), 2), "height": round(float(o["height"]), 2),
            "normalized_wall_position": o.get("normalized_wall_position"),
            "rotation": o.get("rotation"),
        })
    return {"anchor_uid": anchor_uid, "anchor_center": [round(anchor_center[0], 2), round(anchor_center[1], 2)],
            "image_width": image_width, "image_height": image_height, "diag": round(diag, 2),
            "objects": objects, "openings": openings}


# ── deterministic one-to-one assignment with the documented blended cost ───────

def _scale_error(b: dict[str, Any], a: dict[str, Any]) -> float:
    import math
    ba = max(1.0, float(b["width"]) * float(b["height"]))
    aa = max(1.0, float(a["width"]) * float(a["height"]))
    return min(1.5, abs(math.log((aa / ba) ** 0.5)))  # |log linear-scale ratio|, clipped


def pair_cost(b: dict[str, Any], a: dict[str, Any], *, gate: float, diag: float,
              anchor_base: tuple[float, float] | None, anchor_ai: tuple[float, float] | None) -> float:
    """Documented blended cost for one (base, ai) pair, or +inf beyond the gate.
    cost = W_CENTER*normCenter + W_IOU*(1-IoU) + W_SCALE*scaleErr + W_ORDER*orderPenalty."""
    cd = center_distance(b, a)
    if cd > gate:
        return float("inf")
    norm_center = cd / gate
    order_pen = 0.0
    if anchor_base is not None and anchor_ai is not None:
        bc, ac = _center(b), _center(a)
        bt = _ordering_tokens(bc[0], bc[1], anchor_base[0], anchor_base[1], diag)
        at = _ordering_tokens(ac[0], ac[1], anchor_ai[0], anchor_ai[1], diag)
        flips = 0
        if "center" not in (bt["horizontal"], at["horizontal"]) and bt["horizontal"] != at["horizontal"]:
            flips += 1
        if "center" not in (bt["vertical"], at["vertical"]) and bt["vertical"] != at["vertical"]:
            flips += 1
        order_pen = 1.0 if flips else 0.0
    return (W_CENTER * norm_center + W_IOU * (1.0 - iou(b, a))
            + W_SCALE * _scale_error(b, a) + W_ORDER * order_pen)


def assign_one_to_one(cost: list[list[float]], n_ai: int) -> dict[int, int]:
    """Injective base->ai assignment minimizing total cost via scipy linear_sum_assignment
    when available, else a deterministic brute-force (optimal for the small n here). Unmatched
    bases are allowed via padded dummy columns whose cost is UNMATCHED_PEN (> any in-gate cost),
    so an in-gate detection is always matched (even if displaced => FAIL) rather than dropped."""
    nb = len(cost)
    if nb == 0:
        return {}
    UNMATCHED_PEN = (W_CENTER + W_IOU + W_SCALE + W_ORDER) * 2.0  # exceeds any finite in-gate cost
    BIG = UNMATCHED_PEN * 100.0
    width = n_ai + nb  # real AI columns + nb dummy (unmatched) columns
    full = [[0.0] * width for _ in range(nb)]
    for i in range(nb):
        for j in range(n_ai):
            c = cost[i][j]
            full[i][j] = BIG if c == float("inf") else c
        for d in range(nb):
            full[i][n_ai + d] = UNMATCHED_PEN  # dummy columns = leave base i unmatched
    try:
        from scipy.optimize import linear_sum_assignment
        import numpy as _np
        ri, ci = linear_sum_assignment(_np.array(full))
        out: dict[int, int] = {}
        for i, j in zip(ri.tolist(), ci.tolist()):
            if j < n_ai and full[i][j] < BIG:
                out[i] = j
        return out
    except Exception:  # noqa: BLE001 — scipy missing / any failure => deterministic fallback
        import itertools
        padded = list(range(n_ai)) + [-1] * nb
        best = {"total": float("inf"), "assign": {}}
        seen: set[tuple[int, ...]] = set()
        for perm in itertools.permutations(padded, nb):
            if perm in seen:
                continue
            seen.add(perm)
            total = 0.0; ok = True
            for bi, aj in enumerate(perm):
                if aj == -1:
                    total += UNMATCHED_PEN; continue
                c = cost[bi][aj]
                if c == float("inf"):
                    ok = False; break
                total += c
            if ok and total < best["total"]:
                best = {"total": total, "assign": {bi: aj for bi, aj in enumerate(perm) if aj != -1}}
        return best["assign"]


# ── per-object + per-opening status and the Task-8 report ──────────────────────

def _match_status(matched: bool, cd: float, iou_v: float, scale: float, conf: float,
                  ordering_violated: bool, pass_tol: float, fail_tol: float,
                  identity_supported: bool) -> tuple[str, str]:
    """One status per object. Missing/weak/ambiguous => UNCERTAIN (never FAIL). A FAIL needs a
    confident detection that is ALSO TYPE-CONSISTENT with the canonical object (identity
    corroborated) AND proves displacement, gross rescale, or an impossible ordering — a
    confident-but-wrong-type match is a probable mis-assignment => UNCERTAIN, never FAIL."""
    if not matched:
        return "UNCERTAIN", "DETECTOR_MISSED_OR_NOT_VALIDATABLE"
    if conf < MIN_DET_CONF:
        return "UNCERTAIN", f"detection confidence {round(conf,3)} < {MIN_DET_CONF} (cannot confirm)"
    if conf >= STRONG_DET_CONF and identity_supported:
        if cd > fail_tol:
            return "FAIL", f"same-type detection displaced {round(cd,1)}px > {round(fail_tol,1)} at conf {round(conf,2)}"
        if scale < FAIL_SCALE_LO or scale > FAIL_SCALE_HI:
            return "FAIL", f"same-type detection scale {round(scale,2)} outside [{FAIL_SCALE_LO},{FAIL_SCALE_HI}] at conf {round(conf,2)}"
        if ordering_violated:
            return "FAIL", f"same-type detection ordering vs anchor reversed at conf {round(conf,2)}"
    if conf >= STRONG_DET_CONF and not identity_supported and (cd > fail_tol or scale < FAIL_SCALE_LO
                                                               or scale > FAIL_SCALE_HI or ordering_violated):
        return "UNCERTAIN", "confident detection but TYPE mismatches the canonical object (probable mis-assignment)"
    if (cd <= pass_tol and iou_v >= PASS_IOU and PASS_SCALE_LO <= scale <= PASS_SCALE_HI and not ordering_violated):
        return "PASS", "within center/IoU/scale tolerances, ordering consistent"
    return "UNCERTAIN", "matched but delta/IoU/scale/confidence insufficient to confirm preservation"


def _ai_ordering(a: dict[str, Any], anchor_ai: tuple[float, float] | None, diag: float) -> dict[str, str] | None:
    if anchor_ai is None:
        return None
    ac = _center(a)
    return _ordering_tokens(ac[0], ac[1], anchor_ai[0], anchor_ai[1], diag)


def validate_objects(registry: dict[str, Any], ai_boxes: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic two-pass validation. Pass 1 assigns without the ordering term to locate
    the anchor's AI box; pass 2 re-assigns with the full cost (incl. ordering vs that anchor),
    then classifies each object. AI detections never redefine identity."""
    diag = float(registry["diag"])
    gate = GATE_FRACTION * diag
    pass_tol, fail_tol = PASS_CENTER_FRACTION * diag, FAIL_CENTER_FRACTION * diag
    objs = registry["objects"]
    base_boxes = [{"x": o["base_bbox"][0], "y": o["base_bbox"][1], "width": o["base_bbox"][2],
                   "height": o["base_bbox"][3], "center_x": o["base_center"][0], "center_y": o["base_center"][1]}
                  for o in objs]
    anchor_base = tuple(registry["anchor_center"]) if objs else None

    def _assign(anchor_ai):
        cost = [[pair_cost(b, a, gate=gate, diag=diag, anchor_base=anchor_base, anchor_ai=anchor_ai)
                 for a in ai_boxes] for b in base_boxes]
        return assign_one_to_one(cost, len(ai_boxes))

    assign = _assign(None)
    anchor_i = next((i for i, o in enumerate(objs) if o["is_anchor"]), None)
    anchor_ai = _center(ai_boxes[assign[anchor_i]]) if (anchor_i is not None and anchor_i in assign) else None
    if anchor_ai is not None:
        assign = _assign(anchor_ai)
        anchor_ai = _center(ai_boxes[assign[anchor_i]]) if anchor_i in assign else None

    out_objects = []
    dissolved: set[int] = set()   # AI indices whose forced pairing was rejected (returned to extras)
    for i, o in enumerate(objs):
        rec = {k: o[k] for k in ("uid", "item_id", "room")}
        rec["base_bbox"] = o["base_bbox"]; rec["base_center"] = o["base_center"]
        rec.update({"ai_bbox": None, "ai_center": None, "center_delta": None, "iou": 0.0,
                    "width_ratio": None, "height_ratio": None, "area_ratio": None,
                    "relative_position_base": o["relative_position"], "relative_position_ai": None,
                    "ordering_status": "UNCERTAIN", "rotation_status": "NOT_VALIDATABLE",
                    "match_confidence": None, "missing": False, "status": "UNCERTAIN", "reason": ""})
        aj = assign.get(i)
        if aj is None:
            rec["status"], rec["reason"] = "UNCERTAIN", "DETECTOR_MISSED_OR_NOT_VALIDATABLE"
            rec["missing"] = True
            out_objects.append(rec); continue
        a = ai_boxes[aj]; b = base_boxes[i]
        ac = _center(a); bc = _center(b)
        conf = float(a.get("score", a.get("confidence", 0.0)) or 0.0)
        cd = center_distance(b, a); iou_v = iou(b, a)
        wr = float(a["width"]) / max(1.0, float(b["width"]))
        hr = float(a["height"]) / max(1.0, float(b["height"]))
        ar = (float(a["width"]) * float(a["height"])) / max(1.0, float(b["width"]) * float(b["height"]))
        lin_scale = ar ** 0.5
        id_ok_pre = _identity_supported(o["item_id"], a.get("query"))
        # ACCEPTANCE: a forced within-gate pairing is a real match ONLY with positive same-object
        # evidence. No type match AND negligible overlap AND beyond the displacement bound =>
        # DISSOLVE: this base object is MISSING and the detection is an EXTRA candidate.
        if not (id_ok_pre or iou_v >= MATCH_MIN_IOU or cd <= fail_tol):
            rec["status"] = "UNCERTAIN"; rec["missing"] = True
            rec["detected_query"] = a.get("query"); rec["identity_supported"] = id_ok_pre
            rec["reason"] = ("no valid AI match: nearest detection is type-inconsistent, non-overlapping "
                             f"(IoU {round(iou_v,3)}) and displaced {round(cd,1)}px > {round(fail_tol,1)} "
                             "— probable MISSING; detection returned to extras")
            dissolved.add(aj)
            out_objects.append(rec); continue
        ai_ord = _ai_ordering(a, anchor_ai, diag)
        ordering_violated = False; ordering_status = "UNCERTAIN"
        if o["is_anchor"]:
            ordering_status = "ANCHOR"
        elif ai_ord is not None:
            bt = o["relative_position"]; flips = []
            if "center" not in (bt["horizontal"], ai_ord["horizontal"]) and bt["horizontal"] != ai_ord["horizontal"]:
                flips.append("horizontal")
            if "center" not in (bt["vertical"], ai_ord["vertical"]) and bt["vertical"] != ai_ord["vertical"]:
                flips.append("vertical")
            ordering_violated = bool(flips)
            ordering_status = ("VIOLATED:" + ",".join(flips)) if flips else "OK"
        id_ok = id_ok_pre
        st, reason = _match_status(True, cd, iou_v, lin_scale, conf, ordering_violated, pass_tol, fail_tol, id_ok)
        rec.update({
            "ai_bbox": [round(v, 1) for v in _xywh(a)], "ai_center": [round(ac[0], 1), round(ac[1], 1)],
            "center_delta": [round(ac[0] - bc[0], 1), round(ac[1] - bc[1], 1)],
            "iou": round(iou_v, 3), "width_ratio": round(wr, 3), "height_ratio": round(hr, 3),
            "area_ratio": round(ar, 3), "relative_position_ai": ai_ord,
            "ordering_status": ordering_status, "match_confidence": round(conf, 3),
            "detected_query": a.get("query"), "identity_supported": id_ok,
            "status": st, "reason": reason,
        })
        out_objects.append(rec)

    # Final matched set EXCLUDES dissolved pairings, so those detections are returned to extras.
    matched_ai = set(assign.values()) - dissolved
    # Unmatched detections (never assigned + dissolved). A strong one is an EXTRA_CANDIDATE flagged
    # FOR REVIEW — but detector confidence ALONE never proves a real extra furniture object (OWLv2
    # double-detects and hallucinates on these renders), so it NEVER forces a FAIL. It only
    # downgrades a would-be clean PASS to UNCERTAIN. A real DUPLICATED_OBJECT needs corroboration.
    extras = []
    for j, a in enumerate(ai_boxes):
        if j in matched_ai:
            continue
        conf = float(a.get("score", a.get("confidence", 0.0)) or 0.0)
        extras.append({"index": j, "query": a.get("query"), "score": round(conf, 3),
                       "center": [a.get("center_x"), a.get("center_y")],
                       "dissolved_from_base": j in dissolved,
                       "classification": "EXTRA_CANDIDATE_REVIEW" if conf >= STRONG_DET_CONF else "AMBIGUOUS_IGNORED"})
    has_extra_candidate = any(e["classification"] == "EXTRA_CANDIDATE_REVIEW" for e in extras)

    statuses = {o["status"] for o in out_objects}
    if not objs:
        overall = "NOT_VALIDATABLE"
    elif "FAIL" in statuses:               # only a corroborated per-object FAIL fails the scene
        overall = "FAIL"
    elif statuses <= {"PASS"} and not has_extra_candidate:
        overall = "PASS"
    else:
        overall = "UNCERTAIN"              # a strong extra downgrades PASS->UNCERTAIN, never FAIL
    return {"overall_status": overall, "objects": out_objects, "extras": extras,
            "has_extra_candidate": has_extra_candidate, "anchor_ai_located": anchor_ai is not None,
            "gate_px": round(gate, 1), "pass_center_px": round(pass_tol, 1), "fail_center_px": round(fail_tol, 1),
            "match_min_iou": MATCH_MIN_IOU,
            "pass_count": sum(1 for o in out_objects if o["status"] == "PASS"),
            "uncertain_count": sum(1 for o in out_objects if o["status"] == "UNCERTAIN"),
            "fail_count": sum(1 for o in out_objects if o["status"] == "FAIL"),
            "missing_count": sum(1 for o in out_objects if o.get("missing")),
            "extra_candidate_count": sum(1 for e in extras if e["classification"] == "EXTRA_CANDIDATE_REVIEW")}


def validate_openings(registry: dict[str, Any], ai_boxes: list[dict[str, Any]]) -> dict[str, Any]:
    """Openings: position may be matched spatially, but WALL association stays NOT_VALIDATABLE
    (OWLv2 cannot prove a wall), so a door/window is at best UNCERTAIN, never PASS, here."""
    diag = float(registry["diag"]); gate = GATE_FRACTION * diag
    ops = registry["openings"]
    base_boxes = [{"x": o["base_bbox"][0], "y": o["base_bbox"][1], "width": o["base_bbox"][2],
                   "height": o["base_bbox"][3], "center_x": o["base_center"][0], "center_y": o["base_center"][1]}
                  for o in ops]
    cost = [[pair_cost(b, a, gate=gate, diag=diag, anchor_base=None, anchor_ai=None) for a in ai_boxes]
            for b in base_boxes]
    assign = assign_one_to_one(cost, len(ai_boxes))
    out = []
    for i, o in enumerate(ops):
        rec = {"opening_id": o["opening_id"], "type": o["type"], "room": o["room"], "wall": o["wall"],
               "base_bbox": o["base_bbox"], "base_center": o["base_center"], "ai_bbox": None,
               "normalized_wall_position": o["normalized_wall_position"],
               "ai_wall_association": "NOT_VALIDATABLE", "status": "UNCERTAIN",
               "reason": "wall association not provable from OWLv2 (pixels cannot localize a wall)"}
        aj = assign.get(i)
        if aj is not None:
            a = ai_boxes[aj]
            rec["ai_bbox"] = [round(v, 1) for v in _xywh(a)]
            rec["reason"] = "a candidate opening-like box was localized, but wall association remains NOT_VALIDATABLE from pixels"
        out.append(rec)
    overall = "NOT_VALIDATABLE" if not ops else ("UNCERTAIN" if any(r["status"] != "PASS" for r in out) else "PASS")
    return {"overall_status": overall, "objects": out}


def run_object_validation(
    base_furniture: list[dict[str, Any]],
    base_openings: list[dict[str, Any]] | None,
    ai_image: Any | None,
    *,
    image_width: int = 1216,
    image_height: int = 832,
    base_png_sha256: str | None = None,
    output_png_sha256: str | None = None,
    room: str | None = None,
    detector: Callable[[Any], list[dict[str, Any]]] | None = None,
    calibrated: bool = False,
) -> dict[str, Any]:
    """Orchestrate object-level validation and emit the Task-8 report. ``detector`` defaults to
    OWLv2; inject a stub in tests. NOT_VALIDATABLE when base/registry or AI image/detector are
    unavailable. ``gating_status`` is NOT_CALIBRATED until tolerances are calibrated on a set."""
    if not (base_furniture or base_openings):
        return {"overall_status": "NOT_VALIDATABLE", "reason": "no deterministic base boxes"}
    if ai_image is None:
        return {"overall_status": "NOT_VALIDATABLE", "reason": "no AI output image"}
    det = detector or detect_owlv2
    try:
        ai_boxes = det(ai_image)
    except Exception as exc:  # noqa: BLE001
        return {"overall_status": "NOT_VALIDATABLE", "reason": f"detector unavailable: {type(exc).__name__}"}

    registry = build_object_registry(base_furniture, base_openings, image_width=image_width, image_height=image_height)
    furn = validate_objects(registry, ai_boxes)
    opn = validate_openings(registry, ai_boxes)
    overalls = [furn["overall_status"]] + ([opn["overall_status"]] if registry["openings"] else [])
    if "FAIL" in overalls:
        overall = "FAIL"
    elif all(o == "PASS" for o in overalls):
        overall = "PASS"
    elif all(o == "NOT_VALIDATABLE" for o in overalls):
        overall = "NOT_VALIDATABLE"
    else:
        overall = "UNCERTAIN"
    return {
        "room": room, "base_png_sha256": base_png_sha256, "output_png_sha256": output_png_sha256,
        "overall_status": overall,
        "gating_status": "CALIBRATED" if calibrated else "NOT_CALIBRATED",
        "detector": "owlv2" if detector is None else "injected",
        "ai_detection_count": len(ai_boxes),
        "anchor_uid": registry["anchor_uid"],
        "furniture_overall": furn["overall_status"],
        "furniture_counts": {"base_total": len(registry["objects"]),
                             "pass": furn["pass_count"], "uncertain": furn["uncertain_count"],
                             "fail": furn["fail_count"], "missing": furn["missing_count"],
                             "extra_candidates": furn["extra_candidate_count"]},
        "tolerances": {"gate_px": furn["gate_px"], "pass_center_px": furn["pass_center_px"],
                       "fail_center_px": furn["fail_center_px"], "pass_iou": PASS_IOU,
                       "pass_scale": [PASS_SCALE_LO, PASS_SCALE_HI], "fail_scale": [FAIL_SCALE_LO, FAIL_SCALE_HI],
                       "weights": {"center": W_CENTER, "iou": W_IOU, "scale": W_SCALE, "order": W_ORDER}},
        "objects": furn["objects"], "extras": furn["extras"],
        "openings_overall": opn["overall_status"], "openings": opn["objects"],
    }
