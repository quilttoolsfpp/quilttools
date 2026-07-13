#!/usr/bin/env python3
import json
import os
import inkex
from lxml import etree

import quilttools_theme as qtheme

class MetadataBlocksPlugin(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--block_text", type=str, default="")
        pars.add_argument("--block_type", type=str, default="step")
        pars.add_argument("--step_number", type=int, default=1)
        pars.add_argument("--theme_override", type=str, default="")

    def effect(self):
        # Load theme preference
        theme = qtheme.resolve_active_theme(self.options)
            
        layer = self.svg.get_current_layer()
        g = etree.SubElement(layer, inkex.addNS("g", "svg"))
        
        fonts = theme.get("fonts", {})
        palette = theme.get("palette", {})
        ts = theme.get("type_scale_pt", {})
        
        text_el = etree.SubElement(g, inkex.addNS("text", "svg"))
        # Put in arbitrary default location (e.g. center of view if available, or just 100,100)
        # We can extract center of view from self.svg.namedview if needed. Using 100,100 for now.
        text_el.set("x", "100")
        text_el.set("y", "100")
        
        b_type = self.options.block_type
        text_content = self.options.block_text
        
        if b_type == "title":
            f_cfg = fonts.get("heading", {})
            style = f"font-family:{f_cfg.get('family', 'sans-serif')}; font-weight:{f_cfg.get('weight','bold')}; font-size:{ts.get('heading', 14)}pt; fill:{palette.get('primary', '#000')};"
            text_el.text = text_content
        elif b_type == "warning":
            f_cfg = fonts.get("body", {})
            style = f"font-family:{f_cfg.get('family', 'sans-serif')}; font-weight:bold; font-size:{ts.get('body', 10)}pt; fill:{palette.get('warning', '#D00')};"
            text_el.text = f"WARNING: {text_content}"
        elif b_type == "note":
            f_cfg = fonts.get("body", {})
            style = f"font-family:{f_cfg.get('family', 'sans-serif')}; font-style:italic; font-size:{ts.get('body', 10)}pt; fill:{palette.get('muted', '#666')};"
            text_el.text = f"Note: {text_content}"
        else: # step
            f_cfg = fonts.get("body", {})
            style = f"font-family:{f_cfg.get('family', 'sans-serif')}; font-weight:{f_cfg.get('weight','normal')}; font-size:{ts.get('body', 10)}pt; fill:{palette.get('ink', '#000')};"
            text_el.text = f"{self.options.step_number}. {text_content}"
            
        text_el.set("style", style)
        
        inkex.utils.debug(f"Added {b_type} block.")

if __name__ == "__main__":
    MetadataBlocksPlugin().run()
