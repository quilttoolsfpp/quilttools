#!/usr/bin/env python3
import os
import math
import inkex
from lxml import etree
import quilttools_fpp_core as core
import quilttools_svg as qsvg

class ImportSVGBlockPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--svg_file", type=str, default="")
        pars.add_argument("--resize_page", type=inkex.Boolean, default=True)

    def effect(self):
        svg_file = self.options.svg_file.strip()
        if not svg_file:
            return inkex.errormsg("Please specify an SVG block file to import.")
        if not os.path.exists(svg_file):
            return inkex.errormsg(f"Specified file does not exist: {svg_file}")

        try:
            doc = etree.parse(svg_file)
        except Exception as e:
            return inkex.errormsg(f"Failed to parse SVG file: {e}")

        # Recursively extract shapes and curves
        shapes, curves = self.extract_shapes(doc.getroot())
        if not shapes:
            return inkex.errormsg("No valid closed polygons or paths found in the SVG file.")

        # Compute bounding box
        all_pts = [pt for poly in shapes for pt in poly]
        xs = [pt[0] for pt in all_pts]
        ys = [pt[1] for pt in all_pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w = max_x - min_x
        h = max_y - min_y

        if w <= 0 or h <= 0:
            return inkex.errormsg("The bounding box of the imported shapes is empty.")

        # Shift coordinates to start at (0, 0)
        shifted_shapes = []
        for poly in shapes:
            shifted_shapes.append([(p[0] - min_x, p[1] - min_y) for p in poly])

        shifted_curves = []
        for curve in curves:
            shifted_curves.append([(p[0] - min_x, p[1] - min_y) for p in curve])

        # Compute outline union
        outline, sound = qsvg.section_outline(shifted_shapes)
        if not sound or not outline:
            outline = [(0, 0), (w, 0), (w, h), (0, h)]

        # Build RegionTree
        tree = core.RegionTree(outline)
        tree.curves = shifted_curves

        # Add each shape as a leaf region under root
        root_id = tree.root_id
        root_reg = tree.regions[root_id]
        
        leaf_ids = []
        for poly in shifted_shapes:
            r = core.Region(poly, parent_id=root_id)
            tree.regions[r.id] = r
            root_reg.children.append(r.id)
            leaf_ids.append(r.id)

        # Set split_boundary flag for the root
        root_reg.split_boundary = True

        # Check for Y-seams using virtual sewing validator
        is_valid, sequence = tree.virtual_sewing_validator(leaf_ids)
        
        block_data = core.BlockData(tree)
        
        unseparable_ids = set(leaf_ids) - set(sequence)
        if not is_valid or unseparable_ids:
            inkex.errormsg(
                f"WARNING: This block contains Y-seams (partial seams).\n"
                f"{len(unseparable_ids)} piece(s) could not be sewn using straight seams "
                f"and have been tagged with the Y-Seam technique."
            )
            for rid in unseparable_ids:
                block_data.set_piece_meta(rid, technique="y_seam")

        # Label the regions in sewing order
        full_sequence = sequence + list(unseparable_ids)
        for idx, rid in enumerate(full_sequence):
            tree.regions[rid].label = f"A{idx + 1}"

        # Setup page if requested
        if self.options.resize_page:
            self.svg.set("width", f"{w}px")
            self.svg.set("height", f"{h}px")
            self.svg.set("viewBox", f"0 0 {w} {h}")

        # Render block layer
        g = core.build_fpp_layer(block_data)
        self.svg.get_current_layer().append(g)
        
        inkex.utils.debug(f"Success! Imported {len(leaf_ids)} pieces into FPP Block.")

    def extract_shapes(self, el, current_transform=inkex.Transform()):
        shapes = []
        curves = []
        
        # Combine transform of this element
        if el.get("transform"):
            try:
                transform = current_transform @ inkex.Transform(el.get("transform"))
            except Exception:
                transform = current_transform
        else:
            transform = current_transform
            
        tag = el.tag.split("}")[-1]
        
        if tag == "polygon":
            pts = []
            raw_pts = el.get("points", "").replace(",", " ").split()
            for i in range(0, len(raw_pts), 2):
                try:
                     x, y = float(raw_pts[i]), float(raw_pts[i+1])
                     pts.append(transform.apply_to_point((x, y)))
                except (IndexError, ValueError):
                     pass
            if len(pts) >= 3:
                shapes.append(pts)
                 
        elif tag == "rect":
            try:
                 x = float(el.get("x", 0))
                 y = float(el.get("y", 0))
                 w = float(el.get("width", 0))
                 h = float(el.get("height", 0))
                 pts = [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]
                 pts = [transform.apply_to_point(p) for p in pts]
                 shapes.append(pts)
            except (ValueError, TypeError):
                 pass
                 
        elif tag == "path":
            d = el.get("d")
            if d:
                 path_obj = inkex.Path(d)
                 sp = path_obj.to_superpath()
                 inkex.bezier.cspsubdiv(sp, 0.5)
                 for sub in sp:
                     pts = [transform.apply_to_point((node[1][0], node[1][1])) for node in sub]
                     if pts:
                         if path_obj[-1].letter in ('Z', 'z') or math.hypot(pts[0][0]-pts[-1][0], pts[0][1]-pts[-1][1]) < 1.0:
                             shapes.append(pts)
                             
                 # Extract curves
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
                             seg_pts = [transform.apply_to_point((node[1][0], node[1][1])) for node in seg_sp[0]]
                             if len(seg_pts) >= 2:
                                 curves.append(seg_pts)
                         if cmd.args:
                             prev_x, prev_y = cmd.args[-2], cmd.args[-1]
                         elif letter == 'Z':
                             prev_x, prev_y = start_x, start_y
                             
        for child in el:
             s, c = self.extract_shapes(child, transform)
             shapes.extend(s)
             curves.extend(c)
             
        return shapes, curves

if __name__ == "__main__":
    ImportSVGBlockPlugin().run()
