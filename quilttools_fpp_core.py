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
            if are_collinear(p_prev, p_curr, p_next, tol=0.1):
                poly.pop(i)
                changed = True
                break
    return poly


def edges_match(e1, e2, tol=1.5):
    if pt_dist(e1[0], e1[1]) < 2.0 or pt_dist(e2[0], e2[1]) < 2.0:
        return False
    match_anti = pt_dist(e1[0], e2[1]) < tol and pt_dist(e1[1], e2[0]) < tol
    match_para = pt_dist(e1[0], e2[0]) < tol and pt_dist(e1[1], e2[1]) < tol
    return match_anti or match_para


def merge_polygons(poly1, poly2, e1_idx, e2_idx):
    n1, n2 = len(poly1), len(poly2)
    e1_a, e1_b = poly1[e1_idx], poly1[(e1_idx + 1) % n1]
    e2_a, e2_b = poly2[e2_idx], poly2[(e2_idx + 1) % n2]
    is_anti = pt_dist(e1_a, e2_b) < 1.5 and pt_dist(e1_b, e2_a) < 1.5
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


def get_polygon_union(polygons):
    if not polygons:
        return []
    if len(polygons) == 1:
        return simplify_polygon(polygons[0])

    current = polygons[0]
    remaining = polygons[1:]

    changed = True
    while changed and remaining:
        changed = False
        for next_poly in remaining:
            merged = None
            for i in range(len(current)):
                e1 = (current[i], current[(i + 1) % len(current)])
                for j in range(len(next_poly)):
                    e2 = (next_poly[j], next_poly[(j + 1) % len(next_poly)])
                    if edges_match(e1, e2, tol=1.5):
                        merged = merge_polygons(current, next_poly, i, j)
                        break
                if merged:
                    break
            if merged:
                current = merged
                remaining.remove(next_poly)
                changed = True
                break

    if remaining:
        return simplify_polygon(current)
    return simplify_polygon(current)


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
        """Purges micro-slivers and collapses redundant/dead branches."""
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

        # Geometric Validation
        merged_poly = None
        for i in range(len(p1)):
            e1 = (p1[i], p1[(i + 1) % len(p1)])
            for j in range(len(p2)):
                e2 = (p2[j], p2[(j + 1) % len(p2)])
                if edges_match(e1, e2, tol=1.5):
                    merged_poly = merge_polygons(p1, p2, i, j)
                    break
            if merged_poly:
                break

        if not merged_poly:
            return False, "Selected pieces do not share an identical, straight edge."

        # Create the new orphan region first
        new_region = Region(merged_poly, label=r1.label)

        # Track the parents before deleting the children
        parents_to_check = set()
        if r1.parent_id in self.regions:
            parents_to_check.add(r1.parent_id)
        if r2.parent_id in self.regions:
            parents_to_check.add(r2.parent_id)

        # Remove the old pieces from their parents and the tree
        for old_r in [r1, r2]:
            if old_r.parent_id and old_r.parent_id in self.regions:
                parent = self.regions[old_r.parent_id]
                if old_r.id in parent.children:
                    parent.children.remove(old_r.id)
            del self.regions[old_r.id]

        # Add the new region to the tree
        self.regions[new_region.id] = new_region

        # DUPLICATE NODE RESOLUTION:
        # Check if the new orphan perfectly matches a newly emptied parent
        duplicate_parent_id = None
        for pid in parents_to_check:
            parent = self.regions[pid]
            # If the parent is now a leaf (0 children)
            if len(parent.children) == 0:
                # Check geometric similarity
                area_diff = abs(parent.area_sq_in() - new_region.area_sq_in())
                cx_p, cy_p = polygon_centroid(parent.polygon)
                cx_n, cy_n = polygon_centroid(new_region.polygon)
                dist = math.hypot(cx_p - cx_n, cy_p - cy_n)

                # If area and centroid match, it's the exact same piece of fabric
                if area_diff < 0.01 and dist < 1.0:
                    duplicate_parent_id = pid
                    break

        if duplicate_parent_id:
            # Match found! The orphan is redundant. Delete it and restore the parent.
            parent = self.regions[duplicate_parent_id]
            parent.label = r1.label
            parent.polygon = new_region.polygon  # Inherit the clean, merged geometry
            del self.regions[new_region.id]
            msg = "Heal Successful. Redundant duplicate prevented."
        else:
            # No match found, the orphan stays as a valid cross-branch piece
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
        if not selected_leaf_ids:
            return False, []
        if len(selected_leaf_ids) == 1:
            return True, list(selected_leaf_ids)
        start_candidates = (
            [force_start_id]
            if force_start_id
            else sorted(
                list(selected_leaf_ids), key=lambda nid: self.regions[nid].area_sq_in()
            )
        )

        for start_id in start_candidates:
            seq = [start_id]
            current_poly = self.regions[start_id].polygon
            remaining = set(selected_leaf_ids) - {start_id}
            while remaining:
                found_next = False
                for next_id in list(remaining):
                    p_next = self.regions[next_id].polygon
                    merged = None
                    for i in range(len(current_poly)):
                        e1 = (
                            current_poly[i],
                            current_poly[(i + 1) % len(current_poly)],
                        )
                        for j in range(len(p_next)):
                            e2 = (p_next[j], p_next[(j + 1) % len(p_next)])
                            if edges_match(e1, e2, tol=1.5):
                                merged = merge_polygons(current_poly, p_next, i, j)
                                break
                        if merged:
                            break
                    if merged:
                        current_poly = merged
                        seq.append(next_id)
                        remaining.remove(next_id)
                        found_next = True
                        break
                if not found_next:
                    break
            if not remaining:
                return True, seq
        return False, []

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

        sections = []
        while remaining_ids:
            start_id = min(
                remaining_ids, key=lambda nid: self.regions[nid].area_sq_in()
            )
            seq = [start_id]
            current_poly = self.regions[start_id].polygon
            remaining_ids.remove(start_id)

            changed = True
            while changed:
                changed = False
                for next_id in list(remaining_ids):
                    if self.separated_by_boundary(start_id, next_id):
                        continue
                    p_next = self.regions[next_id].polygon
                    merged = None
                    for i in range(len(current_poly)):
                        e1 = (
                            current_poly[i],
                            current_poly[(i + 1) % len(current_poly)],
                        )
                        for j in range(len(p_next)):
                            e2 = (p_next[j], p_next[(j + 1) % len(p_next)])
                            if edges_match(e1, e2, tol=1.5):
                                merged = merge_polygons(current_poly, p_next, i, j)
                                break
                        if merged:
                            break
                    if merged:
                        test_seq = seq + [next_id]
                        is_valid, _ = self.virtual_sewing_validator(test_seq)
                        if is_valid:
                            current_poly = merged
                            seq.append(next_id)
                            remaining_ids.remove(next_id)
                            changed = True
                            break
            sections.append(seq)

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

    for idx, region in enumerate(sorted(tree.leaf_regions(), key=lambda r: r.label)):
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
                etree.SubElement(g, "{%s}path" % SVG_NS, **sa_attribs)

        fill_color = custom_colors.get(str(region.id))
        if not fill_color:
            fill_color = get_color_for_label(region.label, color_mode, idx)

        path_el = etree.SubElement(
            g,
            "{%s}path" % SVG_NS,
            d=region.path_d(),
            id=f"region-{region.label}",
            style=f"fill:{fill_color};fill-opacity:0.80;stroke:#222222;stroke-width:1.0;stroke-linejoin:round",
        )
        path_el.set(FPP_REGION_ATTR, str(region.id))

        cx, cy = polygon_centroid(region.polygon)
        txt = etree.SubElement(
            g,
            "{%s}text" % SVG_NS,
            x=f"{cx:.2f}",
            y=f"{cy:.2f}",
            style="font-size:11px;font-family:sans-serif;text-anchor:middle;dominant-baseline:middle;fill:#333333;pointer-events:none",
        )
        txt.text = region.label

    desc = etree.SubElement(g, "{%s}desc" % SVG_NS, id=FPP_DATA_TAG_ID)
    desc.text = block_data.to_json()
