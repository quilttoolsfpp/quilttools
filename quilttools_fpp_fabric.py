#!/usr/bin/env python3
"""Fabric requirement estimation and cutting-layout rendering.

Two modes (DESIGN_fabric_cutplan.md):
  * FPP foundation: padded bounding boxes (3/4" pad) — rough-cut oversize,
    calculate_fabric_requirements / draw_fabric_layout_map (unchanged
    behaviour).
  * Template: exact SA-offset shapes planned into strips/subcuts/batches
    by quilttools_cutplan — calculate_template_requirements /
    draw_cutting_plan_map.
"""
import math
import re

import inkex
from lxml import etree
import quilttools_fpp_core as core
import quilttools_cutplan as cutplan

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

def _block_scale(block_data, finished_size_in):
    all_pts = [pt for r in block_data.tree.leaf_regions() for pt in r.polygon]
    if not all_pts:
        return None
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    orig_w = max(xs) - min(xs)
    orig_h = max(ys) - min(ys)
    if orig_w <= 0 or orig_h <= 0:
        return None
    return finished_size_in * core.PX_PER_INCH / max(orig_w, orig_h)

def region_colors(block_data):
    """{region_id: color_hex} using saved custom colors then palette."""
    regions = block_data.tree.leaf_regions()
    color_mode = block_data.prefs.get("color_mode", "piece")
    user_colors = block_data.prefs.get("custom_colors", {})
    out = {}
    for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
        color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
        if not color_hex:
            color_hex = core.get_color_for_label(r.label, color_mode, idx)
        out[r.id] = color_hex
    return out

def _label_prefix(label):
    m = re.match(r"^([A-Za-z]+)", label or "")
    return m.group(1).upper() if m else ""


def fabric_estimate(pieces, usable_wof=41.0):
    """Group pieces by color, calculate fixed/free bounding boxes,
    and pack them to estimate fabric requirements.
    
    pieces: list of (poly_in, color_hex) or (poly_in, color_hex, meta)
    """
    fabric_groups = {}
    for item in pieces:
        if len(item) == 3:
            poly, color, meta = item
        else:
            poly, color = item
            meta = {}
        if color not in fabric_groups:
            fabric_groups[color] = []
        fabric_groups[color].append((poly, meta))
        
    wof_px = usable_wof * core.PX_PER_INCH
    
    def get_padded_poly(poly, meta):
        sc_poly = [(pt[0] * core.PX_PER_INCH, pt[1] * core.PX_PER_INCH) for pt in poly]
        pad_val = 72.0
        if meta and (meta.get("is_bg") or meta.get("is_applique") or meta.get("is_pieced")):
            pad_val = 24.0 # 1/4" seam allowance padding instead of 3/4" FPP
        padded = core.offset_polygon(sc_poly, pad_val, miter_limit=2.0)
        if not padded:
            sc_xs = [pt[0] for pt in sc_poly]
            sc_ys = [pt[1] for pt in sc_poly]
            padded = [
                (min(sc_xs) - pad_val, min(sc_ys) - pad_val),
                (max(sc_xs) + pad_val, min(sc_ys) - pad_val),
                (max(sc_xs) + pad_val, max(sc_ys) + pad_val),
                (min(sc_xs) - pad_val, max(sc_ys) + pad_val)
            ]
        return padded

    def get_fixed_box(poly, meta):
        padded = get_padded_poly(poly, meta)
        w = max(pt[0] for pt in padded) - min(pt[0] for pt in padded)
        h = max(pt[1] for pt in padded) - min(pt[1] for pt in padded)
        return w, h

    def get_free_box(poly, meta):
        padded = get_padded_poly(poly, meta)
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

    estimates = {}
    for color, polys_with_meta in fabric_groups.items():
        fixed_boxes = [get_fixed_box(p, m) for p, m in polys_with_meta]
        free_boxes = [get_free_box(p, m) for p, m in polys_with_meta]
        
        fixed_height_px = pack_fabric_strip(fixed_boxes, wof_px)
        free_height_px = pack_fabric_strip(free_boxes, wof_px)
        
        exceeds_wof = any(w > wof_px and h > wof_px for w, h in fixed_boxes)
        
        estimates[color] = {
            "pieces_count": len(polys_with_meta),
            "fixed_in": fixed_height_px / core.PX_PER_INCH,
            "free_in": free_height_px / core.PX_PER_INCH,
            "exceeds_wof": exceeds_wof
        }
    return estimates


def calculate_fabric_requirements(block_data, finished_size_in, wof_in=40.0,
                                  only_prefixes=None):
    """FPP padded-box estimates. only_prefixes limits the calculation to
    regions whose section letter is in the set (hybrid exports: the
    Always-FPP sections)."""
    scale = _block_scale(block_data, finished_size_in)
    if scale is None:
        return []

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
    if only_prefixes is not None:
        regions = [r for r in regions
                   if _label_prefix(r.label) in only_prefixes]
    colors = region_colors(block_data)

    fabric_groups = {}
    for r in sorted(regions, key=lambda x: x.label):
        color_hex = colors[r.id]
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


# ---------------------------------------------------------------------------
# Template mode: exact shapes via the cutplan engine
# ---------------------------------------------------------------------------

def pieces_from_block(block_data, finished_size_in, exclude_prefixes=None):
    """Leaf regions -> cutplan piece dicts (inches, finished size), with
    piece_meta technique/grain tags attached. Returns (pieces, colors).
    exclude_prefixes: section letters to leave out (Always-FPP sections)."""
    block_kind = block_data.prefs.get("block_kind", "fpp")
    scale = _block_scale(block_data, finished_size_in)
    if scale is None:
        return [], {}
    colors = region_colors(block_data)
    meta_all = block_data.piece_meta() if hasattr(block_data, "piece_meta") \
        else (block_data.prefs.get("piece_meta") or {})
    to_in = scale / core.PX_PER_INCH
    pieces = []

    # Handle background for applique blocks
    if block_kind == "applique":
        bg_color = block_data.prefs.get("bg_color", "#ffffff")
        if not block_data.prefs.get("bypass_custom_colors", False):
            custom_colors = block_data.prefs.get("custom_colors", {})
            bg_color = custom_colors.get("bg", bg_color)
        colors["bg"] = bg_color
        
        outline_in = [(p[0] * to_in, p[1] * to_in) for p in block_data.tree.regions[block_data.tree.root_id].polygon]
        pieces.append({
            "id": "bg",
            "polygon": outline_in,
            "fabric": bg_color,
            "qty": 1,
            "label": "BG",
            "meta": {"technique": "template", "is_bg": True},
        })

    for r in sorted(block_data.tree.leaf_regions(), key=lambda x: x.label):
        if exclude_prefixes and _label_prefix(r.label) in exclude_prefixes:
            continue
        meta = dict(meta_all.get(str(r.id)) or {})
        if block_kind == "applique":
            meta["is_applique"] = True
        elif block_kind == "pieced":
            meta["is_pieced"] = True
            
        pieces.append({
            "id": str(r.id),
            "polygon": [(p[0] * to_in, p[1] * to_in) for p in r.polygon],
            "fabric": colors[r.id],
            "qty": 1,
            "label": r.label,
            "meta": meta,
        })
    return pieces, colors


def calculate_template_requirements(block_data, finished_size_in, options=None,
                                    fpp_prefixes=None):
    """Exact-template cut plan for a block. options are cutplan options
    (wof_in, sa_in, oversize_batch, use_techniques, ...).

    fpp_prefixes: section letters delivered as FPP foundations in a hybrid
    export — their pieces are excluded from the template plan and costed
    with the padded FPP estimate instead (returned per fabric as fpp_in and
    folded into total_in).

    Returns {"plan": <cutplan result>, "per_fabric": [{color, pieces_count,
    total_in, fq_total_in, lines, fpp_in, fpp_pieces}, ...],
    "fpp_prefixes": set}.
    """
    options = dict(options or {})
    fpp_prefixes = set(fpp_prefixes or [])
    pieces, _colors = pieces_from_block(block_data, finished_size_in,
                                        exclude_prefixes=fpp_prefixes)

    wof_in = float(options.get("wof_in", 40.0))
    fpp_by_fab = {}
    if fpp_prefixes:
        for est in calculate_fabric_requirements(
                block_data, finished_size_in, wof_in,
                only_prefixes=fpp_prefixes):
            fpp_by_fab[est["color"]] = est

    if not pieces and not fpp_by_fab:
        return {"plan": {"fabrics": {}, "warnings": [], "notes": []},
                "per_fabric": [], "fpp_prefixes": fpp_prefixes}
    plan = cutplan.plan_cutting(pieces, options) if pieces else \
        {"fabrics": {}, "warnings": [], "notes": []}

    # Fat-quarter feasibility: re-plan at 21" usable width.
    fq_plan = {"fabrics": {}}
    if pieces:
        fq_opt = dict(options)
        fq_opt["wof_in"] = 21.0
        fq_plan = cutplan.plan_cutting(pieces, fq_opt)

    per_fabric = []
    counts = {}
    for p in pieces:
        counts[p["fabric"]] = counts.get(p["fabric"], 0) + p["qty"]
    all_fabs = sorted(set(plan["fabrics"]) | set(fpp_by_fab),
                      key=str)
    for fab in all_fabs:
        res = plan["fabrics"].get(fab)
        fq_res = fq_plan["fabrics"].get(fab)
        fpp_est = fpp_by_fab.get(fab)
        fpp_in = fpp_est["fixed_in"] if fpp_est else 0.0
        tpl_in = res["total_length_in"] if res else 0.0

        # Calculate total and FQ total
        total_in = tpl_in + fpp_in
        fq_total_in = (fq_res["total_length_in"] + fpp_in) if fq_res else (fpp_in if fpp_est else None)

        suggested = suggest_purchase(total_in, fq_total_in)

        if (suggested == "Fat Eighth (FE)" or suggested == "Fat Quarter (FQ)") and fq_res:
            plan["fabrics"][fab] = fq_res
            plan["fabrics"][fab]["wof_in"] = 21.0
            plan["fabrics"][fab]["fq_total_in"] = fq_total_in
            plan["fabrics"][fab]["suggested_purchase"] = suggested
            tpl_in = fq_res["total_length_in"]
        else:
            if res:
                plan["fabrics"][fab]["wof_in"] = wof_in
                plan["fabrics"][fab]["fq_total_in"] = fq_total_in
                plan["fabrics"][fab]["suggested_purchase"] = suggested

        per_fabric.append({
            "color": fab,
            "pieces_count": counts.get(fab, 0),
            "total_in": tpl_in + fpp_in,
            "fq_total_in": fq_total_in,
            "lines": cutplan.format_ops_text(plan["fabrics"][fab]) if plan["fabrics"].get(fab) else [],
            "warnings": plan["fabrics"][fab]["warnings"] if plan["fabrics"].get(fab) else [],
            "notes": plan["fabrics"][fab]["notes"] if plan["fabrics"].get(fab) else [],
            "fpp_in": fpp_in,
            "fpp_pieces": fpp_est["pieces_count"] if fpp_est else 0,
        })
    return {"plan": plan, "per_fabric": per_fabric,
            "fpp_prefixes": fpp_prefixes}


def suggest_purchase(total_in, fq_total_in):
    """Suggested purchase text matching the FPP table conventions."""
    if fq_total_in is not None and fq_total_in <= 9.0:
        return "Fat Eighth (FE)"
    if fq_total_in is not None and fq_total_in <= 18.0:
        return "Fat Quarter (FQ)"
    eighths = max(1, math.ceil(total_in / 36.0 * 8.0))
    return f"{eighths/8.0:.3f} yd ({eighths}/8 yd)"


def estimate_map_heights(plan, wof_in, target_width):
    """Predicted drawn height (px) of each fabric's cutting-map block at
    the given map width - MUST mirror draw_cutting_plan_map so the export
    can paginate the map without overflowing pages."""
    out = {}
    for fab, res in plan["fabrics"].items():
        s = target_width / wof_in
        
        is_fe = (res.get("suggested_purchase") == "Fat Eighth (FE)")
        is_fq = (res.get("suggested_purchase") == "Fat Quarter (FQ)")
        
        if is_fe or is_fq:
            draw_h_in = 9.0 if is_fe else 18.0
            h = 8.0 + draw_h_in * s
        else:
            h = 8.0  # header label
            for op in res["ops"]:
                if op["op"] == "strip":
                    h += op["height"] * s + 6.0
                elif op["op"] == "pieced_strip":
                    h += op["strips"] * (op["width"] * s + 2.0) + 14.0
                elif op["op"] == "panel":
                    h += op["height"] * s + 6.0
        out[fab] = h + 14.0  # trailing gap
    return out


def draw_cutting_plan_map(container, start_x, start_y, target_width, plan,
                          wof_in, color_codes=None, max_height=None,
                          fabrics=None):
    """Draw the template-mode cutting layout: per fabric, each strip with
    its subcut lines, pieced strips, and the nested yardage panel.

    plan is the cutplan result ({"fabrics": {...}}). Coordinates px.
    fabrics limits drawing to a subset (paginated map pages).
    Returns the y position after the last drawn row.
    """
    curr_y = start_y
    if color_codes is None:
        color_codes = {}

    for fab, res in plan["fabrics"].items():
        if fabrics is not None and fab not in fabrics:
            continue
        code = color_codes.get(fab, "FAB")
        
        suggested = res.get("suggested_purchase") or suggest_purchase(res["total_length_in"], res.get("fq_total_in"))
        is_fe = (suggested == "Fat Eighth (FE)")
        is_fq = (suggested == "Fat Quarter (FQ)")
        current_wof_in = 21.0 if (is_fe or is_fq) else res.get("wof_in", wof_in)
        map_scale = target_width / wof_in

        if max_height is not None and curr_y - start_y > max_height:
            etree.SubElement(
                container, "{%s}text" % core.SVG_NS,
                x=str(start_x), y=str(curr_y + 12),
                style="font-size:9px;font-family:sans-serif;fill:#666666;",
            ).text = "(further fabrics omitted from the map for space)"
            break

        etree.SubElement(
            container, "{%s}text" % core.SVG_NS,
            x=str(start_x), y=str(curr_y),
            style="font-size:10px;font-family:sans-serif;font-weight:bold;fill:#333333;",
        ).text = f"Fabric {code} ({fab}) - suggested: {suggested}"
        curr_y += 8.0

        if is_fe or is_fq:
            draw_h_in = 9.0 if is_fe else 18.0
            h_px = draw_h_in * map_scale
            
            etree.SubElement(
                container, "{%s}rect" % core.SVG_NS,
                x=str(start_x), y=str(curr_y),
                width=str(current_wof_in * map_scale), height=str(h_px),
                style=f"fill:{fab};fill-opacity:0.08;stroke:{fab};stroke-width:1.0;stroke-dasharray:4,4;",
            )
            
            for op in res["ops"]:
                if op["op"] == "strip":
                    for cell in op.get("cells", []):
                        cx = start_x + cell["x"] * map_scale
                        if cell.get("poly"):
                            pts = " ".join(
                                f"{cx + p[0]*map_scale:.2f},{curr_y + p[1]*map_scale:.2f}"
                                for p in cell["poly"])
                            etree.SubElement(
                                container, "{%s}polygon" % core.SVG_NS,
                                points=pts,
                                style=f"fill:{fab};fill-opacity:0.4;stroke:#333333;stroke-width:0.6;",
                            )
                        else:
                            etree.SubElement(
                                container, "{%s}rect" % core.SVG_NS,
                                x=str(cx), y=str(curr_y),
                                width=str(cell["w"] * map_scale),
                                height=str(op["height"] * map_scale),
                                style=f"fill:{fab};fill-opacity:0.4;stroke:#333333;stroke-width:0.6;",
                            )
                        if cell["labels"]:
                            fs = max(5.0, min(9.0, cell["w"] * map_scale * 0.3))
                            etree.SubElement(
                                container, "{%s}text" % core.SVG_NS,
                                x=str(cx + cell["w"] * map_scale / 2),
                                y=str(curr_y + op["height"] * map_scale / 2),
                                style=f"font-size:{fs:.1f}px;font-family:sans-serif;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                            ).text = cell["labels"][0]
                elif op["op"] == "panel":
                    for pl in op["placements"]:
                        pts = " ".join(
                            f"{start_x + p[0]*map_scale:.2f},{curr_y + p[1]*map_scale:.2f}"
                            for p in pl["poly"])
                        etree.SubElement(
                            container, "{%s}polygon" % core.SVG_NS,
                            points=pts,
                            style=f"fill:{fab};fill-opacity:0.4;stroke:#333333;stroke-width:0.6;stroke-linejoin:round;",
                        )
                        if pl["labels"]:
                            cxs = [start_x + p[0] * map_scale for p in pl["poly"]]
                            cys = [curr_y + p[1] * map_scale for p in pl["poly"]]
                            etree.SubElement(
                                container, "{%s}text" % core.SVG_NS,
                                x=str(sum(cxs) / len(cxs)),
                                y=str(sum(cys) / len(cys)),
                                style="font-size:7px;font-family:sans-serif;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                            ).text = pl["labels"][0]
            curr_y += h_px + 6.0
        else:
            for op in res["ops"]:
                if max_height is not None and curr_y - start_y > max_height:
                    etree.SubElement(
                        container, "{%s}text" % core.SVG_NS,
                        x=str(start_x), y=str(curr_y + 10),
                        style="font-size:9px;font-family:sans-serif;fill:#666666;",
                    ).text = "(map truncated for space)"
                    break
                if op["op"] == "strip":
                    h_px = op["height"] * map_scale
                    etree.SubElement(
                        container, "{%s}rect" % core.SVG_NS,
                        x=str(start_x), y=str(curr_y),
                        width=str(current_wof_in * map_scale), height=str(h_px),
                        style=f"fill:{fab};fill-opacity:0.15;stroke:{fab};stroke-width:1.0;stroke-dasharray:4,4;",
                    )
                    for cell in op.get("cells", []):
                        cx = start_x + cell["x"] * map_scale
                        if cell.get("poly"):
                            pts = " ".join(
                                f"{cx + p[0]*map_scale:.2f},{curr_y + p[1]*map_scale:.2f}"
                                for p in cell["poly"])
                            etree.SubElement(
                                container, "{%s}polygon" % core.SVG_NS,
                                points=pts,
                                style=f"fill:{fab};fill-opacity:0.4;stroke:#333333;stroke-width:0.6;",
                            )
                        else:
                            etree.SubElement(
                                container, "{%s}rect" % core.SVG_NS,
                                x=str(cx), y=str(curr_y),
                                width=str(cell["w"] * map_scale),
                                height=str(h_px),
                                style=f"fill:{fab};fill-opacity:0.4;stroke:#333333;stroke-width:0.6;",
                            )
                            if cell.get("contains", 1) == 2:
                                etree.SubElement(
                                    container, "{%s}line" % core.SVG_NS,
                                    x1=str(cx), y1=str(curr_y + h_px),
                                    x2=str(cx + cell["w"] * map_scale),
                                    y2=str(curr_y),
                                    style="stroke:#333333;stroke-width:0.5;stroke-dasharray:2,2;",
                                )
                        if cell["labels"]:
                            fs = max(5.0, min(9.0, cell["w"] * map_scale * 0.3))
                            etree.SubElement(
                                container, "{%s}text" % core.SVG_NS,
                                x=str(cx + cell["w"] * map_scale / 2),
                                y=str(curr_y + h_px / 2),
                                style=f"font-size:{fs:.1f}px;font-family:sans-serif;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                            ).text = cell["labels"][0]
                    curr_y += h_px + 6.0
                elif op["op"] == "pieced_strip":
                    h_px = op["width"] * map_scale
                    for s in range(op["strips"]):
                        etree.SubElement(
                            container, "{%s}rect" % core.SVG_NS,
                            x=str(start_x), y=str(curr_y),
                            width=str(current_wof_in * map_scale), height=str(h_px),
                            style=f"fill:{fab};fill-opacity:0.3;stroke:#333333;stroke-width:0.6;",
                        )
                        curr_y += h_px + 2.0
                    etree.SubElement(
                        container, "{%s}text" % core.SVG_NS,
                        x=str(start_x + 4), y=str(curr_y + 8),
                        style="font-size:8px;font-family:sans-serif;fill:#333333;",
                    ).text = (f"{op['strips']} x {cutplan.fmt_in(op['width'])} strips, "
                              f"join ({op['join']}) then subcut "
                              + ", ".join(f"{c['qty']}x{cutplan.fmt_in(c['length'])}"
                                          for c in op["cuts"][:4]))
                    curr_y += 14.0
                elif op["op"] == "panel":
                    h_px = op["height"] * map_scale
                    etree.SubElement(
                        container, "{%s}rect" % core.SVG_NS,
                        x=str(start_x), y=str(curr_y),
                        width=str(current_wof_in * map_scale), height=str(h_px),
                        style=f"fill:none;stroke:{fab};stroke-width:1.0;stroke-dasharray:4,4;",
                    )
                    for pl in op["placements"]:
                        pts = " ".join(
                            f"{start_x + p[0]*map_scale:.2f},{curr_y + p[1]*map_scale:.2f}"
                            for p in pl["poly"])
                        etree.SubElement(
                            container, "{%s}polygon" % core.SVG_NS,
                            points=pts,
                            style=f"fill:{fab};fill-opacity:0.4;stroke:#333333;stroke-width:0.6;stroke-linejoin:round;",
                        )
                        if pl["labels"]:
                            cxs = [start_x + p[0] * map_scale for p in pl["poly"]]
                            cys = [curr_y + p[1] * map_scale for p in pl["poly"]]
                            etree.SubElement(
                                container, "{%s}text" % core.SVG_NS,
                                x=str(sum(cxs) / len(cxs)),
                                y=str(sum(cys) / len(cys)),
                                style="font-size:7px;font-family:sans-serif;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                            ).text = pl["labels"][0]
                    curr_y += h_px + 6.0
        curr_y += 14.0
    return curr_y


def draw_fabric_layout_map(container, start_x, start_y, target_width, block_data, finished_size_in, wof_in=40.0, color_codes=None):
    fabric_estimates = calculate_fabric_requirements(block_data, finished_size_in, wof_in)

    if color_codes is None:
        unique_colors = sorted(list(set(est["color"] for est in fabric_estimates)))
        color_codes = core.assign_color_codes(unique_colors, block_data.prefs.get("color_code_overrides", ""))

    etree.SubElement(
        container,
        "{%s}text" % core.SVG_NS,
        x=str(start_x),
        y=str(start_y),
        style="font-size:14px;font-family:sans-serif;font-weight:bold;fill:#333333;",
    ).text = f"Fabric Cut Layout Map (WOF = {wof_in}\", Size = {finished_size_in}\")"

    curr_y = start_y + 25.0
    for est in fabric_estimates:
        color_hex = est["color"]
        code = color_codes.get(color_hex, "FAB")

        scale = _block_scale(block_data, finished_size_in)

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
            boxes.append((w, h, r, padded))

        total_in = est["fixed_in"]
        fq_total_in = est["fq_fixed_in"]
        suggested = suggest_purchase(total_in, fq_total_in)
        is_fe = (suggested == "Fat Eighth (FE)")
        is_fq = (suggested == "Fat Quarter (FQ)")

        if is_fe:
            current_usable_width_in = 21.0
            draw_h_in = 9.0
            current_usable_width_px = 21.0 * core.PX_PER_INCH
            total_h, placements = pack_fabric_strip_with_coords([(w, h, r) for (w, h, r, p) in boxes], current_usable_width_px)
        elif is_fq:
            current_usable_width_in = 21.0
            draw_h_in = 18.0
            current_usable_width_px = 21.0 * core.PX_PER_INCH
            total_h, placements = pack_fabric_strip_with_coords([(w, h, r) for (w, h, r, p) in boxes], current_usable_width_px)
        else:
            current_usable_width_in = wof_in
            current_usable_width_px = wof_in * core.PX_PER_INCH
            total_h, placements = pack_fabric_strip_with_coords([(w, h, r) for (w, h, r, p) in boxes], current_usable_width_px)
            draw_h_in = total_h / core.PX_PER_INCH

        if total_h <= 0:
            continue

        wof_px = wof_in * core.PX_PER_INCH
        map_scale = target_width / wof_px

        label_text = f"Fabric {code} ({color_hex}) - suggested: {suggested}"
        etree.SubElement(
            container,
            "{%s}text" % core.SVG_NS,
            x=str(start_x),
            y=str(curr_y),
            style="font-size:10px;font-family:sans-serif;font-weight:bold;fill:#333333;",
        ).text = label_text

        curr_y += 8.0

        etree.SubElement(
            container,
            "{%s}rect" % core.SVG_NS,
            x=str(start_x),
            y=str(curr_y),
            width=str(current_usable_width_px * map_scale),
            height=str(draw_h_in * core.PX_PER_INCH * map_scale),
            style=f"fill:{color_hex};fill-opacity:0.08;stroke:{color_hex};stroke-width:1.0;stroke-dasharray:4,4;",
        )

        for idx, (w, h, r, padded) in enumerate(boxes):
            px, py, pw, ph = placements[idx]

            etree.SubElement(
                container,
                "{%s}rect" % core.SVG_NS,
                x=str(start_x + px * map_scale),
                y=str(curr_y + py * map_scale),
                width=str(pw * map_scale),
                height=str(ph * map_scale),
                style="fill:none;stroke:#bbbbbb;stroke-width:0.5;stroke-dasharray:2,2;",
            )

            min_x = min(pt[0] for pt in padded)
            min_y = min(pt[1] for pt in padded)
            shifted_pts = []
            for pt in padded:
                sx = start_x + (px + (pt[0] - min_x)) * map_scale
                sy = curr_y + (py + (pt[1] - min_y)) * map_scale
                shifted_pts.append(f"{sx:.2f},{sy:.2f}")
            pts_str = " ".join(shifted_pts)

            etree.SubElement(
                container,
                "{%s}polygon" % core.SVG_NS,
                points=pts_str,
                style=f"fill:{color_hex};fill-opacity:0.4;stroke:#333333;stroke-width:0.75;stroke-linejoin:round;",
            )

            label_fs = max(6.0, min(10.0, 10.0 * map_scale * 1.5))
            etree.SubElement(
                container,
                "{%s}text" % core.SVG_NS,
                x=str(start_x + (px + pw/2) * map_scale),
                y=str(curr_y + (py + ph/2) * map_scale),
                style=f"font-size:{label_fs:.1f}px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
            ).text = f"{r.label}"

        curr_y += draw_h_in * core.PX_PER_INCH * map_scale + 20.0
    return curr_y


def calculate_quilt_fabric_requirements(quilt_data, g_quilt, wof_in, options):
    """Calculate fabric requirements for an entire quilt layout (blocks, sashing, borders, binding).
    
    quilt_data: QuiltData object
    g_quilt: XML element of the quilt layout group
    wof_in: Width of fabric in inches
    options: Dictionary or object with options (cutting_math, share_techniques)
    """
    import os
    import quilttools_placement as qplace

    ext_dir = os.path.dirname(__file__)
    lib_dir = os.path.join(ext_dir, "BlockLibrary")

    # If options is an object, convert to dict
    opt_dict = {}
    if options is not None:
        if hasattr(options, "__dict__"):
            opt_dict = vars(options)
        elif isinstance(options, dict):
            opt_dict = options

    cutting_math = opt_dict.get("cutting_math", "techniques")
    share_techniques = opt_dict.get("share_techniques", True)

    # 1. Gather all pieces
    all_pieces = []

    # 1.1 Process sashing, borders, binding, empty/plain blocks
    for cell_id, cell_info in quilt_data.cells.items():
        role = cell_info.get("role")
        state = cell_info.get("state")
        poly = cell_info.get("polygon")
        pb = cell_info.get("placed_block")

        if state == "placed" and pb:
            continue

        cell_el = g_quilt.find(f".//{{{core.SVG_NS}}}*[@id='{cell_id}']")
        color = None
        if cell_el is not None:
            poly_el = cell_el.find(f".//{{{core.SVG_NS}}}polygon")
            if poly_el is not None:
                color = core.resolve_element_fill(poly_el)
            else:
                color = core.resolve_element_fill(cell_el)
        if not color:
            color = "#ffffff"

        poly_in = [(p[0] / core.PX_PER_INCH, p[1] / core.PX_PER_INCH) for p in poly]

        all_pieces.append({
            "id": cell_id,
            "polygon": poly_in,
            "fabric": color,
            "qty": 1,
            "label": cell_id.replace("quilt-cell-", ""),
            "meta": {}
        })

    # 1.2 Process placed block cells
    for cell_id, cell_info in quilt_data.cells.items():
        state = cell_info.get("state")
        pb = cell_info.get("placed_block")
        if state != "placed" or not pb:
            continue

        source_rel = pb["source"]
        rot = pb.get("rotation", 0.0)
        flp = pb.get("flip", "none")
        sm = pb.get("sizing_mode", "stretch")
        dst_poly = cell_info["polygon"]
        cell_el = g_quilt.find(f".//{{{core.SVG_NS}}}*[@id='{cell_id}']")

        import_path = os.path.join(lib_dir, source_rel)
        if not os.path.exists(import_path):
            import_path = os.path.join(ext_dir, source_rel)

        if not os.path.exists(import_path):
            continue

        try:
            doc_lib = etree.parse(import_path)
            desc_el = doc_lib.getroot().find(f".//{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
            lib_bd = None
            if desc_el is not None and desc_el.text:
                lib_bd = core.BlockData.from_json(desc_el.text)

            all_L_pts = []
            if lib_bd and lib_bd.tree:
                lib_regions = lib_bd.tree.leaf_regions()
                all_L_pts = [pt for r in lib_regions for pt in r.polygon]
            if not all_L_pts:
                lib_w = 96.0
                lib_h = 96.0
                try:
                    w_str = doc_lib.getroot().get("width") or "100px"
                    h_str = doc_lib.getroot().get("height") or "100px"
                    if "in" in w_str:
                        lib_w = float(w_str.replace("in", "")) * core.PX_PER_INCH
                    elif "px" in w_str:
                        lib_w = float(w_str.replace("px", ""))
                    else:
                        lib_w = float(re.sub(r"[^\d.]", "", w_str))
                    if "in" in h_str:
                        lib_h = float(h_str.replace("in", "")) * core.PX_PER_INCH
                    elif "px" in h_str:
                        lib_h = float(h_str.replace("px", ""))
                    else:
                        lib_h = float(re.sub(r"[^\d.]", "", h_str))
                except:
                    pass
                all_L_pts = [(0, 0), (lib_w, 0), (lib_w, lib_h), (0, lib_h)]

            map_pt_list, _ = qplace.calculate_tiled_placement_transforms(
                all_L_pts, dst_poly, sizing_mode=sm, rotation=rot, flip=flp, auto_align=True
            )

            if lib_bd and lib_bd.tree:
                lib_regions = lib_bd.tree.leaf_regions()
                user_colors = lib_bd.prefs.get("custom_colors", {})
                color_mode = lib_bd.prefs.get("color_mode", "piece")
                piece_meta = lib_bd.prefs.get("piece_meta", {})
                block_kind = lib_bd.prefs.get("block_kind", "fpp")

                # Handle background for applique block cells on quilt layout
                if block_kind == "applique":
                    bg_color = lib_bd.prefs.get("bg_color", "#ffffff")
                    if not lib_bd.prefs.get("bypass_custom_colors", False):
                        bg_color = user_colors.get("bg", bg_color)
                        
                    for tile_idx, map_pt in enumerate(map_pt_list):
                        color_hex = None
                        if cell_el is not None:
                            tile_el = cell_el.find(f".//{{{core.SVG_NS}}}g[@id='{cell_id}-placed-{tile_idx}']")
                            if tile_el is not None:
                                bg_path_el = tile_el.find(f".//*[@id='qt-block-bg']")
                                if bg_path_el is not None:
                                    color_hex = core.resolve_element_fill(bg_path_el)
                        if not color_hex:
                            color_hex = bg_color
                            
                        mapped_poly = [map_pt(p) for p in lib_bd.tree.regions[lib_bd.tree.root_id].polygon]
                        poly_in = [(p[0] / core.PX_PER_INCH, p[1] / core.PX_PER_INCH) for p in mapped_poly]
                        all_pieces.append({
                            "id": f"{cell_id}_bg_tile{tile_idx}",
                            "polygon": poly_in,
                            "fabric": color_hex,
                            "qty": 1,
                            "label": f"{cell_id.replace('quilt-cell-', '')}:BG",
                            "meta": {"technique": "template", "is_bg": True}
                        })

                for r_idx, r in enumerate(lib_regions):
                    meta = dict(piece_meta.get(str(r.id)) or piece_meta.get(r.id) or {})
                    if block_kind == "applique":
                        meta["is_applique"] = True
                    elif block_kind == "pieced":
                        meta["is_pieced"] = True

                    for tile_idx, map_pt in enumerate(map_pt_list):
                        mapped_poly = [map_pt(p) for p in r.polygon]
                        poly_in = [(p[0] / core.PX_PER_INCH, p[1] / core.PX_PER_INCH) for p in mapped_poly]

                        # Attempt to resolve color from canvas path
                        color_hex = None
                        if cell_el is not None:
                            tile_el = cell_el.find(f".//{{{core.SVG_NS}}}g[@id='{cell_id}-placed-{tile_idx}']")
                            if tile_el is not None:
                                path_el = tile_el.find(f".//*[@{core.FPP_REGION_ATTR}='{r.id}']")
                                if path_el is not None:
                                    color_hex = core.resolve_element_fill(path_el)

                        # Fallback to block template colors
                        if not color_hex:
                            color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
                        if not color_hex:
                            color_hex = core.get_color_for_label(r.label, color_mode, r_idx)

                        all_pieces.append({
                            "id": f"{cell_id}_{r.id}_tile{tile_idx}",
                            "polygon": poly_in,
                            "fabric": color_hex,
                            "qty": 1,
                            "label": f"{cell_id.replace('quilt-cell-', '')}:{r.label}",
                            "meta": meta
                        })
        except Exception as e:
            inkex.utils.debug(f"Warning: could not load placed block {source_rel}: {e}")
            continue

    if cutting_math == "fpp":
        est_pieces = []
        for p in all_pieces:
            est_pieces.append((p["polygon"], p["fabric"], p.get("meta", {})))
        estimates = fabric_estimate(est_pieces, usable_wof=wof_in)

        out = {}
        for color, est in estimates.items():
            out[color] = {
                "ops": [
                    {
                        "op": "panel",
                        "height": max(est["fixed_in"], est["free_in"]),
                        "pieces": est["pieces_count"],
                        "exceeds_wof": est["exceeds_wof"]
                    }
                ],
                "total_length_in": max(est["fixed_in"], est["free_in"]),
                "fq_total_in": None,
                "suggested_purchase": None,
                "warnings": ["exceeds WOF!"] if est["exceeds_wof"] else [],
                "notes": []
            }
        return {"fabrics": out, "warnings": [], "notes": []}

    else:
        cutplan_opt = {
            "sa_in": opt_dict.get("sa_in", 0.25),
            "use_techniques": (cutting_math == "techniques"),
            "share_techniques": share_techniques,
            "usable_wof_in": wof_in,
            "grain_default": opt_dict.get("grain_default", "cross"),
            "oversize_batch": opt_dict.get("oversize_batch", True)
        }

        if not share_techniques:
            for p in all_pieces:
                if "meta" in p and p["meta"]:
                    p["meta"] = dict(p["meta"])
                    tech = p["meta"].get("technique")
                    if tech:
                        p["meta"]["batch_group"] = f"{p['id']}-auto"

        plan = cutplan.plan_cutting(all_pieces, cutplan_opt)
        return plan

