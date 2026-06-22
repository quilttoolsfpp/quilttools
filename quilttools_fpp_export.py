#!/usr/bin/env python3
import math
import re

import inkex
from lxml import etree

import quilttools_fpp_core as core

PAGE_SIZES = {
    "letter": (8.5 * core.PX_PER_INCH, 11.0 * core.PX_PER_INCH),
    "a4": (8.27 * core.PX_PER_INCH, 11.69 * core.PX_PER_INCH),
    "a3": (11.69 * core.PX_PER_INCH, 16.54 * core.PX_PER_INCH),
}


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
    return best_angle


def get_line_extents(poly, axis, val):
    """Finds the min/max span of a polygon along a specific X or Y cutting line."""
    pts = []
    n = len(poly)
    for i in range(n):
        p1, p2 = poly[i], poly[(i + 1) % n]
        v1, v2 = p1[axis], p2[axis]
        # Check if segment crosses the cut line (with floating point tolerance)
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


def pack_fabric_strip(boxes, fabric_width_px):
    # Sort boxes by height descending
    sorted_boxes = sorted(boxes, key=lambda b: b[1], reverse=True)
    shelves = [] # Each shelf is: [used_width, shelf_height]
    total_height = 0
    
    for w, h in sorted_boxes:
        if w > fabric_width_px:
            # Try to swap dimensions
            if h <= fabric_width_px:
                w, h = h, w
            else:
                # Piece exceeds width in both directions; place on its own shelf
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


class ExportPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="layout")
        pars.add_argument("--layout_mode", type=str, default="compact_rotate")
        pars.add_argument("--include_preview", type=inkex.Boolean, default=True)
        pars.add_argument("--include_fabric_estimation", type=inkex.Boolean, default=True)
        pars.add_argument("--show_section_labels", type=inkex.Boolean, default=False)
        pars.add_argument("--page_size", type=str, default="letter")
        pars.add_argument("--orientation", type=str, default="portrait")
        pars.add_argument("--sa_in", type=float, default=0.25)
        pars.add_argument("--spacing_in", type=float, default=0.2)
        pars.add_argument("--template_color_mode", type=str, default="none")
        pars.add_argument("--export_preview_mode", type=str, default="color")
        pars.add_argument("--mirror_templates", type=inkex.Boolean, default=True)
        pars.add_argument("--mirror_preview", type=inkex.Boolean, default=False)
        pars.add_argument("--block_name", type=str, default="My Quilt Block")
        pars.add_argument("--designer_name", type=str, default="")
        pars.add_argument("--finished_size_in", type=float, default=12.0)
        pars.add_argument("--copyright_notice", type=str, default="For personal use only.")

    def effect(self):
        # MASTER ROUTER
        if self.options.action == "layout":
            if self.options.layout_mode == "explode":
                self._generate_open_canvas()
            else:
                self._generate_smart_pack()
        elif self.options.action == "finalize":
            self._finalize_open_canvas()

    def _get_start_page(self):
        start_page = 0
        if self.options.include_preview:
            start_page += 1
            if self.options.include_fabric_estimation:
                start_page += 1
        return start_page

    def _get_processed_sections(self, allow_rotate):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            inkex.errormsg("No Quilt Tools FPP block found.")
            return None, None, None

        tree = block_data.tree
        user_colors = {}
        for path in g.findall(f".//{{{core.SVG_NS}}}path"):
            rid = path.get(core.FPP_REGION_ATTR)
            if rid:
                style = path.get("style", "")
                m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", style)
                if m:
                    user_colors[int(rid)] = m.group(1)

        valid_sections = {}
        bad_labels = []
        for r in tree.leaf_regions():
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
        margin = 0.5 * core.PX_PER_INCH
        avail_w, avail_h = pw - (margin * 2), ph - (margin * 2)
        sa_px = self.options.sa_in * core.PX_PER_INCH

        processed_sections = []
        for prefix in sorted(valid_sections.keys()):
            valid_sections[prefix].sort(key=lambda x: x[0])
            regions = [x[1] for x in valid_sections[prefix]]

            polys = [r.polygon for r in regions]
            hull_poly = core.get_polygon_union(polys)
            if not hull_poly:
                continue

            cx_hull, cy_hull = core.polygon_centroid(hull_poly)

            # Local copy of regions and hull_poly to avoid mutating master LOM
            if self.options.mirror_templates:
                hull_poly_local = [(2.0 * cx_hull - pt[0], pt[1]) for pt in hull_poly]
                regions_local = []
                for r in regions:
                    regions_local.append({
                        "label": r.label,
                        "id": r.id,
                        "polygon": [(2.0 * cx_hull - pt[0], pt[1]) for pt in r.polygon]
                    })
            else:
                hull_poly_local = list(hull_poly)
                regions_local = []
                for r in regions:
                    regions_local.append({
                        "label": r.label,
                        "id": r.id,
                        "polygon": list(r.polygon)
                    })

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
        
        is_outline = (self.options.export_preview_mode == "outline")
        has_custom = (len(user_colors) > 0)

        for idx, r in enumerate(tree.leaf_regions()):
            # Handle preview mirroring toggle
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
            
            # Determine color according to preview state
            if is_outline:
                fill_color = "#ffffff"
            elif has_custom:
                fill_color = user_colors.get(str(r.id)) or user_colors.get(r.id)
                if not fill_color:
                    fill_color = core.get_color_for_label(r.label, color_mode, idx)
            else:
                fill_color = "#d6eaf8" # default blue tripwire warning
                
            etree.SubElement(
                preview_g,
                "{%s}path" % core.SVG_NS,
                d=r_d,
                style=f"fill:{fill_color};stroke:#000000;stroke-width:1.5;stroke-linejoin:round;",
            )
            r_cx, r_cy = core.polygon_centroid(scaled_poly)
            etree.SubElement(
                preview_g,
                "{%s}text" % core.SVG_NS,
                x=f"{r_cx:.2f}",
                y=f"{r_cy:.2f}",
                style="font-size:12px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
            ).text = r.label

    def _generate_open_canvas(self):
        g, block_data, processed_sections = self._get_processed_sections(
            allow_rotate=False
        )
        if not processed_sections:
            return
        layout_layer, defs, _ = self._setup_layout_layer()

        pw, ph = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw, ph = ph, pw
        margin = 0.5 * core.PX_PER_INCH
        avail_w, avail_h = pw - (margin * 2), ph - (margin * 2)
        spacing_px = self.options.spacing_in * core.PX_PER_INCH

        start_page = self._get_start_page()
        sim_page, sim_x, sim_y, sim_row_h = start_page, 0, 0, 0.0

        # Calculate Required Grid Size
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

        # Draw Preview & Calibration on Cell 0
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

            # Draw 1-Inch Square
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
                style="fill:none;stroke:#000000;stroke-width:1.5;",
            )
            etree.SubElement(
                sq_g,
                "{%s}text" % core.SVG_NS,
                x=str(px + sq_rect[0] + sq_size / 2),
                y=str(py + sq_rect[1] + sq_size / 2),
                style="font-size:12px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
            ).text = "1 in"

        # Draw Empty Page Grids
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

        # Place Sections
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
                r_cx, r_cy = core.polygon_centroid(r["polygon"])
                etree.SubElement(
                    sec_g,
                    "{%s}text" % core.SVG_NS,
                    x=f"{r_cx:.2f}",
                    y=f"{r_cy:.2f}",
                    style="font-size:14px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                ).text = r["label"]

        g.getparent().append(layout_layer)
        inkex.utils.debug(
            "Open Canvas Generated. Freely rotate and drag items across the grids, then select 'Finalize'!"
        )

    def _finalize_open_canvas(self):
        g, block_data, processed_sections = self._get_processed_sections(
            allow_rotate=False
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
        margin = 0.5 * core.PX_PER_INCH
        avail_w, avail_h = pw - (margin * 2), ph - (margin * 2)

        # ----------------------------------------------------
        # RUN PRE-EXPORT VALIDATION (LINT) PASS
        # ----------------------------------------------------
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

        validation_report = []
        validation_report.append("=========================================")
        validation_report.append("      FPP PATTERN VALIDATION REPORT      ")
        validation_report.append("=========================================")

        # Check metadata
        if not self.options.block_name or self.options.block_name == "My Quilt Block":
            validation_report.append("[!] Metadata: Block name is default or empty.")
        if not self.options.designer_name:
            validation_report.append("[!] Metadata: Designer Name is empty.")

        # Check colors
        user_colors = block_data.prefs.get("custom_colors", {})
        if not user_colors:
            validation_report.append("[!] Color: 0 custom colors saved. All pieces use default-blue.")

        # Check sewing order
        steps, has_sewing_warning = core.calculate_section_sewing_order(block_data)
        if has_sewing_warning:
            validation_report.append("[!] Sewing Order: WARNING: No Y-seam-free assembly sequence exists!")
        else:
            validation_report.append("[✓] Sewing Order: Valid Y-seam-free assembly sequence found.")

        # Check overlaps
        has_overlap = False
        for sec1_prefix, poly1 in placed_polys.items():
            for sec2_prefix, poly2 in placed_polys.items():
                if sec1_prefix < sec2_prefix:
                    if core.polygons_overlap(poly1, poly2):
                        validation_report.append(f"[!] CRITICAL: Section {sec1_prefix} overlaps with Section {sec2_prefix}!")
                        has_overlap = True

        # Check layout grid bounds
        has_bleed = False
        for sec_prefix, poly in placed_polys.items():
            out_of_bounds = False
            for p in poly:
                if p[0] < -1.0 or p[0] > grid_w + 1.0 or p[1] < -1.0 or p[1] > grid_h + 1.0:
                    out_of_bounds = True
                    break
            if out_of_bounds:
                validation_report.append(f"[!] WARNING: Section {sec_prefix} extends outside the page layout boundaries!")
                has_bleed = True

        if not has_overlap and not has_bleed:
            validation_report.append("[✓] Layout: No overlaps or out-of-bounds pieces detected.")
        validation_report.append("=========================================")

        inkex.utils.debug("\n".join(validation_report))
        # ----------------------------------------------------

        packable_items = []
        global_tab_counter = 1
        max_page_idx = 0

        grid_max_page = total_pages - 1
        next_extra_page = grid_max_page + 1
        finalized_polys = {}

        # MAGICAL ABSOLUTE TRANSFORM SLICER
        for sec in processed_sections:
            sec_g = layout_layer.find(
                f".//{{{core.SVG_NS}}}g[@id='manual-sec-{sec['prefix']}']"
            )
            if sec_g is None:
                continue

            # Read exact user transformation (Handles manual Translation and Rotation perfectly)
            user_transform = inkex.Transform(sec_g.get("transform", ""))

            # Get the current placed polygon
            placed_poly = [user_transform.apply_to_point((p[0], p[1])) for p in sec["sa_poly"]]

            # Check overlap with previously finalized sections
            overlaps = False
            overlap_partner = None
            for other_prefix, other_poly in finalized_polys.items():
                if core.polygons_overlap(placed_poly, other_poly):
                    overlaps = True
                    overlap_partner = other_prefix
                    break

            if overlaps:
                # Relocate to its own page at the back of the pattern
                target_page = next_extra_page
                next_extra_page += 1
                max_page_idx = max(max_page_idx, target_page)

                validation_report.append(f"[!] Layout: Section {sec['prefix']} overlaps with Section {overlap_partner} on canvas. Automatically relocated to new Page {target_page + 1} at the back.")

                # Calculate bounding box of the transformed shape
                rot_min_x = min(p[0] for p in placed_poly)
                rot_max_x = max(p[0] for p in placed_poly)
                rot_min_y = min(p[1] for p in placed_poly)
                rot_max_y = max(p[1] for p in placed_poly)
                rot_w = rot_max_x - rot_min_x
                rot_h = rot_max_y - rot_min_y

                # Center the piece on the new page
                page_x = (avail_w - rot_w) / 2.0
                page_y = (avail_h - rot_h) / 2.0
                
                # Transform to align it relative to the centered page coordinates
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

                # Transform original coordinates to find true absolute bounds on canvas
                abs_x_vals = []
                abs_y_vals = []
                for p in sec["sa_poly"]:
                    tp = user_transform.apply_to_point((p[0], p[1]))
                    abs_x_vals.append(tp[0])
                    abs_y_vals.append(tp[1])

                abs_x0, abs_x1 = min(abs_x_vals), max(abs_x_vals)
                abs_y0, abs_y1 = min(abs_y_vals), max(abs_y_vals)

                # Determine exact page grid cells overlapped
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

                        # Calculate local clipping boundary
                        core_x0, core_x1 = max(abs_x0, cell_x0), min(abs_x1, cell_x1)
                        core_y0, core_y1 = max(abs_y0, cell_y0), min(abs_y1, cell_y1)
                        core_w, core_h = core_x1 - core_x0, core_y1 - core_y0
                        if core_w <= 0 or core_h <= 0:
                            continue

                        target_page = r * MAX_COLUMNS + c
                        max_page_idx = max(max_page_idx, target_page)

                        # Matrix Magic: Align original geometry precisely into the page clip mask
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

        self._render_pdf_pages(
            packable_items, max_page_idx + 1, g.getparent(), block_data
        )
        inkex.utils.debug(
            "Finalize Complete! Custom rotations preserved and snapped seamlessly to PDF grids."
        )

    def _generate_smart_pack(self):
        g, block_data, processed_sections = self._get_processed_sections(
            allow_rotate=True
        )
        if not processed_sections:
            return

        pw, ph = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw, ph = ph, pw
        margin = 0.5 * core.PX_PER_INCH
        avail_w, avail_h = pw - (margin * 2), ph - (margin * 2)
        overlap_px = 0.5 * core.PX_PER_INCH

        packable_items = []
        global_tab_counter = 1
        eff_w, eff_h = avail_w - overlap_px, avail_h - overlap_px

        for sec in processed_sections:
            if sec["width"] <= avail_w and sec["height"] <= avail_h:
                packable_items.append(
                    {
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
                            inkex.Transform(
                                f"translate({-sec['min_x']}, {-sec['min_y']})"
                            )
                        ),
                        "right_glue": None,
                        "left_align": None,
                        "bottom_glue": None,
                        "top_align": None,
                        "sa_poly": sec["sa_poly"],
                        "regions": sec["regions"],
                    }
                )
            else:
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

                        packable_items.append(
                            {
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
                            }
                        )

        start_page = self._get_start_page()
        current_page, current_x, current_y, row_max_h = start_page, 0.0, 0.0, 0.0
        spacing_px = self.options.spacing_in * core.PX_PER_INCH

        # DYNAMIC BIN PACKING
        for item in packable_items:
            if current_x + item["T_w"] > avail_w:
                current_x, current_y, row_max_h = (
                    0.0,
                    current_y + row_max_h + spacing_px,
                    0.0,
                )
            if current_y + item["T_h"] > avail_h:
                current_page += 1
                current_x, current_y, row_max_h = 0.0, 0.0, 0.0
            if item["T_w"] > avail_w or item["T_h"] > avail_h:
                current_page += 1
                current_x, current_y, row_max_h = 0.0, 0.0, item["T_h"]

            row_max_h = max(row_max_h, item["T_h"])
            item["target_page"] = current_page
            item["page_x"] = current_x
            item["page_y"] = current_y
            current_x += item["T_w"] + spacing_px

        self._render_pdf_pages(
            packable_items, current_page + 1, g.getparent(), block_data
        )
        inkex.utils.debug("Smart Pack Layout complete! Geometry preserved.")

    def _render_pdf_pages(self, packable_items, total_pages, parent, block_data):
        layout_layer, defs, namedview = self._setup_layout_layer()

        pw, ph = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw, ph = ph, pw
        margin = 0.5 * core.PX_PER_INCH
        avail_w, avail_h = pw - (margin * 2), ph - (margin * 2)
        MAX_COLUMNS = 5

        self.svg.set("width", f"{pw}")
        self.svg.set("height", f"{ph}")
        self.svg.set("viewBox", f"0 0 {pw} {ph}")

        def add_page_rect(page_index):
            col, row = page_index % MAX_COLUMNS, page_index // MAX_COLUMNS
            px, py = col * (pw + margin), row * (ph + margin)
            if namedview is not None:
                np = etree.SubElement(
                    namedview,
                    "{%s}page" % core.INKSCAPE_NS,
                    id=f"export-page-{page_index + 1}",
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
            ).text = f"Page {page_index + 1}"
            return px, py

        page_offsets = {}
        for pi in range(total_pages):
            page_offsets[pi] = add_page_rect(pi)

        if self.options.include_preview and 0 in page_offsets:
            p0_x, p0_y = page_offsets[0]
            
            # 1. Main Header Title
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(p0_x + margin),
                y=str(p0_y + margin + 30),
                style="font-size:24px;font-family:sans-serif;font-weight:bold;fill:#333333;",
            ).text = self.options.block_name

            # 2. Sub-header / Designer Credit & Copyright
            credit_str = f"Designed by: {self.options.designer_name}" if self.options.designer_name else "Designer: Unknown"
            size_str = f"Finished Size: {self.options.finished_size_in:.1f}\" x {self.options.finished_size_in:.1f}\""
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(p0_x + margin),
                y=str(p0_y + margin + 55),
                style="font-size:12px;font-family:sans-serif;fill:#666666;",
            ).text = f"{credit_str}  |  {size_str}  |  {self.options.copyright_notice}"

            # 3. Dynamic Block Preview (left side) - scaled to 62% of available width
            preview_w = int(avail_w * 0.62)
            preview_h = preview_w
            user_colors = block_data.prefs.get("custom_colors", {})
            self._draw_preview_block(
                layout_layer,
                p0_x + margin,
                p0_y + margin + 80,
                preview_w,
                preview_h,
                block_data.tree,
                block_data.prefs,
                user_colors,
            )

            # 4. Right side panel: Sewing Order & Legend
            panel_x = p0_x + margin + preview_w + 25
            panel_y = p0_y + margin + 100

            # recommended sewing order
            steps, has_sewing_warning = core.calculate_section_sewing_order(block_data)
            
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x),
                y=str(panel_y),
                style="font-size:14px;font-family:sans-serif;font-weight:bold;fill:#333333;",
            ).text = "Recommended Assembly Sequence"
            
            curr_y = panel_y + 20
            if has_sewing_warning:
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(panel_x),
                    y=str(curr_y),
                    style="font-size:10px;font-family:sans-serif;fill:#cc0000;font-weight:bold;",
                ).text = "WARNING: No Y-seam-free assembly sequence exists!"
                curr_y += 15

            if not steps:
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(panel_x),
                    y=str(curr_y),
                    style="font-size:12px;font-family:sans-serif;fill:#666666;font-style:italic;",
                ).text = "No section joins required (single section block)."
                curr_y += 20
            else:
                for idx, step in enumerate(steps):
                    etree.SubElement(
                        layout_layer,
                        "{%s}text" % core.SVG_NS,
                        x=str(panel_x),
                        y=str(curr_y),
                        style="font-size:12px;font-family:sans-serif;fill:#444444;",
                    ).text = f"{idx + 1}. {step}"
                    curr_y += 18

            # Legend
            curr_y += 20
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x),
                y=str(curr_y),
                style="font-size:14px;font-family:sans-serif;font-weight:bold;fill:#333333;",
            ).text = "Pattern Key & Legend"
            curr_y += 20

            # Draw solid line
            etree.SubElement(
                layout_layer,
                "{%s}line" % core.SVG_NS,
                x1=str(panel_x),
                y1=str(curr_y - 4),
                x2=str(panel_x + 30),
                y2=str(curr_y - 4),
                style="stroke:#000000;stroke-width:2.0;",
            )
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x + 40),
                y=str(curr_y),
                style="font-size:11px;font-family:sans-serif;fill:#444444;",
            ).text = "Stitch Line (sew fabric here)"
            curr_y += 20

            # Draw dashed line
            etree.SubElement(
                layout_layer,
                "{%s}line" % core.SVG_NS,
                x1=str(panel_x),
                y1=str(curr_y - 4),
                x2=str(panel_x + 30),
                y2=str(curr_y - 4),
                style="stroke:#000000;stroke-width:1.5;stroke-dasharray:4,4;",
            )
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x + 40),
                y=str(curr_y),
                style="font-size:11px;font-family:sans-serif;fill:#444444;",
            ).text = "Cut/Trim Line (outer 1/4\" seam allowance)"
            curr_y += 25

            # Reassembly Legend Note
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x),
                y=str(curr_y),
                style="font-size:11px;font-family:sans-serif;fill:#555555;font-weight:bold;",
            ).text = "Align / Glue Tabs:"
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x),
                y=str(curr_y + 16),
                style="font-size:10px;font-family:sans-serif;fill:#888888;font-style:italic;",
            ).text = "Used to reassemble sections printed across page boundaries."
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(panel_x),
                y=str(curr_y + 28),
                style="font-size:10px;font-family:sans-serif;fill:#888888;font-style:italic;",
            ).text = "Glue the shaded tab over the matching Align dashed line."

            # 5. Calibration Square
            sq_size = 1.0 * core.PX_PER_INCH
            sq_abs_x = p0_x + margin
            sq_abs_y = p0_y + ph - margin - sq_size
            sq_g = etree.SubElement(layout_layer, "{%s}g" % core.SVG_NS)
            etree.SubElement(
                sq_g,
                "{%s}rect" % core.SVG_NS,
                x=str(sq_abs_x),
                y=str(sq_abs_y),
                width=str(sq_size),
                height=str(sq_size),
                style="fill:none;stroke:#000000;stroke-width:1.5;",
            )
            etree.SubElement(
                sq_g,
                "{%s}text" % core.SVG_NS,
                x=str(sq_abs_x + sq_size / 2),
                y=str(sq_abs_y + sq_size / 2),
                style="font-size:12px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
            ).text = "1 in"

        # 6. Optional Page 2: Fabric Requirements
        if self.options.include_preview and self.options.include_fabric_estimation and 1 in page_offsets:
            p1_x, p1_y = page_offsets[1]
            
            # Title
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(p1_x + margin),
                y=str(p1_y + margin + 30),
                style="font-size:22px;font-family:sans-serif;font-weight:bold;fill:#333333;",
            ).text = "Fabric Requirements"

            # Sub-header
            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(p1_x + margin),
                y=str(p1_y + margin + 55),
                style="font-size:12px;font-family:sans-serif;fill:#666666;",
            ).text = "Estimates based on 40\" usable Width of Fabric (WOF) and include 3/4\" padding around each piece."

            # Calculate fabric requirements
            def get_padded_poly(poly):
                padded = core.offset_polygon(poly, 72.0, miter_limit=2.0)
                if not padded:
                    xs = [pt[0] for pt in poly]
                    ys = [pt[1] for pt in poly]
                    padded = [
                        (min(xs) - 72.0, min(ys) - 72.0),
                        (max(xs) + 72.0, min(ys) - 72.0),
                        (max(xs) + 72.0, max(ys) + 72.0),
                        (min(xs) - 72.0, max(ys) + 72.0)
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

            wof_px = 3840.0
            fabric_estimates = []
            for color_hex, grp in fabric_groups.items():
                fixed_boxes = [get_fixed_box(r.polygon) for r in grp]
                free_boxes = [get_free_box(r.polygon) for r in grp]
                
                fixed_height_px = pack_fabric_strip(fixed_boxes, wof_px)
                free_height_px = pack_fabric_strip(free_boxes, wof_px)
                
                fabric_estimates.append({
                    "color": color_hex,
                    "pieces_count": len(grp),
                    "fixed_in": fixed_height_px / 96.0,
                    "free_in": free_height_px / 96.0
                })

            table_x = p1_x + margin + 40
            table_y = p1_y + margin + 100
            
            headers = ["Fabric", "Hex", "Pieces", "Direction-Fixed", "Direction-Free", "Suggested Purchase"]
            col_offsets = [0, 60, 150, 220, 350, 480]
            
            header_y = table_y + 18
            etree.SubElement(
                layout_layer,
                "{%s}line" % core.SVG_NS,
                x1=str(table_x),
                y1=str(header_y + 6),
                x2=str(p1_x + pw - margin - 40),
                y2=str(header_y + 6),
                style="stroke:#cccccc;stroke-width:1.0;",
            )
            for text, offset in zip(headers, col_offsets):
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(table_x + offset),
                    y=str(header_y),
                    style="font-size:11px;font-family:sans-serif;font-weight:bold;fill:#555555;",
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
                    style="font-size:10px;font-family:sans-serif;fill:#444444;",
                ).text = est['color']
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(table_x + 150),
                    y=str(row_y),
                    style="font-size:10px;font-family:sans-serif;fill:#444444;",
                ).text = str(est['pieces_count'])
                
                fixed_yd = est['fixed_in'] / 36.0
                fixed_str = f"{est['fixed_in']:.1f}\" ({fixed_yd:.2f} yd)"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(table_x + 220),
                    y=str(row_y),
                    style="font-size:10px;font-family:sans-serif;fill:#444444;",
                ).text = fixed_str
                
                free_yd = est['free_in'] / 36.0
                free_str = f"{est['free_in']:.1f}\" ({free_yd:.2f} yd)"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(table_x + 350),
                    y=str(row_y),
                    style="font-size:10px;font-family:sans-serif;fill:#444444;",
                ).text = free_str
                
                if est['free_in'] <= 9.0:
                    suggested = "Fat Eighth (FE) / Scrap"
                elif est['free_in'] <= 18.0:
                    suggested = "Fat Quarter (FQ)"
                else:
                    eighths = math.ceil(free_yd * 8.0)
                    suggested = f"{eighths/8.0:.3f} yd ({eighths}/8 yd)"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(table_x + 480),
                    y=str(row_y),
                    style="font-size:10px;font-family:sans-serif;fill:#333333;font-weight:bold;",
                ).text = suggested
                
                etree.SubElement(
                    layout_layer,
                    "{%s}line" % core.SVG_NS,
                    x1=str(table_x),
                    y1=str(row_y + 8),
                    x2=str(p1_x + pw - margin - 40),
                    y2=str(row_y + 8),
                    style="stroke:#eeeeee;stroke-width:0.5;",
                )
                row_y += 24

        # SHARED PDF RENDERER (Agnostic to Layout Mode)
        for i, item in enumerate(packable_items):
            if item["target_page"] not in page_offsets:
                continue
            page_offset_x, page_offset_y = page_offsets[item["target_page"]]

            sec_g = etree.SubElement(
                layout_layer, "{%s}g" % core.SVG_NS, id=f"template-{item['prefix']}-{i}"
            )
            sec_g.set(
                "transform",
                f"translate({page_offset_x + margin + item['page_x']}, {page_offset_y + margin + item['page_y']})",
            )

            # Optional Debug Label
            if self.options.show_section_labels:
                etree.SubElement(
                    sec_g,
                    "{%s}text" % core.SVG_NS,
                    x="0",
                    y="-5",
                    style="font-size:12px;font-family:sans-serif;fill:#0000aa;font-weight:bold;",
                ).text = f"Section {item['prefix']}{item['part_str']}"

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

            # The Universal Magic Transform
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

            has_custom = (len(user_colors) > 0)
            color_mode = block_data.prefs.get("color_mode", "piece")

            for idx, r in enumerate(item["regions"]):
                r_d = (
                    "M {:.4f},{:.4f} ".format(*r["polygon"][0])
                    + " ".join("L {:.4f},{:.4f}".format(*p) for p in r["polygon"][1:])
                    + " Z"
                )
                
                # Retrieve assigned fabric color
                assigned_col = user_colors.get(str(r["id"])) or user_colors.get(r["id"])
                if not assigned_col:
                    if has_custom:
                        assigned_col = core.get_color_for_label(r["label"], color_mode, idx)
                    else:
                        assigned_col = "#d6eaf8"  # default blue warning
                
                # Check if piece is too small for tag
                poly = r["polygon"]
                pw_r = max(p[0] for p in poly) - min(p[0] for p in poly)
                ph_r = max(p[1] for p in poly) - min(p[1] for p in poly)
                area_r = core.polygon_area(poly)
                is_too_small = (pw_r < 40.0 or ph_r < 40.0 or area_r < 3686.0)
                
                # Determine fill color
                mode = self.options.template_color_mode
                if mode == "full" or (mode == "tag" and is_too_small):
                    fill_col = assigned_col
                else:
                    fill_col = "#ffffff"
                    
                etree.SubElement(
                    shift_g,
                    "{%s}path" % core.SVG_NS,
                    d=r_d,
                    style=f"fill:{fill_col};stroke:#000000;stroke-width:2.0;stroke-linejoin:round;",
                )
                
                r_cx, r_cy = core.polygon_centroid(r["polygon"])
                
                # Draw text and optional tag
                if mode == "tag" and not is_too_small:
                    etree.SubElement(
                        shift_g,
                        "{%s}text" % core.SVG_NS,
                        x=f"{r_cx:.2f}",
                        y=f"{r_cy - 8:.2f}",
                        style="font-size:14px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                    ).text = r["label"]
                    etree.SubElement(
                        shift_g,
                        "{%s}rect" % core.SVG_NS,
                        x=f"{r_cx - 12:.2f}",
                        y=f"{r_cy + 4:.2f}",
                        width="24",
                        height="16",
                        style=f"fill:{assigned_col};stroke:#000000;stroke-width:0.5;",
                    )
                else:
                    etree.SubElement(
                        shift_g,
                        "{%s}text" % core.SVG_NS,
                        x=f"{r_cx:.2f}",
                        y=f"{r_cy:.2f}",
                        style="font-size:14px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                    ).text = r["label"]

            # FIX: DYNAMIC TAB SIZING MATH
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

            overlap_px = margin

            # CUT LINES (Only drawn exactly where the shape hits the cell boundary)
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

            # PERFECTLY MATED TABS
            if item["right_glue"] and r_span:
                tx, ty, tab_id = item["core_w"], r_min, item["right_glue"]
                etree.SubElement(
                    pad_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(tx),
                    y=str(ty),
                    width=str(overlap_px),
                    height=str(r_span),
                    style="fill:#cccccc;fill-opacity:0.6;stroke:none;",
                )
                etree.SubElement(
                    pad_g,
                    "{%s}text" % core.SVG_NS,
                    x=str(tx + overlap_px / 2),
                    y=str(ty + r_span / 2),
                    transform=f"rotate(-90 {tx + overlap_px / 2} {ty + r_span / 2})",
                    style="font-size:12px;font-family:sans-serif;font-weight:bold;text-anchor:middle;fill:#333333;",
                ).text = f"Glue {tab_id}"
            if item["left_align"] and l_span:
                tx, ty, tab_id = -overlap_px, l_min, item["left_align"]
                etree.SubElement(
                    pad_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(tx),
                    y=str(ty),
                    width=str(overlap_px),
                    height=str(l_span),
                    style="fill:none;stroke:#aaaaaa;stroke-width:1.0;stroke-dasharray:4,4;",
                )
                etree.SubElement(
                    pad_g,
                    "{%s}text" % core.SVG_NS,
                    x=str(tx + overlap_px / 2),
                    y=str(ty + l_span / 2),
                    transform=f"rotate(-90 {tx + overlap_px / 2} {ty + l_span / 2})",
                    style="font-size:12px;font-family:sans-serif;font-weight:bold;text-anchor:middle;fill:#aaaaaa;",
                ).text = f"Align {tab_id}"
            if item["bottom_glue"] and b_span:
                tx, ty, tab_id = b_min, item["core_h"], item["bottom_glue"]
                etree.SubElement(
                    pad_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(tx),
                    y=str(ty),
                    width=str(b_span),
                    height=str(overlap_px),
                    style="fill:#cccccc;fill-opacity:0.6;stroke:none;",
                )
                etree.SubElement(
                    pad_g,
                    "{%s}text" % core.SVG_NS,
                    x=str(tx + b_span / 2),
                    y=str(ty + overlap_px / 2 + 4),
                    style="font-size:12px;font-family:sans-serif;font-weight:bold;text-anchor:middle;fill:#333333;",
                ).text = f"Glue {tab_id}"
            if item["top_align"] and t_span:
                tx, ty, tab_id = t_min, -overlap_px, item["top_align"]
                etree.SubElement(
                    pad_g,
                    "{%s}rect" % core.SVG_NS,
                    x=str(tx),
                    y=str(ty),
                    width=str(t_span),
                    height=str(overlap_px),
                    style="fill:none;stroke:#aaaaaa;stroke-width:1.0;stroke-dasharray:4,4;",
                )
                etree.SubElement(
                    pad_g,
                    "{%s}text" % core.SVG_NS,
                    x=str(tx + t_span / 2),
                    y=str(ty + overlap_px / 2 + 4),
                    style="font-size:12px;font-family:sans-serif;font-weight:bold;text-anchor:middle;fill:#aaaaaa;",
                ).text = f"Align {tab_id}"

        parent.append(layout_layer)


if __name__ == "__main__":
    ExportPlugin().run()
