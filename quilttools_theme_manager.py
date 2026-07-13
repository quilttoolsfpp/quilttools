#!/usr/bin/env python3
import json
import os
import shutil
import sys
from lxml import etree
import inkex

import quilttools_theme as qtheme

class ThemeManagerPlugin(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--notebook", type=str, default="active_theme_tab")
        pars.add_argument("--active_theme_id", type=str, default="ifh")
        pars.add_argument("--list_themes", type=inkex.Boolean, default=False)
        pars.add_argument("--validate_theme_id", type=str, default="")
        pars.add_argument("--swatch_theme_id", type=str, default="")
        pars.add_argument("--new_theme_id", type=str, default="my_custom_theme")

    def effect(self):
        tab = self.options.notebook
        
        if tab == "active_theme_tab":
            self.run_active_theme()
        elif tab == "validate_theme_tab":
            self.run_validate_theme()
        elif tab == "render_swatch_tab":
            self.run_render_swatch()
        elif tab == "new_theme_tab":
            self.run_new_theme()
        else:
            inkex.errormsg(f"Unknown action tab: {tab}")

    def run_active_theme(self):
        theme_id = (self.options.active_theme_id or "").strip()
        if not theme_id:
            inkex.errormsg("Please enter a valid Theme ID.")
            return

        # Verify theme exists or can be loaded
        theme_path = os.path.join(qtheme.THEMES_DIR, f"{theme_id}.json")
        if not os.path.exists(theme_path):
            inkex.errormsg(f"Error: Theme file '{theme_id}.json' not found in themes/ folder.")
            return

        # Save preference
        prefs = qtheme.get_prefs()
        if theme_id in ["ifh", "childrens_moments"]:
            prefs["theme"] = theme_id
            if "custom_theme" in prefs:
                del prefs["custom_theme"]
        else:
            prefs["theme"] = "custom"
            prefs["custom_theme"] = theme_id
            
        qtheme.set_prefs(prefs)
        
        msg = f"Active theme set to: '{theme_id}'\n"
        if self.options.list_themes:
            themes = qtheme.discover_themes()
            msg += "\nDiscovered Themes:\n"
            for tid, info in themes.items():
                active_marker = " (Active)" if tid == theme_id else ""
                msg += f"- {info['name']}{active_marker} [ID: {tid}]\n  {info['description']}\n"
        
        inkex.utils.debug(msg)

    def run_validate_theme(self):
        theme_id = (self.options.validate_theme_id or "").strip()
        if not theme_id:
            # Fallback to active theme
            prefs = qtheme.get_prefs()
            theme_id = prefs.get("theme", "ifh")
            if theme_id == "custom":
                theme_id = prefs.get("custom_theme", "ifh")

        theme_path = os.path.join(qtheme.THEMES_DIR, f"{theme_id}.json")
        if not os.path.exists(theme_path):
            inkex.errormsg(f"Error: Theme file '{theme_id}.json' not found.")
            return

        report = [f"Theme Validation Report for '{theme_id}':"]
        errors = 0
        
        # 1. JSON parse check
        try:
            with open(theme_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            report.append("[✓] JSON Syntax: Valid")
        except Exception as e:
            report.append(f"[✗] JSON Syntax: Invalid ({e})")
            inkex.errormsg("\n".join(report))
            return

        # 2. Check required schema fields
        required_fields = ["schema_version", "name", "id", "fonts", "palette", "type_scale_pt", "page", "rules"]
        for f in required_fields:
            if f in data:
                report.append(f"[✓] Required Field '{f}': Present")
            else:
                report.append(f"[✗] Required Field '{f}': Missing")
                errors += 1

        # 3. Font existence check
        req_fonts = data.get("required_fonts", [])
        if req_fonts:
            report.append("\nRequired Fonts Check:")
            installed_fonts = self.get_system_fonts()
            for font in req_fonts:
                # Case-insensitive substring match
                found = False
                for f_name in installed_fonts:
                    if font.lower() in f_name.lower():
                        found = True
                        break
                if found:
                    report.append(f"  [✓] Font '{font}': Installed")
                else:
                    report.append(f"  [!] Font '{font}': NOT found on system (Warning)")
                    
        if errors == 0:
            report.append("\nTheme is fully valid and ready to use!")
        else:
            report.append(f"\nTheme has {errors} schema error(s). Please fix before exporting.")

        inkex.utils.debug("\n".join(report))

    def get_system_fonts(self):
        """Helper to get a list of system font names on Windows."""
        fonts = set()
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
            for i in range(10000):
                try:
                    name, _, _ = winreg.EnumValue(key, i)
                    fonts.add(name.split(" (")[0].strip())
                except OSError:
                    break
        except Exception:
            pass
            
        try:
            user_fonts = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
            if os.path.exists(user_fonts):
                for f in os.listdir(user_fonts):
                    name, _ = os.path.splitext(f)
                    fonts.add(name.replace("-", " ").title())
        except Exception:
            pass
            
        return fonts

    def run_render_swatch(self):
        theme_id = (self.options.swatch_theme_id or "").strip()
        if not theme_id:
            # Fallback to active theme
            prefs = qtheme.get_prefs()
            theme_id = prefs.get("theme", "ifh")
            if theme_id == "custom":
                theme_id = prefs.get("custom_theme", "ifh")

        theme = qtheme.load_theme(theme_id)
        
        # Get insertion point
        layer = self.svg.get_current_layer()
        g = etree.SubElement(layer, inkex.addNS("g", "svg"), id=f"theme-swatch-{theme_id}")
        
        # Default positioning
        g.set("transform", "translate(50, 50)")
        
        palette = theme.get("palette", {})
        fonts = theme.get("fonts", {})
        ts = theme.get("type_scale_pt", {})
        
        bg_col = palette.get("background", "#FFFFFF")
        primary_col = palette.get("primary", "#000000")
        ink_col = palette.get("ink", "#000000")
        muted_col = palette.get("muted", "#666666")
        
        # 1. Background Rect
        bg = etree.SubElement(g, inkex.addNS("rect", "svg"), {
            "x": "0", "y": "0", "width": "500", "height": "300",
            "style": f"fill:{bg_col}; stroke:{primary_col}; stroke-width:1.5; rx:10; ry:10;"
        })
        
        # 2. Header Title
        heading_font = fonts.get("heading", {}).get("family", "Fraunces")
        heading_weight = fonts.get("heading", {}).get("weight", "600")
        heading_style = fonts.get("heading", {}).get("style", "normal")
        
        title_text = etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "20", "y": "40",
            "style": f"font-family:{heading_font}; font-size:18pt; font-weight:{heading_weight}; font-style:{heading_style}; fill:{primary_col};"
        })
        title_text.text = theme.get("name", theme_id)
        
        # 3. Header Subtitle
        sub_font = fonts.get("subtitle", {}).get("family", "Fraunces")
        sub_weight = fonts.get("subtitle", {}).get("weight", "400")
        sub_style = fonts.get("subtitle", {}).get("style", "italic")
        
        sub_text = etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "20", "y": "60",
            "style": f"font-family:{sub_font}; font-size:9pt; font-weight:{sub_weight}; font-style:{sub_style}; fill:{muted_col};"
        })
        sub_text.text = theme.get("description", "")[:75]
        
        # 4. Divider
        etree.SubElement(g, inkex.addNS("line", "svg"), {
            "x1": "20", "y1": "75", "x2": "480", "y2": "75",
            "style": f"stroke:{muted_col}; stroke-width:1;"
        })
        
        # 5. Typography column
        etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "20", "y": "95",
            "style": f"font-family:{heading_font}; font-size:11pt; font-weight:bold; fill:{ink_col};"
        }).text = "Typography"
        
        # Heading Sample
        h_sample = etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "20", "y": "130",
            "style": f"font-family:{heading_font}; font-size:12pt; font-weight:{heading_weight}; font-style:{heading_style}; fill:{ink_col};"
        })
        h_sample.text = f"Heading: {heading_font} ({heading_weight})"
        
        # Subtitle Sample
        s_sample = etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "20", "y": "160",
            "style": f"font-family:{sub_font}; font-size:11pt; font-weight:{sub_weight}; font-style:{sub_style}; fill:{ink_col};"
        })
        s_sample.text = f"Subtitle: {sub_font}"
        
        # Body Sample
        body_font = fonts.get("body", {}).get("family", "Fraunces")
        body_weight = fonts.get("body", {}).get("weight", "400")
        body_style = fonts.get("body", {}).get("style", "normal")
        b_sample = etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "20", "y": "190",
            "style": f"font-family:{body_font}; font-size:10pt; font-weight:{body_weight}; font-style:{body_style}; fill:{ink_col};"
        })
        b_sample.text = f"Body: {body_font} ({body_weight})"
        
        # Mono Sample
        mono_font = fonts.get("mono", {}).get("family", "IBM Plex Mono")
        mono_weight = fonts.get("mono", {}).get("weight", "400")
        mono_style = fonts.get("mono", {}).get("style", "normal")
        m_sample = etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "20", "y": "220",
            "style": f"font-family:{mono_font}; font-size:9pt; font-weight:{mono_weight}; font-style:{mono_style}; fill:{ink_col};"
        })
        m_sample.text = f"Mono: {mono_font}"
        
        # 6. Colors column
        etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "280", "y": "95",
            "style": f"font-family:{heading_font}; font-size:11pt; font-weight:bold; fill:{ink_col};"
        }).text = "Color Palette"
        
        color_keys = ["primary", "accent", "muted", "ink", "background", "warning"]
        y_offset = 120
        for key in color_keys:
            col_val = palette.get(key, "#000000")
            
            # Swatch rect
            etree.SubElement(g, inkex.addNS("rect", "svg"), {
                "x": "280", "y": str(y_offset), "width": "18", "height": "18", "rx": "4", "ry": "4",
                "style": f"fill:{col_val}; stroke:{ink_col}; stroke-width:0.5;"
            })
            
            # Text label
            lbl = etree.SubElement(g, inkex.addNS("text", "svg"), {
                "x": "305", "y": str(y_offset + 13),
                "style": f"font-family:{mono_font}; font-size:8pt; fill:{ink_col};"
            })
            lbl.text = f"{key}: {col_val}"
            y_offset += 26
            
        inkex.utils.debug(f"Rendered swatch card for theme '{theme_id}' onto the canvas.")

    def run_new_theme(self):
        new_id = (self.options.new_theme_id or "").strip()
        if not new_id:
            inkex.errormsg("Please specify a new Theme ID.")
            return

        new_id_clean = "".join(c for c in new_id if c.isalnum() or c == "_").lower()
        if not new_id_clean:
            inkex.errormsg("Theme ID contains invalid characters.")
            return

        dest_path = os.path.join(qtheme.THEMES_DIR, f"{new_id_clean}.json")
        if os.path.exists(dest_path):
            inkex.errormsg(f"A theme with ID '{new_id_clean}' already exists at:\n  {dest_path}")
            return

        src_path = os.path.join(qtheme.THEMES_DIR, "ifh.json")
        if not os.path.exists(src_path):
            inkex.errormsg("Could not locate the template theme 'ifh.json'.")
            return

        try:
            # Clone and modify metadata
            with open(src_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            data["id"] = new_id_clean
            data["name"] = new_id_clean.replace("_", " ").title()
            data["description"] = f"Custom theme cloned from IFH template."
            
            os.makedirs(qtheme.THEMES_DIR, exist_ok=True)
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            inkex.utils.debug(f"New theme cloned successfully!\nFile location:\n  {dest_path}\n\nYou can edit this JSON file directly to customize colors and typography.")
        except Exception as e:
            inkex.errormsg(f"Failed to clone theme template: {e}")

if __name__ == "__main__":
    ThemeManagerPlugin().run()
