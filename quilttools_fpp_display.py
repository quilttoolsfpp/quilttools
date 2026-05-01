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
                    style = path.get("style", "")
                    # Regex to find hex codes or named colors
                    m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", style)
                    if m:
                        user_colors[str(rid)] = m.group(1)

            block_data.prefs["custom_colors"] = user_colors
            inkex.utils.debug(
                f"Saved {len(user_colors)} custom colors into permanent block memory!"
            )

        elif self.options.action == "clear_colors":
            block_data.prefs["custom_colors"] = {}
            inkex.utils.debug(
                "Cleared custom colors. Reverting to default algorithmic palette."
            )

        # Update Display Preferences
        block_data.prefs["color_mode"] = self.options.color_mode
        block_data.prefs["show_sa"] = self.options.show_sa
        block_data.prefs["sa_in"] = self.options.sa_in

        # Trigger a full mathematical redraw to apply new settings
        core.refresh_layer(g, block_data)


if __name__ == "__main__":
    DisplayPlugin().run()
