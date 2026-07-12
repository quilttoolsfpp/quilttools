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

    # 1. Blocks
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
            
    # 2. Sashing & Cornerstones
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
    
    for i, b_w in enumerate(border_widths):
        layer = i + 1
        # Pick color alternately
        fill_col = fill_primary if i % 2 == 0 else fill_accent
        
        # Top
        poly_top = [
            (inner_left - b_w, inner_top - b_w),
            (inner_right + b_w, inner_top - b_w),
            (inner_right + b_w, inner_top),
            (inner_left - b_w, inner_top)
        ]
        add_cell(f"quilt-cell-border-{layer}-top", "border", "plain_fabric", poly_top, fill_col)
        
        # Bottom
        poly_bottom = [
            (inner_left - b_w, inner_bottom),
            (inner_right + b_w, inner_bottom),
            (inner_right + b_w, inner_bottom + b_w),
            (inner_left - b_w, inner_bottom + b_w)
        ]
        add_cell(f"quilt-cell-border-{layer}-bottom", "border", "plain_fabric", poly_bottom, fill_col)
        
        # Left
        poly_left = [
            (inner_left - b_w, inner_top),
            (inner_left, inner_top),
            (inner_left, inner_bottom),
            (inner_left - b_w, inner_bottom)
        ]
        add_cell(f"quilt-cell-border-{layer}-left", "border", "plain_fabric", poly_left, fill_col)
        
        # Right
        poly_right = [
            (inner_right, inner_top),
            (inner_right + b_w, inner_top),
            (inner_right + b_w, inner_bottom),
            (inner_right, inner_bottom)
        ]
        add_cell(f"quilt-cell-border-{layer}-right", "border", "plain_fabric", poly_right, fill_col)
        
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
