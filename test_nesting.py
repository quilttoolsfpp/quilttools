"""Tests for quilttools_nesting (NFP-based Smart Pack engine).

Run with any Python 3: python test_nesting.py
Verifies placements with an independent SAT overlap / clearance check.
"""

import math
import random

import quilttools_nesting as nest

PAGE_W, PAGE_H = 720.0, 893.0  # letter minus 0.5in margins/headers, px
SPACING = 19.2  # 0.2 in


# --- Independent convex-polygon separation check (SAT distance) ---

def _project(poly, axis):
    dots = [p[0] * axis[0] + p[1] * axis[1] for p in poly]
    return min(dots), max(dots)


def sat_separation(a, b):
    """Largest separation between convex polygons along any edge normal.
    Positive = disjoint by at least that distance along some axis;
    negative = overlapping."""
    best = -float("inf")
    for poly in (a, b):
        n = len(poly)
        for i in range(n):
            ex = poly[(i + 1) % n][0] - poly[i][0]
            ey = poly[(i + 1) % n][1] - poly[i][1]
            L = math.hypot(ex, ey)
            if L < 1e-12:
                continue
            axis = (-ey / L, ex / L)
            a0, a1 = _project(a, axis)
            b0, b1 = _project(b, axis)
            gap = max(b0 - a1, a0 - b1)
            best = max(best, gap)
    return best


def _pt_seg_dist(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    if L2 < 1e-18:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.hypot(p[0] - (a[0] + t * ax), p[1] - (a[1] + t * ay))


def poly_min_dist(a, b):
    """True Euclidean clearance between convex polygons (negative = overlap).
    SAT projection gaps underestimate the distance when the closest features
    are vertices, so measure segment-to-segment once disjointness is known."""
    gap = sat_separation(a, b)
    if gap <= 0:
        return gap
    best = float("inf")
    na, nb = len(a), len(b)
    for i in range(na):
        a1, a2 = a[i], a[(i + 1) % na]
        for j in range(nb):
            b1, b2 = b[j], b[(j + 1) % nb]
            best = min(
                best,
                _pt_seg_dist(a1, b1, b2),
                _pt_seg_dist(a2, b1, b2),
                _pt_seg_dist(b1, a1, a2),
                _pt_seg_dist(b2, a1, a2),
            )
    return best


def placed_hull(item_hull, pl):
    norm, w, h = nest._norm_rot(nest.convex_hull(item_hull), pl["rot"])
    return [(p[0] + pl["x"], p[1] + pl["y"]) for p in norm]


def check_pack(items, placements, page_w=PAGE_W, page_h=PAGE_H, spacing=SPACING):
    by_page = {}
    for it, pl in zip(items, placements):
        poly = placed_hull(it["hull"], pl)
        for x, y in poly:
            assert -0.01 <= x <= page_w + 0.01, f"x={x} outside page 0..{page_w}"
            assert -0.01 <= y <= page_h + 0.01, f"y={y} outside page 0..{page_h}"
        by_page.setdefault(pl["page"], []).append(poly)
    for page, polys in by_page.items():
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                sep = poly_min_dist(polys[i], polys[j])
                assert sep >= spacing - 0.5, (
                    f"page {page}: pieces {i},{j} separated by {sep:.2f}px "
                    f"(< spacing {spacing}px)"
                )
    return by_page


def test_minkowski_squares():
    a = [(0, 0), (10, 0), (10, 10), (0, 10)]
    b = [(0, 0), (5, 0), (5, 5), (0, 5)]
    s = nest.minkowski_sum_convex(a, b)
    xs = [p[0] for p in s]
    ys = [p[1] for p in s]
    assert abs(min(xs) - 0) < 1e-6 and abs(max(xs) - 15) < 1e-6
    assert abs(min(ys) - 0) < 1e-6 and abs(max(ys) - 15) < 1e-6
    print("ok minkowski_squares")


def test_inflate_clearance():
    tri = [(0, 0), (100, 0), (0, 100)]
    inf = nest.inflate_convex(tri, 10)
    # Every original edge must be pushed out by >= 10
    sep = sat_separation(tri, [(p[0] + 200, p[1]) for p in tri])
    assert sep > 0  # sanity of SAT itself
    for px, py in tri:
        assert nest.point_in_convex((px, py), inf) == 2
    # A point 9.9px outside the hypotenuse must still be inside the inflated hull
    d = 9.9 / math.sqrt(2)
    assert nest.point_in_convex((50 + d, 50 + d), inf) == 2
    print("ok inflate_clearance")


def test_two_triangles_nest_together():
    """Two complementary right triangles must share a page and pack into
    roughly one rectangle - the case bbox packing can never do."""
    t = [(0, 0), (500, 0), (0, 500)]
    items = [
        {"hull": t, "rotations": [0.0, 90.0, 180.0, 270.0]},
        {"hull": t, "rotations": [0.0, 90.0, 180.0, 270.0]},
    ]
    placements = nest.nest_pack(items, PAGE_W, PAGE_H, SPACING)
    check_pack(items, placements)
    assert placements[0]["page"] == placements[1]["page"] == 0
    polys = [placed_hull(it["hull"], pl) for it, pl in zip(items, placements)]
    all_pts = [p for poly in polys for p in poly]
    bw = max(p[0] for p in all_pts) - min(p[0] for p in all_pts)
    bh = max(p[1] for p in all_pts) - min(p[1] for p in all_pts)
    # bbox packing needs 1000px+ in one dimension; nesting should be ~500+spacing
    assert bw <= 560 and bh <= 560, f"triangles did not nest: {bw:.0f}x{bh:.0f}"
    print(f"ok two_triangles_nest_together ({bw:.0f}x{bh:.0f})")


def test_four_triangles_one_page():
    t = [(0, 0), (400, 0), (0, 400)]
    items = [{"hull": t, "rotations": [0.0, 90.0, 180.0, 270.0]} for _ in range(4)]
    placements = nest.nest_pack(items, PAGE_W, PAGE_H, SPACING)
    check_pack(items, placements)
    pages = {pl["page"] for pl in placements}
    assert pages == {0}, f"expected 1 page, got {sorted(pages)}"
    print("ok four_triangles_one_page")


def test_random_convex_shapes():
    rng = random.Random(42)
    items = []
    for _ in range(14):
        cx, cy = rng.uniform(100, 300), rng.uniform(100, 300)
        pts = []
        for _ in range(rng.randint(3, 8)):
            ang = rng.uniform(0, 2 * math.pi)
            rad = rng.uniform(40, 220)
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        hull = nest.convex_hull(pts)
        if len(hull) >= 3:
            items.append({"hull": hull, "rotations": [0.0, 90.0, 180.0, 270.0]})
    items.sort(key=lambda it: -abs(nest._signed_area(nest.convex_hull(it["hull"]))))
    placements = nest.nest_pack(items, PAGE_W, PAGE_H, SPACING)
    by_page = check_pack(items, placements)
    print(f"ok random_convex_shapes ({len(items)} pieces on {len(by_page)} pages)")


def test_beats_shelf_packing():
    """Mixed thin slivers + triangles: nesting must not use more pages than
    a naive bbox shelf pack."""
    shapes = []
    for i in range(6):
        shapes.append([(0, 0), (600, 0), (0, 140 + 10 * i)])  # wide slivers
    for i in range(4):
        shapes.append([(0, 0), (300, 0), (300, 300), (0, 300)])  # squares
    items = [{"hull": s, "rotations": [0.0, 90.0, 180.0, 270.0]} for s in shapes]
    items.sort(key=lambda it: -abs(nest._signed_area(nest.convex_hull(it["hull"]))))
    placements = nest.nest_pack(items, PAGE_W, PAGE_H, SPACING)
    check_pack(items, placements)

    # Naive shelf pack on bboxes for comparison
    shelf_pages, x, y, row_h = 1, 0.0, 0.0, 0.0
    for it in items:
        h = nest.convex_hull(it["hull"])
        w = max(p[0] for p in h) - min(p[0] for p in h)
        hh = max(p[1] for p in h) - min(p[1] for p in h)
        if x + w > PAGE_W:
            x, y, row_h = 0.0, y + row_h + SPACING, 0.0
        if y + hh > PAGE_H:
            shelf_pages += 1
            x, y, row_h = 0.0, 0.0, 0.0
        row_h = max(row_h, hh)
        x += w + SPACING
    nest_pages = max(pl["page"] for pl in placements) + 1
    assert nest_pages <= shelf_pages, f"nesting used {nest_pages} > shelf {shelf_pages}"
    print(f"ok beats_shelf_packing (nest {nest_pages} vs shelf {shelf_pages} pages)")


def test_oversize_fallback():
    big = [(0, 0), (2000, 0), (2000, 2000), (0, 2000)]
    items = [{"hull": big, "rotations": [0.0]}]
    placements = nest.nest_pack(items, PAGE_W, PAGE_H, SPACING)
    assert placements[0]["x"] == 0.0 and placements[0]["y"] == 0.0
    print("ok oversize_fallback")


if __name__ == "__main__":
    test_minkowski_squares()
    test_inflate_clearance()
    test_two_triangles_nest_together()
    test_four_triangles_one_page()
    test_random_convex_shapes()
    test_beats_shelf_packing()
    test_oversize_fallback()
    print("ALL NESTING TESTS PASSED")
