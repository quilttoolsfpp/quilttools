#!/usr/bin/env python3
import json
import math
import re

import inkex
from lxml import etree

EPSILON = 1e-9
PX_PER_INCH = 96.0
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SVG_NS = "http://www.w3.org/2000/svg"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"

FPP_REGION_ATTR = "data-fpp-region-id"
FPP_DATA_TAG_ID = "fpp-tree-data-quilttools"

PIECE_COLORS = [
    "#d6eaf8",
    "#d5f5e3",
    "#fef9e7",
    "#f9ebea",
    "#f4ecf7",
    "#eaf4fb",
    "#fdfefe",
    "#e8f8f5",
    "#fdf2f8",
    "#e9f7ef",
    "#fef5e4",
    "#eaecee",
    "#d7bde2",
    "#a9cce3",
    "#a9dfbf",
]

SECTION_PALETTE = {
    "A": "#ffadad",
    "B": "#a0c4ff",
    "C": "#caffbf",
    "D": "#fdffb6",
    "E": "#bdb2ff",
    "F": "#ffd6a5",
    "G": "#ffc6ff",
    "H": "#9bf6ff",
    "I": "#e5e5e5",
    "J": "#ffb5a7",
    "K": "#a8dadc",
    "L": "#f1faee",
}
SECTION_PALETTE_LIST = list(SECTION_PALETTE.values())


# --- Geometry Math ---
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


def deduplicate_polygon(polygon, eps=0.5):
    result = []
    for p in polygon:
        if not result or pt_dist(p, result[-1]) > eps:
            result.append(p)
    if result and len(result) > 1 and pt_dist(result[0], result[-1]) < eps:
        result.pop()
    return result


def simplify_polygon(poly):
    poly = deduplicate_polygon(poly)
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
            if are_collinear(p_prev, p_curr, p_next, tol=1.5):
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
    if not polygon:
        return (0, 0)
    return (
        sum(p[0] for p in polygon) / len(polygon),
        sum(p[1] for p in polygon) / len(polygon),
    )


def split_polygon_by_line(polygon, p1, p2):
    d = vec_sub(p2, p1)
    left_verts, right_verts = [], []
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        side_a = vec_cross(d, vec_sub(a, p1))
        r = segment_intersect(a, b, p1, p2)
        if r:
            _, cp = r
            if side_a >= 0:
                left_verts.extend([a, cp])
                right_verts.append(cp)
            else:
                right_verts.extend([a, cp])
                left_verts.append(cp)
        else:
            if side_a >= 0:
                left_verts.append(a)
            else:
                right_verts.append(a)

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

        L1_p1 = (p_prev[0] + n1[0] * amount, p_prev[1] + n1[1] * amount)
        L1_p2 = (p_curr[0] + n1[0] * amount, p_curr[1] + n1[1] * amount)
        L2_p1 = (p_curr[0] + n2[0] * amount, p_curr[1] + n2[1] * amount)
        L2_p2 = (p_next[0] + n2[0] * amount, p_next[1] + n2[1] * amount)

        d1x, d1y = L1_p2[0] - L1_p1[0], L1_p2[1] - L1_p1[1]
        d2x, d2y = L2_p2[0] - L2_p1[0], L2_p2[1] - L2_p1[1]

        cross = d1x * d2y - d1y * d2x

        if abs(cross) < EPSILON:
            new_poly.append(L1_p2)
        else:
            t = ((L2_p1[0] - L1_p1[0]) * d2y - (L2_p1[1] - L1_p1[1]) * d2x) / cross
            new_px, new_py = L1_p1[0] + t * d1x, L1_p1[1] + t * d1y

            miter_length = math.hypot(new_px - p_curr[0], new_py - p_curr[1])

            if miter_length > abs(amount) * miter_limit:
                bx, by = n1[0] + n2[0], n1[1] + n2[1]
                blen = math.hypot(bx, by)
                if blen > EPSILON:
                    bx, by = bx / blen, by / blen
                trunc_dist = abs(amount)
                pA_x = new_px - d1x * (miter_length - trunc_dist) / math.hypot(d1x, d1y)
                pA_y = new_py - d1y * (miter_length - trunc_dist) / math.hypot(d1x, d1y)
                pB_x = new_px + d2x * (miter_length - trunc_dist) / math.hypot(d2x, d2y)
                pB_y = new_py + d2y * (miter_length - trunc_dist) / math.hypot(d2x, d2y)
                new_poly.append((pA_x, pA_y))
                new_poly.append((pB_x, pB_y))
            else:
                new_poly.append((new_px, new_py))

    return simplify_polygon(new_poly)


def clip_polygon_to_rect(polygon, x0, y0, x1, y1):
    """Clip an arbitrary simple polygon against an axis-aligned rectangle.

    Sutherland-Hodgman against the four half-planes of the rectangle.
    Returns a (possibly empty) list of points. The subject polygon may be
    concave; the clip region (a rect) is convex, so this is exact.
    """
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

    # Left (x >= x0)
    poly = clip_edge(
        list(polygon),
        lambda p: p[0] >= x0,
        lambda a, b: lerp(a, b, (x0 - a[0]) / (b[0] - a[0])) if b[0] != a[0] else a,
    )
    # Right (x <= x1)
    poly = clip_edge(
        poly,
        lambda p: p[0] <= x1,
        lambda a, b: lerp(a, b, (x1 - a[0]) / (b[0] - a[0])) if b[0] != a[0] else a,
    )
    # Top (y >= y0)
    poly = clip_edge(
        poly,
        lambda p: p[1] >= y0,
        lambda a, b: lerp(a, b, (y0 - a[1]) / (b[1] - a[1])) if b[1] != a[1] else a,
    )
    # Bottom (y <= y1)
    poly = clip_edge(
        poly,
        lambda p: p[1] <= y1,
        lambda a, b: lerp(a, b, (y1 - a[1]) / (b[1] - a[1])) if b[1] != a[1] else a,
    )

    return simplify_polygon(poly) if len(poly) >= 3 else []


def rect_frame_strips(box, covered, min_dim=0.5):
    """Decompose the margin between an outer box and an inner 'covered' rect
    into up to four non-overlapping rectangular strips (a picture frame).

    box / covered are (x0, y0, x1, y1). Left/right strips run the full box
    height; top/bottom strips only span the covered width, so the four strips
    tile the frame without overlapping. Returns a list of polygons.
    """
    X0, Y0, X1, Y1 = box
    cX0, cY0, cX1, cY1 = covered
    # Clamp covered inside the box so we never emit negative strips.
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
    """Cheap test: do two polygons describe (near) the same shape?
    Compares vertex count and bounding box. Good enough to count reshapes."""
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


class Region:
    _counter = 0

    def __init__(self, polygon, label=None, parent_id=None):
        Region._counter += 1
        self.id = Region._counter
        self.polygon = simplify_polygon(polygon)
        self.label = label or f"P{self.id}"
        self.parent_id = parent_id
        self.children = []
        self.split_boundary = False

    def is_leaf(self):
        return len(self.children) == 0

    def area_sq_in(self):
        return polygon_area(self.polygon) / (PX_PER_INCH**2)

    def path_d(self):
        if not self.polygon:
            return ""
        return (
            "M {:.4f},{:.4f} ".format(*self.polygon[0])
            + " ".join("L {:.4f},{:.4f}".format(*p) for p in self.polygon[1:])
            + " Z"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "polygon": self.polygon,
            "parent_id": self.parent_id,
            "children": self.children,
            "split_boundary": self.split_boundary,
        }

    @staticmethod
    def from_dict(d):
        r = Region.__new__(Region)
        r.__dict__.update({k: d.get(k) for k in ["id", "label", "parent_id"]})
        r.polygon = [tuple(p) for p in d["polygon"]]
        r.children = d.get("children", [])
        r.split_boundary = d.get("split_boundary", False)
        return r


class RegionTree:
    def __init__(self, root_polygon=None):
        self.regions = {}
        self.root_id = None
        if root_polygon:
            root = Region(root_polygon, label="A1")
            self.regions[root.id] = root
            self.root_id = root.id

    def leaf_regions(self):
        return [r for r in self.regions.values() if r.is_leaf()]

    def sanitize_tree(self, min_area_sq_in=0.01):
        degenerate_ids = [
            r.id for r in self.leaf_regions() if r.area_sq_in() < min_area_sq_in
        ]

        for rid in degenerate_ids:
            node = self.regions.get(rid)
            if not node:
                continue
            if node.parent_id and node.parent_id in self.regions:
                parent = self.regions[node.parent_id]
                if rid in parent.children:
                    parent.children.remove(rid)
            del self.regions[rid]

        changed = True
        while changed:
            changed = False
            for rid, node in list(self.regions.items()):
                if rid not in self.regions:
                    continue
                if not node.is_leaf() and len(node.children) == 1:
                    survivor_id = node.children[0]
                    if survivor_id in self.regions:
                        survivor = self.regions[survivor_id]
                        node.polygon = survivor.polygon
                        node.children = survivor.children
                        for grandchild_id in survivor.children:
                            if grandchild_id in self.regions:
                                self.regions[grandchild_id].parent_id = node.id
                        del self.regions[survivor_id]
                        changed = True

    def find_path(self, current_id, target_id, path=None):
        if path is None:
            path = []
        path.append(current_id)
        if current_id == target_id:
            return path
        for child_id in self.regions[current_id].children:
            res = self.find_path(child_id, target_id, path.copy())
            if res:
                return res
        return None

    def separated_by_boundary(self, id1, id2):
        path1, path2 = (
            self.find_path(self.root_id, id1),
            self.find_path(self.root_id, id2),
        )
        if not path1 or not path2:
            return False
        lca_id = self.root_id
        for p1, p2 in zip(path1, path2):
            if p1 == p2:
                lca_id = p1
            else:
                break
        return self.regions[lca_id].split_boundary

    def reset_to_boundaries(self):
        valid_nodes = set()

        def walk(n_id):
            valid_nodes.add(n_id)
            node = self.regions[n_id]
            if not node.children:
                return
            if not node.split_boundary:
                node.children = []
            else:
                walk(node.children[0])
                walk(node.children[1])

        walk(self.root_id)
        keys_to_delete = [k for k in self.regions if k not in valid_nodes]
        for k in keys_to_delete:
            del self.regions[k]
        self.sanitize_tree()
        self.auto_partition_and_label()

    def multi_guillotine_cut(
        self,
        draw_p1,
        draw_p2,
        angle_snap_deg=None,
        limit_to_region_id=None,
        is_boundary=False,
    ):
        raw_angle = angle_of_line(draw_p1, draw_p2)
        length = vec_len(vec_sub(draw_p2, draw_p1))
        if angle_snap_deg and angle_snap_deg > 0:
            raw_angle = snap_angle(raw_angle, angle_snap_deg)
        rad = math.radians(raw_angle)
        snap_p2 = pt(
            draw_p1[0] + math.cos(rad) * length, draw_p1[1] + math.sin(rad) * length
        )
        ray = line_from_point_angle(draw_p1, raw_angle)

        def dist_along_ray(p):
            return (p[0] - ray[0][0]) * math.cos(rad) + (p[1] - ray[0][1]) * math.sin(
                rad
            )

        t_draw1, t_draw2 = dist_along_ray(draw_p1), dist_along_ray(snap_p2)
        t_draw_min, t_draw_max = min(t_draw1, t_draw2), max(t_draw1, t_draw2)

        touched_ids = []
        for region in self.leaf_regions():
            if limit_to_region_id and region.id != limit_to_region_id:
                continue
            clipped = clip_line_to_polygon(ray[0], ray[1], region.polygon)
            if not clipped:
                continue
            t_cut1, t_cut2 = dist_along_ray(clipped[0]), dist_along_ray(clipped[1])
            overlap_min = max(t_draw_min, min(t_cut1, t_cut2))
            overlap_max = min(t_draw_max, max(t_cut1, t_cut2))
            if overlap_max - overlap_min > 0.5:
                touched_ids.append(region.id)

        cut_count = 0
        for rid in touched_ids:
            region = self.regions[rid]
            clipped = clip_line_to_polygon(ray[0], ray[1], region.polygon)
            if not clipped:
                continue
            poly_a, poly_b = split_polygon_by_line(
                region.polygon, clipped[0], clipped[1]
            )
            if (
                len(poly_a) < 3
                or len(poly_b) < 3
                or polygon_area(poly_a) < 0.1
                or polygon_area(poly_b) < 0.1
            ):
                continue

            child_a = Region(poly_a, label=region.label + "a", parent_id=region.id)
            child_b = Region(poly_b, label=region.label + "b", parent_id=region.id)
            self.regions[child_a.id], self.regions[child_b.id] = child_a, child_b
            region.children = [child_a.id, child_b.id]
            region.split_boundary = is_boundary
            cut_count += 1

        self.sanitize_tree()
        return cut_count

    def heal_regions(self, id1, id2):
        if id1 not in self.regions or id2 not in self.regions:
            return False, "One or both pieces could not be found."

        r1, r2 = self.regions[id1], self.regions[id2]
        p1, p2 = r1.polygon, r2.polygon

        match = exact_edge_match(p1, p2, tol=1.5)
        if not match:
            return (
                False,
                "Selected pieces do not share an exact straight edge boundary.",
            )

        merged_poly = merge_polygons(p1, p2, match[0], match[1], match[2])
        new_region = Region(merged_poly, label=r1.label)

        parents_to_check = set()
        if r1.parent_id in self.regions:
            parents_to_check.add(r1.parent_id)
        if r2.parent_id in self.regions:
            parents_to_check.add(r2.parent_id)

        for old_r in [r1, r2]:
            if old_r.parent_id and old_r.parent_id in self.regions:
                parent = self.regions[old_r.parent_id]
                if old_r.id in parent.children:
                    parent.children.remove(old_r.id)
            del self.regions[old_r.id]

        self.regions[new_region.id] = new_region

        duplicate_parent_id = None
        for pid in parents_to_check:
            parent = self.regions[pid]
            if len(parent.children) == 0:
                area_diff = abs(parent.area_sq_in() - new_region.area_sq_in())
                cx_p, cy_p = polygon_centroid(parent.polygon)
                cx_n, cy_n = polygon_centroid(new_region.polygon)
                dist = math.hypot(cx_p - cx_n, cy_p - cy_n)
                if area_diff < 0.01 and dist < 1.0:
                    duplicate_parent_id = pid
                    break

        if duplicate_parent_id:
            parent = self.regions[duplicate_parent_id]
            parent.label = r1.label
            parent.polygon = new_region.polygon
            del self.regions[new_region.id]
            msg = "Heal Successful. Redundant duplicate prevented."
        else:
            msg = "Heal Successful. Orphan node generated."

        self.sanitize_tree()
        return True, msg

    def smart_heal_regions(self, selected_leaf_ids):
        if not selected_leaf_ids or len(selected_leaf_ids) < 2:
            return False, "Select at least two pieces.", []

        paths = [self.find_path(self.root_id, sid) for sid in selected_leaf_ids]
        if not all(paths):
            return False, "Could not trace pieces in the block history.", []

        lca_id = self.root_id
        min_len = min(len(p) for p in paths)
        for i in range(min_len):
            val = paths[0][i]
            if all(p[i] == val for p in paths):
                lca_id = val
            else:
                break

        for sid in selected_leaf_ids:
            path = self.find_path(self.root_id, sid)
            idx = path.index(lca_id)
            for node_id in path[idx:]:
                if self.regions[node_id].split_boundary:
                    return (
                        False,
                        "Cannot heal across an initial structural grid boundary.",
                        [],
                    )

        lca_node = self.regions[lca_id]
        if lca_node.is_leaf():
            return False, "Pieces are already healed.", []

        consumed_leaves = []

        def get_leaves(n_id):
            n = self.regions[n_id]
            if n.is_leaf():
                consumed_leaves.append(n)
            else:
                for c_id in n.children:
                    get_leaves(c_id)

        get_leaves(lca_id)
        guide_polys = [leaf.polygon for leaf in consumed_leaves]

        def delete_descendants(n_id):
            n = self.regions[n_id]
            for c_id in n.children:
                delete_descendants(c_id)
                if c_id in self.regions:
                    del self.regions[c_id]
            n.children = []

        delete_descendants(lca_id)
        lca_node.label = "TEMP_HEAL"
        lca_node.split_boundary = False

        self.sanitize_tree()
        return (
            True,
            f"Smart Heal activated: Collapsed {len(consumed_leaves)} pieces into their original parent block.",
            guide_polys,
        )

    def virtual_sewing_validator(self, selected_leaf_ids, force_start_id=None):
        """Guillotine Convex Separability Check - Normalized absolute pixel tolerance"""
        if not selected_leaf_ids:
            return False, []
        if len(selected_leaf_ids) == 1:
            return True, list(selected_leaf_ids)

        polygons = {nid: self.regions[nid].polygon for nid in selected_leaf_ids}
        sequence = []
        remaining_ids = set(selected_leaf_ids)

        while remaining_ids:
            removed_id = None

            for test_id in list(remaining_ids):
                if (
                    force_start_id
                    and len(remaining_ids) > 1
                    and test_id == force_start_id
                ):
                    continue

                p_test = polygons[test_id]
                rest_ids = remaining_ids - {test_id}
                if not rest_ids:
                    removed_id = test_id
                    break

                is_separable = False
                n = len(p_test)
                for i in range(n):
                    p1 = p_test[i]
                    p2 = p_test[(i + 1) % n]
                    d = vec_sub(p2, p1)
                    l_d = vec_len(d)
                    if l_d < EPSILON:
                        continue

                    # NORMALIZE the direction vector to prevent floating point explosions on long lines
                    nd = (d[0] / l_d, d[1] / l_d)

                    crosses = False
                    rest_side = 0

                    for r_id in rest_ids:
                        for pt in polygons[r_id]:
                            v = vec_sub(pt, p1)
                            # Absolute pixel distance from the cut line
                            dist = nd[0] * v[1] - nd[1] * v[0]

                            if dist > 1.5:
                                if rest_side == -1:
                                    crosses = True
                                    break
                                rest_side = 1
                            elif dist < -1.5:
                                if rest_side == 1:
                                    crosses = True
                                    break
                                rest_side = -1
                        if crosses:
                            break

                    if not crosses:
                        test_side = 0
                        for pt in p_test:
                            v = vec_sub(pt, p1)
                            dist = nd[0] * v[1] - nd[1] * v[0]

                            if dist > 1.5:
                                if test_side == -1:
                                    crosses = True
                                    break
                                test_side = 1
                            elif dist < -1.5:
                                if test_side == 1:
                                    crosses = True
                                    break
                                test_side = -1

                        if not crosses and (
                            rest_side == 0 or test_side == 0 or rest_side != test_side
                        ):
                            is_separable = True
                            break

                if is_separable:
                    removed_id = test_id
                    break

            if removed_id is not None:
                sequence.append(removed_id)
                remaining_ids.remove(removed_id)
            else:
                return False, []

        sequence.reverse()
        if force_start_id and sequence[0] != force_start_id:
            return False, []
        return True, sequence

    def get_structural_groups(self):
        groups = []

        def walk(node_id):
            node = self.regions[node_id]
            if node.is_leaf():
                return [node.id]
            left_leaves = walk(node.children[0])
            right_leaves = walk(node.children[1])
            if node.split_boundary:
                if left_leaves:
                    groups.append(left_leaves)
                if right_leaves:
                    groups.append(right_leaves)
                return []
            else:
                return left_leaves + right_leaves

        top_leaves = walk(self.root_id)
        if top_leaves:
            groups.append(top_leaves)
        return groups

    def auto_partition_and_label(self, preserve_manual=False):
        self.sanitize_tree()
        remaining_ids = set(r.id for r in self.leaf_regions())

        if preserve_manual:
            for r in self.leaf_regions():
                if not r.label.startswith("P") and not r.label.startswith("A"):
                    if re.match(r"^[A-Za-z]+\d+$", r.label):
                        if r.id in remaining_ids:
                            remaining_ids.remove(r.id)

        def greedy_fallback(rem_ids):
            local_secs = []
            local_rem = set(rem_ids)
            while local_rem:
                start_id = min(
                    local_rem, key=lambda nid: self.regions[nid].area_sq_in()
                )
                seq = [start_id]
                local_rem.remove(start_id)
                changed = True
                while changed:
                    changed = False
                    for next_id in list(local_rem):
                        test_seq = seq + [next_id]
                        is_valid, _ = self.virtual_sewing_validator(test_seq)
                        if is_valid:
                            seq.append(next_id)
                            local_rem.remove(next_id)
                            changed = True
                            break
                local_secs.append(seq)
            return local_secs

        def partition_into_sections(region_ids):
            """Recursive Guillotine Slicer with Normalized Tolerance"""
            is_valid, seq = self.virtual_sewing_validator(region_ids)
            if is_valid:
                return [seq]

            polys = {rid: self.regions[rid].polygon for rid in region_ids}
            for rid, poly in polys.items():
                n = len(poly)
                for i in range(n):
                    p1 = poly[i]
                    p2 = poly[(i + 1) % n]
                    d = vec_sub(p2, p1)
                    l_d = vec_len(d)
                    if l_d < EPSILON:
                        continue

                    nd = (d[0] / l_d, d[1] / l_d)

                    cuts_interior = False
                    left_group = []
                    right_group = []

                    for test_rid, test_poly in polys.items():
                        side_1 = False
                        side_neg1 = False
                        for pt in test_poly:
                            v = vec_sub(pt, p1)
                            dist = nd[0] * v[1] - nd[1] * v[0]

                            if dist > 1.5:
                                side_1 = True
                            elif dist < -1.5:
                                side_neg1 = True

                        if side_1 and side_neg1:
                            cuts_interior = True
                            break
                        elif side_1:
                            left_group.append(test_rid)
                        elif side_neg1:
                            right_group.append(test_rid)
                        else:
                            left_group.append(test_rid)

                    if not cuts_interior and left_group and right_group:
                        return partition_into_sections(
                            left_group
                        ) + partition_into_sections(right_group)

            return greedy_fallback(region_ids)

        sections = []
        groups = self.get_structural_groups()

        for grp_ids in groups:
            grp_rem = [nid for nid in grp_ids if nid in remaining_ids]
            if not grp_rem:
                continue

            secs = partition_into_sections(grp_rem)
            sections.extend(secs)
            for sec in secs:
                for nid in sec:
                    remaining_ids.discard(nid)

        def sec_centroid(sec_ids):
            cx = sum(
                polygon_centroid(self.regions[nid].polygon)[0] for nid in sec_ids
            ) / len(sec_ids)
            cy = sum(
                polygon_centroid(self.regions[nid].polygon)[1] for nid in sec_ids
            ) / len(sec_ids)
            return (cx, cy)

        sections.sort(key=lambda s: (sec_centroid(s)[1], sec_centroid(s)[0]))

        used_letters = set()
        if preserve_manual:
            for r in self.leaf_regions():
                match = re.match(r"^([A-Za-z]+)", r.label)
                if match:
                    used_letters.add(match.group(1).upper())

        def get_available_letter():
            for idx in range(26):
                letter = chr(65 + idx)
                if letter not in used_letters:
                    used_letters.add(letter)
                    return letter
            return "Z"

        for sec_ids in sections:
            letter = get_available_letter()
            for i, nid in enumerate(sec_ids):
                self.regions[nid].label = f"{letter}{i + 1}"

    def rebuild_alphabet(self):
        self.sanitize_tree()
        groups = {}
        for r in self.leaf_regions():
            match = re.match(r"^([A-Za-z_]+)", r.label)
            prefix = match.group(1) if match else "A"
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(r)

        def group_centroid(grp):
            cx = sum(polygon_centroid(n.polygon)[0] for n in grp) / len(grp)
            cy = sum(polygon_centroid(n.polygon)[1] for n in grp) / len(grp)
            return (cx, cy)

        sorted_groups = sorted(
            groups.values(),
            key=lambda grp: (group_centroid(grp)[1], group_centroid(grp)[0]),
        )

        def get_letter(idx):
            if idx < 26:
                return chr(65 + idx)
            return chr(65 + (idx // 26) - 1) + chr(65 + (idx % 26))

        for sec_idx, grp in enumerate(sorted_groups):
            letter = get_letter(sec_idx)
            grp_ids = [n.id for n in grp]
            current_first = min(
                grp,
                key=lambda n: (
                    int(re.search(r"\d+", n.label).group())
                    if re.search(r"\d+", n.label)
                    else 999
                ),
            )

            is_valid, sequence = self.virtual_sewing_validator(
                grp_ids, force_start_id=current_first.id
            )
            if not is_valid:
                is_valid, sequence = self.virtual_sewing_validator(grp_ids)

            if is_valid:
                for i, nid in enumerate(sequence):
                    self.regions[nid].label = f"{letter}{i + 1}"
            else:
                for i, n in enumerate(grp):
                    n.label = f"{letter}{i + 1}"

    def undo_last_cut(self):
        leaf_ids = {r.id for r in self.leaf_regions()}
        candidates = [
            r
            for r in self.regions.values()
            if r.children and all(c in leaf_ids for c in r.children)
        ]
        if not candidates:
            return None
        parent = max(candidates, key=lambda r: r.id)
        for cid in parent.children:
            del self.regions[cid]
        parent.children = []
        self.sanitize_tree()
        return parent

    # ------------------------------------------------------------------
    # Crop to shape (used by the Resize plugin's "Crop to Shape" action)
    # ------------------------------------------------------------------
    def _chain_leaves(self, leaf_ids, fill_polygon):
        """Build a right-leaning *binary* chain over the given leaf ids and
        return the id of the chain's top node. All internal nodes are
        non-boundary, so downstream code treats the chain as one structural
        group. ``fill_polygon`` is a harmless placeholder for internal nodes
        (their polygons are never read by the labelling engine)."""
        if not leaf_ids:
            return None
        if len(leaf_ids) == 1:
            return leaf_ids[0]
        prev = leaf_ids[-1]
        for lid in reversed(leaf_ids[:-1]):
            internal = Region(list(fill_polygon))
            internal.children = [lid, prev]
            internal.split_boundary = False
            self.regions[internal.id] = internal
            self.regions[lid].parent_id = internal.id
            self.regions[prev].parent_id = internal.id
            prev = internal.id
        return prev

    def _next_section_letter(self):
        used = set()
        for r in self.leaf_regions():
            m = re.match(r"^([A-Za-z]+)", r.label)
            if m:
                used.add(m.group(1).upper())
        for i in range(26):
            ch = chr(65 + i)
            if ch not in used:
                return ch
        return "Z"

    def _attach_spacing_frame(self, strip_polys, box_polygon):
        """GROW path: leave the existing tree (and all its labels) untouched
        and bolt the spacing strips on as their own structural section."""
        if not strip_polys:
            return 0
        # Order strips top->bottom then left->right for a natural sew sequence.
        ordered = sorted(strip_polys, key=lambda p: polygon_centroid(p)[::-1])
        letter = self._next_section_letter()
        spacing_ids = []
        for i, poly in enumerate(ordered):
            r = Region(poly, label=f"{letter}{i + 1}")
            self.regions[r.id] = r
            spacing_ids.append(r.id)

        spacing_top = self._chain_leaves(spacing_ids, box_polygon)
        old_root_id = self.root_id

        new_root = Region(list(box_polygon), label="ROOT")
        new_root.children = [old_root_id, spacing_top]
        new_root.split_boundary = True  # keep block & frame as separate sections
        self.regions[new_root.id] = new_root
        self.regions[old_root_id].parent_id = new_root.id
        self.regions[spacing_top].parent_id = new_root.id
        self.root_id = new_root.id
        self.sanitize_tree()
        return len(spacing_ids)

    def _rebuild_from_pieces(self, piece_polys, box_polygon):
        """CROP path: discard the old hierarchy and rebuild a fresh, valid
        binary tree from the supplied finished-piece polygons."""
        self.regions = {}
        leaf_ids = []
        for poly in piece_polys:
            r = Region(poly)
            self.regions[r.id] = r
            leaf_ids.append(r.id)
        if not leaf_ids:
            root = Region(list(box_polygon), label="A1")
            self.regions[root.id] = root
            self.root_id = root.id
            return
        self.root_id = self._chain_leaves(leaf_ids, box_polygon)
        self.sanitize_tree()

    def crop_to_box(self, x0, y0, x1, y1, min_area_sq_in=0.05, relabel_on_crop=True):
        """Crop or grow the managed block to an axis-aligned box (local px).

        Two regimes:
          * GROW  - the box fully contains the current block: the block is
            kept verbatim (geometry AND labels) and the surplus margin is
            filled with spacing strips that form their own section.
          * CROP  - any box edge cuts into the block: leaf pieces are clipped
            to the box (fully-outside pieces dropped), any surplus margin is
            filled with spacing strips, and the tree is rebuilt + relabelled.

        Returns a report dict.
        """
        X0, X1 = (x0, x1) if x0 <= x1 else (x1, x0)
        Y0, Y1 = (y0, y1) if y0 <= y1 else (y1, y0)
        box_poly = [(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)]

        leaves = self.leaf_regions()
        pts = [p for r in leaves for p in r.polygon]
        if not pts:
            return {"mode": "empty", "removed": 0, "reshaped": 0, "spacing": 0}

        bminx = min(p[0] for p in pts)
        bmaxx = max(p[0] for p in pts)
        bminy = min(p[1] for p in pts)
        bmaxy = max(p[1] for p in pts)

        TOL = 0.5  # px slack so a box drawn exactly on the edge counts as grow
        grow_only = (
            X0 <= bminx + TOL
            and Y0 <= bminy + TOL
            and X1 >= bmaxx - TOL
            and Y1 >= bmaxy - TOL
        )

        if grow_only:
            strips = rect_frame_strips((X0, Y0, X1, Y1), (bminx, bminy, bmaxx, bmaxy))
            n = self._attach_spacing_frame(strips, box_poly)
            return {
                "mode": "grow",
                "removed": 0,
                "reshaped": 0,
                "spacing": n,
                "box": (X0, Y0, X1, Y1),
            }

        # --- CROP regime -------------------------------------------------
        survivors = []
        removed = 0
        reshaped = 0
        for r in leaves:
            clipped = clip_polygon_to_rect(r.polygon, X0, Y0, X1, Y1)
            if (
                len(clipped) < 3
                or polygon_area(clipped) / (PX_PER_INCH ** 2) < min_area_sq_in
            ):
                removed += 1
                continue
            if not _polys_equivalent(clipped, r.polygon):
                reshaped += 1
            survivors.append((clipped, r.label))

        if survivors:
            spts = [p for poly, _ in survivors for p in poly]
            cminx = min(p[0] for p in spts)
            cmaxx = max(p[0] for p in spts)
            cminy = min(p[1] for p in spts)
            cmaxy = max(p[1] for p in spts)
        else:
            cminx, cminy, cmaxx, cmaxy = X0, Y0, X1, Y1

        strips = rect_frame_strips((X0, Y0, X1, Y1), (cminx, cminy, cmaxx, cmaxy))

        all_pieces = [poly for poly, _ in survivors] + strips
        # Stash surviving labels so we can optionally restore them.
        survivor_labels = [lbl for _, lbl in survivors]
        self._rebuild_from_pieces(all_pieces, box_poly)

        if relabel_on_crop:
            self.auto_partition_and_label()
        else:
            # Best-effort: hand surviving pieces their old labels back (in the
            # order they were rebuilt), and give spacing strips a fresh section.
            ordered_leaves = [
                self.regions[i] for i in self.regions if self.regions[i].is_leaf()
            ]
            ordered_leaves.sort(key=lambda r: r.id)
            for r, lbl in zip(ordered_leaves, survivor_labels):
                r.label = lbl
            self.rebuild_alphabet()

        return {
            "mode": "crop",
            "removed": removed,
            "reshaped": reshaped,
            "spacing": len(strips),
            "box": (X0, Y0, X1, Y1),
        }

    def to_dict(self):
        return {
            "root_id": self.root_id,
            "regions": {str(k): v.to_dict() for k, v in self.regions.items()},
        }

    @staticmethod
    def from_dict(d):
        tree = RegionTree()
        tree.root_id = d["root_id"]
        for v in d["regions"].values():
            r = Region.from_dict(v)
            tree.regions[r.id] = r
            if r.id >= Region._counter:
                Region._counter = r.id + 1
        return tree


class BlockData:
    def __init__(self, tree, prefs=None):
        self.tree = tree
        self.prefs = prefs or {"show_sa": False, "sa_in": 0.25, "color_mode": "piece"}
        if "custom_colors" not in self.prefs:
            self.prefs["custom_colors"] = {}

    def to_json(self):
        return json.dumps({"tree": self.tree.to_dict(), "prefs": self.prefs})

    @staticmethod
    def from_json(text):
        data = json.loads(text)
        if "tree" in data and "prefs" in data:
            return BlockData(RegionTree.from_dict(data["tree"]), data["prefs"])
        else:
            return BlockData(RegionTree.from_dict(data))


def find_fpp_group(svg):
    for g in svg.findall(f".//{{{SVG_NS}}}g"):
        desc = g.find(f"{{{SVG_NS}}}desc[@id='{FPP_DATA_TAG_ID}']")
        if desc is not None and desc.text:
            return g, BlockData.from_json(desc.text)
    return None, None


def get_color_for_label(label, mode, idx):
    if mode == "section":
        match = re.search(r"^([A-Za-z]+)", label)
        if match and not match.group(0).startswith("TEMP"):
            char = match.group(0).upper()
            pal_idx = (ord(char[0]) - 65) % len(SECTION_PALETTE)
            return SECTION_PALETTE.get(char[0], SECTION_PALETTE_LIST[pal_idx])
    return PIECE_COLORS[idx % len(PIECE_COLORS)]


def build_fpp_layer(block_data):
    g = etree.Element(
        "{%s}g" % SVG_NS,
        id="fpp-quilttools-layer",
        **{
            f"{{{INKSCAPE_NS}}}label": "Quilt Tools FPP Regions",
            f"{{{INKSCAPE_NS}}}groupmode": "layer",
        },
    )
    refresh_layer(g, block_data)
    return g


def refresh_layer(g, block_data):
    for child in list(g):
        g.remove(child)
    tree, prefs = block_data.tree, block_data.prefs
    sa_px = (
        prefs.get("sa_in", 0.25) * PX_PER_INCH if prefs.get("show_sa", False) else 0.0
    )
    color_mode = prefs.get("color_mode", "piece")
    custom_colors = prefs.get("custom_colors", {})
    group_by_color = prefs.get("group_by_color", False)

    color_groups = {}

    for idx, region in enumerate(sorted(tree.leaf_regions(), key=lambda r: r.label)):
        fill_color = custom_colors.get(str(region.id))
        if not fill_color:
            fill_color = get_color_for_label(region.label, color_mode, idx)

        # Decide container group
        if group_by_color:
            if fill_color not in color_groups:
                clean_hex = fill_color.lstrip("#")
                color_g = etree.SubElement(
                    g,
                    "{%s}g" % SVG_NS,
                    id=f"color-group-{clean_hex}",
                    style=f"fill:{fill_color}",
                    **{
                        f"{{{INKSCAPE_NS}}}label": f"Fabric {fill_color}",
                        f"{{{INKSCAPE_NS}}}groupmode": "group",
                    }
                )
                color_groups[fill_color] = color_g
            container = color_groups[fill_color]
            path_fill = "inherit"
        else:
            container = g
            path_fill = fill_color

        if sa_px > 0:
            sa_poly = offset_polygon(region.polygon, sa_px, miter_limit=2.0)
            if sa_poly:
                sa_d = (
                    "M {:.4f},{:.4f} ".format(*sa_poly[0])
                    + " ".join("L {:.4f},{:.4f}".format(*p) for p in sa_poly[1:])
                    + " Z"
                )
                sa_attribs = {
                    "d": sa_d,
                    "id": f"sa-{region.label}",
                    "style": "fill:none;stroke:#cc0000;stroke-width:0.6;stroke-dasharray:4,2;opacity:0.7;pointer-events:none;",
                    f"{{{SODIPODI_NS}}}insensitive": "true",
                }
                etree.SubElement(container, "{%s}path" % SVG_NS, **sa_attribs)

        path_el = etree.SubElement(
            container,
            "{%s}path" % SVG_NS,
            d=region.path_d(),
            id=f"region-{region.label}",
            style=f"fill:{path_fill};fill-opacity:0.80;stroke:#222222;stroke-width:1.0;stroke-linejoin:round",
        )
        path_el.set(FPP_REGION_ATTR, str(region.id))

        cx, cy = polygon_centroid(region.polygon)
        txt = etree.SubElement(
            container,
            "{%s}text" % SVG_NS,
            x=f"{cx:.2f}",
            y=f"{cy:.2f}",
            style="font-size:11px;font-family:sans-serif;text-anchor:middle;dominant-baseline:middle;fill:#333333;pointer-events:none",
        )
        txt.text = region.label

    desc = etree.SubElement(g, "{%s}desc" % SVG_NS, id=FPP_DATA_TAG_ID)
    desc.text = block_data.to_json()


def invert_transform(t):
    t = inkex.Transform(t)
    a, b, c, d, e, f = t.a, t.b, t.c, t.d, t.e, t.f
    det = a * d - b * c
    if abs(det) < 1e-9:
        return inkex.Transform()
    inv_a = d / det
    inv_b = -b / det
    inv_c = -c / det
    inv_d = a / det
    inv_e = (c * f - d * e) / det
    inv_f = (b * e - a * f) / det
    return inkex.Transform(((inv_a, inv_c, inv_e), (inv_b, inv_d, inv_f)))


def parse_svg_dim(val, default):
    if not val:
        return default
    m = re.match(r"^\s*([0-9.]+)\s*([a-zA-Z]*)", val)
    if m:
        num = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "in":
            return num * 96.0
        elif unit == "pt":
            return num * (96.0 / 72.0)
        elif unit == "mm":
            return num * (96.0 / 25.4)
        elif unit == "cm":
            return num * (96.0 / 2.54)
        return num
    return default


def resolve_element_fill(el):
    current = el
    while current is not None:
        style = current.get("style", "")
        m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", style)
        if m:
            fill_val = m.group(1)
            if fill_val not in ["none", "currentColor"]:
                return fill_val
        
        fill_attr = current.get("fill")
        if fill_attr and fill_attr not in ["none", "currentColor"]:
            return fill_attr
            
        current = current.getparent()
    return None


def safe_float_unit(el, val_str):
    if not val_str:
        return 0.0
    if hasattr(el, "unittouu"):
        try:
            return float(el.unittouu(val_str))
        except Exception:
            pass
    m = re.match(r"^\s*([0-9.-]+)\s*([a-zA-Z]*)", val_str)
    if m:
        num = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "in":
            return num * 96.0
        elif unit == "pt":
            return num * (96.0 / 72.0)
        elif unit == "mm":
            return num * (96.0 / 25.4)
        elif unit == "cm":
            return num * (96.0 / 2.54)
        return num
    return 0.0


def estimate_element_bbox(el):
    tag = el.tag.split("}")[-1]
    pts = []
    
    if tag == "rect":
        try:
            x = safe_float_unit(el, el.get("x", "0"))
            y = safe_float_unit(el, el.get("y", "0"))
            w = safe_float_unit(el, el.get("width", "0"))
            h = safe_float_unit(el, el.get("height", "0"))
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        except Exception:
            pass
    elif tag in ["circle", "ellipse"]:
        try:
            cx = safe_float_unit(el, el.get("cx", "0"))
            cy = safe_float_unit(el, el.get("cy", "0"))
            r = el.get("r")
            if r:
                rx = ry = safe_float_unit(el, r)
            else:
                rx = safe_float_unit(el, el.get("rx", "0"))
                ry = safe_float_unit(el, el.get("ry", "0"))
            pts = [(cx - rx, cy - ry), (cx + rx, cy - ry), (cx + rx, cy + ry), (cx - rx, cy + ry)]
        except Exception:
            pass
    elif tag == "polygon":
        try:
            raw_pts = [float(v) for v in re.split(r"[,\s]+", el.get("points", "")) if v]
            if raw_pts:
                pts = list(zip(raw_pts[0::2], raw_pts[1::2]))
        except Exception:
            pass
    elif tag == "path":
        try:
            d = el.get("d", "")
            raw_pts = [float(val) for val in re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", d)]
            if raw_pts:
                pts = list(zip(raw_pts[0::2], raw_pts[1::2]))
        except Exception:
            pass

    if not pts:
        return None

    try:
        t = el.composed_transform()
        trans_pts = [t.apply_to_point(pt) for pt in pts]
    except Exception:
        trans_pts = pts

    xs = [pt[0] for pt in trans_pts]
    ys = [pt[1] for pt in trans_pts]
    
    class SimpleBBox:
        def __init__(self, x0, y0, x1, y1):
            self.left = x0
            self.right = x1
            self.top = y0
            self.bottom = y1
            self.width = x1 - x0
            self.height = y1 - y0
            
    return SimpleBBox(min(xs), min(ys), max(xs), max(ys))


def extract_vector_shapes(root_el):
    shapes = []
    for el in root_el.xpath("//*[local-name()='path' or local-name()='rect' or local-name()='circle' or local-name()='ellipse' or local-name()='polygon']"):
        color = resolve_element_fill(el)
        if not color:
            continue
            
        bbox = estimate_element_bbox(el)
        if bbox:
            w = bbox.width
            h = bbox.height
            if w > 0 and h > 0:
                shapes.append(((bbox.left, bbox.top, bbox.right, bbox.bottom), color, w * h))
    return shapes


def sample_image_colors(svg, block_data):
    import base64
    import io
    import os
    import urllib.parse
    custom_colors = block_data.prefs.setdefault("custom_colors", {})
    regions = block_data.tree.leaf_regions()
    sampled_count = 0

    try:
        from PIL import Image
        images = svg.findall(f".//{{{SVG_NS}}}image")
    except ImportError:
        images = []
        Image = None

    for img_el in images:
        href = img_el.get("href") or img_el.get(f"{{{SVG_NS}}}href") or img_el.get("{http://www.w3.org/1999/xlink}href")
        if not href:
            continue

        try:
            is_svg = False
            ext_svg = None
            
            if href.startswith("data:image/svg+xml"):
                is_svg = True
                header, encoded = href.split(";base64,", 1)
                data = base64.b64decode(encoded).decode("utf-8")
                ext_svg = etree.fromstring(data.encode("utf-8"))
            elif href.lower().endswith(".svg") or ".svg?" in href.lower() or ".svg#" in href.lower():
                is_svg = True
                if href.startswith("file:///"):
                    filepath = urllib.parse.unquote(href[8:])
                    if (filepath[1] == ":" or filepath[2] == ":") and filepath[0] == "/":
                        filepath = filepath[1:]
                elif href.startswith("file://"):
                    filepath = urllib.parse.unquote(href[7:])
                else:
                    filepath = href
                    docname = svg.get(f"{{{SODIPODI_NS}}}docname") or svg.get("sodipodi:docname")
                    if docname:
                        base_dir = os.path.dirname(docname)
                        candidate = os.path.join(base_dir, href)
                        if os.path.exists(candidate):
                            filepath = candidate
                ext_svg = etree.parse(filepath).getroot()

            if is_svg and ext_svg is not None:
                ext_w = parse_svg_dim(ext_svg.get("width"), 100.0)
                ext_h = parse_svg_dim(ext_svg.get("height"), 100.0)
                viewbox = ext_svg.get("viewBox")
                if viewbox:
                    parts = viewbox.split()
                    if len(parts) == 4:
                        try:
                            ext_w = float(parts[2])
                            ext_h = float(parts[3])
                        except ValueError:
                            pass
                
                bg_shapes = extract_vector_shapes(ext_svg)
                if bg_shapes:
                    x_attr = float(svg.unittouu(img_el.get("x", "0")))
                    y_attr = float(svg.unittouu(img_el.get("y", "0")))
                    w_attr = float(svg.unittouu(img_el.get("width", "0")))
                    h_attr = float(svg.unittouu(img_el.get("height", "0")))
                    if w_attr > 0 and h_attr > 0:
                        img_t = img_el.composed_transform()
                        inv_t = invert_transform(img_t)
                        
                        for r in regions:
                            if str(r.id) in custom_colors:
                                continue
                            cx, cy = polygon_centroid(r.polygon)
                            local_cx, local_cy = inv_t.apply_to_point((cx, cy))
                            u = (local_cx - x_attr) / w_attr
                            v = (local_cy - y_attr) / h_attr
                            
                            if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                                ext_cx = u * ext_w
                                ext_cy = v * ext_h
                                
                                matching = []
                                for bbox, color, area in bg_shapes:
                                    if bbox[0] <= ext_cx <= bbox[2] and bbox[1] <= ext_cy <= bbox[3]:
                                        matching.append((color, area))
                                if matching:
                                    matching.sort(key=lambda x: x[1])
                                    custom_colors[str(r.id)] = matching[0][0]
                                    sampled_count += 1
            else:
                if Image is None:
                    continue
                if href.startswith("data:image/"):
                    header, encoded = href.split(";base64,", 1)
                    data = base64.b64decode(encoded)
                    pil_img = Image.open(io.BytesIO(data))
                else:
                    if href.startswith("file:///"):
                        filepath = urllib.parse.unquote(href[8:])
                        if (filepath[1] == ":" or filepath[2] == ":") and filepath[0] == "/":
                            filepath = filepath[1:]
                    elif href.startswith("file://"):
                        filepath = urllib.parse.unquote(href[7:])
                    else:
                        filepath = href
                        docname = svg.get(f"{{{SODIPODI_NS}}}docname") or svg.get("sodipodi:docname")
                        if docname:
                            base_dir = os.path.dirname(docname)
                            candidate = os.path.join(base_dir, href)
                            if os.path.exists(candidate):
                                filepath = candidate
                    pil_img = Image.open(filepath)

                x_attr = float(svg.unittouu(img_el.get("x", "0")))
                y_attr = float(svg.unittouu(img_el.get("y", "0")))
                w_attr = float(svg.unittouu(img_el.get("width", "0")))
                h_attr = float(svg.unittouu(img_el.get("height", "0")))
                if w_attr <= 0 or h_attr <= 0:
                    continue

                img_t = img_el.composed_transform()
                inv_t = invert_transform(img_t)

                for r in regions:
                    if str(r.id) in custom_colors:
                        continue
                    cx, cy = polygon_centroid(r.polygon)
                    local_cx, local_cy = inv_t.apply_to_point((cx, cy))
                    u = (local_cx - x_attr) / w_attr
                    v = (local_cy - y_attr) / h_attr

                    if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                        px_x = int(u * pil_img.width)
                        px_y = int(v * pil_img.height)
                        colors = []
                        for dx in range(-1, 2):
                            for dy in range(-1, 2):
                                xx = min(max(0, px_x + dx), pil_img.width - 1)
                                yy = min(max(0, px_y + dy), pil_img.height - 1)
                                color = pil_img.getpixel((xx, yy))
                                if isinstance(color, tuple):
                                    colors.append(color[:3])
                                else:
                                    colors.append((color, color, color))
                        r_vals = sorted([c[0] for c in colors])
                        g_vals = sorted([c[1] for c in colors])
                        b_vals = sorted([c[2] for c in colors])
                        median_rgb = (r_vals[len(r_vals)//2], g_vals[len(g_vals)//2], b_vals[len(b_vals)//2])
                        hex_color = "#{:02x}{:02x}{:02x}".format(*median_rgb)
                        custom_colors[str(r.id)] = hex_color
                        sampled_count += 1

        except Exception:
            continue

    # 2. Try to sample from vector background shapes (SVG tracing mode)
    bg_shapes = []
    for tag in ["path", "rect", "circle", "ellipse", "polygon"]:
        for el in svg.findall(f".//{{{SVG_NS}}}{tag}"):
            # Skip if part of FPP layout
            parent = el.getparent()
            is_fpp = False
            while parent is not None:
                pid = parent.get("id")
                if pid in ["fpp-quilttools-layer", "fpp-layout-layer"]:
                    is_fpp = True
                    break
                parent = parent.getparent()
            if is_fpp:
                continue

            color = resolve_element_fill(el)
            if color:
                bbox = estimate_element_bbox(el)

                if bbox and bbox.width > 0 and bbox.height > 0:
                    # Compute bbox area for sorting
                    area = bbox.width * bbox.height
                    bg_shapes.append((bbox, color, area))

    if bg_shapes:
        for r in regions:
            if str(r.id) in custom_colors:
                continue
            cx, cy = polygon_centroid(r.polygon)
            matching = []
            for bbox, color, area in bg_shapes:
                if bbox.left <= cx <= bbox.right and bbox.top <= cy <= bbox.bottom:
                    matching.append((color, area))
            if matching:
                # Sort by area ascending so that the smallest/innermost overlapping shape is picked
                matching.sort(key=lambda x: x[1])
                custom_colors[str(r.id)] = matching[0][0]
                sampled_count += 1
    return sampled_count


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def quantize_block_colors(block_data, N, locked_hex_list):
    custom_colors = block_data.prefs.setdefault("custom_colors", {})
    regions = block_data.tree.leaf_regions()
    if not regions:
        return

    # Parse locked colors
    locked_rgbs = []
    for h in locked_hex_list:
        if h.strip():
            try:
                locked_rgbs.append(hex_to_rgb(h.strip()))
            except Exception:
                pass

    # Gather current colors
    color_mode = block_data.prefs.get("color_mode", "piece")
    region_colors = {}
    for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
        c = custom_colors.get(str(r.id))
        if not c:
            c = get_color_for_label(r.label, color_mode, idx)
        try:
            region_colors[r.id] = hex_to_rgb(c)
        except Exception:
            region_colors[r.id] = (214, 234, 248)  # default blue

    unique_colors = list(set(region_colors.values()))
    if len(unique_colors) <= N:
        # No quantization needed
        for rid, rgb in region_colors.items():
            custom_colors[str(rid)] = rgb_to_hex(rgb)
        return

    # Setup centroids
    L = len(locked_rgbs)
    if L >= N:
        centroids = locked_rgbs[:N]
        # Just map everything to closest locked color
        for rid, rgb in region_colors.items():
            best_c = min(centroids, key=lambda c: math.hypot(rgb[0]-c[0], rgb[1]-c[1], rgb[2]-c[2]))
            custom_colors[str(rid)] = rgb_to_hex(best_c)
        return

    # Standard K-means in RGB space
    centroids = list(locked_rgbs)
    remaining_colors = [c for c in unique_colors if c not in locked_rgbs]
    # Initialize remaining centroids from most frequent remaining colors
    freqs = {}
    for rgb in region_colors.values():
        if rgb not in locked_rgbs:
            freqs[rgb] = freqs.get(rgb, 0) + 1
    sorted_rem = sorted(remaining_colors, key=lambda c: freqs.get(c, 0), reverse=True)
    centroids.extend(sorted_rem[:N-L])
    while len(centroids) < N and unique_colors:
        centroids.append(unique_colors[0])

    for _ in range(20):
        clusters = [[] for _ in range(N)]
        for rid, rgb in region_colors.items():
            best_idx = min(range(N), key=lambda idx: math.hypot(rgb[0]-centroids[idx][0], rgb[1]-centroids[idx][1], rgb[2]-centroids[idx][2]))
            clusters[best_idx].append(rgb)

        # Update variable centroids only
        for i in range(L, N):
            if clusters[i]:
                avg_r = int(sum(c[0] for c in clusters[i]) / len(clusters[i]))
                avg_g = int(sum(c[1] for c in clusters[i]) / len(clusters[i]))
                avg_b = int(sum(c[2] for c in clusters[i]) / len(clusters[i]))
                centroids[i] = (avg_r, avg_g, avg_b)

    # Assign final colors
    for rid, rgb in region_colors.items():
        best_c = min(centroids, key=lambda c: math.hypot(rgb[0]-c[0], rgb[1]-c[1], rgb[2]-c[2]))
        custom_colors[str(rid)] = rgb_to_hex(best_c)


def mirror_block_geometry(block_data):
    root = block_data.tree.regions.get(block_data.tree.root_id)
    if not root:
        return
    xs = [p[0] for p in root.polygon]
    cx = (min(xs) + max(xs)) / 2.0
    for r in block_data.tree.regions.values():
        r.polygon = [(2.0 * cx - p[0], p[1]) for p in r.polygon]
    block_data.tree.sanitize_tree()


def translate_block_geometry(block_data, dx, dy):
    """Shift every region (leaf AND internal) by (dx, dy) so the managed tree
    stays internally consistent. Mirrors the all-regions approach used by
    resize/mirror."""
    for r in block_data.tree.regions.values():
        r.polygon = [(p[0] + dx, p[1] + dy) for p in r.polygon]


def scale_block_geometry(block_data, sx, sy):
    """Scale every region (leaf AND internal) about the origin (0, 0). Call
    normalize_block_to_origin first if you want to scale about the block's own
    top-left corner."""
    for r in block_data.tree.regions.values():
        r.polygon = [(p[0] * sx, p[1] * sy) for p in r.polygon]


def block_bounds(block_data):
    """Return (min_x, min_y, max_x, max_y) of the block's leaf geometry, or
    None if the block is empty."""
    pts = [p for r in block_data.tree.leaf_regions() for p in r.polygon]
    if not pts:
        return None
    return (
        min(p[0] for p in pts),
        min(p[1] for p in pts),
        max(p[0] for p in pts),
        max(p[1] for p in pts),
    )


def normalize_block_to_origin(block_data):
    """Translate the block so its top-left corner sits at (0, 0). Returns the
    block's (width_px, height_px)."""
    b = block_bounds(block_data)
    if b is None:
        return (0.0, 0.0)
    min_x, min_y, max_x, max_y = b
    translate_block_geometry(block_data, -min_x, -min_y)
    return (max_x - min_x, max_y - min_y)


def block_data_to_standalone_svg(block_data, name=None):
    """Render a BlockData into a self-contained SVG root element (lxml) that
    carries the embedded tree JSON, so it round-trips perfectly via
    find_fpp_group / extract_block_data_from_svg_root."""
    b = block_bounds(block_data)
    if b is None:
        min_x = min_y = 0.0
        w = h = PX_PER_INCH
    else:
        min_x, min_y, max_x, max_y = b
        w, h = (max_x - min_x), (max_y - min_y)

    nsmap = {None: SVG_NS, "inkscape": INKSCAPE_NS, "sodipodi": SODIPODI_NS}
    svg = etree.Element("{%s}svg" % SVG_NS, nsmap=nsmap)
    svg.set("width", f"{w}")
    svg.set("height", f"{h}")
    svg.set("viewBox", f"{min_x} {min_y} {w} {h}")
    svg.set("data-quilttools-block", "1")
    if name:
        svg.set("data-quilttools-name", str(name))
        title = etree.SubElement(svg, "{%s}title" % SVG_NS)
        title.text = str(name)

    svg.append(build_fpp_layer(block_data))
    return svg


def extract_block_data_from_svg_root(root):
    """Pull a BlockData out of any parsed SVG that contains a Quilt Tools FPP
    block (i.e. a <desc id='fpp-tree-data-quilttools'>). Returns None if the
    SVG is not a native Quilt Tools block."""
    for desc in root.iter("{%s}desc" % SVG_NS):
        if desc.get("id") == FPP_DATA_TAG_ID and desc.text:
            try:
                return BlockData.from_json(desc.text)
            except Exception:
                return None
    return None


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
    # Check bounding box overlap first
    if max_x1 <= min_x2 + 1.0 or min_x1 >= max_x2 - 1.0 or max_y1 <= min_y2 + 1.0 or min_y1 >= max_y2 - 1.0:
        return False

    # Check edge intersections
    n1, n2 = len(poly1), len(poly2)
    for i in range(n1):
        p1a, p1b = poly1[i], poly1[(i + 1) % n1]
        for j in range(n2):
            p2a, p2b = poly2[j], poly2[(j + 1) % n2]
            res = segment_intersect(p1a, p1b, p2a, p2b)
            if res:
                t, pt = res
                # Check that intersection is not right at the endpoints (within tolerance)
                if 0.02 < t < 0.98:
                    return True

    # Check if one centroid is inside the other
    c1 = polygon_centroid(poly1)
    if point_in_polygon(c1, poly2):
        return True
    c2 = polygon_centroid(poly2)
    if point_in_polygon(c2, poly1):
        return True

    return False


def calculate_section_sewing_order(block_data):
    tree = block_data.tree
    regions = tree.leaf_regions()
    if not regions:
        return [], False

    # Group regions by section prefix
    sec_regions = {}
    for r in regions:
        match = re.match(r"^([A-Za-z_]+)", r.label)
        prefix = match.group(1).upper() if match else "A"
        if prefix not in sec_regions:
            sec_regions[prefix] = []
        sec_regions[prefix].append(r)

    # Compute unified polygons for each section
    section_polys = {}
    section_areas = {}
    for prefix, grp in sec_regions.items():
        polys = [r.polygon for r in grp]
        union = get_polygon_union(polys)
        if union:
            section_polys[prefix] = union
            section_areas[prefix] = polygon_area(union)

    section_names = list(section_polys.keys())
    if len(section_names) <= 1:
        return [], False

    has_warning = [False]

    def solve_assembly(names):
        if len(names) <= 1:
            return list(names)[0]

        best_split = None
        best_score = -1.0

        for name in names:
            poly = section_polys[name]
            n = len(poly)
            for i in range(n):
                p1, p2 = poly[i], poly[(i + 1) % n]
                d = vec_sub(p2, p1)
                l_d = vec_len(d)
                if l_d < 1e-4:
                    continue
                nd = (d[0] / l_d, d[1] / l_d)

                cuts = False
                g1, g2 = [], []
                for other in names:
                    other_poly = section_polys[other]
                    side_pos = False
                    side_neg = False
                    for pt in other_poly:
                        v = vec_sub(pt, p1)
                        dist = nd[0]*v[1] - nd[1]*v[0]
                        if dist > 1.5:
                            side_pos = True
                        elif dist < -1.5:
                            side_neg = True

                    if side_pos and side_neg:
                        cuts = True
                        break
                    elif side_pos:
                        g1.append(other)
                    elif side_neg:
                        g2.append(other)
                    else:
                        g1.append(other)

                if not cuts and g1 and g2:
                    area_g1 = sum(section_areas[n] for n in g1)
                    area_g2 = sum(section_areas[n] for n in g2)
                    total_area = area_g1 + area_g2
                    balance = 1.0 - abs(area_g1 - area_g2) / total_area
                    score = l_d * balance
                    if score > best_score:
                        best_score = score
                        best_split = (g1, g2)

        if best_split:
            g1, g2 = best_split
            return (solve_assembly(g1), solve_assembly(g2))
        else:
            has_warning[0] = True
            names_list = sorted(list(names))
            g1 = names_list[:len(names_list)//2]
            g2 = names_list[len(names_list)//2:]
            return (solve_assembly(g1), solve_assembly(g2))

    split_tree = solve_assembly(section_names)

    steps = []
    def flatten_tree(node):
        if isinstance(node, str):
            return node
        left, right = node
        l_name = flatten_tree(left)
        r_name = flatten_tree(right)
        joined_name = "".join(sorted(list(set(l_name + r_name))))
        steps.append(f"Join {l_name} + {r_name} -> {joined_name}")
        return joined_name

    flatten_tree(split_tree)
    return steps, has_warning[0]

