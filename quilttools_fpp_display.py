#!/usr/bin/env python3
"""05. FPP Display Toggle (Quilt Tools Block).

NON-DESTRUCTIVE display switches for block drafting: the one-click
temporary bypass of custom colours, the default palette view
(rainbow-per-piece vs section colours), seam-allowance preview and
fabric-colour grouping. Nothing here changes the block's saved colours -
the permanent colour actions live in Quilt Tools Colour > 03. Custom
Block Colours.
"""
import inkex

import quilttools_fpp_core as core


class DisplayPlugin(inkex.Effect):
    def add_arguments(self, pars):
        # Streamlined mode: by default alternates between block colour and section overlay
        pars.add_argument("--mode", type=str, default="toggle",
                          choices=["toggle", "block", "section"])
        # Legacy args kept so any existing saved parameters never error
        pars.add_argument("--toggle_bypass", type=inkex.Boolean, default=False)
        pars.add_argument("--block_kind", type=str, default="fpp")
        pars.add_argument("--bg_color", type=str, default="#ffffff")
        pars.add_argument("--color_mode", type=str, default="section")
        pars.add_argument("--show_sa", type=inkex.Boolean, default=False)
        pars.add_argument("--sa_in", type=float, default=0.25)
        pars.add_argument("--fill_opacity", type=float, default=1.0)
        pars.add_argument("--group_by_color", type=inkex.Boolean, default=False)
        pars.add_argument("--action", type=str, default="toggle")
        pars.add_argument("--bypass_custom_colors", type=inkex.Boolean, default=False)
        pars.add_argument("--quantize_n", type=int, default=6)
        pars.add_argument("--locked_colors", type=str, default="")
        pars.add_argument("--color_code_overrides", type=str, default="")

    def effect(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg(
                "No Quilt Tools FPP block found on this canvas.\n"
                "(This is a block drafting aid - quilt layouts are "
                "recoloured via the Quilt Tools Colour menu.)")

        is_currently_overlay = bool(
            block_data.prefs.get("bypass_custom_colors", False)
        )

        mode = getattr(self.options, "mode", "toggle")
        if mode == "block":
            switch_to_overlay = False
        elif mode == "section":
            switch_to_overlay = True
        else:  # toggle
            switch_to_overlay = not is_currently_overlay

        if switch_to_overlay:
            # Switching from Block Colours to Section Overlay:
            # 1. Scrape any canvas custom colours painted by the user so they are saved
            custom_colors = block_data.prefs.setdefault("custom_colors", {})
            for path in g.findall(f".//{{{core.SVG_NS}}}path"):
                rid = path.get(core.FPP_REGION_ATTR)
                if rid:
                    col = core.resolve_element_fill(path)
                    if col:
                        custom_colors[str(rid)] = col

            # 2. Activate section overlay mode
            block_data.prefs["color_mode"] = "section"
            block_data.prefs["bypass_custom_colors"] = True
            core.refresh_layer(g, block_data, scrape=False)
            inkex.utils.debug(
                "FPP Display: Section Overlay ON (Coloured by Section A, B, C...).\n"
                "Run FPP Display Toggle again to return to Block Colours."
            )
        else:
            # Switching from Section Overlay back to Block Colours:
            block_data.prefs["bypass_custom_colors"] = False
            core.refresh_layer(g, block_data, scrape=False)
            inkex.utils.debug(
                "FPP Display: Block Colours ON (Showing Saved Block Palette).\n"
                "Run FPP Display Toggle again to switch to Section Overlay."
            )


if __name__ == "__main__":
    DisplayPlugin().run()

