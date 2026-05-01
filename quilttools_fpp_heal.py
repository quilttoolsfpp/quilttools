#!/usr/bin/env python3
import inkex
from lxml import etree

import quilttools_fpp_core as core


class HealGuidesPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="smart_heal")
        pars.add_argument("--preserve_guides", type=inkex.Boolean, default=True)
        pars.add_argument("--guide_color", type=str, default="#00ffff")
        pars.add_argument("--clear_guides", type=inkex.Boolean, default=True)
        pars.add_argument("--guides_new_block", type=inkex.Boolean, default=True)

    def effect(self):
        if self.options.action == "smart_heal":
            self._smart_heal()
        elif self.options.action == "to_guides":
            self._to_guides()
        elif self.options.action == "clear_guides":
            self._clear_guides()

    def _clear_guides(self):
        guides_removed = 0

        # 1. Annihilate Native Inkscape Guides
        namedview = self.svg.find(f".//{{{core.SODIPODI_NS}}}namedview")
        if namedview is not None:
            for guide in namedview.findall(f"{{{core.SODIPODI_NS}}}guide"):
                namedview.remove(guide)
                guides_removed += 1

        # 2. Annihilate Custom Drawn Guide/Grid Layers
        for layer in self.svg.findall(f".//{{{core.SVG_NS}}}g"):
            label = layer.get(f"{{{core.INKSCAPE_NS}}}label", "").lower()
            if "guide" in label or "grid" in label:
                if layer.getparent() is not None:
                    layer.getparent().remove(layer)
                    guides_removed += 1

        if guides_removed > 0:
            inkex.utils.debug(
                "Workspace cleared. All guides and grids have been removed."
            )
        else:
            inkex.utils.debug("Workspace is already clean. No guides found.")

    def _clear_all_guide_layers(self):
        """Obliterates all layers labeled as FPP Guides to prevent ghost duplicates."""
        for g in self.svg.findall(f".//{{{core.SVG_NS}}}g"):
            # Inkscape silently renames duplicate IDs, so we target the label instead!
            if g.get(f"{{{core.INKSCAPE_NS}}}label") == "FPP Guides" or str(
                g.get("id", "")
            ).startswith("fpp-guides-layer"):
                if g.getparent() is not None:
                    g.getparent().remove(g)

    def _get_global_guide_layer(self, parent, transform_attr):
        """Finds the single global guide layer or creates it if it doesn't exist."""
        guide_layer = None
        for g in self.svg.findall(f".//{{{core.SVG_NS}}}g"):
            if g.get(f"{{{core.INKSCAPE_NS}}}label") == "FPP Guides":
                guide_layer = g
                break

        if guide_layer is None:
            guide_layer = etree.Element(
                "{%s}g" % core.SVG_NS,
                id="fpp-guides-layer",
                **{
                    f"{{{core.INKSCAPE_NS}}}label": "FPP Guides",
                    f"{{{core.INKSCAPE_NS}}}groupmode": "layer",
                },
            )
            if transform_attr:
                guide_layer.set("transform", transform_attr)

        # Always pop the global guide layer to the absolute top of the parent stack
        if guide_layer.getparent() is not None:
            guide_layer.getparent().remove(guide_layer)
        parent.append(guide_layer)

        return guide_layer

    def _smart_heal(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        selected_els = [
            el for el in self.svg.selection.values() if el.get(core.FPP_REGION_ATTR)
        ]
        if len(selected_els) < 2:
            return inkex.errormsg(
                "Please select at least two pieces to trigger a Smart Heal."
            )

        selected_ids = {int(el.get(core.FPP_REGION_ATTR)) for el in selected_els}

        success, msg, guide_polys = block_data.tree.smart_heal_regions(selected_ids)
        if not success:
            return inkex.errormsg(f"Smart Heal failed: {msg}")

        block_data.tree.rebuild_alphabet()
        core.refresh_layer(g, block_data)

        if self.options.preserve_guides and guide_polys:
            parent = g.getparent()
            guide_layer = self._get_global_guide_layer(parent, g.get("transform"))

            for poly in guide_polys:
                path_d = (
                    "M {:.4f},{:.4f} ".format(*poly[0])
                    + " ".join("L {:.4f},{:.4f}".format(*p) for p in poly[1:])
                    + " Z"
                )
                path_el = etree.SubElement(guide_layer, "{%s}path" % core.SVG_NS)
                path_el.set("d", path_d)
                # Added vector-effect:non-scaling-stroke to freeze dash density
                path_el.set(
                    "style",
                    f"fill:none;stroke:{self.options.guide_color};stroke-width:2.0;stroke-dasharray:4,4;opacity:0.8;pointer-events:none;vector-effect:non-scaling-stroke;",
                )
                path_el.set("data-fpp-ignore", "true")

        inkex.utils.debug(msg)

    def _to_guides(self):
        if self.options.clear_guides:
            self._clear_all_guide_layers()

        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        parent = g.getparent()
        guide_layer = self._get_global_guide_layer(parent, g.get("transform"))

        for region in block_data.tree.leaf_regions():
            path_el = etree.SubElement(guide_layer, "{%s}path" % core.SVG_NS)
            path_el.set("d", region.path_d())
            # Added vector-effect:non-scaling-stroke here too
            path_el.set(
                "style",
                f"fill:none;stroke:{self.options.guide_color};stroke-width:1.0;stroke-opacity:0.6;pointer-events:none;vector-effect:non-scaling-stroke;",
            )
            path_el.set("data-fpp-ignore", "true")

        msg = "Converted block to guides."
        if self.options.guides_new_block:
            block_data.tree.reset_to_boundaries()
            new_g = core.build_fpp_layer(block_data)
            parent.append(new_g)
            msg += " A fresh block matching your original grid was generated."

        # Re-append guides LAST so they definitively render on top of the fresh block
        if guide_layer.getparent() is not None:
            guide_layer.getparent().remove(guide_layer)
        parent.append(guide_layer)

        if g.getparent() is not None:
            g.getparent().remove(g)

        inkex.utils.debug(msg)


if __name__ == "__main__":
    HealGuidesPlugin().run()
