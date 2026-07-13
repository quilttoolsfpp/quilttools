#!/usr/bin/env python3
import re
import math
import string
import inkex
from lxml import etree
import quilttools_fpp_core as core

class AddBorderPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--border_width_in", type=float, default=2.0)
        pars.add_argument("--border_layout", type=str, default="long_horizontal")

    def effect(self):
        # 1. Find FPP block on canvas
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found on canvas.")
            
        # 2. Get current block dimensions from the root region polygon
        root_id = block_data.tree.root_id
        root_reg = block_data.tree.regions[root_id]
        root_poly = root_reg.polygon
        if not root_poly:
            return inkex.errormsg("FPP block root region has no polygon geometry.")
            
        xs = [p[0] for p in root_poly]
        ys = [p[1] for p in root_poly]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        W = max_x - min_x
        H = max_y - min_y
        
        B = self.options.border_width_in * core.PX_PER_INCH
        if B <= 0.0:
            return inkex.errormsg("Border width must be positive.")
            
        # 3. Shift all existing regions and curves by +B in X and Y
        shift_x = -min_x + B
        shift_y = -min_y + B
        
        for r in block_data.tree.regions.values():
            r.polygon = [(p[0] + shift_x, p[1] + shift_y) for p in r.polygon]
            
        if hasattr(block_data.tree, "curves") and block_data.tree.curves:
            for curve in block_data.tree.curves:
                for i in range(len(curve)):
                    curve[i] = (curve[i][0] + shift_x, curve[i][1] + shift_y)
                    
        # 4. Define the 4 border polygons in the new coordinates
        layout = self.options.border_layout
        if layout == "long_horizontal":
            poly_top = [(0.0, H + B), (W + 2*B, H + B), (W + 2*B, H + 2*B), (0.0, H + 2*B)]
            poly_bottom = [(0.0, 0.0), (W + 2*B, 0.0), (W + 2*B, B), (0.0, B)]
            poly_left = [(0.0, B), (B, B), (B, H + B), (0.0, H + B)]
            poly_right = [(W + B, B), (W + 2*B, B), (W + 2*B, H + B), (W + B, H + B)]
        elif layout == "long_vertical":
            poly_left = [(0.0, 0.0), (B, 0.0), (B, H + 2*B), (0.0, H + 2*B)]
            poly_right = [(W + B, 0.0), (W + 2*B, 0.0), (W + 2*B, H + 2*B), (W + B, H + 2*B)]
            poly_top = [(B, H + B), (W + B, H + B), (W + B, H + 2*B), (B, H + 2*B)]
            poly_bottom = [(B, 0.0), (W + B, 0.0), (W + B, B), (B, B)]
        elif layout == "log_cabin_cw":
            poly_left = [(0.0, 0.0), (B, 0.0), (B, H + 2*B), (0.0, H + 2*B)]
            poly_top = [(B, H + B), (W + B, H + B), (W + B, H + 2*B), (B, H + 2*B)]
            poly_right = [(W + B, B), (W + 2*B, B), (W + 2*B, H + 2*B), (W + B, H + 2*B)]
            poly_bottom = [(B, 0.0), (W + 2*B, 0.0), (W + 2*B, B), (B, B)]
        else: # "log_cabin_ccw"
            poly_right = [(W + B, 0.0), (W + 2*B, 0.0), (W + 2*B, H + 2*B), (W + B, H + 2*B)]
            poly_top = [(B, H + B), (W + B, H + B), (W + B, H + 2*B), (B, H + 2*B)]
            poly_left = [(0.0, B), (B, B), (B, H + 2*B), (0.0, H + 2*B)]
            poly_bottom = [(0.0, 0.0), (W + B, 0.0), (W + B, B), (0.0, B)]
            
        # 5. Find the next 4 available alphabetical section prefixes
        existing_prefixes = set()
        for r in block_data.tree.leaf_regions():
            match = re.match(r"^([A-Za-z]+)", r.label)
            if match:
                existing_prefixes.add(match.group(1).upper())
                
        available_letters = []
        alphabet = list(string.ascii_uppercase)
        def letter_gen():
            for c in alphabet:
                yield c
            for c1 in alphabet:
                for c2 in alphabet:
                    yield c1 + c2
        gen = letter_gen()
        while len(available_letters) < 4:
            let = next(gen)
            if let not in existing_prefixes:
                available_letters.append(let)
                
        # 6. Update the root region polygon
        root_reg.polygon = [
            (0.0, 0.0),
            (W + 2*B, 0.0),
            (W + 2*B, H + 2*B),
            (0.0, H + 2*B)
        ]
        
        # 7. Create the 4 new Region objects
        core.Region._counter = max(max(block_data.tree.regions.keys()), core.Region._counter)
        
        border_regions = [
            core.Region(poly_left, label=f"{available_letters[0]}1", parent_id=root_id),
            core.Region(poly_top, label=f"{available_letters[1]}1", parent_id=root_id),
            core.Region(poly_right, label=f"{available_letters[2]}1", parent_id=root_id),
            core.Region(poly_bottom, label=f"{available_letters[3]}1", parent_id=root_id)
        ]
        
        for br in border_regions:
            block_data.tree.regions[br.id] = br
            block_data.tree.regions[root_id].children.append(br.id)
            
        # 8. Rebuild alphabet labels and refresh
        block_data.tree.rebuild_alphabet()
        core.refresh_layer(g, block_data)
        
        inkex.utils.debug(
            f"Successfully added a {self.options.border_width_in:.2f}in plain border ({layout}). "
            f"Borders assigned to new sections: {', '.join(available_letters)}. "
            f"New block size: {(W + 2*B)/core.PX_PER_INCH:.2f}in x {(H + 2*B)/core.PX_PER_INCH:.2f}in."
        )

if __name__ == "__main__":
    AddBorderPlugin().run()
