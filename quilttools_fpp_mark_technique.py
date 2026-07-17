#!/usr/bin/env python3
"""Mark Cutting Technique — tag pieces with cutting techniques for the
template-mode fabric planner (DESIGN_fabric_cutplan.md §4).

Tags live in BlockData.prefs["piece_meta"] (backwards compatible: legacy
SVGs simply have no tags). Stitch-and-flip is ONLY ever applied here,
never automatically at export.
"""
import math

import inkex
from lxml import etree

import quilttools_fpp_core as core
import quilttools_cutplan as cutplan
import quilttools_fpp_fabric as fabric

MARK_LAYER_ID = "qt-technique-marks"

TECH_BADGE = {
    "stitch_flip": ("S&F", "#c0392b"),
    "hst2": ("x2", "#8e44ad"),
    "hst8": ("x8", "#8e44ad"),
    "fg4": ("FG4", "#2471a3"),
    "y_seam": ("Y-Seam", "#d35400"),
}
GRAIN_BADGE = {
    "fixed": ("FIX", "#1e8449"),
    "fussy": ("FUSSY", "#b7950b"),
}


class MarkTechniquePlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="apply")
        pars.add_argument("--technique", type=str, default="none")
        pars.add_argument("--grain", type=str, default="keep")
        pars.add_argument("--notebook", type=str, default="")

    # ---------------- helpers ----------------

    def _load(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            inkex.errormsg("No Quilt Tools FPP block found.")
            return None, None
        return g, block_data

    def _save(self, g, block_data):
        desc = g.find(f"{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
        if desc is None:
            desc = etree.SubElement(g, "{%s}desc" % core.SVG_NS,
                                    id=core.FPP_DATA_TAG_ID)
        desc.text = block_data.to_json()

    def _selected_region_ids(self):
        ids = []
        for el in self.svg.selection.values():
            rid = el.get(core.FPP_REGION_ATTR)
            if rid is not None:
                ids.append(str(rid))
        return ids

    def _region_map(self, block_data):
        return {str(r.id): r for r in block_data.tree.leaf_regions()}

    def _poly_in(self, region):
        """Region polygon in inches at current canvas size."""
        return [(p[0] / core.PX_PER_INCH, p[1] / core.PX_PER_INCH)
                for p in region.polygon]

    # ---------------- actions ----------------

    def effect(self):
        g, block_data = self._load()
        if g is None:
            return
        action = self.options.action

        # Check if the review card is already present in the SVG XML before we modify the layers
        card_existed = (self.svg.find(f".//{{{core.SVG_NS}}}g[@id='qt-technique-review-card']") is not None)

        if action == "apply":
            changed = self._apply(block_data)
        elif action == "clear":
            changed = self._clear(block_data)
        elif action == "autodetect":
            changed = self._autodetect(block_data)
        elif action == "show":
            changed = False
        else:
            return inkex.errormsg(f"Unknown action: {action}")

        if changed:
            self._save(g, block_data)

        self._draw_marks(g, block_data)

        if action == "show":
            if not card_existed:
                self._draw_review_card(g, block_data)
        else:
            if card_existed:
                self._draw_review_card(g, block_data)

        self._text_summary(block_data)

    def _apply(self, block_data):
        ids = self._selected_region_ids()
        if not ids:
            inkex.errormsg("Select the piece(s) to tag first (paths with "
                           "quilt-tools region data).")
            return False
        regions = self._region_map(block_data)
        ids = [i for i in ids if i in regions]
        tech = self.options.technique
        grain = self.options.grain
        changed = False

        if tech == "stitch_flip":
            changed = self._apply_stitch_flip(block_data, regions, ids)
        elif tech in ("hst2", "hst8", "fg4"):
            changed = self._apply_batch(block_data, regions, ids, tech)
        elif tech == "fpp_section":
            changed = self._apply_fpp_section(block_data, regions, ids)
        elif tech == "template":
            prefixes = {self._prefix_of(regions[rid].label) for rid in ids}
            cur = [p for p in (block_data.prefs.get("fpp_sections") or [])
                   if p.upper() not in prefixes]
            if len(cur) != len(block_data.prefs.get("fpp_sections") or []):
                block_data.prefs["fpp_sections"] = cur
                changed = True
            for rid in ids:
                block_data.set_piece_meta(rid, technique=None,
                                          sf_bases=None, batch_group=None,
                                          suggested=None)
                changed = True

        if grain != "keep":
            for rid in ids:
                # free is the default -> store nothing.
                block_data.set_piece_meta(
                    rid, grain=None if grain == "free" else grain)
                changed = True
        return changed

    @staticmethod
    def _prefix_of(label):
        import re as _re
        m = _re.match(r"^([A-Za-z]+)", label or "")
        return m.group(1).upper() if m else ""

    def _apply_fpp_section(self, block_data, regions, ids):
        """Opt the selected pieces' WHOLE SECTIONS into 'Always FPP':
        template exports deliver those sections as FPP foundation
        templates (rough-cut fabric estimates) instead of single-piece
        templates."""
        prefixes = sorted({self._prefix_of(regions[rid].label)
                           for rid in ids if self._prefix_of(
                               regions[rid].label)})
        if not prefixes:
            inkex.errormsg("Selected pieces have no section letters.")
            return False
        cur = {p.upper() for p in
               (block_data.prefs.get("fpp_sections") or [])}
        cur.update(prefixes)
        block_data.prefs["fpp_sections"] = sorted(cur)
        inkex.utils.debug(
            "Always-FPP sections: " + ", ".join(sorted(cur)) + ". Template "
            "exports now print these sections as FPP foundations. (Apply "
            "'Default (plain template)' to section pieces to undo. Note: "
            "re-running the auto-labeller can change section letters.)")
        return True

    def _sf_pieces_list(self, block_data, regions):
        meta_all = block_data.piece_meta()
        return [{"id": rid, "polygon": self._poly_in(r), "label": r.label,
                 "meta": dict(meta_all.get(rid) or {})}
                for rid, r in regions.items()]

    def _apply_stitch_flip(self, block_data, regions, ids):
        # Double-layer corners: apply every OTHER existing stitch-and-flip
        # tag first, so a corner that is itself flipped over (e.g. sewn
        # first, partly covered by a later corner) is analysed on its full
        # pre-trim footprint rather than its visible sliver.
        pieces_all = self._sf_pieces_list(block_data, regions)
        _corners, overrides, _warn = cutplan.resolve_stitch_flips(
            pieces_all, exclude_ids=set(ids))

        def eff(rid):
            return overrides.get(rid, self._poly_in(regions[rid]))

        tris, others = [], []
        for rid in ids:
            info = cutplan.classify_piece(eff(rid))
            (tris if info["kind"] == "tri" else others).append(rid)
        if not tris:
            inkex.errormsg("Stitch-and-flip: select the corner TRIANGLE "
                           "piece(s) (optionally together with their base "
                           "pieces to pair explicitly).")
            return False
        if others and len(tris) > 1:
            inkex.errormsg("Stitch-and-flip: to pair explicitly, select ONE "
                           "triangle plus its base piece(s).")
            return False

        changed = False
        for tid in tris:
            tri_poly = eff(tid)
            layered = tid in overrides
            if others:
                base_ids = list(others)
            else:
                cand_ids = [rid for rid in regions if rid != tid]
                cand_polys = [eff(rid) for rid in cand_ids]
                hits = cutplan.find_snowball_bases(tri_poly, cand_polys)
                base_ids = [cand_ids[i] for i in hits]
            if not base_ids:
                inkex.errormsg(f"{regions[tid].label}: no neighbouring "
                               "piece found along the corner seam.")
                continue
            base_polys = [eff(b) for b in base_ids]
            ext, err = cutplan.snowball_extend(tri_poly, base_polys)
            if err:
                inkex.errormsg(
                    f"{regions[tid].label}: stitch-and-flip NOT applied - "
                    f"{err}. Select the triangle together with its base "
                    "piece(s) to assert the pairing, or use a template "
                    "for this corner.")
                continue
            block_data.set_piece_meta(tid, technique="stitch_flip",
                                      sf_bases=base_ids, batch_group=None,
                                      suggested=None)
            base_labels = "+".join(regions[b].label for b in base_ids)
            extra = (" (double-layer: analysed on its full pre-trim "
                     "footprint under the later corner)" if layered else "")
            inkex.utils.debug(
                f"{regions[tid].label}: stitch-and-flip corner flips onto "
                f"{base_labels}.{extra}")
            changed = True
        return changed

    def _apply_batch(self, block_data, regions, ids, tech):
        tri_ids = []
        for rid in ids:
            info = cutplan.classify_piece(self._poly_in(regions[rid]))
            if info["kind"] != "tri":
                inkex.errormsg(f"{regions[rid].label} is not a triangle; "
                               f"skipped for {tech}.")
                continue
            tri_ids.append(rid)
        if not tri_ids:
            return False
        existing = {m.get("batch_group") for m in
                    block_data.piece_meta().values() if m.get("batch_group")}
        n = 1
        while f"{tech}-{n}" in existing:
            n += 1
        group = f"{tech}-{n}"
        for rid in tri_ids:
            block_data.set_piece_meta(rid, technique=tech,
                                      batch_group=group, sf_bases=None,
                                      suggested=None)
        colors = fabric.region_colors(block_data)
        per_fab = {}
        for rid in tri_ids:
            per_fab[colors[regions[rid].id]] = \
                per_fab.get(colors[regions[rid].id], 0) + 1
        yield_txt = {"hst2": "2 HSTs per square pair",
                     "hst8": "8 HSTs per square pair",
                     "fg4": "4 geese per large square"}[tech]
        counts = ", ".join(f"{v} x {k}" for k, v in sorted(per_fab.items()))
        inkex.utils.debug(f"Batch group {group}: {len(tri_ids)} triangles "
                          f"({counts}); {yield_txt}. Fabric requirements "
                          "update on the next Template export.")
        return True

    def _clear(self, block_data):
        ids = self._selected_region_ids()
        regions = self._region_map(block_data)
        ids = [i for i in ids if i in regions]
        if not ids:
            inkex.errormsg("Select the piece(s) whose tags should be "
                           "cleared.")
            return False
        for rid in ids:
            block_data.set_piece_meta(rid, technique=None, grain=None,
                                      sf_bases=None, batch_group=None,
                                      suggested=None)
        inkex.utils.debug(f"Cleared technique tags on {len(ids)} piece(s).")
        return True

    def _autodetect(self, block_data):
        regions = self._region_map(block_data)
        pieces = [{"id": rid, "polygon": self._poly_in(r)}
                  for rid, r in regions.items()]
        polys = [p["polygon"] for p in pieces]
        outline, _sound = core.section_outline(polys)
        if not outline or len(outline) < 3:
            inkex.errormsg("Could not derive the block outline.")
            return False
        outline_in = outline
        cand = cutplan.detect_snowball_candidates(pieces, outline_in)
        meta = block_data.piece_meta()
        changed = False
        found = []
        for tid in cand:
            if (meta.get(tid) or {}).get("technique"):
                continue  # already tagged; leave user decisions alone
            tri_poly = next(p["polygon"] for p in pieces if p["id"] == tid)
            cand_ids = [rid for rid in regions if rid != tid]
            cand_polys = [self._poly_in(regions[rid]) for rid in cand_ids]
            hits = cutplan.find_snowball_bases(tri_poly, cand_polys)
            base_ids = [cand_ids[i] for i in hits]
            if not base_ids:
                continue
            ext, err = cutplan.snowball_extend(
                tri_poly, [self._poly_in(regions[b]) for b in base_ids])
            if err:
                continue
            block_data.set_piece_meta(tid, technique="stitch_flip",
                                      sf_bases=base_ids, suggested=True)
            found.append(regions[tid].label)
            changed = True
        if found:
            inkex.utils.debug(
                "Auto-detected stitch-and-flip corner candidates (marked "
                "'suggested', shown with dashed badges): "
                + ", ".join(sorted(found))
                + ". Re-run Apply on a corner to confirm it, or Clear to "
                  "reject.")
        else:
            inkex.utils.debug("No new stitch-and-flip candidates found.")
        return changed

    # ---------------- canvas drawing ----------------

    def _marks_layer(self, fresh=True):
        for layer in self.svg.findall(f".//{{{core.SVG_NS}}}g"):
            if layer.get("id") == MARK_LAYER_ID:
                layer.getparent().remove(layer)
        if not fresh:
            return None
        return etree.SubElement(
            self.svg, "{%s}g" % core.SVG_NS, id=MARK_LAYER_ID, **{
                f"{{{core.INKSCAPE_NS}}}label":
                    "Technique Marks (annotation only)",
                f"{{{core.INKSCAPE_NS}}}groupmode": "layer",
                "style": "display:inline;",
                f"{{{core.SODIPODI_NS}}}insensitive": "true",
            })

    def _draw_marks(self, g, block_data):
        layer = self._marks_layer(fresh=True)
        meta = block_data.piece_meta()
        fpp_sections = {p.upper() for p in
                        (block_data.prefs.get("fpp_sections") or [])}
        if not meta and not fpp_sections:
            return
        regions = self._region_map(block_data)
        if fpp_sections:
            for rid, r in regions.items():
                if self._prefix_of(r.label) not in fpp_sections:
                    continue
                cx, cy = core.polygon_centroid(r.polygon)
                etree.SubElement(
                    layer, "{%s}rect" % core.SVG_NS,
                    x=str(cx - 16), y=str(cy - 24), width="32", height="13",
                    rx="4",
                    style="fill:#ffffff;fill-opacity:0.85;stroke:#117a65;stroke-width:1.0;",
                )
                etree.SubElement(
                    layer, "{%s}text" % core.SVG_NS,
                    x=str(cx), y=str(cy - 13.5),
                    style="font-size:9px;font-family:sans-serif;font-weight:bold;text-anchor:middle;fill:#117a65;",
                ).text = "FPP"
        for rid, m in meta.items():
            r = regions.get(rid)
            if r is None:
                continue
            cx, cy = core.polygon_centroid(r.polygon)
            badges = []
            tech = m.get("technique")
            if tech in TECH_BADGE:
                badges.append((TECH_BADGE[tech], bool(m.get("suggested"))))
            grain = m.get("grain")
            if grain in GRAIN_BADGE:
                badges.append((GRAIN_BADGE[grain], False))
            for i, ((txt, col), suggested) in enumerate(badges):
                by = cy + i * 16.0
                dash = "stroke-dasharray:2,2;" if suggested else ""
                etree.SubElement(
                    layer, "{%s}rect" % core.SVG_NS,
                    x=str(cx - 16), y=str(by - 8), width="32", height="13",
                    rx="4",
                    style=f"fill:#ffffff;fill-opacity:0.85;stroke:{col};stroke-width:1.0;{dash}",
                )
                etree.SubElement(
                    layer, "{%s}text" % core.SVG_NS,
                    x=str(cx), y=str(by + 2.5),
                    style=f"font-size:9px;font-family:sans-serif;font-weight:bold;text-anchor:middle;fill:{col};",
                ).text = txt + ("?" if suggested else "")

    def _draw_review_card(self, g, block_data):
        """Review card on the annotation layer: mini block with marked
        pieces highlighted + a legend for every technique tag."""
        layer = self.svg.find(f".//{{{core.SVG_NS}}}g[@id='{MARK_LAYER_ID}']")
        if layer is None:
            layer = self._marks_layer(fresh=True)

        card_layer = etree.SubElement(layer, "{%s}g" % core.SVG_NS, id="qt-technique-review-card")

        meta = block_data.piece_meta()
        regions = self._region_map(block_data)
        colors = fabric.region_colors(block_data)
        corners_info, _ov, _w = cutplan.resolve_stitch_flips(
            self._sf_pieces_list(block_data, regions))

        all_pts = [pt for r in regions.values() for pt in r.polygon]
        if not all_pts:
            return
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        bx0, bx1 = min(xs), max(xs)
        by0, by1 = min(ys), max(ys)
        bw = max(bx1 - bx0, 1.0)
        bh = max(by1 - by0, 1.0)

        card_x = bx1 + 60.0
        card_y = by0
        mini = 220.0
        sc = mini / max(bw, bh)

        etree.SubElement(
            card_layer, "{%s}rect" % core.SVG_NS,
            x=str(card_x - 12), y=str(card_y - 30),
            width=str(mini + 320), height=str(mini + 70 + 14 * max(len(meta), 1)),
            rx="6",
            style="fill:#fffdf5;stroke:#888888;stroke-width:1.0;",
        )
        etree.SubElement(
            card_layer, "{%s}text" % core.SVG_NS,
            x=str(card_x), y=str(card_y - 10),
            style="font-size:13px;font-family:sans-serif;font-weight:bold;fill:#333333;",
        ).text = "Marked Cutting Techniques (annotation - not exported)"

        fpp_sections = {p.upper() for p in (block_data.prefs.get("fpp_sections") or [])}

        # mini block
        sf_no = 0
        legend = []
        for rid, r in sorted(regions.items(), key=lambda kv: kv[1].label):
            m = meta.get(rid) or {}
            tech = m.get("technique")
            grain = m.get("grain")
            is_fpp = (self._prefix_of(r.label) in fpp_sections)
            pts = " ".join(
                f"{card_x + (p[0]-bx0)*sc:.2f},{card_y + (p[1]-by0)*sc:.2f}"
                for p in r.polygon)
            
            if is_fpp:
                col = "#117a65"
                fill = f"{col};fill-opacity:0.45"
            elif tech in TECH_BADGE:
                col = TECH_BADGE[tech][1]
                fill = f"{col};fill-opacity:0.45"
            elif grain in GRAIN_BADGE:
                col = GRAIN_BADGE[grain][1]
                fill = f"{col};fill-opacity:0.35"
            else:
                col = "#999999"
                fill = "#ffffff;fill-opacity:0.0"
                
            etree.SubElement(
                card_layer, "{%s}polygon" % core.SVG_NS, points=pts,
                style=f"fill:{fill};stroke:#666666;stroke-width:0.7;",
            )
            if tech == "stitch_flip":
                sf_no += 1
                cx, cy = core.polygon_centroid(r.polygon)
                etree.SubElement(
                    card_layer, "{%s}text" % core.SVG_NS,
                    x=str(card_x + (cx - bx0) * sc),
                    y=str(card_y + (cy - by0) * sc + 3),
                    style="font-size:11px;font-family:sans-serif;font-weight:bold;text-anchor:middle;fill:#7b241c;",
                ).text = str(sf_no)
                ci = corners_info.get(rid)
                if ci:
                    legs = ci["legs"]
                else:
                    info = cutplan.classify_piece(self._poly_in(r))
                    legs = info["legs"] or (0, 0)
                side = (legs[0] + legs[1]) / 2.0 + 0.5
                bases = "+".join(regions[b].label
                                 for b in m.get("sf_bases", [])
                                 if b in regions)
                sugg = " [auto - verify]" if m.get("suggested") else ""
                legend.append((TECH_BADGE["stitch_flip"][1],
                               f"{sf_no}: {r.label} corner "
                               f"{cutplan.fmt_in(side)} sq "
                               f"({colors[r.id]}) flips onto "
                               f"{bases or '?'}{sugg}"))

        # batch groups
        groups = {}
        for rid, m in meta.items():
            gkey = m.get("batch_group")
            if gkey and rid in regions:
                groups.setdefault((m.get("technique"), gkey), []).append(rid)
        for (tech, gkey), rids in sorted(groups.items(),
                                         key=lambda kv: kv[0][1]):
            labels = ", ".join(sorted(regions[i].label for i in rids))
            legend.append((TECH_BADGE.get(tech, ("", "#555555"))[1],
                           f"{gkey}: {len(rids)} triangles ({labels})"))

        fpp_sections_list = sorted(list(fpp_sections))
        if fpp_sections_list:
            legend.append(("#117a65",
                           "Always-FPP sections (foundation templates): "
                           + ", ".join(fpp_sections_list)))

        # grain-tagged pieces
        for badge_key, title in (("fixed", "grain-fixed"),
                                 ("fussy", "fussy cut")):
            tagged = sorted(regions[rid].label for rid, m in meta.items()
                            if m.get("grain") == badge_key and rid in regions)
            if tagged:
                legend.append((GRAIN_BADGE[badge_key][1],
                               f"{title}: {', '.join(tagged)}"))
        if not legend:
            legend.append(("#555555",
                           "No technique tags yet - select pieces and run "
                           "Apply."))

        ly = card_y + mini + 24
        for col, txt in legend:
            etree.SubElement(
                card_layer, "{%s}circle" % core.SVG_NS,
                cx=str(card_x + 4), cy=str(ly - 3.5), r="4",
                style=f"fill:{col};",
            )
            etree.SubElement(
                card_layer, "{%s}text" % core.SVG_NS,
                x=str(card_x + 14), y=str(ly),
                style="font-size:10px;font-family:sans-serif;fill:#333333;",
            ).text = txt
            ly += 14.0

    def _text_summary(self, block_data):
        meta = block_data.piece_meta()
        if not meta:
            return
        regions = self._region_map(block_data)
        n_sf = sum(1 for m in meta.values()
                   if m.get("technique") == "stitch_flip")
        n_sugg = sum(1 for m in meta.values() if m.get("suggested"))
        n_batch = len({m.get("batch_group") for m in meta.values()
                       if m.get("batch_group")})
        parts = []
        if n_sf:
            parts.append(f"{n_sf} stitch-and-flip corner(s)"
                         + (f" ({n_sugg} suggested, unconfirmed)"
                            if n_sugg else ""))
        if n_batch:
            parts.append(f"{n_batch} batch group(s)")
        n_grain = sum(1 for m in meta.values() if m.get("grain"))
        if n_grain:
            parts.append(f"{n_grain} grain-tagged piece(s)")
        if parts:
            inkex.utils.debug("Block tags: " + "; ".join(parts) + ".")


if __name__ == "__main__":
    MarkTechniquePlugin().run()
