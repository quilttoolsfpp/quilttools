"""Technique-aware template cutting planner (DESIGN_fabric_cutplan.md).

Turns finished-size pattern pieces into per-fabric cutting instructions:
strips with subcuts, paired triangles, batch units (stitch-and-flip,
2/8-at-a-time HSTs, 4-at-a-time flying geese), pieced strips for pieces
longer than the usable width of fabric, and an NFP-nested yardage panel
for everything that doesn't earn a strip.

Pure Python / stdlib (plus the sibling pure modules quilttools_geometry
and quilttools_nesting) so it can be unit-tested outside Inkscape.

ALL DIMENSIONS IN THIS MODULE ARE INCHES. Callers convert from px.

Canonical input piece (one entry per leaf region / cut shape):

    {
        "id": <hashable, stable region id>,
        "polygon": [(x, y), ...],      # finished size, inches, y-down
        "fabric": <fabric key>,         # colour hex or role name
        "qty": 1,                       # explicit quantity (quilt-level callers
                                        #  multiply block counts in here)
        "label": "A3",
        "meta": {                       # all optional -> legacy defaults
            "grain": "free",            # free | fixed | fussy
            "technique": "template",    # template | stitch_flip | hst2 | hst8 | fg4
            "sf_bases": [id, ...],      # stitch_flip: pieces extended under the corner
            "batch_group": "hst-...",   # hst2/hst8/fg4 grouping key
            "suggested": False,
        },
    }

The planner never assumes "one block's worth" of pieces: quantities are
explicit and there is no per-block state, so block export and quilt
export share this code path.
"""

import math

from quilttools_geometry import (
    polygon_area,
    polygon_area_signed,
    polygon_centroid,
    offset_polygon,
    simplify_polygon,
)
import quilttools_nesting as nesting

EPS = 1e-6
DEFAULT_OPTIONS = {
    "wof_in": 40.0,           # usable width of fabric
    "sa_in": 0.25,
    "oversize_batch": True,   # HST/geese cut oversize for trimming
    "use_techniques": True,   # False = "Templates only" export override
    "min_strip_util": 0.5,
    "spacing_in": 0.2,        # gap between panel-nested pieces
    "border_join": "straight",  # straight | diagonal (pieced strips)
    "snap_eighth": True,      # round rectangular cut dims UP to 1/8"
}

GRAIN_FREE = "free"
GRAIN_FIXED = "fixed"
GRAIN_FUSSY = "fussy"

_EIGHTHS = {0: "", 1: "⅛", 2: "¼", 3: "⅜", 4: "½",
            5: "⅝", 6: "¾", 7: "⅞"}


def fmt_in(v):
    """4.625 -> '4⅝"'. Values are shown to the nearest 1/8 (round up)."""
    eighths = int(math.ceil(v * 8.0 - _SNAP_SLACK))
    whole, frac = divmod(max(eighths, 0), 8)
    txt = ("%d" % whole if whole else "") + _EIGHTHS[frac]
    return (txt if txt else "0") + '"'


def _opt(options):
    o = dict(DEFAULT_OPTIONS)
    if options:
        o.update(options)
    return o


# Snapping rounds UP to the next 1/8", but tolerates ~1/160" of numeric
# wobble (EQ imports, seam-extension unions) so 8.0002" stays 8", not 8-1/8".
_SNAP_SLACK = 0.05  # in eighth-units = 0.00625"


def _snap8(v, enabled=True):
    return math.ceil(v * 8.0 - _SNAP_SLACK) / 8.0 if enabled else v


def _bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_wh(poly):
    x0, y0, x1, y1 = _bbox(poly)
    return x1 - x0, y1 - y0


def _norm_origin(poly):
    x0, y0, _, _ = _bbox(poly)
    return [(p[0] - x0, p[1] - y0) for p in poly]


def _rot(poly, angle_deg):
    r = math.radians(angle_deg)
    c, s = math.cos(r), math.sin(r)
    return [(p[0] * c - p[1] * s, p[0] * s + p[1] * c) for p in poly]


def clean_collinear(poly, tol_in=0.015):
    """Remove phantom vertices: points lying (nearly) on the straight line
    between their neighbours. EQ imports and healed geometry leave seam
    endpoints on piece edges with sub-thousandth-inch wobble, which the
    global simplify_polygon (1e-4 tolerance) keeps — turning triangles
    into 5-gons. Cutting tolerance is 1/64", so anything within tol_in
    (default 0.015") of the line is noise for planning purposes."""
    pts = [tuple(p) for p in poly]
    # dedupe
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0],
                                   out[0][1] - out[-1][1]) <= 1e-6:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        n = len(out)
        for i in range(n):
            a, b, c = out[(i - 1) % n], out[i], out[(i + 1) % n]
            dx, dy = c[0] - a[0], c[1] - a[1]
            ln = math.hypot(dx, dy)
            if ln < 1e-9:
                continue
            dist = abs(dx * (b[1] - a[1]) - dy * (b[0] - a[0])) / ln
            if dist <= tol_in:
                out.pop(i)
                changed = True
                break
    return out


def _offset_or_bbox(poly, amount):
    """SA-offset a polygon; fall back to a padded bbox if the offset
    degenerates (mirrors the defensive pattern used elsewhere)."""
    out = offset_polygon(poly, amount, miter_limit=4.0)
    if out and len(out) >= 3:
        return out
    x0, y0, x1, y1 = _bbox(poly)
    return [(x0 - amount, y0 - amount), (x1 + amount, y0 - amount),
            (x1 + amount, y1 + amount), (x0 - amount, y1 + amount)]


# ---------------------------------------------------------------------------
# Shape classification
# ---------------------------------------------------------------------------

def classify_piece(polygon, tol=0.02):
    """Classify a finished-size polygon.

    Returns {"kind": square|rect|tri|other, "w", "h", "angle", "legs",
    "is45", "n"} where w/h are the true side lengths (NOT the bbox) for
    rects, so on-point squares still cut square-to-grain; angle is the
    design rotation of the first edge (deg); legs are the two sides
    around the right angle for triangles.
    """
    poly = clean_collinear(simplify_polygon(list(polygon)))
    n = len(poly)
    bw, bh = _bbox_wh(poly)
    out = {"kind": "other", "w": bw, "h": bh, "angle": 0.0,
           "legs": None, "is45": False, "n": n}
    if n == 3:
        # Find the right-angle vertex, if any.
        for i in range(3):
            a, b, c = poly[(i - 1) % 3], poly[i], poly[(i + 1) % 3]
            v1 = (a[0] - b[0], a[1] - b[1])
            v2 = (c[0] - b[0], c[1] - b[1])
            l1 = math.hypot(*v1)
            l2 = math.hypot(*v2)
            if l1 < EPS or l2 < EPS:
                continue
            cosang = (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)
            if abs(cosang) < tol:  # ~90 degrees
                legs = (min(l1, l2), max(l1, l2))
                out.update({
                    "kind": "tri", "legs": legs,
                    "is45": abs(legs[0] - legs[1]) <= tol * legs[1],
                    "angle": math.degrees(math.atan2(a[1] - b[1], a[0] - b[0])),
                    "w": legs[1], "h": legs[0],
                })
                return out
        return out
    if n == 4:
        sides = []
        for i in range(4):
            p, q = poly[i], poly[(i + 1) % 4]
            sides.append(math.hypot(q[0] - p[0], q[1] - p[1]))
        for i in range(4):
            a, b, c = poly[(i - 1) % 4], poly[i], poly[(i + 1) % 4]
            v1 = (a[0] - b[0], a[1] - b[1])
            v2 = (c[0] - b[0], c[1] - b[1])
            l1 = math.hypot(*v1)
            l2 = math.hypot(*v2)
            if l1 < EPS or l2 < EPS:
                return out
            cosang = (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)
            if abs(cosang) > tol:
                return out  # not a rectangle
        w = (sides[0] + sides[2]) / 2.0
        h = (sides[1] + sides[3]) / 2.0
        p, q = poly[0], poly[1]
        angle = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
        kind = "square" if abs(w - h) <= tol * max(w, h) else "rect"
        out.update({"kind": kind, "w": max(w, h), "h": min(w, h),
                    "angle": angle})
        return out
    return out


def congruence_key(polygon, tol=0.5):
    """Canonical signature for template congruence under rotation and
    translation — NOT mirroring (a mirrored asymmetric piece needs its own
    template). Congruent pieces share a key.

    tol is the length rounding grain in the polygon's units (pass ~1.0 for
    px coordinates, ~0.01 for inches). Turn angles bucket to 2 degrees.
    """
    poly = clean_collinear(simplify_polygon(list(polygon)), tol_in=tol)
    n = len(poly)
    if n < 3:
        return ("degenerate", n)
    if polygon_area_signed(poly) < 0:
        poly = poly[::-1]
    seq = []
    for i in range(n):
        p, q, r = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        e = math.hypot(q[0] - p[0], q[1] - p[1])
        turn = math.degrees(
            math.atan2(r[1] - q[1], r[0] - q[0])
            - math.atan2(q[1] - p[1], q[0] - p[0]))
        while turn <= -180.0:
            turn += 360.0
        while turn > 180.0:
            turn -= 360.0
        seq.append((int(round(e / tol)), int(round(turn / 2.0))))
    best = min(tuple(seq[i:] + seq[:i]) for i in range(n))
    return (n,) + best


# ---------------------------------------------------------------------------
# Stitch-and-flip: guillotine seam extension over (possibly pieced) bases
# ---------------------------------------------------------------------------

def _clip_halfplane(poly, p0, d, keep_left):
    """Sutherland-Hodgman clip of poly against the line through p0 with
    direction d, keeping the left (or right) side."""
    def side(pt):
        s = d[0] * (pt[1] - p0[1]) - d[1] * (pt[0] - p0[0])
        return s if keep_left else -s

    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        sa_, sb_ = side(a), side(b)
        if sa_ >= -EPS:
            out.append(a)
        if (sa_ > EPS and sb_ < -EPS) or (sa_ < -EPS and sb_ > EPS):
            t = sa_ / (sa_ - sb_)
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return simplify_polygon(out) if len(out) >= 3 else []


def _longest_edge(poly):
    best, blen = None, -1.0
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        ln = math.hypot(q[0] - p[0], q[1] - p[1])
        if ln > blen:
            best, blen = (p, q), ln
    return best


def _project_onto(seg, pt):
    (p, q) = seg
    dx, dy = q[0] - p[0], q[1] - p[1]
    ln2 = dx * dx + dy * dy
    if ln2 < EPS:
        return 0.0, 0.0
    t = ((pt[0] - p[0]) * dx + (pt[1] - p[1]) * dy) / ln2
    dist = abs((pt[0] - p[0]) * dy - (pt[1] - p[1]) * dx) / math.sqrt(ln2)
    return t, dist


def _shared_span(hyp, base_poly, tol=0.02):
    """Portion [t0, t1] of the hypotenuse that base_poly borders, plus the
    base's outgoing seam directions at each end (None when the base simply
    continues past that end of the hypotenuse)."""
    n = len(base_poly)
    spans = []
    for i in range(n):
        p, q = base_poly[i], base_poly[(i + 1) % n]
        tp, dp_ = _project_onto(hyp, p)
        tq, dq_ = _project_onto(hyp, q)
        if dp_ <= tol and dq_ <= tol:
            lo, hi = min(tp, tq), max(tp, tq)
            lo, hi = max(lo, 0.0), min(hi, 1.0)
            if hi - lo > tol:
                spans.append((lo, hi, i))
    if not spans:
        return None
    lo = min(s[0] for s in spans)
    hi = max(s[1] for s in spans)

    def seam_dir_at(t_end):
        """Direction of the base edge leaving the hypotenuse at span end."""
        px = (hyp[0][0] + t_end * (hyp[1][0] - hyp[0][0]),
              hyp[0][1] + t_end * (hyp[1][1] - hyp[0][1]))
        for j in range(n):
            v = base_poly[j]
            if math.hypot(v[0] - px[0], v[1] - px[1]) <= tol * 2:
                for k in (j - 1, j + 1):
                    w = base_poly[k % n]
                    tw, dw = _project_onto(hyp, w)
                    if dw > tol:  # edge leaves the hyp line
                        return (w[0] - v[0], w[1] - v[1])
        return None

    return lo, hi, seam_dir_at(lo), seam_dir_at(hi)


def snowball_extend(tri_poly, base_polys, tol=0.02):
    """Extend base pieces under a stitch-and-flip corner triangle.

    Continues each straight seam that terminates on the triangle's
    hypotenuse straight across the corner footprint (guillotine logic),
    partitioning the footprint into cells; each base's cut shape becomes
    union(base, its cell).

    Handles any number of bases along the seam by peeling them off in
    hypotenuse order: the seam at each junction between two neighbouring
    bases is extended across the remaining footprint, splitting it.

    Returns (extended_polys aligned with base_polys, None) on success or
    (None, reason) when the layout is not cleanly guillotine-extendable.
    """
    tri = clean_collinear(simplify_polygon(list(tri_poly)))
    if len(tri) != 3:
        return None, "corner piece is not a triangle"
    hyp = _longest_edge(tri)
    hyp_len = math.hypot(hyp[1][0] - hyp[0][0], hyp[1][1] - hyp[0][1])
    tri_area = polygon_area(tri)
    t_tol = max(tol / max(hyp_len, EPS), 1e-4)

    def hyp_pt(t):
        return (hyp[0][0] + t * (hyp[1][0] - hyp[0][0]),
                hyp[0][1] + t * (hyp[1][1] - hyp[0][1]))

    spans = []
    for idx, bp in enumerate(base_polys):
        span = _shared_span(hyp, clean_collinear(simplify_polygon(list(bp))),
                            tol)
        if span is None:
            return None, "a base piece does not touch the corner seam"
        spans.append((span[0], span[1], span[2], span[3], idx))
    spans.sort()

    # The bases together must cover the whole seam, without overlaps.
    if spans[0][0] > t_tol or spans[-1][1] < 1.0 - t_tol:
        return None, ("the selected base pieces do not cover the whole "
                      "corner seam - include every piece the corner "
                      "flips onto")
    for (lo1, hi1, *_), (lo2, hi2, *_) in zip(spans, spans[1:]):
        if lo2 > hi1 + t_tol:
            return None, ("the selected base pieces leave a gap along the "
                          "corner seam - include every piece the corner "
                          "flips onto")
        if lo2 < hi1 - t_tol:
            return None, "base pieces overlap along the corner seam"

    # Peel bases off the footprint in seam order. At each junction the
    # departing seams of the two neighbours must lie on ONE straight line
    # (guillotine); that line splits the remaining footprint.
    cells = [None] * len(base_polys)
    remaining = list(tri)
    for k, (lo, hi, dir_lo, dir_hi, idx) in enumerate(spans):
        if k == len(spans) - 1:
            cell = remaining
            remaining = []
        else:
            nxt = spans[k + 1]
            d = dir_hi or nxt[2]
            if d is None:
                return None, ("no seam found at a junction between base "
                              "pieces (non-guillotine layout)")
            if dir_hi is not None and nxt[2] is not None:
                cross = dir_hi[0] * nxt[2][1] - dir_hi[1] * nxt[2][0]
                if abs(cross) > tol * math.hypot(*dir_hi) * \
                        math.hypot(*nxt[2]):
                    return None, ("the seams meeting the corner at a "
                                  "junction do not continue in one "
                                  "straight line (non-guillotine layout)")
            p0 = hyp_pt((hi + nxt[0]) / 2.0)
            pc = hyp_pt((lo + hi) / 2.0)
            keep = (d[0] * (pc[1] - p0[1]) - d[1] * (pc[0] - p0[0])) >= 0
            cell = _clip_halfplane(remaining, p0, d, keep)
            remaining = _clip_halfplane(remaining, p0, d, not keep)
        if not cell or polygon_area(cell) < EPS:
            return None, "seam extension produced an empty cell"
        cells[idx] = cell

    total = sum(polygon_area(c) for c in cells)
    if abs(total - tri_area) > max(tri_area * 0.02, 1e-4):
        return None, ("extended seams do not tile the corner cleanly "
                      "(non-guillotine layout)")

    extended = []
    for bp, cell in zip(base_polys, cells):
        merged = nesting.convex_hull(list(bp) + list(cell))
        want = polygon_area(list(bp)) + polygon_area(cell)
        if abs(polygon_area(merged) - want) > max(want * 0.02, 1e-4):
            return None, ("extended piece is not convex; cut it as a "
                          "template instead")
        extended.append(merged)
    return extended, None


def find_snowball_bases(tri_poly, candidate_polys, tol=0.02):
    """Indices of candidate polygons that border the triangle's
    hypotenuse (the pieces a stitch-and-flip corner flips onto)."""
    tri = clean_collinear(simplify_polygon(list(tri_poly)))
    if len(tri) != 3:
        return []
    hyp = _longest_edge(tri)
    hits = []
    for i, cand in enumerate(candidate_polys):
        span = _shared_span(hyp, clean_collinear(simplify_polygon(list(cand))),
                            tol)
        if span is not None:
            hits.append(i)
    return hits


def resolve_appliques(pieces):
    """Identify pieces with technique="applique" or is_applique=True,
    and union their polygons with their base pieces (listed in meta["app_bases"]).
    
    Returns overrides dict {base_id: extended_polygon}.
    """
    import quilttools_geometry as geom
    
    by_id = {str(p["id"]): p for p in pieces}
    by_label = {str(p.get("label", "")): p for p in pieces}
    
    overrides = {}
    
    for p in pieces:
        m = p.get("meta") or {}
        is_app = (m.get("technique") == "applique") or m.get("is_applique")
        if not is_app:
            continue
            
        app_bases = m.get("app_bases") or []
        if not app_bases:
            continue
            
        app_poly = p["polygon"]
        for base_ref in app_bases:
            base_ref_str = str(base_ref)
            base_piece = by_id.get(base_ref_str) or by_label.get(base_ref_str)
            if base_piece is None:
                continue
                
            bid = base_piece["id"]
            base_poly = overrides.get(bid, base_piece["polygon"])
            
            try:
                union_poly = geom.get_polygon_union([base_poly, app_poly])
                if union_poly:
                    overrides[bid] = union_poly
            except Exception:
                pass
                
    return overrides


def resolve_stitch_flips(pieces, exclude_ids=()):
    """Process every stitch_flip tag in DEPENDENCY order and compute the
    resulting geometry.

    Double-layer corners: when corner X flips over corner Y (Y appears in
    X's sf_bases), X's seam extension restores Y's full pre-trim footprint
    — so X must be processed first, and Y is then analysed on its EXTENDED
    polygon. This is why processing order matters and why a piece's raw
    (visible) polygon can be the wrong shape to analyse.

    Returns (corners, overrides, warnings):
      corners   {id: {"legs": (a,b), "is45": bool, "poly": analysed tri}}
      overrides {id: extended polygon} for every base piece
    exclude_ids: tags to ignore (the Mark tool excludes the piece being
    re-tagged so its stale tag cannot pre-extend its own bases).
    """
    orig_id_map = {str(p["id"]): p["id"] for p in pieces}
    exclude_str = {str(eid) for eid in exclude_ids}

    norm_pieces = []
    for p in pieces:
        m = dict(p.get("meta") or {})
        if "sf_bases" in m and m["sf_bases"]:
            m["sf_bases"] = [str(b) for b in m["sf_bases"]]
        norm_pieces.append({
            "id": str(p["id"]),
            "polygon": p["polygon"],
            "label": p.get("label", str(p["id"])),
            "meta": m
        })

    by_id = {p["id"]: p for p in norm_pieces}
    sf = [p for p in norm_pieces
          if (p.get("meta") or {}).get("technique") == "stitch_flip"
          and p["id"] not in exclude_str]

    corners, overrides, warnings = {}, {}, []
    remaining = list(sf)
    while remaining:
        pick = None
        for p in remaining:
            # X goes first if no OTHER unprocessed corner flips onto X.
            if not any(p["id"] in ((q.get("meta") or {}).get("sf_bases") or [])
                       for q in remaining if q is not p):
                pick = p
                break
        if pick is None:
            pick = remaining[0]
            warnings.append("Stitch-and-flip corners reference each other "
                            "in a loop; processing order is arbitrary.")
        remaining.remove(pick)
        label = pick.get("label", str(pick["id"]))
        m = pick.get("meta") or {}
        tri_poly = overrides.get(pick["id"], pick["polygon"])
        info = classify_piece(tri_poly)
        if info["kind"] != "tri":
            warnings.append("%s tagged stitch-and-flip but is not a "
                            "triangle; cut as template." % label)
            continue
        base_ids = [b for b in (m.get("sf_bases") or []) if b in by_id]
        if not base_ids:
            warnings.append("%s: stitch-and-flip tag has no base pieces; "
                            "cut as template." % label)
            continue
        base_polys = [overrides.get(b, by_id[b]["polygon"])
                      for b in base_ids]
        extended, err = snowball_extend(tri_poly, base_polys)
        if err:
            warnings.append("%s: stitch-and-flip not applied (%s); cut as "
                            "template." % (label, err))
            continue
        for bid, ext in zip(base_ids, extended):
            overrides[bid] = ext
        corners[pick["id"]] = {"legs": info["legs"], "is45": info["is45"],
                               "poly": tri_poly}

    orig_corners = {orig_id_map[cid]: val for cid, val in corners.items()}
    orig_overrides = {orig_id_map[bid]: val for bid, val in overrides.items()}
    return orig_corners, orig_overrides, warnings


def detect_snowball_candidates(pieces, outline, tol=0.05):
    """Suggest stitch-and-flip corners: 45-degree right triangles whose two
    legs both lie along the block outline (i.e. sit in a corner of the
    block or of a guillotine sub-unit bounded by the outline).

    Returns a list of piece ids. Pure geometry; the Mark tool decides how
    to present/confirm them.
    """
    out_edges = []
    n = len(outline)
    for i in range(n):
        out_edges.append((outline[i], outline[(i + 1) % n]))

    def on_outline(p, q):
        for seg in out_edges:
            tp, dp_ = _project_onto(seg, p)
            tq, dq_ = _project_onto(seg, q)
            if dp_ <= tol and dq_ <= tol and -tol <= tp <= 1 + tol \
                    and -tol <= tq <= 1 + tol:
                return True
        return False

    hits = []
    for pc in pieces:
        info = classify_piece(pc["polygon"])
        if info["kind"] != "tri" or not info["is45"]:
            continue
        poly = clean_collinear(simplify_polygon(list(pc["polygon"])))
        hyp = _longest_edge(poly)
        hyp_set = {tuple(hyp[0]), tuple(hyp[1])}
        legs = [(p, q) for (p, q) in [(poly[i], poly[(i + 1) % 3])
                                      for i in range(3)]
                if {tuple(p), tuple(q)} != hyp_set]
        if len(legs) == 2 and all(on_outline(p, q) for p, q in legs):
            hits.append(pc["id"])
    return hits


# ---------------------------------------------------------------------------
# Technique expansion: pieces -> cut units
# ---------------------------------------------------------------------------

def _meta(piece):
    m = dict(piece.get("meta") or {})
    m.setdefault("grain", GRAIN_FREE)
    m.setdefault("technique", "template")
    return m


def _rect_unit(fabric, w, h, qty, labels, source, opt, grain=GRAIN_FREE,
               secondary=None, contains=1):
    snap = opt["snap_eighth"]
    w, h = max(w, h), min(w, h)
    return {"type": "rect", "fabric": fabric,
            "w": _snap8(w, snap), "h": _snap8(h, snap),
            "qty": int(qty), "labels": list(labels), "source": source,
            "grain": grain, "secondary": secondary, "contains": contains,
            "poly": None, "design_angle": 0.0}


def _poly_unit(kind, fabric, poly, qty, labels, source, opt,
               grain=GRAIN_FREE, design_angle=0.0):
    return {"type": kind, "fabric": fabric, "poly": _norm_origin(poly),
            "qty": int(qty), "labels": list(labels), "source": source,
            "grain": grain, "secondary": None, "contains": 1,
            "design_angle": design_angle,
            "w": _bbox_wh(poly)[0], "h": _bbox_wh(poly)[1]}


def _hst_sq(leg, sa, oversize):
    # finished + 7/8" exact (3.5*sa) or +1" oversize-and-trim (4*sa).
    return leg + (4.0 * sa if oversize else 3.5 * sa)


def expand_units(pieces, options=None):
    """Apply technique tags and produce cut units.

    Returns (units, warnings, notes). Units are what the strip planner
    consumes; each carries its own fabric so callers can split later.
    """
    opt = _opt(options)
    sa = opt["sa_in"]
    warnings, notes = [], []
    by_id = {p["id"]: p for p in pieces}
    poly_override = {}   # id -> extended polygon (stitch-and-flip bases)
    consumed = set()     # ids emitted through a technique path
    units = []

    use_tech = opt["use_techniques"]

    # --- Stitch-and-flip corners (dependency-ordered: double-layer
    # corners are analysed on their EXTENDED footprint) ----------------
    if use_tech:
        corners, sf_overrides, sf_warn = resolve_stitch_flips(pieces)
        warnings.extend(sf_warn)
        poly_override.update(sf_overrides)
        
        app_overrides = resolve_appliques(pieces)
        poly_override.update(app_overrides)
        for p in pieces:
            c = corners.get(p["id"])
            if c is None:
                continue
            m = _meta(p)
            legs = c["legs"]
            if not c["is45"]:
                warnings.append("%s: rectangular stitch-and-flip corner - "
                                "a template method is usually preferred."
                                % p["label"])
                units.append(_rect_unit(p["fabric"], legs[1] + 2 * sa,
                                        legs[0] + 2 * sa, p.get("qty", 1),
                                        [p["label"]], "stitch_flip", opt,
                                        m["grain"]))
            else:
                side = (legs[0] + legs[1]) / 2.0 + 2 * sa
                units.append(_rect_unit(p["fabric"], side, side,
                                        p.get("qty", 1), [p["label"]],
                                        "stitch_flip", opt, m["grain"]))
            consumed.add(p["id"])
            notes.append("%s: stitch-and-flip corner %s square; sew on the "
                         "diagonal, trim to %s SA (bonus HST possible from "
                         "the trimmed corner)."
                         % (p["label"], fmt_in((legs[0] + legs[1]) / 2.0
                                               + 2 * sa), fmt_in(sa)))

    # --- Batch techniques (hst2 / hst8 / fg4) ------------------------
    if use_tech:
        batches = {}
        for p in pieces:
            if p["id"] in consumed:
                continue
            m = _meta(p)
            if m["technique"] not in ("hst2", "hst8", "fg4"):
                continue
            info = classify_piece(p["polygon"])
            if info["kind"] != "tri":
                warnings.append("%s tagged %s but is not a triangle; cut "
                                "as template." % (p["label"], m["technique"]))
                continue
            key = (m["technique"],
                   m.get("batch_group")
                   or "auto-%s-%s-%.3f" % (m["technique"], p["fabric"],
                                           info["legs"][1]))
            batches.setdefault(key, []).append((p, info))
            consumed.add(p["id"])

        for (tech, _), members in sorted(batches.items(),
                                         key=lambda kv: kv[0]):
            _expand_batch(tech, members, units, warnings, notes, opt)

    # --- Everything else: plain templates (and fussy cuts) -----------
    for p in pieces:
        if p["id"] in consumed:
            continue
        m = _meta(p)
        poly = poly_override.get(p["id"], p["polygon"])
        qty = p.get("qty", 1)
        if m["grain"] == GRAIN_FUSSY:
            units.append(_poly_unit("fussy", p["fabric"],
                                    _offset_or_bbox(poly, sa), qty,
                                    [p["label"]], "fussy", opt, GRAIN_FUSSY))
            continue
        info = classify_piece(poly)
        if info["kind"] in ("square", "rect"):
            # Always cut square-to-grain, even if on point in the design.
            units.append(_rect_unit(p["fabric"], info["w"] + 2 * sa,
                                    info["h"] + 2 * sa, qty, [p["label"]],
                                    "template", opt, m["grain"]))
        elif info["kind"] == "tri":
            tpl = _offset_or_bbox(poly, sa)
            # Normalise to legs-on-axes so grain lands on the legs.
            u = _poly_unit("tri", p["fabric"], _axis_align_tri(tpl), qty,
                           [p["label"]], "template", opt, m["grain"],
                           design_angle=info["angle"])
            u["legs"] = info["legs"]
            u["is45"] = info["is45"]
            units.append(u)
        else:
            units.append(_poly_unit("odd", p["fabric"],
                                    _offset_or_bbox(poly, sa), qty,
                                    [p["label"]], "template", opt,
                                    m["grain"], design_angle=info["angle"]))
    return units, warnings, notes


def _axis_align_tri(tpl):
    """Rotate a triangle template so its legs run with the grain
    (right-angle vertex at axis alignment)."""
    tri = clean_collinear(simplify_polygon(list(tpl)))
    if len(tri) != 3:
        return _norm_origin(tpl)
    hyp = _longest_edge(tri)
    corner = [p for p in tri if p not in hyp]
    if not corner:
        return _norm_origin(tri)
    c = corner[0]
    lega = next(p for p in hyp)
    ang = math.degrees(math.atan2(lega[1] - c[1], lega[0] - c[0]))
    best = None
    for cand in (-ang, -ang + 90, -ang + 180, -ang + 270):
        r = _rot(tri, cand)
        w, h = _bbox_wh(r)
        # prefer the orientation whose bbox is smallest then widest
        key = (round(w * h, 6), -round(w, 6))
        if best is None or key < best[0]:
            best = (key, r)
    return _norm_origin(best[1])


def _expand_batch(tech, members, units, warnings, notes, opt):
    sa = opt["sa_in"]
    over = opt["oversize_batch"]
    fabrics = {}
    for p, info in members:
        fabrics.setdefault(p["fabric"], []).append((p, info))

    if tech in ("hst2", "hst8"):
        for fab, mem in sorted(fabrics.items()):
            n = sum(p.get("qty", 1) for p, _ in mem)
            leg = sum(i["legs"][0] * p.get("qty", 1) for p, i in mem) / n
            labels = [p["label"] for p, _ in mem]
            if tech == "hst8":
                full, rem = divmod(n, 8)
                if full:
                    side = 2.0 * _hst_sq(leg, sa, over)
                    units.append(_rect_unit(fab, side, side, full, labels,
                                            "hst8", opt,
                                            secondary="cut the 8-at-a-time "
                                            "grid to yield 8 HSTs"))
                if rem:
                    warnings.append("%d %s triangle(s) left over from "
                                    "8-at-a-time grouping; cut via "
                                    "2-at-a-time." % (rem, fab))
                    n = rem
                else:
                    n = 0
            if n:
                sq = int(math.ceil(n / 2.0))
                side = _hst_sq(leg, sa, over)
                units.append(_rect_unit(fab, side, side, sq, labels, "hst2",
                                        opt,
                                        secondary="pair with the partner "
                                        "fabric square; sew both sides of "
                                        "the diagonal, cut apart"))
                if n % 2:
                    warnings.append("Odd number of %s HST triangles (%d); "
                                    "one square yields a spare HST."
                                    % (fab, n))
        notes.append("HST squares %s - %s."
                     % ("include trimming allowance (finished + 1\")"
                        if over else "are cut exact (finished + ⅞\")",
                        "disable 'Oversize batch units' to cut exact"
                        if over else
                        "enable 'Oversize batch units' to add trim room"))
        return

    if tech == "fg4":
        if len(fabrics) < 2:
            warnings.append("Flying geese group needs goose AND sky "
                            "fabrics; got %d fabric(s) - cut as templates."
                            % len(fabrics))
            for fab, mem in fabrics.items():
                for p, info in mem:
                    tpl = _offset_or_bbox(p["polygon"], sa)
                    units.append(_poly_unit("tri", fab, _axis_align_tri(tpl),
                                            p.get("qty", 1), [p["label"]],
                                            "template", opt))
            return
        # Larger average triangle = goose fabric, smaller = sky.
        sized = sorted(fabrics.items(),
                       key=lambda kv: -max(polygon_area(p["polygon"])
                                           for p, _ in kv[1]))
        goose_fab, goose_mem = sized[0]
        for fab, mem in sized[1:]:
            n_sky = sum(p.get("qty", 1) for p, _ in mem)
            leg = sum(i["legs"][0] * p.get("qty", 1)
                      for p, i in mem) / n_sky
            sq = int(math.ceil(n_sky / 2.0))
            side = leg + (4.0 * sa if over else 3.5 * sa)
            units.append(_rect_unit(fab, side, side, sq,
                                    [p["label"] for p, _ in mem], "fg4",
                                    opt, secondary="sky squares for "
                                    "4-at-a-time flying geese"))
        n_geese = sum(p.get("qty", 1) for p, _ in goose_mem)
        # goose finished width = hypotenuse of the goose triangle
        width = sum(max(_bbox_wh(p["polygon"])) * p.get("qty", 1)
                    for p, _ in goose_mem) / n_geese
        height = width / 2.0
        if any(abs(max(_bbox_wh(p["polygon"])) -
                   2 * min(_bbox_wh(p["polygon"]))) > 0.05 * width
               for p, _ in goose_mem):
            warnings.append("Flying geese group is not 2:1 "
                            "(width:height); check the tagged pieces.")
        big = int(math.ceil(n_geese / 4.0))
        side = width + (6.0 * sa if over else 5.0 * sa)
        units.append(_rect_unit(goose_fab, side, side, big,
                                [p["label"] for p, _ in goose_mem], "fg4",
                                opt, secondary="goose square for "
                                "4-at-a-time flying geese"))
        notes.append("Flying geese cut %s: goose square = width + %s, sky "
                     "squares = height + %s (%d geese of %s x %s)."
                     % ("oversized for trimming" if over else "exact",
                        fmt_in(6 * sa if over else 5 * sa),
                        fmt_in(4 * sa if over else 3.5 * sa),
                        n_geese, fmt_in(width), fmt_in(height)))
        return


# ---------------------------------------------------------------------------
# Pairing pass: nest leftover right triangles two-up into rectangles
# ---------------------------------------------------------------------------

def pair_triangles(units, warnings, opt):
    """Replace pairs of identical template triangles (same fabric & size)
    with two-template rectangles. Free-grain triangles always pair;
    fixed-grain triangles only pair when design orientations already
    complement (180 degrees apart)."""
    out = [u for u in units if u["type"] != "tri"]
    tris = [u for u in units if u["type"] == "tri"]
    groups = {}
    for u in tris:
        key = (u["fabric"], round(u["w"], 3), round(u["h"], 3))
        groups.setdefault(key, []).append(u)

    for key, grp in sorted(groups.items(), key=lambda kv: kv[0]):
        free_n = sum(u["qty"] for u in grp if u["grain"] == GRAIN_FREE)
        fixed = [u for u in grp if u["grain"] != GRAIN_FREE]
        labels = sorted({l for u in grp for l in u["labels"]})
        w, h = grp[0]["w"], grp[0]["h"]

        pairs, single = divmod(free_n, 2)
        # Fixed triangles: count complementary orientation pairs only.
        angles = []
        for u in fixed:
            angles.extend([u["design_angle"] % 360.0] * u["qty"])
        used = [False] * len(angles)
        blocked = 0
        for i in range(len(angles)):
            if used[i]:
                continue
            for j in range(i + 1, len(angles)):
                if not used[j] and abs(((angles[i] - angles[j]) % 360)
                                       - 180) < 5:
                    used[i] = used[j] = True
                    pairs += 1
                    break
            if not used[i]:
                blocked += 1
        if blocked:
            warnings.append("%d fixed-grain triangle(s) (%s) could not be "
                            "paired - grain lock limits rotation."
                            % (blocked, ", ".join(labels)))
        if pairs:
            out.append(_rect_unit(key[0], w, h, pairs, labels, "tri_pair",
                                  opt, GRAIN_FREE,
                                  secondary="cut each rectangle in half on "
                                  "the diagonal (2 triangles per rectangle)",
                                  contains=2))
        leftovers = single + blocked
        if leftovers:
            lone = dict(grp[0])
            lone["qty"] = leftovers
            lone["labels"] = labels
            out.append(lone)
    return out


# ---------------------------------------------------------------------------
# Strip building, pieced strips, panel
# ---------------------------------------------------------------------------

def _plan_fabric(units, opt):
    wof = opt["wof_in"]
    warnings, notes, ops = [], [], []

    units = pair_triangles(units, warnings, opt)

    strip_units, long_rects, panel_units = [], [], []
    for u in units:
        if u["type"] == "rect":
            if u["h"] > wof + EPS and u["w"] > wof + EPS:
                warnings.append("Piece(s) %s are larger than the fabric "
                                "width in both directions."
                                % ", ".join(u["labels"]))
                panel_units.append(u)
            elif u["w"] > wof + EPS:
                long_rects.append(u)
            else:
                strip_units.append(u)
        else:
            panel_units.append(u)

    # ---- pieced strips for over-WOF rectangles ----------------------
    pieced_widths = set()
    by_width = {}
    for u in long_rects:
        by_width.setdefault(round(u["h"], 3), []).append(u)
    for width, grp in sorted(by_width.items()):
        pieced_widths.add(width)
        rider_labels = []
        run = sum(u["w"] * u["qty"] for u in grp)
        cuts = [{"length": u["w"], "qty": u["qty"], "labels": u["labels"]}
                for u in grp]
        # Same-width strip units ride along in the pieced run.
        riders = [u for u in strip_units
                  if abs(u["h"] - width) <= 1e-3
                  or (u["grain"] == GRAIN_FREE
                      and abs(u["w"] - width) <= 1e-3)]
        for u in riders:
            strip_units.remove(u)
            ln = u["w"] if abs(u["h"] - width) <= 1e-3 else u["h"]
            run += ln * u["qty"]
            cuts.append({"length": ln, "qty": u["qty"],
                         "labels": u["labels"],
                         "secondary": u.get("secondary")})
            rider_labels.extend(u["labels"])
        join = opt["border_join"]
        allow = 0.5 if join == "straight" else width
        strips = max(1, int(math.ceil(run / wof)))
        while True:
            joins = max(0, strips - 1)
            need = int(math.ceil((run + joins * allow) / wof))
            if need == strips:
                break
            strips = need
        ops.append({"op": "pieced_strip", "width": width, "strips": strips,
                    "join": join, "join_allow": allow, "run": run,
                    "cuts": sorted(cuts, key=lambda c: -c["length"]),
                    "labels": sorted({l for c in cuts
                                      for l in c["labels"]})})
        if rider_labels:
            notes.append("Pieces %s share the %s pieced strips."
                         % (", ".join(sorted(rider_labels)), fmt_in(width)))
        if join == "straight":
            notes.append("%s strips: join end-to-end with straight seams "
                         "(preferred for long-arm quilting); diagonal "
                         "joins available via the border join option."
                         % fmt_in(width))

    # ---- plain strips ------------------------------------------------
    groups = {}
    for u in strip_units:
        # Free-grain units lie down (height = short side); fixed keep
        # their design height.
        if u["grain"] == GRAIN_FREE:
            hgt, wid = min(u["w"], u["h"]), max(u["w"], u["h"])
        else:
            hgt, wid = u["h"], u["w"]
        groups.setdefault(round(hgt, 3), []).append((wid, u))

    for hgt, grp in sorted(groups.items(), reverse=True):
        widths = []
        for wid, u in grp:
            widths.extend([(wid, u)] * u["qty"])
        widths.sort(key=lambda t: -t[0])
        cur, strips = None, []
        for wid, u in widths:
            if cur is None or cur["consumed"] + wid > wof + EPS:
                cur = {"consumed": 0.0, "cells": []}
                strips.append(cur)
            cur["cells"].append({"w": wid, "unit": u,
                                 "x": cur["consumed"]})
            cur["consumed"] += wid

        # Try to slot odd/loose shapes into remaining strip space.
        for strip in strips:
            for u in list(panel_units):
                if u["type"] not in ("odd", "tri"):
                    continue
                bw, bh = _odd_footprint(u, hgt)
                if bw is None:
                    continue
                while u["qty"] > 0 and strip["consumed"] + bw <= wof + EPS:
                    strip["cells"].append({"w": bw, "unit": u,
                                           "x": strip["consumed"],
                                           "shape": True})
                    strip["consumed"] += bw
                    u["qty"] -= 1
                if u["qty"] == 0:
                    panel_units.remove(u)

        for strip in strips:
            area = 0.0
            for cell in strip["cells"]:
                un = cell["unit"]
                if un["type"] == "rect":
                    area += cell["w"] * hgt if not un.get("poly") else 0
                else:
                    area += polygon_area(un["poly"])
            util = area / (hgt * strip["consumed"]) if strip["consumed"] \
                else 0.0
            if util + EPS < opt["min_strip_util"]:
                for cell in strip["cells"]:
                    un = dict(cell["unit"])
                    un["qty"] = 1
                    panel_units.append(un)
                notes.append("A %s strip fell below %d%% utilisation; its "
                             "pieces move to the open yardage layout."
                             % (fmt_in(hgt),
                                int(opt["min_strip_util"] * 100)))
                continue
            ops.append(_strip_op(hgt, strip, util))

    # ---- panel (NFP nesting) ----------------------------------------
    panel = _plan_panel(panel_units, opt, warnings)
    if panel:
        ops.append(panel)

    total = sum(op["height"] * op.get("count", 1) for op in ops
                if op["op"] == "strip")
    total += sum(op["width"] * op["strips"] for op in ops
                 if op["op"] == "pieced_strip")
    total += sum(op["height"] for op in ops if op["op"] == "panel")
    return {"ops": ops, "total_length_in": total,
            "warnings": warnings, "notes": notes}


def _odd_footprint(u, strip_h):
    """Smallest-width bbox of an odd/tri unit that fits a strip of height
    strip_h under the unit's rotation policy, or (None, None)."""
    if u["grain"] == GRAIN_FUSSY:
        rots = [0]
    elif u["type"] == "odd" and u["grain"] == GRAIN_FREE:
        rots = range(0, 180, 15)
    else:
        rots = (0, 90)
    best = None
    for r in rots:
        w, h = _bbox_wh(_rot(u["poly"], r))
        if h <= strip_h + EPS and (best is None or w < best[0]):
            best = (w, h, r)
    if best is None:
        return None, None
    return best[0], best[1]


def _strip_op(hgt, strip, util):
    # Aggregate identical subcuts for readable instructions; keep the raw
    # cell positions so renderers can draw the subcut lines.
    agg = {}
    order = []
    cells_draw = []
    for cell in strip["cells"]:
        un = cell["unit"]
        cells_draw.append({"x": cell["x"], "w": cell["w"],
                           "kind": un["type"], "poly": un.get("poly"),
                           "contains": un.get("contains", 1),
                           "labels": un["labels"]})
        key = (round(cell["w"], 3), un["type"], un.get("secondary"))
        if key not in agg:
            agg[key] = {"w": cell["w"], "qty": 0, "kind": un["type"],
                        "labels": [],
                        "secondary": un.get("secondary"),
                        "contains": un.get("contains", 1),
                        "poly": un.get("poly"), "source": un["source"]}
            order.append(key)
        agg[key]["qty"] += 1
        agg[key]["labels"] = sorted(set(agg[key]["labels"])
                                    | set(un["labels"]))
    return {"op": "strip", "height": hgt, "consumed": strip["consumed"],
            "count": 1, "util": util, "subcuts": [agg[k] for k in order],
            "cells": cells_draw}


def _plan_panel(panel_units, opt, warnings):
    items, meta = [], []
    for u in panel_units:
        poly = u.get("poly")
        if poly is None:
            poly = [(0, 0), (u["w"], 0), (u["w"], u["h"]), (0, u["h"])]
        if u["grain"] == GRAIN_FUSSY:
            rots = [0.0]
        elif u["type"] == "odd" and u["grain"] == GRAIN_FREE:
            rots = [float(a) for a in range(0, 360, 15)]
        elif u["grain"] == GRAIN_FREE:
            rots = [0.0, 90.0, 180.0, 270.0]
        else:
            rots = [0.0]
        for _ in range(u["qty"]):
            items.append({"hull": poly, "rotations": rots})
            meta.append(u)
    if not items:
        return None
    bin_h = sum(max(_bbox_wh(it["hull"])) for it in items) + 20.0
    placed = nesting.nest_pack(items, opt["wof_in"], bin_h,
                               opt["spacing_in"])
    height = 0.0
    placements = []
    for it, u, res in zip(items, meta, placed):
        if res["page"] != 0:
            warnings.append("Panel nesting overflowed; estimate is "
                            "approximate.")
        height = max(height, res["y"] + res["h"])
        hull = nesting.convex_hull(it["hull"])
        norm = _norm_origin(_rot(hull, res["rot"]))
        placements.append({
            "poly": [(p[0] + res["x"], p[1] + res["y"]) for p in norm],
            "labels": u["labels"], "rot": res["rot"], "kind": u["type"],
            "source": u["source"],
        })
    return {"op": "panel", "height": height, "placements": placements}


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def plan_cutting(pieces, options=None):
    """pieces -> {"fabrics": {fabric: plan}, "warnings": [...],
    "notes": [...]}. See module docstring for the piece schema."""
    opt = _opt(options)
    units, warnings, notes = expand_units(pieces, opt)
    fabrics = {}
    for u in units:
        fabrics.setdefault(u["fabric"], []).append(u)
    out = {}
    for fab, us in sorted(fabrics.items(), key=lambda kv: str(kv[0])):
        out[fab] = _plan_fabric(us, opt)
    return {"fabrics": out, "warnings": warnings, "notes": notes}


def binding_plan(quilt_w_in, quilt_h_in, strip_width_in=2.5,
                 slack_in=10.0, wof_in=40.0):
    """Quilt-level binding: run = 2W + 2L + slack, ALWAYS diagonal joins
    (each join consumes ~strip width of length)."""
    run = 2.0 * (quilt_w_in + quilt_h_in) + slack_in
    strips = max(1, int(math.ceil(run / wof_in)))
    while True:
        joins = max(0, strips - 1)
        need = int(math.ceil((run + joins * strip_width_in) / wof_in))
        if need == strips:
            break
        strips = need
    return {"op": "binding", "width": strip_width_in, "strips": strips,
            "run": run, "join": "diagonal",
            "total_length_in": strips * strip_width_in,
            "text": "Binding: cut %d strips %s x WOF; join with diagonal "
                    "seams; makes ~%d\" of binding."
                    % (strips, fmt_in(strip_width_in), int(run))}


def format_ops_text(plan):
    """Human-readable instruction lines for one fabric's plan."""
    lines = []
    for op in plan["ops"]:
        if op["op"] == "strip":
            subs = []
            for sc in op["subcuts"]:
                shape = {"rect": "rectangle", "square": "square"}.get(
                    sc["kind"], sc["kind"])
                if sc["kind"] == "rect":
                    shape = ("%s square" % fmt_in(sc["w"])
                             if abs(sc["w"] - op["height"]) < 1e-3
                             else "%s x %s rectangle"
                             % (fmt_in(sc["w"]), fmt_in(op["height"])))
                else:
                    shape = "%s wide %s" % (fmt_in(sc["w"]), sc["kind"])
                qty = sc["qty"]
                txt = "%d x %s" % (qty, shape) if qty > 1 else shape
                if sc.get("secondary"):
                    txt += " (%s)" % sc["secondary"]
                txt += " [%s]" % ", ".join(sc["labels"][:6])
                subs.append(txt)
            lines.append("Cut 1 strip %s x WOF (uses %s); subcut %s."
                         % (fmt_in(op["height"]), fmt_in(op["consumed"]),
                            "; ".join(subs)))
        elif op["op"] == "pieced_strip":
            cuts = "; ".join(
                "%d x %s" % (c["qty"], fmt_in(c["length"]))
                if c["qty"] > 1 else fmt_in(c["length"])
                for c in op["cuts"])
            lines.append("Cut %d strips %s x WOF; join end-to-end with %s "
                         "seams; subcut %s. [%s]"
                         % (op["strips"], fmt_in(op["width"]), op["join"],
                            cuts, ", ".join(op["labels"][:8])))
        elif op["op"] == "panel":
            lines.append("From a %s length of full-width fabric, cut the "
                         "remaining %d shape(s) as laid out in the map."
                         % (fmt_in(op["height"]), len(op["placements"])))
    return lines
