#!/usr/bin/env python3
import inkex
import quilttools_fpp_core as core


class ResizePlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--new_w_in", type=float, default=12.0)
        pars.add_argument("--new_h_in", type=float, default=12.0)

    def effect(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        tree = block_data.tree
        all_pts = [p for r in tree.leaf_regions() for p in r.polygon]
        if not all_pts:
            return inkex.errormsg("Block is empty.")

        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)

        old_w = max_x - min_x
        old_h = max_y - min_y

        if old_w <= 0.001 or old_h <= 0.001:
            return inkex.errormsg("Invalid block dimensions.")

        new_w_px = self.options.new_w_in * core.PX_PER_INCH
        new_h_px = self.options.new_h_in * core.PX_PER_INCH

        scale_x = new_w_px / old_w
        scale_y = new_h_px / old_h

        for r_id, region in tree.regions.items():
            scaled_poly = []
            for p in region.polygon:
                nx = min_x + (p[0] - min_x) * scale_x
                ny = min_y + (p[1] - min_y) * scale_y
                scaled_poly.append((nx, ny))
            region.polygon = scaled_poly

        core.refresh_layer(g, block_data)

        # --- NEW: Resize the underlying Inkscape page ---
        self.svg.set("width", f"{new_w_px}")
        self.svg.set("height", f"{new_h_px}")
        self.svg.set("viewBox", f"{min_x} {min_y} {new_w_px} {new_h_px}")

        # Update Native Inkscape Pages if they exist (Inkscape 1.2+)
        namedview = self.svg.find(f".//{{{core.SODIPODI_NS}}}namedview")
        if namedview is not None:
            pages = namedview.findall(f"{{{core.INKSCAPE_NS}}}page")
            if pages:
                # Update the very first page to perfectly frame the resized block
                first_page = pages[0]
                first_page.set("x", str(min_x))
                first_page.set("y", str(min_y))
                first_page.set("width", str(new_w_px))
                first_page.set("height", str(new_h_px))

        inkex.utils.debug(
            f'Block and Page successfully resized to {self.options.new_w_in}" x {self.options.new_h_in}"!'
        )


if __name__ == "__main__":
    ResizePlugin().run()
