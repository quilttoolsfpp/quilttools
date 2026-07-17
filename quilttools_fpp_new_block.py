#!/usr/bin/env python3
import math
import inkex
from lxml import etree
import quilttools_fpp_core as core

class NewBlockPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--use_page_size", type=inkex.Boolean, default=False)
        pars.add_argument("--use_selection_path", type=inkex.Boolean, default=False)
        pars.add_argument("--block_w_in", type=float, default=6.0)
        pars.add_argument("--block_h_in", type=float, default=6.0)
        pars.add_argument("--resize_page", type=inkex.Boolean, default=False)
        pars.add_argument("--scale_mode", type=str, default="none")
        pars.add_argument("--grid_rows", type=int, default=1)
        pars.add_argument("--grid_cols", type=int, default=1)

    def effect(self):
        if self.options.use_selection_path:
            selected = list(self.svg.selection.values())
            if not selected:
                return inkex.errormsg("Please select a closed path on the canvas to use as the block boundary.")
            path_el = selected[0]
            if path_el.tag.split("}")[-1] != "path":
                return inkex.errormsg("Selected object is not a path. Please select a path element.")
            path_d = path_el.get("d")
            if not path_d:
                return inkex.errormsg("Selected path has no shape data (d attribute is empty).")

            # Get layers and transforms
            layer = self.svg.get_current_layer()
            el_xf = path_el.composed_transform()
            layer_inv_xf = -layer.composed_transform()

            def to_layer(x, y):
                gp = el_xf.apply_to_point(inkex.Vector2d(x, y))
                lp = layer_inv_xf.apply_to_point(gp)
                return (lp[0], lp[1])

            # Tessellate the path to a closed polygon
            path_obj = inkex.Path(path_d)
            sp = path_obj.to_superpath()
            inkex.bezier.cspsubdiv(sp, 0.5)

            raw_points = [(node[1][0], node[1][1]) for sub in sp for node in sub]
            polygon_points = [to_layer(x, y) for (x, y) in raw_points]
            polygon_points = core.simplify_polygon(polygon_points)
            if len(polygon_points) < 3:
                return inkex.errormsg("Failed to initialize block: the path's outline is degenerate or not closed.")

            # Extract curve segments for boundary templates
            curves = []
            start_x, start_y = 0.0, 0.0
            prev_x, prev_y = 0.0, 0.0
            for cmd in path_obj:
                letter = cmd.letter
                if letter == 'M':
                    start_x, start_y = cmd.args[0], cmd.args[1]
                    prev_x, prev_y = start_x, start_y
                else:
                    if letter in ('C', 'S', 'Q', 'T', 'A'):
                        seg_path = inkex.Path(f"M {prev_x},{prev_y} {cmd}")
                        seg_sp = seg_path.to_superpath()
                        inkex.bezier.cspsubdiv(seg_sp, 0.5)
                        seg_pts = [to_layer(node[1][0], node[1][1]) for node in seg_sp[0]]
                        if len(seg_pts) >= 2:
                            curves.append(seg_pts)
                    if cmd.args:
                        prev_x, prev_y = cmd.args[-2], cmd.args[-1]
                    elif letter == 'Z':
                        prev_x, prev_y = start_x, start_y

            xs = [p[0] for p in polygon_points]
            ys = [p[1] for p in polygon_points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            w = max_x - min_x
            h = max_y - min_y

            if self.options.resize_page:
                bbox = path_el.bounding_box()
                if bbox and bbox.width > 0 and bbox.height > 0:
                    self.svg.set('width', f"{bbox.width}px")
                    self.svg.set('height', f"{bbox.height}px")
                    self.svg.set('viewBox', f"{bbox.left} {bbox.top} {bbox.width} {bbox.height}")

            if path_el.getparent() is not None:
                path_el.getparent().remove(path_el)

            tree = core.RegionTree(polygon_points)
            tree.curves = curves
        else:
            if self.options.use_page_size:
                w = self.svg.viewport_width if hasattr(self.svg, 'viewport_width') else self.svg.unittouu(self.svg.get('width'))
                h = self.svg.viewport_height if hasattr(self.svg, 'viewport_height') else self.svg.unittouu(self.svg.get('height'))
                if w == 0 or h == 0: w, h = self.options.block_w_in * core.PX_PER_INCH, self.options.block_h_in * core.PX_PER_INCH
            else:
                w, h = self.options.block_w_in * core.PX_PER_INCH, self.options.block_h_in * core.PX_PER_INCH

            if self.options.resize_page:
                self.svg.set('width', f"{w}px")
                self.svg.set('height', f"{h}px")
                self.svg.set('viewBox', f"0 0 {w} {h}")

            if self.options.scale_mode != "none":
                if not self.svg.selection:
                    inkex.errormsg("Note: 'Selected object scaling' is active, but no objects were selected on the canvas. Generating blank block anyway.")
                else:
                    clip_id = self.svg.get_unique_id('block_clip')
                    clip_path = etree.SubElement(self.svg.defs, "{%s}clipPath" % core.SVG_NS, id=clip_id, clipPathUnits="userSpaceOnUse")
                    etree.SubElement(clip_path, "{%s}rect" % core.SVG_NS, x="0", y="0", width=str(w), height=str(h))
                    clip_group = etree.SubElement(self.svg.get_current_layer(), "{%s}g" % core.SVG_NS)
                    clip_group.set("clip-path", f"url(#{clip_id})")

                    for el in list(self.svg.selection.values()):
                        bbox = el.bounding_box()
                        if bbox and bbox.width > 0 and bbox.height > 0:
                            scale_x, scale_y = w / bbox.width, h / bbox.height
                            if self.options.scale_mode == "fit": final_scale_x = final_scale_y = min(scale_x, scale_y)
                            elif self.options.scale_mode == "crop": final_scale_x = final_scale_y = max(scale_x, scale_y)
                            elif self.options.scale_mode == "stretch": final_scale_x, final_scale_y = scale_x, scale_y
                            else: final_scale_x = final_scale_y = 1.0

                            cx, cy = (w - (bbox.width * final_scale_x)) / 2, (h - (bbox.height * final_scale_y)) / 2
                            transform = inkex.Transform()
                            transform.add_translate(cx, cy)
                            transform.add_scale(final_scale_x, final_scale_y)
                            transform.add_translate(-bbox.left, -bbox.top)
                            el.transform = transform @ el.transform
                            clip_group.append(el)

            tree = core.RegionTree([(0,0),(w,0),(w,h),(0,h)])
            min_x, min_y = 0.0, 0.0

        rows, cols = self.options.grid_rows, self.options.grid_cols
        for i in range(1, rows):
            y = min_y + i * (h / rows)
            tree.multi_guillotine_cut(core.pt(min_x - 10, y), core.pt(max_x + 10, y), angle_snap_deg=None, is_boundary=True)
        for j in range(1, cols):
            x = min_x + j * (w / cols)
            tree.multi_guillotine_cut(core.pt(x, min_y - 10), core.pt(x, max_y + 10), angle_snap_deg=None, is_boundary=True)

        block_data = core.BlockData(tree)
        g = core.build_fpp_layer(block_data)
        self.svg.get_current_layer().append(g)
        inkex.utils.debug(f"New Block created: {w/core.PX_PER_INCH:.2f}\" x {h/core.PX_PER_INCH:.2f}\" with {rows}x{cols} grid.")

if __name__ == "__main__":
    NewBlockPlugin().run()
