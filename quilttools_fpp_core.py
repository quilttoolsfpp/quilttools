#!/usr/bin/env python3
import json
import math
import re

import inkex
from lxml import etree

from quilttools_geometry import *
from quilttools_svg import *



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
        self.curves = []
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
        # 1. Pre-snap check: find which leaf regions are touched by the original unsnapped line segment
        raw_angle_unsnapped = angle_of_line(draw_p1, draw_p2)
        rad_unsnapped = math.radians(raw_angle_unsnapped)
        ray_unsnapped = line_from_point_angle(draw_p1, raw_angle_unsnapped)

        def dist_along_ray_unsnapped(p):
            return (p[0] - ray_unsnapped[0][0]) * math.cos(rad_unsnapped) + (p[1] - ray_unsnapped[0][1]) * math.sin(
                rad_unsnapped
            )

        t_unsnapped_draw1 = dist_along_ray_unsnapped(draw_p1)
        t_unsnapped_draw2 = dist_along_ray_unsnapped(draw_p2)
        t_unsnapped_draw_min = min(t_unsnapped_draw1, t_unsnapped_draw2)
        t_unsnapped_draw_max = max(t_unsnapped_draw1, t_unsnapped_draw2)

        touched_before_snap = set()
        for region in self.leaf_regions():
            if limit_to_region_id and region.id != limit_to_region_id:
                continue
            clipped = clip_line_to_polygon(ray_unsnapped[0], ray_unsnapped[1], region.polygon)
            if not clipped:
                continue
            t_cut1, t_cut2 = dist_along_ray_unsnapped(clipped[0]), dist_along_ray_unsnapped(clipped[1])
            overlap_min = max(t_unsnapped_draw_min, min(t_cut1, t_cut2))
            overlap_max = min(t_unsnapped_draw_max, max(t_cut1, t_cut2))
            if overlap_max - overlap_min > 0.5:
                touched_before_snap.add(region.id)

        # 2. Snapped angle computation
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
            # Apply original touch restriction
            if region.id not in touched_before_snap:
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
        committed_nodes = []
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
            committed_nodes.append((region, child_a.id, child_b.id))
            cut_count += 1

        self.sanitize_tree()
        actual_cuts = 0
        for parent, ca_id, cb_id in committed_nodes:
            if not parent.is_leaf():
                actual_cuts += 1
        
        if actual_cuts > 0:
            self.rebuild_alphabet()
            
        return actual_cuts

    def multi_circle_cut(self, center, radius, limit_to_region_id=None, subdivisions=32):
        # 1. Identify which leaf regions are intersected by the circle
        regions_to_cut = []
        for region in self.leaf_regions():
            if limit_to_region_id and region.id != limit_to_region_id:
                continue
            intersections = find_circle_intersections(region.polygon, center, radius)
            intersections = deduplicate_intersections(intersections)
            if len(intersections) == 2:
                regions_to_cut.append((region, intersections))
                
        if not regions_to_cut:
            return 0
            
        committed_nodes = []
        cut_count = 0
        
        for region, intersections in regions_to_cut:
            # Sort intersections by edge index, then t parameter
            intersections.sort(key=lambda x: (x[0], x[1]))
            
            a_idx, t1, I1 = intersections[0]
            b_idx, t2, I2 = intersections[1]
            
            # If on the same edge, make sure t1 < t2
            if a_idx == b_idx and t1 > t2:
                I1, I2 = I2, I1
                t1, t2 = t2, t1
                
            # Get angles for arc interpolation
            theta1 = math.atan2(I1[1] - center[1], I1[0] - center[0])
            theta2 = math.atan2(I2[1] - center[1], I2[0] - center[0])
            
            # Generate CCW and CW arcs
            arc_ccw = generate_circle_arc(center, radius, theta1, theta2, ccw=True, subdivisions=subdivisions)
            arc_cw = generate_circle_arc(center, radius, theta1, theta2, ccw=False, subdivisions=subdivisions)
            
            # Determine which arc is inside the polygon
            xc, yc = center
            t2_ccw = theta2 if theta2 >= theta1 else theta2 + 2 * math.pi
            theta_mid_ccw = theta1 + 0.5 * (t2_ccw - theta1)
            midpoint_ccw = (xc + radius * math.cos(theta_mid_ccw), yc + radius * math.sin(theta_mid_ccw))
            
            if point_in_polygon(midpoint_ccw, region.polygon):
                arc = arc_ccw
            else:
                arc = arc_cw
                
            # Split parent polygon into Chain 1 and Chain 2
            poly = region.polygon
            n_p = len(poly)
            
            # Chain 1: from I1 to I2 along the polygon boundary
            if a_idx == b_idx:
                chain1 = [I1, I2]
            else:
                chain1 = [I1]
                idx = (a_idx + 1) % n_p
                while True:
                    chain1.append(poly[idx])
                    if idx == b_idx:
                        break
                    idx = (idx + 1) % n_p
                chain1.append(I2)
                
            # Chain 2: from I2 to I1 along the polygon boundary
            if a_idx == b_idx:
                chain2 = [I2]
                idx = (b_idx + 1) % n_p
                while True:
                    chain2.append(poly[idx])
                    if idx == a_idx:
                        break
                    idx = (idx + 1) % n_p
                chain2.append(I1)
            else:
                chain2 = [I2]
                idx = (b_idx + 1) % n_p
                while True:
                    chain2.append(poly[idx])
                    if idx == a_idx:
                        break
                    idx = (idx + 1) % n_p
                chain2.append(I1)
                
            # Build child polygons
            poly_a = chain1 + arc[::-1][1:-1]
            poly_b = chain2 + arc[1:-1]
            
            poly_a = simplify_polygon(poly_a)
            poly_b = simplify_polygon(poly_b)
            
            if (
                len(poly_a) < 3
                or len(poly_b) < 3
                or polygon_area(poly_a) < 0.1
                or polygon_area(poly_b) < 0.1
            ):
                continue
            
            # Create child regions
            child_a = Region(poly_a, label=region.label + "a", parent_id=region.id)
            child_b = Region(poly_b, label=region.label + "b", parent_id=region.id)
            
            self.regions[child_a.id] = child_a
            self.regions[child_b.id] = child_b
            region.children = [child_a.id, child_b.id]
            region.split_boundary = True
            
            # Register curve boundary
            if not hasattr(self, "curves"):
                self.curves = []
            self.curves.append(arc)
            
            committed_nodes.append((region, child_a.id, child_b.id))
            cut_count += 1
            
        self.sanitize_tree()
        actual_cuts = 0
        for parent, ca_id, cb_id in committed_nodes:
            if not parent.is_leaf():
                actual_cuts += 1
                
        if actual_cuts > 0:
            self.rebuild_alphabet()
            
        return actual_cuts


    def multi_path_cut(self, path_points, limit_to_region_id=None):
        if len(path_points) < 2:
            return 0

        # Extend the start and end of the path slightly to ensure they cross the boundaries
        # Extend start point
        d_start = vec_sub(path_points[0], path_points[1])
        l_start = math.hypot(*d_start)
        if l_start > EPSILON:
            extended_start = (path_points[0][0] + d_start[0] * 10.0 / l_start, path_points[0][1] + d_start[1] * 10.0 / l_start)
        else:
            extended_start = path_points[0]

        # Extend end point
        d_end = vec_sub(path_points[-1], path_points[-2])
        l_end = math.hypot(*d_end)
        if l_end > EPSILON:
            extended_end = (path_points[-1][0] + d_end[0] * 10.0 / l_end, path_points[-1][1] + d_end[1] * 10.0 / l_end)
        else:
            extended_end = path_points[-1]

        # Build extended path
        ext_path = [extended_start] + list(path_points[1:-1]) + [extended_end]

        regions_to_cut = []
        for region in self.leaf_regions():
            if limit_to_region_id and region.id != limit_to_region_id:
                continue

            intersections = []
            n_poly = len(region.polygon)
            n_path = len(ext_path)

            for i in range(n_poly):
                poly_p1 = region.polygon[i]
                poly_p2 = region.polygon[(i + 1) % n_poly]

                for j in range(n_path - 1):
                    path_p1 = ext_path[j]
                    path_p2 = ext_path[j + 1]

                    res = segment_intersect(poly_p1, poly_p2, path_p1, path_p2)
                    if res:
                        t, I = res
                        d_path = vec_sub(path_p2, path_p1)
                        l_path_sq = d_path[0]**2 + d_path[1]**2
                        v_diff = vec_sub(I, path_p1)
                        u = (v_diff[0] * d_path[0] + v_diff[1] * d_path[1]) / l_path_sq if l_path_sq > EPSILON else 0.0
                        intersections.append((i, t, I, j + u))

            intersections = deduplicate_intersections(intersections)

            if len(intersections) == 2:
                regions_to_cut.append((region, intersections))

        if not regions_to_cut:
            return 0

        committed_nodes = []
        cut_count = 0

        for region, intersections in regions_to_cut:
            intersections.sort(key=lambda x: x[3])

            a_idx, t1, I1, p1 = intersections[0]
            b_idx, t2, I2, p2 = intersections[1]

            j1 = int(math.floor(p1))
            j2 = int(math.floor(p2))

            arc = [I1]
            for idx in range(j1 + 1, j2 + 1):
                if idx < len(ext_path):
                    arc.append(ext_path[idx])
            arc.append(I2)

            poly = region.polygon
            n_p = len(poly)

            poly_intersections = sorted(intersections, key=lambda x: (x[0], x[1]))
            pa_idx = poly_intersections[0][0]
            pb_idx = poly_intersections[1][0]
            pt1 = poly_intersections[0][1]
            pt2 = poly_intersections[1][1]
            pI1 = poly_intersections[0][2]
            pI2 = poly_intersections[1][2]

            if pa_idx == pb_idx and pt1 > pt2:
                pI1, pI2 = pI2, pI1
                pt1, pt2 = pt2, pt1

            if pa_idx == pb_idx:
                chain1 = [pI1, pI2]
            else:
                chain1 = [pI1]
                idx = (pa_idx + 1) % n_p
                while True:
                    chain1.append(poly[idx])
                    if idx == pb_idx:
                        break
                    idx = (idx + 1) % n_p
                chain1.append(pI2)

            chain2 = [pI2]
            idx = (pb_idx + 1) % n_p
            while True:
                chain2.append(poly[idx])
                if idx == pa_idx:
                    break
                idx = (idx + 1) % n_p
            chain2.append(pI1)

            if pt_dist(I1, pI1) < 1e-4:
                poly_a = chain1 + arc[::-1][1:-1]
                poly_b = chain2 + arc[1:-1]
            else:
                poly_a = chain1 + arc[1:-1]
                poly_b = chain2 + arc[::-1][1:-1]

            poly_a = simplify_polygon(poly_a)
            poly_b = simplify_polygon(poly_b)

            if (
                len(poly_a) < 3
                or len(poly_b) < 3
                or polygon_area(poly_a) < 0.1
                or polygon_area(poly_b) < 0.1
            ):
                continue

            child_a = Region(poly_a, label=region.label + "a", parent_id=region.id)
            child_b = Region(poly_b, label=region.label + "b", parent_id=region.id)

            self.regions[child_a.id] = child_a
            self.regions[child_b.id] = child_b
            region.children = [child_a.id, child_b.id]
            region.split_boundary = True

            if not hasattr(self, "curves"):
                self.curves = []
            self.curves.append(arc)

            committed_nodes.append((region, child_a.id, child_b.id))
            cut_count += 1

        self.sanitize_tree()
        actual_cuts = 0
        for parent, ca_id, cb_id in committed_nodes:
            if not parent.is_leaf():
                actual_cuts += 1

        if actual_cuts > 0:
            self.rebuild_alphabet()

        return actual_cuts


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

        if hasattr(self, "curves") and self.curves:
            i, j, _ = match
            sa, sb = p1[i], p1[(i + 1) % len(p1)]
            for curve in self.curves:
                n_c = len(curve)
                for idx_c in range(n_c - 1):
                    c1, c2 = curve[idx_c], curve[idx_c + 1]
                    if (pt_dist(sa, c1) < 1.5 and pt_dist(sb, c2) < 1.5) or \
                       (pt_dist(sa, c2) < 1.5 and pt_dist(sb, c1) < 1.5):
                        return False, "Selected pieces share a curved boundary and cannot be healed."

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
                    # Gather all leaf descendants of node_id to check if they are all selected
                    descendant_leaves = []
                    def gather_leaves(nid):
                        node = self.regions[nid]
                        if node.is_leaf():
                            descendant_leaves.append(nid)
                        else:
                            for cid in node.children:
                                gather_leaves(cid)
                    gather_leaves(node_id)
                    
                    if not all(dl in selected_leaf_ids for dl in descendant_leaves):
                        return (
                            False,
                            "Cannot heal across an initial structural grid boundary unless all pieces on both sides of the boundary are selected to be healed.",
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

    def _selection_contains_curve(self, selected_leaf_ids):
        if not hasattr(self, "curves") or not self.curves:
            return False
        for nid in selected_leaf_ids:
            if nid not in self.regions:
                continue
            poly = self.regions[nid].polygon
            n = len(poly)
            for i in range(n):
                p1, p2 = poly[i], poly[(i + 1) % n]
                for curve in self.curves:
                    n_c = len(curve)
                    for idx_c in range(n_c - 1):
                        c1, c2 = curve[idx_c], curve[idx_c + 1]
                        if (pt_dist(p1, c1) < 1.5 and pt_dist(p2, c2) < 1.5) or \
                           (pt_dist(p1, c2) < 1.5 and pt_dist(p2, c1) < 1.5):
                            return True
        return False

    def virtual_sewing_validator(self, selected_leaf_ids, force_start_id=None):
        """Guillotine Convex Separability Check - Normalized absolute pixel tolerance"""
        if not selected_leaf_ids:
            return False, []
        if len(selected_leaf_ids) == 1:
            return True, list(selected_leaf_ids)

        if self._selection_contains_curve(selected_leaf_ids):
            if force_start_id:
                # We are setting a piece as first; preserve the existing label sequence and rotate/reverse it to find the most sewable contiguous order
                def get_label_num(nid):
                    label = self.regions[nid].label
                    if not label or not isinstance(label, str):
                        return 999999
                    m = re.search(r"\d+", label)
                    return int(m.group()) if m else 999999

                seq = sorted(list(selected_leaf_ids), key=get_label_num)
                if force_start_id in seq:
                    # Candidate 1: Rotated forward
                    idx = seq.index(force_start_id)
                    seq_rot = seq[idx:] + seq[:idx]

                    # Candidate 2: Reversed and rotated
                    seq_rev = seq[::-1]
                    idx_rev = seq_rev.index(force_start_id)
                    seq_rev_rot = seq_rev[idx_rev:] + seq_rev[:idx_rev]

                    # Calculate physical path cost (sum of adjacent centroid distances) to avoid unsewable jumps
                    centroids = {}
                    for nid in selected_leaf_ids:
                        centroids[nid] = polygon_centroid(self.regions[nid].polygon)

                    def get_cost(s):
                        return sum(pt_dist(centroids[s[i]], centroids[s[i+1]]) for i in range(len(s)-1))

                    cost_rot = get_cost(seq_rot)
                    cost_rev = get_cost(seq_rev_rot)

                    seq = seq_rot if cost_rot < cost_rev else seq_rev_rot

                return True, seq
            else:
                # Fully Auto-Labeling; return in ID-sorted creation order (original behavior)
                return True, sorted(list(selected_leaf_ids))


        polygons = {nid: self.regions[nid].polygon for nid in selected_leaf_ids}

        # Physical adjacency: a piece can only be sewn onto the unit that is
        # already assembled if it shares a seam of positive length with it.
        # Straight-line separability alone accepts impossible orders, e.g.
        # "sewing" the two disconnected legs of a U-shaped section together.
        ids_list = list(selected_leaf_ids)
        adjacency = {nid: set() for nid in ids_list}
        for a_idx in range(len(ids_list)):
            for b_idx in range(a_idx + 1, len(ids_list)):
                a_id, b_id = ids_list[a_idx], ids_list[b_idx]
                if polygons_share_edge(polygons[a_id], polygons[b_id]):
                    adjacency[a_id].add(b_id)
                    adjacency[b_id].add(a_id)

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

                # The piece must touch the unit it will be sewn onto.
                if not (adjacency[test_id] & rest_ids):
                    continue

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

        # Adopt orphan leaves. Heal operations can leave a region parentless
        # and unreachable from the root; such leaves are invisible to the
        # structural-group walk, so they would never be partitioned, merged
        # or relabelled (and their stale labels can collide with fresh ones).
        # Chain them onto the root with non-boundary internals so they join
        # the top structural group and the tree is well-formed again.
        if self.root_id is not None:
            reachable = set()
            stack = [self.root_id]
            while stack:
                nid = stack.pop()
                if nid in reachable or nid not in self.regions:
                    continue
                reachable.add(nid)
                stack.extend(self.regions[nid].children)
            orphans = [r.id for r in self.leaf_regions() if r.id not in reachable]
            for oid in orphans:
                old_root_id = self.root_id
                new_root = Region(list(self.regions[old_root_id].polygon))
                new_root.children = [old_root_id, oid]
                new_root.split_boundary = False
                self.regions[new_root.id] = new_root
                self.regions[old_root_id].parent_id = new_root.id
                self.regions[oid].parent_id = new_root.id
                self.root_id = new_root.id

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

        # Split each section into connected components to ensure physical sewability
        def polygons_adjacent(poly_a, poly_b, tol=1.5):
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
                    
                    v_q1 = (q1[0] - p1[0], q1[1] - p1[1])
                    dist_q1 = u_a[0] * v_q1[1] - u_a[1] * v_q1[0]
                    if abs(dist_q1) > tol:
                        continue
                        
                    v_q2 = (q2[0] - p1[0], q2[1] - p1[1])
                    dist_q2 = u_a[0] * v_q2[1] - u_a[1] * v_q2[0]
                    if abs(dist_q2) > tol:
                        continue
                        
                    t1 = v_q1[0] * u_a[0] + v_q1[1] * u_a[1]
                    t2 = v_q2[0] * u_a[0] + v_q2[1] * u_a[1]
                    
                    min_t, max_t = min(t1, t2), max(t1, t2)
                    overlap_min = max(0.0, min_t)
                    overlap_max = min(len_a, max_t)
                    if (overlap_max - overlap_min) >= tol:
                        return True
            return False

        def split_into_connected_components(sec_ids):
            visited = set()
            components = []
            for rid in sec_ids:
                if rid in visited:
                    continue
                comp = []
                queue = [rid]
                visited.add(rid)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    curr_poly = self.regions[curr].polygon
                    for other in sec_ids:
                        if other not in visited:
                            if polygons_adjacent(curr_poly, self.regions[other].polygon):
                                visited.add(other)
                                queue.append(other)
                comp.sort(key=lambda x: sec_ids.index(x))
                components.append(comp)
            return components

        final_sections = []
        for sec_ids in sections:
            final_sections.extend(split_into_connected_components(sec_ids))
        sections = final_sections

        # ------------------------------------------------------------------
        # Merge pass: the guillotine slicer above is greedy — it recurses on
        # the first clean separating line it finds and never reconsiders, so
        # it can shear off 1-2 piece fragments that would sew perfectly well
        # into a neighbouring section. Absorb such fragments, but ONLY when
        # the result stays Y-seam free at both levels:
        #   1. the merged piece list has a valid straight-seam piecing order
        #      (virtual_sewing_validator), and
        #   2. the block's section-to-section assembly still solves without
        #      warnings (calculate_section_sewing_order).
        # Merges never cross structural-group boundaries (deliberate
        # split_boundary marks, e.g. from healing) and never involve curved
        # selections, which the validator cannot genuinely verify.
        MAX_FRAGMENT_PIECES = 2

        group_of = {}
        for gi, grp in enumerate(groups):
            for nid in grp:
                group_of[nid] = gi

        auto_ids = {nid for sec in sections for nid in sec}
        saved_labels = {
            r.id: r.label for r in self.leaf_regions() if r.id in auto_ids
        }

        def _provisional_prefixes(count, taken):
            out = []
            k = 0
            while len(out) < count:
                letter = ""
                n = k
                while True:
                    letter = chr(65 + n % 26) + letter
                    n = n // 26 - 1
                    if n < 0:
                        break
                k += 1
                if letter.upper() not in taken:
                    out.append(letter)
            return out

        _union_cache = {}

        def _union_sound(sec_ids):
            """The section-assembly solver works on get_polygon_union of each
            section's pieces — a union that silently drops pieces (no exact
            shared edge found) makes that check meaningless. A merge may only
            be trusted when every section's union truly covers its pieces."""
            key = frozenset(sec_ids)
            if key not in _union_cache:
                polys = [self.regions[nid].polygon for nid in sec_ids]
                total = sum(polygon_area(p) for p in polys)
                union = get_polygon_union(polys)
                ua = polygon_area(union) if union else 0.0
                _union_cache[key] = total <= 0 or abs(ua - total) < max(
                    0.01 * total, 1.0
                )
            return _union_cache[key]

        def _assembly_clean(trial_sections):
            # No verification without sound geometry: if any section union
            # is unreliable the solver is blind, so refuse the merge.
            for sec in trial_sections:
                if not _union_sound(sec):
                    return False
            taken = set()
            for r in self.leaf_regions():
                if r.id not in auto_ids:
                    m = re.match(r"^([A-Za-z_]+)", r.label)
                    if m:
                        taken.add(m.group(1).upper())
            prefixes = _provisional_prefixes(len(trial_sections), taken)
            for prefix, sec in zip(prefixes, trial_sections):
                for i, nid in enumerate(sec):
                    self.regions[nid].label = f"{prefix}{i + 1}"
            _, warn = calculate_section_sewing_order(BlockData(self))
            return not warn

        def _mergeable_sequence(s1, s2):
            if group_of.get(s1[0]) != group_of.get(s2[0]):
                return None
            if not any(
                polygons_adjacent(self.regions[a].polygon, self.regions[b].polygon)
                for a in s1
                for b in s2
            ):
                return None
            union_ids = s1 + s2
            if self._selection_contains_curve(union_ids):
                return None
            ok, seq = self.virtual_sewing_validator(union_ids)
            return seq if ok else None

        merged = True
        while merged:
            merged = False
            order = sorted(
                range(len(sections)),
                key=lambda k: (
                    len(sections[k]),
                    sum(polygon_area(self.regions[n].polygon) for n in sections[k]),
                ),
            )
            for oi in order:
                if len(sections[oi]) > MAX_FRAGMENT_PIECES:
                    continue
                candidates = []
                for oj in range(len(sections)):
                    if oj == oi:
                        continue
                    seq = _mergeable_sequence(sections[oi], sections[oj])
                    if seq is not None:
                        candidates.append((len(sections[oj]), oj, seq))
                # Prefer the smallest valid host so sections stay compact.
                candidates.sort()
                for _, oj, seq in candidates:
                    trial = [
                        s for k, s in enumerate(sections) if k not in (oi, oj)
                    ]
                    trial.append(seq)
                    if _assembly_clean(trial):
                        sections = trial
                        merged = True
                        break
                if merged:
                    break

        # The assembly checks leave provisional labels behind; restore the
        # originals so the preserve_manual letter scan below stays accurate.
        for nid, lbl in saved_labels.items():
            self.regions[nid].label = lbl

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

        for prefix, grp in groups.items():
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
                    self.regions[nid].label = f"{prefix}{i + 1}"
            else:
                grp_sorted = sorted(grp, key=lambda n: (polygon_centroid(n.polygon)[1], polygon_centroid(n.polygon)[0]))
                for i, n in enumerate(grp_sorted):
                    n.label = f"{prefix}{i + 1}"

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
            "curves": self.curves,
        }

    @staticmethod
    def from_dict(d):
        tree = RegionTree()
        tree.root_id = d["root_id"]
        tree.curves = d.get("curves", [])
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

    def is_exact_library_block(self):
        if not self.prefs.get("is_library_block"):
            return False
        orig_sig = self.prefs.get("original_signature")
        if not orig_sig:
            return False
        current_sig = sorted([r.id for r in self.tree.leaf_regions()])
        return current_sig == orig_sig

    @staticmethod
    def from_json(text):
        data = json.loads(text)
        if "tree" in data and "prefs" in data:
            return BlockData(RegionTree.from_dict(data["tree"]), data["prefs"])
        else:
            return BlockData(RegionTree.from_dict(data))


