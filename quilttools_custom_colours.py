#!/usr/bin/env python3
"""03. Custom Block Colours (Quilt Tools Colour).

The PERMANENT colour memory of a block: save canvas paint into the block,
sample from a traced image, quantize to N fabrics, export an Inkscape
palette, or clear. Split out of the old FPP Display tool - the
non-destructive display switches (bypass toggle, palette mode, seam
allowances) stayed in Quilt Tools Block > 05. FPP Display Toggle.

BLOCKS ONLY: these actions edit a block's saved colour data. On a quilt
layout, recolour placed cells with the Fabric Palette or Colour
Randomiser instead, or open the source block from the Block Library.
"""
import os

import inkex

import quilttools_fpp_core as core
import quilttools_colour as qcol


class CustomColoursPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="save_colors")
        pars.add_argument("--fill_opacity", type=float, default=1.0)
        pars.add_argument("--show_sa", type=inkex.Boolean, default=False)
        pars.add_argument("--sa_in", type=float, default=0.25)
        pars.add_argument("--group_by_color", type=inkex.Boolean, default=False)
        pars.add_argument("--quantize_n", type=int, default=6)
        pars.add_argument("--locked_colors", type=str, default="")
        pars.add_argument("--color_code_overrides", type=str, default="")

    def effect(self):
        ctx = qcol.detect_context(self.svg)
        if ctx["block_g"] is None:
            key = "need_block" if ctx["kind"] == "quilt" else "need_any"
            return inkex.errormsg(qcol.CONTEXT_HELP[key])
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg(qcol.CONTEXT_HELP["need_block"])

        # Update display settings
        block_data.prefs["fill_opacity"] = self.options.fill_opacity
        block_data.prefs["show_sa"] = self.options.show_sa
        block_data.prefs["sa_in"] = self.options.sa_in
        block_data.prefs["group_by_color"] = self.options.group_by_color

        action = self.options.action

        if action == "save_colors":
            user_colors = block_data.prefs.get("custom_colors", {})
            count = 0
            for path in g.findall(f".//{{{core.SVG_NS}}}path"):
                rid = path.get(core.FPP_REGION_ATTR)
                if rid:
                    color = core.resolve_element_fill(path)
                    if color:
                        user_colors[str(rid)] = color
                        count += 1
            block_data.prefs["custom_colors"] = user_colors
            block_data.prefs["bypass_custom_colors"] = False
            inkex.utils.debug(
                f"Saved {count} canvas colour(s) into the block. "
                + qcol.context_note(ctx, "block"))

        elif action == "set_display":
            inkex.utils.debug(
                f"Updated block display preferences: fill opacity={self.options.fill_opacity:.2f}, "
                f"seam allowances={'ON' if self.options.show_sa else 'OFF'}, "
                f"group by color={'ON' if self.options.group_by_color else 'OFF'}."
            )


        elif action == "clear_colors":
            block_data.prefs["custom_colors"] = {}
            block_data.prefs["bypass_custom_colors"] = False
            inkex.utils.debug("Cleared all saved custom colours - the "
                              "block reverts to the default palette. "
                              + qcol.context_note(ctx, "block"))

        elif action == "sample_image":
            sampled = core.sample_image_colors(self.svg, block_data)
            if sampled > 0:
                block_data.prefs["bypass_custom_colors"] = False
                inkex.utils.debug(
                    f"Sampled {sampled} colour(s) from the traced image. "
                    + qcol.context_note(ctx, "block"))
            else:
                inkex.utils.debug(
                    "No colors sampled. Make sure there is a background "
                    "image overlapping the block centroid.")

        elif action == "quantize":
            locked_list = [c.strip() for c in
                           self.options.locked_colors.split(",") if c.strip()]
            selection_colors = []
            if self.svg.selection:
                for el in self.svg.selection.values():
                    color = core.resolve_element_fill(el)
                    if color:
                        color = color.strip().lower()
                        if color.startswith("#") and \
                                color not in selection_colors:
                            selection_colors.append(color)
            for sc in selection_colors:
                if sc not in locked_list:
                    locked_list.append(sc)
            if len(locked_list) > self.options.quantize_n:
                inkex.utils.debug(
                    f"Warning: Number of locked colors ({len(locked_list)}) "
                    f"exceeds N ({self.options.quantize_n}). All locked "
                    "colors will still be preserved.")
            core.quantize_block_colors(block_data, self.options.quantize_n,
                                       locked_list)
            block_data.prefs["bypass_custom_colors"] = False
            inkex.utils.debug(
                f"Quantized to {self.options.quantize_n} fabric(s). "
                + qcol.context_note(ctx, "block"))

        elif action == "export_palette":
            user_colors = block_data.prefs.get("custom_colors", {})
            for path in g.findall(f".//{{{core.SVG_NS}}}path"):
                rid = path.get(core.FPP_REGION_ATTR)
                if rid:
                    color = core.resolve_element_fill(path)
                    if color:
                        user_colors[str(rid)] = color
            block_data.prefs["custom_colors"] = user_colors
            block_data.prefs["bypass_custom_colors"] = False

            colors = sorted(list(set(
                c.strip() for c in user_colors.values()
                if c and c.strip().startswith("#"))))
            if not colors:
                regions = block_data.tree.leaf_regions()
                color_mode = block_data.prefs.get("color_mode", "piece")
                for idx, r in enumerate(sorted(regions,
                                               key=lambda x: x.label)):
                    c = core.get_color_for_label(r.label, color_mode, idx)
                    if c and c.startswith("#"):
                        colors.append(c)
                colors = sorted(list(set(colors)))

            if not colors:
                inkex.utils.debug("No colors found in block to export.")
            else:
                docname = self.svg.get(f"{{{core.SODIPODI_NS}}}docname") \
                    or self.svg.get("sodipodi:docname")
                palette_name = "FPP_Block_Palette"
                if docname:
                    base_name = os.path.basename(docname)
                    if base_name.lower().endswith(".svg"):
                        base_name = base_name[:-4]
                    palette_name = "FPP_" + "".join(
                        c if c.isalnum() or c in ("-", "_") else "_"
                        for c in base_name)

                gpl_lines = ["GIMP Palette", f"Name: {palette_name}",
                             "Columns: 8", "#"]
                for idx, c_hex in enumerate(colors, 1):
                    try:
                        r_val, g_val, b_val = core.hex_to_rgb(c_hex)
                        gpl_lines.append(
                            f"{r_val:3d} {g_val:3d} {b_val:3d}\t"
                            f"Fabric {idx} ({c_hex})")
                    except Exception:
                        pass

                palettes_dir = os.path.join(
                    os.environ.get("APPDATA", ""), "inkscape", "palettes")
                os.makedirs(palettes_dir, exist_ok=True)
                palette_file = os.path.join(palettes_dir,
                                            f"{palette_name}.gpl")
                with open(palette_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(gpl_lines) + "\n")

                inkex.utils.debug(
                    f"Created Inkscape palette '{palette_name}' with "
                    f"{len(colors)} colors!\nSaved to: {palette_file}\n"
                    "Open Inkscape's palette menu (small triangle at the "
                    "bottom-right of the color bar) to load it!")

        if (self.options.color_code_overrides or "").strip() or \
                block_data.prefs.get("color_code_overrides"):
            block_data.prefs["color_code_overrides"] = \
                self.options.color_code_overrides

        scrape_canvas = action not in ("clear_colors", "sample_image",
                                       "quantize")
        core.refresh_layer(g, block_data, scrape=scrape_canvas)


if __name__ == "__main__":
    CustomColoursPlugin().run()
