import math

EPSILON = 1e-9
PX_PER_INCH = 96.0

def pt(x, y):
    return (float(x), float(y))

def vec_sub(a, b):
    return (a[0] - b[0], a[1] - b[1])

def vec_len(v):
    return math.hypot(v[0], v[1])

def vec_cross(a, b):
    return a[0] * b[1] - a[1] * b[0]

def pt_dist(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def snap_angle(angle_deg, increment_deg=15.0):
    if increment_deg <= 0:
        return angle_deg
    return round(angle_deg / increment_deg) * increment_deg

def angle_of_line(p1, p2):
    return math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))

def line_from_point_angle(p, angle_deg):
    rad = math.radians(angle_deg)
    BIG = 1e7
    dx, dy = math.cos(rad) * BIG, math.sin(rad) * BIG
    return (pt(p[0] - dx, p[1] - dy), pt(p[0] + dx, p[1] + dy))

def are_collinear(p1, p2, p3, tol=0.5):
    line_len = pt_dist(p1, p3)
    if line_len < EPSILON:
        return True
    cross_prod = abs(
        (p3[1] - p1[1]) * p2[0]
        - (p3[0] - p1[0]) * p2[1]
        + p3[0] * p1[1]
        - p3[1] * p1[0]
    )
    distance = cross_prod / line_len
    return distance < tol

def deduplicate_polygon(polygon, eps=1e-4):
    result = []
    for p in polygon:
        if not result or pt_dist(p, result[-1]) > eps:
            result.append(p)
    if result and len(result) > 1 and pt_dist(result[0], result[-1]) < eps:
        result.pop()
    return result

def simplify_polygon(poly):
    poly = deduplicate_polygon(poly, eps=1e-4)
    if len(poly) <= 3:
        return poly
    changed = True
    while changed and len(poly) > 3:
        changed = False
        n = len(poly)
        for i in range(n):
            p_prev = poly[(i - 1) % n]
            p_curr = poly[i]
            p_next = poly[(i + 1) % n]
            if are_collinear(p_prev, p_curr, p_next, tol=1e-4):
                poly.pop(i)
                changed = True
                break
    return poly

def exact_edge_match(poly1, poly2, tol=1.5):
    for i in range(len(poly1)):
        e1 = (poly1[i], poly1[(i + 1) % len(poly1)])
        for j in range(len(poly2)):
            e2 = (poly2[j], poly2[(j + 1) % len(poly2)])
            if pt_dist(e1[0], e2[1]) < tol and pt_dist(e1[1], e2[0]) < tol:
                return i, j, True
            if pt_dist(e1[0], e2[0]) < tol and pt_dist(e1[1], e2[1]) < tol:
                return i, j, False
    return None

def merge_polygons(poly1, poly2, e1_idx, e2_idx, is_anti):
    n1, n2 = len(poly1), len(poly2)
    res = []
    for k in range(1, n1 + 1):
        res.append(poly1[(e1_idx + k) % n1])
    if is_anti:
        for k in range(1, n2):
            res.append(poly2[(e2_idx + 1 + k) % n2])
    else:
        for k in range(1, n2):
            res.append(poly2[(e2_idx - k) % n2])
    return simplify_polygon(res)

def get_polygon_union(polygons):
    if not polygons:
        return []
    if len(polygons) == 1:
        return simplify_polygon(polygons[0])
    poly_list = [simplify_polygon(p) for p in polygons]
    changed = True
    while changed and len(poly_list) > 1:
        changed = False
        for i in range(len(poly_list)):
            for j in range(i + 1, len(poly_list)):
                match = exact_edge_match(poly_list[i], poly_list[j], tol=1.5)
                if match:
                    merged = merge_polygons(
                        poly_list[i], poly_list[j], match[0], match[1], match[2]
                    )
                    poly_list.pop(j)
                    poly_list.pop(i)
                    poly_list.append(merged)
                    changed = True
                    break
            if changed:
                break
    return poly_list[0] if poly_list else []

def segment_intersect(p1, p2, p3, p4):
    d1, d2 = vec_sub(p2, p1), vec_sub(p4, p3)
    cross = vec_cross(d1, d2)
    if abs(cross) < EPSILON:
        return None
    d3 = vec_sub(p3, p1)
    t = vec_cross(d3, d2) / cross
    u = vec_cross(d3, d1) / cross
    if -EPSILON <= t <= 1 + EPSILON and -EPSILON <= u <= 1 + EPSILON:
        return (t, pt(p1[0] + t * d1[0], p1[1] + t * d1[1]))
    return None

def clip_line_to_polygon(ray_p1, ray_p2, polygon):
    hits = []
    n = len(polygon)
    for i in range(n):
        r = segment_intersect(ray_p1, ray_p2, polygon[i], polygon[(i + 1) % n])
        if r:
            hits.append(r)
    if len(hits) < 2:
        return None
    hits.sort(key=lambda x: x[0])
    return (hits[0][1], hits[-1][1])

def polygon_area_signed(polygon):
    area = 0.0
    n = len(polygon)
    for i in range(n):
        j = (i + 1) % n
        area += polygon[i][0] * polygon[j][1] - polygon[j][0] * polygon[i][1]
    return area / 2.0

def polygon_area(polygon):
    return abs(polygon_area_signed(polygon))

def polygon_centroid(polygon):
    if not polygon or len(polygon) < 3:
        if not polygon:
            return (0, 0)
        return (
            sum(p[0] for p in polygon) / len(polygon),
            sum(p[1] for p in polygon) / len(polygon),
        )
    ans_twice = 0.0
    for i in range(len(polygon)):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % len(polygon)]
        ans_twice += p1[0] * p2[1] - p2[0] * p1[1]
    
    A = ans_twice / 2.0
    if abs(A) < 1e-7:
        return (
            sum(p[0] for p in polygon) / len(polygon),
            sum(p[1] for p in polygon) / len(polygon),
        )
    
    cx = 0.0
    cy = 0.0
    n = len(polygon)
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        factor = p1[0] * p2[1] - p2[0] * p1[1]
        cx += (p1[0] + p2[0]) * factor
        cy += (p1[1] + p2[1]) * factor
    cx /= (6.0 * A)
    cy /= (6.0 * A)
    return (cx, cy)

def find_circle_intersections(polygon, center, radius):
    intersections = []
    n = len(polygon)
    xc, yc = center
    R = radius
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        vx, vy = p2[0] - p1[0], p2[1] - p1[1]
        ux, uy = p1[0] - xc, p1[1] - yc
        a = vx*vx + vy*vy
        if a < 1e-9:
            continue
        b = 2 * (ux*vx + uy*vy)
        c = ux*ux + uy*uy - R*R
        D = b*b - 4*a*c
        if D >= 0:
            roots = []
            if D < 1e-9:
                roots.append(-b / (2*a))
            else:
                sqrt_D = math.sqrt(D)
                roots.append((-b - sqrt_D) / (2*a))
                roots.append((-b + sqrt_D) / (2*a))
            for t in roots:
                if -1e-6 <= t <= 1 + 1e-6:
                    t = max(0.0, min(1.0, t))
                    ix = p1[0] + t * vx
                    iy = p1[1] + t * vy
                    intersections.append((i, t, (ix, iy)))
    return intersections

def deduplicate_intersections(intersections):
    deduped = []
    for item in intersections:
        duplicate = False
        for existing in deduped:
            if pt_dist(item[2], existing[2]) < 1e-4:
                duplicate = True
                break
        if not duplicate:
            deduped.append(item)
    return deduped

def generate_circle_arc(center, radius, theta1, theta2, ccw, subdivisions=32):
    xc, yc = center
    if ccw:
        t2 = theta2
        if t2 < theta1:
            t2 += 2 * math.pi
        diff = t2 - theta1
    else:
        t2 = theta2
        if t2 > theta1:
            t2 -= 2 * math.pi
        diff = t2 - theta1
        
    pts = []
    for i in range(subdivisions + 1):
        f = i / float(subdivisions)
        theta = theta1 + f * diff
        x = xc + radius * math.cos(theta)
        y = yc + radius * math.sin(theta)
        pts.append((round(x, 4), round(y, 4)))
    return pts

def split_polygon_by_line(polygon, p1, p2, snap_tol=1.5):
    d = vec_sub(p2, p1)
    len_d = math.hypot(d[0], d[1])
    if len_d < 1e-7:
        return simplify_polygon(polygon), []
    
    nd = (d[0] / len_d, d[1] / len_d)
    
    snapped_poly = []
    for v in polygon:
        dist = nd[0] * (v[1] - p1[1]) - nd[1] * (v[0] - p1[0])
        if abs(dist) < snap_tol:
            v_snapped = (v[0] + dist * nd[1], v[1] - dist * nd[0])
            snapped_poly.append(v_snapped)
        else:
            snapped_poly.append(v)
            
    BIG = 1e7
    inf_p1 = (p1[0] - nd[0] * BIG, p1[1] - nd[1] * BIG)
    inf_p2 = (p1[0] + nd[0] * BIG, p1[1] + nd[1] * BIG)
    
    left_verts, right_verts = [], []
    n = len(snapped_poly)
    for i in range(n):
        a, b = snapped_poly[i], snapped_poly[(i + 1) % n]
        
        dist_a = nd[0] * (a[1] - p1[1]) - nd[1] * (a[0] - p1[0])
        side_a = 0 if abs(dist_a) < 1e-7 else (1 if dist_a > 0 else -1)
        
        dist_b = nd[0] * (b[1] - p1[1]) - nd[1] * (b[0] - p1[0])
        side_b = 0 if abs(dist_b) < 1e-7 else (1 if dist_b > 0 else -1)
        
        if side_a >= 0:
            left_verts.append(a)
        if side_a <= 0:
            right_verts.append(a)
            
        if (side_a > 0 and side_b < 0) or (side_a < 0 and side_b > 0):
            r = segment_intersect(a, b, inf_p1, inf_p2)
            if r:
                _, cp = r
                left_verts.append(cp)
                right_verts.append(cp)
 
    return simplify_polygon(left_verts), simplify_polygon(right_verts)

def offset_polygon(polygon, amount, miter_limit=2.0):
    n = len(polygon)
    if n < 3:
        return polygon
    area_signed = polygon_area_signed(polygon)
    sign = 1 if area_signed >= 0 else -1
    normals = []

    for i in range(n):
        p1, p2 = polygon[i], polygon[(i + 1) % n]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.hypot(dx, dy)
        normals.append(
            (0, 0) if length < EPSILON else (dy / length * sign, -dx / length * sign)
        )

    new_poly = []
    for i in range(n):
        n1, n2 = normals[(i - 1) % n], normals[i]
        p_prev, p_curr, p_next = polygon[(i - 1) % n], polygon[i], polygon[(i + 1) % n]

        bx, by = n1[0] + n2[0], n1[1] + n2[1]
        blen2 = bx*bx + by*by

        if blen2 < 1e-4:
            pA = (p_curr[0] + n1[0] * amount, p_curr[1] + n1[1] * amount)
            pB = (p_curr[0] + n2[0] * amount, p_curr[1] + n2[1] * amount)
            new_poly.append(pA)
            new_poly.append(pB)
            continue

        factor = 2.0 / blen2
        mx, my = bx * factor * amount, by * factor * amount
        miter_len = math.hypot(mx, my)

        if miter_len > abs(amount) * miter_limit:
            new_px = p_curr[0] + mx
            new_py = p_curr[1] + my
            
            d1x, d1y = p_curr[0] - p_prev[0], p_curr[1] - p_prev[1]
            d2x, d2y = p_next[0] - p_curr[0], p_next[1] - p_curr[1]
            
            trunc_dist = abs(amount)
            h1 = math.hypot(d1x, d1y)
            h2 = math.hypot(d2x, d2y)
            
            if h1 > 1e-9 and h2 > 1e-9:
                pA_x = new_px - d1x * (miter_len - trunc_dist) / h1
                pA_y = new_py - d1y * (miter_len - trunc_dist) / h1
                pB_x = new_px + d2x * (miter_len - trunc_dist) / h2
                pB_y = new_py + d2y * (miter_len - trunc_dist) / h2
                new_poly.append((pA_x, pA_y))
                new_poly.append((pB_x, pB_y))
            else:
                pA = (p_curr[0] + n1[0] * amount, p_curr[1] + n1[1] * amount)
                pB = (p_curr[0] + n2[0] * amount, p_curr[1] + n2[1] * amount)
                new_poly.append(pA)
                new_poly.append(pB)
        else:
            new_poly.append((p_curr[0] + mx, p_curr[1] + my))

    return simplify_polygon(new_poly)

def clip_polygon_to_rect(polygon, x0, y0, x1, y1):
    x0, x1 = (x0, x1) if x0 <= x1 else (x1, x0)
    y0, y1 = (y0, y1) if y0 <= y1 else (y1, y0)

    def clip_edge(poly, inside_fn, intersect_fn):
        if not poly:
            return []
        out = []
        n = len(poly)
        for i in range(n):
            cur = poly[i]
            nxt = poly[(i + 1) % n]
            cur_in = inside_fn(cur)
            nxt_in = inside_fn(nxt)
            if cur_in:
                out.append(cur)
                if not nxt_in:
                    out.append(intersect_fn(cur, nxt))
            else:
                if nxt_in:
                    out.append(intersect_fn(cur, nxt))
        return out

    def lerp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    poly = clip_edge(
        list(polygon),
        lambda p: p[0] >= x0,
        lambda a, b: lerp(a, b, (x0 - a[0]) / (b[0] - a[0])) if b[0] != a[0] else a,
    )
    poly = clip_edge(
        poly,
        lambda p: p[0] <= x1,
        lambda a, b: lerp(a, b, (x1 - a[0]) / (b[0] - a[0])) if b[0] != a[0] else a,
    )
    poly = clip_edge(
        poly,
        lambda p: p[1] >= y0,
        lambda a, b: lerp(a, b, (y0 - a[1]) / (b[1] - a[1])) if b[1] != a[1] else a,
    )
    poly = clip_edge(
        poly,
        lambda p: p[1] <= y1,
        lambda a, b: lerp(a, b, (y1 - a[1]) / (b[1] - a[1])) if b[1] != a[1] else a,
    )

    return simplify_polygon(poly) if len(poly) >= 3 else []

def rect_frame_strips(box, covered, min_dim=0.5):
    X0, Y0, X1, Y1 = box
    cX0, cY0, cX1, cY1 = covered
    cX0 = max(min(cX0, X1), X0)
    cX1 = max(min(cX1, X1), X0)
    cY0 = max(min(cY0, Y1), Y0)
    cY1 = max(min(cY1, Y1), Y0)

    strips = []
    if cX0 - X0 > min_dim:  # left
        strips.append([(X0, Y0), (cX0, Y0), (cX0, Y1), (X0, Y1)])
    if X1 - cX1 > min_dim:  # right
        strips.append([(cX1, Y0), (X1, Y0), (X1, Y1), (cX1, Y1)])
    if cY0 - Y0 > min_dim:  # top
        strips.append([(cX0, Y0), (cX1, Y0), (cX1, cY0), (cX0, cY0)])
    if Y1 - cY1 > min_dim:  # bottom
        strips.append([(cX0, cY1), (cX1, cY1), (cX1, Y1), (cX0, Y1)])
    return strips

def _polys_equivalent(a, b, tol=1.0):
    if len(a) != len(b):
        return False
    axs = [p[0] for p in a]
    ays = [p[1] for p in a]
    bxs = [p[0] for p in b]
    bys = [p[1] for p in b]
    return (
        abs(min(axs) - min(bxs)) < tol
        and abs(max(axs) - max(bxs)) < tol
        and abs(min(ays) - min(bys)) < tol
        and abs(max(ays) - max(bys)) < tol
    )

def polygons_share_edge(poly_a, poly_b, tol=1.5):
    """True if the polygons share a collinear boundary overlap of at least
    tol px — i.e. they could be joined by a physical seam."""
    for i in range(len(poly_a)):
        p1 = poly_a[i]
        p2 = poly_a[(i + 1) % len(poly_a)]
        v_a = (p2[0] - p1[0], p2[1] - p1[1])
        len_a = math.hypot(*v_a)
        if len_a < tol:
            continue
        u_a = (v_a[0] / len_a, v_a[1] / len_a)
        for j in range(len(poly_b)):
            q1 = poly_b[j]
            q2 = poly_b[(j + 1) % len(poly_b)]
            d1 = u_a[0] * (q1[1] - p1[1]) - u_a[1] * (q1[0] - p1[0])
            if abs(d1) > tol:
                continue
            d2 = u_a[0] * (q2[1] - p1[1]) - u_a[1] * (q2[0] - p1[0])
            if abs(d2) > tol:
                continue
            t1 = (q1[0] - p1[0]) * u_a[0] + (q1[1] - p1[1]) * u_a[1]
            t2 = (q2[0] - p1[0]) * u_a[0] + (q2[1] - p1[1]) * u_a[1]
            lo, hi = max(0.0, min(t1, t2)), min(len_a, max(t1, t2))
            if hi - lo >= tol:
                return True
    return False


def convex_hull(points):
    """Convex hull (monotone chain) of a point cloud, positive orientation."""
    pts = sorted(set((float(p[0]), float(p[1])) for p in points))
    if len(pts) <= 2:
        return list(pts)

    def cross_oab(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross_oab(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross_oab(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        if min(p1[1], p2[1]) < y <= max(p1[1], p2[1]):
            if x <= max(p1[0], p2[0]):
                if p1[1] != p2[1]:
                    xinters = (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1]) + p1[0]
                if p1[0] == p2[0] or x <= xinters:
                    inside = not inside
    return inside

def polygons_overlap(poly1, poly2):
    min_x1, max_x1 = min(p[0] for p in poly1), max(p[0] for p in poly1)
    min_y1, max_y1 = min(p[1] for p in poly1), max(p[1] for p in poly1)
    min_x2, max_x2 = min(p[0] for p in poly2), max(p[0] for p in poly2)
    min_y2, max_y2 = min(p[1] for p in poly2), max(p[1] for p in poly2)
    if max_x1 <= min_x2 + 1.0 or min_x1 >= max_x2 - 1.0 or max_y1 <= min_y2 + 1.0 or min_y1 >= max_y2 - 1.0:
        return False

    n1, n2 = len(poly1), len(poly2)
    for i in range(n1):
        p1a, p1b = poly1[i], poly1[(i + 1) % n1]
        for j in range(n2):
            p2a, p2b = poly2[j], poly2[(j + 1) % n2]
            res = segment_intersect(p1a, p1b, p2a, p2b)
            if res:
                t, pt = res
                if 0.02 < t < 0.98:
                    return True

    c1 = polygon_centroid(poly1)
    if point_in_polygon(c1, poly2):
        return True
    c2 = polygon_centroid(poly2)
    if point_in_polygon(c2, poly1):
        return True

    return False

