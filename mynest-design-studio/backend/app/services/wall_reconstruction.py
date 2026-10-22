"""Deterministic, scale-invariant, NO-FABRICATION architectural wall reconstruction.

Turns raw double-line, fragmented wall segments from a vector floor plan into room
polygons WITHOUT inventing geometry:
  - tolerances are DERIVED from measured geometry (never hardcoded pixels);
  - double-line faces are collapsed to a centerline only with real longitudinal
    overlap + thickness-consistent spacing;
  - collinear fragments merge only across gaps below a conservative derived bound
    (bridges dashes, NOT wide openings or the space between separate rooms);
  - corners are formed only by SNAPPING two already-near-coincident endpoints —
    a wall is NEVER extended into empty space to manufacture a corner;
  - a polygon is accepted only when every edge is actually covered by collapsed
    wall spans (no tolerance "fills in" a missing side);
  - furniture is used ONLY to drop empty candidates AFTER geometric validation —
    it never creates, extends, closes, or rescues a boundary.

If the source cannot yield a room without fabrication, the room is reported with a
validation_status (UNSUPPORTED / SLIVER / INVALID) rather than fabricated.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

Seg = tuple[float, float, float, float]


def _is_h(s: Seg) -> bool:
    return abs(s[1] - s[3]) <= abs(s[0] - s[2])


def _length(s: Seg) -> float:
    return math.hypot(s[2] - s[0], s[3] - s[1])


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def measure_tolerances(walls: list[Seg]) -> dict[str, float]:
    """Derive every tolerance from the plan's own geometry (scale-invariant)."""
    lengths = [_length(w) for w in walls if _length(w) > 0]
    unit = statistics.median(lengths) if lengths else 1.0
    hs = [w for w in walls if _is_h(w)]
    vs = [w for w in walls if not _is_h(w)]

    def _spacings(segs: list[Seg], axis: int) -> list[float]:
        out: list[float] = []
        for i, a in enumerate(segs):
            ac, a0, a1 = ((a[1] + a[3]) / 2, min(a[0], a[2]), max(a[0], a[2])) if axis == 0 \
                else ((a[0] + a[2]) / 2, min(a[1], a[3]), max(a[1], a[3]))
            best = math.inf
            for j, b in enumerate(segs):
                if i == j:
                    continue
                bc, b0, b1 = ((b[1] + b[3]) / 2, min(b[0], b[2]), max(b[0], b[2])) if axis == 0 \
                    else ((b[0] + b[2]) / 2, min(b[1], b[3]), max(b[1], b[3]))
                if _overlap(a0, a1, b0, b1) <= 0:
                    continue
                d = abs(ac - bc)
                if 0.5 < d < best:
                    best = d
            if math.isfinite(best):
                out.append(best)
        return out

    # Wall thickness = the spacing between a wall's two parallel faces. The
    # nearest-parallel-overlapping spacings are multi-modal: ~detail-line noise,
    # the true double-line spacing, then room-to-room distances (super-unit).
    # VALLEY DETECTION: within the sub-unit band, the wall-thickness population is
    # the run of spacings up to the largest internal gap; its upper edge is the
    # true thickness. This separates the true ~double-line spacing from smaller
    # detail-line noise (a plain median under-estimated it, so faces never
    # collapsed — audit: 21/38 spans left uncollapsed; valley detection -> 12+12).
    spac = sorted(_spacings(hs, 0) + _spacings(vs, 1))
    if not spac:
        thickness = unit * 0.1
    else:
        # A genuine double-line wall's face-to-face spacing is a small fraction of
        # the median segment length (walls are far longer than they are thick). A
        # single-line plan's closest parallel spacing is instead room-scale
        # (~unit). So min-spacing << unit ⇒ double-line; otherwise single-line, for
        # which the thickness is a small nominal value and pair_tol must NOT grow
        # to room scale (which would merge separate parallel walls).
        double_line = min(spac) <= unit * 0.6
        if double_line:
            below = [s for s in spac if s <= unit]
            if len(below) >= 2:
                gaps = [(below[i + 1] - below[i], below[i]) for i in range(len(below) - 1)]
                thickness = max(gaps)[1]
            else:
                thickness = below[-1] if below else min(spac)
        else:
            thickness = max(1.0, min(spac) * 0.1)
    thickness = max(1.0, min(thickness, unit))
    return {
        "unit": round(unit, 2),
        "thickness": round(thickness, 2),
        "pair_tol": thickness * 1.6,     # two faces this close (with overlap) are one wall band
        "merge_gap": thickness * 2.0,    # bridge dash gaps only — NOT wide openings/room gaps
        "snap_tol": thickness * 1.6,     # snap two near-coincident endpoints (no extension)
    }


def _collapse(
    segs_idx: list[tuple[int, Seg]],
    axis: int,
    pair_tol: float,
    merge_gap: float,
    thickness: float | None = None,
) -> list[tuple[float, float, float, set[int]]]:
    """Collapse double-line faces with genuine architectural evidence and merge collinear fragments.

    Two separate parallel architectural walls must NOT collapse into one band merely because
    their longitudinal ranges overlap and coordinate distance is <= pair_tol.
    Real double-line evidence required:
      - compatible spacing around measured wall thickness
      - meaningful longitudinal overlap (>= max(0.75*thickness, 0.4*min_length))
      - mutual best-match pairing between opposing faces
      - no merging across longitudinal gaps for parallel lines
      - separate parallel walls are preserved.
    Returns [(const, a0, a1, source_indices_set)].
    """
    if not segs_idx:
        return []
    th = thickness if thickness is not None and thickness > 0 else (pair_tol / 1.6)
    collinear_eps = max(1.0, th * 0.15)
    min_face_dist = th * 0.65
    max_face_dist = min(pair_tol, th * 1.35)

    items: list[tuple[float, float, float, int]] = []
    for idx, w in segs_idx:
        const, a0, a1 = (
            ((w[1] + w[3]) / 2, min(w[0], w[2]), max(w[0], w[2]))
            if axis == 0
            else ((w[0] + w[2]) / 2, min(w[1], w[3]), max(w[1], w[3]))
        )
        if a1 - a0 > 1e-6:
            items.append((const, a0, a1, idx))
    items.sort()

    # Phase 1: Collinear fragment merge along the SAME face
    collinear_bands: list[dict[str, Any]] = []
    for const, a0, a1, idx in items:
        placed = False
        for bd in collinear_bands:
            if abs(const - bd["const"]) <= collinear_eps:
                bd["const"] = (bd["const"] * bd["n"] + const) / (bd["n"] + 1)
                bd["n"] += 1
                bd["parts"].append((a0, a1, idx))
                placed = True
                break
        if not placed:
            collinear_bands.append({"const": const, "n": 1, "parts": [(a0, a1, idx)]})

    faces: list[dict[str, Any]] = []
    for bd in collinear_bands:
        parts = sorted(bd["parts"])
        runs: list[list[Any]] = []
        for a0, a1, idx in parts:
            if runs and a0 <= runs[-1][1] + merge_gap:
                runs[-1][1] = max(runs[-1][1], a1)
                runs[-1][2].add(idx)
            else:
                runs.append([a0, a1, {idx}])
        for a0, a1, ids in runs:
            faces.append({"const": bd["const"], "a0": a0, "a1": a1, "ids": ids})

    faces.sort(key=lambda f: (f["const"], f["a0"]))

    # Phase 2: Double-line face collapse with real evidence
    best_match_for: dict[int, tuple[int, float, float]] = {}
    for i in range(len(faces)):
        fi = faces[i]
        len_i = fi["a1"] - fi["a0"]
        best_j, best_diff, best_ov = None, float("inf"), 0.0
        for j in range(len(faces)):
            if i == j:
                continue
            fj = faces[j]
            dist = abs(fj["const"] - fi["const"])
            if not (min_face_dist <= dist <= max_face_dist):
                continue
            ov = _overlap(fi["a0"], fi["a1"], fj["a0"], fj["a1"])
            min_len = min(len_i, fj["a1"] - fj["a0"])
            if ov < max(th * 0.75, min_len * 0.4):
                continue
            diff = abs(dist - th)
            if diff < best_diff or (abs(diff - best_diff) < 1e-3 and ov > best_ov):
                best_diff = diff
                best_j = j
                best_ov = ov
        if best_j is not None:
            best_match_for[i] = (best_j, best_diff, best_ov)

    used_face_idx: set[int] = set()
    spans: list[tuple[float, float, float, set[int]]] = []

    # Pair faces that are mutual best matches
    for i, (j, _, _ov) in list(best_match_for.items()):
        if i in used_face_idx or j in used_face_idx:
            continue
        if best_match_for.get(j, (None,))[0] == i:
            used_face_idx.add(i)
            used_face_idx.add(j)
            fi, fj = faces[i], faces[j]
            c_mid = (fi["const"] + fj["const"]) / 2.0
            ov_a0 = min(fi["a0"], fj["a0"])
            ov_a1 = max(fi["a1"], fj["a1"])
            spans.append(
                (round(c_mid, 2), round(ov_a0, 2), round(ov_a1, 2), fi["ids"] | fj["ids"])
            )

    # Unpaired faces remain separate architectural walls
    for i, fi in enumerate(faces):
        if i not in used_face_idx:
            spans.append(
                (round(fi["const"], 2), round(fi["a0"], 2), round(fi["a1"], 2), fi["ids"])
            )

    spans.sort(key=lambda s: (s[0], s[1]))
    return spans


def repair_walls(
    segs: list[Seg], tol: dict[str, float] | None = None
) -> list[dict[str, Any]]:
    """Deterministically repair fragmented/offset vector walls BEFORE rasterization.

    Collapses each architectural wall's double-line faces into a single centreline
    and merges collinear dash fragments across small measured gaps (``merge_gap``),
    using only the plan's own measured tolerances — no furniture, no pixels, no
    arbitrary large-gap closing. Every repaired centreline retains provenance to the
    original extracted wall IDs it was built from.

    Returns ``[{"seg": (x1,y1,x2,y2), "source_wall_ids": [...], "orientation": "h"|"v",
    "const": float, "a0": float, "a1": float}]``.
    """
    tol = tol or measure_tolerances(segs)
    pair_tol, merge_gap = tol["pair_tol"], tol["merge_gap"]
    thickness = tol.get("thickness", 0.0)
    hs = [(i, s) for i, s in enumerate(segs) if _is_h(s)]
    vs = [(i, s) for i, s in enumerate(segs) if not _is_h(s)]
    out: list[dict[str, Any]] = []
    for const, a0, a1, ids in _collapse(hs, 0, pair_tol, merge_gap, thickness):
        out.append({
            "seg": (a0, const, a1, const),
            "source_wall_ids": [f"wall_{i + 1:03d}" for i in sorted(ids)],
            "orientation": "h",
            "const": const,
            "a0": a0,
            "a1": a1,
        })
    for const, a0, a1, ids in _collapse(vs, 1, pair_tol, merge_gap, thickness):
        out.append({
            "seg": (const, a0, const, a1),
            "source_wall_ids": [f"wall_{i + 1:03d}" for i in sorted(ids)],
            "orientation": "v",
            "const": const,
            "a0": a0,
            "a1": a1,
        })
    return out


def _snap_and_polygonize(hspans, vspans, snap_tol: float) -> list[Polygon]:
    """Build the planar arrangement by SNAPPING near-coincident endpoints to shared
    nodes (never extending a wall), then polygonize. Snapping only moves an already
    near-touching endpoint onto its neighbour — it adds no wall length into empty
    space."""
    # candidate node coords: cluster H y-lines & V x-lines and all endpoint coords
    xs = [x for _, a0, a1, _ in [(0, s[1], s[2], 0) for s in hspans] for x in (a0, a1)]
    xs += [s[0] for s in vspans]
    ys = [s[0] for s in hspans]
    ys += [y for s in vspans for y in (s[1], s[2])]

    def _grid(vals):
        vals = sorted(vals)
        reps: list[list[float]] = []
        m: dict[float, float] = {}
        for v in vals:
            for r in reps:
                if abs(v - r[1]) <= snap_tol:
                    r[0] += v
                    r[2] += 1
                    r[1] = r[0] / r[2]
                    m[v] = r[1]
                    break
            else:
                reps.append([v, v, 1])
                m[v] = v
        return {k: round(val, 2) for k, val in m.items()}

    gx = _grid(xs)
    gy = _grid(ys)

    def sx(v):
        return gx.get(v, min(gx.values(), key=lambda g: abs(g - v)) if gx else v)

    def sy(v):
        return gy.get(v, min(gy.values(), key=lambda g: abs(g - v)) if gy else v)

    lines = []
    for y, x0, x1, _ in hspans:
        yy = sy(y)
        # endpoints snapped to shared nodes; length is NOT extended
        lines.append(LineString([(sx(x0), yy), (sx(x1), yy)]))
    for x, y0, y1, _ in vspans:
        xx = sx(x)
        lines.append(LineString([(xx, sy(y0)), (xx, sy(y1))]))
    if not lines:
        return []
    return [p for p in polygonize(unary_union(lines)) if p.area > 0]


def _edge_supported(p0, p1, spans, is_h: bool, tol: float) -> bool:
    """True if the polygon edge p0->p1 is actually COVERED by collapsed wall spans
    (>=90% of its length), i.e. not fabricated. Gaps are allowed only where real
    span coverage exists — tolerance never fills a missing side."""
    if is_h:
        y = (p0[1] + p1[1]) / 2
        e0, e1 = sorted((p0[0], p1[0]))
        segs = [(a0, a1) for c, a0, a1, _ in spans if abs(c - y) <= tol]
    else:
        x = (p0[0] + p1[0]) / 2
        e0, e1 = sorted((p0[1], p1[1]))
        segs = [(a0, a1) for c, a0, a1, _ in spans if abs(c - x) <= tol]
    total = max(1e-6, e1 - e0)
    covered = sum(_overlap(e0, e1, a0, a1) for a0, a1 in segs)
    return covered / total >= 0.9


def _supporting_ids(poly: Polygon, hspans, vspans, tol: float) -> list[int]:
    ids: set[int] = set()
    coords = list(poly.exterior.coords)
    for (x0, y0), (x1, y1) in zip(coords[:-1], coords[1:], strict=False):
        is_h = abs(y1 - y0) <= abs(x1 - x0)
        spans = hspans if is_h else vspans
        c = (y0 + y1) / 2 if is_h else (x0 + x1) / 2
        e0, e1 = sorted((x0, x1)) if is_h else sorted((y0, y1))
        for cc, a0, a1, sids in spans:
            if abs(cc - c) <= tol and _overlap(e0, e1, a0, a1) > 0:
                ids |= sids
    return sorted(ids)


def reconstruct_rooms(walls, furniture: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Reconstruct room polygons with strict no-fabrication validation.

    Returns {"rooms":[{polygon,bbox,area,wall_supported,validation_status,
    supporting_wall_ids,furniture_ids}], "tolerances", "stats"}.
    validation_status ∈ {CONFIRMED, SLIVER, UNSUPPORTED, INVALID}.
    """
    segs = [tuple(map(float, w[:4])) for w in walls if _length(tuple(map(float, w[:4]))) > 0]
    if not segs:
        return {"rooms": [], "tolerances": {}, "stats": {"reason": "no walls"}}
    tol = measure_tolerances(segs)
    idxd = list(enumerate(segs))
    hspans = _collapse([(i, w) for i, w in idxd if _is_h(w)], 0, tol["pair_tol"], tol["merge_gap"])
    vspans = _collapse([(i, w) for i, w in idxd if not _is_h(w)], 1,
                       tol["pair_tol"], tol["merge_gap"])
    polys = _snap_and_polygonize(hspans, vspans, tol["snap_tol"])

    areas = sorted(p.area for p in polys)
    median_area = statistics.median(areas) if areas else 0.0
    min_area = max(median_area * 0.2, (tol["unit"]) ** 2 * 0.5)

    fpts = []
    if furniture:
        for f in furniture:
            iid = str(f.get("item_id", ""))
            if "window" in iid or "door" in iid:
                continue
            try:
                fpts.append((f, Point(float(f["cx"]), float(f["cy"]))))
            except (KeyError, TypeError, ValueError):
                continue

    rooms = []
    for p in polys:
        if not (p.is_valid and p.is_simple and p.area > 0):
            status = "INVALID"
        else:
            minx, miny, maxx, maxy = p.bounds
            w, h = maxx - minx, maxy - miny
            aspect = max(w, h) / max(1e-6, min(w, h))
            rect_fill = p.area / max(1e-6, w * h)
            coords = list(p.exterior.coords)
            all_edges_supported = all(
                _edge_supported(a, b, hspans if abs(b[1] - a[1]) <= abs(b[0] - a[0]) else vspans,
                                abs(b[1] - a[1]) <= abs(b[0] - a[0]), tol["pair_tol"])
                for a, b in zip(coords[:-1], coords[1:], strict=False)
            )
            if not all_edges_supported:
                status = "UNSUPPORTED"
            elif p.area < min_area or aspect > 4.0 or rect_fill < 0.75:
                status = "SLIVER"
            else:
                status = "CONFIRMED"

        minx, miny, maxx, maxy = p.bounds
        fids = ([str(f.get("uid") or f.get("item_id")) for f, pt in fpts if p.covers(pt)]
                if status == "CONFIRMED" else [])
        rooms.append({
            "polygon": [(round(x, 2), round(y, 2)) for x, y in p.exterior.coords],
            "bbox": [round(minx, 2), round(miny, 2), round(maxx - minx, 2), round(maxy - miny, 2)],
            "area": round(p.area, 1),
            "wall_supported": status == "CONFIRMED",
            "validation_status": status,
            "supporting_wall_ids": _supporting_ids(p, hspans, vspans, tol["pair_tol"]),
            "furniture_ids": fids,
        })

    confirmed = [r for r in rooms if r["validation_status"] == "CONFIRMED"]
    return {
        "rooms": confirmed,
        "all_candidates": rooms,
        "tolerances": tol,
        "stats": {
            "hspans": len(hspans),
            "vspans": len(vspans),
            "raw_polys": len(polys),
            "confirmed": len(confirmed),
            "by_status": {s: sum(1 for r in rooms if r["validation_status"] == s)
                          for s in ("CONFIRMED", "SLIVER", "UNSUPPORTED", "INVALID")},
        },
    }


# ---------------------------------------------------------------------------
# TOPOLOGY-FIRST reconstruction via POINT -> PERPENDICULAR-SEGMENT junctions.
#
# The raster corner-evidence experiment proved many real junctions are an
# endpoint touching the BODY of a perpendicular wall (T-junctions) with a large
# endpoint->endpoint gap. This reconstructs rooms from that evidence WITHOUT
# extending walls, joining nearest neighbours, or using infinite-line
# intersections.
#
# Guarantees (each enforced below, not merely intended):
#   * A junction is accepted ONLY when an actual span endpoint projects strictly
#     ONTO an existing perpendicular span (projection parameter in [0, 1]) and the
#     perpendicular distance is within one wall thickness. Endpoint tolerance is
#     used ONLY to classify L vs T — never to extend a segment or invent a node.
#   * Duplicate H->V / V->H detections of the same physical corner are merged
#     GEOMETRICALLY, combining (never discarding) every incident wall id and
#     source-segment id.
#   * The wall graph is built with NO global coordinate clustering. Nodes are
#     proven junctions; edges are sub-spans of REAL walls split only at the
#     junctions that provably lie on that wall (the wall participates in the
#     junction). No edge can exist without a supporting source wall.
#   * A room is accepted only when it is a closed cycle whose every boundary
#     segment maps back to a provenance-bearing graph edge and whose every corner
#     is a proven junction. polygonize() alone is NEVER sufficient.
# Every junction / edge / room carries diagnostics explaining accept / reject.
# ---------------------------------------------------------------------------


def _project_param(p: float, a0: float, a1: float) -> float:
    """Parameter t of point coord p on the axis span [a0, a1] (a0 may exceed a1)."""
    lo, hi = (a0, a1) if a0 <= a1 else (a1, a0)
    if hi - lo <= 1e-9:
        return 0.0
    return (p - lo) / (hi - lo)


def _add_incident(incident, wall_id, source_ids, role, t, dist):
    """Accumulate an incident wall on a merged junction, combining provenance."""
    cur = incident.get(wall_id)
    if cur is None:
        incident[wall_id] = {
            "wall_id": wall_id, "source_ids": set(source_ids),
            "role": role, "projection_parameter": t, "distance": dist,
        }
    else:
        cur["source_ids"] |= set(source_ids)
        if role == "through":            # interior contact dominates a corner end
            cur["role"] = "through"
        cur["distance"] = min(cur["distance"], dist)


def find_junctions(hspans, vspans, thickness):
    """Point->perpendicular-segment junctions with full provenance.

    ``hspans``/``vspans`` are ``(const, a0, a1, source_ids)`` bands from
    :func:`_collapse`.  For every span endpoint we project onto every
    perpendicular span and accept the contact ONLY when the projection lies
    strictly on that span (parameter in [0, 1], no endpoint slack) and the
    perpendicular gap is within one wall thickness.  Raw H->V and V->H detections
    of the same physical corner are then merged, unioning all incident wall ids
    and source ids.  Returns a list of merged junction dicts.
    """
    evidence_tol = float(thickness)
    end_tol = float(thickness) * 0.6
    raw: list[dict[str, Any]] = []

    def _detect(endpoint_orientation, e_wall, e_ids, e_along, e_const,
                s_wall, s_ids, s_const, s_a0, s_a1):
        # e_along = the endpoint coordinate PARALLEL to the supporting span's
        # extent (must land inside [s_a0, s_a1]); e_const = the endpoint
        # coordinate PERPENDICULAR to it (compared with the supporting centreline
        # s_const for the point->segment distance).
        t = _project_param(e_along, s_a0, s_a1)
        if t < 0.0 or t > 1.0:               # STRICTLY on the supporting segment
            return
        dist = abs(e_const - s_const)
        if dist > evidence_tol:              # within one wall thickness only
            return
        span_len = abs(s_a1 - s_a0)
        # Does the supporting wall ALSO terminate at this contact? Endpoint slack
        # is used ONLY for this L/T classification, never to accept the junction.
        near0 = abs(e_along - s_a0) <= end_tol
        near1 = abs(e_along - s_a1) <= end_tol
        supporting_terminates = near0 or near1
        if endpoint_orientation == "H":
            jx, jy = s_const, e_along        # V supporting: x=s_const, y=e_along
        else:
            jx, jy = e_along, s_const        # H supporting: x=e_along, y=s_const
        raw.append({
            "coordinate": (round(jx, 3), round(jy, 3)),
            "endpoint_wall": e_wall,
            "endpoint_source_ids": set(e_ids),
            "endpoint_orientation": endpoint_orientation,
            "supporting_wall": s_wall,
            "supporting_source_ids": set(s_ids),
            "supporting_terminates": supporting_terminates,
            "projection_parameter": round(t, 4),
            "span_length": round(span_len, 3),
            "distance": round(dist, 3),
        })

    for hi, (hy, hx0, hx1, hids) in enumerate(hspans):
        for ex in (hx0, hx1):
            for vi, (vx, vy0, vy1, vids) in enumerate(vspans):
                # H endpoint (ex, hy): along=hy onto V y-extent, const=ex vs vx.
                _detect("H", f"H{hi}", hids, hy, ex, f"V{vi}", vids, vx, vy0, vy1)
    for vi, (vx, vy0, vy1, vids) in enumerate(vspans):
        for ey in (vy0, vy1):
            for hi, (hy, hx0, hx1, hids) in enumerate(hspans):
                # V endpoint (vx, ey): along=vx onto H x-extent, const=ey vs hy.
                _detect("V", f"V{vi}", vids, vx, ey, f"H{hi}", hids, hy, hx0, hx1)

    # --- merge duplicate detections of the same physical corner ------------
    # Union-find over raw detections whose coordinates coincide within a small
    # geometric epsilon (well below the inter-corner distance of any real plan),
    # COMBINING provenance rather than picking one and discarding the other.
    merge_eps = max(1e-6, float(thickness) * 0.75)
    parent = list(range(len(raw)))

    def _find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for i in range(len(raw)):
        xi, yi = raw[i]["coordinate"]
        for j in range(i + 1, len(raw)):
            xj, yj = raw[j]["coordinate"]
            if abs(xi - xj) <= merge_eps and abs(yi - yj) <= merge_eps:
                _union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(len(raw)):
        clusters.setdefault(_find(i), []).append(i)

    merged: list[dict[str, Any]] = []
    jid = 0
    for members in clusters.values():
        jid += 1
        recs = [raw[m] for m in members]
        # node coordinate = mean of the coincident detections (all within eps)
        nx = round(sum(r["coordinate"][0] for r in recs) / len(recs), 2)
        ny = round(sum(r["coordinate"][1] for r in recs) / len(recs), 2)
        # incident walls: each contributing wall with the role it plays here.
        incident: dict[str, dict[str, Any]] = {}
        for r in recs:
            _add_incident(incident, r["endpoint_wall"], r["endpoint_source_ids"],
                          "endpoint", r["projection_parameter"], r["distance"])
            _add_incident(incident, r["supporting_wall"], r["supporting_source_ids"],
                          "endpoint" if r["supporting_terminates"] else "through",
                          None, r["distance"])
        walls_sorted = sorted(incident.keys())
        source_ids = sorted({sid for w in incident.values() for sid in w["source_ids"]})
        # L: every incident wall terminates here (a true corner). T/X: at least
        # one incident wall passes THROUGH its interior.
        any_through = any(w["role"] == "through" for w in incident.values())
        jtype = "T_JUNCTION" if any_through else "L_JUNCTION"
        max_dist = max(r["distance"] for r in recs)
        merged.append({
            "junction_id": f"J{jid}",
            "coordinate": [nx, ny],
            "junction_type": jtype,
            "walls": walls_sorted,
            "source_ids": source_ids,
            "incident": [
                {"wall_id": w["wall_id"], "role": w["role"],
                 "source_ids": sorted(w["source_ids"]),
                 "projection_parameter": w["projection_parameter"]}
                for w in (incident[k] for k in walls_sorted)
            ],
            "evidence_count": len(recs),
            "distance": round(max_dist, 2),
            "distance_in_wall_thickness": round(max_dist / float(thickness), 2),
            "evidence_status": "ACCEPTED",
        })
    merged.sort(key=lambda j: (j["coordinate"][1], j["coordinate"][0]))
    return merged


def _build_wall_graph(hspans, vspans, junctions, thickness):
    """Split real spans at the junctions that provably lie on them.

    A junction lies on a span ONLY when that span's wall id is one of the
    junction's incident walls (proven participation) — never by mere coordinate
    proximity.  Consecutive on-span junctions bound a provenance-bearing edge that
    is a genuine sub-segment of the source wall.  Returns ``(edges, diagnostics)``.
    """
    node_of: dict[str, dict[str, Any]] = {}
    on_wall: dict[str, list[dict[str, Any]]] = {}
    for j in junctions:
        node_of[j["junction_id"]] = j
        for wid in j["walls"]:
            on_wall.setdefault(wid, []).append(j)

    edges: list[dict[str, Any]] = []
    diag: list[dict[str, Any]] = []
    eid = 0
    min_edge = float(thickness) * 0.5

    def _emit(orientation, const, wall_id, src_ids, ja, jb):
        nonlocal eid
        pa = ja["coordinate"]
        pb = jb["coordinate"]
        along_a = pa[0] if orientation == "H" else pa[1]
        along_b = pb[0] if orientation == "H" else pb[1]
        lo, hi = sorted((along_a, along_b))
        if hi - lo < min_edge:
            return
        if orientation == "H":
            geom = LineString([(lo, const), (hi, const)])
        else:
            geom = LineString([(const, lo), (const, hi)])
        eid += 1
        edges.append({
            "edge_id": f"E{eid}",
            "orientation": orientation,
            "const": round(const, 2),
            "a": round(lo, 2), "b": round(hi, 2),
            "geometry": geom,
            "wall_id": wall_id,
            "source_segment_ids": sorted(src_ids),
            "junction_start": ja["junction_id"],
            "junction_end": jb["junction_id"],
        })

    def _process(spans, orientation):
        for si, span in enumerate(spans):
            const, a0, a1, sids = span
            wid = f"{orientation}{si}"
            js = on_wall.get(wid, [])
            if len(js) < 2:
                diag.append({"wall_id": wid, "accepted_edges": 0,
                             "reason": "fewer than two proven junctions on wall",
                             "junctions": [j["junction_id"] for j in js]})
                continue
            axis = 0 if orientation == "H" else 1
            js_sorted = sorted(js, key=lambda j: j["coordinate"][axis])
            n_before = eid
            for ja, jb in zip(js_sorted[:-1], js_sorted[1:], strict=False):
                _emit(orientation, const, wid, sids, ja, jb)
            diag.append({"wall_id": wid, "accepted_edges": eid - n_before,
                         "reason": "split at proven on-wall junctions",
                         "junctions": [j["junction_id"] for j in js_sorted]})

    _process(hspans, "H")
    _process(vspans, "V")
    return edges, node_of, diag


def _coverage_by_edges(p0, p1, edges, tol):
    """Fraction of segment p0->p1 covered by provenance-bearing graph edges of the
    same orientation, plus the supporting wall / source / edge ids."""
    dx, dy = abs(p1[0] - p0[0]), abs(p1[1] - p0[1])
    orientation = "H" if dx >= dy else "V"
    if orientation == "H":
        const = (p0[1] + p1[1]) / 2
        e0, e1 = sorted((p0[0], p1[0]))
    else:
        const = (p0[0] + p1[0]) / 2
        e0, e1 = sorted((p0[1], p1[1]))
    total = max(1e-6, e1 - e0)
    wall_ids: set[str] = set()
    src_ids: set[int] = set()
    edge_ids: set[str] = set()
    intervals: list[tuple[float, float]] = []
    for ed in edges:
        if ed["orientation"] != orientation or abs(ed["const"] - const) > tol:
            continue
        lo, hi = max(e0, ed["a"]), min(e1, ed["b"])
        if hi > lo:
            intervals.append((lo, hi))
            wall_ids.add(ed["wall_id"])
            src_ids |= set(ed["source_segment_ids"])
            edge_ids.add(ed["edge_id"])
    # Union the covered intervals so two edges overlapping the same stretch are
    # NOT double-counted (goal §wall_reconstruction: unioned intervals).
    covered = 0.0
    merged_hi = -math.inf
    for lo, hi in sorted(intervals):
        lo = max(lo, merged_hi)
        if hi > lo:
            covered += hi - lo
            merged_hi = hi
    return min(1.0, covered / total), sorted(wall_ids), sorted(src_ids), sorted(edge_ids)


def reconstruct_rooms_topology(walls, furniture=None, openings=None):
    """Topology-first, provenance-preserving room reconstruction.

    normalized spans -> validated PDF opening bridges -> proven point->segment
    junctions -> real-wall graph split only at those junctions -> polygonized
    cycles -> rooms accepted ONLY when every boundary segment maps to a
    provenance-bearing edge and every corner is a proven junction.
    Furniture never creates, extends, or closes a boundary.

    Returns ``{rooms, all_candidates, junctions, edges, tolerances, diagnostics,
    stats}``.  ``validation_status`` in {CONFIRMED, UNSUPPORTED, SLIVER, INVALID}.
    """
    segs = [tuple(map(float, w[:4])) for w in walls if _length(tuple(map(float, w[:4]))) > 0]
    if not segs:
        return {"rooms": [], "all_candidates": [], "junctions": [], "edges": [],
                "tolerances": {}, "diagnostics": {"reason": "no walls"},
                "stats": {"reason": "no walls", "confirmed": 0}}
    tol = measure_tolerances(segs)
    th = tol["thickness"]
    idxd = list(enumerate(segs))
    h_items = [(i, w) for i, w in idxd if _is_h(w)]
    v_items = [(i, w) for i, w in idxd if not _is_h(w)]
    hspans = _collapse(h_items, 0, tol["pair_tol"], tol["merge_gap"], th)
    vspans = _collapse(v_items, 1, tol["pair_tol"], tol["merge_gap"], th)

    # Validate and incorporate opening bridges if openings provided
    bridge_diag: list[dict[str, Any]] = []
    if openings:
        repaired_for_bridges = []
        for const, a0, a1, ids in hspans:
            repaired_for_bridges.append({
                "seg": (a0, const, a1, const),
                "source_wall_ids": [f"wall_{i + 1:03d}" for i in sorted(ids)],
                "orientation": "h",
                "const": const, "a0": a0, "a1": a1,
            })
        for const, a0, a1, ids in vspans:
            repaired_for_bridges.append({
                "seg": (const, a0, const, a1),
                "source_wall_ids": [f"wall_{i + 1:03d}" for i in sorted(ids)],
                "orientation": "v",
                "const": const, "a0": a0, "a1": a1,
            })
        validated_bridges = validate_opening_bridges(openings, repaired_for_bridges, th)
        bridge_diag = validated_bridges
        # Add applied bridges as spans to close vector cycles across openings
        for b in validated_bridges:
            if not b["bridge_applied"]:
                continue
            bx0, by0, bx1, by1 = b["box"]
            src_ids = {
                int(wid.replace("wall_", "")) - 1
                for wid in b["supporting_source_ids"]
                if wid.startswith("wall_")
            }
            if b["orientation"] == "h":
                hspans.append((round((by0 + by1) / 2, 2), round(bx0, 2), round(bx1, 2), src_ids))
            else:
                vspans.append((round((bx0 + bx1) / 2, 2), round(by0, 2), round(by1, 2), src_ids))

    junctions = find_junctions(hspans, vspans, th)
    edges, node_of, wall_diag = _build_wall_graph(hspans, vspans, junctions, th)

    geoms = [ed["geometry"] for ed in edges]
    polys = [p for p in polygonize(unary_union(geoms)) if p.area > 0] if geoms else []
    areas = sorted(p.area for p in polys)
    median_area = statistics.median(areas) if areas else 0.0
    # A sliver is caught by the aspect test and by being tiny relative to its
    # peers; the absolute floor is a few wall-thicknesses squared (NOT unit**2,
    # which wrongly rejects a legitimately thin room hung off long walls).
    min_area = max(median_area * 0.2, (th ** 2) * 4.0)
    line_tol = th * 0.75
    # Corners must coincide with an ACTUAL graph junction — edges are built from
    # exact junction coordinates, so this stays tight (no large nearest-junction
    # slack that could accept a fabricated corner). Goal §wall_reconstruction.
    vertex_tol = th * 0.5

    fpts = []
    if furniture:
        for f in furniture:
            iid = str(f.get("item_id", ""))
            if "window" in iid or "door" in iid:
                continue
            try:
                fpts.append((f, Point(float(f["cx"]), float(f["cy"]))))
            except (KeyError, TypeError, ValueError):
                continue

    jcoords = [(j["coordinate"][0], j["coordinate"][1], j["junction_id"]) for j in junctions]

    def _nearest_junction(x, y):
        best, bid = vertex_tol, None
        for jx, jy, jid in jcoords:
            d = math.hypot(x - jx, y - jy)
            if d <= best:
                best, bid = d, jid
        return bid

    rooms = []
    room_diag = []
    rid = 0
    for p in polys:
        rid += 1
        minx, miny, maxx, maxy = p.bounds
        w, h = maxx - minx, maxy - miny
        aspect = max(w, h) / max(1e-6, min(w, h))
        coords = list(p.exterior.coords)
        reasons: list[str] = []
        status = "CONFIRMED"

        if not (p.is_valid and p.is_simple and p.area > 0):
            status, reasons = "INVALID", ["polygon not valid/simple"]
        else:
            # every corner must be a proven junction
            corner_jids: list[str] = []
            for (vx, vy) in coords[:-1]:
                jid = _nearest_junction(vx, vy)
                if jid is None:
                    reasons.append(
                        f"corner ({round(vx, 1)},{round(vy, 1)}) is not a proven junction")
                else:
                    corner_jids.append(jid)
            # every boundary segment must map to provenance-bearing edges
            edge_support = []
            min_cov = 1.0
            support_walls: set[str] = set()
            support_src: set[int] = set()
            for a, b in zip(coords[:-1], coords[1:], strict=False):
                cov, wl, sr, eids = _coverage_by_edges(a, b, edges, line_tol)
                edge_support.append({"segment": [ [round(a[0], 1), round(a[1], 1)],
                                                  [round(b[0], 1), round(b[1], 1)] ],
                                     "coverage": round(cov, 3), "edge_ids": eids,
                                     "wall_ids": wl})
                min_cov = min(min_cov, cov)
                support_walls.update(wl)
                support_src.update(sr)
                if cov < 0.9:
                    reasons.append(
                        f"edge {[round(a[0], 1), round(a[1], 1)]}->"
                        f"{[round(b[0], 1), round(b[1], 1)]} only {round(cov * 100)}% "
                        "supported by source walls")
            if reasons:
                status = "UNSUPPORTED"
            elif p.area < min_area or aspect > 6.0:
                status, reasons = "SLIVER", [
                    f"area {round(p.area)} < min {round(min_area)}" if p.area < min_area
                    else f"aspect {round(aspect, 1)} > 6.0"]
            else:
                status = "CONFIRMED"

        fids = ([str(f.get("uid") or f.get("item_id")) for f, pt in fpts if p.covers(pt)]
                if status == "CONFIRMED" else [])
        room = {
            "room_id": f"R{rid}",
            "polygon": [(round(x, 2), round(y, 2)) for x, y in coords],
            "bbox": [round(minx, 2), round(miny, 2), round(w, 2), round(h, 2)],
            "area": round(p.area, 1),
            "validation_status": status,
            "wall_supported": status == "CONFIRMED",
            "supporting_wall_ids": sorted(support_walls) if status != "INVALID" else [],
            "supporting_source_ids": sorted(support_src) if status != "INVALID" else [],
            "corner_junction_ids": corner_jids if status != "INVALID" else [],
            "min_edge_coverage": round(min_cov, 3) if status != "INVALID" else 0.0,
            "furniture_ids": fids,
            "rejection_reasons": reasons,
        }
        rooms.append(room)
        room_diag.append({"room_id": room["room_id"], "status": status,
                          "reasons": reasons, "area": room["area"]})

    confirmed = [r for r in rooms if r["validation_status"] == "CONFIRMED"]
    public_junctions = [dict(j) for j in junctions]
    public_edges = [{k: v for k, v in ed.items() if k != "geometry"} for ed in edges]
    return {
        "rooms": confirmed,
        "all_candidates": rooms,
        "junctions": public_junctions,
        "edges": public_edges,
        "tolerances": tol,
        "diagnostics": {"walls": wall_diag, "rooms": room_diag, "opening_bridges": bridge_diag},
        "stats": {
            "hspans": len(hspans), "vspans": len(vspans),
            "junctions": len(junctions),
            "L": sum(1 for j in junctions if j["junction_type"] == "L_JUNCTION"),
            "T": sum(1 for j in junctions if j["junction_type"] == "T_JUNCTION"),
            "edges": len(edges), "raw_polys": len(polys),
            "confirmed": len(confirmed),
            "openings_bridged": sum(1 for b in bridge_diag if b.get("bridge_applied")),
            "by_status": {s: sum(1 for r in rooms if r["validation_status"] == s)
                          for s in ("CONFIRMED", "SLIVER", "UNSUPPORTED", "INVALID")},
        },
    }


def validate_opening_bridges(
    openings: list[dict[str, Any]],
    repaired_walls: list[dict[str, Any]],
    thickness: float,
) -> list[dict[str, Any]]:
    """Validate opening bridges against repaired wall spans.

    For every VALID PDF opening:
      - identifies supporting repaired wall
      - calculates opening footprint intersection with that wall
      - bridges ONLY if a real intersection/crossing exists (intersection_length > 0)
      - records: opening_id, supporting_wall_id, intersection_length, bridge_applied.
    """
    from shapely.geometry import LineString, box

    results: list[dict[str, Any]] = []
    reach = max(2.0, float(thickness) * 0.75)
    for o in openings:
        if o.get("validation_status") != "VALID" or o.get("uncertain"):
            continue
        try:
            cx = float(o.get("cx", o.get("x")))
            cy = float(o.get("cy", o.get("y")))
            ow = float(o.get("w", o.get("width", 0)))
            oh = float(o.get("h", o.get("height", 0)))
        except (TypeError, ValueError):
            continue
        if ow <= 0 or oh <= 0:
            continue

        footprint = box(cx - ow / 2, cy - oh / 2, cx + ow / 2, cy + oh / 2)
        best_wall_id: str | None = None
        best_source_ids: list[str] = []
        best_len = 0.0
        best_orientation = "h" if ow >= oh else "v"

        for r in repaired_walls:
            s = r["seg"]
            line = LineString([(s[0], s[1]), (s[2], s[3])])
            wall_band = line.buffer(reach)
            if footprint.intersects(wall_band):
                inter = footprint.intersection(wall_band)
                ilen = max(inter.bounds[2] - inter.bounds[0], inter.bounds[3] - inter.bounds[1])
                if ilen > best_len:
                    best_len = ilen
                    best_wall_id = r["source_wall_ids"][0] if r.get("source_wall_ids") else None
                    best_source_ids = r.get("source_wall_ids", [])
                    best_orientation = r.get("orientation", best_orientation)

        applied = best_len > 0.0
        results.append({
            "opening_id": str(o.get("id") or o.get("uid") or ""),
            "kind": o.get("kind", "door"),
            "supporting_wall_id": best_wall_id,
            "supporting_source_ids": best_source_ids,
            "intersection_length": round(best_len, 2),
            "bridge_applied": applied,
            "reason": "geometric_intersection_ok" if applied else "no_geometric_wall_intersection",
            "cx": cx,
            "cy": cy,
            "w": ow,
            "h": oh,
            "box": (cx - ow / 2, cy - oh / 2, cx + ow / 2, cy + oh / 2),
            "orientation": best_orientation,
        })
    return results


def opening_on_wall(opening, hspans, vspans, thickness):
    """Validate that a door/window opening lies ON a real collapsed wall span.

    Returns ``{on_wall, wall_id, source_ids, distance, axis}``.  An opening is
    tied to a wall only when its centre is within one wall thickness of that
    span's centreline AND within or bounding the span's longitudinal extent.
    """
    from shapely.geometry import LineString, box

    try:
        ox = float(opening.get("x", opening.get("cx")))
        oy = float(opening.get("y", opening.get("cy")))
        ow = float(opening.get("w", opening.get("width", thickness)))
        oh = float(opening.get("h", opening.get("height", thickness)))
    except (TypeError, ValueError):
        return {"on_wall": False, "wall_id": None, "source_ids": [], "distance": None, "axis": None}

    footprint = box(ox - ow / 2, oy - oh / 2, ox + ow / 2, oy + oh / 2)
    reach = max(2.0, float(thickness) * 0.75)
    best = None

    for si, (c, a0, a1, sids) in enumerate(hspans):
        line = LineString([(a0, c), (a1, c)])
        d = line.distance(footprint)
        if d <= reach:
            if best is None or d < best["distance"]:
                best = {"on_wall": True, "wall_id": f"H{si}", "source_ids": sorted(sids),
                        "distance": round(d, 2), "axis": "H"}

    for si, (c, a0, a1, sids) in enumerate(vspans):
        line = LineString([(c, a0), (c, a1)])
        d = line.distance(footprint)
        if d <= reach:
            if best is None or d < best["distance"]:
                best = {"on_wall": True, "wall_id": f"V{si}", "source_ids": sorted(sids),
                        "distance": round(d, 2), "axis": "V"}

    return best or {"on_wall": False, "wall_id": None, "source_ids": [],
                    "distance": None, "axis": None}
