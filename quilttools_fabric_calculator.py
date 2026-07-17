#!/usr/bin/env python3
import json
import os
import inkex
from lxml import etree
import quilttools_fpp_core as core
import quilttools_fpp_fabric as fabric

import quilttools_quilt_core as qcore
import quilttools_theme as qtheme

class FabricCalculatorPlugin(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--calc_mode", type=str, default="fpp")
        pars.add_argument("--cutting_math", type=str, default="techniques")
        pars.add_argument("--share_techniques", type=inkex.Boolean, default=True)
        pars.add_argument("--manual_input", type=str, default="")
        pars.add_argument("--usable_wof", type=float, default=41.0)
        pars.add_argument("--theme_override", type=str, default="")

    def effect(self):
        # 1. Load Theme
        theme = qtheme.resolve_active_theme(self.options)

        # 2. Gather Data
        results = [] # list of (Role, Yardage, Notes)
        
        if self.options.calc_mode == "fpp":
            g_quilt, quilt_data = qcore.find_quilt_group(self.svg)
            if g_quilt is not None:
                # 2.1 Whole Quilt Mode!
                try:
                    plan = fabric.calculate_quilt_fabric_requirements(
                        quilt_data, g_quilt, self.options.usable_wof, self.options
                    )
                    
                    for color, res in sorted(plan["fabrics"].items()):
                        total_in = res["total_length_in"]
                        req = total_in / 36.0 # in yards
                        suggested = res.get("suggested_purchase") or fabric.suggest_purchase(total_in, res.get("fq_total_in"))
                        
                        # Count total pieces
                        total_pieces = 0
                        for op in res["ops"]:
                            if op["op"] in ("strip", "panel"):
                                total_pieces += op.get("pieces", 0)
                            elif op["op"] == "pieced_strip":
                                total_pieces += sum(len(sub["labels"]) for sub in op.get("subcuts", []))
                            elif op["op"] == "binding":
                                total_pieces += 1
                        
                        note = f"For {total_pieces} pieces ({suggested})"
                        warnings = res.get("warnings", [])
                        if any("exceeds" in w.lower() for w in warnings):
                            note += " (WARNING: exceeds WOF)"
                        results.append((f"Fabric {color}", f"{req:.2f} yd", note))
                except Exception as e:
                    inkex.errormsg(f"Whole Quilt Mode failed: {e}")
                    return
            else:
                # 2.2 Standard Single Block FPP Mode
                try:
                    block_data = core.extract_block_data_from_svg_root(self.svg)
                    if not block_data:
                        raise ValueError("No FPP block found in selection or layout.")
                    
                    finished_in = 10.0 # Default fallback
                    pieces_dict, _ = fabric.pieces_from_block(block_data, finished_in)
                    pieces = []
                    for p in pieces_dict:
                        pieces.append((p["polygon"], p["fabric"], p.get("meta", {})))
                        
                    estimates = fabric.fabric_estimate(pieces, usable_wof=self.options.usable_wof)
                    
                    for color, est in sorted(estimates.items()):
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
