import math
import quilttools_fpp_core as core

def get_longest_edge_angle(poly):
    best_angle = 0.0
    max_len = 0.0
    for i in range(len(poly)):
        p1 = poly[i]
        p2 = poly[(i + 1) % len(poly)]
        length = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
        if length > max_len:
            max_len = length
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            best_angle = math.degrees(math.atan2(dy, dx))
    return best_angle

def calculate_placement_transform(src_poly, dst_poly, sizing_mode="stretch", rotation=0.0, flip="none", auto_align=True):
    xs_src = [p[0] for p in src_poly]
    ys_src = [p[1] for p in src_poly]
    min_x_src, max_x_src = min(xs_src), max(xs_src)
    min_y_src, max_y_src = min(ys_src), max(ys_src)
    cx_src = (min_x_src + max_x_src) / 2.0
    cy_src = (min_y_src + max_y_src) / 2.0
    
    align_angle = get_longest_edge_angle(dst_poly) if auto_align else 0.0
    total_rot = align_angle + rotation
    
    def local_transform(p):
        tx, ty = p[0] - cx_src, p[1] - cy_src
        if flip == "horizontal":
            tx = -tx
        elif flip == "vertical":
            ty = -ty
            
        rad = math.radians(total_rot)
        rx = tx * math.cos(rad) - ty * math.sin(rad)
        ry = tx * math.sin(rad) + ty * math.cos(rad)
        return (rx, ry)
        
    trans_src_pts = [local_transform(p) for p in src_poly]
    ts_xs = [p[0] for p in trans_src_pts]
    ts_ys = [p[1] for p in trans_src_pts]
    ts_min_x, ts_max_x = min(ts_xs), max(ts_xs)
    ts_min_y, ts_max_y = min(ts_ys), max(ts_ys)
    ts_w = ts_max_x - ts_min_x
    ts_h = ts_max_y - ts_min_y
    
    xs_dst = [p[0] for p in dst_poly]
    ys_dst = [p[1] for p in dst_poly]
    min_x_dst, max_x_dst = min(xs_dst), max(xs_dst)
    min_y_dst, max_y_dst = min(ys_dst), max(ys_dst)
    dst_w = max_x_dst - min_x_dst
    dst_h = max_y_dst - min_y_dst
    
    if sizing_mode == "stretch":
        scale_x = dst_w / ts_w if ts_w > 0 else 1.0
        scale_y = dst_h / ts_h if ts_h > 0 else 1.0
        dx = min_x_dst - ts_min_x * scale_x
        dy = min_y_dst - ts_min_y * scale_y
        def map_pt(p):
            fx, fy = local_transform(p)
            return (fx * scale_x + dx, fy * scale_y + dy)
    else: # "cover"
        scale_factor = max(dst_w / ts_w, dst_h / ts_h) if (ts_w > 0 and ts_h > 0) else 1.0
        dx = min_x_dst + (dst_w - ts_w * scale_factor) / 2.0 - ts_min_x * scale_factor
        dy = min_y_dst + (dst_h - ts_h * scale_factor) / 2.0 - ts_min_y * scale_factor
        def map_pt(p):
            fx, fy = local_transform(p)
            return (fx * scale_factor + dx, fy * scale_factor + dy)
            
    m0 = map_pt((cx_src, cy_src))
    m1 = map_pt((cx_src + 1.0, cy_src))
    m2 = map_pt((cx_src, cy_src + 1.0))
    
    a = m1[0] - m0[0]
    b = m1[1] - m0[1]
    c = m2[0] - m0[0]
    d = m2[1] - m0[1]
    e = m0[0] - a * cx_src - c * cy_src
    f = m0[1] - b * cx_src - d * cy_src
    
    transform_matrix_str = f"matrix({a:.6f},{b:.6f},{c:.6f},{d:.6f},{e:.6f},{f:.6f})"
    
    return map_pt, transform_matrix_str

def calculate_tiled_placement_transforms(src_poly, dst_poly, sizing_mode="stretch", rotation=0.0, flip="none", auto_align=True):
    if sizing_mode not in ("tile_stretch", "tile_ratio"):
        map_pt, matrix_str = calculate_placement_transform(src_poly, dst_poly, sizing_mode, rotation, flip, auto_align)
        return [map_pt], [matrix_str]
        
    xs_src = [p[0] for p in src_poly]
    ys_src = [p[1] for p in src_poly]
    min_x_src, max_x_src = min(xs_src), max(xs_src)
    min_y_src, max_y_src = min(ys_src), max(ys_src)
    cx_src = (min_x_src + max_x_src) / 2.0
    cy_src = (min_y_src + max_y_src) / 2.0
    w_src = max_x_src - min_x_src
    h_src = max_y_src - min_y_src
    
    align_angle = get_longest_edge_angle(dst_poly) if auto_align else 0.0
    total_rot = align_angle + rotation
    
    xs_dst = [p[0] for p in dst_poly]
    ys_dst = [p[1] for p in dst_poly]
    cx_dst = (min(xs_dst) + max(xs_dst)) / 2.0
    cy_dst = (min(ys_dst) + max(ys_dst)) / 2.0
    
    def rotate_pt(p, angle, cx, cy):
        tx, ty = p[0] - cx, p[1] - cy
        rad = math.radians(angle)
        rx = tx * math.cos(rad) - ty * math.sin(rad) + cx
        ry = tx * math.sin(rad) + ty * math.cos(rad) + cy
        return (rx, ry)
        
    dst_poly_aligned = [rotate_pt(p, -total_rot, cx_dst, cy_dst) for p in dst_poly]
    da_xs = [p[0] for p in dst_poly_aligned]
    da_ys = [p[1] for p in dst_poly_aligned]
    da_min_x, da_max_x = min(da_xs), max(da_xs)
    da_min_y, da_max_y = min(da_ys), max(da_ys)
    W = da_max_x - da_min_x
    H = da_max_y - da_min_y
    
    scale_y = H / h_src if h_src > 0 else 1.0
    if sizing_mode == "tile_stretch":
        N = max(1, round(W / (w_src * scale_y))) if w_src > 0 else 1
        scale_x = W / (N * w_src) if w_src > 0 else 1.0
    else: # "tile_ratio"
        scale_x = scale_y
        w_tile = w_src * scale_x
        N = max(1, math.ceil(W / w_tile)) if w_tile > 0 else 1
        
    map_pt_list = []
    matrix_str_list = []
    
    for k in range(N):
        def make_map_pt_k(tile_idx):
            def map_pt_k(p):
                tx, ty = p[0] - min_x_src, p[1] - min_y_src
                if flip == "horizontal":
                    tx = w_src - tx
                elif flip == "vertical":
                    ty = h_src - ty
                sx = tx * scale_x
                sy = ty * scale_y
                ax = da_min_x + tile_idx * w_src * scale_x + sx
                ay = da_min_y + sy
                return rotate_pt((ax, ay), total_rot, cx_dst, cy_dst)
            return map_pt_k
            
        map_pt_k = make_map_pt_k(k)
        map_pt_list.append(map_pt_k)
        
        m0 = map_pt_k((cx_src, cy_src))
        m1 = map_pt_k((cx_src + 1.0, cy_src))
        m2 = map_pt_k((cx_src, cy_src + 1.0))
        
        a = m1[0] - m0[0]
        b = m1[1] - m0[1]
        c = m2[0] - m0[0]
        d = m2[1] - m0[1]
        e = m0[0] - a * cx_src - c * cy_src
        f = m0[1] - b * cx_src - d * cy_src
        
        matrix_str_list.append(f"matrix({a:.6f},{b:.6f},{c:.6f},{d:.6f},{e:.6f},{f:.6f})")
        
    return map_pt_list, matrix_str_list
