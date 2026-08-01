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
        pars.add_argument("--toggle_bypass", type=inkex.Boolean, default=False)
        pars.add_argument("--block_kind", type=str, default="fpp")
        pars.add_argument("--bg_color", type=str, default="#ffffff")
        pars.add_argument("--color_mode", type=str, default="piece")
        pars.add_argument("--show_sa", type=inkex.Boolean, default=False)
        pars.add_argument("--sa_in", type=float, default=0.25)
        pars.add_argument("--fill_opacity", type=float, default=1.0)
        pars.add_argument("--group_by_color", type=inkex.Boolean, default=False)
        # Legacy args kept so stale saved dialog values never error.
        pars.add_argument("--action", type=str, default="refresh_only")
        pars.add_argument("--bypass_custom_colors", type=inkex.Boolean,
                          default=False)
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

        # One-click bypass toggle: when ticked, ONLY flip the stored
        # bypass state and redraw - every other input is ignored.
        # scrape=False in both directions so the default-palette canvas
        # can never overwrite saved custom colours on the way back.
        if self.options.toggle_bypass:
            new_state = not bool(
                block_data.prefs.get("bypass_custom_colors", False))
            block_data.prefs["bypass_custom_colors"] = new_state
            core.refresh_layer(g, block_data, scrape=False)
            inkex.utils.debug(
                "Temporary bypass is now %s - showing %s. (Display only: "
                "the block's saved colours are untouched.)" % (
                    "ON" if new_state else "OFF",
                    "the default palette" if new_state
                    else "your custom colours"))
            return

        block_data.prefs["block_kind"] = self.options.block_kind
        bg_col = self.options.bg_color.strip()
        if bg_col.startswith("#"):
            block_data.prefs["bg_color"] = bg_col
        elif bg_col:
            block_data.prefs["bg_color"] = "#" + bg_col.lstrip("#")
        block_data.prefs["color_mode"] = self.options.color_mode
        block_data.prefs["show_sa"] = self.options.show_sa
        block_data.prefs["sa_in"] = self.options.sa_in
        block_data.prefs["group_by_color"] = self.options.group_by_color
        block_data.prefs["fill_opacity"] = self.options.fill_opacity
        # bypass_custom_colors is ONLY changed via the one-click toggle.
        core.refresh_layer(g, block_data, scrape=True)


if __name__ == "__main__":
    DisplayPlugin().run()
