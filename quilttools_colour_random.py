#!/usr/bin/env python3
import os
import sys
import re
import random
from lxml import etree
import inkex

# Ensure extension path is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import quilttools_colour as qcol
import quilttools_fpp_core as core
import quilttools_theme as qtheme
import quilttools_quilt_core as qcore
import quilttools_svg as qsvg

class ColourRandomiserPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--notebook", type=str, default="")
        pars.add_argument("--action", type=str, default="interactive")
        pars.add_argument("--scope", type=str, default="quilt")
        pars.add_argument("--mode", type=str, default="augmented")
        pars.add_argument("--palette_source", type=str, default="current")
        pars.add_argument("--gpl_file", type=str, default="")
        pars.add_argument("--rule", type=str, default="analogous")
        pars.add_argument("--anchor", type=str, default="")
        pars.add_argument("--tolerance", type=float, default=15.0)
        pars.add_argument("--block_variation", type=float, default=0.05)
        pars.add_argument("--seed", type=str, default="")
        pars.add_argument("--locked_colors", type=str, default="")

    def effect(self):
        # 1. Detect document type
        g_quilt, quilt_data = qcore.find_quilt_group(self.svg)
        g_block, block_data = core.find_fpp_group(self.svg)

        if g_quilt is None and g_block is None:
            return inkex.errormsg(qcol.CONTEXT_HELP["need_any"])

        # 2. Read or load settings
        prefs = qtheme.get_prefs()
        random_prefs = prefs.setdefault("colour_randomiser", {})

        action = self.options.action
        if action == "quick":
            # Load sticky settings
            scope = random_prefs.get("scope", "quilt")
            mode = random_prefs.get("mode", "augmented")
            palette_source = random_prefs.get("palette_source", "current")
            gpl_file = random_prefs.get("gpl_file", "")
            rule = random_prefs.get("rule", "analogous")
            anchor = random_prefs.get("anchor", "")
            tolerance = random_prefs.get("tolerance", 15.0)
            block_variation = random_prefs.get("block_variation", 0.05)
            locked_colors_str = random_prefs.get("locked_colors", "")
            # Generate a fresh seed for quick reroll
            seed_val = str(random.randint(1, 999999))
        else:
            # Read from GUI
            scope = self.options.scope
            mode = self.options.mode
            palette_source = self.options.palette_source
            gpl_file = self.options.gpl_file
            rule = self.options.rule
            anchor = self.options.anchor
            tolerance = self.options.tolerance
            block_variation = self.options.block_variation
            locked_colors_str = self.options.locked_colors
            seed_val = self.options.seed.strip()

            # Save sticky settings
            random_prefs["scope"] = scope
            random_prefs["mode"] = mode
            random_prefs["palette_source"] = palette_source
            random_prefs["gpl_file"] = gpl_file
            random_prefs["rule"] = rule
            random_prefs["anchor"] = anchor
            random_prefs["tolerance"] = tolerance
            random_prefs["block_variation"] = block_variation
            random_prefs["locked_colors"] = locked_colors_str
            random_prefs["seed"] = seed_val
            qtheme.set_prefs(prefs)

        # 3. Seed random generator
        if not seed_val:
            seed_val = str(random.randint(1, 999999))
        rng = random.Random(seed_val)

        # 4. Resolve locked colors
        locked_list = []
        if locked_colors_str:
            locked_list = [c.strip().lower() for c in locked_colors_str.split(",") if c.strip()]
        
        # Also lock colors from current canvas selection
        selection_colors = []
        if self.svg.selection:
            for el in self.svg.selection.values():
                color = qsvg.resolve_element_fill(el)
                if color:
                    color = color.strip().lower()
                    if color.startswith("#") and color not in selection_colors:
                        selection_colors.append(color)
        
        for sc in selection_colors:
            if sc not in locked_list:
                locked_list.append(sc)

        # 5. Load palette if needed
        palette = []
        if mode == "palette":
            if palette_source == "current":
                try:
                    profile = os.environ.get("INKSCAPE_PROFILE_DIR") or \
                        os.path.join(os.environ.get("APPDATA", ""), "inkscape")
                    pref_path = os.path.join(profile, "preferences.xml")
                    if os.path.isfile(pref_path):
                        root = etree.parse(pref_path).getroot()
                        pal_ref = None
                        for el in root.iter():
                            if el.get("id") == "swatches" and el.get("palette"):
                                pal_ref = el.get("palette")
                        if pal_ref:
                            palette = qcol.load_gpl(pal_ref)
                except Exception as e:
                    inkex.utils.debug(f"Failed to load active Inkscape palette: {e}")
            else:
                try:
                    palette = qcol.load_gpl(gpl_file)
                except Exception as e:
                    return inkex.errormsg(f"Could not load GPL palette: {e}")

            if not palette:
                return inkex.errormsg("The selected palette is empty or could not be loaded.")

        warn = False

        # 6. Dispatch based on document type
        if g_block is not None:
            # --- FPP Block Adaptor ---
            regions = block_data.tree.leaf_regions()
            if not regions:
                return inkex.errormsg("FPP block contains no pieces.")

            custom_colors = block_data.prefs.setdefault("custom_colors", {})
            color_mode = block_data.prefs.get("color_mode", "piece")
            
            # Map region ID to current color
            region_colors = {}
            for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
                c = custom_colors.get(str(r.id))
                if not c:
                    c = qsvg.get_color_for_label(r.label, color_mode, idx)
                region_colors[r.id] = c.strip().lower()

            unique_colors = sorted(list(set(region_colors.values())))
            locked_slots = set()
            for idx, col in enumerate(unique_colors):
                if col in locked_list:
                    locked_slots.add(idx)

            # Randomize slots
            if mode == "shuffle":
                new_slot_colors = qcol.shuffle(unique_colors, locked_slots, rng)
            elif mode == "palette":
                new_slot_colors, warn = qcol.from_palette(unique_colors, palette, locked_slots, rng)
            elif mode == "full_random":
                new_slot_colors = qcol.full_random(unique_colors, locked_slots, rng)
            else: # augmented
                new_slot_colors = qcol.augmented(unique_colors, locked_slots, rng, rule, tolerance, anchor)

            if scope == "block" and block_variation > 0 and mode == "augmented":
                new_slot_colors = [qcol.jitter(col, block_variation, rng) if i not in locked_slots else col for i, col in enumerate(new_slot_colors)]

            # Save colors back
            for rid, col in region_colors.items():
                slot_idx = unique_colors.index(col)
                custom_colors[str(rid)] = new_slot_colors[slot_idx]

            # Redraw block
            core.refresh_layer(g_block, block_data, scrape=False)

        elif g_quilt is not None:
            # --- Quilt Layout Adaptor ---
            placed_cells = [cid for cid, info in quilt_data.cells.items() if info["role"] == "block" and info["state"] == "placed"]
            
            # Walk placed block paths on the canvas
            pieces = []
            for cell_id in placed_cells:
                g_cell = g_quilt.find(f".//{{{core.SVG_NS}}}g[@id='{cell_id}']")
                if g_cell is None:
                    continue
                # Placed blocks are inside tile groups cell_id-placed-tile_idx
                for tile_group in g_cell.findall(f".//{{{core.SVG_NS}}}g"):
                    tg_id = tile_group.get("id") or ""
                    if tg_id.startswith(f"{cell_id}-placed-"):
                        for path in tile_group.findall(f".//{{{core.SVG_NS}}}path"):
                            rid = path.get(core.FPP_REGION_ATTR)
                            if rid:
                                color = qsvg.resolve_element_fill(path)
                                if color:
                                    pieces.append({
                                        "cell_id": cell_id,
                                        "region_id": rid,
                                        "element": path,
                                        "color": color.strip().lower()
                                    })

            if not pieces:
                return inkex.errormsg("No placed block pieces found in Quilt Layout.")

            unique_colors = sorted(list(set(p["color"] for p in pieces)))
            locked_slots = set()
            for idx, col in enumerate(unique_colors):
                if col in locked_list:
                    locked_slots.add(idx)

            if scope == "quilt" or block_variation == 0 or mode != "augmented":
                # Quilt Level Single Step
                if mode == "shuffle":
                    new_slot_colors = qcol.shuffle(unique_colors, locked_slots, rng)
                elif mode == "palette":
                    new_slot_colors, warn = qcol.from_palette(unique_colors, palette, locked_slots, rng)
                elif mode == "full_random":
                    new_slot_colors = qcol.full_random(unique_colors, locked_slots, rng)
                else: # augmented
                    new_slot_colors = qcol.augmented(unique_colors, locked_slots, rng, rule, tolerance, anchor)

                # Write directly to canvas paths
                for p in pieces:
                    slot_idx = unique_colors.index(p["color"])
                    new_color = new_slot_colors[slot_idx]
                    style = p["element"].get("style", "")
                    if "fill:" in style:
                        style = re.sub(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", f"fill:{new_color}", style)
                    else:
                        style = f"fill:{new_color};" + style
                    p["element"].set("style", style)
            else:
                # Per Block Scope (Two-Level Jitter)
                base_slot_colors = qcol.augmented(unique_colors, locked_slots, rng, rule, tolerance, anchor)
                
                # Group pieces by cell
                cell_pieces = {}
                for p in pieces:
                    cell_pieces.setdefault(p["cell_id"], []).append(p)
                
                for cell_id, p_list in cell_pieces.items():
                    cell_slot_colors = []
                    for idx, base_col in enumerate(base_slot_colors):
                        if idx in locked_slots:
                            cell_slot_colors.append(base_col)
                        else:
                            cell_slot_colors.append(qcol.jitter(base_col, block_variation, rng))
                    
                    for p in p_list:
                        slot_idx = unique_colors.index(p["color"])
                        new_color = cell_slot_colors[slot_idx]
                        style = p["element"].get("style", "")
                        if "fill:" in style:
                            style = re.sub(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", f"fill:{new_color}", style)
                        else:
                            style = f"fill:{new_color};" + style
                        p["element"].set("style", style)

        # 7. Print result popup
        msg = f"Reroll successful! Seed used: {seed_val}"
        if warn:
            msg += "\nWarning: Palette was smaller than slot count; some colors were repeated."
        inkex.utils.debug(msg)

if __name__ == "__main__":
    ColourRandomiserPlugin().run()
