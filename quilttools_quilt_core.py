import json
from lxml import etree
import quilttools_fpp_core as core

QUILT_DATA_TAG_ID = "quilt-data-quilttools"

class QuiltData:
    def __init__(self, spec=None):
        if spec is None:
            spec = {}
        self.name = spec.get("name", "My Quilt")
        self.finished_width_in = spec.get("finished_width_in", 0.0)
        self.finished_height_in = spec.get("finished_height_in", 0.0)
        self.units = spec.get("units", "in")
        self.setting = spec.get("setting", "straight")
        self.grid = spec.get("grid", {"rows": 1, "cols": 1, "cell_w_in": 12.0, "cell_h_in": 12.0})
        self.sashing = spec.get("sashing", {"width_in": 0.0, "cornerstones": False, "color_ref": ""})
        self.borders = spec.get("borders", [])
        self.binding = spec.get("binding", {"width_in": 0.25, "color_ref": ""})
        self.colours = spec.get("colours", {})
        self.cells = spec.get("cells", {})

    def to_json(self):
        return json.dumps({
            "name": self.name,
            "finished_width_in": self.finished_width_in,
            "finished_height_in": self.finished_height_in,
            "units": self.units,
            "setting": self.setting,
            "grid": self.grid,
            "sashing": self.sashing,
            "borders": self.borders,
            "binding": self.binding,
            "colours": self.colours,
            "cells": self.cells
        }, indent=2)

    @staticmethod
    def from_json(text):
        data = json.loads(text)
        return QuiltData(data)

def find_quilt_group(svg):
    for g in svg.findall(f".//{{{core.SVG_NS}}}g"):
        desc = g.find(f"{{{core.SVG_NS}}}desc[@id='{QUILT_DATA_TAG_ID}']")
        if desc is not None and desc.text:
            return g, QuiltData.from_json(desc.text)
    return None, None

def build_quilt_layer(quilt_data, theme):
    # Colors from theme
    stroke_color = theme.colour("diagram_stroke") or "#333333"
    fill_bg = theme.colour("background") or "#ffffff"
    fill_muted = theme.colour("muted") or "#f5f5f5"
    fill_primary = theme.colour("primary") or "#a0c4ff"
    fill_accent = theme.colour("accent") or "#ffadad"
    
    g_main = etree.Element(
        "{%s}g" % core.SVG_NS,
        id="quilttools-quilt-layer",
        **{
            f"{{{core.INKSCAPE_NS}}}label": "Quilt Layout",
            f"{{{core.INKSCAPE_NS}}}groupmode": "layer",
            "style": "display:inline;"
        }
    )
    desc = etree.SubElement(g_main, "{%s}desc" % core.SVG_NS, id=QUILT_DATA_TAG_ID)
    
    # Calculate widths in pixels
    cell_w = quilt_data.grid["cell_w_in"] * core.PX_PER_INCH
    cell_h = quilt_data.grid["cell_h_in"] * core.PX_PER_INCH
    sashing_w = quilt_data.sashing["width_in"] * core.PX_PER_INCH
    
    rows = quilt_data.grid["rows"]
    cols = quilt_data.grid["cols"]
    
    # Build list of border widths in pixels
    border_widths = [b["width_in"] * core.PX_PER_INCH for b in quilt_data.borders]
    binding_w = quilt_data.binding["width_in"] * core.PX_PER_INCH
    
    total_border_w = sum(border_widths) + binding_w
    
    setting = quilt_data.setting
    
    if setting == "on-point":
        import math
        # Enforce cell_w as side length S
        S = cell_w
        D = (S + sashing_w) * math.sqrt(2)
        grid_w = cols * D
        grid_h = rows * D
    else:
        grid_w = cols * cell_w + (cols - 1) * sashing_w if cols > 0 else 0
        grid_h = rows * cell_h + (rows - 1) * sashing_w if rows > 0 else 0
    
    quilt_w = grid_w + 2 * total_border_w
    quilt_h = grid_h + 2 * total_border_w
    
    # Set dimensions in quilt_data
    quilt_data.finished_width_in = quilt_w / core.PX_PER_INCH
    quilt_data.finished_height_in = quilt_h / core.PX_PER_INCH
    desc.text = quilt_data.to_json()
    
    # Cell helper
    def add_cell(cell_id, role, state, poly, fill_col, label=""):
        # Save to cell registry in quilt_data
        quilt_data.cells[cell_id] = {
            "role": role,
            "state": state,
            "polygon": poly,
            "placed_block": None
        }
        
        g_cell = etree.SubElement(g_main, "{%s}g" % core.SVG_NS, id=cell_id, **{
            "data-quilt-role": role,
            "data-quilt-state": state
        })
        
        pts_str = " ".join(f"{pt[0]:.2f},{pt[1]:.2f}" for pt in poly)
        etree.SubElement(g_cell, "{%s}polygon" % core.SVG_NS, points=pts_str, style=f"fill:{fill_col};stroke:{stroke_color};stroke-width:1.0;stroke-linejoin:round;")
        
        if label:
            # Add text label in center of polygon
            xs = [pt[0] for pt in poly]
            ys = [pt[1] for pt in poly]
            cx = sum(xs) / len(poly)
            cy = sum(ys) / len(poly)
            etree.SubElement(
                g_cell,
                "{%s}text" % core.SVG_NS,
                x=str(cx),
                y=str(cy),
                style=f"font-size:12px;font-family:{theme.font('body')['family']};font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:{theme.colour('ink')};"
            ).text = label

    # 1. Blocks & Grid elements
    if setting == "on-point":
        import math
        S = cell_w
        D = (S + sashing_w) * math.sqrt(2)
        d_S = S * math.sqrt(2) / 2
        d_W = sashing_w * math.sqrt(2) / 2
        
        # 1.1 Blocks
        for r in range(rows):
            for c in range(cols):
                cx = total_border_w + (c + 0.5) * D
                cy = total_border_w + (r + 0.5) * D
                poly = [
                    (cx, cy - d_S), # Top
                    (cx + d_S, cy), # Right
                    (cx, cy + d_S), # Bottom
                    (cx - d_S, cy)  # Left
                ]
                add_cell(f"quilt-cell-{r}-{c}", "block", "empty", poly, fill_bg, f"{r+1}-{c+1}")
                
        # 1.2 Sashing & Cornerstones
        if sashing_w > 0:
            cos45 = math.sqrt(2) / 2
            sin45 = math.sqrt(2) / 2
            u_x, u_y = cos45, sin45
            v_x, v_y = -cos45, sin45
            
            seen_sash = set()
            
            for r in range(rows):
                for c in range(cols):
                    cx = total_border_w + (c + 0.5) * D
                    cy = total_border_w + (r + 0.5) * D
                    
                    # 4 Sashing strips around block (r, c)
                    # Top-Left (parallel to v)
                    p_tl = (cx - 0.25 * D, cy - 0.25 * D)
                    p_tl_key = (round(p_tl[0], 2), round(p_tl[1], 2))
                    if p_tl_key not in seen_sash:
                        seen_sash.add(p_tl_key)
                        poly = [
                            (p_tl[0] + 0.5 * S * v_x + 0.5 * sashing_w * u_x, p_tl[1] + 0.5 * S * v_y + 0.5 * sashing_w * u_y),
                            (p_tl[0] - 0.5 * S * v_x + 0.5 * sashing_w * u_x, p_tl[1] - 0.5 * S * v_y + 0.5 * sashing_w * u_y),
                            (p_tl[0] - 0.5 * S * v_x - 0.5 * sashing_w * u_x, p_tl[1] - 0.5 * S * v_y - 0.5 * sashing_w * u_y),
                            (p_tl[0] + 0.5 * S * v_x - 0.5 * sashing_w * u_x, p_tl[1] + 0.5 * S * v_y - 0.5 * sashing_w * u_y)
                        ]
                        add_cell(f"quilt-cell-sashing-v-{r}-{c}-tl", "sashing", "plain_fabric", poly, fill_muted)
                        
                    # Bottom-Right (parallel to v)
                    p_br = (cx + 0.25 * D, cy + 0.25 * D)
                    p_br_key = (round(p_br[0], 2), round(p_br[1], 2))
                    if p_br_key not in seen_sash:
                        seen_sash.add(p_br_key)
                        poly = [
                            (p_br[0] + 0.5 * S * v_x + 0.5 * sashing_w * u_x, p_br[1] + 0.5 * S * v_y + 0.5 * sashing_w * u_y),
                            (p_br[0] - 0.5 * S * v_x + 0.5 * sashing_w * u_x, p_br[1] - 0.5 * S * v_y + 0.5 * sashing_w * u_y),
                            (p_br[0] - 0.5 * S * v_x - 0.5 * sashing_w * u_x, p_br[1] - 0.5 * S * v_y - 0.5 * sashing_w * u_y),
                            (p_br[0] + 0.5 * S * v_x - 0.5 * sashing_w * u_x, p_br[1] + 0.5 * S * v_y - 0.5 * sashing_w * u_y)
                        ]
                        add_cell(f"quilt-cell-sashing-v-{r}-{c}-br", "sashing", "plain_fabric", poly, fill_muted)
                        
                    # Top-Right (parallel to u)
                    p_tr = (cx + 0.25 * D, cy - 0.25 * D)
                    p_tr_key = (round(p_tr[0], 2), round(p_tr[1], 2))
                    if p_tr_key not in seen_sash:
                        seen_sash.add(p_tr_key)
                        poly = [
                            (p_tr[0] + 0.5 * S * u_x + 0.5 * sashing_w * v_x, p_tr[1] + 0.5 * S * u_y + 0.5 * sashing_w * v_y),
                            (p_tr[0] - 0.5 * S * u_x + 0.5 * sashing_w * v_x, p_tr[1] - 0.5 * S * u_y + 0.5 * sashing_w * v_y),
                            (p_tr[0] - 0.5 * S * u_x - 0.5 * sashing_w * v_x, p_tr[1] - 0.5 * S * u_y - 0.5 * sashing_w * v_y),
                            (p_tr[0] + 0.5 * S * u_x - 0.5 * sashing_w * v_x, p_tr[1] + 0.5 * S * u_y - 0.5 * sashing_w * v_y)
                        ]
                        add_cell(f"quilt-cell-sashing-h-{r}-{c}-tr", "sashing", "plain_fabric", poly, fill_muted)
                        
                    # Bottom-Left (parallel to u)
                    p_bl = (cx - 0.25 * D, cy + 0.25 * D)
                    p_bl_key = (round(p_bl[0], 2), round(p_bl[1], 2))
                    if p_bl_key not in seen_sash:
                        seen_sash.add(p_bl_key)
                        poly = [
                            (p_bl[0] + 0.5 * S * u_x + 0.5 * sashing_w * v_x, p_bl[1] + 0.5 * S * u_y + 0.5 * sashing_w * v_y),
                            (p_bl[0] - 0.5 * S * u_x + 0.5 * sashing_w * v_x, p_bl[1] - 0.5 * S * u_y + 0.5 * sashing_w * v_y),
                            (p_bl[0] - 0.5 * S * u_x - 0.5 * sashing_w * v_x, p_bl[1] - 0.5 * S * u_y - 0.5 * sashing_w * v_y),
                            (p_bl[0] + 0.5 * S * u_x - 0.5 * sashing_w * v_x, p_bl[1] + 0.5 * S * u_y - 0.5 * sashing_w * v_y)
                        ]
                        add_cell(f"quilt-cell-sashing-h-{r}-{c}-bl", "sashing", "plain_fabric", poly, fill_muted)
            
            # Cornerstones
            # Type A:
            for c in range(cols + 1):
                for r in range(rows):
                    cx = total_border_w + c * D
                    cy = total_border_w + (r + 0.5) * D
                    poly = [
                        (cx, cy - d_W),
                        (cx + d_W, cy),
                        (cx, cy + d_W),
                        (cx - d_W, cy)
                    ]
                    add_cell(f"quilt-cell-cornerstone-a-{r}-{c}", "cornerstone", "plain_fabric", poly, fill_accent)
            # Type B:
            for c in range(cols):
                for r in range(rows + 1):
                    cx = total_border_w + (c + 0.5) * D
                    cy = total_border_w + r * D
                    poly = [
                        (cx, cy - d_W),
                        (cx + d_W, cy),
                        (cx, cy + d_W),
                        (cx - d_W, cy)
                    ]
                    add_cell(f"quilt-cell-cornerstone-b-{r}-{c}", "cornerstone", "plain_fabric", poly, fill_accent)

        # 1.3 Setting Triangles
        # Corner Setting Triangles (exactly 4)
        poly_tl = [
            (total_border_w, total_border_w),
            (total_border_w + 0.5 * D - d_W, total_border_w),
            (total_border_w, total_border_w + 0.5 * D - d_W)
        ]
        add_cell("quilt-cell-setting-corner-tl", "setting_triangle", "plain_fabric", poly_tl, fill_muted)
        
        poly_tr = [
            (total_border_w + grid_w, total_border_w),
            (total_border_w + grid_w - 0.5 * D + d_W, total_border_w),
            (total_border_w + grid_w, total_border_w + 0.5 * D - d_W)
        ]
        add_cell("quilt-cell-setting-corner-tr", "setting_triangle", "plain_fabric", poly_tr, fill_muted)
        
        poly_bl = [
            (total_border_w, total_border_w + grid_h),
            (total_border_w + 0.5 * D - d_W, total_border_w + grid_h),
            (total_border_w, total_border_w + grid_h - 0.5 * D + d_W)
        ]
        add_cell("quilt-cell-setting-corner-bl", "setting_triangle", "plain_fabric", poly_bl, fill_muted)
        
        poly_br = [
            (total_border_w + grid_w, total_border_w + grid_h),
            (total_border_w + grid_w - 0.5 * D + d_W, total_border_w + grid_h),
            (total_border_w + grid_w, total_border_w + grid_h - 0.5 * D + d_W)
        ]
        add_cell("quilt-cell-setting-corner-br", "setting_triangle", "plain_fabric", poly_br, fill_muted)

        # Side Setting Triangles
        # Top Edge (Y = total_border_w)
        for c in range(cols - 1):
            poly = [
                (total_border_w + (c + 0.5) * D + d_W, total_border_w),
                (total_border_w + (c + 1.5) * D - d_W, total_border_w),
                (total_border_w + (c + 1) * D, total_border_w + 0.5 * D - d_W)
            ]
            add_cell(f"quilt-cell-setting-top-{c}", "setting_triangle", "plain_fabric", poly, fill_muted)
            
        # Bottom Edge (Y = total_border_w + grid_h)
        for c in range(cols - 1):
            poly = [
                (total_border_w + (c + 0.5) * D + d_W, total_border_w + grid_h),
                (total_border_w + (c + 1.5) * D - d_W, total_border_w + grid_h),
                (total_border_w + (c + 1) * D, total_border_w + grid_h - 0.5 * D + d_W)
            ]
            add_cell(f"quilt-cell-setting-bottom-{c}", "setting_triangle", "plain_fabric", poly, fill_muted)
            
        # Left Edge (X = total_border_w)
        for r in range(rows - 1):
            poly = [
                (total_border_w, total_border_w + (r + 0.5) * D + d_W),
                (total_border_w, total_border_w + (r + 1.5) * D - d_W),
                (total_border_w + 0.5 * D - d_W, total_border_w + (r + 1) * D)
            ]
            add_cell(f"quilt-cell-setting-left-{r}", "setting_triangle", "plain_fabric", poly, fill_muted)
            
        # Right Edge (X = total_border_w + grid_w)
        for r in range(rows - 1):
            poly = [
                (total_border_w + grid_w, total_border_w + (r + 0.5) * D + d_W),
                (total_border_w + grid_w, total_border_w + (r + 1.5) * D - d_W),
                (total_border_w + grid_w - 0.5 * D + d_W, total_border_w + (r + 1) * D)
            ]
            add_cell(f"quilt-cell-setting-right-{r}", "setting_triangle", "plain_fabric", poly, fill_muted)

    else:
        # 1. Blocks (Straight Layout)
        for r in range(rows):
            for c in range(cols):
                x_start = total_border_w + c * (cell_w + sashing_w)
                y_start = total_border_w + r * (cell_h + sashing_w)
                poly = [
                    (x_start, y_start),
                    (x_start + cell_w, y_start),
                    (x_start + cell_w, y_start + cell_h),
                    (x_start, y_start + cell_h)
                ]
                add_cell(f"quilt-cell-{r}-{c}", "block", "empty", poly, fill_bg, f"{r+1}-{c+1}")
                
        # 2. Sashing & Cornerstones (Straight Layout)
        if sashing_w > 0:
            # Horizontal Sashing
            for r in range(rows - 1):
                for c in range(cols):
                    x_start = total_border_w + c * (cell_w + sashing_w)
                    y_start = total_border_w + r * (cell_h + sashing_w) + cell_h
                    poly = [
                        (x_start, y_start),
                        (x_start + cell_w, y_start),
                        (x_start + cell_w, y_start + sashing_w),
                        (x_start, y_start + sashing_w)
                    ]
                    add_cell(f"quilt-cell-sashing-h-{r}-{c}", "sashing", "plain_fabric", poly, fill_muted)
                    
            # Vertical Sashing
            for r in range(rows):
                for c in range(cols - 1):
                    x_start = total_border_w + c * (cell_w + sashing_w) + cell_w
                    y_start = total_border_w + r * (cell_h + sashing_w)
                    poly = [
                        (x_start, y_start),
                        (x_start + sashing_w, y_start),
                        (x_start + sashing_w, y_start + cell_h),
                        (x_start, y_start + cell_h)
                    ]
                    add_cell(f"quilt-cell-sashing-v-{r}-{c}", "sashing", "plain_fabric", poly, fill_muted)
                    
            # Cornerstones
            if quilt_data.sashing["cornerstones"]:
                for r in range(rows - 1):
                    for c in range(cols - 1):
                        x_start = total_border_w + c * (cell_w + sashing_w) + cell_w
                        y_start = total_border_w + r * (cell_h + sashing_w) + cell_h
                        poly = [
                            (x_start, y_start),
                            (x_start + sashing_w, y_start),
                            (x_start + sashing_w, y_start + sashing_w),
                            (x_start, y_start + sashing_w)
                        ]
                        add_cell(f"quilt-cell-cornerstone-{r}-{c}", "cornerstone", "plain_fabric", poly, fill_accent)

    # 3. Borders
    inner_left = total_border_w
    inner_right = total_border_w + grid_w
    inner_top = total_border_w
    inner_bottom = total_border_w + grid_h
    
    for i, b in enumerate(quilt_data.borders):
        b_w = b["width_in"] * core.PX_PER_INCH
        style = b.get("style", "long_h")
        layer = i + 1
        # Pick color alternately
        fill_col = fill_primary if i % 2 == 0 else fill_accent
        
        if style == "long_h":
            poly_top = [
                (inner_left - b_w, inner_top - b_w),
                (inner_right + b_w, inner_top - b_w),
                (inner_right + b_w, inner_top),
                (inner_left - b_w, inner_top)
            ]
            poly_bottom = [
                (inner_left - b_w, inner_bottom),
                (inner_right + b_w, inner_bottom),
                (inner_right + b_w, inner_bottom + b_w),
                (inner_left - b_w, inner_bottom + b_w)
            ]
            poly_left = [
                (inner_left - b_w, inner_top),
                (inner_left, inner_top),
                (inner_left, inner_bottom),
                (inner_left - b_w, inner_bottom)
            ]
            poly_right = [
                (inner_right, inner_top),
                (inner_right + b_w, inner_top),
                (inner_right + b_w, inner_bottom),
                (inner_right, inner_bottom)
            ]
            add_cell(f"quilt-cell-border-{layer}-top", "border", "plain_fabric", poly_top, fill_col)
            add_cell(f"quilt-cell-border-{layer}-bottom", "border", "plain_fabric", poly_bottom, fill_col)
            add_cell(f"quilt-cell-border-{layer}-left", "border", "plain_fabric", poly_left, fill_col)
            add_cell(f"quilt-cell-border-{layer}-right", "border", "plain_fabric", poly_right, fill_col)
            
        elif style == "long_v":
            poly_top = [
                (inner_left, inner_top - b_w),
                (inner_right, inner_top - b_w),
                (inner_right, inner_top),
                (inner_left, inner_top)
            ]
            poly_bottom = [
                (inner_left, inner_bottom),
                (inner_right, inner_bottom),
                (inner_right, inner_bottom + b_w),
                (inner_left, inner_bottom + b_w)
            ]
            poly_left = [
                (inner_left - b_w, inner_top - b_w),
                (inner_left, inner_top - b_w),
                (inner_left, inner_bottom + b_w),
                (inner_left - b_w, inner_bottom + b_w)
            ]
            poly_right = [
                (inner_right, inner_top - b_w),
                (inner_right + b_w, inner_top - b_w),
                (inner_right + b_w, inner_bottom + b_w),
                (inner_right, inner_bottom + b_w)
            ]
            add_cell(f"quilt-cell-border-{layer}-top", "border", "plain_fabric", poly_top, fill_col)
            add_cell(f"quilt-cell-border-{layer}-bottom", "border", "plain_fabric", poly_bottom, fill_col)
            add_cell(f"quilt-cell-border-{layer}-left", "border", "plain_fabric", poly_left, fill_col)
            add_cell(f"quilt-cell-border-{layer}-right", "border", "plain_fabric", poly_right, fill_col)
            
        elif style == "cornerstone":
            poly_top = [
                (inner_left, inner_top - b_w),
                (inner_right, inner_top - b_w),
                (inner_right, inner_top),
                (inner_left, inner_top)
            ]
            poly_bottom = [
                (inner_left, inner_bottom),
                (inner_right, inner_bottom),
                (inner_right, inner_bottom + b_w),
                (inner_left, inner_bottom + b_w)
            ]
            poly_left = [
                (inner_left - b_w, inner_top),
                (inner_left, inner_top),
                (inner_left, inner_bottom),
                (inner_left - b_w, inner_bottom)
            ]
            poly_right = [
                (inner_right, inner_top),
                (inner_right + b_w, inner_top),
                (inner_right + b_w, inner_bottom),
                (inner_right, inner_bottom)
            ]
            poly_tl = [
                (inner_left - b_w, inner_top - b_w),
                (inner_left, inner_top - b_w),
                (inner_left, inner_top),
                (inner_left - b_w, inner_top)
            ]
            poly_tr = [
                (inner_right, inner_top - b_w),
                (inner_right + b_w, inner_top - b_w),
                (inner_right + b_w, inner_top),
                (inner_right, inner_top)
            ]
            poly_bl = [
                (inner_left - b_w, inner_bottom),
                (inner_left, inner_bottom),
                (inner_left, inner_bottom + b_w),
                (inner_left - b_w, inner_bottom + b_w)
            ]
            poly_br = [
                (inner_right, inner_bottom),
                (inner_right + b_w, inner_bottom),
                (inner_right + b_w, inner_bottom + b_w),
                (inner_right, inner_bottom + b_w)
            ]
            add_cell(f"quilt-cell-border-{layer}-top", "border", "plain_fabric", poly_top, fill_col)
            add_cell(f"quilt-cell-border-{layer}-bottom", "border", "plain_fabric", poly_bottom, fill_col)
            add_cell(f"quilt-cell-border-{layer}-left", "border", "plain_fabric", poly_left, fill_col)
            add_cell(f"quilt-cell-border-{layer}-right", "border", "plain_fabric", poly_right, fill_col)
            add_cell(f"quilt-cell-border-{layer}-cornerstone-tl", "border", "plain_fabric", poly_tl, fill_accent)
            add_cell(f"quilt-cell-border-{layer}-cornerstone-tr", "border", "plain_fabric", poly_tr, fill_accent)
            add_cell(f"quilt-cell-border-{layer}-cornerstone-bl", "border", "plain_fabric", poly_bl, fill_accent)
            add_cell(f"quilt-cell-border-{layer}-cornerstone-br", "border", "plain_fabric", poly_br, fill_accent)
            
        inner_left -= b_w
        inner_right += b_w
        inner_top -= b_w
        inner_bottom += b_w
        
    # 4. Binding
    if binding_w > 0:
        fill_col = fill_primary
        # Top
        poly_top = [
            (inner_left - binding_w, inner_top - binding_w),
            (inner_right + binding_w, inner_top - binding_w),
            (inner_right + binding_w, inner_top),
            (inner_left - binding_w, inner_top)
        ]
        add_cell(f"quilt-cell-binding-top", "binding", "plain_fabric", poly_top, fill_col)
        
        # Bottom
        poly_bottom = [
            (inner_left - binding_w, inner_bottom),
            (inner_right + binding_w, inner_bottom),
            (inner_right + binding_w, inner_bottom + binding_w),
            (inner_left - binding_w, inner_bottom + binding_w)
        ]
        add_cell(f"quilt-cell-binding-bottom", "binding", "plain_fabric", poly_bottom, fill_col)
        
        # Left
        poly_left = [
            (inner_left - binding_w, inner_top),
            (inner_left, inner_top),
            (inner_left, inner_bottom),
            (inner_left - binding_w, inner_bottom)
        ]
        add_cell(f"quilt-cell-binding-left", "binding", "plain_fabric", poly_left, fill_col)
        
        # Right
        poly_right = [
            (inner_right, inner_top),
            (inner_right + binding_w, inner_top),
            (inner_right + binding_w, inner_bottom),
            (inner_right, inner_bottom)
        ]
        add_cell(f"quilt-cell-binding-right", "binding", "plain_fabric", poly_right, fill_col)
        
    desc.text = quilt_data.to_json()
    return g_main
