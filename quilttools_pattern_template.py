#!/usr/bin/env python3
import json
import os
import inkex
from lxml import etree

import quilttools_theme as qtheme

class PatternTemplatePlugin(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--header_prefs", type=str, default="")
        pars.add_argument("--pattern_title", type=str, default="My New Quilt")
        pars.add_argument("--pattern_subtitle", type=str, default="A modern FPP design")
        pars.add_argument("--author_brand", type=str, default="")
        pars.add_argument("--logo_path", type=str, default="")
        pars.add_argument("--page_size", type=str, default="A4")
        pars.add_argument("--theme_override", type=str, default="")

    def effect(self):
        # 1. Load preferences
        prefs = qtheme.get_prefs()
        author_brand = prefs.get("author_brand", "My Quilt Brand")
        logo_path = prefs.get("logo_path", "")
        
        # 2. Resolve inputs and update prefs
        if self.options.author_brand.strip():
            author_brand = self.options.author_brand.strip()
            prefs["author_brand"] = author_brand
        if self.options.logo_path.strip():
            logo_path = self.options.logo_path.strip()
            prefs["logo_path"] = logo_path
            
        qtheme.set_prefs(prefs)

        # 3. Load Theme
        theme = qtheme.resolve_active_theme(self.options)

        # 4. Set Page Size (A4 or US Letter)
        svg = self.svg
        if self.options.page_size == "A4":
            w_mm, h_mm = 210, 297
            svg.set("width", "210mm")
            svg.set("height", "297mm")
            svg.set("viewBox", f"0 0 {w_mm} {h_mm}")
        else: # US Letter
            # 8.5 x 11 inches = 215.9 x 279.4 mm
            w_mm, h_mm = 215.9, 279.4
            svg.set("width", "8.5in")
            svg.set("height", "11in")
            svg.set("viewBox", f"0 0 {w_mm} {h_mm}")
            
        # Optional: scale document properly if viewbox was different, but this is a scaffold so assume empty.
        
        # 5. Create Layers (Guides, Background, Diagrams, Text)
        def create_layer(name):
            layer = etree.SubElement(svg, inkex.addNS("g", "svg"))
            layer.set(inkex.addNS("groupmode", "inkscape"), "layer")
            layer.set(inkex.addNS("label", "inkscape"), name)
            return layer
            
        bg_layer = create_layer("Background")
        guides_layer = create_layer("Guides")
        diagrams_layer = create_layer("Diagrams")
        text_layer = create_layer("Text")

        # 6. Apply Theme Styling (Borders, Placeholders)
        page_margins = theme.get("page", {}).get("margins_mm", {"top":18, "bottom":18, "inner":16, "outer":14})
        top, bot, inn, out = page_margins.get("top", 18), page_margins.get("bottom", 18), page_margins.get("inner", 16), page_margins.get("outer", 14)
        
        # Draw Border
        border_info = theme.get("page", {}).get("border", {})
        if border_info.get("enabled", False):
            rect = etree.SubElement(bg_layer, inkex.addNS("rect", "svg"))
            rect.set("x", str(inn))
            rect.set("y", str(top))
            rect.set("width", str(w_mm - inn - out))
            rect.set("height", str(h_mm - top - bot))
            style = f"fill:none; stroke:{border_info.get('stroke', '#000')}; stroke-width:{border_info.get('width_mm', 0.5)};"
            rect.set("style", style)
            
        # Draw Header/Title Block Placeholder
        fonts = theme.get("fonts", {})
        ts = theme.get("type_scale_pt", {})
        palette = theme.get("palette", {})
        
        title_text = etree.SubElement(text_layer, inkex.addNS("text", "svg"))
        title_text.set("x", str(inn + 5))
        title_text.set("y", str(top + 15))
        fh = fonts.get("heading", {})
        title_text.set("style", f"font-family:{fh.get('family', 'sans-serif')}; font-weight:{fh.get('weight','bold')}; font-size:{ts.get('title', 24)}pt; fill:{palette.get('primary', '#000')};")
        title_text.text = self.options.pattern_title
        
        sub_text = etree.SubElement(text_layer, inkex.addNS("text", "svg"))
        sub_text.set("x", str(inn + 5))
        sub_text.set("y", str(top + 25))
        fs = fonts.get("subtitle", {})
        sub_text.set("style", f"font-family:{fs.get('family', 'sans-serif')}; font-weight:{fs.get('weight','normal')}; font-style:{fs.get('style','normal')}; font-size:{ts.get('subtitle', 14)}pt; fill:{palette.get('muted', '#666')};")
        sub_text.text = self.options.pattern_subtitle
        
        brand_text = etree.SubElement(text_layer, inkex.addNS("text", "svg"))
        brand_text.set("x", str(inn + 5))
        brand_text.set("y", str(h_mm - bot - 5))
        brand_text.set("style", f"font-family:{fs.get('family', 'sans-serif')}; font-size:{ts.get('caption', 8)}pt; fill:{palette.get('muted', '#666')};")
        brand_text.text = prefs["author_brand"]
        
        # Logo placeholder
        if prefs["logo_path"] and os.path.exists(prefs["logo_path"]):
            image = etree.SubElement(diagrams_layer, inkex.addNS("image", "svg"))
            image.set("x", str(w_mm - out - 40))
            image.set("y", str(top + 5))
            image.set("width", "35")
            image.set("height", "35")
            image.set(inkex.addNS("href", "xlink"), f"file://{prefs['logo_path']}")
            
        inkex.utils.debug(f"Scaffolded new pattern: {self.options.pattern_title}")

if __name__ == "__main__":
    PatternTemplatePlugin().run()
