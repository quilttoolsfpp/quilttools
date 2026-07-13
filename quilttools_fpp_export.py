#!/usr/bin/env python3
import math
import re

import inkex
from lxml import etree

import quilttools_fpp_core as core
import quilttools_fpp_fabric
import quilttools_nesting as nesting

# EXPORT STYLE CONFIGURATION
# Third-party developers can customize fonts, sizes, strokes, and fills here.
STYLE_CONFIG = {
    # Typography
    "font_family": "sans-serif",
    "font_size_title": "24px",
    "font_size_subtitle": "22px",
    "font_size_header": "14px",
    "font_size_body": "12px",
    "font_size_caption": "10px",
    "font_size_tiny": "9px",
    
    # Colors
    "color_dark": "#333333",
    "color_mid": "#666666",
    "color_light": "#888888",
    "color_warn": "#cc0000",
    "color_black": "#000000",
    "color_white": "#ffffff",
    "color_accent": "#0000ff",
    
    # Lines & Fills
    "seam_allowance_stroke": "#cc0000",
    "seam_allowance_stroke_width": 0.6,
    "seam_allowance_dash": "4,2",
    "seam_allowance_opacity": 0.7,
    
    "template_border_stroke": "#000000",
    "template_border_stroke_width": 2.0,
    
    "stitch_line_stroke": "#000000",
    "stitch_line_stroke_width": 2.0,
    
    "cut_line_stroke": "#000000",
    "cut_line_stroke_width": 1.5,
    "cut_line_dash": "4,4",
    
    "header_footer_line_stroke": "#dddddd",
    "header_footer_line_stroke_width": 0.5,
    
    # Tabs
    "glue_tab_fill": "#e0e0e0",
    "glue_tab_fill_opacity": 0.6,
    "align_tab_fill": "#f0f0f0",
    "align_tab_fill_opacity": 0.6,
    "tab_stroke": "#888888",
    "tab_stroke_width": 1.0,
    "tab_stroke_dash": "4,4",
    "tab_font_size": "12px",
    "tab_font_weight": "bold",
    "tab_text_color_glue": "#333333",
    "tab_text_color_align": "#888888",
}

PAGE_SIZES = {
    "letter": (8.5 * core.PX_PER_INCH, 11.0 * core.PX_PER_INCH),
    "a4": (8.27 * core.PX_PER_INCH, 11.69 * core.PX_PER_INCH),
    "a3": (11.69 * core.PX_PER_INCH, 16.54 * core.PX_PER_INCH),
}


def is_color_dark(hex_str):
    if not hex_str:
        return False
    hex_str = hex_str.strip().lower()
    
    # Handle named colors
    color_names_dark = {
        "black": True, "navy": True, "darkblue": True, "blue": True, 
        "purple": True, "maroon": True, "brown": True, "darkgreen": True,
        "indigo": True, "darkgrey": True, "darkgray": True, "darkviolet": True
    }
    if hex_str in color_names_dark:
        return color_names_dark[hex_str]
    
    # Handle hex
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 3:
        hex_str = "".join(c*2 for c in hex_str)
    if len(hex_str) != 6:
        return False
    try:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        return luminance < 0.28
    except ValueError:
        return False



def rotate_poly(poly, cx, cy, angle_deg):
    if angle_deg == 0:
        return poly
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return [
        (
            cx + (p[0] - cx) * cos_a - (p[1] - cy) * sin_a,
            cy + (p[0] - cx) * sin_a + (p[1] - cy) * cos_a,
        )
        for p in poly
    ]


def get_longest_edge_angle(poly):
    best_angle = 0
    max_len = 0
    for i in range(len(poly)):
        p1 = poly[i]
        p2 = poly[(i + 1) % len(poly)]
        length = core.pt_dist(p1, p2)
        if length > max_len:
            max_len = length
            best_angle = -core.angle_of_line(p1, p2)
            
    while best_angle > 90.0:
        best_angle -= 180.0
    while best_angle <= -90.0:
        best_angle += 180.0
        
    return best_angle


def get_line_extents(poly, axis, val):
    pts = []
    n = len(poly)
    for i in range(n):
        p1, p2 = poly[i], poly[(i + 1) % n]
        v1, v2 = p1[axis], p2[axis]
        if min(v1, v2) - 1e-3 <= val <= max(v1, v2) + 1e-3:
            if abs(v2 - v1) < 1e-3:  # Parallel
                pts.extend([p1[1 - axis], p2[1 - axis]])
            else:  # Interpolate exact crossing point
                t = (val - v1) / (v2 - v1)
                cross_val = p1[1 - axis] + t * (p2[1 - axis] - p1[1 - axis])
                pts.append(cross_val)
    if not pts:
        return None, None
    return min(pts), max(pts)


class ExportPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="step2")
        pars.add_argument("--export_type", type=str, default="fpp")
        pars.add_argument("--layout_mode", type=str, default="compact_rotate")
        pars.add_argument("--include_preview", type=inkex.Boolean, default=True)
        pars.add_argument("--separate_section_alignment_image", type=inkex.Boolean, default=False)
        pars.add_argument("--include_fabric_estimation", type=inkex.Boolean, default=True)
        pars.add_argument("--wof_in", type=float, default=40.0)
        pars.add_argument("--visualize_fabric_layout", type=inkex.Boolean, default=False)
        pars.add_argument("--include_colouring_page", type=inkex.Boolean, default=True)
        pars.add_argument("--show_section_labels", type=inkex.Boolean, default=False)
        pars.add_argument("--page_size", type=str, default="letter")
        pars.add_argument("--orientation", type=str, default="portrait")
        pars.add_argument("--margin_in", type=float, default=0.5)
        pars.add_argument("--sa_in", type=float, default=0.25)
        pars.add_argument("--spacing_in", type=float, default=0.2)
        pars.add_argument("--template_color_mode", type=str, default="none")
        pars.add_argument("--mirror_templates", type=inkex.Boolean, default=True)
        pars.add_argument("--mirror_preview", type=inkex.Boolean, default=False)
        pars.add_argument("--block_name", type=str, default="My Quilt Block")
        pars.add_argument("--designer_name", type=str, default="")
        pars.add_argument("--finished_size_in", type=float, default=12.0)
        pars.add_argument("--finished_sizes", type=str, default="")
        pars.add_argument("--template_copies", type=int, default=1)
        pars.add_argument("--copyright_notice", type=str, default="For personal use only.")
        pars.add_argument("--notebook", type=str, default="")
        pars.add_argument("--theme_override", type=str, default="")

    def effect(self):
        import quilttools_theme as qtheme
        theme = qtheme.resolve_active_theme(self.options)
        
        # Override STYLE_CONFIG with theme fonts and colors dynamically
        STYLE_CONFIG["font_family"] = theme.font("body")["family"]
        STYLE_CONFIG["font_size_title"] = f"{theme.type_pt('title')}px"
        STYLE_CONFIG["font_size_subtitle"] = f"{theme.type_pt('subtitle')}px"
        STYLE_CONFIG["font_size_header"] = f"{theme.type_pt('heading')}px"
        STYLE_CONFIG["font_size_body"] = f"{theme.type_pt('body')}px"
        STYLE_CONFIG["font_size_caption"] = f"{theme.type_pt('caption')}px"
        STYLE_CONFIG["font_size_tiny"] = f"{max(6, theme.type_pt('caption') - 1)}px"
        
        STYLE_CONFIG["color_dark"] = theme.colour("ink")
        STYLE_CONFIG["color_mid"] = theme.colour("muted")
        STYLE_CONFIG["color_light"] = theme.colour("muted")
        STYLE_CONFIG["color_warn"] = theme.colour("warning")
        STYLE_CONFIG["color_accent"] = theme.colour("accent")
        STYLE_CONFIG["color_white"] = theme.colour("background")

        g, block_data = core.find_fpp_group(self.svg)
        if block_data:
            if block_data.is_exact_library_block():
                self.options.copyright_notice = "For personal use only."
            lib_name = block_data.prefs.get("block_library_name")
            if lib_name and (not self.options.block_name or self.options.block_name == "My Quilt Block"):
                self.options.block_name = lib_name

        if self.options.action == "step1":
            self._generate_open_canvas()
        elif self.options.action == "step2":
            layout_layer = self.svg.find(f".//{{{core.SVG_NS}}}g[@id='fpp-layout-layer']")
            if layout_layer is not None:
                self._finalize_open_canvas()
            else:
                self._generate_smart_pack()

    def _get_start_page(self):
        start_page = 0
        if self.options.include_preview:
            start_page += 1
            g, block_data = core.find_fpp_group(self.svg)
            if block_data:
                regions = block_data.tree.leaf_regions()
                user_colors = block_data.prefs.get("custom_colors", {})
                color_mode = block_data.prefs.get("color_mode", "piece")
                all_colors = []
                for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
                    color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
                    if not color_hex:
                        color_hex = core.get_color_for_label(r.label, color_mode, idx)
                    all_colors.append(color_hex)
                unique_colors = set(all_colors)
                if len(unique_colors) > 10 and not self.options.separate_section_alignment_image:
                    start_page += 1
            if self.options.separate_section_alignment_image:
                start_page += 1
            if self.options.include_fabric_estimation:
                start_page += 1
        return start_page

    def _get_processed_sections(self, finished_size_in, allow_rotate):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            inkex.errormsg("No Quilt Tools FPP block found.")
            return None, None, None

        tree = block_data.tree
        self.alignment_marks = []
        tick_dist_px = 1.5 * core.PX_PER_INCH
        if hasattr(tree, "curves") and tree.curves:
            for curve in tree.curves:
                if len(curve) < 2:
                    continue
                s = [0.0]
                for k in range(1, len(curve)):
                    s.append(s[-1] + core.pt_dist(curve[k-1], curve[k]))
                total_len = s[-1]
                num_ticks = int(total_len / tick_dist_px)
                for k in range(1, num_ticks + 1):
                    target_d = k * tick_dist_px
                    idx = 0
                    while idx < len(s) - 1 and not (s[idx] <= target_d <= s[idx+1]):
                        idx += 1
                    if idx >= len(s) - 1:
                        idx = len(s) - 2
                    seg_len = s[idx+1] - s[idx]
                    t = 0.0 if seg_len < 1e-9 else (target_d - s[idx]) / seg_len
                    p1, p2 = curve[idx], curve[idx+1]
                    px = p1[0] + t * (p2[0] - p1[0])
                    py = p1[1] + t * (p2[1] - p1[1])
                    tx = p2[0] - p1[0]
                    ty = p2[1] - p1[1]
                    tlen = math.hypot(tx, ty)
                    if tlen > 1e-9:
                        tx, ty = tx / tlen, ty / tlen
                    else:
                        tx, ty = 1.0, 0.0
                    nx, ny = -ty, tx
                    self.alignment_marks.append(((px, py), (nx, ny)))

        user_colors = {}
        for path in g.findall(f".//{{{core.SVG_NS}}}path"):
            rid = path.get(core.FPP_REGION_ATTR)
            if rid:
                style = path.get("style", "")
                m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", style)
                if m:
                    user_colors[int(rid)] = m.group(1)

        # Sync and save colors permanently if they changed
        existing_colors = block_data.prefs.get("custom_colors", {})
        colors_changed = False
        for rid, col in user_colors.items():
            s_rid = str(rid)
            if existing_colors.get(s_rid) != col:
                existing_colors[s_rid] = col
                colors_changed = True
        if colors_changed:
            block_data.prefs["custom_colors"] = existing_colors
            desc = g.find(f"{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
            if desc is None:
                desc = etree.SubElement(g, "{%s}desc" % core.SVG_NS, id=core.FPP_DATA_TAG_ID)
            desc.text = block_data.to_json()
            inkex.utils.debug("Color changes detected on canvas have been automatically saved to block metadata.")

        valid_sections = {}
        bad_labels = []
        for r in tree.leaf_regions():
            if self.options.export_type == "template":
                # In template mode, each piece is its own section
                valid_sections[r.label] = [(1, r)]
            else:
                match = re.match(r"^([A-Za-z]+)(\d+)$", r.label)
                if not match:
                    bad_labels.append(r.label)
                    continue
                prefix, num = match.groups()
                prefix = prefix.upper()
                if prefix not in valid_sections:
                    valid_sections[prefix] = []
                valid_sections[prefix].append((int(num), r))

        if not valid_sections:
            inkex.errormsg("ERROR: Block has not been labeled. You must run '3. Labels & Guides > Fully Auto-Label' (or define sections manually) before exporting.")
            return None, None, None

        if bad_labels:
            inkex.errormsg(f"WARNING: Invalid labels ignored: {', '.join(bad_labels)}")

        pw, ph = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw, ph = ph, pw
        margin = self.options.margin_in * core.PX_PER_INCH
        header_gap = 0.4 * core.PX_PER_INCH
        avail_w, avail_h = pw - (margin * 2), ph - (margin * 2) - (2 * header_gap)
        sa_px = self.options.sa_in * core.PX_PER_INCH

        all_pts = [pt for r in tree.leaf_regions() for pt in r.polygon]
        if not all_pts:
            return None, None, None
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        orig_w = max(xs) - min(xs)
        orig_h = max(ys) - min(ys)
        if orig_w <= 0 or orig_h <= 0:
            return None, None, None

        if finished_size_in <= 0.0:
            scale = 1.0
        else:
            scale = finished_size_in * core.PX_PER_INCH / max(orig_w, orig_h)

        processed_sections = []
        for prefix in sorted(valid_sections.keys()):
            valid_sections[prefix].sort(key=lambda x: x[0])
            regions = [x[1] for x in valid_sections[prefix]]

            # Scale regions to target size
            regions_scaled = []
            for r in regions:
                regions_scaled.append({
                    "label": r.label,
                    "id": r.id,
                    "polygon": [(pt[0] * scale, pt[1] * scale) for pt in r.polygon]
                })

            polys = [r["polygon"] for r in regions_scaled]
            # section_outline falls back to a conservative convex hull when
            # the pieces don't union cleanly, so a section can never be
            # silently dropped or printed with a partial outline.
            hull_poly, _sound = core.section_outline(polys)
            if not hull_poly or len(hull_poly) < 3:
                continue

            cx_hull, cy_hull = core.polygon_centroid(hull_poly)

            # Local copy of regions and hull_poly to avoid mutating master
            if self.options.mirror_templates:
                hull_poly_local = [(2.0 * cx_hull - pt[0], pt[1]) for pt in hull_poly]
                regions_local = []
                for r in regions_scaled:
                    regions_local.append({
                        "label": r["label"],
                        "id": r["id"],
                        "polygon": [(2.0 * cx_hull - pt[0], pt[1]) for pt in r["polygon"]]
                    })
            else:
                hull_poly_local = list(hull_poly)
                regions_local = list(regions_scaled)

            best_angle = 0
            if allow_rotate:
                best_angle = get_longest_edge_angle(hull_poly_local)
                cx, cy = core.polygon_centroid(hull_poly_local)
                test_poly = rotate_poly(hull_poly_local, cx, cy, best_angle)
                tw = max(p[0] for p in test_poly) - min(p[0] for p in test_poly)
                th = max(p[1] for p in test_poly) - min(p[1] for p in test_poly)
                if (tw > avail_w or th > avail_h) and (th <= avail_w and tw <= avail_h):
                    best_angle -= 90

            export_regions = []
            cx, cy = core.polygon_centroid(hull_poly_local)
            if best_angle != 0:
                hull_poly_local = rotate_poly(hull_poly_local, cx, cy, best_angle)
                for r in regions_local:
                    export_regions.append(
                        {
                            "label": r["label"],
                            "id": r["id"],
                            "polygon": rotate_poly(r["polygon"], cx, cy, best_angle),
                        }
                    )
            else:
                for r in regions_local:
                    export_regions.append(
                        {"label": r["label"], "id": r["id"], "polygon": list(r["polygon"])}
                    )

            sa_poly = core.offset_polygon(hull_poly_local, sa_px, miter_limit=2.0)
            if not sa_poly:
                continue

            if self.options.export_type == "template":
                # Compute label points and include them in bounding box calculation
                lbl_points = []
                cx_sa, cy_sa = core.polygon_centroid(sa_poly)
                for k in range(len(sa_poly)):
                    p1 = sa_poly[k]
                    p2 = sa_poly[(k + 1) % len(sa_poly)]
                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    mid_x = (p1[0] + p2[0]) / 2.0
                    mid_y = (p1[1] + p2[1]) / 2.0
                    
                    vx = mid_x - cx_sa
                    vy = mid_y - cy_sa
                    perp_x = -dy
                    perp_y = dx
                    if perp_x * vx + perp_y * vy < 0:
                        perp_x, perp_y = -perp_x, -perp_y
                    plen = math.hypot(perp_x, perp_y)
                    if plen > 1e-9:
                        nx = perp_x / plen
                        ny = perp_y / plen
                    else:
                        nx, ny = 0.0, 0.0
                    
                    # Offset + text padding (20px total)
                    offset_total = 20.0
                    lbl_points.append((mid_x + nx * offset_total, mid_y + ny * offset_total))
                
                all_bbox_pts = list(sa_poly) + lbl_points
                min_x, max_x = min(p[0] for p in all_bbox_pts), max(p[0] for p in all_bbox_pts)
                min_y, max_y = min(p[1] for p in all_bbox_pts), max(p[1] for p in all_bbox_pts)
            else:
                min_x, max_x = min(p[0] for p in sa_poly), max(p[0] for p in sa_poly)
                min_y, max_y = min(p[1] for p in sa_poly), max(p[1] for p in sa_poly)

            processed_sections.append(
                {
                    "prefix": prefix,
                    "regions": export_regions,
                    "sa_poly": sa_poly,
                    "min_x": min_x,
                    "min_y": min_y,
                    "width": max_x - min_x,
                    "height": max_y - min_y,
                    "scale": scale,
                    "cx_hull": cx_hull,
                    "cx": cx,
                    "cy": cy,
                    "best_angle": best_angle,
                }
            )

        return g, block_data, processed_sections

    def _setup_layout_layer(self):
        for layer in self.svg.findall(f".//{{{core.SVG_NS}}}g"):
            if layer.get(f"{{{core.INKSCAPE_NS}}}groupmode") == "layer":
                layer.set("style", "display:none;")

        layout_layer = self.svg.find(f".//{{{core.SVG_NS}}}g[@id='fpp-layout-layer']")
        if layout_layer is not None:
            layout_layer.getparent().remove(layout_layer)

        layout_layer = etree.Element(
            "{%s}g" % core.SVG_NS,
            id="fpp-layout-layer",
            **{
                f"{{{core.INKSCAPE_NS}}}label": "FPP Layout",
                f"{{{core.INKSCAPE_NS}}}groupmode": "layer",
                "style": "display:inline;",
            },
        )
        defs = etree.SubElement(layout_layer, "{%s}defs" % core.SVG_NS)

        namedview = self.svg.find(f".//{{{core.SODIPODI_NS}}}namedview")
        if namedview is not None:
            for page_node in namedview.findall(f"{{{core.INKSCAPE_NS}}}page"):
                namedview.remove(page_node)

        return layout_layer, defs, namedview

    def _draw_preview_block(
        self, target_g, px, py, fit_w, fit_h, tree, prefs, user_colors
    ):
        all_pts = [pt for r in tree.leaf_regions() for pt in r.polygon]
        if not all_pts:
            return
        min_x, max_x = min(p[0] for p in all_pts), max(p[0] for p in all_pts)
        min_y, max_y = min(p[1] for p in all_pts), max(p[1] for p in all_pts)
        bw, bh = max_x - min_x, max_y - min_y
        if bw <= 0 or bh <= 0:
            return

        scale = min(
            (fit_w - 0.2 * core.PX_PER_INCH) / bw, (fit_h - 0.2 * core.PX_PER_INCH) / bh
        )
        center_x, center_y = px + (fit_w / 2), py + (fit_h / 2)
        block_cx, block_cy = min_x + (bw / 2), min_y + (bh / 2)

        preview_g = etree.SubElement(
            target_g, "{%s}g" % core.SVG_NS, id="fpp-block-preview"
        )
        color_mode = prefs.get("color_mode", "piece")

        for idx, r in enumerate(tree.leaf_regions()):
            sign_x = -1 if self.options.mirror_preview else 1
            scaled_poly = [
                (
                    center_x + sign_x * (p[0] - block_cx) * scale,
                    center_y + (p[1] - block_cy) * scale,
                )
                for p in r.polygon
            ]
            r_d = (
                "M {:.4f},{:.4f} ".format(*scaled_poly[0])
                + " ".join("L {:.4f},{:.4f}".format(*p) for p in scaled_poly[1:])
                + " Z"
            )
            
            fill_color = user_colors.get(str(r.id)) or user_colors.get(r.id)
            if not fill_color:
                fill_color = core.get_color_for_label(r.label, color_mode, idx)
                
            etree.SubElement(
                preview_g,
                "{%s}path" % core.SVG_NS,
                d=r_d,
                style=f"fill:{fill_color};stroke:{STYLE_CONFIG['template_border_stroke']};stroke-width:1.5;stroke-linejoin:round;",
            )
            r_cx, r_cy = core.polygon_centroid(scaled_poly)
            text_color = STYLE_CONFIG["color_white"] if is_color_dark(fill_color) else STYLE_CONFIG["color_black"]
            etree.SubElement(
                preview_g,
                "{%s}text" % core.SVG_NS,
                x=f"{r_cx:.2f}",
                y=f"{r_cy:.2f}",
                style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{text_color};",
            ).text = r.label

    def _run_pre_export_lint(self, block_data, processed_sections):
        report = []
        report.append("=========================================")
        report.append("      FPP PATTERN VALIDATION REPORT      ")
        report.append("=========================================")
        
        # Check metadata
        if not self.options.block_name or self.options.block_name == "My Quilt Block":
            report.append("[!] Metadata: Block name is default or empty.")
        if not self.options.designer_name:
            report.append("[!] Metadata: Designer Name is empty.")
            
        # Check sewing order
        steps, has_sewing_warning = core.calculate_section_sewing_order(block_data)
        approx_secs = core.unsound_union_sections(block_data)
        if has_sewing_warning:
            report.append("[!] Sewing Order: WARNING: No Y-seam-free assembly sequence exists!")
        else:
            report.append("[✓] Sewing Order: Valid Y-seam-free assembly sequence found.")
        if approx_secs:
            report.append(
                "[!] Sewing Order: geometry of section(s) "
                + ", ".join(approx_secs)
                + " could not be fully verified (pieces do not form a clean "
                "outline); the check used a conservative outline. Review "
                "these sections' piecing manually."
            )
            
        # Check colors
        user_colors = block_data.prefs.get("custom_colors", {})
        if not user_colors:
            report.append("[i] Colors: No custom colors saved; using default palette.")
        else:
            unique_custom = set(c.strip().lower() for c in user_colors.values() if c and c.strip())
            report.append(f"[✓] Colors: {len(unique_custom)} unique custom colors loaded ({len(user_colors)} pieces colored).")
            
        report.append("=========================================")
        return report

    def _generate_open_canvas(self):
        g, block_data, processed_sections = self._get_processed_sections(
            self.options.finished_size_in, allow_rotate=False
        )
        if not processed_sections:
            return
            
        lint_report = self._run_pre_export_lint(block_data, processed_sections)
        inkex.utils.debug("\n".join(lint_report))

        layout_layer, defs, _ = self._setup_layout_layer()

        pw, ph = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw, ph = ph, pw
        margin = self.options.margin_in * core.PX_PER_INCH
        header_gap = 0.4 * core.PX_PER_INCH
        avail_w, avail_h = pw - (margin * 2), ph - (margin * 2) - (2 * header_gap)
        spacing_px = self.options.spacing_in * core.PX_PER_INCH

        start_page = self._get_start_page()
        sim_page, sim_x, sim_y, sim_row_h = start_page, 0, 0, 0.0

        for sec in processed_sections:
            if sim_x + sec["width"] > avail_w:
                sim_x, sim_y, sim_row_h = 0, sim_y + sim_row_h + spacing_px, 0.0
            if sim_y + sec["height"] > avail_h:
                sim_page += 1
                sim_x, sim_y, sim_row_h = 0, 0, 0.0
            if sec["width"] > avail_w or sec["height"] > avail_h:
                sim_page += 1
                sim_x, sim_y, sim_row_h = 0, 0, sec["height"]
            sim_row_h = max(sim_row_h, sec["height"])
            sim_x += sec["width"] + spacing_px

        MAX_COLUMNS = 5
        total_pages = max(start_page + 1, sim_page + 1)
        grid_cols = min(total_pages, MAX_COLUMNS)
        grid_rows = math.ceil(total_pages / MAX_COLUMNS)
        grid_w, grid_h = grid_cols * avail_w, grid_rows * avail_h

        self.svg.set("width", f"{grid_w}")
        self.svg.set("height", f"{grid_h}")
        self.svg.set("viewBox", f"0 0 {grid_w} {grid_h}")

        if self.options.include_preview:
            px, py = 0, 0
            etree.SubElement(
                layout_layer,
                "{%s}rect" % core.SVG_NS,
                x=str(px),
                y=str(py),
                width=str(avail_w),
                height=str(avail_h),
                style="fill:none;stroke:#0000ff;stroke-width:1.5;stroke-dasharray:8,8;",
            )
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(px + 10),
                y=str(py + 20),
                style="font-size:16px;font-family:sans-serif;fill:#0000ff;",
            ).text = "Preview & Calibration"

            user_colors = block_data.prefs.get("custom_colors", {})
            self._draw_preview_block(
                layout_layer,
                px,
                py,
                avail_w,
                avail_h,
                block_data.tree,
                block_data.prefs,
                user_colors,
            )

            sq_size = 1.0 * core.PX_PER_INCH
            sq_rect = (avail_w - sq_size - 10, 10, avail_w - 10, 10 + sq_size)
            sq_g = etree.SubElement(layout_layer, "{%s}g" % core.SVG_NS)
            etree.SubElement(
                sq_g,
                "{%s}rect" % core.SVG_NS,
                x=str(px + sq_rect[0]),
                y=str(py + sq_rect[1]),
                width=str(sq_size),
                height=str(sq_size),
                style=f"fill:none;stroke:{STYLE_CONFIG['color_black']};stroke-width:1.5;",
            )
            etree.SubElement(
                sq_g,
                "{%s}text" % core.SVG_NS,
                x=str(px + sq_rect[0] + sq_size / 2),
                y=str(py + sq_rect[1] + sq_size / 2),
                style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{STYLE_CONFIG['color_black']};",
            ).text = "1 in"

        for pi in range(start_page, total_pages):
            px, py = (pi % MAX_COLUMNS) * avail_w, (pi // MAX_COLUMNS) * avail_h
            etree.SubElement(
                layout_layer,
                "{%s}rect" % core.SVG_NS,
                x=str(px),
                y=str(py),
                width=str(avail_w),
                height=str(avail_h),
                style="fill:none;stroke:#0000ff;stroke-width:1.5;stroke-dasharray:8,8;",
            )
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(px + 10),
                y=str(py + 20),
                style="font-size:16px;font-family:sans-serif;fill:#0000ff;",
            ).text = f"Page {pi - start_page + 1}"

        for i, sec in enumerate(processed_sections):
            pi = i + start_page
            px, py = (pi % MAX_COLUMNS) * avail_w, (pi // MAX_COLUMNS) * avail_h

            sec_g = etree.SubElement(
                layout_layer, "{%s}g" % core.SVG_NS, id=f"manual-sec-{sec['prefix']}"
            )
            tx, ty = px - sec["min_x"], py - sec["min_y"]
            sec_g.set("transform", f"translate({tx}, {ty})")

            sa_d = (
                "M {:.4f},{:.4f} ".format(*sec["sa_poly"][0])
                + " ".join("L {:.4f},{:.4f}".format(*p) for p in sec["sa_poly"][1:])
                + " Z"
            )
            etree.SubElement(
                sec_g,
                "{%s}path" % core.SVG_NS,
                d=sa_d,
                style="fill:none;stroke:#000000;stroke-width:1.5;stroke-dasharray:6,6;",
            )
            if self.options.export_type == "template":
                self._draw_template_edge_labels(sec_g, sec["sa_poly"])

            for r in sec["regions"]:
                r_d = (
                    "M {:.4f},{:.4f} ".format(*r["polygon"][0])
                    + " ".join("L {:.4f},{:.4f}".format(*p) for p in r["polygon"][1:])
                    + " Z"
                )
                etree.SubElement(
                    sec_g,
                    "{%s}path" % core.SVG_NS,
                    d=r_d,
                    style="fill:none;stroke:#000000;stroke-width:2.0;stroke-linejoin:round;",
                )
                
                self._draw_alignment_ticks(
                    sec_g,
                    r,
                    sec.get("scale", 1.0),
                    sec.get("cx_hull", 0.0),
                    sec.get("cx", 0.0),
                    sec.get("cy", 0.0),
                    sec.get("best_angle", 0.0),
                    self.alignment_marks,
                    block_data,
                    self.options.mirror_templates
                )
                r_cx, r_cy = core.polygon_centroid(r["polygon"])
                etree.SubElement(
                    sec_g,
                    "{%s}text" % core.SVG_NS,
                    x=f"{r_cx:.2f}",
                    y=f"{r_cy:.2f}",
                    style="font-size:14px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                ).text = r["label"]

        self.svg.append(layout_layer)
        
        if self.options.visualize_fabric_layout:
            # Resolve base size for fabric visualization
            resolved_base_size = self.options.finished_size_in
            if resolved_base_size <= 0.0:
                all_pts = [pt for r in block_data.tree.leaf_regions() for pt in r.polygon]
                if all_pts:
                    xs = [p[0] for p in all_pts]
                    ys = [p[1] for p in all_pts]
                    canvas_w = max(xs) - min(xs)
                    canvas_h = max(ys) - min(ys)
                    resolved_base_size = max(canvas_w, canvas_h) / core.PX_PER_INCH
                else:
                    resolved_base_size = 12.0
            
            for layer in self.svg.findall(f".//{{{core.SVG_NS}}}g"):
                if layer.get(f"{{{core.INKSCAPE_NS}}}label") == "FPP Fabric Layout Map":
                    layer.getparent().remove(layer)
                    
            fabric_layer = etree.SubElement(self.svg, "{%s}g" % core.SVG_NS, id="fpp-fabric-layout-map", **{
                f"{{{core.INKSCAPE_NS}}}label": "FPP Fabric Layout Map",
                f"{{{core.INKSCAPE_NS}}}groupmode": "layer",
                "style": "display:inline;"
            })
            quilttools_fpp_fabric.draw_fabric_layout_map(
                fabric_layer, 900.0, 100.0, 700.0,
                block_data, resolved_base_size, self.options.wof_in
            )
            
        inkex.utils.debug(
            "Open Canvas Generated. Freely rotate and drag items across the grids, then select 'Finalize'!"
        )

    def _finalize_open_canvas(self):
        g, block_data, processed_sections = self._get_processed_sections(
            self.options.finished_size_in, allow_rotate=False
        )
        if not processed_sections:
            return

        layout_layer = self.svg.find(f".//{{{core.SVG_NS}}}g[@id='fpp-layout-layer']")
        if layout_layer is None:
            return inkex.errormsg(
                "No Open Canvas layout found. Please run '1. Generate Workspace' first."
            )

        pw, ph = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw, ph = ph, pw
        margin = self.options.margin_in * core.PX_PER_INCH
        header_gap = 0.4 * core.PX_PER_INCH
        avail_w, avail_h = pw - (margin * 2), ph - (margin * 2) - (2 * header_gap)

        placed_polys = {}
        for sec in processed_sections:
            sec_g = layout_layer.find(f".//{{{core.SVG_NS}}}g[@id='manual-sec-{sec['prefix']}']")
            if sec_g is not None:
                user_transform = inkex.Transform(sec_g.get("transform", ""))
                placed_polys[sec["prefix"]] = [
                    user_transform.apply_to_point((p[0], p[1])) for p in sec["sa_poly"]
                ]

        spacing_px = self.options.spacing_in * core.PX_PER_INCH
        start_page = self._get_start_page()
        # Try to dynamically detect start_page from existing layout_layer grids
        detected_start_page = None
        for txt in layout_layer.findall(f".//{{{core.SVG_NS}}}text"):
            if txt.text == "Page 1":
                try:
                    tx = float(txt.get("x", 0))
                    ty = float(txt.get("y", 0))
                    px = tx - 10
                    py = ty - 20
                    col = round(px / avail_w)
                    row = round(py / avail_h)
                    detected_start_page = row * 5 + col
                    break
                except Exception:
                    pass
        if detected_start_page is not None:
            start_page = detected_start_page

        sim_page, sim_x, sim_y, sim_row_h = start_page, 0, 0, 0.0
        for sec in processed_sections:
            if sim_x + sec["width"] > avail_w:
                sim_x, sim_y, sim_row_h = 0, sim_y + sim_row_h + spacing_px, 0.0
            if sim_y + sec["height"] > avail_h:
                sim_page += 1
                sim_x, sim_y, sim_row_h = 0, 0, 0.0
            if sec["width"] > avail_w or sec["height"] > avail_h:
                sim_page += 1
                sim_x, sim_y, sim_row_h = 0, 0, sec["height"]
            sim_row_h = max(sim_row_h, sec["height"])
            sim_x += sec["width"] + spacing_px

        MAX_COLUMNS = 5
        total_pages = max(start_page + 1, sim_page + 1)
        grid_cols = min(total_pages, MAX_COLUMNS)
        grid_rows = math.ceil(total_pages / MAX_COLUMNS)
        grid_w, grid_h = grid_cols * avail_w, grid_rows * avail_h

        lint_report = self._run_pre_export_lint(block_data, processed_sections)

        has_overlap = False
        for sec1_prefix, poly1 in placed_polys.items():
            for sec2_prefix, poly2 in placed_polys.items():
                if sec1_prefix < sec2_prefix:
                    if core.polygons_overlap(poly1, poly2):
                        lint_report.append(f"[!] CRITICAL: Section {sec1_prefix} overlaps with Section {sec2_prefix}!")
                        has_overlap = True

        has_bleed = False
        for sec_prefix, poly in placed_polys.items():
            out_of_bounds = False
            for p in poly:
                if p[0] < -1.0 or p[0] > grid_w + 1.0 or p[1] < -1.0 or p[1] > grid_h + 1.0:
                    out_of_bounds = True
                    break
            if out_of_bounds:
                lint_report.append(f"[!] WARNING: Section {sec_prefix} extends outside the page layout boundaries!")
                has_bleed = True

        if not has_overlap and not has_bleed:
            lint_report.append("[✓] Layout: No overlaps or out-of-bounds pieces detected.")
        lint_report.append("=========================================")

        inkex.utils.debug("\n".join(lint_report))

        packable_items = []
        global_tab_counter = 1
        max_page_idx = start_page

        grid_max_page = total_pages - 1
        next_extra_page = grid_max_page + 1
        finalized_polys = {}

        for sec in processed_sections:
            sec_g = layout_layer.find(
                f".//{{{core.SVG_NS}}}g[@id='manual-sec-{sec['prefix']}']"
            )
            if sec_g is None:
                continue

            user_transform = inkex.Transform(sec_g.get("transform", ""))
            placed_poly = [user_transform.apply_to_point((p[0], p[1])) for p in sec["sa_poly"]]

            overlaps = False
            overlap_partner = None
            for other_prefix, other_poly in finalized_polys.items():
                if core.polygons_overlap(placed_poly, other_poly):
                    overlaps = True
                    overlap_partner = other_prefix
                    break

            if overlaps:
                target_page = next_extra_page
                next_extra_page += 1
                max_page_idx = max(max_page_idx, target_page)

                validation_report_overlap = f"[!] Layout: Section {sec['prefix']} overlaps with Section {overlap_partner} on canvas. Automatically relocated to new Page {target_page + 1} at the back."
                inkex.utils.debug(validation_report_overlap)

                rot_min_x = min(p[0] for p in placed_poly)
                rot_max_x = max(p[0] for p in placed_poly)
                rot_min_y = min(p[1] for p in placed_poly)
                rot_max_y = max(p[1] for p in placed_poly)
                rot_w = rot_max_x - rot_min_x
                rot_h = rot_max_y - rot_min_y

                page_x = (avail_w - rot_w) / 2.0
                page_y = (avail_h - rot_h) / 2.0
                
                inner_transform = inkex.Transform(f"translate({-rot_min_x}, {-rot_min_y})") @ user_transform

                packable_items.append({
                    "prefix": sec["prefix"],
                    "part_str": "",
                    "target_page": target_page,
                    "page_x": page_x,
                    "page_y": page_y,
                    "core_w": rot_w,
                    "core_h": rot_h,
                    "pad_l": 0,
                    "pad_r": 0,
                    "pad_t": 0,
                    "pad_b": 0,
                    "inner_transform": str(inner_transform),
                    "right_glue": None,
                    "left_align": None,
                    "bottom_glue": None,
                    "top_align": None,
                    "sa_poly": sec["sa_poly"],
                    "regions": sec["regions"],
                })
            else:
                finalized_polys[sec["prefix"]] = placed_poly

                abs_x_vals = []
                abs_y_vals = []
                for p in sec["sa_poly"]:
                    tp = user_transform.apply_to_point((p[0], p[1]))
                    abs_x_vals.append(tp[0])
                    abs_y_vals.append(tp[1])

                abs_x0, abs_x1 = min(abs_x_vals), max(abs_x_vals)
                abs_y0, abs_y1 = min(abs_y_vals), max(abs_y_vals)

                c_start = int(math.floor(abs_x0 / avail_w))
                c_end = int(math.floor((abs_x1 - 1e-4) / avail_w))
                r_start = int(math.floor(abs_y0 / avail_h))
                r_end = int(math.floor((abs_y1 - 1e-4) / avail_h))

                v_tabs, h_tabs = {}, {}
                for r in range(r_start, r_end + 1):
                    for c in range(c_start, c_end):
                        v_tabs[(c, r)] = global_tab_counter
                        global_tab_counter += 1
                for c in range(c_start, c_end + 1):
                    for r in range(r_start, r_end):
                        h_tabs[(c, r)] = global_tab_counter
                        global_tab_counter += 1

                for r in range(r_start, r_end + 1):
                    for c in range(c_start, c_end + 1):
                        cell_x0, cell_y0 = c * avail_w, r * avail_h
                        cell_x1, cell_y1 = cell_x0 + avail_w, cell_y0 + avail_h

                        core_x0, core_x1 = max(abs_x0, cell_x0), min(abs_x1, cell_x1)
                        core_y0, core_y1 = max(abs_y0, cell_y0), min(abs_y1, cell_y1)
                        core_w, core_h = core_x1 - core_x0, core_y1 - core_y0
                        if core_w <= 0 or core_h <= 0:
                            continue

                        target_page = r * MAX_COLUMNS + c
                        max_page_idx = max(max_page_idx, target_page)

                        inner_transform = (
                            inkex.Transform(f"translate({-core_x0}, {-core_y0})")
                            @ user_transform
                        )

                        packable_items.append(
                            {
                                "prefix": sec["prefix"],
                                "part_str": f" (Part {r - r_start + 1}-{c - c_start + 1})"
                                if (c_end > c_start or r_end > r_start)
                                else "",
                                "target_page": target_page,
                                "page_x": core_x0 - cell_x0,
                                "page_y": core_y0 - cell_y0,
                                "core_w": core_w,
                                "core_h": core_h,
                                "pad_l": 0,
                                "pad_r": 0,
                                "pad_t": 0,
                                "pad_b": 0,
                                "inner_transform": str(inner_transform),
                                "right_glue": v_tabs.get((c, r)) if c < c_end else None,
                                "left_align": v_tabs.get((c - 1, r))
                                if c > c_start
                                else None,
                                "bottom_glue": h_tabs.get((c, r)) if r < r_end else None,
                                "top_align": h_tabs.get((c, r - 1))
                                if r > r_start
                                else None,
                                "sa_poly": sec["sa_poly"],
                                "regions": sec["regions"],
                            }
                        )

        regions = block_data.tree.leaf_regions()
        user_colors = block_data.prefs.get("custom_colors", {})
        color_mode = block_data.prefs.get("color_mode", "piece")
        all_colors = []
        for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
            color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
            if not color_hex:
                color_hex = core.get_color_for_label(r.label, color_mode, idx)
            all_colors.append(color_hex)
        unique_colors = set(all_colors)

        # Resolve sizing (Use canvas size if <= 0.0)
        base_size = self.options.finished_size_in
        if base_size <= 0.0:
            all_pts = [pt for r in block_data.tree.leaf_regions() for pt in r.polygon]
            if all_pts:
                xs = [p[0] for p in all_pts]
                ys = [p[1] for p in all_pts]
                canvas_w = max(xs) - min(xs)
                canvas_h = max(ys) - min(ys)
                base_size = max(canvas_w, canvas_h) / core.PX_PER_INCH
            else:
                base_size = 12.0

        pages_list = []
        if self.options.include_preview:
            pages_list.append({"type": "cover", "sizes": [base_size]})
            if len(unique_colors) > 10 and not self.options.separate_section_alignment_image:
                pages_list.append({"type": "color_key"})
            if self.options.separate_section_alignment_image:
                pages_list.append({"type": "section_map"})

        if self.options.include_preview and self.options.include_fabric_estimation:
            pages_list.append({"type": "fabric_requirements", "size": base_size})

        current_len = len(pages_list)
        total_pages = max(max_page_idx + 1, current_len)
        for pi in range(current_len, total_pages):
            pages_list.append({
                "type": "templates",
                "size": base_size,
                "local_page_idx": pi - current_len
            })

        if self.options.include_colouring_page:
            pages_list.append({"type": "colouring"})

        page_shift = current_len - start_page
        for item in packable_items:
            item["target_page"] += page_shift

        self._render_pdf_pages(
            packable_items, pages_list, g.getparent(), block_data
        )
        

        inkex.utils.debug(
            "Finalize Complete! Custom rotations preserved and snapped seamlessly to PDF grids."
        )

    def _generate_smart_pack(self):
        g, block_data, base_sections = self._get_processed_sections(self.options.finished_size_in, allow_rotate=True)
        if not base_sections:
            return

        # Resolve sizing (Use canvas size if <= 0.0)
        base_size = self.options.finished_size_in
        if base_size <= 0.0:
            all_pts = [pt for r in block_data.tree.leaf_regions() for pt in r.polygon]
            if all_pts:
                xs = [p[0] for p in all_pts]
                ys = [p[1] for p in all_pts]
                canvas_w = max(xs) - min(xs)
                canvas_h = max(ys) - min(ys)
                base_size = max(canvas_w, canvas_h) / core.PX_PER_INCH
            else:
                base_size = 12.0

        sizes = [base_size]
        if self.options.finished_sizes:
            for sz_str in self.options.finished_sizes.split(","):
                sz_str = sz_str.strip()
                if sz_str:
                    try:
                        sz = float(sz_str)
                        if sz > 0 and sz not in sizes:
                            sizes.append(sz)
                    except ValueError:
                        pass

        lint_report = self._run_pre_export_lint(block_data, base_sections)
        inkex.utils.debug("\n".join(lint_report))

        regions = block_data.tree.leaf_regions()
        user_colors = block_data.prefs.get("custom_colors", {})
        color_mode = block_data.prefs.get("color_mode", "piece")
        all_colors = []
        for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
            color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
            if not color_hex:
                color_hex = core.get_color_for_label(r.label, color_mode, idx)
            all_colors.append(color_hex)
        unique_colors = sorted(list(set(all_colors)))

        pages_list = []
        if self.options.include_preview:
            pages_list.append({"type": "cover", "sizes": sizes})
            if len(unique_colors) > 10 and not self.options.separate_section_alignment_image:
                pages_list.append({"type": "color_key"})
            if self.options.separate_section_alignment_image:
                pages_list.append({"type": "section_map"})

        pw, ph = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw, ph = ph, pw
        margin = self.options.margin_in * core.PX_PER_INCH
        header_gap = 0.4 * core.PX_PER_INCH
        avail_w = pw - (margin * 2)
        avail_h = ph - (margin * 2) - (2 * header_gap)
        spacing_px = self.options.spacing_in * core.PX_PER_INCH
        overlap_px = 0.5 * core.PX_PER_INCH

        all_packed_items = []

        for sz in sizes:
            if self.options.include_fabric_estimation:
                pages_list.append({"type": "fabric_requirements", "size": sz})

            g_sz, _, sections = self._get_processed_sections(sz, allow_rotate=True)
            if not sections:
                continue

            size_items = []
            global_tab_counter = 1

            if sz != base_size:
                size_items.append({
                    "prefix": "CAL",
                    "part_str": "",
                    "T_w": 96.0,
                    "T_h": 96.0,
                    "core_w": 96.0,
                    "core_h": 96.0,
                    "pad_l": 0,
                    "pad_r": 0,
                    "pad_t": 0,
                    "pad_b": 0,
                    "inner_transform": "",
                    "right_glue": None,
                    "left_align": None,
                    "bottom_glue": None,
                    "top_align": None,
                    "sa_poly": [],
                    "regions": [],
                })

            # Multiple template sets: repeat every section n_copies times.
            # The nesting engine packs all copies together, so identical
            # pieces interlock across sets. Glue-tab numbering continues
            # across copies so every tab id stays unique.
            n_copies = max(1, int(self.options.template_copies))
            copy_iter = [
                (f" (Copy {ci + 1})" if n_copies > 1 else "", s)
                for ci in range(n_copies)
                for s in sections
            ]

            for copy_str, sec in copy_iter:
                if sec["width"] <= avail_w and sec["height"] <= avail_h:
                    size_items.append({
                        "prefix": sec["prefix"],
                        "part_str": "",
                        "T_w": sec["width"],
                        "T_h": sec["height"],
                        "core_w": sec["width"],
                        "core_h": sec["height"],
                        "pad_l": 0,
                        "pad_r": 0,
                        "pad_t": 0,
                        "pad_b": 0,
                        "inner_transform": str(
                            inkex.Transform(f"translate({-sec['min_x']}, {-sec['min_y']})")
                        ),
                        "right_glue": None,
                        "left_align": None,
                        "bottom_glue": None,
                        "top_align": None,
                        "sa_poly": sec["sa_poly"],
                        "regions": sec["regions"],
                        "scale": sec.get("scale", 1.0),
                        "cx_hull": sec.get("cx_hull", 0.0),
                        "cx": sec.get("cx", 0.0),
                        "cy": sec.get("cy", 0.0),
                        "best_angle": sec.get("best_angle", 0.0),
                        "copy_str": copy_str,
                    })
                else:
                    # Effective tile size: with 3+ tiles in a dimension the
                    # middle tiles carry overlap padding on both sides, so
                    # shrink the core to keep every tile within the printable
                    # area (otherwise middle tiles can never share a page).
                    eff_w = avail_w - overlap_px
                    if math.ceil(sec["width"] / eff_w) >= 3:
                        eff_w = avail_w - 2 * overlap_px
                    eff_h = avail_h - overlap_px
                    if math.ceil(sec["height"] / eff_h) >= 3:
                        eff_h = avail_h - 2 * overlap_px
                    t_cols, t_rows = (
                        math.ceil(sec["width"] / eff_w),
                        math.ceil(sec["height"] / eff_h),
                    )
                    v_tabs, h_tabs = {}, {}
                    for r in range(t_rows):
                        for c in range(t_cols - 1):
                            v_tabs[(c, r)] = global_tab_counter
                            global_tab_counter += 1
                    for c in range(t_cols):
                        for r in range(t_rows - 1):
                            h_tabs[(c, r)] = global_tab_counter
                            global_tab_counter += 1

                    for r in range(t_rows):
                        for c in range(t_cols):
                            core_w = eff_w if c < t_cols - 1 else sec["width"] - (c * eff_w)
                            core_h = (
                                eff_h if r < t_rows - 1 else sec["height"] - (r * eff_h)
                            )

                            pad_l, pad_r = (
                                overlap_px if c > 0 else 0,
                                overlap_px if c < t_cols - 1 else 0,
                            )
                            pad_t, pad_b = (
                                overlap_px if r > 0 else 0,
                                overlap_px if r < t_rows - 1 else 0,
                            )

                            shift_x = -(c * eff_w) - sec["min_x"]
                            shift_y = -(r * eff_h) - sec["min_y"]

                            sa_local = [
                                (p[0] + shift_x, p[1] + shift_y) for p in sec["sa_poly"]
                            ]
                            clipped = core.clip_polygon_to_rect(
                                sa_local, 0.0, 0.0, core_w, core_h
                            )
                            if len(clipped) < 3 or core.polygon_area(clipped) < 1.0:
                                continue  # grid cell holds no pattern content

                            # Content hull for nesting: the visible sa content
                            # plus any glue/align tab strips, which are drawn
                            # margin px beyond the core edges (see
                            # overlap_px_tab in _render_pdf_pages). Coordinates
                            # are in the tile's padded frame.
                            hull_pts = [
                                (p[0] + pad_l, p[1] + pad_t) for p in clipped
                            ]

                            def _edge_span(axis, val, bound):
                                lo, hi = get_line_extents(sa_local, axis, val)
                                if lo is None:
                                    return None
                                lo = max(0.0, min(lo, bound))
                                hi = max(0.0, min(hi, bound))
                                if hi - lo < 1e-2:
                                    return None
                                return lo, hi

                            if c < t_cols - 1:
                                span = _edge_span(0, core_w, core_h)
                                if span:
                                    hull_pts += [
                                        (pad_l + core_w + margin, pad_t + span[0]),
                                        (pad_l + core_w + margin, pad_t + span[1]),
                                    ]
                            if c > 0:
                                span = _edge_span(0, 0.0, core_h)
                                if span:
                                    hull_pts += [
                                        (pad_l - margin, pad_t + span[0]),
                                        (pad_l - margin, pad_t + span[1]),
                                    ]
                            if r < t_rows - 1:
                                span = _edge_span(1, core_h, core_w)
                                if span:
                                    hull_pts += [
                                        (pad_l + span[0], pad_t + core_h + margin),
                                        (pad_l + span[1], pad_t + core_h + margin),
                                    ]
                            if r > 0:
                                span = _edge_span(1, 0.0, core_w)
                                if span:
                                    hull_pts += [
                                        (pad_l + span[0], pad_t - margin),
                                        (pad_l + span[1], pad_t - margin),
                                    ]

                            size_items.append({
                                "prefix": sec["prefix"],
                                "part_str": f" (Part {r + 1}-{c + 1})",
                                "T_w": pad_l + core_w + pad_r,
                                "T_h": pad_t + core_h + pad_b,
                                "core_w": core_w,
                                "core_h": core_h,
                                "pad_l": pad_l,
                                "pad_r": pad_r,
                                "pad_t": pad_t,
                                "pad_b": pad_b,
                                "inner_transform": str(
                                    inkex.Transform(f"translate({shift_x}, {shift_y})")
                                ),
                                "right_glue": v_tabs.get((c, r))
                                if c < t_cols - 1
                                else None,
                                "left_align": v_tabs.get((c - 1, r)) if c > 0 else None,
                                "bottom_glue": h_tabs.get((c, r))
                                if r < t_rows - 1
                                else None,
                                "top_align": h_tabs.get((c, r - 1)) if r > 0 else None,
                                "sa_poly": sec["sa_poly"],
                                "regions": sec["regions"],
                                "scale": sec.get("scale", 1.0),
                                "cx_hull": sec.get("cx_hull", 0.0),
                                "cx": sec.get("cx", 0.0),
                                "cy": sec.get("cy", 0.0),
                                "best_angle": sec.get("best_angle", 0.0),
                                "nest_hull": hull_pts,
                                "copy_str": copy_str,
                            })

            # True-shape nesting: pack seam-allowance hulls (not bounding
            # boxes) with NFP placement. Whole sections may rotate in 90
            # degree steps (baked into geometry below); split parts rotate
            # 0/90 via a render transform; the calibration square stays
            # upright and is pinned to the first page of its size.
            nest_inputs = []
            for item in size_items:
                if item["prefix"] == "CAL":
                    hull = [(0.0, 0.0), (item["T_w"], 0.0), (item["T_w"], item["T_h"]), (0.0, item["T_h"])]
                    rots = [0.0]
                elif item["part_str"]:
                    hull = item["nest_hull"]
                    rots = [0.0, 90.0, 180.0, 270.0]
                else:
                    sa_min_x = min(p[0] for p in item["sa_poly"])
                    sa_min_y = min(p[1] for p in item["sa_poly"])
                    hull = [(p[0] - sa_min_x, p[1] - sa_min_y) for p in item["sa_poly"]]
                    rots = [0.0, 90.0, 180.0, 270.0]
                nest_inputs.append({"hull": hull, "rotations": rots, "item": item})

            nest_inputs.sort(
                key=lambda ni: (
                    0 if ni["item"]["prefix"] == "CAL" else 1,
                    -core.polygon_area(nesting.convex_hull(ni["hull"])),
                    ni["item"]["prefix"],
                    ni["item"]["part_str"],
                    ni["item"].get("copy_str", ""),
                )
            )
            placements = nesting.nest_pack(
                [{"hull": ni["hull"], "rotations": ni["rotations"]} for ni in nest_inputs],
                avail_w,
                avail_h,
                spacing_px,
            )

            local_pages_used = 0
            for ni, pl in zip(nest_inputs, placements):
                item = ni["item"]
                rot = pl["rot"]
                if item.get("nest_hull"):
                    xs = [p[0] for p in item["nest_hull"]]
                    ys = [p[1] for p in item["nest_hull"]]
                    item["hull_bbox"] = (min(xs), min(ys), max(xs), max(ys))
                if rot and item["part_str"]:
                    item["placed_rot"] = rot
                elif rot:
                    # Bake the placement rotation into the geometry about the
                    # same centre used for best_angle so alignment-tick math
                    # (_draw_alignment_ticks) stays consistent.
                    cx, cy = item["cx"], item["cy"]
                    new_sa = rotate_poly(item["sa_poly"], cx, cy, rot)
                    item["sa_poly"] = new_sa
                    item["regions"] = [
                        {
                            "label": r["label"],
                            "id": r["id"],
                            "polygon": rotate_poly(r["polygon"], cx, cy, rot),
                        }
                        for r in item["regions"]
                    ]
                    n_min_x = min(p[0] for p in new_sa)
                    n_min_y = min(p[1] for p in new_sa)
                    item["inner_transform"] = str(
                        inkex.Transform(f"translate({-n_min_x}, {-n_min_y})")
                    )
                    item["T_w"] = item["core_w"] = pl["w"]
                    item["T_h"] = item["core_h"] = pl["h"]
                    item["best_angle"] = item.get("best_angle", 0.0) + rot
                item["local_page_idx"] = pl["page"]
                item["page_x"] = pl["x"]
                item["page_y"] = pl["y"]
                local_pages_used = max(local_pages_used, pl["page"])

            num_temp_pages = local_pages_used + 1
            template_start_page_idx = len(pages_list)
            for p in range(num_temp_pages):
                pages_list.append({"type": "templates", "size": sz, "local_page_idx": p})

            for item in size_items:
                item["target_page"] = template_start_page_idx + item["local_page_idx"]
                item["size"] = sz
                all_packed_items.append(item)

        if self.options.include_colouring_page:
            pages_list.append({"type": "colouring"})

        self._render_pdf_pages(
            all_packed_items, pages_list, g.getparent(), block_data
        )
        

        inkex.utils.debug("Smart Pack Layout complete! Geometry preserved.")

    def _draw_assembly_and_legend(self, layout_layer, panel_x, panel_y, block_data, side_by_side=False, right_col_x=None):
        steps, has_sewing_warning = core.calculate_section_sewing_order(block_data)
        
        etree.SubElement(
            layout_layer,
            "{%s}text" % core.SVG_NS,
            x=str(panel_x),
            y=str(panel_y),
            style=f"font-size:{STYLE_CONFIG['font_size_header']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
        ).text = "Recommended Assembly Sequence"
        
        curr_y = panel_y + 20
        if has_sewing_warning:
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x),
                y=str(curr_y),
                style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_warn']};font-weight:bold;",
            ).text = "WARNING: No Y-seam-free assembly sequence exists!"
            curr_y += 15

        if not steps:
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x),
                y=str(curr_y),
                style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};font-style:italic;",
            ).text = "No section joins required (single section block)."
            curr_y += 20
        else:
            for idx, step in enumerate(steps):
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(panel_x),
                    y=str(curr_y),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_dark']};",
                ).text = f"{idx + 1}. {step}"
                curr_y += 18

        # Draw Pattern Key & Legend
        key_y = panel_y if side_by_side else curr_y + 20
        key_x = right_col_x if side_by_side else panel_x

        etree.SubElement(
            layout_layer,
            "{%s}text" % core.SVG_NS,
            x=str(key_x),
            y=str(key_y),
            style=f"font-size:{STYLE_CONFIG['font_size_header']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
        ).text = "Pattern Key & Legend"
        curr_y_key = key_y + 20

        etree.SubElement(
            layout_layer,
            "{%s}line" % core.SVG_NS,
            x1=str(key_x),
            y1=str(curr_y_key - 4),
            x2=str(key_x + 30),
            y2=str(curr_y_key - 4),
            style=f"stroke:{STYLE_CONFIG['stitch_line_stroke']};stroke-width:{STYLE_CONFIG['stitch_line_stroke_width']};",
        )
        etree.SubElement(
            layout_layer,
            "{%s}text" % core.SVG_NS,
            x=str(key_x + 40),
            y=str(curr_y_key),
            style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_dark']};",
        ).text = "Stitch Line (sew fabric here)"
        curr_y_key += 20

        etree.SubElement(
            layout_layer,
            "{%s}line" % core.SVG_NS,
            x1=str(key_x),
            y1=str(curr_y_key - 4),
            x2=str(key_x + 30),
            y2=str(curr_y_key - 4),
            style=f"stroke:{STYLE_CONFIG['cut_line_stroke']};stroke-width:{STYLE_CONFIG['cut_line_stroke_width']};stroke-dasharray:{STYLE_CONFIG['cut_line_dash']};",
        )
        etree.SubElement(
            layout_layer,
            "{%s}text" % core.SVG_NS,
            x=str(key_x + 40),
            y=str(curr_y_key),
            style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_dark']};",
        ).text = "Cut/Trim Line (outer 1/4\" seam allowance)"
        curr_y_key += 25

        etree.SubElement(
            layout_layer,
            "{%s}text" % core.SVG_NS,
            x=str(key_x),
            y=str(curr_y_key),
            style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_dark']};font-weight:bold;",
        ).text = "Align / Glue Tabs:"
        etree.SubElement(
            layout_layer,
            "{%s}text" % core.SVG_NS,
            x=str(key_x),
            y=str(curr_y_key + 16),
            style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_light']};font-style:italic;",
        ).text = "Used to reassemble sections printed across page boundaries."
        etree.SubElement(
            layout_layer,
            "{%s}text" % core.SVG_NS,
            x=str(key_x),
            y=str(curr_y_key + 28),
            style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_light']};font-style:italic;",
        ).text = "Glue the shaded tab over the matching Align dashed line."

    def _draw_color_key_grid(self, layout_layer, start_x, start_y, max_h, unique_colors, color_codes, all_colors):
        for idx, c_hex in enumerate(unique_colors):
            col = idx % 4
            row = idx // 4
            item_x = start_x + col * 165
            item_y = start_y + row * 24
            
            code = color_codes.get(c_hex, "FAB")
            count = sum(1 for c in all_colors if c == c_hex)
            
            etree.SubElement(
                layout_layer,
                "{%s}rect" % core.SVG_NS,
                x=str(item_x),
                y=str(item_y - 10),
                width="24",
                height="12",
                style=f"fill:{c_hex};stroke:#666666;stroke-width:0.5;",
            )
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(item_x + 30),
                y=str(item_y),
                style="font-size:11px;font-family:sans-serif;font-weight:bold;fill:#333333;",
            ).text = f"{code}"
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(item_x + 65),
                y=str(item_y),
                style="font-size:10px;font-family:sans-serif;fill:#666666;",
            ).text = f"{c_hex} ({count})"

    def _draw_section_map_block(self, target_g, px, py, fit_w, fit_h, block_data, user_colors):
        tree = block_data.tree
        prefs = block_data.prefs
        all_pts = [pt for r in tree.leaf_regions() for pt in r.polygon]
        if not all_pts:
            return
        min_x, max_x = min(p[0] for p in all_pts), max(p[0] for p in all_pts)
        min_y, max_y = min(p[1] for p in all_pts), max(p[1] for p in all_pts)
        bw, bh = max_x - min_x, max_y - min_y
        if bw <= 0 or bh <= 0:
            return

        scale = min(
            (fit_w - 0.2 * core.PX_PER_INCH) / bw, (fit_h - 0.2 * core.PX_PER_INCH) / bh
        )
        center_x, center_y = px + (fit_w / 2), py + (fit_h / 2)
        block_cx, block_cy = min_x + (bw / 2), min_y + (bh / 2)

        preview_g = etree.SubElement(
            target_g, "{%s}g" % core.SVG_NS, id="fpp-section-map-preview"
        )
        color_mode = prefs.get("color_mode", "piece")
        
        for idx, r in enumerate(tree.leaf_regions()):
            scaled_poly = [
                (
                    center_x + (p[0] - block_cx) * scale,
                    center_y + (p[1] - block_cy) * scale,
                )
                for p in r.polygon
            ]
            r_d = (
                "M {:.4f},{:.4f} ".format(*scaled_poly[0])
                + " ".join("L {:.4f},{:.4f}".format(*p) for p in scaled_poly[1:])
                + " Z"
            )
            
            fill_color = user_colors.get(str(r.id)) or user_colors.get(r.id)
            if not fill_color:
                fill_color = core.get_color_for_label(r.label, color_mode, idx)
                
            etree.SubElement(
                preview_g,
                "{%s}path" % core.SVG_NS,
                d=r_d,
                style=f"fill:{fill_color};fill-opacity:0.3;stroke:#aaaaaa;stroke-width:1.0;stroke-linejoin:round;",
            )

        valid_sections = {}
        for r in tree.leaf_regions():
            match = re.match(r"^([A-Za-z]+)(\d+)$", r.label)
            if match:
                prefix = match.group(1).upper()
                if prefix not in valid_sections:
                    valid_sections[prefix] = []
                valid_sections[prefix].append(r)
                
        for prefix, regions in valid_sections.items():
            polys = [r.polygon for r in regions]
            hull_poly = core.get_polygon_union(polys)
            if hull_poly:
                scaled_hull = [
                    (
                        center_x + (p[0] - block_cx) * scale,
                        center_y + (p[1] - block_cy) * scale,
                    )
                    for p in hull_poly
                ]
                hull_d = (
                    "M {:.4f},{:.4f} ".format(*scaled_hull[0])
                    + " ".join("L {:.4f},{:.4f}".format(*p) for p in scaled_hull[1:])
                    + " Z"
                )
                etree.SubElement(
                    preview_g,
                    "{%s}path" % core.SVG_NS,
                    d=hull_d,
                    style="fill:none;stroke:#000000;stroke-width:2.0;stroke-linejoin:round;",
                )
                
                cx_hull, cy_hull = core.polygon_centroid(scaled_hull)
                etree.SubElement(
                    preview_g,
                    "{%s}circle" % core.SVG_NS,
                    cx=f"{cx_hull:.2f}",
                    cy=f"{cy_hull:.2f}",
                    r="14",
                    style="fill:#ffffff;stroke:#000000;stroke-width:1.5;",
                )
                etree.SubElement(
                    preview_g,
                    "{%s}text" % core.SVG_NS,
                    x=f"{cx_hull:.2f}",
                    y=f"{cy_hull:.2f}",
                    style="font-size:16px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                ).text = prefix

    def _draw_outline_only_preview(self, target_g, px, py, fit_w, fit_h, tree):
        all_pts = [pt for r in tree.leaf_regions() for pt in r.polygon]
        if not all_pts:
            return
        min_x, max_x = min(p[0] for p in all_pts), max(p[0] for p in all_pts)
        min_y, max_y = min(p[1] for p in all_pts), max(p[1] for p in all_pts)
        bw, bh = max_x - min_x, max_y - min_y
        if bw <= 0 or bh <= 0:
            return

        scale = min(
            (fit_w - 0.2 * core.PX_PER_INCH) / bw, (fit_h - 0.2 * core.PX_PER_INCH) / bh
        )
        center_x, center_y = px + (fit_w / 2), py + (fit_h / 2)
        block_cx, block_cy = min_x + (bw / 2), min_y + (bh / 2)

        preview_g = etree.SubElement(
            target_g, "{%s}g" % core.SVG_NS, id="fpp-coloring-preview"
        )
        
        for r in tree.leaf_regions():
            scaled_poly = [
                (
                    center_x + (p[0] - block_cx) * scale,
                    center_y + (p[1] - block_cy) * scale,
                )
                for p in r.polygon
            ]
            r_d = (
                "M {:.4f},{:.4f} ".format(*scaled_poly[0])
                + " ".join("L {:.4f},{:.4f}".format(*p) for p in scaled_poly[1:])
                + " Z"
            )
            etree.SubElement(
                preview_g,
                "{%s}path" % core.SVG_NS,
                d=r_d,
                style="fill:#ffffff;stroke:#000000;stroke-width:1.5;stroke-linejoin:round;",
            )

    def _render_fabric_table(self, layout_layer, px, py, pw, margin, fabric_estimates, color_codes):
        table_x = px + margin + 40
        table_y = py + margin + 100
        
        headers = ["Fabric", "Hex", "Pieces", "Direction-Fixed", "Direction-Free", "Suggested Purchase"]
        col_offsets = [0, 60, 150, 220, 350, 480]
        
        header_y = table_y + 18
        etree.SubElement(
            layout_layer,
            "{%s}line" % core.SVG_NS,
            x1=str(table_x),
            y1=str(header_y + 6),
            x2=str(px + pw - margin - 40),
            y2=str(header_y + 6),
            style="stroke:#cccccc;stroke-width:1.0;",
        )
        for text, offset in zip(headers, col_offsets):
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(table_x + offset),
                y=str(header_y),
                style=f"font-size:11px;font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_mid']};",
            ).text = text
            
        row_y = header_y + 30
        for est in fabric_estimates:
            etree.SubElement(
                layout_layer,
                "{%s}rect" % core.SVG_NS,
                x=str(table_x),
                y=str(row_y - 10),
                width="35",
                height="14",
                style=f"fill:{est['color']};stroke:#999999;stroke-width:0.5;",
            )
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(table_x + 60),
                y=str(row_y),
                style=f"font-size:10px;font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
            ).text = est['color']
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(table_x + 150),
                y=str(row_y),
                style=f"font-size:10px;font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
            ).text = str(est['pieces_count'])
            
            fixed_yd = est['fixed_in'] / 36.0
            fixed_str = f"{est['fixed_in']:.1f}\" ({fixed_yd:.2f} yd)"
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(table_x + 220),
                y=str(row_y),
                style=f"font-size:10px;font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
            ).text = fixed_str
            
            free_yd = est['free_in'] / 36.0
            free_str = f"{est['free_in']:.1f}\" ({free_yd:.2f} yd)"
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(table_x + 350),
                y=str(row_y),
                style=f"font-size:10px;font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
            ).text = free_str
            
            free_in_fq = est["fq_free_in"]
            if free_in_fq <= 9.0:
                suggested = "Fat Eighth (FE)"
            elif free_in_fq <= 18.0:
                suggested = "Fat Quarter (FQ)"
            else:
                eighths = math.ceil(free_yd * 8.0)
                suggested = f"{eighths/8.0:.3f} yd ({eighths}/8 yd)"
                
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(table_x + 480),
                y=str(row_y),
                style=f"font-size:10px;font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_dark']};font-weight:bold;",
            ).text = suggested
            
            etree.SubElement(
                layout_layer,
                "{%s}line" % core.SVG_NS,
                x1=str(table_x),
                y1=str(row_y + 8),
                x2=str(px + pw - margin - 40),
                y2=str(row_y + 8),
                style="stroke:#eeeeee;stroke-width:0.5;",
            )
            row_y += 24
        return row_y

    def _draw_alignment_ticks(self, container, r, scale, cx_hull, cx, cy, best_angle, alignment_marks, block_data, mirror_templates):
        orig_r = block_data.tree.regions.get(str(r["id"])) or block_data.tree.regions.get(r["id"])
        if orig_r and alignment_marks:
            poly = orig_r.polygon
            for (m_pt, m_norm) in alignment_marks:
                min_dist = float("inf")
                for v_idx in range(len(poly)):
                    q1, q2 = poly[v_idx], poly[(v_idx + 1) % len(poly)]
                    dx, dy = q2[0] - q1[0], q2[1] - q1[1]
                    l2 = dx*dx + dy*dy
                    if l2 < 1e-9:
                        d = math.hypot(m_pt[0] - q1[0], m_pt[1] - q1[1])
                    else:
                        t_val = ((m_pt[0] - q1[0]) * dx + (m_pt[1] - q1[1]) * dy) / l2
                        t_val = max(0.0, min(1.0, t_val))
                        proj_x = q1[0] + t_val * dx
                        proj_y = q1[1] + t_val * dy
                        d = math.hypot(m_pt[0] - proj_x, m_pt[1] - proj_y)
                    if d < min_dist:
                        min_dist = d
                
                if min_dist < 0.05:
                    px_s, py_s = m_pt[0] * scale, m_pt[1] * scale
                    if mirror_templates:
                        px_m = 2.0 * cx_hull - px_s
                        py_m = py_s
                        nx_m, ny_m = -m_norm[0], m_norm[1]
                    else:
                        px_m, py_m = px_s, py_s
                        nx_m, ny_m = m_norm[0], m_norm[1]
                    
                    if best_angle != 0:
                        rad = math.radians(best_angle)
                        cos_a, sin_a = math.cos(rad), math.sin(rad)
                        tx_pt, ty_pt = px_m - cx, py_m - cy
                        px_r = tx_pt * cos_a - ty_pt * sin_a + cx
                        py_r = tx_pt * sin_a + ty_pt * cos_a + cy
                        nx_r = nx_m * cos_a - ny_m * sin_a
                        ny_r = nx_m * sin_a + ny_m * cos_a
                    else:
                        px_r, py_r = px_m, py_m
                        nx_r, ny_r = nx_m, ny_m
                    
                    TICK_LEN = 20.0
                    x1 = px_r - nx_r * TICK_LEN / 2.0
                    y1 = py_r - ny_r * TICK_LEN / 2.0
                    x2 = px_r + nx_r * TICK_LEN / 2.0
                    y2 = py_r + ny_r * TICK_LEN / 2.0
                    
                    etree.SubElement(
                        container,
                        "{%s}line" % core.SVG_NS,
                        x1=f"{x1:.4f}",
                        y1=f"{y1:.4f}",
                        x2=f"{x2:.4f}",
                        y2=f"{y2:.4f}",
                        style="stroke:#000000;stroke-width:1.0;",
                    )

    def _render_pdf_pages(self, packable_items, pages_list, parent, block_data):
        layout_layer, defs, namedview = self._setup_layout_layer()

        pw, ph = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw, ph = ph, pw
        margin = self.options.margin_in * core.PX_PER_INCH
        header_gap = 0.4 * core.PX_PER_INCH
        avail_w = pw - (margin * 2)
        avail_h = ph - (margin * 2) - (2 * header_gap)
        MAX_COLUMNS = 5

        total_pages = len(pages_list)
        grid_cols = min(total_pages, MAX_COLUMNS)
        grid_rows = math.ceil(total_pages / MAX_COLUMNS)
        grid_w, grid_h = grid_cols * pw + (grid_cols - 1) * margin, grid_rows * ph + (grid_rows - 1) * margin

        # Set root SVG size to match Page 1 size. This prevents Inkscape's PDF export
        # from making Page 1 double-width (matching the overall grid size).
        self.svg.set("width", f"{pw}")
        self.svg.set("height", f"{ph}")
        self.svg.set("viewBox", f"0 0 {pw} {ph}")

        page_offsets = {}
        for pi in range(total_pages):
            col, row = pi % MAX_COLUMNS, pi // MAX_COLUMNS
            px, py = col * (pw + margin), row * (ph + margin)
            page_offsets[pi] = (px, py)
            
            if namedview is not None:
                np = etree.SubElement(
                    namedview,
                    "{%s}page" % core.INKSCAPE_NS,
                    id=f"export-page-{pi + 1}",
                )
                np.set("x", str(px))
                np.set("y", str(py))
                np.set("width", str(pw))
                np.set("height", str(ph))
                
            etree.SubElement(
                layout_layer,
                "{%s}rect" % core.SVG_NS,
                x=str(px),
                y=str(py),
                width=str(pw),
                height=str(ph),
                style="fill:#ffffff;stroke:#dddddd;stroke-width:1.0;",
            )
            etree.SubElement(
                layout_layer,
                "{%s}rect" % core.SVG_NS,
                x=str(px + margin),
                y=str(py + margin),
                width=str(pw - 2 * margin),
                height=str(ph - 2 * margin),
                style="fill:none;stroke:#0000ff;stroke-width:1.5;stroke-dasharray:8,8;",
            )
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(px + margin),
                y=str(py + margin - 10),
                style="font-size:16px;font-family:sans-serif;fill:#0000ff;",
            ).text = f"Page {pi + 1}"

        regions = block_data.tree.leaf_regions()
        user_colors = block_data.prefs.get("custom_colors", {})
        color_mode = block_data.prefs.get("color_mode", "piece")
        
        all_colors = []
        for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
            color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
            if not color_hex:
                color_hex = core.get_color_for_label(r.label, color_mode, idx)
            all_colors.append(color_hex)
            
        unique_colors = sorted(list(set(all_colors)))
        color_codes = core.assign_color_codes(unique_colors, block_data.prefs.get("color_code_overrides", ""))

        for pi, page_info in enumerate(pages_list):
            px, py = page_offsets[pi]
            p_type = page_info["type"]
            
            if p_type != "cover":
                header_y = py + margin + header_gap / 2
                sz_lbl = f"  |  Size: {page_info['size']:.1f}\"" if "size" in page_info else ""
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(header_y),
                    style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_mid']};",
                ).text = f"{self.options.block_name}{sz_lbl}"
                
                etree.SubElement(
                    layout_layer,
                    "{%s}line" % core.SVG_NS,
                    x1=str(px + margin),
                    y1=str(py + margin + header_gap - 5),
                    x2=str(px + pw - margin),
                    y2=str(py + margin + header_gap - 5),
                    style=f"stroke:{STYLE_CONFIG['header_footer_line_stroke']};stroke-width:{STYLE_CONFIG['header_footer_line_stroke_width']};",
                )
                
                footer_y = py + ph - margin - header_gap / 2
                credit_str = f"Designed by: {self.options.designer_name}" if self.options.designer_name else "FPP Pattern"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(footer_y + 4),
                    style=f"font-size:{STYLE_CONFIG['font_size_tiny']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_light']};",
                ).text = f"{credit_str}  |  {self.options.copyright_notice}"
                
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + pw - margin),
                    y=str(footer_y + 4),
                    style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:end;fill:{STYLE_CONFIG['color_mid']};",
                ).text = f"Page {pi + 1} of {total_pages}"
                
                etree.SubElement(
                    layout_layer,
                    "{%s}line" % core.SVG_NS,
                    x1=str(px + margin),
                    y1=str(py + ph - margin - header_gap + 5),
                    x2=str(px + pw - margin),
                    y2=str(py + ph - margin - header_gap + 5),
                    style="stroke:#dddddd;stroke-width:0.5;",
                )
            else:
                footer_y = py + ph - margin - header_gap / 2
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + pw - margin),
                    y=str(footer_y + 4),
                    style="font-size:10px;font-family:sans-serif;font-weight:bold;text-anchor:end;fill:#666666;",
                ).text = f"Page {pi + 1} of {total_pages}"
            
            if p_type == "cover":
                sizes_list = page_info["sizes"]
                
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 30),
                    style=f"font-size:{STYLE_CONFIG['font_size_title']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
                ).text = self.options.block_name
                
                credit_str = f"Designed by: {self.options.designer_name}" if self.options.designer_name else "Designer: Unknown"
                sizes_str = ", ".join(f"{sz:.1f}\"" for sz in sorted(sizes_list, reverse=True))
                size_str = f"Finished Size(s): {sizes_str}"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 55),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
                ).text = f"{credit_str}  |  {size_str}  |  {self.options.copyright_notice}"
                
                preview_side = min(int(avail_w * 0.90), int(avail_h * 0.65))
                preview_w = preview_side
                preview_h = preview_side
                preview_x = px + margin + (avail_w - preview_w) / 2
                preview_y = py + margin + 80
                
                self._draw_preview_block(
                    layout_layer,
                    preview_x,
                    preview_y,
                    preview_w,
                    preview_h,
                    block_data.tree,
                    block_data.prefs,
                    user_colors,
                )
                
                if not self.options.separate_section_alignment_image:
                    self._draw_assembly_and_legend(
                        layout_layer,
                        px + margin,
                        preview_y + preview_h + 20,
                        block_data,
                        side_by_side=True,
                        right_col_x=px + margin + avail_w / 2 + 10
                    )
                
                # Draw color key at the bottom of Page 1 if there are 10 or fewer colors
                if len(unique_colors) <= 10:
                    if self.options.separate_section_alignment_image:
                        grid_y = preview_y + preview_h + 30
                    else:
                        grid_y = preview_y + preview_h + 150
                    self._draw_color_key_grid(
                        layout_layer,
                        px + margin,
                        grid_y,
                        avail_h - (grid_y - py),
                        unique_colors,
                        color_codes,
                        all_colors
                    )
                    
                sq_size = 1.0 * core.PX_PER_INCH
                sq_abs_x = px + margin
                sq_abs_y = py + ph - margin - sq_size
                sq_g = etree.SubElement(layout_layer, "{%s}g" % core.SVG_NS)
                etree.SubElement(
                    sq_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(sq_abs_x),
                    y=str(sq_abs_y),
                    width=str(sq_size),
                    height=str(sq_size),
                    style=f"fill:none;stroke:{STYLE_CONFIG['color_black']};stroke-width:1.5;",
                )
                etree.SubElement(
                    sq_g,
                    "{%s}text" % core.SVG_NS,
                    x=str(sq_abs_x + sq_size / 2),
                    y=str(sq_abs_y + sq_size / 2),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{STYLE_CONFIG['color_black']};",
                ).text = "1 in"
                
            elif p_type == "color_key":
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 30),
                    style=f"font-size:{STYLE_CONFIG['font_size_subtitle']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
                ).text = "Fabric Color Key"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 55),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
                ).text = "Complete color indexing for the FPP pattern."
                
                self._draw_color_key_grid(layout_layer, px + margin, py + margin + 90, avail_h - 100, unique_colors, color_codes, all_colors)
                
            elif p_type == "section_map":
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 30),
                    style=f"font-size:{STYLE_CONFIG['font_size_subtitle']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
                ).text = "Section Map & Assembly Key"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 55),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
                ).text = "Use this map to assemble the printed sections in the correct sequence."
                
                preview_w = int(avail_w * 0.62)
                preview_h = preview_w
                self._draw_section_map_block(
                    layout_layer,
                    px + margin,
                    py + margin + 80,
                    preview_w,
                    preview_h,
                    block_data,
                    user_colors,
                )
                
                self._draw_assembly_and_legend(layout_layer, px + margin + preview_w + 25, py + margin + 100, block_data)
                
                # Draw color key under the section map if there are more than 10 colors
                if len(unique_colors) > 10:
                    grid_y = py + margin + 80 + preview_h + 30
                    self._draw_color_key_grid(
                        layout_layer,
                        px + margin,
                        grid_y,
                        avail_h - (grid_y - py),
                        unique_colors,
                        color_codes,
                        all_colors
                    )
                
            elif p_type == "fabric_requirements":
                sz = page_info["size"]
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 30),
                    style=f"font-size:{STYLE_CONFIG['font_size_subtitle']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
                ).text = f"Fabric Requirements ({sz:.1f}\" Block)"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 55),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
                ).text = f"Estimates based on {self.options.wof_in:.1f}\" usable Width of Fabric (WOF) and include 3/4\" padding around each piece."

                if int(self.options.template_copies) > 1:
                    etree.SubElement(
                        layout_layer,
                        "{%s}text" % core.SVG_NS,
                        x=str(px + margin),
                        y=str(py + margin + 75),
                        style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_mid']};",
                    ).text = f"Note: quantities below are for ONE block. This document contains {int(self.options.template_copies)} template sets."
                
                fabric_estimates = quilttools_fpp_fabric.calculate_fabric_requirements(block_data, sz, self.options.wof_in)
                end_table_y = self._render_fabric_table(layout_layer, px, py, pw, margin, fabric_estimates, color_codes)
                
                if self.options.visualize_fabric_layout:
                    quilttools_fpp_fabric.draw_fabric_layout_map(
                        layout_layer, px + margin, end_table_y + 30, avail_w,
                        block_data, sz, self.options.wof_in, color_codes
                    )
                
            elif p_type == "colouring":
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 30),
                    style=f"font-size:{STYLE_CONFIG['font_size_subtitle']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
                ).text = "Color Planning Page"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 55),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
                ).text = "Use this sheet to plan your fabrics and color layout before sewing."
                
                preview_w = int(avail_w * 0.75)
                preview_h = preview_w
                preview_x = px + margin + (avail_w - preview_w) / 2
                preview_y = py + margin + 80
                
                self._draw_outline_only_preview(
                    layout_layer,
                    preview_x,
                    preview_y,
                    preview_w,
                    preview_h,
                    block_data.tree,
                )
                
                planning_y = py + ph - margin - 60
                for sw_idx in range(6):
                    sw_x = px + margin + sw_idx * 110 + 20
                    etree.SubElement(layout_layer, "{%s}rect" % core.SVG_NS, x=str(sw_x), y=str(planning_y), width="20", height="20", style="fill:#ffffff;stroke:#666666;stroke-width:1.0;")
                    etree.SubElement(layout_layer, "{%s}line" % core.SVG_NS, x1=str(sw_x + 25), y1=str(planning_y + 15), x2=str(sw_x + 95), y2=str(planning_y + 15), style="stroke:#cccccc;stroke-width:1.0;")

        for i, item in enumerate(packable_items):
            if item["target_page"] not in page_offsets:
                continue
            page_offset_x, page_offset_y = page_offsets[item["target_page"]]

            if item["prefix"] == "CAL":
                sq_abs_x = page_offset_x + margin + item["page_x"]
                sq_abs_y = page_offset_y + margin + header_gap + item["page_y"]
                sq_g = etree.SubElement(layout_layer, "{%s}g" % core.SVG_NS, id=f"calibration-square-{item['target_page']}")
                etree.SubElement(
                    sq_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(sq_abs_x),
                    y=str(sq_abs_y),
                    width=str(96.0),
                    height=str(96.0),
                    style=f"fill:none;stroke:{STYLE_CONFIG['color_black']};stroke-width:1.5;",
                )
                etree.SubElement(
                    sq_g,
                    "{%s}text" % core.SVG_NS,
                    x=str(sq_abs_x + 48.0),
                    y=str(sq_abs_y + 42.0),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{STYLE_CONFIG['color_black']};",
                ).text = "1 in x 1 in"
                etree.SubElement(
                    sq_g,
                    "{%s}text" % core.SVG_NS,
                    x=str(sq_abs_x + 48.0),
                    y=str(sq_abs_y + 62.0),
                    style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};text-anchor:middle;dominant-baseline:middle;fill:{STYLE_CONFIG['color_mid']};",
                ).text = "Measure to verify scale"
                continue

            abs_x = page_offset_x + margin + item["page_x"]
            abs_y = page_offset_y + margin + header_gap + item["page_y"]
            sec_g = etree.SubElement(
                layout_layer, "{%s}g" % core.SVG_NS, id=f"template-{item['prefix']}-{i}"
            )
            # (abs_x, abs_y) is where the placed content hull's bbox min must
            # land; hull_bbox is that hull's bbox in the item's local frame
            # (identical to the frame origin for whole sections and CAL).
            hx0, hy0, hx1, hy1 = item.get("hull_bbox", (0.0, 0.0, 0.0, 0.0))
            placed_rot = int(round(item.get("placed_rot", 0)))
            if placed_rot == 90:
                sec_g.set(
                    "transform",
                    f"translate({abs_x + hy1}, {abs_y - hx0}) rotate(90)",
                )
            elif placed_rot == 180:
                sec_g.set(
                    "transform",
                    f"translate({abs_x + hx1}, {abs_y + hy1}) rotate(180)",
                )
            elif placed_rot == 270:
                sec_g.set(
                    "transform",
                    f"translate({abs_x - hy0}, {abs_y + hx1}) rotate(270)",
                )
            else:
                sec_g.set("transform", f"translate({abs_x - hx0}, {abs_y - hy0})")

            if self.options.show_section_labels:
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(abs_x),
                    y=str(abs_y - 5),
                    style="font-size:12px;font-family:sans-serif;fill:#0000aa;font-weight:bold;",
                ).text = f"Section {item['prefix']}{item['part_str']}{item.get('copy_str', '')}"

            clip_id = f"clip-{item['prefix']}-{i}"
            clipPath = etree.SubElement(defs, "{%s}clipPath" % core.SVG_NS, id=clip_id)
            etree.SubElement(
                clipPath,
                "{%s}rect" % core.SVG_NS,
                x="0",
                y="0",
                width=str(item["core_w"]),
                height=str(item["core_h"]),
            )

            pad_g = etree.SubElement(
                sec_g,
                "{%s}g" % core.SVG_NS,
                transform=f"translate({item['pad_l']}, {item['pad_t']})",
            )

            clip_g = etree.SubElement(
                pad_g, "{%s}g" % core.SVG_NS, style=f"clip-path:url(#{clip_id});"
            )

            inner_transform = inkex.Transform(item["inner_transform"])
            shift_g = etree.SubElement(
                clip_g, "{%s}g" % core.SVG_NS, transform=str(inner_transform)
            )

            sa_d = (
                "M {:.4f},{:.4f} ".format(*item["sa_poly"][0])
                + " ".join("L {:.4f},{:.4f}".format(*p) for p in item["sa_poly"][1:])
                + " Z"
            )
            etree.SubElement(
                shift_g,
                "{%s}path" % core.SVG_NS,
                d=sa_d,
                style="fill:none;stroke:#000000;stroke-width:1.5;stroke-dasharray:6,6;",
            )
            if self.options.export_type == "template":
                self._draw_template_edge_labels(shift_g, item["sa_poly"])

            for idx, r in enumerate(item["regions"]):
                r_d = (
                    "M {:.4f},{:.4f} ".format(*r["polygon"][0])
                    + " ".join("L {:.4f},{:.4f}".format(*p) for p in r["polygon"][1:])
                    + " Z"
                )
                
                assigned_col = user_colors.get(str(r["id"])) or user_colors.get(r["id"])
                if not assigned_col:
                    assigned_col = core.get_color_for_label(r["label"], color_mode, idx)
                
                poly = r["polygon"]
                pw_r = max(p[0] for p in poly) - min(p[0] for p in poly)
                ph_r = max(p[1] for p in poly) - min(p[1] for p in poly)
                area_r = core.polygon_area(poly)
                is_too_small = (pw_r < 40.0 or ph_r < 40.0 or area_r < 3686.0)
                
                mode = self.options.template_color_mode
                if mode == "full" or (mode == "tag" and is_too_small):
                    fill_col = assigned_col
                else:
                    fill_col = "#ffffff"
                    
                etree.SubElement(
                    shift_g,
                    "{%s}path" % core.SVG_NS,
                    d=r_d,
                    style=f"fill:{fill_col};stroke:{STYLE_CONFIG['template_border_stroke']};stroke-width:{STYLE_CONFIG['template_border_stroke_width']};stroke-linejoin:round;",
                )
                
                self._draw_alignment_ticks(
                    shift_g,
                    r,
                    item.get("scale", 1.0),
                    item.get("cx_hull", 0.0),
                    item.get("cx", 0.0),
                    item.get("cy", 0.0),
                    item.get("best_angle", 0.0),
                    self.alignment_marks,
                    block_data,
                    self.options.mirror_templates
                )
                
                r_cx, r_cy = core.polygon_centroid(r["polygon"])
                label_text = r["label"]
                code_text = color_codes.get(assigned_col, "")
                
                # Determine text colors based on contrast
                text_color = STYLE_CONFIG["color_black"]
                subtext_color = STYLE_CONFIG["color_mid"]
                if fill_col != STYLE_CONFIG["color_white"] and is_color_dark(fill_col):
                    text_color = STYLE_CONFIG["color_white"]
                    subtext_color = "#dddddd"

                if mode == "tag" and not is_too_small:
                    etree.SubElement(
                        shift_g,
                        "{%s}text" % core.SVG_NS,
                        x=f"{r_cx:.2f}",
                        y=f"{r_cy - 12:.2f}",
                        style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{text_color};",
                    ).text = label_text
                    etree.SubElement(
                        shift_g,
                        "{%s}rect" % core.SVG_NS,
                        x=f"{r_cx - 12:.2f}",
                        y=f"{r_cy - 4:.2f}",
                        width="24",
                        height="16",
                        style=f"fill:{assigned_col};stroke:{STYLE_CONFIG['template_border_stroke']};stroke-width:0.5;",
                    )
                    if code_text:
                        etree.SubElement(
                            shift_g,
                            "{%s}text" % core.SVG_NS,
                            x=f"{r_cx:.2f}",
                            y=f"{r_cy + 18:.2f}",
                            style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};font-weight:normal;text-anchor:middle;fill:{subtext_color};",
                        ).text = f"[{code_text}]"
                else:
                    if code_text and not is_too_small:
                        etree.SubElement(
                            shift_g,
                            "{%s}text" % core.SVG_NS,
                            x=f"{r_cx:.2f}",
                            y=f"{r_cy - 7:.2f}",
                            style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;fill:{text_color};",
                        ).text = label_text
                        etree.SubElement(
                            shift_g,
                            "{%s}text" % core.SVG_NS,
                            x=f"{r_cx:.2f}",
                            y=f"{r_cy + 7:.2f}",
                            style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};font-weight:normal;text-anchor:middle;fill:{subtext_color};",
                        ).text = f"[{code_text}]"
                    else:
                        etree.SubElement(
                            shift_g,
                            "{%s}text" % core.SVG_NS,
                            x=f"{r_cx:.2f}",
                            y=f"{r_cy:.2f}",
                            style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{text_color};",
                        ).text = label_text

            local_sa = [
                inner_transform.apply_to_point((p[0], p[1])) for p in item["sa_poly"]
            ]

            def clamp_extents(val_min, val_max, bound_max):
                if val_min is None or val_max is None:
                    return None, None
                c_min = max(0, min(val_min, bound_max))
                c_max = max(0, min(val_max, bound_max))
                if c_max - c_min < 1e-2:
                    return None, None
                return c_min, c_max - c_min

            r_min, r_span = clamp_extents(
                *get_line_extents(local_sa, 0, item["core_w"]), item["core_h"]
            )
            l_min, l_span = clamp_extents(
                *get_line_extents(local_sa, 0, 0), item["core_h"]
            )
            b_min, b_span = clamp_extents(
                *get_line_extents(local_sa, 1, item["core_h"]), item["core_w"]
            )
            t_min, t_span = clamp_extents(
                *get_line_extents(local_sa, 1, 0), item["core_w"]
            )

            overlap_px_tab = margin

            if item["left_align"] and l_span:
                etree.SubElement(
                    pad_g,
                    "{%s}line" % core.SVG_NS,
                    x1="0",
                    y1=str(l_min),
                    x2="0",
                    y2=str(l_min + l_span),
                    style="stroke:#000000;stroke-width:2.0;",
                )
            if item["right_glue"] and r_span:
                etree.SubElement(
                    pad_g,
                    "{%s}line" % core.SVG_NS,
                    x1=str(item["core_w"]),
                    y1=str(r_min),
                    x2=str(item["core_w"]),
                    y2=str(r_min + r_span),
                    style="stroke:#000000;stroke-width:2.0;",
                )
            if item["top_align"] and t_span:
                etree.SubElement(
                    pad_g,
                    "{%s}line" % core.SVG_NS,
                    x1=str(t_min),
                    y1="0",
                    x2=str(t_min + t_span),
                    y2="0",
                    style="stroke:#000000;stroke-width:2.0;",
                )
            if item["bottom_glue"] and b_span:
                etree.SubElement(
                    pad_g,
                    "{%s}line" % core.SVG_NS,
                    x1=str(b_min),
                    y1=str(item["core_h"]),
                    x2=str(b_min + b_span),
                    y2=str(item["core_h"]),
                    style="stroke:#000000;stroke-width:2.0;",
                )

            if item["right_glue"] and r_span:
                tx, ty, tab_id = item["core_w"], r_min, item["right_glue"]
                etree.SubElement(
                    pad_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(tx),
                    y=str(ty),
                    width=str(overlap_px_tab),
                    height=str(r_span),
                    style=f"fill:{STYLE_CONFIG['glue_tab_fill']};fill-opacity:{STYLE_CONFIG['glue_tab_fill_opacity']};stroke:{STYLE_CONFIG['tab_stroke']};stroke-width:{STYLE_CONFIG['tab_stroke_width']};stroke-dasharray:{STYLE_CONFIG['tab_stroke_dash']};",
                )
                num_repeats = max(1, int(r_span / 100))
                spacing = r_span / (num_repeats + 1)
                for i in range(1, num_repeats + 1):
                    y_pos = ty + i * spacing
                    etree.SubElement(
                        pad_g,
                        "{%s}text" % core.SVG_NS,
                        x=str(tx + overlap_px_tab / 2),
                        y=str(y_pos),
                        transform=f"rotate(-90 {tx + overlap_px_tab / 2} {y_pos})",
                        style=f"font-size:{STYLE_CONFIG['tab_font_size']};font-family:{STYLE_CONFIG['font_family']};font-weight:{STYLE_CONFIG['tab_font_weight']};text-anchor:middle;dominant-baseline:middle;fill:{STYLE_CONFIG['tab_text_color_glue']};",
                    ).text = f"Glue {tab_id}"
            if item["left_align"] and l_span:
                tx, ty, tab_id = -overlap_px_tab, l_min, item["left_align"]
                etree.SubElement(
                    pad_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(tx),
                    y=str(ty),
                    width=str(overlap_px_tab),
                    height=str(l_span),
                    style=f"fill:{STYLE_CONFIG['align_tab_fill']};fill-opacity:{STYLE_CONFIG['align_tab_fill_opacity']};stroke:{STYLE_CONFIG['tab_stroke']};stroke-width:{STYLE_CONFIG['tab_stroke_width']};stroke-dasharray:{STYLE_CONFIG['tab_stroke_dash']};",
                )
                num_repeats = max(1, int(l_span / 100))
                spacing = l_span / (num_repeats + 1)
                for i in range(1, num_repeats + 1):
                    y_pos = ty + i * spacing
                    etree.SubElement(
                        pad_g,
                        "{%s}text" % core.SVG_NS,
                        x=str(tx + overlap_px_tab / 2),
                        y=str(y_pos),
                        transform=f"rotate(-90 {tx + overlap_px_tab / 2} {y_pos})",
                        style=f"font-size:{STYLE_CONFIG['tab_font_size']};font-family:{STYLE_CONFIG['font_family']};font-weight:{STYLE_CONFIG['tab_font_weight']};text-anchor:middle;dominant-baseline:middle;fill:{STYLE_CONFIG['tab_text_color_align']};",
                    ).text = f"Align {tab_id}"
            if item["bottom_glue"] and b_span:
                tx, ty, tab_id = b_min, item["core_h"], item["bottom_glue"]
                etree.SubElement(
                    pad_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(tx),
                    y=str(ty),
                    width=str(b_span),
                    height=str(overlap_px_tab),
                    style=f"fill:{STYLE_CONFIG['glue_tab_fill']};fill-opacity:{STYLE_CONFIG['glue_tab_fill_opacity']};stroke:{STYLE_CONFIG['tab_stroke']};stroke-width:{STYLE_CONFIG['tab_stroke_width']};stroke-dasharray:{STYLE_CONFIG['tab_stroke_dash']};",
                )
                num_repeats = max(1, int(b_span / 100))
                spacing = b_span / (num_repeats + 1)
                for i in range(1, num_repeats + 1):
                    x_pos = tx + i * spacing
                    etree.SubElement(
                        pad_g,
                        "{%s}text" % core.SVG_NS,
                        x=str(x_pos),
                        y=str(ty + overlap_px_tab / 2),
                        style=f"font-size:{STYLE_CONFIG['tab_font_size']};font-family:{STYLE_CONFIG['font_family']};font-weight:{STYLE_CONFIG['tab_font_weight']};text-anchor:middle;dominant-baseline:middle;fill:{STYLE_CONFIG['tab_text_color_glue']};",
                    ).text = f"Glue {tab_id}"
            if item["top_align"] and t_span:
                tx, ty, tab_id = t_min, -overlap_px_tab, item["top_align"]
                etree.SubElement(
                    pad_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(tx),
                    y=str(ty),
                    width=str(t_span),
                    height=str(overlap_px_tab),
                    style=f"fill:{STYLE_CONFIG['align_tab_fill']};fill-opacity:{STYLE_CONFIG['align_tab_fill_opacity']};stroke:{STYLE_CONFIG['tab_stroke']};stroke-width:{STYLE_CONFIG['tab_stroke_width']};stroke-dasharray:{STYLE_CONFIG['tab_stroke_dash']};",
                )
                num_repeats = max(1, int(t_span / 100))
                spacing = t_span / (num_repeats + 1)
                for i in range(1, num_repeats + 1):
                    x_pos = tx + i * spacing
                    etree.SubElement(
                        pad_g,
                        "{%s}text" % core.SVG_NS,
                        x=str(x_pos),
                        y=str(ty + overlap_px_tab / 2),
                        style=f"font-size:{STYLE_CONFIG['tab_font_size']};font-family:{STYLE_CONFIG['font_family']};font-weight:{STYLE_CONFIG['tab_font_weight']};text-anchor:middle;dominant-baseline:middle;fill:{STYLE_CONFIG['tab_text_color_align']};",
                    ).text = f"Align {tab_id}"

        self.svg.append(layout_layer)

    def _draw_template_edge_labels(self, container, sa_poly):
        if not sa_poly or len(sa_poly) < 3:
            return
        cx_sa, cy_sa = core.polygon_centroid(sa_poly)
        for i in range(len(sa_poly)):
            p1 = sa_poly[i]
            p2 = sa_poly[(i + 1) % len(sa_poly)]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            len_px = math.hypot(dx, dy)
            if len_px < 2.0:
                continue
            len_in = len_px / core.PX_PER_INCH
            label_text = f"{len_in:.2f}\""
            
            mid_x = (p1[0] + p2[0]) / 2.0
            mid_y = (p1[1] + p2[1]) / 2.0
            
            vx = mid_x - cx_sa
            vy = mid_y - cy_sa
            perp_x = -dy
            perp_y = dx
            if perp_x * vx + perp_y * vy < 0:
                perp_x, perp_y = -perp_x, -perp_y
                
            plen = math.hypot(perp_x, perp_y)
            if plen > 1e-9:
                nx = perp_x / plen
                ny = perp_y / plen
            else:
                nx, ny = 0.0, 0.0
                
            offset = 12.0
            lbl_x = mid_x + nx * offset
            lbl_y = mid_y + ny * offset
            
            etree.SubElement(
                container,
                "{%s}text" % core.SVG_NS,
                x=f"{lbl_x:.2f}",
                y=f"{lbl_y:.2f}",
                style=f"font-size:9px;font-family:{STYLE_CONFIG['font_family']};fill:#555555;text-anchor:middle;dominant-baseline:middle;",
            ).text = label_text


if __name__ == "__main__":
    ExportPlugin().run()
