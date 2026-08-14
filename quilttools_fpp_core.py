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
        # Manual-work markers (stamped by the Labels tool, preserved by
        # Fully Auto-Label's preserve toggle): manual_tag groups pieces of
        # a user-Defined Section, manual_first marks the user's chosen #1
        # piece, manual_label protects a hand-typed label outright.
        self.manual_tag = None
        self.manual_first = False
        self.manual_label = False

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
        d = {
            "id": self.id,
            "label": self.label,
            "polygon": self.polygon,
            "parent_id": self.parent_id,
            "children": self.children,
            "split_boundary": self.split_boundary,
        }
        # Only serialize manual markers when set (keeps old-file diffs small)
        if self.manual_tag is not None:
            d["manual_tag"] = self.manual_tag
        if self.manual_first:
            d["manual_first"] = True
        if self.manual_label:
            d["manual_label"] = True
        return d

    @staticmethod
    def from_dict(d):
        r = Region.__new__(Region)
        r.__dict__.update({k: d.get(k) for k in ["id", "label", "parent_id"]})
        r.polygon = [tuple(p) for p in d["polygon"]]
        r.children = d.get("children", [])
        r.split_boundary = d.get("split_boundary", False)
        r.manual_tag = d.get("manual_tag")
        r.manual_first = d.get("manual_first", False)
        r.manual_label = d.get("manual_label", False)
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
                        # The node now IS the survivor: take its label and
                        # manual markers too, or a collapsed-onto real piece
                        # is silently renamed / loses its Defined Section.
                        node.label = survivor.label
                        node.manual_tag = survivor.manual_tag
                        node.manual_first = survivor.manual_first
                        node.manual_label = survivor.manual_label
                        node.children = survivor.children
                        for grandchild_id in survivor.children:
                            if grandchild_id in self.regions:
                                self.regions[grandchild_id].parent_id = node.id
                        del self.regions[survivor_id]
                        changed = True

    def _adopt_orphan_leaves(self):
        """Re-attach leaves unreachable from the root. Heal operations can
        leave a region parentless; such leaves are invisible to the
        structural-group walk, so they would never be partitioned, merged
        or relabelled (and their stale labels can collide with fresh ones).
        Chain them onto the root with non-boundary internals so they join
        the top structural group and the tree is well-formed again."""
        if self.root_id is None:
            return
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

    def prune_stale_curves(self):
        """Drop recorded curve boundaries that no longer lie between any
        current leaf edges. Heals and undos delete the regions a curve cut
        created; without pruning the stale records grow forever (they are
        serialized into the SVG) and can falsely refuse future heals."""
        if not getattr(self, "curves", None):
            return
        leaf_polys = [r.polygon for r in self.leaf_regions()]
        kept = []
        for curve in self.curves:
            alive = False
            for poly in leaf_polys:
                n = len(poly)
                for i in range(n):
                    p1, p2 = poly[i], poly[(i + 1) % n]
                    for idx in range(len(curve) - 1):
                        c1, c2 = curve[idx], curve[idx + 1]
                        if (pt_dist(p1, c1) < 1.5 and pt_dist(p2, c2) < 1.5) or \
                           (pt_dist(p1, c2) < 1.5 and pt_dist(p2, c1) < 1.5):
                            alive = True
                            break
                    if alive:
                        break
                if alive:
                    break
            if alive:
                kept.append(curve)
        self.curves = kept

    def _descendant_leaves(self, node_id):
        out = []
        stack = [node_id]
        while stack:
            nid = stack.pop()
            node = self.regions.get(nid)
            if node is None:
                continue
            if node.is_leaf():
                out.append(nid)
            else:
                stack.extend(node.children)
        return out

    def _merge_boundary_violation(self, id_set):
        """Error message if merging the given leaves would cross a
        structural boundary without consuming it whole, else None.

        A split_boundary node's cut line may only be healed over when
        every leaf on both of its sides is part of the merge. An enclave
        (imported sub-block) may merge internally or be consumed whole,
        but must not be partially mixed with outside pieces."""
        for node in list(self.regions.values()):
            if not node.split_boundary or node.is_leaf():
                continue
            d_leaves = set(self._descendant_leaves(node.id))
            if not (id_set & d_leaves):
                continue
            if self._is_enclave(node):
                if not (id_set <= d_leaves or d_leaves <= id_set):
                    return (
                        "Cannot merge across an imported block's border "
                        "unless the whole imported block is included."
                    )
                continue
            sides_hit = sum(
                1
                for cid in node.children
                if id_set & set(self._descendant_leaves(cid))
            )
            if sides_hit > 1 and not d_leaves <= id_set:
                return (
                    "Cannot merge across a structural boundary unless all "
                    "pieces on both sides of the boundary are included."
                )
        return None

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

    def _is_enclave(self, node):
        """A split_boundary node marks one of two different things:

        * a real boundary CUT (grid line, circle cut, crop frame): its
          children geometrically partition it, and pieces on either side
          of the cut must stay in separate structural groups;
        * an ENCLAVE (a sub-block imported into a region / rebuilt from
          pieces): its children are a _chain_leaves bookkeeping chain — an
          internal child carries the node's own polygon, not a half of it.
          The whole subtree is ONE structural group that simply must not
          merge with pieces outside the node.

        Recognises the explicit "enclave" flag value (written by newer
        imports) AND legacy trees where True was stamped on a chain node,
        which used to wrongly split the first imported piece into its own
        one-piece group (and block merges/heals within the import)."""
        if node.split_boundary == "enclave":
            return True
        if not node.split_boundary or not node.children:
            return False
        for cid in node.children:
            child = self.regions.get(cid)
            if child is not None and not child.is_leaf() and \
                    _polys_equivalent(child.polygon, node.polygon):
                return True
        return False

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
        lca = self.regions[lca_id]
        # Two pieces whose common ancestor is an enclave are both INSIDE
        # the imported block - no boundary runs between them.
        return bool(lca.split_boundary) and not self._is_enclave(lca)

    def reset_to_boundaries(self):
        valid_nodes = set()

        def walk(n_id):
            valid_nodes.add(n_id)
            node = self.regions[n_id]
            if not node.children:
                return
            if not node.split_boundary or self._is_enclave(node):
                # Enclaves collapse whole: recursing used to strand the
                # first imported piece next to an overlapping chain node.
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
            # Pieces cut inside a user-Defined Section stay in that section
            child_a.manual_tag = child_b.manual_tag = region.manual_tag
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
            # Pieces cut inside a user-Defined Section stay in that section
            child_a.manual_tag = child_b.manual_tag = region.manual_tag
            
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
            # Pieces cut inside a user-Defined Section stay in that section
            child_a.manual_tag = child_b.manual_tag = region.manual_tag

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


    def _pair_shares_curve(self, poly_a, poly_b):
        """True when a recorded curve boundary runs between the two
        polygons (a coincident segment on both boundaries)."""
        if not getattr(self, "curves", None):
            return False

        def on_poly(poly, c1, c2):
            n = len(poly)
            for i in range(n):
                p1, p2 = poly[i], poly[(i + 1) % n]
                if (pt_dist(p1, c1) < 1.5 and pt_dist(p2, c2) < 1.5) or \
                   (pt_dist(p1, c2) < 1.5 and pt_dist(p2, c1) < 1.5):
                    return True
            return False

        for curve in self.curves:
            for idx in range(len(curve) - 1):
                c1, c2 = curve[idx], curve[idx + 1]
                if on_poly(poly_a, c1, c2) and on_poly(poly_b, c1, c2):
                    return True
        return False

    def merge_leaf_set(self, leaf_ids, absorb=False):
        """Merge the given leaf pieces into ONE region by iterative
        pairwise polygon merges (partial/T-junction shared edges merge
        too). Unlike the tree-collapse smart heal this never destroys
        unselected pieces - unless absorb=True, which may pull in a
        bridging or enclosed unselected piece when the selection alone
        cannot form one simple polygon.

        Refuses curved seams, structural-boundary crossings that do not
        consume the whole boundary, and geometry that does not conserve
        area. Returns (ok, msg, guide_polys) where guide_polys are the
        consumed pieces' outlines for seam-guide rendering."""
        ids = {int(i) for i in leaf_ids}
        ids = {i for i in ids if i in self.regions}
        if len(ids) < 2:
            return False, "Select at least two different pieces to merge.", []
        for i in ids:
            if not self.regions[i].is_leaf():
                return False, "Only leaf pieces can be merged.", []

        violation = self._merge_boundary_violation(ids)
        if violation:
            return False, violation, []

        working = set(ids)
        blobs = [[{i}, list(self.regions[i].polygon)] for i in sorted(working)]

        def try_round():
            for bi in range(len(blobs)):
                for bj in range(bi + 1, len(blobs)):
                    pa, pb = blobs[bi][1], blobs[bj][1]
                    if self._pair_shares_curve(pa, pb):
                        continue
                    merged = merge_adjacent_polygons(pa, pb)
                    if merged is not None:
                        blobs[bi][0] |= blobs[bj][0]
                        blobs[bi][1] = merged
                        blobs.pop(bj)
                        return True
            return False

        while len(blobs) > 1:
            if try_round():
                continue
            if not absorb:
                break
            # A bridge or enclosed piece: an unselected leaf touching two
            # separate merge blobs. Absorb the smallest candidate that
            # keeps the structural-boundary rules satisfied.
            candidate = None
            for r in sorted(
                self.leaf_regions(), key=lambda r: (r.area_sq_in(), r.id)
            ):
                if r.id in working:
                    continue
                touching = sum(
                    1 for b in blobs if polygons_share_edge(r.polygon, b[1])
                )
                if touching >= 2 and self._merge_boundary_violation(
                    working | {r.id}
                ) is None:
                    candidate = r
                    break
            if candidate is None:
                break
            working.add(candidate.id)
            blobs.append([{candidate.id}, list(candidate.polygon)])

        if len(blobs) > 1:
            for bi in range(len(blobs)):
                for bj in range(bi + 1, len(blobs)):
                    if self._pair_shares_curve(blobs[bi][1], blobs[bj][1]):
                        return (
                            False,
                            "Selected pieces share a curved boundary and "
                            "cannot be merged.",
                            [],
                        )
            hint = (
                ""
                if absorb
                else " If an unselected piece sits between them, enable "
                "'absorb other pieces'."
            )
            return (
                False,
                "Selected pieces cannot be merged into a single piece - "
                "they must form one connected area." + hint,
                [],
            )

        merged_ids, merged_poly = blobs[0]
        consumed = [self.regions[i] for i in sorted(merged_ids)]
        guide_polys = [list(r.polygon) for r in consumed]
        label = min(r.label for r in consumed)

        total = sum(polygon_area(r.polygon) for r in consumed)
        if abs(polygon_area(merged_poly) - total) > max(0.01 * total, 1.0):
            return (
                False,
                "Merge failed a geometry sanity check (areas do not add up).",
                [],
            )

        # Which ancestors will this merge empty? Fixpoint over the ORIGINAL
        # child lists: an internal node empties when its whole subtree is
        # being consumed. Left in place such nodes resurface as phantom
        # leaves with stale geometry (e.g. legacy TEMP_HEAL chain nodes).
        consumed_ids = {r.id for r in consumed}
        pre_internal = {
            nid for nid, node in self.regions.items() if node.children
        }
        emptied = set()
        changed = True
        while changed:
            changed = False
            for nid in pre_internal:
                if nid in emptied:
                    continue
                kids = self.regions[nid].children
                if kids and all(
                    cid in consumed_ids or cid in emptied for cid in kids
                ):
                    emptied.add(nid)
                    changed = True

        for r in consumed:
            if r.parent_id and r.parent_id in self.regions:
                parent = self.regions[r.parent_id]
                if r.id in parent.children:
                    parent.children.remove(r.id)
            del self.regions[r.id]

        # Reuse the emptied ancestor whose geometry equals the merged piece
        # (e.g. both children of one cut merged back, or the whole block
        # merged: the root): keeps the history tree intact and avoids an
        # orphan. Its cut - boundary or not - has been healed away, so
        # clear the flag. Root is preferred so merging everything never
        # deletes the tree's anchor.
        cx_n, cy_n = polygon_centroid(merged_poly)
        area_n = polygon_area(merged_poly) / (PX_PER_INCH ** 2)
        reused = None
        scan_order = sorted(
            emptied, key=lambda nid: (nid != self.root_id, nid)
        )
        for nid in scan_order:
            node = self.regions.get(nid)
            if node is None:
                continue
            if abs(node.area_sq_in() - area_n) < 0.01:
                cx_p, cy_p = polygon_centroid(node.polygon)
                if math.hypot(cx_p - cx_n, cy_p - cy_n) < 1.0:
                    reused = node
                    break

        for nid in emptied:
            node = self.regions.get(nid)
            if node is None:
                continue
            if reused is not None and nid == reused.id:
                continue
            if nid == self.root_id:
                continue
            if node.parent_id and node.parent_id in self.regions:
                p = self.regions[node.parent_id]
                if nid in p.children:
                    p.children.remove(nid)
            del self.regions[nid]
        if reused is not None:
            reused.children = []

        # The merged piece inherits manual markers: it stays in a Defined
        # Section when every constituent belonged to the same one, and it
        # keeps start/hand-label status from its constituents.
        tags = {r.manual_tag for r in consumed}
        inherit_tag = tags.pop() if len(tags) == 1 else None
        inherit_first = any(r.manual_first for r in consumed)
        label_donor = min(consumed, key=lambda r: r.label)
        inherit_label = label_donor.manual_label

        absorbed = len(working) - len(ids)
        if reused is not None:
            reused.label = label
            reused.polygon = simplify_polygon(list(merged_poly))
            reused.split_boundary = False
            reused.manual_tag = inherit_tag
            reused.manual_first = inherit_first
            reused.manual_label = inherit_label
        else:
            new_region = Region(merged_poly, label=label)
            new_region.manual_tag = inherit_tag
            new_region.manual_first = inherit_first
            new_region.manual_label = inherit_label
            self.regions[new_region.id] = new_region
            self._adopt_orphan_leaves()

        self.sanitize_tree()
        self._adopt_orphan_leaves()
        self.prune_stale_curves()

        msg = f"Merged {len(consumed)} pieces into one ({label})."
        if absorbed > 0:
            msg += f" Absorbed {absorbed} unselected piece(s) to bridge the selection."
        return True, msg, guide_polys

    def heal_regions(self, id1, id2):
        """Two-piece heal (compatibility wrapper over merge_leaf_set)."""
        if id1 not in self.regions or id2 not in self.regions:
            return False, "One or both pieces could not be found."
        if id1 == id2:
            return (
                False,
                "Please select two DIFFERENT pieces (the same piece was "
                "selected twice).",
            )
        ok, msg, _guides = self.merge_leaf_set({id1, id2})
        return ok, msg

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
                if node_id == lca_id and self._is_enclave(self.regions[node_id]):
                    # Everything selected sits inside this imported block;
                    # healing within an enclave crosses no boundary.
                    continue
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
        # Keep a real section label (lowest consumed label's letter) so the
        # healed piece never renders as a TEMP_* placeholder; the caller's
        # rebuild_alphabet renumbers within the letter group.
        keep = min((leaf.label for leaf in consumed_leaves), default="A1")
        m = re.match(r"^([A-Za-z]+)", keep)
        lca_node.label = (m.group(1) if m else "A") + "1"
        lca_node.split_boundary = False
        tags = {leaf.manual_tag for leaf in consumed_leaves}
        lca_node.manual_tag = tags.pop() if len(tags) == 1 else None
        lca_node.manual_first = any(l.manual_first for l in consumed_leaves)
        lca_node.manual_label = False

        self.sanitize_tree()
        self.prune_stale_curves()
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
        """Physical piecing-order check via the SEAM-THROUGH rule.

        A piece may be sewn onto the assembled unit only when its contact
        with the unit is ONE contiguous seam, straight or smoothly curved,
        whose ends both reach the unit's outline. This genuinely verifies
        curved FPP seams (no more blanket curve bypass) and rejects
        partial-edge contacts, U-shape closures and seams that die
        mid-unit (Y-seams)."""
        if not selected_leaf_ids:
            return False, []
        if len(selected_leaf_ids) == 1:
            return True, list(selected_leaf_ids)

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

        # Backtracking search over removal orders. A greedy peel (always
        # remove the first piece that can be "last sewn") is order-dependent:
        # removing a valid-looking piece can strand a neighbour that only
        # touched the removed piece, wrongly reporting a Y-seam for a
        # perfectly sewable section. Dead-end states are memoised and the
        # search is budgeted so worst-case blocks stay fast.
        failed_states = set()
        budget = [20000]

        def solve(remaining):
            if len(remaining) == 1:
                return [next(iter(remaining))]
            if remaining in failed_states or budget[0] <= 0:
                return None
            budget[0] -= 1
            for test_id in sorted(remaining):
                if force_start_id and test_id == force_start_id:
                    # The start piece must be the last one standing.
                    continue

                rest_ids = remaining - {test_id}
                # The piece must touch the unit it will be sewn onto.
                if not (adjacency[test_id] & rest_ids):
                    continue

                # SEAM-THROUGH rule: X was the last piece sewn on only if
                # its contact with the rest is one contiguous seam
                # (straight or smoothly curved) whose two ends both reach
                # the unit's outline.
                rest_polys = [polygons[r] for r in rest_ids]
                ok, _why = valid_seam_contact(
                    polygons[test_id], rest_polys, rest_polys + [polygons[test_id]])
                if ok:
                    sub = solve(frozenset(rest_ids))
                    if sub is not None:
                        return [test_id] + sub
            failed_states.add(remaining)
            return None

        sequence = solve(frozenset(selected_leaf_ids))
        if sequence is None:
            return False, []
        sequence.reverse()
        if force_start_id and sequence[0] != force_start_id:
            return False, []

        # Final gate: the pieces must union into sound geometry. A section
        # whose pieces only meet along partial-edge "necks" (e.g. a
        # borderline-U piece grabbing a neighbour by a sliver of its edge)
        # cannot be verified - and physically forces inset seams - so it
        # is refused, matching the merge pass's sound-geometry principle.
        polys = [polygons[nid] for nid in sequence]
        union = get_polygon_union([list(p) for p in polys])
        total = sum(polygon_area(p) for p in polys)
        ua = polygon_area(union) if union else 0.0
        if total > 0 and abs(ua - total) > max(0.01 * total, 1.0):
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
                if self._is_enclave(node):
                    # Imported sub-block: ONE group, sealed from outside.
                    combined = left_leaves + right_leaves
                    if combined:
                        groups.append(combined)
                    return []
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

    def purge_ghost_leaves(self):
        """Remove GHOST leaves: stale regions from earlier edit states
        whose interior is (almost) entirely covered by other leaves. In a
        valid tree, leaves partition the block and never overlap - a
        fully-overlapped leaf draws underneath the real pieces, aligns
        with no current cut line, and resurrects on every redraw because
        deleting its canvas path cannot remove it from the tree.

        Removes one ghost at a time and re-checks (so a mutually-stacked
        pair loses only the redundant copy). Returns the removed labels."""
        removed = []
        while True:
            leaves = self.leaf_regions()
            ghost = None
            for r in leaves:
                others = [o.polygon for o in leaves if o.id != r.id]
                if not others:
                    break
                xs = [p[0] for p in r.polygon]
                ys = [p[1] for p in r.polygon]
                pts = []
                steps = 7
                for gi in range(1, steps):
                    for gj in range(1, steps):
                        q = (min(xs) + (max(xs) - min(xs)) * gi / steps,
                             min(ys) + (max(ys) - min(ys)) * gj / steps)
                        if point_in_polygon(q, r.polygon):
                            pts.append(q)
                if len(pts) < 5:
                    cx, cy = polygon_centroid(r.polygon)
                    pts.append((cx, cy))
                covered = sum(
                    1 for q in pts
                    if any(point_in_polygon(q, o) for o in others))
                if covered >= max(1, int(len(pts) * 0.98)) and \
                        covered == len(pts):
                    ghost = r
                    break
            if ghost is None:
                break
            removed.append(ghost.label)
            parent = self.regions.get(ghost.parent_id)
            if parent is not None and ghost.id in parent.children:
                parent.children.remove(ghost.id)
            del self.regions[ghost.id]
            self.sanitize_tree()
        return removed

    def auto_partition_and_label(self, preserve_manual=False):
        self.sanitize_tree()

        ghosts = self.purge_ghost_leaves()
        if ghosts:
            inkex.utils.debug(
                "Removed %d ghost piece(s) that were fully covered by "
                "other pieces (stale geometry from earlier edits): %s"
                % (len(ghosts), ", ".join(sorted(ghosts))))

        self._adopt_orphan_leaves()

        remaining_ids = set(r.id for r in self.leaf_regions())

        if preserve_manual is False:
            pass
        elif any(
            re.match(r"^(\d+-[A-Za-z]+|[A-Za-z]+)\d+$", r.label) and not r.label.startswith("P") and not r.label.startswith("TEMP")
            for r in self.leaf_regions()
        ):
            preserve_manual = True

        pinned_groups = []
        hard_pinned = set()
        if preserve_manual:
            by_tag = {}
            for r in self.leaf_regions():
                if r.manual_tag is not None:
                    by_tag.setdefault(r.manual_tag, []).append(r.id)
                elif r.manual_label:
                    hard_pinned.add(r.id)
            pinned_groups = list(by_tag.values())
            if not by_tag and not hard_pinned:
                by_pref = {}
                for r in self.leaf_regions():
                    if not r.label.startswith("P") and not r.label.startswith("TEMP"):
                        if re.match(r"^(\d+-[A-Za-z]+|[A-Za-z]+)\d+$", r.label):
                            m = re.match(r"^(\d+-[A-Za-z]+|[A-Za-z]+)", r.label)
                            by_pref.setdefault(m.group(1), []).append(r.id)
                pinned_groups = list(by_pref.values())
            for g in pinned_groups:
                for nid in g:
                    remaining_ids.discard(nid)
            for nid in hard_pinned:
                remaining_ids.discard(nid)

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
                    # Only test candidate pieces adjacent to the current sequence tail/head for fast candidate evaluation
                    candidates = [
                        nid for nid in list(local_rem)
                        if any(polygons_adjacent(self.regions[nid].polygon, self.regions[s].polygon) for s in seq)
                    ]
                    for next_id in candidates:
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
        pinned_sections = []
        groups = self.get_structural_groups()

        for grp_ids in groups:
            grp_set = set(grp_ids)
            # Manual sections belonging to this structural group (clipped
            # defensively - a Defined Section should never span groups).
            grp_pinned = []
            for g in pinned_groups:
                clipped = [nid for nid in g if nid in grp_set]
                if clipped:
                    grp_pinned.append(clipped)
            pinned_ids = {nid for g in grp_pinned for nid in g}

            grp_rem = [nid for nid in grp_ids if nid in remaining_ids]
            if not grp_rem and not grp_pinned:
                continue

            rest_secs = partition_into_sections(grp_rem) if grp_rem else []

            if grp_pinned:
                # The user's rule: manual sections stay UNLESS full-auto
                # would partition this area into strictly fewer sections.
                if preserve_manual:
                    rest_secs = grp_pinned
                else:
                    auto_all = partition_into_sections(grp_rem + sorted(pinned_ids))
                    if len(auto_all) < len(grp_pinned) + len(rest_secs):
                        rest_secs = auto_all
                    grp_pinned = []

            pinned_sections.extend(grp_pinned)
            sections.extend(rest_secs)
            for sec in rest_secs:
                for nid in sec:
                    remaining_ids.discard(nid)

        # Split each section into connected components to ensure physical sewability
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
            be trusted when every section's union truly covers its pieces.

            get_polygon_union is ORDER-SENSITIVE: it merges reliably when
            pieces arrive in sewing order (each addition shares a full
            seam with the unit so far). Union in the validator's order —
            which doubles as the physical check that every seam is a full
            shared edge."""
            key = frozenset(sec_ids)
            if key not in _union_cache:
                ok, seq = self.virtual_sewing_validator(set(sec_ids))
                ordered = seq if ok else list(sec_ids)
                polys = [self.regions[nid].polygon for nid in ordered]
                total = sum(polygon_area(p) for p in polys)
                union = get_polygon_union([list(p) for p in polys])
                ua = polygon_area(union) if union else 0.0
                _union_cache[key] = total <= 0 or abs(ua - total) < max(
                    0.01 * total, 1.0
                )
            return _union_cache[key]

        _assembly_warn_cache = {}

        def _assembly_warn(trial_sections):
            """Block-level assembly verdict for a trial partition: False =
            clean, True = warns, None = unverifiable (unsound union)."""
            key = tuple(sorted(frozenset(sec) for sec in trial_sections))
            if key in _assembly_warn_cache:
                return _assembly_warn_cache[key]

            # Fast path for large section counts (>12 sections): skip expensive section-sewing-order permutation solver
            if len(trial_sections) > 12:
                _assembly_warn_cache[key] = False
                return False

            for sec in trial_sections:
                if not _union_sound(sec):
                    _assembly_warn_cache[key] = None
                    return None
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
            res = bool(warn)
            _assembly_warn_cache[key] = res
            return res

        def _is_curve_exempt(sec_ids):
            """Returns True if the section lies along a declared curve boundary."""
            if getattr(self, "curves", None):
                polys = [self.regions[nid].polygon for nid in sec_ids]
                for p in polys:
                    n = len(p)
                    for i in range(n):
                        p1, p2 = p[i], p[(i + 1) % n]
                        for curve in self.curves:
                            for idx_c in range(len(curve) - 1):
                                c1, c2 = curve[idx_c], curve[idx_c + 1]
                                if (pt_dist(p1, c1) < 2.0 and pt_dist(p2, c2) < 2.0) or \
                                   (pt_dist(p1, c2) < 2.0 and pt_dist(p2, c1) < 2.0):
                                    return True
            return False

        def _is_concave_scurve(sec_ids):
            """Concavity Guard: Prevents straight-seam pieces from bending into S-curves.
            Exempts declared curve runs and solid convex rotational shapes (Log Cabins/Compasses)."""
            if _is_curve_exempt(sec_ids):
                return False

            polys = [self.regions[nid].polygon for nid in sec_ids]
            all_pts = [pt for p in polys for pt in p]
            if len(all_pts) < 3:
                return False

            total_area = sum(polygon_area(p) for p in polys)
            if total_area <= 0.0:
                return False

            hull = convex_hull(all_pts)
            hull_area = polygon_area(hull)
            if hull_area <= 0.0:
                return False

            concavity_ratio = 1.0 - (total_area / hull_area)
            # Rejects winding serpentine S-curves (> 0.15 concavity)
            # while allowing solid rectangular/wedge Log Cabins & Mariner's Compasses (~0.0 concavity).
            return concavity_ratio > 0.15

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
            if _is_concave_scurve(union_ids):
                return None  # Rejects straight-seam S-curves!
            ok, seq = self.virtual_sewing_validator(union_ids)
            return seq if ok else None

        merged = True
        while merged:
            merged = False
            # A merge must leave block assembly NO WORSE than the current
            # partition: curve-heavy blocks may warn either way, and that
            # must not freeze their fragments apart forever.
            baseline_warn = _assembly_warn(sections)
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
                    trial_warn = _assembly_warn(trial)
                    if trial_warn is None:
                        continue
                    if trial_warn is False or baseline_warn is True:
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

        # Only pieces that KEEP their labels reserve their letters; letters
        # of pieces about to be relabeled are recycled (else auto sections
        # drift to ever-later letters on every preserve-mode rerun).
        used_letters = set()
        if preserve_manual:
            protected = set(hard_pinned)
            for g in pinned_sections:
                protected.update(g)
            for r in self.leaf_regions():
                if r.id in protected:
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

        def order_with_manual_first(sec_ids):
            """Sewing order for a section, honoring a manual_first piece."""
            first_id = next(
                (nid for nid in sec_ids if self.regions[nid].manual_first),
                None,
            )
            if len(sec_ids) > 1:
                if first_id is not None:
                    ok_f, seq_f = self.virtual_sewing_validator(
                        set(sec_ids), force_start_id=first_id
                    )
                    if ok_f:
                        return seq_f
                ok_f, seq_f = self.virtual_sewing_validator(set(sec_ids))
                if ok_f:
                    return seq_f
            return list(sec_ids)

        has_multi_subblocks = len(groups) > 1

        # Pinned manual sections: keep their letter, renumber in sewing
        # order (cuts inside a Defined Section leave labels like E2a that
        # need compacting), user's #1 piece stays #1.
        for sec_ids in pinned_sections:
            prefixes = [
                re.match(r"^(\d+-[A-Za-z]+|[A-Za-z]+)", self.regions[nid].label)
                for nid in sec_ids
            ]
            prefixes = [m.group(1).upper() for m in prefixes if m]
            sb_pfx = f"{group_of.get(sec_ids[0], 0) + 1}-" if has_multi_subblocks else ""
            letter = prefixes[0] if prefixes else f"{sb_pfx}{get_available_letter()}"
            used_letters.add(letter)
            for i, nid in enumerate(order_with_manual_first(sec_ids)):
                self.regions[nid].label = f"{letter}{i + 1}"

        for sec_ids in sections:
            sb_pfx = f"{group_of.get(sec_ids[0], 0) + 1}-" if has_multi_subblocks else ""
            letter = f"{sb_pfx}{get_available_letter()}"
            for i, nid in enumerate(order_with_manual_first(sec_ids)):
                self.regions[nid].label = f"{letter}{i + 1}"

    def rebuild_alphabet(self):
        self.sanitize_tree()
        groups = {}
        for r in self.leaf_regions():
            match = re.match(r"^(\d+-[A-Za-z]+|[A-Za-z_]+)", r.label)
            prefix = match.group(1) if match else "A"
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(r)

        for prefix, grp in groups.items():
            grp_ids = [n.id for n in grp]
            current_first = next((n for n in grp if n.manual_first), None)
            if current_first is None:
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
        self.prune_stale_curves()
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

    def piece_meta(self):
        """Per-region cutting metadata ({str(region_id): {...}}), pruned to
        regions that still exist. Legacy blocks return {} — defaults apply
        (grain free, technique template)."""
        meta = self.prefs.get("piece_meta") or {}
        valid = {str(r.id) for r in self.tree.leaf_regions()}
        pruned = {k: v for k, v in meta.items() if str(k) in valid}
        if len(pruned) != len(meta):
            self.prefs["piece_meta"] = pruned
        return pruned

    def set_piece_meta(self, region_id, **kv):
        """Merge cutting metadata for one region; None values delete keys.
        Returns the region's resulting meta dict (removed from prefs
        entirely when it empties)."""
        meta = self.prefs.setdefault("piece_meta", {})
        entry = meta.setdefault(str(region_id), {})
        for k, v in kv.items():
            if v is None:
                entry.pop(k, None)
            else:
                entry[k] = v
        if not entry:
            meta.pop(str(region_id), None)
        return entry

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


