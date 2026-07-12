#!/usr/bin/env python3
import inkex
import quilttools_fpp_core as core

class SaveColorsPlugin(inkex.Effect):
    def effect(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        # Scrape colors directly from the Inkscape paths
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
        
        # Trigger redraw and save to block metadata tag
        core.refresh_layer(g, block_data)
        
        inkex.utils.debug(
            f"Successfully scraped and saved {count} canvas colors to the block metadata!"
        )

if __name__ == "__main__":
    SaveColorsPlugin().run()
