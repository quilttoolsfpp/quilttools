#!/usr/bin/env python3
import math
import inkex
from lxml import etree

import quilttools_fpp_core as core

class ShapeCutPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="shape_cut")
        pars.add_argument("--min_piece_area", type=float, default=0.25)
        pars.add_argument("--subdivisions", type=int, default=32)

    def effect(self):
        self._shape_cut()

    def _shape_cut(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")
        tree = block_data.tree

        selected = list(self.svg.selection.values())
        region_el = next((el for el in selected if el.get(core.FPP_REGION_ATTR)), None)
        shape_elements = [el for el in selected if not el.get(core.FPP_REGION_ATTR)]

        if not shape_elements:
            # Auto-detect circle shape in the document if none is selected
            cands = [
                el
                for tag in ("circle", "ellipse", "path")
                for el in self.svg.findall(f".//{{{core.SVG_NS}}}{tag}")
                if not el.get(core.FPP_REGION_ATTR)
                and not el.get("data-fpp-ignore")
                and not el.get("id", "").startswith(("sa-", "region-"))
            ]
            if cands:
                shape_elements = [cands[-1]]

        if not shape_elements:
            return inkex.errormsg("No shape selected. Please draw or select a circle to cut with.")

        inv_transform = -g.composed_transform()
        man_id = (
            int(region_el.get(core.FPP_REGION_ATTR)) if region_el is not None else None
        )

        total_cuts = 0
        for shape_el in shape_elements:
            try:
                xf_func = shape_el.composed_transform().apply_to_point
            except:
                xf_func = lambda x: inkex.Vector2d(x.x, x.y)

            tag = shape_el.tag.split("}")[-1]
            is_circle = False

            # Check if it has sodipodi arc attributes (very common for Inkscape circles)
            sodipodi_type = shape_el.get(f"{{{core.SODIPODI_NS}}}type")
            if sodipodi_type == "arc" or tag in ("circle", "ellipse"):
                is_circle = True

            if is_circle:
                cx, cy, r = None, None, None
                if sodipodi_type == "arc":
                    try:
                        cx = float(shape_el.get(f"{{{core.SODIPODI_NS}}}cx", 0))
                        cy = float(shape_el.get(f"{{{core.SODIPODI_NS}}}cy", 0))
                        r = float(shape_el.get(f"{{{core.SODIPODI_NS}}}rx", 0))
                    except (ValueError, TypeError):
                        pass

                if cx is None or cy is None or r is None:
                    if tag == "circle":
                        try:
                            cx = float(shape_el.get("cx", 0))
                            cy = float(shape_el.get("cy", 0))
                            r = float(shape_el.get("r", 0))
                        except (ValueError, TypeError):
                            pass
                    elif tag == "ellipse":
                        try:
                            cx = float(shape_el.get("cx", 0))
                            cy = float(shape_el.get("cy", 0))
                            r = float(shape_el.get("rx", 0))
                        except (ValueError, TypeError):
                            pass

                if cx is None or cy is None or r is None:
                    # Estimate center and radius from bounding box
                    try:
                        bbox = shape_el.bounding_box()
                        if bbox and bbox.width > 0:
                            cx = bbox.center.x
                            cy = bbox.center.y
                            r = bbox.width / 2.0
                    except Exception:
                        continue

                if cx is None or cy is None or r is None:
                    continue

                # Transform circle properties to FPP group local space
                p_center = inkex.Vector2d(cx, cy)
                p_edge = inkex.Vector2d(cx + r, cy)

                g_center = xf_func(p_center)
                g_edge = xf_func(p_edge)

                local_center_v = inv_transform.apply_to_point(g_center)
                local_edge_v = inv_transform.apply_to_point(g_edge)

                local_center = (local_center_v.x, local_center_v.y)
                local_radius = math.hypot(local_edge_v.x - local_center_v.x, local_edge_v.y - local_center_v.y)

                try:
                    cuts = tree.multi_circle_cut(
                        local_center, local_radius, man_id, self.options.subdivisions
                    )
                    total_cuts += cuts
                    if cuts > 0 and shape_el.getparent() is not None:
                        shape_el.getparent().remove(shape_el)
                except ValueError:
                    pass
            else:
                # General Path/Curve logic
                path_d = shape_el.get("d")
                if not path_d:
                    continue

                path_obj = inkex.Path(path_d)
                sp = path_obj.to_superpath()
                inkex.bezier.cspsubdiv(sp, 0.5)
                curve_points = [(seg[1][0], seg[1][1]) for sub in sp for seg in sub]

                local_points = []
                for px, py in curve_points:
                    gp = xf_func(inkex.Vector2d(px, py))
                    local_gp = inv_transform.apply_to_point(gp)
                    local_points.append((local_gp.x, local_gp.y))

                try:
                    cuts = tree.multi_path_cut(local_points, man_id)
                    total_cuts += cuts
                    if cuts > 0 and shape_el.getparent() is not None:
                        shape_el.getparent().remove(shape_el)
                except ValueError:
                    pass

        if total_cuts == 0:
            return inkex.errormsg(
                "Shape Cut failed: The shape did not intersect any cuttable regions at exactly 2 points."
            )

        core.refresh_layer(g, block_data)
        warning_msg = ""
        min_sq_in = self.options.min_piece_area
        for region in tree.leaf_regions():
            if region.area_sq_in() < min_sq_in:
                warning_msg += f"\nWARNING: Piece {region.label} is only {region.area_sq_in():.2f} sq in!"

        inkex.utils.debug(f"Success! {total_cuts} region(s) were split using Shape Cut.{warning_msg}")

if __name__ == "__main__":
    ShapeCutPlugin().run()
