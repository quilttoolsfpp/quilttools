#!/usr/bin/env python3
import os
import sys
import re
import math
import copy
from lxml import etree
import inkex

# Ensure extension path is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import quilttools_fpp_core as core
import quilttools_theme as qtheme
import quilttools_quilt_core as qcore
import quilttools_placement as qplace

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


class FillBlocksPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--notebook", type=str, default="selection_page")
        pars.add_argument("--svg_file", type=str, default="")
        pars.add_argument("--sizing_mode", type=str, default="stretch")
        pars.add_argument("--auto_align", type=inkex.Boolean, default=True)
        pars.add_argument("--rotation", type=float, default=0.0)
        pars.add_argument("--flip", type=str, default="none")
        pars.add_argument("--theme_override", type=str, default="")

    def effect(self):
        # 1. Identify quilt layer
        g_quilt, quilt_data = qcore.find_quilt_group(self.svg)
        if g_quilt is None:
            return inkex.errormsg("No Quilt Layout layer found. Run '02. New Quilt' first.")

        # 2. Identify selected cells
        selected_cell_ids = set()
        for el in self.svg.selection.values():
            cur = el
            while cur is not None and cur != self.svg:
                cid = cur.get("id")
                if cid and cid in quilt_data.cells:
                    selected_cell_ids.add(cid)
                    break
                cur = cur.getparent()

        if not selected_cell_ids:
            return inkex.errormsg("No quilt grid cells selected. Please select one or more block cells (e.g. '1-1') to fill.")

        # Filter out non-block roles (sashing, borders, binding shouldn't be filled with library blocks)
        block_cell_ids = [cid for cid in selected_cell_ids if quilt_data.cells[cid]["role"] == "block"]
        if not block_cell_ids:
            return inkex.errormsg("None of the selected layout cells are block cells. You can only place library blocks into Block grid cells.")

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
                
                dialog = Gtk.Dialog(title="Quilt Tools Pattern - Fill Blocks from Library")
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
                sizing_combo.set_active(0 if settings["sizing_mode"] == "stretch" else 1)
                sizing_box.pack_start(sizing_lbl, False, False, 0)
                sizing_box.pack_start(sizing_combo, True, True, 0)
                right_vbox.pack_start(sizing_box, False, False, 0)
                
                align_check = Gtk.CheckButton(label="Auto-align to cell orientation")
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
                    
                    # Draw target cell polygon outline
                    poly = quilt_data.cells[block_cell_ids[0]]["polygon"]
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
                                desc_el = doc_lib.getroot().find(f".//{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
                                if desc_el is not None and desc_el.text:
                                    lib_bd_cache[path] = core.BlockData.from_json(desc_el.text)
                                else:
                                    lib_bd_cache[path] = None
                            
                            lib_bd = lib_bd_cache[path]
                            if lib_bd and lib_bd.tree:
                                sm = sizing_combo.get_active_id()
                                aa = align_check.get_active()
                                rot = float(rot_combo.get_active_id() or 0.0)
                                flp = flip_combo.get_active_id()
                                
                                lib_regions = lib_bd.tree.leaf_regions()
                                all_L_pts = [pt for r in lib_regions for pt in r.polygon]
                                map_pt, _ = qplace.calculate_placement_transform(all_L_pts, poly, sm, rot, flp, aa)
                                
                                # Draw sub-regions
                                ctx.set_line_width(1.0)
                                for idx, r in enumerate(lib_regions):
                                    r_poly = [map_pt(p) for p in r.polygon]
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
                dialog.add_button("Fill Selected Cells", Gtk.ResponseType.OK)
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
                # GTK failed or headless fallback
                inkex.utils.debug(f"GTK picker skipped: {e}")
                
        # 4. Perform Placement
        import_path = chosen["path"]
        if not import_path:
            return inkex.utils.debug("Fill cancelled: No block selected.")
            
        if not os.path.isfile(import_path):
            return inkex.errormsg(f"Block file does not exist:\n  {import_path}")
            
        try:
            doc_lib = etree.parse(import_path)
            # Try to get block_kind from BlockData desc
            desc_el = doc_lib.getroot().find(f".//{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
            lib_bd = None
            if desc_el is not None and desc_el.text:
                lib_bd = core.BlockData.from_json(desc_el.text)
                
            block_kind = "fpp"
            if lib_bd and "block_kind" in lib_bd.prefs:
                block_kind = lib_bd.prefs["block_kind"]
        except Exception as e:
            return inkex.errormsg(f"Could not load selected block file: {e}")
            
        # Get source geometry polygon coordinates
        all_L_pts = []
        if lib_bd and lib_bd.tree:
            lib_regions = lib_bd.tree.leaf_regions()
            all_L_pts = [pt for r in lib_regions for pt in r.polygon]
        if not all_L_pts:
            # Fallback: width/height bounds of library root
            lib_w = self.svg.unittouu(doc_lib.getroot().get("width") or "100px")
            lib_h = self.svg.unittouu(doc_lib.getroot().get("height") or "100px")
            all_L_pts = [(0, 0), (lib_w, 0), (lib_w, lib_h), (0, lib_h)]
            
        # Identify the library block's main content group
        g_lib = doc_lib.getroot().find(f".//{{{core.SVG_NS}}}g[@id='fpp-quilttools-layer']")
        if g_lib is None:
            g_lib = doc_lib.getroot().find(f".//{{{core.SVG_NS}}}g[@label='fpp-quilttools-layer']")
        if g_lib is None:
            # Copy all children of root (excluding defs, metadata, desc, namedview)
            g_lib = etree.Element("{%s}g" % core.SVG_NS)
            for child in doc_lib.getroot():
                if child.tag not in (f"{{{core.SVG_NS}}}defs", f"{{{core.SVG_NS}}}metadata", f"{{{core.SVG_NS}}}desc", "{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview"):
                    g_lib.append(copy.deepcopy(child))
                    
        # Apply transformation and insert block to each target cell
        rel_path = os.path.relpath(import_path, LIB_DIR) if import_path.startswith(LIB_DIR) else os.path.basename(import_path)
        
        filled_count = 0
        for cell_id in block_cell_ids:
            # 1. Find group on canvas
            g_cell = g_quilt.find(f".//{{{core.SVG_NS}}}g[@id='{cell_id}']")
            if g_cell is None:
                continue
                
            # Remove any existing placed block element
            for placed_el in list(g_cell.findall(f".//{{{core.SVG_NS}}}g[@class='placed-block-content']")):
                g_cell.remove(placed_el)
            for placed_el in list(g_cell.findall(f".//{{{core.SVG_NS}}}g")):
                if placed_el.get("id") == f"{cell_id}-placed":
                    g_cell.remove(placed_el)
                    
            # 2. Compute placement matrix
            poly = quilt_data.cells[cell_id]["polygon"]
            _, transform_matrix_str = qplace.calculate_placement_transform(
                all_L_pts,
                poly,
                sizing_mode=settings["sizing_mode"],
                rotation=settings["rotation"],
                flip=settings["flip"],
                auto_align=settings["auto_align"]
            )
            
            # 3. Create content group and clone children
            g_placed = etree.SubElement(g_cell, "{%s}g" % core.SVG_NS, id=f"{cell_id}-placed", attrib={
                "transform": transform_matrix_str,
                "class": "placed-block-content"
            })
            for child in g_lib:
                if child.tag in (f"{{{core.SVG_NS}}}desc", f"{{{core.SVG_NS}}}title", f"{{{core.SVG_NS}}}metadata"):
                    continue
                g_placed.append(copy.deepcopy(child))
                
            # 4. Update serialised registry state
            quilt_data.cells[cell_id]["state"] = "placed"
            quilt_data.cells[cell_id]["placed_block"] = {
                "source": rel_path,
                "block_kind": block_kind,
                "rotation": settings["rotation"],
                "flip": settings["flip"],
                "sizing_mode": settings["sizing_mode"]
            }
            filled_count += 1
            
        # Save updated metadata
        desc_el = g_quilt.find(f"{{{core.SVG_NS}}}desc[@id='{qcore.QUILT_DATA_TAG_ID}']")
        if desc_el is not None:
            desc_el.text = quilt_data.to_json()
            
        inkex.utils.debug(f"Successfully filled {filled_count} cell(s) with '{os.path.basename(import_path)}'.")

if __name__ == "__main__":
    FillBlocksPlugin().run()
