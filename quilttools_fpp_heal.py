#!/usr/bin/env python3
import re

import inkex
from lxml import etree

import quilttools_fpp_core as core


class HealGuidesPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="merge_selected")
        pars.add_argument("--preserve_guides", type=inkex.Boolean, default=True)
        pars.add_argument("--absorb_pieces", type=inkex.Boolean, default=False)
        pars.add_argument("--guide_color", type=str, default="#00ffff")
        pars.add_argument("--clear_guides", type=inkex.Boolean, default=True)
        pars.add_argument("--guides_new_block", type=inkex.Boolean, default=True)

    def effect(self):
        if self.options.action == "smart_heal":
            self._smart_heal()
        elif self.options.action == "merge_two":
            self._merge(mode="two")
        elif self.options.action == "merge_selected":
            self._merge(mode="selected")
        elif self.options.action == "merge_section":
            self._merge(mode="section")
        elif self.options.action == "to_guides":
            self._to_guides()
        elif self.options.action == "clear_guides":
            self._clear_guides()
        elif self.options.action == "strip_metadata":
            self._strip_metadata()

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

    def _draw_seam_guides(self, g, guide_polys):
        """Preserve healed-away piece outlines as dashed reference guides."""
        if not guide_polys:
            return
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
            # vector-effect:non-scaling-stroke freezes dash density
            path_el.set(
                "style",
                f"fill:none;stroke:{self.options.guide_color};stroke-width:2.0;stroke-dasharray:4,4;opacity:0.8;pointer-events:none;vector-effect:non-scaling-stroke;",
            )
            path_el.set("data-fpp-ignore", "true")

    def _selected_region_ids(self):
        return {
            int(el.get(core.FPP_REGION_ATTR))
            for el in self.svg.selection.values()
            if el.get(core.FPP_REGION_ATTR)
        }

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

        if self.options.preserve_guides:
            self._draw_seam_guides(g, guide_polys)

        inkex.utils.debug(msg)

    def _merge(self, mode):
        """Iterative merges (non-destructive alternative to Smart Heal's
        tree collapse): 'two' = exactly two adjacent pieces, 'selected' =
        all selected pieces (optionally absorbing bridging pieces),
        'section' = every section a selected piece belongs to collapses
        into one piece per section."""
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")
        tree = block_data.tree

        selected_ids = self._selected_region_ids()
        if not selected_ids:
            return inkex.errormsg("Please select the piece(s) to merge first.")

        if mode == "two":
            if len(selected_ids) != 2:
                return inkex.errormsg(
                    "Please select EXACTLY TWO different pieces to merge."
                )
            merge_sets = [selected_ids]
            absorb = False
        elif mode == "selected":
            if len(selected_ids) < 2:
                return inkex.errormsg(
                    "Please select at least two pieces to merge."
                )
            merge_sets = [selected_ids]
            absorb = self.options.absorb_pieces
        else:  # section
            prefixes = set()
            for nid in selected_ids:
                r = tree.regions.get(nid)
                if r is not None:
                    m = re.match(r"^([A-Za-z]+)", r.label)
                    if m:
                        prefixes.add(m.group(1).upper())
            if not prefixes:
                return inkex.errormsg(
                    "Selected pieces have no standard section letters."
                )
            merge_sets = []
            for prefix in sorted(prefixes):
                ids = {
                    r.id
                    for r in tree.leaf_regions()
                    if re.match(r"^([A-Za-z]+)", r.label)
                    and re.match(r"^([A-Za-z]+)", r.label).group(1).upper() == prefix
                }
                if len(ids) >= 2:
                    merge_sets.append(ids)
            if not merge_sets:
                return inkex.errormsg(
                    "The selected section(s) are already single pieces."
                )
            absorb = False

        messages, all_guides, merged_any = [], [], False
        for ids in merge_sets:
            ok, msg, guide_polys = tree.merge_leaf_set(ids, absorb=absorb)
            messages.append(msg)
            if ok:
                merged_any = True
                all_guides.extend(guide_polys)

        if not merged_any:
            return inkex.errormsg("Merge failed: " + " ".join(messages))

        tree.rebuild_alphabet()
        core.refresh_layer(g, block_data)

        if self.options.preserve_guides:
            self._draw_seam_guides(g, all_guides)

        inkex.utils.debug(" ".join(messages))

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

    def _strip_metadata(self):
        fpp_groups = []
        for g in self.svg.findall(f".//{{{core.SVG_NS}}}g"):
            desc = g.find(f"{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
            if desc is not None:
                fpp_groups.append((g, desc))

        if not fpp_groups:
            return inkex.errormsg("No Quilt Tools FPP blocks found in this document.")

        for g, desc in fpp_groups:
            # 1. Remove the desc metadata tag
            g.remove(desc)

            # 2. Clean up group attributes (ID and Inkscape layer label)
            g.set("id", f"plain-paths-{g.get('id', 'block')}")
            label = g.get(f"{{{core.INKSCAPE_NS}}}label")
            if label:
                g.set(f"{{{core.INKSCAPE_NS}}}label", f"{label} (Plain Paths)")

            # 3. Iterate through all child elements and remove data-fpp-region-id attributes
            for el in g.iter():
                if el.get(core.FPP_REGION_ATTR) is not None:
                    del el.attrib[core.FPP_REGION_ATTR]

        inkex.utils.debug(
            f"Successfully stripped Quilt Tools metadata from {len(fpp_groups)} block(s). They are now plain paths."
        )


if __name__ == "__main__":
    HealGuidesPlugin().run()
