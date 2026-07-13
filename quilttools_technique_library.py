#!/usr/bin/env python3
import json
import os
import math
import inkex
from lxml import etree

def format_fraction(val):
    val = round(val * 8) / 8.0
    whole = int(val)
    frac = val - whole
    fractions = {
        0.125: "⅛", 0.25: "¼", 0.375: "⅜", 0.5: "½",
        0.625: "⅝", 0.75: "¾", 0.875: "⅞"
    }
    for k, v in fractions.items():
        if abs(frac - k) < 1e-4:
            return f"{whole}{v}" if whole > 0 else v
    if abs(frac) < 1e-4:
        return str(whole)
    return f"{val:.3g}"

def get_technique_data(tech, w, h):
    title = ""
    instructions = ""
    if tech == "fg_4_at_a_time":
        title = "4-at-a-time Flying Geese"
        large_sq = w + 1.25
        small_sq = h + 0.875
        instructions = f"Cut 1 large square ({format_fraction(large_sq)}\") and 4 small squares ({format_fraction(small_sq)}\")."
    elif tech == "hst_2_at_a_time":
        title = "2-at-a-time Half-Square Triangles"
        sq = w + 0.875
        instructions = f"Cut 2 squares ({format_fraction(sq)}\"). Draw a diagonal line and sew ¼\" on each side."
    elif tech == "hst_8_at_a_time":
        title = "8-at-a-time Half-Square Triangles"
        sq = w * 2 + 1.75
        instructions = f"Cut 2 squares ({format_fraction(sq)}\"). Draw two diagonal lines and sew ¼\" on each side of both lines."
    elif tech == "qst_hourglass":
        title = "Quarter-Square Triangles (Hourglass)"
        sq = w + 1.25
        instructions = f"Cut 2 squares ({format_fraction(sq)}\"). Make 2-at-a-time HSTs, then pair those and repeat."
    elif tech == "square_in_square":
        title = "Square-in-a-Square (Economy Block)"
        center = w / 1.41421356 + 1.25
        corner = w / 2 + 0.875
        instructions = f"Cut 1 center square ({format_fraction(center)}\") and 2 squares ({format_fraction(corner)}\") cut in half diagonally."
    elif tech == "stitch_and_flip":
        title = "Stitch-and-Flip Corners"
        sq = w + 0.5
        instructions = f"Cut squares ({format_fraction(sq)}\"). Draw diagonal line, sew on line, trim ¼\" away."
    elif tech == "strip_set":
        title = "Strip-Set Sub-cutting"
        strip = w + 0.5
        instructions = f"Cut strips ({format_fraction(strip)}\" wide)."
    elif tech == "hrt":
        title = "Half-Rectangle Triangles"
        hr_w = w + 1.0 # Standard 2-at-a-time HRT adds about 1" to width and height for trimming
        hr_h = h + 1.0
        instructions = f"Cut 2 rectangles ({format_fraction(hr_w)}\" x {format_fraction(hr_h)}\"). Trim to {format_fraction(w+0.5)}\" x {format_fraction(h+0.5)}\"."
    return title, instructions

import quilttools_theme as qtheme

class TechniqueLibraryPlugin(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--technique", type=str, default="fg_4_at_a_time")
        pars.add_argument("--finished_width", type=float, default=4.0)
        pars.add_argument("--finished_height", type=float, default=2.0)
        pars.add_argument("--theme_override", type=str, default="")

    def effect(self):
        theme = qtheme.resolve_active_theme(self.options)
            
        w = self.options.finished_width
        h = self.options.finished_height
        title, instructions = get_technique_data(self.options.technique, w, h)
        
        # Build SVG group
        layer = self.svg.get_current_layer()
        g = etree.SubElement(layer, inkex.addNS("g", "svg"))
        
        font_head = theme.get("fonts", {}).get("heading", {})
        font_body = theme.get("fonts", {}).get("body", {})
        palette = theme.get("palette", {})
        ts = theme.get("type_scale_pt", {})
        
        # Insert Title
        head_text = etree.SubElement(g, inkex.addNS("text", "svg"))
        head_text.set("x", "100")
        head_text.set("y", "100")
        style = f"font-family:{font_head.get('family', 'sans-serif')}; font-weight:{font_head.get('weight', 'bold')}; font-size:{ts.get('heading', 14)}pt; fill:{palette.get('primary', '#000')};"
        head_text.set("style", style)
        head_text.text = title
        
        # Insert Instructions
        body_text = etree.SubElement(g, inkex.addNS("text", "svg"))
        body_text.set("x", "100")
        body_text.set("y", str(100 + ts.get('heading', 14) * 1.5))
        b_style = f"font-family:{font_body.get('family', 'sans-serif')}; font-weight:{font_body.get('weight', 'normal')}; font-size:{ts.get('body', 10)}pt; fill:{palette.get('ink', '#333')};"
        body_text.set("style", b_style)
        body_text.text = instructions
        
        # Draw simple instructional diagram
        diag_g = etree.SubElement(g, inkex.addNS("g", "svg"))
        diag_g.set("transform", "translate(100, 150)")
        stroke_color = palette.get("diagram_stroke", "#000")
        fill_color = palette.get("diagram_fill", "#CCC")
        fill_opacity = str(palette.get("diagram_fill_opacity", "0.2"))
        
        diag_style = f"fill:{fill_color}; fill-opacity:{fill_opacity}; stroke:{stroke_color}; stroke-width:1.5px; stroke-linejoin:round;"
        
        def draw_poly(pts):
            poly = etree.SubElement(diag_g, inkex.addNS("polygon", "svg"))
            poly.set("points", " ".join(f"{x},{y}" for x, y in pts))
            poly.set("style", diag_style)
            
        def draw_line(x1, y1, x2, y2, dashed=False):
            line = etree.SubElement(diag_g, inkex.addNS("line", "svg"))
            line.set("x1", str(x1))
            line.set("y1", str(y1))
            line.set("x2", str(x2))
            line.set("y2", str(y2))
            l_style = f"stroke:{stroke_color}; stroke-width:1px;"
            if dashed:
                l_style += " stroke-dasharray:4,4;"
            line.set("style", l_style)

        # Draw a generic block scaled to ~60px
        scale = min(100.0 / w, 100.0 / h)
        dw, dh = w * scale, h * scale
        
        tech = self.options.technique
        if tech == "fg_4_at_a_time":
            draw_poly([(0,dh), (dw/2,0), (dw,dh)]) # large triangle
            draw_poly([(0,0), (dw/2,0), (0,dh)]) # corner
            draw_poly([(dw,0), (dw/2,0), (dw,dh)]) # corner
        elif tech in ("hst_2_at_a_time", "stitch_and_flip"):
            draw_poly([(0,0), (dw,0), (dw,dh), (0,dh)])
            draw_line(0,0, dw,dh)
        elif tech == "hst_8_at_a_time":
            draw_poly([(0,0), (dw,0), (dw,dh), (0,dh)])
            draw_line(0,0, dw,dh)
            draw_line(dw,0, 0,dh)
            draw_line(dw/2,0, dw/2,dh, dashed=True)
            draw_line(0,dh/2, dw,dh/2, dashed=True)
        elif tech == "qst_hourglass":
            draw_poly([(0,0), (dw,0), (dw/2,dh/2)])
            draw_poly([(0,dh), (dw,dh), (dw/2,dh/2)])
            draw_poly([(0,0), (0,dh), (dw/2,dh/2)])
            draw_poly([(dw,0), (dw,dh), (dw/2,dh/2)])
        elif tech == "square_in_square":
            draw_poly([(dw/2,0), (dw,dh/2), (dw/2,dh), (0,dh/2)])
            draw_line(0,0, dw,0)
            draw_line(dw,0, dw,dh)
            draw_line(dw,dh, 0,dh)
            draw_line(0,dh, 0,0)
            draw_line(dw/2,0, 0,0)
            draw_line(dw/2,0, dw,0)
            draw_line(0,dh/2, 0,0)
            draw_line(dw,dh/2, dw,0)
        elif tech == "hrt":
            draw_poly([(0,0), (dw,0), (dw,dh), (0,dh)])
            draw_line(0,0, dw,dh)
        elif tech == "strip_set":
            draw_poly([(0,0), (dw,0), (dw,dh), (0,dh)])
            draw_line(dw/3,0, dw/3,dh, dashed=True)
            draw_line(2*dw/3,0, 2*dw/3,dh, dashed=True)

        inkex.utils.debug(f"Generated {title}: {instructions}")
        req_fonts = theme.get("required_fonts", [])
        inkex.utils.debug(f"Note: Ensure fonts are installed: {', '.join(req_fonts)}")

if __name__ == "__main__":
    TechniqueLibraryPlugin().run()
