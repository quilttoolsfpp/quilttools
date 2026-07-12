#!/usr/bin/env python3
import json
import os
import inkex
from lxml import etree
import quilttools_fpp_core as core
import quilttools_fpp_fabric as fabric

import quilttools_theme as qtheme

class FabricCalculatorPlugin(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--calc_mode", type=str, default="fpp")
        pars.add_argument("--manual_input", type=str, default="")
        pars.add_argument("--usable_wof", type=float, default=41.0)
        pars.add_argument("--theme_override", type=str, default="")

    def effect(self):
        # 1. Load Theme
        theme = qtheme.resolve_active_theme(self.options)

        # 2. Gather Data
        results = [] # list of (Role, Yardage, Notes)
        
        if self.options.calc_mode == "fpp":
            try:
                block_data = core.extract_block_data_from_svg_root(self.svg)
                if not block_data:
                    raise ValueError("No FPP block found.")
                
                finished_in = 10.0 # Default fallback
                
                # Scale geometry to inches
                all_pts = [pt for r in block_data.tree.leaf_regions() for pt in r.polygon]
                if all_pts:
                    orig_w = max(p[0] for p in all_pts) - min(p[0] for p in all_pts)
                    orig_h = max(p[1] for p in all_pts) - min(p[1] for p in all_pts)
                    scale = finished_in / max(orig_w, orig_h) if max(orig_w, orig_h) > 0 else 1.0
                else:
                    scale = 1.0
                    
                color_mode = block_data.prefs.get("color_mode", "piece")
                user_colors = block_data.prefs.get("custom_colors", {})
                
                pieces = []
                for idx, r in enumerate(sorted(block_data.tree.leaf_regions(), key=lambda x: x.label)):
                    color_hex = user_colors.get(str(r.id)) or user_colors.get(r.id)
                    if not color_hex:
                        color_hex = core.get_color_for_label(r.label, color_mode, idx)
                    
                    sc_poly = [(pt[0]*scale, pt[1]*scale) for pt in r.polygon]
                    pieces.append((sc_poly, color_hex))
                    
                estimates = fabric.fabric_estimate(pieces, usable_wof=self.options.usable_wof)
                
                for color, est in estimates.items():
                    req = max(est["fixed_in"], est["free_in"]) / 36.0 # in yards
                    note = f"For {est['pieces_count']} pieces"
                    if est["exceeds_wof"]:
                        note += " (WARNING: exceeds WOF)"
                    results.append((f"Fabric {color}", f"{req:.2f} yd", note))
                    
            except Exception as e:
                inkex.errormsg(f"FPP Mode failed: {e}")
                return
                
        else: # Manual Mode
            pieces = []
            for token in self.options.manual_input.split(';'):
                token = token.strip()
                if not token: continue
                parts = token.split(',')
                if len(parts) == 2:
                    try:
                        w, h = float(parts[0]), float(parts[1])
                        poly = [(0,0), (w,0), (w,h), (0,h)]
                        pieces.append((poly, "Manual"))
                    except:
                        pass
            
            estimates = fabric.fabric_estimate(pieces, usable_wof=self.options.usable_wof)
            if "Manual" in estimates:
                est = estimates["Manual"]
                req = max(est["fixed_in"], est["free_in"]) / 36.0
                note = f"For {est['pieces_count']} pieces"
                if est["exceeds_wof"]:
                    note += " (WARNING: exceeds WOF)"
                results.append(("Main Fabric", f"{req:.2f} yd", note))

        # 3. Draw Themed Table
        layer = self.svg.get_current_layer()
        g = etree.SubElement(layer, inkex.addNS("g", "svg"))
        g.set("transform", "translate(50, 200)")
        
        fonts = theme.get("fonts", {})
        palette = theme.get("palette", {})
        ts = theme.get("type_scale_pt", {})
        
        # Table Header
        h_rect = etree.SubElement(g, inkex.addNS("rect", "svg"))
        h_rect.set("x", "0")
        h_rect.set("y", "0")
        h_rect.set("width", "300")
        h_rect.set("height", "25")
        h_rect.set("style", f"fill:{palette.get('table_header_fill', '#333')};")
        
        f_head = fonts.get("heading", {})
        f_body = fonts.get("body", {})
        
        col_x = [10, 110, 210]
        headers = ["Role", "Buy", "Notes"]
        for i, text in enumerate(headers):
            txt = etree.SubElement(g, inkex.addNS("text", "svg"))
            txt.set("x", str(col_x[i]))
            txt.set("y", "17")
            txt.set("style", f"font-family:{f_head.get('family', 'sans-serif')}; font-weight:bold; font-size:{ts.get('body', 10)}pt; fill:{palette.get('table_header_text', '#FFF')};")
            txt.text = text
            
        # Table Rows
        row_y = 25
        alt_fill = palette.get("table_row_alt_fill", "#EEE")
        
        for idx, (role, buy, notes) in enumerate(results):
            if idx % 2 == 0:
                bg = etree.SubElement(g, inkex.addNS("rect", "svg"))
                bg.set("x", "0")
                bg.set("y", str(row_y))
                bg.set("width", "300")
                bg.set("height", "20")
                bg.set("style", f"fill:{alt_fill};")
                
            for i, text in enumerate([role, buy, notes]):
                txt = etree.SubElement(g, inkex.addNS("text", "svg"))
                txt.set("x", str(col_x[i]))
                txt.set("y", str(row_y + 14))
                txt.set("style", f"font-family:{f_body.get('family', 'sans-serif')}; font-size:{ts.get('body', 10)}pt; fill:{palette.get('ink', '#000')};")
                txt.text = text
                
            row_y += 20
            
        # Caveat
        cav = etree.SubElement(g, inkex.addNS("text", "svg"))
        cav.set("x", "0")
        cav.set("y", str(row_y + 15))
        cav.set("style", f"font-family:{f_body.get('family', 'sans-serif')}; font-style:italic; font-size:{ts.get('caption', 8)}pt; fill:{palette.get('muted', '#666')};")
        cav.text = "Estimate — add margin for fussy-cutting / directional fabric."
        
        inkex.utils.debug(f"Generated Fabric Requirements Table with {len(results)} rows.")

if __name__ == "__main__":
    FabricCalculatorPlugin().run()
