#!/usr/bin/env python3
"""03b. Quick Save Colours (Quilt Tools Colour) - one-click, keybindable
save of the canvas paint into the block's permanent colour memory.
BLOCKS ONLY."""
import inkex
import quilttools_fpp_core as core
import quilttools_colour as qcol

class SaveColorsPlugin(inkex.Effect):
    def effect(self):
        ctx = qcol.detect_context(self.svg)
        if ctx["block_g"] is None:
            key = "need_block" if ctx["kind"] == "quilt" else "need_any"
            return inkex.errormsg(qcol.CONTEXT_HELP[key])
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg(qcol.CONTEXT_HELP["need_block"])

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
            f"Quick-saved {count} canvas colour(s) into the block. "
            + qcol.context_note(ctx, "block"))

if __name__ == "__main__":
    SaveColorsPlugin().run()
