#!/usr/bin/env python3
import os
import sys
import random
from lxml import etree
import inkex

# Ensure extension path is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import quilttools_colour as qcol
import quilttools_theme as qtheme
import quilttools_svg as qsvg

def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

class PaletteGeneratorPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--notebook", type=str, default="rules_page")
        pars.add_argument("--n", type=int, default=6)
        pars.add_argument("--rule", type=str, default="analogous")
        pars.add_argument("--anchor", type=str, default="")
        pars.add_argument("--anchor_source", type=str, default="hex")
        pars.add_argument("--anchor_pick", type=str, default="0x5e8c61ff")
        pars.add_argument("--tolerance", type=float, default=15.0)
        pars.add_argument("--seed", type=str, default="")
        pars.add_argument("--export_gpl", type=inkex.Boolean, default=True)
        pars.add_argument("--palette_name", type=str, default="Generated_Palette")
        pars.add_argument("--draw_swatches", type=inkex.Boolean, default=True)

    def parse_arguments(self, args):
        # Tolerate dialog params the script doesn't know (keeps the tool
        # working while the .inx evolves).
        self.options, _unknown = self.arg_parser.parse_known_args(args)

    @staticmethod
    def _parse_colour_opt(raw):
        """Inkscape colour params arrive as a (possibly negative) 32-bit
        RGBA integer or 0x... string; accept plain hex too."""
        import re as _re
        s = str(raw or "").strip()
        try:
            if _re.match(r"^-?\d+$", s):
                rgba = int(s) & 0xFFFFFFFF
            elif _re.match(r"^0x[0-9a-fA-F]+$", s):
                rgba = int(s, 16) & 0xFFFFFFFF
            else:
                s = s.lstrip("#").lower()
                if _re.match(r"^[0-9a-f]{6}$", s):
                    return "#" + s
                if _re.match(r"^[0-9a-f]{3}$", s):
                    return "#" + "".join(ch * 2 for ch in s)
                return None
            return "#%02x%02x%02x" % ((rgba >> 24) & 255,
                                      (rgba >> 16) & 255,
                                      (rgba >> 8) & 255)
        except Exception:
            return None

    def effect(self):
        n = self.options.n
        rule = self.options.rule
        source = (self.options.anchor_source or "hex").strip()
        if source == "picker":
            anchor = self._parse_colour_opt(self.options.anchor_pick) or ""
            if not anchor:
                inkex.utils.debug("Could not read the picked colour; "
                                  "using a random anchor instead.")
        elif source == "random":
            anchor = ""
        else:
            anchor = self._parse_colour_opt(self.options.anchor) or ""
            if self.options.anchor.strip() and not anchor:
                inkex.utils.debug(
                    f"'{self.options.anchor.strip()}' is not a valid hex "
                    "colour; using a random anchor instead.")
        tolerance = self.options.tolerance
        seed = self.options.seed.strip()
        export_gpl = self.options.export_gpl
        palette_name = self.options.palette_name.strip() or "Generated_Palette"
        draw_swatches = self.options.draw_swatches

        # 1. Resolve seed
        if not seed:
            seed = str(random.randint(1, 999999))
        rng = random.Random(seed)

        # 2. Generate colors
        colors = qcol.generate_palette(n, rule, anchor, tolerance, rng)

        # 3. Export to GPL
        gpl_path = ""
        if export_gpl:
            # Clean name for filename
            clean_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in palette_name)
            gpl_lines = [
                "GIMP Palette",
                f"Name: {palette_name}",
                "Columns: 8",
                "#"
            ]
            for idx, c_hex in enumerate(colors, 1):
                try:
                    r, g, b = hex_to_rgb(c_hex)
                    gpl_lines.append(f"{r:3d} {g:3d} {b:3d}\tColor {idx} ({c_hex})")
                except Exception:
                    pass

            palettes_dir = os.path.join(os.environ.get("APPDATA", ""), "inkscape", "palettes")
            os.makedirs(palettes_dir, exist_ok=True)
            gpl_path = os.path.join(palettes_dir, f"{clean_name}.gpl")
            try:
                with open(gpl_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(gpl_lines) + "\n")
            except Exception as e:
                inkex.utils.debug(f"Warning: Could not save GPL file: {e}")
                export_gpl = False

        # 4. Draw swatches on canvas
        if draw_swatches:
            layer_id = "generated-palette-layer"
            
            # Remove existing generated palette layer if it exists
            for old_layer in self.svg.findall(f".//{{{qsvg.SVG_NS}}}g[@id='{layer_id}']"):
                self.svg.getroot().remove(old_layer)

            # Create new layer
            layer = etree.Element(
                "{%s}g" % qsvg.SVG_NS,
                id=layer_id,
                **{
                    f"{{{qsvg.INKSCAPE_NS}}}groupmode": "layer",
                    f"{{{qsvg.INKSCAPE_NS}}}label": "Generated Palette"
                }
            )

            # Swatch arrangement settings
            w, h = 60.0, 60.0
            padding = 20.0
            start_x, start_y = 100.0, 100.0
            columns = 8

            for idx, color in enumerate(colors):
                col_idx = idx % columns
                row_idx = idx // columns

                x = start_x + col_idx * (w + padding)
                y = start_y + row_idx * (h + padding + 20.0)

                # Rect element
                rect = etree.SubElement(
                    layer,
                    "{%s}rect" % qsvg.SVG_NS,
                    x=str(x),
                    y=str(y),
                    width=str(w),
                    height=str(h),
                    style=f"fill:{color};stroke:#333333;stroke-width:1.0;stroke-linejoin:round;"
                )

                # Text label element
                text = etree.SubElement(
                    layer,
                    "{%s}text" % qsvg.SVG_NS,
                    x=str(x + w / 2.0),
                    y=str(y + h + 15.0),
                    style=f"font-size:10px;font-family:sans-serif;text-anchor:middle;fill:#333333;"
                )
                text.text = color

            self.svg.append(layer)

        # 5. Report results
        msg = f"Palette generation successful!\nGenerated {len(colors)} colors under '{rule}' rule.\nSeed used: {seed}"
        if export_gpl and gpl_path:
            msg += f"\nSaved palette file to: {gpl_path}"
        inkex.utils.debug(msg)

if __name__ == "__main__":
    PaletteGeneratorPlugin().run()
