#!/usr/bin/env python3
import math
import re

import inkex
from lxml import etree

import quilttools_fpp_core as core
import quilttools_fpp_fabric
import quilttools_cutplan
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
        pars.add_argument("--template_color_mode", type=str, default="tag")
        pars.add_argument("--mirror_templates", type=inkex.Boolean, default=True)
        pars.add_argument("--mirror_preview", type=inkex.Boolean, default=False)
        pars.add_argument("--block_name", type=str, default="My Quilt Block")
        pars.add_argument("--designer_name", type=str, default="")
        pars.add_argument("--finished_size_in", type=float, default=12.0)
        pars.add_argument("--finished_sizes", type=str, default="")
        pars.add_argument("--template_copies", type=int, default=1)
        pars.add_argument("--oversize_batch", type=inkex.Boolean, default=True)
        pars.add_argument("--cutting_math", type=str, default="techniques")
        pars.add_argument("--template_dedupe", type=str, default="all")
        pars.add_argument("--hst_templates", type=inkex.Boolean, default=True)
        pars.add_argument("--squares_cutting_list_only", type=inkex.Boolean, default=False)
        pars.add_argument("--copyright_notice", type=str, default="For personal use only.")
        pars.add_argument("--notebook", type=str, default="")
        pars.add_argument("--theme_override", type=str, default="")
        pars.add_argument("--include_pattern_test_square", type=inkex.Boolean, default=False)
        pars.add_argument("--show_page_boundaries", type=inkex.Boolean, default=True)
        
        # Precut options
        pars.add_argument("--use_precuts", type=inkex.Boolean, default=False)
        pars.add_argument("--precut_mini_charm", type=inkex.Boolean, default=True)
        pars.add_argument("--precut_charm", type=inkex.Boolean, default=True)
        pars.add_argument("--precut_layer_cake", type=inkex.Boolean, default=True)
        pars.add_argument("--precut_jelly_roll", type=inkex.Boolean, default=True)
        pars.add_argument("--precut_fat_16th", type=inkex.Boolean, default=True)
        pars.add_argument("--precut_fat_8th", type=inkex.Boolean, default=True)
        pars.add_argument("--precut_fat_quarter", type=inkex.Boolean, default=True)

        # Unique page-specific parameters to avoid collisions
        pars.add_argument("--finished_size_in_fpp", type=float, default=0.0)
        pars.add_argument("--finished_sizes_fpp", type=str, default="")
        pars.add_argument("--template_copies_fpp", type=int, default=1)
        
        pars.add_argument("--finished_size_in_temp", type=float, default=0.0)
        pars.add_argument("--finished_sizes_temp", type=str, default="")
        pars.add_argument("--template_copies_temp", type=int, default=1)
        pars.add_argument("--template_dedupe_temp", type=str, default="all")
        pars.add_argument("--squares_cutting_list_only_temp", type=inkex.Boolean, default=False)
        
        pars.add_argument("--finished_size_in_mixed", type=float, default=0.0)
        pars.add_argument("--finished_sizes_mixed", type=str, default="")
        pars.add_argument("--template_copies_mixed", type=int, default=1)
        pars.add_argument("--template_dedupe_mixed", type=str, default="all")
        pars.add_argument("--squares_cutting_list_only_mixed", type=inkex.Boolean, default=False)
        pars.add_argument("--wof_draw_scale_pct", type=int, default=75)

    def _show_gtk_setup_dialog(self, block_data):
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk
        except Exception:
            return self._show_tk_setup_dialog(block_data)

        import os
        import json
        
        prefs_path = os.path.join(os.path.dirname(__file__), "quilttools_fpp_export_prefs.json")
        if os.path.exists(prefs_path):
            try:
                with open(prefs_path, "r", encoding="utf-8") as f:
                    saved_prefs = json.load(f)
                    if "page_size" in saved_prefs:
                        self.options.page_size = saved_prefs["page_size"]
                    if "orientation" in saved_prefs:
                        self.options.orientation = saved_prefs["orientation"]
                    if "margin_in" in saved_prefs:
                        self.options.margin_in = float(saved_prefs["margin_in"])
                    if "sa_in" in saved_prefs:
                        self.options.sa_in = float(saved_prefs["sa_in"])
                    if "spacing_in" in saved_prefs:
                        self.options.spacing_in = float(saved_prefs["spacing_in"])
                    if "template_color_mode" in saved_prefs:
                        self.options.template_color_mode = saved_prefs["template_color_mode"]
                    if "mirror_templates" in saved_prefs:
                        self.options.mirror_templates = bool(saved_prefs["mirror_templates"])
                    if "mirror_preview" in saved_prefs:
                        self.options.mirror_preview = bool(saved_prefs["mirror_preview"])
                    if "wof_draw_scale_pct" in saved_prefs:
                        self.options.wof_draw_scale_pct = int(saved_prefs["wof_draw_scale_pct"])
                    if "use_precuts" in saved_prefs:
                        self.options.use_precuts = bool(saved_prefs["use_precuts"])
                    if "precut_mini_charm" in saved_prefs:
                        self.options.precut_mini_charm = bool(saved_prefs["precut_mini_charm"])
                    if "precut_charm" in saved_prefs:
                        self.options.precut_charm = bool(saved_prefs["precut_charm"])
                    if "precut_layer_cake" in saved_prefs:
                        self.options.precut_layer_cake = bool(saved_prefs["precut_layer_cake"])
                    if "precut_jelly_roll" in saved_prefs:
                        self.options.precut_jelly_roll = bool(saved_prefs["precut_jelly_roll"])
                    if "precut_fat_16th" in saved_prefs:
                        self.options.precut_fat_16th = bool(saved_prefs["precut_fat_16th"])
                    if "precut_fat_8th" in saved_prefs:
                        self.options.precut_fat_8th = bool(saved_prefs["precut_fat_8th"])
                    if "precut_fat_quarter" in saved_prefs:
                        self.options.precut_fat_quarter = bool(saved_prefs["precut_fat_quarter"])
                    if "include_pattern_test_square" in saved_prefs:
                        self.options.include_pattern_test_square = bool(saved_prefs["include_pattern_test_square"])
                    if "show_page_boundaries" in saved_prefs:
                        self.options.show_page_boundaries = bool(saved_prefs["show_page_boundaries"])
            except Exception:
                pass

        dialog = Gtk.Dialog(title="Quilt Tools - Export Setup", transient_for=None)
        dialog.set_default_size(520, 520)
        dialog.set_modal(True)
        dialog.set_keep_above(True)
        content = dialog.get_content_area()
        content.set_spacing(8)

        # Header
        hdr = Gtk.Label()
        hdr.set_markup("<span size='large' weight='bold'>Finalize Export Settings</span>")
        hdr.set_margin_top(10)
        hdr.set_margin_bottom(5)
        content.pack_start(hdr, False, False, 0)

        notebook = Gtk.Notebook()
        notebook.set_margin_start(5)
        notebook.set_margin_end(5)
        content.pack_start(notebook, True, True, 0)

        # PAGE 1: Credits & Page Features
        grid1 = Gtk.Grid()
        grid1.set_column_spacing(10)
        grid1.set_row_spacing(8)
        grid1.set_margin_start(15)
        grid1.set_margin_end(15)
        grid1.set_margin_top(15)
        grid1.set_margin_bottom(15)

        # Block Name
        lbl_bn = Gtk.Label(label="Block / Pattern Name:")
        lbl_bn.set_halign(Gtk.Align.START)
        grid1.attach(lbl_bn, 0, 0, 1, 1)
        entry_block_name = Gtk.Entry()
        entry_block_name.set_text(self.options.block_name or "")
        entry_block_name.set_hexpand(True)
        grid1.attach(entry_block_name, 1, 0, 1, 1)

        # Designer Name
        lbl_dn = Gtk.Label(label="Designer Name / Credit:")
        lbl_dn.set_halign(Gtk.Align.START)
        grid1.attach(lbl_dn, 0, 1, 1, 1)
        entry_designer_name = Gtk.Entry()
        entry_designer_name.set_text(self.options.designer_name or "")
        entry_designer_name.set_hexpand(True)
        grid1.attach(entry_designer_name, 1, 1, 1, 1)

        # Copyright Notice
        lbl_cp = Gtk.Label(label="Copyright Notice:")
        lbl_cp.set_halign(Gtk.Align.START)
        grid1.attach(lbl_cp, 0, 2, 1, 1)
        entry_copyright = Gtk.Entry()
        entry_copyright.set_text(self.options.copyright_notice or "")
        entry_copyright.set_hexpand(True)
        grid1.attach(entry_copyright, 1, 2, 1, 1)

        # Width of Fabric (WOF)
        lbl_wof = Gtk.Label(label="Width of Fabric (WOF) (in):")
        lbl_wof.set_halign(Gtk.Align.START)
        grid1.attach(lbl_wof, 0, 3, 1, 1)
        adj_wof = Gtk.Adjustment(value=self.options.wof_in, lower=20.0, upper=60.0, step_increment=0.5, page_increment=5.0, page_size=0.0)
        spin_wof = Gtk.SpinButton(adjustment=adj_wof, climb_rate=0.5, digits=1)
        grid1.attach(spin_wof, 1, 3, 1, 1)

        # Checkboxes for layout details
        chk_preview = Gtk.CheckButton(label="Include Cover Page (Page 1 Title/Summary & Hero)")
        chk_preview.set_active(self.options.include_preview)
        grid1.attach(chk_preview, 0, 4, 2, 1)

        chk_align_img = Gtk.CheckButton(label="Include Section Map Page (Page 2)")
        chk_align_img.set_active(self.options.separate_section_alignment_image)
        grid1.attach(chk_align_img, 0, 5, 2, 1)

        chk_fabric_est = Gtk.CheckButton(label="Include Fabric Requirements Page")
        chk_fabric_est.set_active(self.options.include_fabric_estimation)
        grid1.attach(chk_fabric_est, 0, 6, 2, 1)

        chk_visualize_fab = Gtk.CheckButton(label="Draw Fabric Cutting Layout Map on Canvas")
        chk_visualize_fab.set_active(self.options.visualize_fabric_layout)
        grid1.attach(chk_visualize_fab, 0, 7, 2, 1)

        chk_colouring = Gtk.CheckButton(label="Include Blank Colouring Outline Page at end")
        chk_colouring.set_active(self.options.include_colouring_page)
        grid1.attach(chk_colouring, 0, 8, 2, 1)

        chk_sec_labels = Gtk.CheckButton(label="Show section header labels (e.g. 'Section A')")
        chk_sec_labels.set_active(self.options.show_section_labels)
        grid1.attach(chk_sec_labels, 0, 9, 2, 1)

        notebook.append_page(grid1, Gtk.Label(label="Credits & Page Features"))

        # PAGE 2: Page Setup & Margins
        grid2 = Gtk.Grid()
        grid2.set_column_spacing(10)
        grid2.set_row_spacing(8)
        grid2.set_margin_start(15)
        grid2.set_margin_end(15)
        grid2.set_margin_top(15)
        grid2.set_margin_bottom(15)

        # Paper Size
        lbl_ps = Gtk.Label(label="Paper Size:")
        lbl_ps.set_halign(Gtk.Align.START)
        grid2.attach(lbl_ps, 0, 0, 1, 1)
        combo_page_size = Gtk.ComboBoxText()
        combo_page_size.append("letter", "US Letter (8.5 x 11 in)")
        combo_page_size.append("a4", "A4 (8.27 x 11.69 in)")
        combo_page_size.append("a3", "A3 (11.69 x 16.54 in)")
        combo_page_size.set_active_id(self.options.page_size or "letter")
        grid2.attach(combo_page_size, 1, 0, 1, 1)

        # Orientation
        lbl_or = Gtk.Label(label="Orientation:")
        lbl_or.set_halign(Gtk.Align.START)
        grid2.attach(lbl_or, 0, 1, 1, 1)
        combo_orient = Gtk.ComboBoxText()
        combo_orient.append("portrait", "Portrait")
        combo_orient.append("landscape", "Landscape")
        combo_orient.set_active_id(self.options.orientation or "portrait")
        grid2.attach(combo_orient, 1, 1, 1, 1)

        # Page Margin
        lbl_mg = Gtk.Label(label="Page Margin (inches):")
        lbl_mg.set_halign(Gtk.Align.START)
        grid2.attach(lbl_mg, 0, 2, 1, 1)
        adj_margin = Gtk.Adjustment(value=self.options.margin_in, lower=0.0, upper=2.0, step_increment=0.05, page_increment=0.2, page_size=0.0)
        spin_margin = Gtk.SpinButton(adjustment=adj_margin, climb_rate=0.05, digits=2)
        grid2.attach(spin_margin, 1, 2, 1, 1)

        # Seam Allowance
        lbl_sa = Gtk.Label(label="Seam Allowance Size (inches):")
        lbl_sa.set_halign(Gtk.Align.START)
        grid2.attach(lbl_sa, 0, 3, 1, 1)
        adj_sa = Gtk.Adjustment(value=self.options.sa_in, lower=0.125, upper=1.0, step_increment=0.0625, page_increment=0.125, page_size=0.0)
        spin_sa = Gtk.SpinButton(adjustment=adj_sa, climb_rate=0.01, digits=3)
        grid2.attach(spin_sa, 1, 3, 1, 1)

        # Min Spacing
        lbl_sp = Gtk.Label(label="Min Spacing between pieces (in):")
        lbl_sp.set_halign(Gtk.Align.START)
        grid2.attach(lbl_sp, 0, 4, 1, 1)
        adj_spacing = Gtk.Adjustment(value=self.options.spacing_in, lower=0.0, upper=2.0, step_increment=0.05, page_increment=0.2, page_size=0.0)
        spin_spacing = Gtk.SpinButton(adjustment=adj_spacing, climb_rate=0.05, digits=2)
        grid2.attach(spin_spacing, 1, 4, 1, 1)

        # Colour Fill Mode
        lbl_cm = Gtk.Label(label="Template Fabric Colour Fill:")
        lbl_cm.set_halign(Gtk.Align.START)
        grid2.attach(lbl_cm, 0, 5, 1, 1)
        combo_color_mode = Gtk.ComboBoxText()
        combo_color_mode.append("none", "White (Line-Art only)")
        combo_color_mode.append("tag", "Colour Swatch (Minimal ink)")
        combo_color_mode.append("full", "Full Colour Fill (Ink-heavy)")
        combo_color_mode.set_active_id(self.options.template_color_mode or "tag")
        grid2.attach(combo_color_mode, 1, 5, 1, 1)

        # Mirror Templates
        chk_mirror_temp = Gtk.CheckButton(label="Mirror templates on Pages 2+ (Recommended for FPP)")
        chk_mirror_temp.set_active(self.options.mirror_templates)
        grid2.attach(chk_mirror_temp, 0, 6, 2, 1)

        # Mirror Preview
        chk_mirror_prev = Gtk.CheckButton(label="Mirror Page 1 Block Preview (Usually false)")
        chk_mirror_prev.set_active(self.options.mirror_preview)
        grid2.attach(chk_mirror_prev, 0, 7, 2, 1)

        # WOF draw scale pct
        lbl_wd = Gtk.Label(label="WOF Map Width on Page:")
        lbl_wd.set_halign(Gtk.Align.START)
        grid2.attach(lbl_wd, 0, 8, 1, 1)
        combo_wof_scale = Gtk.ComboBoxText()
        combo_wof_scale.append("50", "50% of available page width")
        combo_wof_scale.append("75", "75% of available page width")
        combo_wof_scale.append("100", "100% of available page width")
        combo_wof_scale.set_active_id(str(self.options.wof_draw_scale_pct or "75"))
        grid2.attach(combo_wof_scale, 1, 8, 1, 1)

        # Pattern Page Test Square
        chk_pattern_cal = Gtk.CheckButton(label="Include 2nd test square on pattern pages (smart packed)")
        chk_pattern_cal.set_active(self.options.include_pattern_test_square)
        grid2.attach(chk_pattern_cal, 0, 9, 2, 1)

        # Show Page Boundaries
        chk_boundaries = Gtk.CheckButton(label="Show printable page boundaries (blue dashed line & page labels)")
        chk_boundaries.set_active(self.options.show_page_boundaries)
        grid2.attach(chk_boundaries, 0, 10, 2, 1)

        notebook.append_page(grid2, Gtk.Label(label="Page Setup & Styling"))

        # PAGE 3: Fabric & Precuts Setup
        grid3 = Gtk.Grid()
        grid3.set_column_spacing(10)
        grid3.set_row_spacing(8)
        grid3.set_margin_start(15)
        grid3.set_margin_end(15)
        grid3.set_margin_top(15)
        grid3.set_margin_bottom(15)

        chk_use_precuts = Gtk.CheckButton(label="Use Precuts (optimize suggested purchase for precut sizes)")
        chk_use_precuts.set_active(self.options.use_precuts)
        grid3.attach(chk_use_precuts, 0, 0, 2, 1)

        lbl_options = Gtk.Label(label="Enabled Precut Options (used when 'Use Precuts' is checked):")
        lbl_options.set_halign(Gtk.Align.START)
        grid3.attach(lbl_options, 0, 1, 2, 1)

        chk_mc = Gtk.CheckButton(label="Mini Charm (2.5\" square)")
        chk_mc.set_active(self.options.precut_mini_charm)
        grid3.attach(chk_mc, 0, 2, 2, 1)

        chk_ch = Gtk.CheckButton(label="Charm (5\" square)")
        chk_ch.set_active(self.options.precut_charm)
        grid3.attach(chk_ch, 0, 3, 2, 1)

        chk_lc = Gtk.CheckButton(label="Layer Cake (10\" square)")
        chk_lc.set_active(self.options.precut_layer_cake)
        grid3.attach(chk_lc, 0, 4, 2, 1)

        chk_jr = Gtk.CheckButton(label="Jelly Roll (2.5\" x WOF strip)")
        chk_jr.set_active(self.options.precut_jelly_roll)
        grid3.attach(chk_jr, 0, 5, 2, 1)

        chk_f16 = Gtk.CheckButton(label="Fat 16th (9\" x 11\")")
        chk_f16.set_active(self.options.precut_fat_16th)
        grid3.attach(chk_f16, 0, 6, 2, 1)

        chk_f8 = Gtk.CheckButton(label="Fat 8th (9\" x 21\")")
        chk_f8.set_active(self.options.precut_fat_8th)
        grid3.attach(chk_f8, 0, 7, 2, 1)

        chk_fq = Gtk.CheckButton(label="Fat Quarter (18\" x 21\")")
        chk_fq.set_active(self.options.precut_fat_quarter)
        grid3.attach(chk_fq, 0, 8, 2, 1)

        notebook.append_page(grid3, Gtk.Label(label="Fabric & Precuts"))

        # Buttons
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Export Pattern", Gtk.ResponseType.OK)

        dialog.set_modal(True)
        dialog.set_keep_above(True)
        dialog.show_all()
        dialog.present()

        response = dialog.run()

        success = False
        if response == Gtk.ResponseType.OK:
            self.options.block_name = entry_block_name.get_text().strip()
            self.options.designer_name = entry_designer_name.get_text().strip()
            self.options.copyright_notice = entry_copyright.get_text().strip()
            self.options.wof_in = spin_wof.get_value()
            
            self.options.include_preview = chk_preview.get_active()
            self.options.separate_section_alignment_image = chk_align_img.get_active()
            self.options.include_fabric_estimation = chk_fabric_est.get_active()
            self.options.visualize_fabric_layout = chk_visualize_fab.get_active()
            self.options.include_colouring_page = chk_colouring.get_active()
            self.options.show_section_labels = chk_sec_labels.get_active()
            
            self.options.page_size = combo_page_size.get_active_id() or "letter"
            self.options.orientation = combo_orient.get_active_id() or "portrait"
            self.options.margin_in = spin_margin.get_value()
            self.options.sa_in = spin_sa.get_value()
            self.options.spacing_in = spin_spacing.get_value()
            self.options.template_color_mode = combo_color_mode.get_active_id() or "none"
            
            self.options.mirror_templates = chk_mirror_temp.get_active()
            self.options.mirror_preview = chk_mirror_prev.get_active()
            
            scale_id = combo_wof_scale.get_active_id() or "75"
            self.options.wof_draw_scale_pct = int(scale_id)
            
            self.options.use_precuts = chk_use_precuts.get_active()
            self.options.precut_mini_charm = chk_mc.get_active()
            self.options.precut_charm = chk_ch.get_active()
            self.options.precut_layer_cake = chk_lc.get_active()
            self.options.precut_jelly_roll = chk_jr.get_active()
            self.options.precut_fat_16th = chk_f16.get_active()
            self.options.precut_fat_8th = chk_f8.get_active()
            self.options.precut_fat_quarter = chk_fq.get_active()
            self.options.include_pattern_test_square = chk_pattern_cal.get_active()
            self.options.show_page_boundaries = chk_boundaries.get_active()
            
            # Save sticky preferences
            prefs_to_save = {
                "page_size": self.options.page_size,
                "orientation": self.options.orientation,
                "margin_in": self.options.margin_in,
                "sa_in": self.options.sa_in,
                "spacing_in": self.options.spacing_in,
                "template_color_mode": self.options.template_color_mode,
                "mirror_templates": self.options.mirror_templates,
                "mirror_preview": self.options.mirror_preview,
                "wof_draw_scale_pct": self.options.wof_draw_scale_pct,
                "use_precuts": self.options.use_precuts,
                "precut_mini_charm": self.options.precut_mini_charm,
                "precut_charm": self.options.precut_charm,
                "precut_layer_cake": self.options.precut_layer_cake,
                "precut_jelly_roll": self.options.precut_jelly_roll,
                "precut_fat_16th": self.options.precut_fat_16th,
                "precut_fat_8th": self.options.precut_fat_8th,
                "precut_fat_quarter": self.options.precut_fat_quarter,
                "include_pattern_test_square": self.options.include_pattern_test_square,
                "show_page_boundaries": self.options.show_page_boundaries,
            }
            try:
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs_to_save, f, indent=2)
            except Exception:
                pass
                
            success = True

        dialog.destroy()
        while Gtk.events_pending():
            Gtk.main_iteration()

        return success

    def _show_tk_setup_dialog(self, block_data):
        import os
        import json
        import tkinter as tk
        from tkinter import ttk

        prefs_path = os.path.join(os.path.dirname(__file__), "quilttools_fpp_export_prefs.json")
        if os.path.exists(prefs_path):
            try:
                with open(prefs_path, "r", encoding="utf-8") as f:
                    saved_prefs = json.load(f)
                    if "page_size" in saved_prefs:
                        self.options.page_size = saved_prefs["page_size"]
                    if "orientation" in saved_prefs:
                        self.options.orientation = saved_prefs["orientation"]
                    if "margin_in" in saved_prefs:
                        self.options.margin_in = float(saved_prefs["margin_in"])
                    if "sa_in" in saved_prefs:
                        self.options.sa_in = float(saved_prefs["sa_in"])
                    if "spacing_in" in saved_prefs:
                        self.options.spacing_in = float(saved_prefs["spacing_in"])
                    if "template_color_mode" in saved_prefs:
                        self.options.template_color_mode = saved_prefs["template_color_mode"]
                    if "mirror_templates" in saved_prefs:
                        self.options.mirror_templates = bool(saved_prefs["mirror_templates"])
                    if "mirror_preview" in saved_prefs:
                        self.options.mirror_preview = bool(saved_prefs["mirror_preview"])
                    if "wof_draw_scale_pct" in saved_prefs:
                        self.options.wof_draw_scale_pct = int(saved_prefs["wof_draw_scale_pct"])
                    if "use_precuts" in saved_prefs:
                        self.options.use_precuts = bool(saved_prefs["use_precuts"])
                    if "precut_mini_charm" in saved_prefs:
                        self.options.precut_mini_charm = bool(saved_prefs["precut_mini_charm"])
                    if "precut_charm" in saved_prefs:
                        self.options.precut_charm = bool(saved_prefs["precut_charm"])
                    if "precut_layer_cake" in saved_prefs:
                        self.options.precut_layer_cake = bool(saved_prefs["precut_layer_cake"])
                    if "precut_jelly_roll" in saved_prefs:
                        self.options.precut_jelly_roll = bool(saved_prefs["precut_jelly_roll"])
                    if "precut_fat_16th" in saved_prefs:
                        self.options.precut_fat_16th = bool(saved_prefs["precut_fat_16th"])
                    if "precut_fat_8th" in saved_prefs:
                        self.options.precut_fat_8th = bool(saved_prefs["precut_fat_8th"])
                    if "precut_fat_quarter" in saved_prefs:
                        self.options.precut_fat_quarter = bool(saved_prefs["precut_fat_quarter"])
                    if "include_pattern_test_square" in saved_prefs:
                        self.options.include_pattern_test_square = bool(saved_prefs["include_pattern_test_square"])
                    if "show_page_boundaries" in saved_prefs:
                        self.options.show_page_boundaries = bool(saved_prefs["show_page_boundaries"])
            except Exception:
                pass

        result = {"success": False}

        root = tk.Tk()
        root.title("Quilt Tools - Export Setup")
        root.geometry("560x580")
        root.minsize(520, 520)
        root.attributes("-topmost", True)

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        hdr_frame = ttk.Frame(root, padding=10)
        hdr_frame.pack(fill="x")
        hdr_label = ttk.Label(hdr_frame, text="Finalize Export Settings", font=("sans-serif", 13, "bold"))
        hdr_label.pack()

        notebook = ttk.Notebook(root, padding=5)
        notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # PAGE 1: Credits & Page Features
        page1 = ttk.Frame(notebook, padding=15)
        notebook.add(page1, text="Credits & Page Features")

        ttk.Label(page1, text="Block / Pattern Name:").grid(row=0, column=0, sticky="w", pady=4)
        entry_bn = ttk.Entry(page1, width=32)
        entry_bn.insert(0, self.options.block_name or "")
        entry_bn.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(page1, text="Designer / Author Name:").grid(row=1, column=0, sticky="w", pady=4)
        entry_dn = ttk.Entry(page1, width=32)
        entry_dn.insert(0, self.options.designer_name or "")
        entry_dn.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(page1, text="Copyright Notice:").grid(row=2, column=0, sticky="w", pady=4)
        entry_cr = ttk.Entry(page1, width=32)
        entry_cr.insert(0, self.options.copyright_notice or "")
        entry_cr.grid(row=2, column=1, sticky="w", pady=4)

        var_preview = tk.BooleanVar(value=bool(self.options.include_preview))
        ttk.Checkbutton(page1, text="Include Block Preview (Page 1)", variable=var_preview).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)

        var_sec_map = tk.BooleanVar(value=bool(self.options.separate_section_alignment_image))
        ttk.Checkbutton(page1, text="Include Section Map Page (Page 2)", variable=var_sec_map).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)

        var_fabric_est = tk.BooleanVar(value=bool(self.options.include_fabric_estimation))
        ttk.Checkbutton(page1, text="Include Fabric Requirements & Cutting List", variable=var_fabric_est).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)

        var_vis_fab = tk.BooleanVar(value=bool(self.options.visualize_fabric_layout))
        ttk.Checkbutton(page1, text="Visualize Fabric Layout Maps", variable=var_vis_fab).grid(row=6, column=0, columnspan=2, sticky="w", pady=3)

        var_colouring = tk.BooleanVar(value=bool(self.options.include_colouring_page))
        ttk.Checkbutton(page1, text="Include Colouring / Planning Page", variable=var_colouring).grid(row=7, column=0, columnspan=2, sticky="w", pady=3)

        var_sec_labels = tk.BooleanVar(value=bool(self.options.show_section_labels))
        ttk.Checkbutton(page1, text="Include Section Labels on Templates", variable=var_sec_labels).grid(row=8, column=0, columnspan=2, sticky="w", pady=3)

        # PAGE 2: Page Setup & Styling
        page2 = ttk.Frame(notebook, padding=15)
        notebook.add(page2, text="Page Setup & Styling")

        ttk.Label(page2, text="Page Size:").grid(row=0, column=0, sticky="w", pady=4)
        combo_ps = ttk.Combobox(page2, values=["letter", "a4", "legal", "tabloid", "a3"], state="readonly", width=25)
        combo_ps.set(self.options.page_size or "letter")
        combo_ps.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(page2, text="Orientation:").grid(row=1, column=0, sticky="w", pady=4)
        combo_orient = ttk.Combobox(page2, values=["portrait", "landscape"], state="readonly", width=25)
        combo_orient.set(self.options.orientation or "portrait")
        combo_orient.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(page2, text="Page Margin (in):").grid(row=2, column=0, sticky="w", pady=4)
        spin_margin = ttk.Spinbox(page2, from_=0.1, to=2.0, increment=0.05, width=10)
        spin_margin.set(str(self.options.margin_in or 0.5))
        spin_margin.grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(page2, text="Seam Allowance (in):").grid(row=3, column=0, sticky="w", pady=4)
        spin_sa = ttk.Spinbox(page2, from_=0.0, to=1.0, increment=0.05, width=10)
        spin_sa.set(str(self.options.sa_in or 0.25))
        spin_sa.grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(page2, text="Piece Spacing (in):").grid(row=4, column=0, sticky="w", pady=4)
        spin_spacing = ttk.Spinbox(page2, from_=0.0, to=1.0, increment=0.05, width=10)
        spin_spacing.set(str(self.options.spacing_in or 0.2))
        spin_spacing.grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(page2, text="Template Colour Fill:").grid(row=5, column=0, sticky="w", pady=4)
        mode_map = {"tag": "Colour Swatch (Minimal ink)", "full": "Full Colour Fill", "none": "None (Outlines only)"}
        mode_reverse = {v: k for k, v in mode_map.items()}
        combo_color = ttk.Combobox(page2, values=list(mode_map.values()), state="readonly", width=28)
        combo_color.set(mode_map.get(self.options.template_color_mode, "Colour Swatch (Minimal ink)"))
        combo_color.grid(row=5, column=1, sticky="w", pady=4)

        var_mirror_temp = tk.BooleanVar(value=bool(self.options.mirror_templates))
        ttk.Checkbutton(page2, text="Mirror templates on Pages 2+ (Recommended)", variable=var_mirror_temp).grid(row=6, column=0, columnspan=2, sticky="w", pady=3)

        var_mirror_prev = tk.BooleanVar(value=bool(self.options.mirror_preview))
        ttk.Checkbutton(page2, text="Mirror Page 1 Block Preview", variable=var_mirror_prev).grid(row=7, column=0, columnspan=2, sticky="w", pady=3)

        ttk.Label(page2, text="WOF Map Width:").grid(row=8, column=0, sticky="w", pady=4)
        combo_wof = ttk.Combobox(page2, values=["50%", "75%", "100%"], state="readonly", width=15)
        combo_wof.set(f"{self.options.wof_draw_scale_pct or 75}%")
        combo_wof.grid(row=8, column=1, sticky="w", pady=4)

        var_test_sq = tk.BooleanVar(value=bool(self.options.include_pattern_test_square))
        ttk.Checkbutton(page2, text="Include 2nd test square on pattern pages", variable=var_test_sq).grid(row=9, column=0, columnspan=2, sticky="w", pady=3)

        var_boundaries = tk.BooleanVar(value=bool(self.options.show_page_boundaries))
        ttk.Checkbutton(page2, text="Show printable page boundaries", variable=var_boundaries).grid(row=10, column=0, columnspan=2, sticky="w", pady=3)

        # PAGE 3: Fabric & Precuts
        page3 = ttk.Frame(notebook, padding=15)
        notebook.add(page3, text="Fabric & Precuts")

        var_use_precuts = tk.BooleanVar(value=bool(self.options.use_precuts))
        ttk.Checkbutton(page3, text="Use Precuts Optimization", variable=var_use_precuts).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)

        var_mc = tk.BooleanVar(value=bool(self.options.precut_mini_charm))
        ttk.Checkbutton(page3, text="Mini Charm (2.5\" square)", variable=var_mc).grid(row=1, column=0, columnspan=2, sticky="w", pady=3)

        var_ch = tk.BooleanVar(value=bool(self.options.precut_charm))
        ttk.Checkbutton(page3, text="Charm (5\" square)", variable=var_ch).grid(row=2, column=0, columnspan=2, sticky="w", pady=3)

        var_lc = tk.BooleanVar(value=bool(self.options.precut_layer_cake))
        ttk.Checkbutton(page3, text="Layer Cake (10\" square)", variable=var_lc).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)

        var_jr = tk.BooleanVar(value=bool(self.options.precut_jelly_roll))
        ttk.Checkbutton(page3, text="Jelly Roll (2.5\" x WOF)", variable=var_jr).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)

        var_f16 = tk.BooleanVar(value=bool(self.options.precut_fat_16th))
        ttk.Checkbutton(page3, text="Fat 16th (9\" x 11\")", variable=var_f16).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)

        var_f8 = tk.BooleanVar(value=bool(self.options.precut_fat_8th))
        ttk.Checkbutton(page3, text="Fat 8th (9\" x 21\")", variable=var_f8).grid(row=6, column=0, columnspan=2, sticky="w", pady=3)

        var_fq = tk.BooleanVar(value=bool(self.options.precut_fat_quarter))
        ttk.Checkbutton(page3, text="Fat Quarter (18\" x 21\")", variable=var_fq).grid(row=7, column=0, columnspan=2, sticky="w", pady=3)

        # Buttons Frame
        btn_frame = ttk.Frame(root, padding=10)
        btn_frame.pack(fill="x", side="bottom")

        def on_ok():
            self.options.block_name = entry_bn.get().strip()
            self.options.designer_name = entry_dn.get().strip()
            self.options.copyright_notice = entry_cr.get().strip()

            self.options.include_preview = var_preview.get()
            self.options.separate_section_alignment_image = var_sec_map.get()
            self.options.include_fabric_estimation = var_fabric_est.get()
            self.options.visualize_fabric_layout = var_vis_fab.get()
            self.options.include_colouring_page = var_colouring.get()
            self.options.show_section_labels = var_sec_labels.get()

            self.options.page_size = combo_ps.get() or "letter"
            self.options.orientation = combo_orient.get() or "portrait"
            try:
                self.options.margin_in = float(spin_margin.get())
            except Exception:
                pass
            try:
                self.options.sa_in = float(spin_sa.get())
            except Exception:
                pass
            try:
                self.options.spacing_in = float(spin_spacing.get())
            except Exception:
                pass
            self.options.template_color_mode = mode_reverse.get(combo_color.get(), "tag")

            self.options.mirror_templates = var_mirror_temp.get()
            self.options.mirror_preview = var_mirror_prev.get()
            wof_val = combo_wof.get().replace("%", "").strip()
            try:
                self.options.wof_draw_scale_pct = int(wof_val)
            except Exception:
                pass
            self.options.include_pattern_test_square = var_test_sq.get()
            self.options.show_page_boundaries = var_boundaries.get()

            self.options.use_precuts = var_use_precuts.get()
            self.options.precut_mini_charm = var_mc.get()
            self.options.precut_charm = var_ch.get()
            self.options.precut_layer_cake = var_lc.get()
            self.options.precut_jelly_roll = var_jr.get()
            self.options.precut_fat_16th = var_f16.get()
            self.options.precut_fat_8th = var_f8.get()
            self.options.precut_fat_quarter = var_fq.get()

            # Save sticky preferences
            prefs_to_save = {
                "page_size": self.options.page_size,
                "orientation": self.options.orientation,
                "margin_in": self.options.margin_in,
                "sa_in": self.options.sa_in,
                "spacing_in": self.options.spacing_in,
                "template_color_mode": self.options.template_color_mode,
                "mirror_templates": self.options.mirror_templates,
                "mirror_preview": self.options.mirror_preview,
                "wof_draw_scale_pct": self.options.wof_draw_scale_pct,
                "use_precuts": self.options.use_precuts,
                "precut_mini_charm": self.options.precut_mini_charm,
                "precut_charm": self.options.precut_charm,
                "precut_layer_cake": self.options.precut_layer_cake,
                "precut_jelly_roll": self.options.precut_jelly_roll,
                "precut_fat_16th": self.options.precut_fat_16th,
                "precut_fat_8th": self.options.precut_fat_8th,
                "precut_fat_quarter": self.options.precut_fat_quarter,
                "include_pattern_test_square": self.options.include_pattern_test_square,
                "show_page_boundaries": self.options.show_page_boundaries,
            }
            try:
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs_to_save, f, indent=2)
            except Exception:
                pass

            result["success"] = True
            root.destroy()

        def on_cancel():
            result["success"] = False
            root.destroy()

        ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Export Pattern", command=on_ok).pack(side="right", padx=5)

        root.protocol("WM_DELETE_WINDOW", on_cancel)
        root.mainloop()
        return result["success"]

    def _show_lint_report_gui(self, lint_report):
        has_warnings = any("[!]" in line or "WARNING" in line or "CRITICAL" in line for line in lint_report)
        if not has_warnings:
            return

        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk
            
            msg = "\n".join(lint_report)
            
            dialog = Gtk.MessageDialog(
                transient_for=None,
                modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="FPP Pattern Validation Report"
            )
            dialog.format_secondary_text(msg)
            dialog.set_keep_above(True)
            dialog.run()
            dialog.destroy()
            while Gtk.events_pending():
                Gtk.main_iteration()
        except Exception:
            inkex.errormsg("FPP Pattern Validation Warning:\n" + "\n".join(lint_report))

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

        # Resolve notebook params to master values
        tab = (self.options.notebook or "").strip()
        if tab == "fpp_tab":
            self.options.export_type = "fpp"
            self.options.finished_size_in = self.options.finished_size_in_fpp
            self.options.finished_sizes = self.options.finished_sizes_fpp
            self.options.template_copies = self.options.template_copies_fpp
        elif tab == "template_tab":
            self.options.export_type = "template"
            self.options.cutting_math = "templates_only"
            self.options.finished_size_in = self.options.finished_size_in_temp
            self.options.finished_sizes = self.options.finished_sizes_temp
            self.options.template_copies = self.options.template_copies_temp
            self.options.template_dedupe = self.options.template_dedupe_temp
            self.options.squares_cutting_list_only = self.options.squares_cutting_list_only_temp
        elif tab == "mixed_tab":
            self.options.export_type = "template"
            self.options.cutting_math = "techniques"
            self.options.finished_size_in = self.options.finished_size_in_mixed
            self.options.finished_sizes = self.options.finished_sizes_mixed
            self.options.template_copies = self.options.template_copies_mixed
            self.options.template_dedupe = self.options.template_dedupe_mixed
            self.options.squares_cutting_list_only = self.options.squares_cutting_list_only_mixed

        # Show secondary GTK dialog setup screen
        if not self._show_gtk_setup_dialog(block_data):
            return

        if self.options.action == "step1":
            self._generate_open_canvas()
        elif self.options.action == "step2":
            layout_layer = self.svg.find(f".//{{{core.SVG_NS}}}g[@id='fpp-layout-layer']")
            if layout_layer is not None:
                self._finalize_open_canvas()
            else:
                self._generate_smart_pack()

    def _deconflict_separate_section_map(self, block_data, unique_colors):
        import math
        steps, _ = core.calculate_section_sewing_order(block_data)
        num_steps = len(steps)
        
        # Calculate fit on Page 1
        pw_pg, ph_pg = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
        if self.options.orientation == "landscape":
            pw_pg, ph_pg = ph_pg, pw_pg
        margin_px = self.options.margin_in * core.PX_PER_INCH
        avail_w = pw_pg - (margin_px * 2)
        avail_h = ph_pg - (margin_px * 2)
        preview_side = min(int(avail_w * 0.90), int(avail_h * 0.42))
        space_below = avail_h - 80 - preview_side
        
        # Estimated height for assembly + legend + color key + test square
        color_rows = math.ceil(len(unique_colors) / 4) if len(unique_colors) <= 10 else 0
        required_h = 20 + (num_steps * 18) + 120 + (color_rows * 24) + 96 + 30
        
        force_separate = False
        if num_steps > 20:
            force_separate = True
        elif not self.options.separate_section_alignment_image:
            if required_h > space_below:
                force_separate = True
                
        if force_separate:
            self.options.separate_section_alignment_image = True

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
            pass

        valid_sections = {}
        bad_labels = []
        # Template dedupe: one printed template per unique SHAPE, labelled
        # "cut N". Colours are combined: a template covering more than one
        # fabric prints uncoloured (fabric placement lives on the layout
        # page). Maps: rep label -> all labels / rep labels with mixed fabric.
        self._template_dedupe = {}
        self._template_multicolor = set()
        # Hybrid export: sections opted into 'Always FPP' render as FPP
        # foundation section templates inside a template export.
        self._fpp_prefixes = set()
        if self.options.export_type == "template":
            self._fpp_prefixes = {
                str(p).upper()
                for p in (block_data.prefs.get("fpp_sections") or [])}

        def _prefix_of(label):
            m = re.match(r"^([A-Za-z]+)", label)
            return m.group(1).upper() if m else ""

        # Optional: squares/rectangles live in the cutting list only.
        skip_squares = (self.options.export_type == "template"
                        and getattr(self.options,
                                    "squares_cutting_list_only", False))
        use_tech_math = (self.options.export_type == "template"
                         and getattr(self.options, "cutting_math",
                                     "techniques") != "templates_only")
        meta_all = block_data.piece_meta() \
            if hasattr(block_data, "piece_meta") else {}
        self._squares_skipped = []

        # Resolve stitch-and-flip overrides to extend base pieces in template mode
        overrides = {}
        if use_tech_math:
            regions_map = {str(r.id): r for r in tree.leaf_regions()}
            def _poly_in(r):
                return [(p[0]/core.PX_PER_INCH, p[1]/core.PX_PER_INCH) for p in r.polygon]
            pieces_list = []
            for rid, r in regions_map.items():
                m = dict(meta_all.get(rid) or {})
                if "sf_bases" in m and m["sf_bases"]:
                    m["sf_bases"] = [str(b) for b in m["sf_bases"]]
                pieces_list.append({"id": rid, "polygon": _poly_in(r), "label": r.label,
                                    "meta": m})
            _, overrides_in, _ = quilttools_cutplan.resolve_stitch_flips(pieces_list)
            for rid, ext_poly_in in overrides_in.items():
                overrides[int(rid)] = [(p[0] * core.PX_PER_INCH, p[1] * core.PX_PER_INCH)
                                       for p in ext_poly_in]
        self.poly_overrides = overrides

        def _template_piece_wanted(r):
            meta = meta_all.get(str(r.id)) or {}
            # Pieces consumed by technique maths are cut from squares
            # (stitch-and-flip corners, batch HSTs/geese) - the cutting
            # instructions fully specify them, so a printed template of
            # the finished shape would never be used.
            if use_tech_math and meta.get("technique") in (
                    "stitch_flip", "hst2", "hst8", "fg4"):
                return False
            if not skip_squares:
                return True
            if meta.get("grain") == "fussy":
                return True  # fussy squares still need their template
            
            # Use overridden polygon if available!
            poly = self.poly_overrides.get(r.id)
            if poly is not None:
                poly_in = [(p[0]/core.PX_PER_INCH, p[1]/core.PX_PER_INCH) for p in poly]
                info = quilttools_cutplan.classify_piece(poly_in)
            else:
                info = quilttools_cutplan.classify_piece(r.polygon)
                
            if info["kind"] in ("square", "rect"):
                self._squares_skipped.append(r.label)
                return False
            return True

        if (self.options.export_type == "template"
                and getattr(self.options, "template_dedupe", "all") == "unique"):
            colors_by_id = quilttools_fpp_fabric.region_colors(block_data)
            shape_groups = {}
            for r in tree.leaf_regions():
                if _prefix_of(r.label) in self._fpp_prefixes:
                    match = re.match(r"^([A-Za-z]+)(\d+)$", r.label)
                    if match:
                        valid_sections.setdefault(
                            match.group(1).upper(), []).append(
                            (int(match.group(2)), r))
                    continue
                if not _template_piece_wanted(r):
                    continue
                poly = self.poly_overrides.get(r.id, r.polygon)
                key = quilttools_cutplan.congruence_key(poly, tol=1.0)
                shape_groups.setdefault(key, []).append(r)
            for grp in shape_groups.values():
                grp.sort(key=lambda rr: rr.label)
                rep = grp[0]
                valid_sections[rep.label] = [(1, rep)]
                if len(grp) > 1:
                    self._template_dedupe[rep.label] = [rr.label for rr in grp]
                if len({colors_by_id.get(rr.id) for rr in grp}) > 1:
                    self._template_multicolor.add(rep.label)
        else:
            for r in tree.leaf_regions():
                if self.options.export_type == "template":
                    if _prefix_of(r.label) in self._fpp_prefixes:
                        match = re.match(r"^([A-Za-z]+)(\d+)$", r.label)
                        if match:
                            valid_sections.setdefault(
                                match.group(1).upper(), []).append(
                                (int(match.group(2)), r))
                        continue
                    if not _template_piece_wanted(r):
                        continue
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
            if self.options.export_type == "template" and tree.leaf_regions():
                # Legitimate in template mode: every piece is cut from
                # technique squares / the cutting list (no printed
                # templates), e.g. an all-HST block. Continue with an
                # empty section list so instruction pages still render.
                return g, block_data, []
            inkex.errormsg("ERROR: Block has not been labeled. You must run 'Quilt Tools Block > 11. Labels & Guides > Fully Auto-Label' (or define sections manually) before exporting.")
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
                poly = self.poly_overrides.get(r.id, r.polygon)
                regions_scaled.append({
                    "label": r.label,
                    "id": r.id,
                    "polygon": [(pt[0] * scale, pt[1] * scale) for pt in poly]
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
        self._show_lint_report_gui(lint_report)

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
            if self.options.export_type == "template" and \
                    len(sec["regions"]) == 1:
                # Hybrid: multi-piece sections are FPP foundations - edge
                # lengths belong on single-piece templates only.
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
                canvas_label = r["label"]
                dd = getattr(self, "_template_dedupe", {}).get(r["label"])
                if dd:
                    canvas_label = f"{r['label']} - cut {len(dd)}"
                etree.SubElement(
                    sec_g,
                    "{%s}text" % core.SVG_NS,
                    x=f"{r_cx:.2f}",
                    y=f"{r_cy:.2f}",
                    style="font-size:14px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#000000;",
                ).text = canvas_label

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

        regions = block_data.tree.leaf_regions()
        user_colors = block_data.prefs.get("custom_colors", {})
        color_mode = block_data.prefs.get("color_mode", "piece")
        unique_colors = set()
        for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
            color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
            if not color_hex:
                color_hex = core.get_color_for_label(r.label, color_mode, idx)
            unique_colors.add(color_hex)
        self._deconflict_separate_section_map(block_data, unique_colors)

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

        self._show_lint_report_gui(lint_report)

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
                pass

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
            pw_pg, ph_pg = PAGE_SIZES.get(self.options.page_size, PAGE_SIZES["letter"])
            if self.options.orientation == "landscape":
                pw_pg, ph_pg = ph_pg, pw_pg
            pages_list.extend(self._fabric_pages_for_size(
                block_data, base_size, pw_pg, ph_pg,
                self.options.margin_in * core.PX_PER_INCH))

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
        self._show_lint_report_gui(lint_report)

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

        self._deconflict_separate_section_map(block_data, unique_colors)

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
                pages_list.extend(self._fabric_pages_for_size(
                    block_data, sz, pw, ph, margin))

            g_sz, _, sections = self._get_processed_sections(sz, allow_rotate=True)
            if sections is None:
                continue

            size_items = []
            global_tab_counter = 1

            if sz != base_size or bool(getattr(self.options, "include_pattern_test_square", False)):
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

            # HST sewing-line templates: one printable square per unique
            # 2-at-a-time HST size (draw two seams, cut on the diagonal).
            if (self.options.export_type == "template"
                    and getattr(self.options, "hst_templates", True)):
                req = self._template_req(block_data, sz)
                hst_sizes = set()
                for res in req["plan"]["fabrics"].values():
                    for op in res["ops"]:
                        if op["op"] != "strip":
                            continue
                        for sc in op["subcuts"]:
                            if sc.get("source") == "hst2":
                                hst_sizes.add(round(sc["w"], 3))
                for side_in in sorted(hst_sizes):
                    side_px = side_in * core.PX_PER_INCH
                    if side_px > min(avail_w, avail_h):
                        continue
                    size_items.append({
                        "prefix": "HST",
                        "part_str": "",
                        "T_w": side_px,
                        "T_h": side_px,
                        "core_w": side_px,
                        "core_h": side_px,
                        "pad_l": 0, "pad_r": 0, "pad_t": 0, "pad_b": 0,
                        "inner_transform": "",
                        "right_glue": None, "left_align": None,
                        "bottom_glue": None, "top_align": None,
                        "sa_poly": [],
                        "regions": [],
                        "hst_size_in": side_in,
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
                if item["prefix"] in ("CAL", "HST"):
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
        

        pass

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

        return max(curr_y, curr_y_key + 35)

    def _draw_color_key_grid(self, layout_layer, start_x, start_y, max_h, unique_colors, color_codes, all_colors, num_cols=4):
        for idx, c_hex in enumerate(unique_colors):
            col = idx % num_cols
            row = idx // num_cols
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
            
            suggested = est.get("suggested_purchase")
            if not suggested:
                free_yd = est['free_in'] / 36.0
                eighths = math.ceil(free_yd * 8.0)
                suggested = f"{eighths/8.0:.3f} yd ({eighths}/8 yd)"

            precut_name = est.get("precut_name")
            if precut_name:
                free_str = f"{est['free_in']:.1f}\" x {est['fq_free_in']:.1f}\" width"
            else:
                free_yd = est['free_in'] / 36.0
                free_str = f"{est['free_in']:.1f}\" ({free_yd:.2f} yd)"

            etree.SubElement(
                layout_layer,
                "{%s}text" % core.SVG_NS,
                x=str(table_x + 350),
                y=str(row_y),
                style=f"font-size:10px;font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
            ).text = free_str
            
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

    def _cutplan_options(self):
        return {
            "wof_in": self.options.wof_in,
            "sa_in": self.options.sa_in,
            "oversize_batch": bool(self.options.oversize_batch),
            "use_techniques": self.options.cutting_math != "templates_only",
            "use_precuts": bool(self.options.use_precuts),
            "precut_mini_charm": bool(self.options.precut_mini_charm),
            "precut_charm": bool(self.options.precut_charm),
            "precut_layer_cake": bool(self.options.precut_layer_cake),
            "precut_jelly_roll": bool(self.options.precut_jelly_roll),
            "precut_fat_16th": bool(self.options.precut_fat_16th),
            "precut_fat_8th": bool(self.options.precut_fat_8th),
            "precut_fat_quarter": bool(self.options.precut_fat_quarter),
        }

    def _template_req(self, block_data, sz):
        """calculate_template_requirements, cached per size (used for page
        planning, rendering AND the HST template sizes)."""
        cache = getattr(self, "_tpl_req_cache", None)
        if cache is None:
            cache = self._tpl_req_cache = {}
        key = round(float(sz), 4)
        if key not in cache:
            fpp_prefixes = {str(p).upper() for p in
                            (block_data.prefs.get("fpp_sections") or [])}
            cache[key] = quilttools_fpp_fabric.calculate_template_requirements(
                block_data, sz, self._cutplan_options(),
                fpp_prefixes=fpp_prefixes)
        return cache[key]

    @staticmethod
    def _wrap_text(text, width=110):
        words = text.split(" ")
        lines, cur = [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > width:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
        return lines

    def _cutting_plan_rows(self, block_data, sz):
        """Flatten the cutting instructions into styled rows so they can be
        split across as many pages as needed. Cached per size so the page
        planning pass and every chunk render agree on row boundaries."""
        cache = getattr(self, "_plan_rows_cache", None)
        if cache is None:
            cache = self._plan_rows_cache = {}
        key = round(float(sz), 4)
        if key in cache:
            return cache[key]

        colors_map = quilttools_fpp_fabric.region_colors(block_data)
        color_codes = core.assign_color_codes(
            sorted(set(colors_map.values())),
            block_data.prefs.get("color_code_overrides", ""))
        req = self._template_req(block_data, sz)
        plan = req["plan"]
        rows = []

        def add(kind, text, indent=0.0, fab=None, wrap=True):
            for k, ln in enumerate(self._wrap_text(text)
                                   if wrap else [text]):
                rows.append({"kind": kind, "text": ln, "indent": indent,
                             "fab": fab if k == 0 else None})

        if self.options.cutting_math == "templates_only":
            add("warn", "Cutting math: TEMPLATES ONLY - technique tags "
                "(stitch-and-flip, batch HSTs, flying geese) are ignored "
                "for this export.")
        if req.get("fpp_prefixes"):
            add("note", "Sections %s are delivered as FPP FOUNDATIONS - "
                "their rough-cut estimates include 3/4\" padding and are "
                "included in each fabric's total below."
                % ", ".join(sorted(req["fpp_prefixes"])))
        if getattr(self.options, "squares_cutting_list_only", False):
            add("note", "Square/rectangle pieces are listed below but not "
                "printed as templates (cut them straight from these "
                "measurements).")
        if self.options.cutting_math != "templates_only" and \
                hasattr(block_data, "piece_meta") and any(
                    (m or {}).get("technique") in
                    ("stitch_flip", "hst2", "hst8", "fg4")
                    for m in block_data.piece_meta().values()):
            add("note", "Pieces cut via technique squares (stitch-and-flip "
                "corners, batch HSTs, flying geese) are fully specified "
                "below and are not printed as shape templates.")
        for note in plan.get("notes", []):
            add("note", note)
        for warn in plan.get("warnings", []):
            add("warn", "! " + warn)
        rows.append({"kind": "gap", "text": "", "indent": 0, "fab": None})

        for fab_est in req["per_fabric"]:
            fab = fab_est["color"]
            code = color_codes.get(fab, "FAB")
            suggested = fab_est.get("suggested_purchase")
            if not suggested:
                suggested = quilttools_fpp_fabric.suggest_purchase(
                    fab_est["total_in"], fab_est["fq_total_in"])
            
            wof_val = fab_est.get("wof_in", 40.0)
            precut_name = fab_est.get("precut_name")
            if precut_name:
                clean_name = precut_name.replace("1 x ", "")
                width_label = f"{clean_name} width ({quilttools_cutplan.fmt_in(wof_val)})"
            elif abs(wof_val - 21.0) < 1e-3:
                width_label = "FQ width (21\")"
            else:
                width_label = "WOF"

            n_pc = fab_est["pieces_count"] + fab_est.get("fpp_pieces", 0)
            add("header",
                f"        Fabric {code} ({fab}) - {n_pc} piece"
                f"{'s' if n_pc != 1 else ''} - total "
                f"{quilttools_cutplan.fmt_in(fab_est['total_in'])} x {width_label} - "
                f"suggested: {suggested}", fab=fab)
            for line in fab_est["lines"]:
                add("line", line, indent=14.0)
            if fab_est.get("fpp_in"):
                add("line", "FPP foundation sections: allow "
                    f"{quilttools_cutplan.fmt_in(fab_est['fpp_in'])} x WOF "
                    f"({fab_est['fpp_pieces']} rough-cut piece"
                    f"{'s' if fab_est['fpp_pieces'] != 1 else ''}, "
                    "3/4\" padding included).", indent=14.0)
            for note in fab_est["notes"]:
                add("note", note, indent=14.0)
            for warn in fab_est["warnings"]:
                add("warn", "! " + warn, indent=14.0)
            rows.append({"kind": "gap", "text": "", "indent": 0,
                         "fab": None})
        cache[key] = rows
        return rows

    def _fabric_pages_for_size(self, block_data, sz, pw, ph, margin):
        """Page descriptors for one size's fabric requirements - template
        mode paginates the row stream instead of truncating, and the
        optional cutting layout map gets its own paginated page(s)."""
        if self.options.export_type != "template":
            return [{"type": "fabric_requirements", "size": sz}]
        rows = self._cutting_plan_rows(block_data, sz)
        rows_pp = max(18, int((ph - 2 * margin - 130) / 13.0))
        n = max(1, math.ceil(len(rows) / rows_pp)) if rows else 1
        pages = [{"type": "fabric_requirements", "size": sz, "chunk": k,
                  "nchunks": n, "rows_pp": rows_pp} for k in range(n)]

        if self.options.visualize_fabric_layout:
            req = self._template_req(block_data, sz)
            map_w = (pw - 2 * margin) * (self.options.wof_draw_scale_pct / 100.0)
            heights = quilttools_fpp_fabric.estimate_map_heights(
                req["plan"], self.options.wof_in, map_w)
            # Simple blocks: tuck the whole map under the last page of
            # instructions when it fits in the leftover space; only spill
            # onto dedicated map page(s) when it genuinely cannot fit.
            rows_last = len(rows) - (n - 1) * rows_pp
            remaining = (ph - 2 * margin - 130) - rows_last * 13.0 - 30.0
            total_map_h = sum(heights.values())
            if heights and total_map_h <= remaining:
                pages[-1]["map_inline"] = True
                pages[-1]["map_w"] = map_w
            elif heights:
                avail = ph - 2 * margin - 140
                groups, cur, cur_h = [], [], 0.0
                for fab, h in heights.items():
                    if cur and cur_h + h > avail:
                        groups.append(cur)
                        cur, cur_h = [], 0.0
                    cur.append(fab)
                    cur_h += h
                if cur:
                    groups.append(cur)
                for k, fabs in enumerate(groups):
                    pages.append({"type": "cutting_map", "size": sz,
                                  "fabrics": fabs, "chunk": k,
                                  "nchunks": len(groups), "map_w": map_w})
        return pages

    def _render_cutting_plan_page(self, layout_layer, px, py, pw, ph, margin,
                                  avail_w, block_data, sz, color_codes,
                                  chunk=0, nchunks=1, rows_pp=None,
                                  map_inline=False, map_w=None):
        """Template-mode fabric page: one chunk of the cutting-instruction
        rows, plus the layout map after the final chunk."""
        req = self._template_req(block_data, sz)
        rows = self._cutting_plan_rows(block_data, sz)
        if rows_pp is None:
            rows_pp = max(18, int((ph - 2 * margin - 130) / 13.0))
        page_rows = rows[chunk * rows_pp:(chunk + 1) * rows_pp]

        styles = {
            "line": f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_dark']};",
            "note": f"font-size:{STYLE_CONFIG['font_size_tiny']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
            "warn": f"font-size:{STYLE_CONFIG['font_size_tiny']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_warn']};",
            "header": f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
        }
        y = py + margin + 100
        max_y = py + ph - margin - 20
        for row in page_rows:
            if row["kind"] == "gap":
                y += 6
                continue
            if row["fab"]:
                etree.SubElement(
                    layout_layer, "{%s}rect" % core.SVG_NS,
                    x=str(px + margin), y=str(y - 9), width="26",
                    height="11",
                    style=f"fill:{row['fab']};stroke:#999999;stroke-width:0.5;",
                )
            etree.SubElement(
                layout_layer, "{%s}text" % core.SVG_NS,
                x=str(px + margin + row["indent"]), y=str(y),
                style=styles.get(row["kind"], styles["line"]),
            ).text = row["text"]
            y += 13.0

        # Simple blocks: the map fits under the instructions and rides on
        # this page; otherwise it lives on dedicated "cutting_map" pages.
        if map_inline and chunk == nchunks - 1:
            y += 14
            quilttools_fpp_fabric.draw_cutting_plan_map(
                layout_layer, px + margin, y,
                map_w or (avail_w * (self.options.wof_draw_scale_pct / 100.0)), req["plan"],
                self.options.wof_in, color_codes,
                max_height=max_y - y)
        return y

    def _draw_alignment_ticks(self, container, r, scale, cx_hull, cx, cy, best_angle, alignment_marks, block_data, mirror_templates):
        orig_r = block_data.tree.regions.get(str(r["id"])) or block_data.tree.regions.get(r["id"])
        if orig_r and alignment_marks:
            poly = self.poly_overrides.get(r["id"], self.poly_overrides.get(str(r["id"]), orig_r.polygon))
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
            if bool(getattr(self.options, "show_page_boundaries", True)):
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
                
                if not self.options.separate_section_alignment_image:
                    preview_side = min(int(avail_w * 0.90), int(avail_h * 0.42))
                else:
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
                
                max_y = preview_y + preview_h
                if not self.options.separate_section_alignment_image:
                    max_y = self._draw_assembly_and_legend(
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
                        grid_y = max_y + 20
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
                
                # Center the preview map at the top of Page 2
                preview_side = min(int(avail_w * 0.90), int(avail_h * 0.42))
                preview_w = preview_side
                preview_h = preview_side
                preview_x = px + margin + (avail_w - preview_w) / 2
                preview_y = py + margin + 80
                
                self._draw_section_map_block(
                    layout_layer,
                    preview_x,
                    preview_y,
                    preview_w,
                    preview_h,
                    block_data,
                    user_colors,
                )
                
                # Draw assembly sequence and legend side-by-side underneath the map
                right_col_x = px + margin + avail_w / 2 + 10
                max_y = self._draw_assembly_and_legend(
                    layout_layer,
                    px + margin,
                    preview_y + preview_h + 20,
                    block_data,
                    side_by_side=True,
                    right_col_x=right_col_x
                )
                
                # Draw color key below the assembly / legend block
                if len(unique_colors) > 10:
                    grid_y = max_y + 20
                    self._draw_color_key_grid(
                        layout_layer,
                        px + margin,
                        grid_y,
                        avail_h - (grid_y - py),
                        unique_colors,
                        color_codes,
                        all_colors,
                        num_cols=4
                    )
                
            elif p_type == "fabric_requirements":
                sz = page_info["size"]
                is_template_mode = self.options.export_type == "template"
                chunk = page_info.get("chunk", 0)
                nchunks = page_info.get("nchunks", 1)
                cont = (f" - page {chunk + 1} of {nchunks}"
                        if nchunks > 1 else "")
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 30),
                    style=f"font-size:{STYLE_CONFIG['font_size_subtitle']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
                ).text = (f"Cutting Instructions ({sz:.1f}\" Block){cont}"
                          if is_template_mode
                          else f"Fabric Requirements ({sz:.1f}\" Block)")
                if is_template_mode:
                    subtitle = (f"Exact template shapes ({self.options.sa_in:.2f}\" seam allowance included), "
                                f"planned on {self.options.wof_in:.1f}\" usable Width of Fabric (WOF).")
                else:
                    subtitle = f"Estimates based on {self.options.wof_in:.1f}\" usable Width of Fabric (WOF) and include 3/4\" padding around each piece."
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 55),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
                ).text = subtitle

                if int(self.options.template_copies) > 1 and chunk == 0:
                    etree.SubElement(
                        layout_layer,
                        "{%s}text" % core.SVG_NS,
                        x=str(px + margin),
                        y=str(py + margin + 75),
                        style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_mid']};",
                    ).text = f"Note: quantities below are for ONE block. This document contains {int(self.options.template_copies)} template sets."

                if is_template_mode:
                    self._render_cutting_plan_page(
                        layout_layer, px, py, pw, ph, margin, avail_w,
                        block_data, sz, color_codes,
                        chunk=chunk, nchunks=nchunks,
                        rows_pp=page_info.get("rows_pp"),
                        map_inline=page_info.get("map_inline", False),
                        map_w=page_info.get("map_w"))
                else:
                    fabric_estimates = quilttools_fpp_fabric.calculate_fabric_requirements(
                        block_data, sz, self.options.wof_in, options=self._cutplan_options())
                    end_table_y = self._render_fabric_table(layout_layer, px, py, pw, margin, fabric_estimates, color_codes)

                    if self.options.visualize_fabric_layout:
                        quilttools_fpp_fabric.draw_fabric_layout_map(
                            layout_layer, px + margin, end_table_y + 30, avail_w,
                            block_data, sz, self.options.wof_in, color_codes,
                            options=self._cutplan_options()
                        )

            elif p_type == "cutting_map":
                sz = page_info["size"]
                chunk = page_info.get("chunk", 0)
                nchunks = page_info.get("nchunks", 1)
                cont = (f" - page {chunk + 1} of {nchunks}"
                        if nchunks > 1 else "")
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 30),
                    style=f"font-size:{STYLE_CONFIG['font_size_subtitle']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;fill:{STYLE_CONFIG['color_dark']};",
                ).text = f"Cutting Layout Map ({sz:.1f}\" Block){cont}"
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(px + margin),
                    y=str(py + margin + 55),
                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};fill:{STYLE_CONFIG['color_mid']};",
                ).text = (f"Each bar is a WOF strip ({self.options.wof_in:.1f}\" usable width); "
                          "shapes show the subcuts at scale.")
                req = self._template_req(block_data, sz)
                quilttools_fpp_fabric.draw_cutting_plan_map(
                    layout_layer, px + margin, py + margin + 90,
                    page_info.get("map_w", avail_w * (self.options.wof_draw_scale_pct / 100.0)), req["plan"],
                    self.options.wof_in, color_codes,
                    max_height=ph - 2 * margin - 120,
                    fabrics=set(page_info.get("fabrics") or []))

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

            if item["prefix"] == "HST":
                s_px = item["T_w"]
                hx = page_offset_x + margin + item["page_x"]
                hy = page_offset_y + margin + header_gap + item["page_y"]
                hst_g = etree.SubElement(
                    layout_layer, "{%s}g" % core.SVG_NS,
                    id=f"hst-template-{item['target_page']}-{i}")
                etree.SubElement(
                    hst_g, "{%s}rect" % core.SVG_NS,
                    x=str(hx), y=str(hy), width=str(s_px), height=str(s_px),
                    style=f"fill:none;stroke:{STYLE_CONFIG['color_black']};stroke-width:1.5;",
                )
                # Solid diagonal = cut line; dashed lines 1/4" either side
                # = the two seams (sew first, then cut apart).
                etree.SubElement(
                    hst_g, "{%s}line" % core.SVG_NS,
                    x1=str(hx), y1=str(hy + s_px), x2=str(hx + s_px),
                    y2=str(hy),
                    style=f"stroke:{STYLE_CONFIG['color_black']};stroke-width:1.2;",
                )
                off = 0.25 * core.PX_PER_INCH * math.sqrt(2.0)
                for sgn in (-1.0, 1.0):
                    c = sgn * off
                    # anti-diagonal: local x + y = s; sew lines are the
                    # parallels x + y = s + c, clipped to the square.
                    pts = []
                    for lx in (0.0, s_px):
                        ly = s_px + c - lx
                        if 0.0 <= ly <= s_px:
                            pts.append((lx, ly))
                    for ly in (0.0, s_px):
                        lx = s_px + c - ly
                        if 0.0 < lx < s_px:
                            pts.append((lx, ly))
                    if len(pts) >= 2:
                        etree.SubElement(
                            hst_g, "{%s}line" % core.SVG_NS,
                            x1=str(hx + pts[0][0]), y1=str(hy + pts[0][1]),
                            x2=str(hx + pts[1][0]), y2=str(hy + pts[1][1]),
                            style=f"stroke:{STYLE_CONFIG['color_mid']};stroke-width:1.0;stroke-dasharray:5,4;",
                        )
                size_txt = quilttools_cutplan.fmt_in(item["hst_size_in"])
                etree.SubElement(
                    hst_g, "{%s}text" % core.SVG_NS,
                    x=str(hx + s_px * 0.28), y=str(hy + s_px * 0.22),
                    style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;fill:{STYLE_CONFIG['color_black']};",
                ).text = f"HST {size_txt}"
                for k, txt in enumerate((
                        "Layer 2 squares right sides together,",
                        "sew on the dashed lines,",
                        "cut apart on the solid diagonal.")):
                    etree.SubElement(
                        hst_g, "{%s}text" % core.SVG_NS,
                        x=str(hx + s_px * 0.68),
                        y=str(hy + s_px * 0.70 + k * 14.0),
                        style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};text-anchor:middle;fill:{STYLE_CONFIG['color_dark']};",
                    ).text = txt
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
            if self.options.export_type == "template" and \
                    len(item["regions"]) == 1:
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
                is_too_small = (pw_r < 60.0 or ph_r < 60.0 or area_r < 7200.0)
                
                mode = self.options.template_color_mode
                is_multicolor = r["label"] in getattr(
                    self, "_template_multicolor", set())
                if is_multicolor:
                    # Combined template covering several fabrics: print it
                    # uncoloured - fabric placement is on the layout page.
                    mode = "none"
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
                dedupe_labels = getattr(self, "_template_dedupe", {}).get(r["label"])
                if dedupe_labels:
                    label_text = f"{r['label']} - cut {len(dedupe_labels)}"
                code_text = "" if is_multicolor \
                    else color_codes.get(assigned_col, "")
                
                # Determine text colors based on contrast
                text_color = STYLE_CONFIG["color_black"]
                subtext_color = STYLE_CONFIG["color_mid"]
                if fill_col != STYLE_CONFIG["color_white"] and is_color_dark(fill_col):
                    text_color = STYLE_CONFIG["color_white"]
                    subtext_color = "#dddddd"

                is_wide_and_short = (pw_r > 1.8 * ph_r)
                
                if is_wide_and_short:
                    elements = []
                    
                    # 1. Label
                    elements.append({
                        "kind": "label",
                        "width": 35.0 if not is_too_small else 25.0
                    })
                    
                    # 2. Swatch
                    show_swatch = (mode == "tag" and not is_too_small)
                    sw_w = 36.0 if not is_too_small else 24.0
                    sw_h = 24.0 if not is_too_small else 16.0
                    if show_swatch:
                        elements.append({
                            "kind": "swatch",
                            "width": sw_w
                        })
                        
                    # 3. Code
                    if code_text:
                        elements.append({
                            "kind": "code",
                            "width": 45.0 if not is_too_small else 30.0
                        })
                        
                    # 4. Dedupe
                    show_dedupe = bool(dedupe_labels and not is_too_small)
                    if show_dedupe:
                        elements.append({
                            "kind": "dedupe",
                            "width": 60.0
                        })
                        
                    # 5. Multicolor note
                    if is_multicolor and not is_too_small:
                        elements.append({
                            "kind": "multicolor",
                            "width": 120.0
                        })

                    gap = 8.0
                    total_w = sum(el["width"] for el in elements) + gap * (len(elements) - 1)
                    curr_x = r_cx - total_w / 2.0
                    
                    for el in elements:
                        el_w = el["width"]
                        cx = curr_x + el_w / 2.0
                        
                        if el["kind"] == "label":
                            font_sz = "18px" if not is_too_small else STYLE_CONFIG['font_size_body']
                            etree.SubElement(
                                shift_g,
                                "{%s}text" % core.SVG_NS,
                                x=f"{cx:.2f}",
                                y=f"{r_cy:.2f}",
                                style=f"font-size:{font_sz};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{text_color};",
                            ).text = label_text
                        elif el["kind"] == "swatch":
                            etree.SubElement(
                                shift_g,
                                "{%s}rect" % core.SVG_NS,
                                x=f"{cx - sw_w / 2.0:.2f}",
                                y=f"{r_cy - sw_h / 2.0:.2f}",
                                width=str(sw_w),
                                height=str(sw_h),
                                style=f"fill:{assigned_col};stroke:{STYLE_CONFIG['template_border_stroke']};stroke-width:0.5;",
                            )
                        elif el["kind"] == "code":
                            font_sz = "15px" if not is_too_small else STYLE_CONFIG['font_size_tiny']
                            etree.SubElement(
                                shift_g,
                                "{%s}text" % core.SVG_NS,
                                x=f"{cx:.2f}",
                                y=f"{r_cy:.2f}",
                                style=f"font-size:{font_sz};font-family:{STYLE_CONFIG['font_family']};font-weight:normal;text-anchor:middle;dominant-baseline:middle;fill:{subtext_color};",
                            ).text = f"[{code_text}]"
                        elif el["kind"] == "dedupe":
                            covered = ", ".join(dedupe_labels)
                            if len(covered) > 30:
                                covered = covered[:27] + "..."
                            etree.SubElement(
                                shift_g,
                                "{%s}text" % core.SVG_NS,
                                x=f"{cx:.2f}",
                                y=f"{r_cy:.2f}",
                                style=f"font-size:13.5px;font-family:{STYLE_CONFIG['font_family']};font-weight:normal;text-anchor:middle;dominant-baseline:middle;fill:{subtext_color};",
                            ).text = f"for: {covered}"
                        elif el["kind"] == "multicolor":
                            etree.SubElement(
                                shift_g,
                                "{%s}text" % core.SVG_NS,
                                x=f"{cx:.2f}",
                                y=f"{r_cy:.2f}",
                                style=f"font-size:13.5px;font-family:{STYLE_CONFIG['font_family']};font-style:italic;text-anchor:middle;dominant-baseline:middle;fill:{subtext_color};",
                            ).text = "mixed fabrics - see layout page"
                            
                        curr_x += el_w + gap
                else:
                    if mode == "tag" and not is_too_small:
                        # Big pieces: swatch scaled up 50% to 36x24, labels scaled up 50%
                        etree.SubElement(
                            shift_g,
                            "{%s}text" % core.SVG_NS,
                            x=f"{r_cx:.2f}",
                            y=f"{r_cy - 22:.2f}",
                            style=f"font-size:18px;font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{text_color};",
                        ).text = label_text
                        etree.SubElement(
                            shift_g,
                            "{%s}rect" % core.SVG_NS,
                            x=f"{r_cx - 18:.2f}",
                            y=f"{r_cy - 8:.2f}",
                            width="36",
                            height="24",
                            style=f"fill:{assigned_col};stroke:{STYLE_CONFIG['template_border_stroke']};stroke-width:0.5;",
                        )
                        if code_text:
                            etree.SubElement(
                                shift_g,
                                "{%s}text" % core.SVG_NS,
                                x=f"{r_cx:.2f}",
                                y=f"{r_cy + 36:.2f}",
                                style=f"font-size:15px;font-family:{STYLE_CONFIG['font_family']};font-weight:normal;text-anchor:middle;fill:{subtext_color};",
                            ).text = f"[{code_text}]"
                    else:
                        if code_text:
                            if is_too_small:
                                # Stacked layout with body/tiny fonts for small pieces
                                etree.SubElement(
                                    shift_g,
                                    "{%s}text" % core.SVG_NS,
                                    x=f"{r_cx:.2f}",
                                    y=f"{r_cy - 5:.2f}",
                                    style=f"font-size:{STYLE_CONFIG['font_size_body']};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;fill:{text_color};",
                                ).text = label_text
                                etree.SubElement(
                                    shift_g,
                                    "{%s}text" % core.SVG_NS,
                                    x=f"{r_cx:.2f}",
                                    y=f"{r_cy + 5:.2f}",
                                    style=f"font-size:{STYLE_CONFIG['font_size_tiny']};font-family:{STYLE_CONFIG['font_family']};font-weight:normal;text-anchor:middle;fill:{subtext_color};",
                                ).text = f"[{code_text}]"
                            else:
                                # Standard layout with body/caption fonts scaled up 50% for big pieces
                                etree.SubElement(
                                    shift_g,
                                    "{%s}text" % core.SVG_NS,
                                    x=f"{r_cx:.2f}",
                                    y=f"{r_cy - 10:.2f}",
                                    style=f"font-size:18px;font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;fill:{text_color};",
                                ).text = label_text
                                etree.SubElement(
                                    shift_g,
                                    "{%s}text" % core.SVG_NS,
                                    x=f"{r_cx:.2f}",
                                    y=f"{r_cy + 10:.2f}",
                                    style=f"font-size:15px;font-family:{STYLE_CONFIG['font_family']};font-weight:normal;text-anchor:middle;fill:{subtext_color};",
                                ).text = f"[{code_text}]"
                        else:
                            # Centered single label (scaled up 50% to 18px on big pieces)
                            font_sz = STYLE_CONFIG['font_size_body'] if is_too_small else "18px"
                            etree.SubElement(
                                shift_g,
                                "{%s}text" % core.SVG_NS,
                                x=f"{r_cx:.2f}",
                                y=f"{r_cy:.2f}",
                                style=f"font-size:{font_sz};font-family:{STYLE_CONFIG['font_family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{text_color};",
                            ).text = label_text

                    if dedupe_labels and not is_too_small:
                        covered = ", ".join(dedupe_labels)
                        if len(covered) > 30:
                            covered = covered[:27] + "..."
                        
                        y_off = r_cy + 52.0 if (mode == "tag" and code_text) else (r_cy + 22.0 if code_text else r_cy + 14.0)
                        etree.SubElement(
                            shift_g,
                            "{%s}text" % core.SVG_NS,
                            x=f"{r_cx:.2f}",
                            y=f"{y_off:.2f}",
                            style=f"font-size:13.5px;font-family:{STYLE_CONFIG['font_family']};font-weight:normal;text-anchor:middle;fill:{subtext_color};",
                        ).text = f"for: {covered}"
                    if is_multicolor and not is_too_small:
                        y_off = r_cy + 64.0 if (mode == "tag" and code_text) else (r_cy + 34.0 if code_text else r_cy + 26.0)
                        etree.SubElement(
                            shift_g,
                            "{%s}text" % core.SVG_NS,
                            x=f"{r_cx:.2f}",
                            y=f"{y_off:.2f}",
                            style=f"font-size:13.5px;font-family:{STYLE_CONFIG['font_family']};font-style:italic;text-anchor:middle;fill:{subtext_color};",
                        ).text = "mixed fabrics - see layout page"

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

        # Combined multi-fabric templates: flag the affected pages and point
        # the user at the layout page for fabric placement.
        multi_set = getattr(self, "_template_multicolor", set())
        if multi_set:
            multi_pages = sorted({
                item["target_page"] for item in packable_items
                if item.get("prefix") in multi_set
                and item.get("target_page") in page_offsets})
            for tp in multi_pages:
                ox, oy = page_offsets[tp]
                etree.SubElement(
                    layout_layer,
                    "{%s}text" % core.SVG_NS,
                    x=str(ox + margin),
                    y=str(oy + margin + 14),
                    style=f"font-size:{STYLE_CONFIG['font_size_caption']};font-family:{STYLE_CONFIG['font_family']};font-style:italic;fill:{STYLE_CONFIG['color_mid']};",
                ).text = ("Templates marked 'mixed fabrics' are shared across "
                          "several fabrics and print uncoloured - use the "
                          "layout/preview page for fabric placement.")
            hint = ""
            if not self.options.separate_section_alignment_image:
                hint = (" Tip: enable 'Include Section Map Page (Page 2)' "
                        "for a printable fabric layout.")
            inkex.utils.debug(
                f"{len(multi_set)} combined template(s) cover more than one "
                "fabric and are printed uncoloured. Print the layout page to "
                "see which fabric each piece uses." + hint)

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
