#!/usr/bin/env python3
import inkex

import quilttools_fpp_core as core


class CutPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="cut")
        pars.add_argument("--mark_boundary", type=inkex.Boolean, default=False)
        pars.add_argument("--auto_cut", type=inkex.Boolean, default=True)
        pars.add_argument("--angle_snap", type=float, default=15.0)
        pars.add_argument("--min_piece_area", type=float, default=0.25)

    def effect(self):
        if self.options.action == "undo":
            self._undo()
        elif self.options.action == "heal":
            self._heal()
        else:
            self._cut()

    def _cut(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")
        tree = block_data.tree

        selected = list(self.svg.selection.values())
        region_el = next((el for el in selected if el.get(core.FPP_REGION_ATTR)), None)
        guide_elements = [el for el in selected if not el.get(core.FPP_REGION_ATTR)]

        if not guide_elements and self.options.auto_cut:
            cands = [
                el
                for tag in ("path", "line", "polyline")
                for el in self.svg.findall(f".//{{{core.SVG_NS}}}{tag}")
                if not el.get(core.FPP_REGION_ATTR)
                and not el.get("data-fpp-ignore")
                and not el.get("id", "").startswith(("sa-", "region-"))
            ]
            if cands:
                guide_elements = [cands[-1]]

        if not guide_elements:
            return inkex.errormsg("No guide line found. Please draw a line to cut.")

        inv_transform = -g.composed_transform()
        snap = self.options.angle_snap if self.options.angle_snap > 0 else None
        man_id = (
            int(region_el.get(core.FPP_REGION_ATTR)) if region_el is not None else None
        )
        is_bound = self.options.mark_boundary

        total_cuts = 0
        for guide_el in guide_elements:
            try:
                xf_func = guide_el.composed_transform().apply_to_point
            except:
                xf_func = lambda x: inkex.Vector2d(x.x, x.y)

            tag = guide_el.tag.split("}")[-1]
            if tag == "line":
                gp1 = xf_func(
                    inkex.Vector2d(
                        float(guide_el.get("x1", 0)), float(guide_el.get("y1", 0))
                    )
                )
                gp2 = xf_func(
                    inkex.Vector2d(
                        float(guide_el.get("x2", 0)), float(guide_el.get("y2", 0))
                    )
                )
            else:
                try:
                    sp = guide_el.path.to_superpath()
                    if not sp or not sp[0]:
                        continue
                    start_pt, end_pt = sp[0][0][1], sp[0][-1][1]
                    gp1, gp2 = (
                        xf_func(inkex.Vector2d(start_pt[0], start_pt[1])),
                        xf_func(inkex.Vector2d(end_pt[0], end_pt[1])),
                    )
                    if (
                        len(sp[0]) > 2
                        and core.vec_len(core.vec_sub((gp2.x, gp2.y), (gp1.x, gp1.y)))
                        < core.EPSILON
                    ):
                        end_pt = sp[0][-2][1]
                        gp2 = xf_func(inkex.Vector2d(end_pt[0], end_pt[1]))
                except Exception:
                    continue

            local_p1 = core.pt(
                inv_transform.apply_to_point(gp1).x, inv_transform.apply_to_point(gp1).y
            )
            local_p2 = core.pt(
                inv_transform.apply_to_point(gp2).x, inv_transform.apply_to_point(gp2).y
            )

            try:
                cuts = tree.multi_guillotine_cut(
                    local_p1, local_p2, snap, man_id, is_bound
                )
                total_cuts += cuts
                if cuts > 0 and guide_el.getparent() is not None:
                    guide_el.getparent().remove(guide_el)
            except ValueError:
                pass

        if total_cuts == 0:
            return inkex.errormsg(
                "Cut failed: The drawn line(s) did not touch any cuttable regions."
            )

        core.refresh_layer(g, block_data)
        warning_msg = ""
        min_sq_in = self.options.min_piece_area
        for region in tree.leaf_regions():
            if region.area_sq_in() < min_sq_in:
                warning_msg += f"\nWARNING: Piece {region.label} is only {region.area_sq_in():.2f} sq in!"

        inkex.utils.debug(f"Success! {total_cuts} region(s) were split.{warning_msg}")

    def _heal(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        selected_els = [
            el for el in self.svg.selection.values() if el.get(core.FPP_REGION_ATTR)
        ]
        if len(selected_els) != 2:
            return inkex.errormsg("Please select EXACTLY TWO pieces to heal together.")

        id1 = int(selected_els[0].get(core.FPP_REGION_ATTR))
        id2 = int(selected_els[1].get(core.FPP_REGION_ATTR))

        success, msg = block_data.tree.heal_regions(id1, id2)
        if not success:
            return inkex.errormsg(f"Heal failed: {msg}")

        block_data.tree.rebuild_alphabet()
        core.refresh_layer(g, block_data)
        inkex.utils.debug("Pieces successfully healed into a single region.")

    def _undo(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return
        if block_data.tree.undo_last_cut():
            core.refresh_layer(g, block_data)
            inkex.utils.debug("Last cut successfully undone.")
        else:
            inkex.errormsg("Nothing left to undo.")


if __name__ == "__main__":
    CutPlugin().run()
