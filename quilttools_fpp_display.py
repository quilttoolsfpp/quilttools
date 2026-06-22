#!/usr/bin/env python3
import re

import inkex

import quilttools_fpp_core as core


class DisplayPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="refresh_only")
        pars.add_argument("--color_mode", type=str, default="piece")
        pars.add_argument("--show_sa", type=inkex.Boolean, default=False)
        pars.add_argument("--sa_in", type=float, default=0.25)
        pars.add_argument("--quantize_n", type=int, default=6)
        pars.add_argument("--locked_colors", type=str, default="")
        pars.add_argument("--group_by_color", type=inkex.Boolean, default=False)

    def effect(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        if self.options.action == "save_colors":
            # Scrape colors directly from the Inkscape paths
            user_colors = block_data.prefs.get("custom_colors", {})
            for path in g.findall(f".//{{{core.SVG_NS}}}path"):
                rid = path.get(core.FPP_REGION_ATTR)
                if rid:
                    color = core.resolve_element_fill(path)
                    if color:
                        user_colors[str(rid)] = color

            block_data.prefs["custom_colors"] = user_colors
            inkex.utils.debug(
                f"Saved {len(user_colors)} custom colors into permanent block memory!"
            )

        elif self.options.action == "clear_colors":
            block_data.prefs["custom_colors"] = {}
            inkex.utils.debug(
                "Cleared custom colors. Reverting to default algorithmic palette."
            )

        elif self.options.action == "sample_image":
            sampled = core.sample_image_colors(self.svg, block_data)
            if sampled > 0:
                inkex.utils.debug(f"Sampled {sampled} colors from underlying image!")
            else:
                inkex.utils.debug("No colors sampled. Make sure there is a background image overlapping the block centroid.")

        elif self.options.action == "quantize":
            # Get locked colors from input string
            locked_list = [c.strip() for c in self.options.locked_colors.split(",") if c.strip()]
            
            # Also lock colors from current canvas selection
            selection_colors = []
            if self.svg.selection:
                for el in self.svg.selection.values():
                    color = core.resolve_element_fill(el)
                    if color:
                        color = color.strip().lower()
                        if color.startswith("#") and color not in selection_colors:
                            selection_colors.append(color)

            if selection_colors:
                merged_locked = list(locked_list)
                for sc in selection_colors:
                    if sc not in merged_locked:
                        merged_locked.append(sc)
                locked_list = merged_locked
                inkex.utils.debug(f"Locked {len(selection_colors)} color(s) from selected canvas elements: {', '.join(selection_colors)}")

            if len(locked_list) > self.options.quantize_n:
                inkex.utils.debug(f"Warning: Number of locked colors ({len(locked_list)}) exceeds N ({self.options.quantize_n}). All locked colors will still be preserved.")
            
            core.quantize_block_colors(block_data, self.options.quantize_n, locked_list)
            inkex.utils.debug(f"Quantized colors to {self.options.quantize_n} fabrics (with {len(locked_list)} locked).")

        elif self.options.action == "export_palette":
            # Scrape current colors from canvas first to be up to date
            user_colors = block_data.prefs.get("custom_colors", {})
            for path in g.findall(f".//{{{core.SVG_NS}}}path"):
                rid = path.get(core.FPP_REGION_ATTR)
                if rid:
                    color = core.resolve_element_fill(path)
                    if color:
                        user_colors[str(rid)] = color
            block_data.prefs["custom_colors"] = user_colors

            # Get unique custom colors
            colors = sorted(list(set(c.strip() for c in user_colors.values() if c and c.strip().startswith("#"))))
            if not colors:
                # Fallback to default palette
                regions = block_data.tree.leaf_regions()
                color_mode = block_data.prefs.get("color_mode", "piece")
                for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
                    c = core.get_color_for_label(r.label, color_mode, idx)
                    if c and c.startswith("#"):
                        colors.append(c)
                colors = sorted(list(set(colors)))

            if not colors:
                inkex.utils.debug("No colors found in block to export.")
            else:
                import os
                docname = self.svg.get(f"{{{core.SODIPODI_NS}}}docname") or self.svg.get("sodipodi:docname")
                palette_name = "FPP_Block_Palette"
                if docname:
                    base_name = os.path.basename(docname)
                    if base_name.lower().endswith(".svg"):
                        base_name = base_name[:-4]
                    palette_name = "FPP_" + "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base_name)

                # Format as GIMP/Inkscape GPL
                gpl_lines = [
                    "GIMP Palette",
                    f"Name: {palette_name}",
                    "Columns: 8",
                    "#"
                ]
                for idx, c_hex in enumerate(colors, 1):
                    try:
                        r_val, g_val, b_val = core.hex_to_rgb(c_hex)
                        gpl_lines.append(f"{r_val:3d} {g_val:3d} {b_val:3d}\tFabric {idx} ({c_hex})")
                    except Exception:
                        pass

                palettes_dir = r"c:\Users\Pritt\AppData\Roaming\inkscape\palettes"
                os.makedirs(palettes_dir, exist_ok=True)
                palette_file = os.path.join(palettes_dir, f"{palette_name}.gpl")
                with open(palette_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(gpl_lines) + "\n")

                inkex.utils.debug(
                    f"Created Inkscape palette '{palette_name}' with {len(colors)} colors!\n"
                    f"Saved to: {palette_file}\n"
                    f"Open Inkscape's palette menu (click the small triangle in the bottom-right corner of the color bar) to load it!"
                )



        # Update Display Preferences
        block_data.prefs["color_mode"] = self.options.color_mode
        block_data.prefs["show_sa"] = self.options.show_sa
        block_data.prefs["sa_in"] = self.options.sa_in
        block_data.prefs["group_by_color"] = self.options.group_by_color

        # Trigger a full mathematical redraw to apply new settings
        core.refresh_layer(g, block_data)



if __name__ == "__main__":
    DisplayPlugin().run()
