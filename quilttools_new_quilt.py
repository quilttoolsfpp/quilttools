#!/usr/bin/env python3
import inkex
from lxml import etree
import quilttools_fpp_core as core
import quilttools_theme as qtheme
import quilttools_quilt_core as qcore

class NewQuiltPlugin(inkex.Effect):
    def add_arguments(self, pars):
        # Notebook tabs arguments
        pars.add_argument("--notebook", type=str, default="grid_page")
        pars.add_argument("--quilt_name", type=str, default="My New Quilt")
        pars.add_argument("--grid_rows", type=int, default=4)
        pars.add_argument("--grid_cols", type=int, default=4)
        pars.add_argument("--cell_w_in", type=float, default=12.0)
        pars.add_argument("--cell_h_in", type=float, default=12.0)
        pars.add_argument("--sashing_w_in", type=float, default=0.0)
        pars.add_argument("--cornerstones", type=inkex.Boolean, default=False)
        pars.add_argument("--border_1_in", type=float, default=0.0)
        pars.add_argument("--border_2_in", type=float, default=0.0)
        pars.add_argument("--border_3_in", type=float, default=0.0)
        pars.add_argument("--binding_w_in", type=float, default=0.25)
        pars.add_argument("--resize_page", type=inkex.Boolean, default=True)
        pars.add_argument("--theme_override", type=str, default="")

    def effect(self):
        # Resolve active theme
        theme = qtheme.resolve_active_theme(self.options)
        
        # Erase existing Quilt Layout layer if it exists to prevent stacking
        for layer in list(self.svg.findall(f".//{{{core.SVG_NS}}}g")):
            if (layer.get(f"{{{core.INKSCAPE_NS}}}label") == "Quilt Layout" or 
                layer.get("id") == "quilttools-quilt-layer"):
                layer.getparent().remove(layer)

        # Build borders list
        borders = []
        if self.options.border_1_in > 0:
            borders.append({"width_in": self.options.border_1_in, "color_ref": "border1"})
        if self.options.border_2_in > 0:
            borders.append({"width_in": self.options.border_2_in, "color_ref": "border2"})
        if self.options.border_3_in > 0:
            borders.append({"width_in": self.options.border_3_in, "color_ref": "border3"})

        # Initialize quilt data
        spec = {
            "name": self.options.quilt_name,
            "setting": "straight",
            "grid": {
                "rows": self.options.grid_rows,
                "cols": self.options.grid_cols,
                "cell_w_in": self.options.cell_w_in,
                "cell_h_in": self.options.cell_h_in
            },
            "sashing": {
                "width_in": self.options.sashing_w_in,
                "cornerstones": self.options.cornerstones if self.options.sashing_w_in > 0 else False,
                "color_ref": "sashing"
            },
            "borders": borders,
            "binding": {
                "width_in": self.options.binding_w_in,
                "color_ref": "binding"
            }
        }
        
        quilt_data = qcore.QuiltData(spec)
        g_quilt = qcore.build_quilt_layer(quilt_data, theme)
        self.svg.append(g_quilt)

        # Resize page if requested
        if self.options.resize_page:
            # Re-read dimensions from finished quilt_data
            quilt_w_px = quilt_data.finished_width_in * core.PX_PER_INCH
            quilt_h_px = quilt_data.finished_height_in * core.PX_PER_INCH
            self.svg.set('width', f"{quilt_w_px}px")
            self.svg.set('height', f"{quilt_h_px}px")
            self.svg.set('viewBox', f"0 0 {quilt_w_px} {quilt_h_px}")

        inkex.utils.debug(f"New Quilt created: {quilt_data.finished_width_in:.2f}\" x {quilt_data.finished_height_in:.2f}\" with {self.options.grid_rows}x{self.options.grid_cols} grid.")

if __name__ == "__main__":
    NewQuiltPlugin().run()
