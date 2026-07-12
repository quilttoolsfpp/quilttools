"""True-shape nesting engine for Smart Pack.

Packs convex hulls of pattern pieces onto fixed-size pages using
No-Fit-Polygon (NFP) placement: for each piece we compute, per candidate
rotation, the exact set of positions where it would collide with every
already-placed piece (the NFP, via a Minkowski sum) and choose the
bottom-left-most collision-free position. Spacing between pieces is
enforced by inflating placed hulls before NFP computation.

Pure Python / stdlib only so it can be unit-tested outside Inkscape.
All coordinates are in px, y-down (SVG convention); the maths is
orientation-agnostic as long as polygons are normalised to positive
signed area, which this module does internally.
"""

import math

_EPS = 1e-9
_TOL_DIST = 1e-4  # px tolerance for on-boundary tests


def _signed_area(poly):
    a = 0.0
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        a += poly[i][0] * poly[j][1] - poly[j][0] * poly[i][1]
    return a / 2.0


def _dedup(poly, eps=1e-7):
    out = []
    for p in poly:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append((float(p[0]), float(p[1])))
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) <= eps and abs(out[0][1] - out[-1][1]) <= eps:
        out.pop()
    return out


def _positive(poly):
    poly = _dedup(poly)
    if _signed_area(poly) < 0:
        poly = poly[::-1]
    return poly


def convex_hull(points):
    pts = sorted(set((round(p[0], 6), round(p[1], 6)) for p in points))
    if len(pts) <= 2:
        return [tuple(map(float, p)) for p in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [tuple(map(float, p)) for p in lower[:-1] + upper[:-1]]


def rotate_points(pts, angle_deg):
    if angle_deg == 0:
        return [tuple(p) for p in pts]
    rad = math.radians(angle_deg)
    c, s = math.cos(rad), math.sin(rad)
    return [(p[0] * c - p[1] * s, p[0] * s + p[1] * c) for p in pts]


def _reorder_bottom(poly):
    i0 = min(range(len(poly)), key=lambda i: (poly[i][1], poly[i][0]))
    return poly[i0:] + poly[:i0]


def _edge_seq(poly):
    """Edge vectors of a positive-orientation polygon starting at its
    bottom-most vertex, tagged with monotonically increasing polar angle."""
    n = len(poly)
    seq = []
    prev = None
    for i in range(n):
        v = (poly[(i + 1) % n][0] - poly[i][0], poly[(i + 1) % n][1] - poly[i][1])
        a = math.atan2(v[1], v[0])
        if a < 0:
            a += 2 * math.pi
        if prev is not None and a < prev - 1e-9:
            a += 2 * math.pi
        if prev is not None and a < prev:
            a = prev
        seq.append((a, v))
        prev = a
    return seq


def minkowski_sum_convex(P, Q):
    """Minkowski sum of two convex polygons (any orientation on input)."""
    P = _reorder_bottom(_positive(P))
    Q = _reorder_bottom(_positive(Q))
    if len(P) < 3 or len(Q) < 3:
        # Degenerate input: fall back to hull of pairwise sums (small n).
        return convex_hull([(p[0] + q[0], p[1] + q[1]) for p in P for q in Q])
    ep, eq = _edge_seq(P), _edge_seq(Q)
    edges = []
    i = j = 0
    while i < len(ep) or j < len(eq):
        if j >= len(eq):
            edges.append(ep[i][1]); i += 1
        elif i >= len(ep):
            edges.append(eq[j][1]); j += 1
        elif abs(ep[i][0] - eq[j][0]) < 1e-9:
            edges.append((ep[i][1][0] + eq[j][1][0], ep[i][1][1] + eq[j][1][1]))
            i += 1; j += 1
        elif ep[i][0] < eq[j][0]:
            edges.append(ep[i][1]); i += 1
        else:
            edges.append(eq[j][1]); j += 1
    cur = (P[0][0] + Q[0][0], P[0][1] + Q[0][1])
    out = [cur]
    for v in edges[:-1]:
        cur = (cur[0] + v[0], cur[1] + v[1])
        out.append(cur)
    return _dedup(out)


def _octagon(r):
    # Circumscribed octagon: every edge is exactly r from the centre, so
    # inflating with it guarantees at least r of clearance.
    R = r / math.cos(math.pi / 8)
    return [
        (R * math.cos(math.pi / 8 + k * math.pi / 4), R * math.sin(math.pi / 8 + k * math.pi / 4))
        for k in range(8)
    ]


def inflate_convex(poly, r):
    if r <= _EPS:
        return _positive(poly)
    return minkowski_sum_convex(poly, _octagon(r))


def point_in_convex(pt, poly, tol=_TOL_DIST):
    """0 = outside, 1 = on boundary (within tol), 2 = strictly inside.
    poly must have positive orientation."""
    result = 2
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        L = math.hypot(ex, ey)
        if L < _EPS:
            continue
        d = (ex * (pt[1] - ay) - ey * (pt[0] - ax)) / L
        if d < -tol:
            return 0
        if d < tol:
            result = 1
    return result


def _seg_isect(p1, p2, p3, p4):
    d1 = (p2[0] - p1[0], p2[1] - p1[1])
    d2 = (p4[0] - p3[0], p4[1] - p3[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return None
    dx, dy = p3[0] - p1[0], p3[1] - p1[1]
    t = (dx * d2[1] - dy * d2[0]) / den
    u = (dx * d1[1] - dy * d1[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (p1[0] + t * d1[0], p1[1] + t * d1[1])
    return None


def _norm_rot(hull, angle_deg):
    """Rotate hull about origin, translate so bbox min is (0,0).
    Returns (normalised_poly, w, h)."""
    r = rotate_points(hull, angle_deg)
    min_x = min(p[0] for p in r)
    min_y = min(p[1] for p in r)
    norm = [(p[0] - min_x, p[1] - min_y) for p in r]
    w = max(p[0] for p in norm)
    h = max(p[1] for p in norm)
    return _positive(norm), w, h


def _candidates(nfps, ifp_w, ifp_h):
    pts = [(0.0, 0.0), (ifp_w, 0.0), (0.0, ifp_h), (ifp_w, ifp_h)]
    ifp_edges = [
        ((0.0, 0.0), (ifp_w, 0.0)),
        ((ifp_w, 0.0), (ifp_w, ifp_h)),
        ((ifp_w, ifp_h), (0.0, ifp_h)),
        ((0.0, ifp_h), (0.0, 0.0)),
    ]
    edge_lists = []
    for nf in nfps:
        n = len(nf)
        edges = [(nf[i], nf[(i + 1) % n]) for i in range(n)]
        edge_lists.append(edges)
        pts.extend(nf)
        for e in edges:
            for fe in ifp_edges:
                p = _seg_isect(e[0], e[1], fe[0], fe[1])
                if p:
                    pts.append(p)
    # Cross-NFP edge intersections give the tightest wedged placements but
    # cost O(k^2 * v^2); on very crowded pages fall back to vertex and
    # page-boundary candidates only.
    if len(edge_lists) <= 20:
        for a in range(len(edge_lists)):
            for b in range(a + 1, len(edge_lists)):
                for e1 in edge_lists[a]:
                    for e2 in edge_lists[b]:
                        p = _seg_isect(e1[0], e1[1], e2[0], e2[1])
                        if p:
                            pts.append(p)
    seen = set()
    out = []
    for p in pts:
        key = (round(p[0], 3), round(p[1], 3))
        if key not in seen:
            seen.add(key)
            out.append(p)
    out.sort(key=lambda p: (p[1], p[0]))
    return out


def _best_position(obstacles, hull, rotations, bin_w, bin_h):
    """Best (bottom-left) placement of hull on a page with the given
    inflated obstacles. Returns (rot, x, y, norm_poly, w, h) or None."""
    best = None
    for rot in rotations:
        norm, w, h = _norm_rot(hull, rot)
        if w > bin_w + 1e-6 or h > bin_h + 1e-6:
            continue
        ifp_w, ifp_h = bin_w - w, bin_h - h
        if not obstacles:
            cand = [(0.0, 0.0)]
            nfps = []
        else:
            neg = [(-p[0], -p[1]) for p in norm]
            nfps = [minkowski_sum_convex(obs, neg) for obs in obstacles]
            cand = _candidates(nfps, ifp_w, ifp_h)
        for cx, cy in cand:
            if cx < -1e-6 or cy < -1e-6 or cx > ifp_w + 1e-6 or cy > ifp_h + 1e-6:
                continue
            x = min(max(cx, 0.0), ifp_w)
            y = min(max(cy, 0.0), ifp_h)
            feasible = True
            for nf in nfps:
                if point_in_convex((x, y), nf) == 2:
                    feasible = False
                    break
            if feasible:
                key = (y, x)
                if best is None or key < best[0]:
                    best = (key, rot, x, y, norm, w, h)
                break  # candidates are sorted bottom-left first
    if best is None:
        return None
    return best[1:]


def nest_pack(items, bin_w, bin_h, spacing):
    """Pack items onto pages of bin_w x bin_h.

    items: list of {"hull": [(x, y), ...], "rotations": [deg, ...]}
           placed in the given order (sort large-first for best results).
    spacing: minimum gap between placed pieces (page edges may be touched).

    Returns a list (aligned with items) of
    {"page": int, "x": float, "y": float, "rot": float, "w": float, "h": float}
    where (x, y) is the target position of the rotated piece's bbox min and
    (w, h) its rotated bbox size.
    """
    pages = []  # per page: {"obs": [inflated placed hulls], "used": hull area}
    bin_area = bin_w * bin_h
    results = []
    for it in items:
        hull = convex_hull(it["hull"])
        hull_area = abs(_signed_area(hull))
        rotations = it.get("rotations") or [0.0]
        placement = None
        page_idx = None
        for pi in range(len(pages)):
            # Cheap necessary condition before the expensive NFP search.
            if hull_area > bin_area - pages[pi]["used"] + 1e-6:
                continue
            placement = _best_position(pages[pi]["obs"], hull, rotations, bin_w, bin_h)
            if placement:
                page_idx = pi
                break
        if placement is None:
            pages.append({"obs": [], "used": 0.0})
            page_idx = len(pages) - 1
            placement = _best_position(pages[page_idx]["obs"], hull, rotations, bin_w, bin_h)
            if placement is None:
                # Oversize even for an empty page: pin at origin unrotated.
                norm, w, h = _norm_rot(hull, 0.0)
                placement = (0.0, 0.0, 0.0, norm, w, h)
        rot, x, y, norm, w, h = placement
        placed = [(p[0] + x, p[1] + y) for p in norm]
        pages[page_idx]["obs"].append(inflate_convex(placed, spacing))
        pages[page_idx]["used"] += hull_area
        results.append({"page": page_idx, "x": x, "y": y, "rot": rot, "w": w, "h": h})
    return results
