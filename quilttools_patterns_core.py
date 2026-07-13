import sys
import math
import os
import re
from lxml import etree
import quilttools_fpp_core as core

# Expose core attributes/methods so this inherits from quilttools_fpp_core
globals().update({k: v for k, v in core.__dict__.items() if not k.startswith('_')})

def clip_polygon_to_polygon(subject_poly, clip_poly):
    if core.polygon_area_signed(clip_poly) < 0:
        clip_poly = list(reversed(clip_poly))
    
    def clip_edge(poly, q1, q2):
        if not poly:
            return []
        out = []
        n = len(poly)
        
        def is_inside(p):
            return (q2[0] - q1[0]) * (p[1] - q1[1]) - (q2[1] - q1[1]) * (p[0] - q1[0]) >= -1e-9
        
        def intersect(a, b):
            da_x, da_y = b[0] - a[0], b[1] - a[1]
            dq_x, dq_y = q2[0] - q1[0], q2[1] - q1[1]
            denom = da_x * dq_y - da_y * dq_x
            if abs(denom) < 1e-9:
                return a
            num = (q1[0] - a[0]) * dq_y - (q1[1] - a[1]) * dq_x
            t = num / denom
            return (a[0] + t * da_x, a[1] + t * da_y)

        for i in range(n):
            cur = poly[i]
            nxt = poly[(i + 1) % n]
            cur_in = is_inside(cur)
            nxt_in = is_inside(nxt)
            if cur_in:
                out.append(cur)
                if not nxt_in:
                    out.append(intersect(cur, nxt))
            else:
                if nxt_in:
                    out.append(intersect(cur, nxt))
        return out

    poly = list(subject_poly)
    for i in range(len(clip_poly)):
        q1 = clip_poly[i]
        q2 = clip_poly[(i + 1) % len(clip_poly)]
        poly = clip_edge(poly, q1, q2)
        
    return core.simplify_polygon(poly) if len(poly) >= 3 else []


def clip_polyline_to_polygon(polyline, polygon):
    clipped_polylines = []
    current_segment = []
    
    for i in range(len(polyline) - 1):
        a, b = polyline[i], polyline[i+1]
        intersections = []
        n = len(polygon)
        for j in range(n):
            q1, q2 = polygon[j], polygon[(j + 1) % n]
            r = core.segment_intersect(a, b, q1, q2)
            if r:
                t, pt = r
                if 1e-9 < t < 1 - 1e-9:
                    intersections.append((t, pt))
        
        intersections.sort(key=lambda x: x[0])
        
        sub_segments = []
        last_t = 0.0
        last_pt = a
        for t, pt in intersections:
            sub_segments.append((last_pt, pt))
            last_t = t
            last_pt = pt
        sub_segments.append((last_pt, b))
        
        for sa, sb in sub_segments:
            mid = ((sa[0] + sb[0]) / 2.0, (sa[1] + sb[1]) / 2.0)
            if core.point_in_polygon(mid, polygon):
                if not current_segment:
                    current_segment.append(sa)
                current_segment.append(sb)
            else:
                if current_segment:
                    clipped_polylines.append(current_segment)
                    current_segment = []
                    
    if current_segment:
        clipped_polylines.append(current_segment)
        
    return clipped_polylines


def import_block_into_region(parent_tree, parent_region, lib_bd, sizing_mode="stretch", rotation=0.0, flip="none", auto_align=True):
    import quilttools_placement as qplace
    
    lib_regions = lib_bd.tree.leaf_regions()
    all_L_pts = [pt for r in lib_regions for pt in r.polygon]
    if not all_L_pts:
        return 0
    
    R_poly = parent_region.polygon
    is_tiling = sizing_mode in ("tile_stretch", "tile_ratio")
    
    if is_tiling:
        # 1. Determine local bounding box of source block
        L_xs = [p[0] for p in all_L_pts]
        L_ys = [p[1] for p in all_L_pts]
        L_min_x, L_max_x = min(L_xs), max(L_xs)
        L_min_y, L_max_y = min(L_ys), max(L_ys)
        w_src = L_max_x - L_min_x
        h_src = L_max_y - L_min_y
        
        # 2. Align destination region to its longest edge (auto-align / rotation)
        align_angle = qplace.get_longest_edge_angle(R_poly) if auto_align else 0.0
        total_rot = align_angle + rotation
        
        R_xs = [p[0] for p in R_poly]
        R_ys = [p[1] for p in R_poly]
        cx_dst = (min(R_xs) + max(R_xs)) / 2.0
        cy_dst = (min(R_ys) + max(R_ys)) / 2.0
        
        def rotate_pt(p, angle, cx, cy):
            tx, ty = p[0] - cx, p[1] - cy
            rad = math.radians(angle)
            rx = tx * math.cos(rad) - ty * math.sin(rad) + cx
            ry = tx * math.sin(rad) + ty * math.cos(rad) + cy
            return (rx, ry)
            
        R_poly_aligned = [rotate_pt(p, -total_rot, cx_dst, cy_dst) for p in R_poly]
        RA_xs = [p[0] for p in R_poly_aligned]
        RA_ys = [p[1] for p in R_poly_aligned]
        RA_min_x, RA_max_x = min(RA_xs), max(RA_xs)
        RA_min_y, RA_max_y = min(RA_ys), max(RA_ys)
        W = RA_max_x - RA_min_x
        H = RA_max_y - RA_min_y
        
        # 3. Calculate scaling and tile count
        scale_y = H / h_src if h_src > 0 else 1.0
        if sizing_mode == "tile_stretch":
            N = max(1, round(W / (w_src * scale_y))) if w_src > 0 else 1
            scale_x = W / (N * w_src) if w_src > 0 else 1.0
        else: # "tile_ratio"
            scale_x = scale_y
            w_tile = w_src * scale_x
            N = max(1, math.ceil(W / w_tile)) if w_tile > 0 else 1
            
        curr_inside_id = parent_region.id
        
        map_pt_list = []
        for k in range(N):
            def make_map_pt_k(tile_idx):
                def map_pt_k(p):
                    tx, ty = p[0] - L_min_x, p[1] - L_min_y
                    if flip == "horizontal":
                        tx = w_src - tx
                    elif flip == "vertical":
                        ty = h_src - ty
                    sx = tx * scale_x
                    sy = ty * scale_y
                    ax = RA_min_x + tile_idx * w_src * scale_x + sx
                    ay = RA_min_y + sy
                    return rotate_pt((ax, ay), total_rot, cx_dst, cy_dst)
                return map_pt_k
            map_pt_list.append(make_map_pt_k(k))
            
        map_pt = map_pt_list[0]
        
    else:
        map_pt, _ = qplace.calculate_placement_transform(
            all_L_pts, R_poly, sizing_mode=sizing_mode, rotation=rotation, flip=flip, auto_align=auto_align
        )
        
        # 1. Determine the outer boundary of the library block in target region space
        L_xs = [p[0] for p in all_L_pts]
        L_ys = [p[1] for p in all_L_pts]
        L_min_x, L_max_x = min(L_xs), max(L_xs)
        L_min_y, L_max_y = min(L_ys), max(L_ys)
        L_corners = [
            (L_min_x, L_min_y),
            (L_max_x, L_min_y),
            (L_max_x, L_max_y),
            (L_min_x, L_max_y)
        ]
        L_boundary_poly = [map_pt(p) for p in L_corners]
        
        # Helper to cut region
        def cut_region_by_line(tree, region_id, p1, p2):
            d_x = p2[0] - p1[0]
            d_y = p2[1] - p1[1]
            dist = math.hypot(d_x, d_y)
            if dist < 1e-9:
                return [region_id]
            dx_norm = d_x / dist
            dy_norm = d_y / dist
            
            draw_p1 = (p1[0] - dx_norm * 10000.0, p1[1] - dy_norm * 10000.0)
            draw_p2 = (p2[0] + dx_norm * 10000.0, p2[1] + dy_norm * 10000.0)
            
            cuts = tree.multi_guillotine_cut(
                draw_p1, draw_p2, angle_snap_deg=None, limit_to_region_id=region_id, is_boundary=True
            )
            if cuts > 0:
                return tree.regions[region_id].children
            return [region_id]
            
        curr_inside_id = parent_region.id
        for i in range(len(L_boundary_poly)):
            p_start = L_boundary_poly[i]
            p_end = L_boundary_poly[(i + 1) % len(L_boundary_poly)]
            
            children = cut_region_by_line(parent_tree, curr_inside_id, p_start, p_end)
            if len(children) == 2:
                cid1, cid2 = children
                area1 = core.polygon_area(clip_polygon_to_polygon(parent_tree.regions[cid1].polygon, L_boundary_poly))
                area2 = core.polygon_area(clip_polygon_to_polygon(parent_tree.regions[cid2].polygon, L_boundary_poly))
                if area1 >= area2:
                    curr_inside_id = cid1
                else:
                    curr_inside_id = cid2
                    
    # 3. Subdivide the final inside region by recursively copying the library block's subtree
    inside_region = parent_tree.regions[curr_inside_id]
    inside_region.children = []
    inside_region.split_boundary = True
    
    match = re.match(r"^([A-Za-z]+)", inside_region.label)
    prefix = match.group(1) if match else "A"
    
    next_id = max(parent_tree.regions.keys()) + 1
    added_leaf_count = 0
    active_map_pt = map_pt
    
    def copy_subtree(lib_node_id, parent_id_on_canvas):
        nonlocal next_id, added_leaf_count
        lib_node = lib_bd.tree.regions[lib_node_id]
        
        mapped_poly = [active_map_pt(p) for p in lib_node.polygon]
        clipped = clip_polygon_to_polygon(mapped_poly, parent_tree.regions[parent_id_on_canvas].polygon)
        if len(clipped) < 3 or core.polygon_area(clipped) <= 1.0:
            return None
            
        canvas_node_id = next_id
        next_id += 1
        
        canvas_node = core.Region(clipped, label=f"{prefix}{canvas_node_id}", parent_id=parent_id_on_canvas)
        canvas_node.id = canvas_node_id
        canvas_node.split_boundary = lib_node.split_boundary
        
        parent_tree.regions[canvas_node_id] = canvas_node
        
        if lib_node.is_leaf():
            canvas_node.children = []
            added_leaf_count += 1
            return canvas_node_id
        else:
            child_ids = []
            for child_id in lib_node.children:
                res_id = copy_subtree(child_id, canvas_node_id)
                if res_id is not None:
                    child_ids.append(res_id)
                    
            if len(child_ids) == 0:
                canvas_node.children = []
                added_leaf_count += 1
            elif len(child_ids) == 1:
                survivor_id = child_ids[0]
                parent_tree.regions[survivor_id].parent_id = parent_id_on_canvas
                del parent_tree.regions[canvas_node_id]
                return survivor_id
            else:
                canvas_node.children = child_ids
                
            return canvas_node_id

    if is_tiling:
        for k in range(N):
            active_map_pt = map_pt_list[k]
            for child_id in lib_bd.tree.regions[lib_bd.tree.root_id].children:
                res_id = copy_subtree(child_id, curr_inside_id)
                if res_id is not None:
                    inside_region.children.append(res_id)
    else:
        root_copied_id = copy_subtree(lib_bd.tree.root_id, curr_inside_id)
        if root_copied_id is not None:
            copied_node = parent_tree.regions[root_copied_id]
            if copied_node.is_leaf():
                inside_region.children = []
                del parent_tree.regions[root_copied_id]
            else:
                inside_region.children = copied_node.children
                for child_id in copied_node.children:
                    parent_tree.regions[child_id].parent_id = curr_inside_id
                del parent_tree.regions[root_copied_id]
                
    # Process curves
    if hasattr(lib_bd.tree, "curves") and lib_bd.tree.curves:
        if is_tiling:
            for k in range(N):
                active_map_pt = map_pt_list[k]
                for curve in lib_bd.tree.curves:
                    mapped_curve = [active_map_pt(p) for p in curve]
                    clipped_curves = clip_polyline_to_polygon(mapped_curve, inside_region.polygon)
                    for cc in clipped_curves:
                        parent_tree.curves.append(cc)
        else:
            for curve in lib_bd.tree.curves:
                mapped_curve = [map_pt(p) for p in curve]
                clipped_curves = clip_polyline_to_polygon(mapped_curve, inside_region.polygon)
                for cc in clipped_curves:
                    parent_tree.curves.append(cc)
                    
    return added_leaf_count
