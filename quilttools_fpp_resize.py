#!/usr/bin/env python3
import inkex
import quilttools_fpp_core as core


class ResizePlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="resize")
        pars.add_argument("--new_w_in", type=float, default=12.0)
        pars.add_argument("--new_h_in", type=float, default=12.0)
        pars.add_argument("--mirror_bg", type=inkex.Boolean, default=True)
        # Crop-to-shape options
        pars.add_argument("--crop_min_area", type=float, default=0.05)
        pars.add_argument("--crop_relabel", type=inkex.Boolean, default=True)
        pars.add_argument("--crop_remove_rect", type=inkex.Boolean, default=True)

    def effect(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        action = self.options.action
        if action == "mirror":
            return self._mirror(g, block_data)
        if action == "crop":
            return self._crop(g, block_data)
        return self._resize(g, block_data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _block_bounds(self, block_data):
        all_pts = [p for r in block_data.tree.leaf_regions() for p in r.polygon]
        if not all_pts:
            return None
        return (
            min(p[0] for p in all_pts),
            min(p[1] for p in all_pts),
            max(p[0] for p in all_pts),
            max(p[1] for p in all_pts),
        )

    def _set_page(self, min_x, min_y, w_px, h_px):
        """Resize the underlying Inkscape page/viewBox to the given local rect."""
        self.svg.set("width", f"{w_px}")
        self.svg.set("height", f"{h_px}")
        self.svg.set("viewBox", f"{min_x} {min_y} {w_px} {h_px}")

        namedview = self.svg.find(f".//{{{core.SODIPODI_NS}}}namedview")
        if namedview is not None:
            pages = namedview.findall(f"{{{core.INKSCAPE_NS}}}page")
            if pages:
                first_page = pages[0]
                first_page.set("x", str(min_x))
                first_page.set("y", str(min_y))
                first_page.set("width", str(w_px))
                first_page.set("height", str(h_px))

    # ------------------------------------------------------------------
    # MIRROR
    # ------------------------------------------------------------------
    def _mirror(self, g, block_data):
        bounds = self._block_bounds(block_data)
        if bounds is None:
            return inkex.errormsg("Block is empty.")
        min_x, _, max_x, _ = bounds
        cx = (min_x + max_x) / 2.0

        core.mirror_block_geometry(block_data)

        if self.options.mirror_bg:
            layer = self.svg.get_current_layer()
            t_mirror = inkex.Transform(
                f"translate({cx}, 0) scale(-1, 1) translate({-cx}, 0)"
            )
            for child in layer:
                if child.get("id") not in ("fpp-quilttools-layer", "fpp-layout-layer"):
                    child.transform = t_mirror @ child.transform

        core.refresh_layer(g, block_data)
        inkex.utils.debug("Block geometry successfully mirrored horizontally!")

    # ------------------------------------------------------------------
    # RESIZE / STRETCH  (unchanged behaviour)
    # ------------------------------------------------------------------
    def _resize(self, g, block_data):
        bounds = self._block_bounds(block_data)
        if bounds is None:
            return inkex.errormsg("Block is empty.")
        min_x, min_y, max_x, max_y = bounds

        old_w = max_x - min_x
        old_h = max_y - min_y
        if old_w <= 0.001 or old_h <= 0.001:
            return inkex.errormsg("Invalid block dimensions.")

        new_w_px = self.options.new_w_in * core.PX_PER_INCH
        new_h_px = self.options.new_h_in * core.PX_PER_INCH
        scale_x = new_w_px / old_w
        scale_y = new_h_px / old_h

        for r_id, region in block_data.tree.regions.items():
            scaled_poly = []
            for p in region.polygon:
                nx = min_x + (p[0] - min_x) * scale_x
                ny = min_y + (p[1] - min_y) * scale_y
                scaled_poly.append((nx, ny))
            region.polygon = scaled_poly

        core.refresh_layer(g, block_data)
        self._set_page(min_x, min_y, new_w_px, new_h_px)

        inkex.utils.debug(
            f'Block and Page successfully resized to {self.options.new_w_in}" x {self.options.new_h_in}"!'
        )

    # ------------------------------------------------------------------
    # CROP TO SHAPE
    # ------------------------------------------------------------------
    def _read_crop_box(self, g):
        """Read a selected rectangle (or 4-point path) and return its
        axis-aligned bounds in the FPP block's LOCAL coordinate space, plus
        the element itself (so the caller can delete it)."""
        inv = -g.composed_transform()

        candidates = [
            el
            for el in self.svg.selection.values()
            if not el.get(core.FPP_REGION_ATTR)
        ]
        for el in candidates:
            tag = el.tag.split("}")[-1]
            try:
                xf = el.composed_transform().apply_to_point
            except Exception:
                xf = lambda v: inkex.Vector2d(v.x, v.y)

            corners = []
            if tag == "rect":
                x = float(el.get("x", 0))
                y = float(el.get("y", 0))
                w = float(el.get("width", 0))
                h = float(el.get("height", 0))
                if w <= 0 or h <= 0:
                    continue
                corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            elif tag in ("path", "polygon", "polyline"):
                try:
                    sp = el.path.to_superpath()
                    corners = [(seg[1][0], seg[1][1]) for sub in sp for seg in sub]
                except Exception:
                    corners = []
            if len(corners) < 3:
                continue

            local = []
            for cx, cy in corners:
                gpt = xf(inkex.Vector2d(cx, cy))
                lpt = inv.apply_to_point(gpt)
                local.append((lpt.x, lpt.y))

            x0 = min(p[0] for p in local)
            y0 = min(p[1] for p in local)
            x1 = max(p[0] for p in local)
            y1 = max(p[1] for p in local)
            if (x1 - x0) < 1.0 or (y1 - y0) < 1.0:
                continue
            return (x0, y0, x1, y1), el

        return None, None

    def _crop(self, g, block_data):
        box, rect_el = self._read_crop_box(g)
        if box is None:
            return inkex.errormsg(
                "Crop to Shape: draw a rectangle over the block and select it, "
                "then run this action. (No rectangle was found in the selection.)"
            )

        x0, y0, x1, y1 = box
        report = block_data.tree.crop_to_box(
            x0,
            y0,
            x1,
            y1,
            min_area_sq_in=self.options.crop_min_area,
            relabel_on_crop=self.options.crop_relabel,
        )

        if report.get("mode") == "empty":
            return inkex.errormsg("Crop failed: the block is empty.")

        if self.options.crop_remove_rect and rect_el is not None:
            parent = rect_el.getparent()
            if parent is not None:
                parent.remove(rect_el)

        core.refresh_layer(g, block_data)

        w_px = x1 - x0
        h_px = y1 - y0
        self._set_page(x0, y0, w_px, h_px)

        w_in = w_px / core.PX_PER_INCH
        h_in = h_px / core.PX_PER_INCH
        if report["mode"] == "grow":
            inkex.utils.debug(
                f'Block grown to {w_in:.2f}" x {h_in:.2f}". '
                f'Added {report["spacing"]} spacing piece(s) around the edge. '
                "Existing pieces and labels were left untouched."
            )
        else:
            extra = (
                f' Added {report["spacing"]} spacing piece(s).'
                if report["spacing"]
                else ""
            )
            inkex.utils.debug(
                f'Block cropped to {w_in:.2f}" x {h_in:.2f}". '
                f'Removed {report["removed"]} piece(s), reshaped {report["reshaped"]}.'
                + extra
            )


if __name__ == "__main__":
    ResizePlugin().run()
