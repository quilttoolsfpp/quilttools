#!/usr/bin/env python3
import inkex
from lxml import etree
import quilttools_fpp_core as core

class NewBlockPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--use_page_size", type=inkex.Boolean, default=False)
        pars.add_argument("--block_w_in", type=float, default=6.0)
        pars.add_argument("--block_h_in", type=float, default=6.0)
        pars.add_argument("--resize_page", type=inkex.Boolean, default=False)
        pars.add_argument("--scale_mode", type=str, default="none")
        pars.add_argument("--grid_rows", type=int, default=1)
        pars.add_argument("--grid_cols", type=int, default=1)

    def effect(self):
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
        rows, cols = self.options.grid_rows, self.options.grid_cols
        for i in range(1, rows):
            y = i * (h / rows)
            tree.multi_guillotine_cut(core.pt(-10, y), core.pt(w+10, y), angle_snap_deg=None, is_boundary=True)
        for j in range(1, cols):
            x = j * (w / cols)
            tree.multi_guillotine_cut(core.pt(x, -10), core.pt(x, h+10), angle_snap_deg=None, is_boundary=True)

        block_data = core.BlockData(tree)
        g = core.build_fpp_layer(block_data)
        self.svg.get_current_layer().append(g)
        inkex.utils.debug(f"New Block created: {w/core.PX_PER_INCH:.2f}\" x {h/core.PX_PER_INCH:.2f}\" with {rows}x{cols} grid.")

if __name__ == "__main__":
    NewBlockPlugin().run()
