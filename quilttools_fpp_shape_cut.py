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
        pars.add_argument("--allow_y_seams", type=inkex.Boolean, default=False)

    def effect(self):
        self._shape_cut()

    def _shape_cut(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")
        tree = block_data.tree

        # Save original JSON string and Y-seam status for rollback
        desc = g.find(f"{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
        original_json = desc.text
        _, warn_before = core.calculate_section_sewing_order(block_data)
        leaf_ids_before = [r.id for r in tree.leaf_regions()]
        is_valid_before, _ = tree.virtual_sewing_validator(leaf_ids_before)
        block_has_y_seams_before = (not is_valid_before) or warn_before
        has_curves_before = hasattr(tree, "curves") and len(tree.curves) > 0

        selected = list(self.svg.selection.values())
        region_el = next((el for el in selected if el.get(core.FPP_REGION_ATTR)), None)
        shape_elements = [el for el in selected if not el.get(core.FPP_REGION_ATTR)]

        if not shape_elements:
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
        to_delete = []
        for shape_el in shape_elements:
            try:
                xf_func = shape_el.composed_transform().apply_to_point
            except:
                xf_func = lambda x: inkex.Vector2d(x.x, x.y)

            tag = shape_el.tag.split("}")[-1]
            is_circle = False

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
                    if cuts > 0:
                        total_cuts += cuts
                        to_delete.append(shape_el)
                except ValueError:
                    pass
            else:
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
                    if cuts > 0:
                        total_cuts += cuts
                        to_delete.append(shape_el)
                except ValueError:
                    pass

        if total_cuts == 0:
            return inkex.errormsg(
                "Shape Cut failed: The shape did not intersect any cuttable regions at exactly 2 points."
            )

        # Check post-cut Y-seam and curve status
        leaf_ids_after = [r.id for r in tree.leaf_regions()]
        is_valid_after, sequence = tree.virtual_sewing_validator(leaf_ids_after)
        _, warn_after = core.calculate_section_sewing_order(block_data)
        block_has_y_seams_after = (not is_valid_after) or warn_after
        has_curves_after = hasattr(tree, "curves") and len(tree.curves) > 0
        
        introduced_y_seams = block_has_y_seams_after and not block_has_y_seams_before
        introduced_curves = has_curves_after and not has_curves_before
        
        if (introduced_y_seams or introduced_curves) and not self.options.allow_y_seams:
            desc.text = original_json
            return inkex.errormsg(
                "Shape Cut failed: This cut would introduce Y-seams or curves. "
                "Check 'Allow Y-seams / partial seams' in the options dialog if you wish to proceed anyway."
            )

        if block_has_y_seams_after or introduced_curves:
            block_data.prefs["has_y_seams"] = True
            if block_has_y_seams_after:
                unseparable_ids = set(leaf_ids_after) - set(sequence)
                for rid in unseparable_ids:
                    block_data.set_piece_meta(rid, technique="y_seam")

        # Success! Delete guide shapes
        for shape_el in to_delete:
            if shape_el.getparent() is not None:
                shape_el.getparent().remove(shape_el)

        core.refresh_layer(g, block_data)
        warning_msg = ""
        if warn_after or introduced_curves:
            warning_msg += "\nWARNING: This block now contains Y-seams or partial seams!"
            
        min_sq_in = self.options.min_piece_area
        for region in tree.leaf_regions():
            if region.area_sq_in() < min_sq_in:
                warning_msg += f"\nWARNING: Piece {region.label} is only {region.area_sq_in():.2f} sq in!"

        inkex.utils.debug(f"Success! {total_cuts} region(s) were split using Shape Cut.{warning_msg}")

if __name__ == "__main__":
    ShapeCutPlugin().run()
