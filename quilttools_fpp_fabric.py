#!/usr/bin/env python3
import math
import inkex
from lxml import etree
import quilttools_fpp_core as core

def pack_fabric_strip(boxes, fabric_width_px):
    sorted_boxes = sorted(boxes, key=lambda b: b[1], reverse=True)
    shelves = []
    total_height = 0
    
    for w, h in sorted_boxes:
        if w > fabric_width_px:
            if h <= fabric_width_px:
                w, h = h, w
            else:
                total_height += max(w, h)
                continue
                
        placed = False
        for idx, (used_w, shelf_h) in enumerate(shelves):
            if used_w + w <= fabric_width_px:
                shelves[idx] = (used_w + w, shelf_h)
                placed = True
                break
        if not placed:
            shelves.append([w, h])
            
    total_height += sum(s[1] for s in shelves)
    return total_height

def pack_fabric_strip_with_coords(boxes, fabric_width_px):
    sorted_boxes = sorted(enumerate(boxes), key=lambda x: x[1][1], reverse=True)
    
    shelves = []
    total_height = 0
    placements = {}
    
    for orig_idx, (w, h, r_obj) in sorted_boxes:
        best_w, best_h = w, h
        if best_w > fabric_width_px:
            if best_h <= fabric_width_px:
                best_w, best_h = best_h, best_w
            else:
                shelf_y = total_height
                placements[orig_idx] = (0, shelf_y, best_w, best_h)
                total_height += max(best_w, best_h)
                continue
                
        placed = False
        for sh in shelves:
            if sh['used_w'] + best_w <= fabric_width_px:
                placements[orig_idx] = (sh['used_w'], sh['y_offset'], best_w, best_h)
                sh['used_w'] += best_w
                placed = True
                break
        if not placed:
            shelf_y = total_height
            shelves.append({
                'used_w': best_w,
                'height': best_h,
                'y_offset': shelf_y,
            })
            placements[orig_idx] = (0, shelf_y, best_w, best_h)
            total_height += best_h
            
    return total_height, placements

def calculate_fabric_requirements(block_data, finished_size_in, wof_in=40.0):
    all_pts = [pt for r in block_data.tree.leaf_regions() for pt in r.polygon]
    if not all_pts:
        return []
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    orig_w = max(xs) - min(xs)
    orig_h = max(ys) - min(ys)
    if orig_w <= 0 or orig_h <= 0:
        return []
        
    scale = finished_size_in * core.PX_PER_INCH / max(orig_w, orig_h)
    
    def get_padded_poly(poly):
        sc_poly = [(pt[0] * scale, pt[1] * scale) for pt in poly]
        padded = core.offset_polygon(sc_poly, 72.0, miter_limit=2.0)
        if not padded:
            sc_xs = [pt[0] for pt in sc_poly]
            sc_ys = [pt[1] for pt in sc_poly]
            padded = [
                (min(sc_xs) - 72.0, min(sc_ys) - 72.0),
                (max(sc_xs) + 72.0, min(sc_ys) - 72.0),
                (max(sc_xs) + 72.0, max(sc_ys) + 72.0),
                (min(sc_xs) - 72.0, max(sc_ys) + 72.0)
            ]
        return padded

    def get_fixed_box(poly):
        padded = get_padded_poly(poly)
        w = max(pt[0] for pt in padded) - min(pt[0] for pt in padded)
        h = max(pt[1] for pt in padded) - min(pt[1] for pt in padded)
        return w, h

    def get_free_box(poly):
        padded = get_padded_poly(poly)
        min_area = float('inf')
        best_w, best_h = 0, 0
        n = len(padded)
        for i in range(n):
            p1, p2 = padded[i], padded[(i + 1) % n]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            d_len = math.hypot(dx, dy)
            if d_len < 1e-4:
                continue
            rad = -math.atan2(dy, dx)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            rotated = []
            for pt in padded:
                rotated.append((pt[0]*cos_a - pt[1]*sin_a, pt[0]*sin_a + pt[1]*cos_a))
            min_x = min(pt[0] for pt in rotated)
            max_x = max(pt[0] for pt in rotated)
            min_y = min(pt[1] for pt in rotated)
            max_y = max(pt[1] for pt in rotated)
            w = max_x - min_x
            h = max_y - min_y
            area = w * h
            if area < min_area:
                min_area = area
                best_w, best_h = w, h
        if best_w > best_h:
            best_w, best_h = best_h, best_w
        return best_w, best_h

    regions = block_data.tree.leaf_regions()
    color_mode = block_data.prefs.get("color_mode", "piece")
    user_colors = block_data.prefs.get("custom_colors", {})
    
    fabric_groups = {}
    for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
        color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
        if not color_hex:
            color_hex = core.get_color_for_label(r.label, color_mode, idx)
        if color_hex not in fabric_groups:
            fabric_groups[color_hex] = []
        fabric_groups[color_hex].append(r)

    wof_px = wof_in * core.PX_PER_INCH
    fq_width_px = 21.0 * core.PX_PER_INCH
    
    fabric_estimates = []
    for color_hex, grp in fabric_groups.items():
        fixed_boxes = [get_fixed_box(r.polygon) for r in grp]
        free_boxes = [get_free_box(r.polygon) for r in grp]
        
        fixed_height_px = pack_fabric_strip(fixed_boxes, wof_px)
        free_height_px = pack_fabric_strip(free_boxes, wof_px)
        
        fq_fixed_height_px = pack_fabric_strip(fixed_boxes, fq_width_px)
        fq_free_height_px = pack_fabric_strip(free_boxes, fq_width_px)
        
        fabric_estimates.append({
            "color": color_hex,
            "pieces_count": len(grp),
            "fixed_in": fixed_height_px / core.PX_PER_INCH,
            "free_in": free_height_px / core.PX_PER_INCH,
            "fq_fixed_in": fq_fixed_height_px / core.PX_PER_INCH,
            "fq_free_in": fq_free_height_px / core.PX_PER_INCH,
            "regions": grp
        })
        
    return fabric_estimates

def draw_fabric_layout_map(svg, block_data, finished_size_in, wof_in=40.0):
    for layer in svg.findall(f".//{{{core.SVG_NS}}}g"):
        if layer.get(f"{{{core.INKSCAPE_NS}}}label") == "FPP Fabric Layout Map":
            layer.getparent().remove(layer)
            
    fabric_layer = etree.Element(
        "{%s}g" % core.SVG_NS,
        id="fpp-fabric-layout-map",
        **{
            f"{{{core.INKSCAPE_NS}}}label": "FPP Fabric Layout Map",
            f"{{{core.INKSCAPE_NS}}}groupmode": "layer",
            "style": "display:inline;",
        },
    )
    svg.append(fabric_layer)
    
    wof_px = wof_in * core.PX_PER_INCH
    fabric_estimates = calculate_fabric_requirements(block_data, finished_size_in, wof_in)
    
    user_colors = block_data.prefs.get("custom_colors", {})
    unique_colors = sorted(list(set(est["color"] for est in fabric_estimates)))
    color_codes = core.assign_color_codes(unique_colors, block_data.prefs.get("color_code_overrides", ""))
    
    start_x = 900.0
    start_y = 100.0
    
    etree.SubElement(
        fabric_layer,
        "{%s}text" % core.SVG_NS,
        x=str(start_x),
        y=str(start_y - 40),
        style="font-size:20px;font-family:sans-serif;font-weight:bold;fill:#333333;",
    ).text = f"Fabric Cut Layout Map (WOF = {wof_in}\", Size = {finished_size_in}\")"
    
    curr_y = start_y
    for est in fabric_estimates:
        color_hex = est["color"]
        code = color_codes.get(color_hex, "FAB")
        
        all_pts = [pt for r in block_data.tree.leaf_regions() for pt in r.polygon]
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        scale = finished_size_in * core.PX_PER_INCH / max(max(xs)-min(xs), max(ys)-min(ys))
        
        boxes = []
        for r in est["regions"]:
            sc_poly = [(pt[0]*scale, pt[1]*scale) for pt in r.polygon]
            padded = core.offset_polygon(sc_poly, 72.0, miter_limit=2.0)
            if not padded:
                sc_xs = [pt[0] for pt in sc_poly]
                sc_ys = [pt[1] for pt in sc_poly]
                padded = [
                    (min(sc_xs)-72.0, min(sc_ys)-72.0),
                    (max(sc_xs)+72.0, min(sc_ys)-72.0),
                    (max(sc_xs)+72.0, max(sc_ys)+72.0),
                    (min(sc_xs)-72.0, max(sc_ys)+72.0)
                ]
            w = max(pt[0] for pt in padded) - min(pt[0] for pt in padded)
            h = max(pt[1] for pt in padded) - min(pt[1] for pt in padded)
            boxes.append((w, h, r))
            
        total_h, placements = pack_fabric_strip_with_coords(boxes, wof_px)
        
        if total_h <= 0:
            continue
            
        etree.SubElement(
            fabric_layer,
            "{%s}text" % core.SVG_NS,
            x=str(start_x),
            y=str(curr_y - 10),
            style="font-size:12px;font-family:sans-serif;font-weight:bold;fill:#333333;",
        ).text = f"Fabric {code} ({color_hex}) - Packed Height: {total_h/core.PX_PER_INCH:.1f}\" (Qty: {len(boxes)} pieces)"
        
        etree.SubElement(
            fabric_layer,
            "{%s}rect" % core.SVG_NS,
            x=str(start_x),
            y=str(curr_y),
            width=str(wof_px),
            height=str(total_h),
            style=f"fill:none;stroke:{color_hex};stroke-width:2.0;stroke-dasharray:6,6;",
        )
        
        for idx, (w, h, r) in enumerate(boxes):
            px, py, pw, ph = placements[idx]
            etree.SubElement(
                fabric_layer,
                "{%s}rect" % core.SVG_NS,
                x=str(start_x + px),
                y=str(curr_y + py),
                width=str(pw),
                height=str(ph),
                style=f"fill:{color_hex};fill-opacity:0.4;stroke:#333333;stroke-width:1.0;stroke-linejoin:round;",
            )
            etree.SubElement(
                fabric_layer,
                "{%s}text" % core.SVG_NS,
                x=str(start_x + px + pw/2),
                y=str(curr_y + py + ph/2),
                style="font-size:11px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
            ).text = f"{r.label}"
            
        curr_y += total_h + 80.0
