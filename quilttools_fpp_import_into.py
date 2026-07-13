import os
import sys
import re
import math
from lxml import etree
import inkex

# Ensure extension path is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import quilttools_patterns_core as core

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(EXT_DIR, "BlockLibrary")

def _scan_library():
    found = []
    if not os.path.isdir(LIB_DIR):
        return found
    for dirpath, _dirs, files in os.walk(LIB_DIR):
        for fn in files:
            if fn.lower().endswith(".svg"):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, LIB_DIR)
                found.append((rel[:-4].replace(os.sep, "/"), full))
    found.sort(key=lambda x: x[0].lower())
    return found


class ImportIntoPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--svg_file", type=str, default="")
        pars.add_argument("--sizing_mode", type=str, default="stretch")
        pars.add_argument("--auto_align", type=inkex.Boolean, default=True)
        pars.add_argument("--rotation", type=float, default=0.0)
        pars.add_argument("--flip", type=str, default="none")

    def effect(self):
        # 1. Identify current FPP block
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found on canvas.")

        # 2. Get selected canvas elements
        selected_els = [el for el in self.svg.selection.values() if el.get(core.FPP_REGION_ATTR)]
        if not selected_els:
            return inkex.errormsg("Please select one or more regions inside the FPP block to import into.")

        selected_ids = [int(el.get(core.FPP_REGION_ATTR)) for el in selected_els]
        target_regions = [block_data.tree.regions[rid] for rid in selected_ids]

        # Sizing and orientation parameters
        chosen = {"path": None}
        settings = {
            "sizing_mode": self.options.sizing_mode,
            "auto_align": self.options.auto_align,
            "rotation": self.options.rotation,
            "flip": self.options.flip,
        }

        # 3. Check for manual/override file
        fallback_file = (self.options.svg_file or "").strip()
        if fallback_file and os.path.isfile(fallback_file):
            chosen["path"] = fallback_file
        else:
            # Try GTK Picker
            try:
                import gi
                gi.require_version("Gtk", "3.0")
                from gi.repository import Gtk, Gdk, GdkPixbuf
                import cairo
                
                blocks = _scan_library()
                if not blocks:
                    return inkex.errormsg(f"The Block Library is empty under:\n  {LIB_DIR}")
                
                dialog = Gtk.Dialog(title="Quilt Tools Pattern - Import into Region")
                dialog.set_default_size(900, 600)
                content = dialog.get_content_area()
                content.set_spacing(6)
                
                # Search Bar
                search = Gtk.SearchEntry()
                search.set_placeholder_text("Search blocks...")
                search.set_margin_top(8)
                search.set_margin_start(10)
                search.set_margin_end(10)
                
                # Left Catalog Scroller
                scroller = Gtk.ScrolledWindow()
                scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
                scroller.set_vexpand(True)
                
                flow = Gtk.FlowBox()
                flow.set_valign(Gtk.Align.START)
                flow.set_max_children_per_line(3)
                flow.set_selection_mode(Gtk.SelectionMode.NONE)
                flow.set_row_spacing(8)
                flow.set_column_spacing(8)
                for side in ("top", "bottom", "start", "end"):
                    getattr(flow, f"set_margin_{side}")(10)
                scroller.add(flow)
                
                empty = Gtk.Label(label="No blocks match search.")
                empty.set_no_show_all(True)
                
                # Split columns
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                content.pack_start(hbox, True, True, 0)
                
                left_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                hbox.pack_start(left_vbox, True, True, 0)
                left_vbox.pack_start(search, False, False, 0)
                left_vbox.pack_start(scroller, True, True, 0)
                left_vbox.pack_start(empty, False, False, 4)
                
                right_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                right_vbox.set_size_request(340, -1)
                right_vbox.set_margin_top(10)
                right_vbox.set_margin_bottom(10)
                right_vbox.set_margin_end(10)
                hbox.pack_start(right_vbox, False, False, 0)
                
                # Combo Boxes
                sizing_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                sizing_lbl = Gtk.Label(label="Sizing Mode:")
                sizing_combo = Gtk.ComboBoxText()
                sizing_combo.append("stretch", "Stretch to fit")
                sizing_combo.append("cover", "Proportional Crop (Cover)")
                sizing_combo.append("tile_stretch", "Tile (stretch to fit even tiles)")
                sizing_combo.append("tile_ratio", "Tile (keep ratio, crop ends)")
                active_idx = 0
                for idx, mode in enumerate(["stretch", "cover", "tile_stretch", "tile_ratio"]):
                    if settings["sizing_mode"] == mode:
                        active_idx = idx
                sizing_combo.set_active(active_idx)
                sizing_box.pack_start(sizing_lbl, False, False, 0)
                sizing_box.pack_start(sizing_combo, True, True, 0)
                right_vbox.pack_start(sizing_box, False, False, 0)
                
                align_check = Gtk.CheckButton(label="Auto-align to region (longest edge)")
                align_check.set_active(settings["auto_align"])
                right_vbox.pack_start(align_check, False, False, 0)
                
                rot_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                rot_lbl = Gtk.Label(label="Additional Rotation:")
                rot_combo = Gtk.ComboBoxText()
                for deg in ["0", "45", "90", "135", "180", "270"]:
                    rot_combo.append(deg, f"{deg}°")
                active_idx = 0
                for idx, deg in enumerate(["0", "45", "90", "135", "180", "270"]):
                    if abs(float(deg) - settings["rotation"]) < 0.1:
                        active_idx = idx
                rot_combo.set_active(active_idx)
                rot_box.pack_start(rot_lbl, False, False, 0)
                rot_box.pack_start(rot_combo, True, True, 0)
                right_vbox.pack_start(rot_box, False, False, 0)
                
                flip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                flip_lbl = Gtk.Label(label="Flip:")
                flip_combo = Gtk.ComboBoxText()
                flip_combo.append("none", "None")
                flip_combo.append("horizontal", "Horizontal")
                flip_combo.append("vertical", "Vertical")
                active_flip = 0
                if settings["flip"] == "horizontal":
                    active_flip = 1
                elif settings["flip"] == "vertical":
                    active_flip = 2
                flip_combo.set_active(active_flip)
                flip_box.pack_start(flip_lbl, False, False, 0)
                flip_box.pack_start(flip_combo, True, True, 0)
                right_vbox.pack_start(flip_box, False, False, 0)
                
                # Preview Draw Area
                preview_label = Gtk.Label(label="Live Preview:")
                preview_label.set_halign(Gtk.Align.START)
                right_vbox.pack_start(preview_label, False, False, 0)
                
                preview_area = Gtk.DrawingArea()
                preview_area.set_size_request(300, 300)
                right_vbox.pack_start(preview_area, True, True, 0)
                
                # Library Data Cache
                lib_bd_cache = {}
                labels_by_child = {}
                
                def make_click(p):
                    def _cb(_btn):
                        chosen["path"] = p
                        preview_area.queue_draw()
                    return _cb
                
                def make_double_click(p):
                    def _cb(_btn, event):
                        if event.button == 1 and event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
                            chosen["path"] = p
                            dialog.response(Gtk.ResponseType.OK)
                            return True
                        return False
                    return _cb
                
                for label, full in blocks:
                    btn = Gtk.Button()
                    btn.set_relief(Gtk.ReliefStyle.NONE)
                    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                    try:
                        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(full, 120, 120, True)
                        box.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
                    except Exception:
                        pass
                    lbl = Gtk.Label(label=label)
                    lbl.set_line_wrap(True)
                    lbl.set_max_width_chars(15)
                    lbl.set_justify(Gtk.Justification.CENTER)
                    box.pack_start(lbl, False, False, 0)
                    btn.add(box)
                    btn.set_tooltip_text(label)
                    btn.connect("clicked", make_click(full))
                    btn.connect("button-press-event", make_double_click(full))
                    flow.add(btn)
                    labels_by_child[btn.get_parent()] = label.lower()
                    
                def do_filter(child):
                    q = search.get_text().strip().lower()
                    if not q:
                        return True
                    return q in labels_by_child.get(child, "")
                
                flow.set_filter_func(do_filter)
                
                def on_search(_w):
                    flow.invalidate_filter()
                    any_visible = any(do_filter(c) for c in labels_by_child)
                    empty.set_visible(not any_visible)
                search.connect("search-changed", on_search)
                
                def on_draw(widget, ctx):
                    w_a = widget.get_allocated_width()
                    h_a = widget.get_allocated_height()
                    ctx.set_source_rgb(0.98, 0.98, 0.98)
                    ctx.paint()
                    
                    poly = target_regions[0].polygon
                    xs = [p[0] for p in poly]
                    ys = [p[1] for p in poly]
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)
                    pw = max_x - min_x
                    ph = max_y - min_y
                    if pw <= 0 or ph <= 0:
                        return
                    
                    s = min((w_a - 20) / pw, (h_a - 20) / ph)
                    tx = 10 + (w_a - 20 - pw * s) / 2.0 - min_x * s
                    ty = 10 + (h_a - 20 - ph * s) / 2.0 - min_y * s
                    
                    def to_screen(p):
                        return (p[0] * s + tx, p[1] * s + ty)
                    
                    # Fill target region
                    ctx.set_source_rgb(0.92, 0.92, 0.92)
                    sp0 = to_screen(poly[0])
                    ctx.move_to(sp0[0], sp0[1])
                    for pt in poly[1:]:
                        s_pt = to_screen(pt)
                        ctx.line_to(s_pt[0], s_pt[1])
                    ctx.close_path()
                    ctx.fill_preserve()
                    ctx.set_source_rgb(0.4, 0.4, 0.4)
                    ctx.set_line_width(2.0)
                    ctx.stroke()
                    
                    if chosen["path"] and os.path.exists(chosen["path"]):
                        try:
                            path = chosen["path"]
                            if path not in lib_bd_cache:
                                doc_lib = etree.parse(path)
                                lib_bd_cache[path] = core.extract_block_data_from_svg_root(doc_lib.getroot())
                            lib_bd = lib_bd_cache[path]
                            
                            sm = sizing_combo.get_active_id()
                            aa = align_check.get_active()
                            rot = float(rot_combo.get_active_id() or 0.0)
                            flp = flip_combo.get_active_id()
                            
                            temp_tree = core.RegionTree(poly)
                            temp_reg = temp_tree.regions[temp_tree.root_id]
                            
                            core.import_block_into_region(temp_tree, temp_reg, lib_bd, sm, rot, flp, aa)
                            
                            # Draw sub-regions
                            ctx.set_line_width(1.0)
                            for idx, r in enumerate(temp_tree.leaf_regions()):
                                r_poly = r.polygon
                                if len(r_poly) < 3:
                                    continue
                                col = core.get_color_for_label(r.label, "piece", idx)
                                col_hex = col.lstrip("#")
                                r_v = int(col_hex[0:2], 16) / 255.0
                                g_v = int(col_hex[2:4], 16) / 255.0
                                b_v = int(col_hex[4:6], 16) / 255.0
                                
                                ctx.set_source_rgb(r_v, g_v, b_v)
                                sp = to_screen(r_poly[0])
                                ctx.move_to(sp[0], sp[1])
                                for pt in r_poly[1:]:
                                    s_pt = to_screen(pt)
                                    ctx.line_to(s_pt[0], s_pt[1])
                                ctx.close_path()
                                ctx.fill_preserve()
                                ctx.set_source_rgb(0.1, 0.1, 0.1)
                                ctx.stroke()
                                
                            # Draw curves
                            if hasattr(temp_tree, "curves") and temp_tree.curves:
                                ctx.set_source_rgb(0.1, 0.3, 0.9)
                                ctx.set_line_width(2.0)
                                for curve in temp_tree.curves:
                                    if len(curve) < 2:
                                        continue
                                    sp = to_screen(curve[0])
                                    ctx.move_to(sp[0], sp[1])
                                    for pt in curve[1:]:
                                        s_pt = to_screen(pt)
                                        ctx.line_to(s_pt[0], s_pt[1])
                                    ctx.stroke()
                        except Exception as ex:
                            ctx.set_source_rgb(0.9, 0.1, 0.1)
                            ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                            ctx.set_font_size(11)
                            ctx.move_to(15, h_a / 2)
                            ctx.show_text(f"Error: {str(ex)[:40]}")
                            
                preview_area.connect("draw", on_draw)
                
                def on_setting_changed(_w):
                    preview_area.queue_draw()
                
                sizing_combo.connect("changed", on_setting_changed)
                align_check.connect("toggled", on_setting_changed)
                rot_combo.connect("changed", on_setting_changed)
                flip_combo.connect("changed", on_setting_changed)
                
                dialog.add_button("Browse files\u2026", 100)
                dialog.add_button("Import", Gtk.ResponseType.OK)
                dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
                dialog.show_all()
                search.grab_focus()
                
                while True:
                    resp = dialog.run()
                    if resp == 100:
                        fc = Gtk.FileChooserDialog(
                            title="Choose a block SVG",
                            parent=dialog,
                            action=Gtk.FileChooserAction.OPEN,
                        )
                        fc.add_button("Cancel", Gtk.ResponseType.CANCEL)
                        fc.add_button("Open", Gtk.ResponseType.OK)
                        try:
                            fc.set_current_folder(LIB_DIR)
                        except Exception:
                            pass
                        flt = Gtk.FileFilter()
                        flt.set_name("SVG blocks")
                        flt.add_pattern("*.svg")
                        fc.add_filter(flt)
                        fresp = fc.run()
                        if fresp == Gtk.ResponseType.OK:
                            chosen["path"] = fc.get_filename()
                        fc.destroy()
                        if chosen["path"]:
                            preview_area.queue_draw()
                        continue
                    elif resp == Gtk.ResponseType.OK:
                        # Grab finalized settings from GTK dialog controls
                        settings["sizing_mode"] = sizing_combo.get_active_id()
                        settings["auto_align"] = align_check.get_active()
                        settings["rotation"] = float(rot_combo.get_active_id() or 0.0)
                        settings["flip"] = flip_combo.get_active_id()
                        break
                    else:
                        chosen["path"] = None
                        break
                dialog.destroy()
            except Exception as e:
                # No GTK or GTK error: use fallback options
                inkex.utils.debug(f"GTK visual picker disabled or failed: {e}")
                
        # 4. Perform Import Subdivision
        import_path = chosen["path"]
        if not import_path:
            return inkex.utils.debug("Import cancelled: No block selected.")
            
        if not os.path.isfile(import_path):
            return inkex.errormsg(f"Block file does not exist:\n  {import_path}")
            
        try:
            doc_lib = etree.parse(import_path)
            lib_bd = core.extract_block_data_from_svg_root(doc_lib.getroot())
            if lib_bd is None:
                return inkex.errormsg("The selected file is not a valid Quilt Tools block (no block metadata).")
        except Exception as e:
            return inkex.errormsg(f"Could not load library block:\n  {e}")
            
        # Apply subdivision to all selected regions
        total_subdivisions = 0
        for r_target in target_regions:
            subdivisions = core.import_block_into_region(
                block_data.tree,
                r_target,
                lib_bd,
                sizing_mode=settings["sizing_mode"],
                rotation=settings["rotation"],
                flip=settings["flip"],
                auto_align=settings["auto_align"]
            )
            total_subdivisions += subdivisions
            
        if total_subdivisions == 0:
            return inkex.errormsg("Import failed: No sub-regions could be placed inside the selection.")
            
        # Re-sequence labels and refresh
        block_data.tree.rebuild_alphabet()
        core.refresh_layer(g, block_data)
        inkex.utils.debug(f"Successfully subdivided {len(target_regions)} region(s) with '{os.path.basename(import_path)}' ({total_subdivisions} new sub-regions created).")


if __name__ == "__main__":
    ImportIntoPlugin().run()
