#!/usr/bin/env python3
import inkex
from lxml import etree
import json
import os
import math
import quilttools_fpp_core as core
import quilttools_theme as qtheme
import quilttools_quilt_core as qcore

LAYOUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LayoutLibrary")

# the very important pattern manager
STANDARD_LAYOUTS = {
    "Baby": [
        {
            "name": "Baby Star Bloom (18\" Blocks)",
            "description": "2x2 grid of 18\" blocks, with a 2\" horizontal-first border and a 4.5\" cornerstone border. Finished size: approx 50\" x 50\".",
            "setting": "straight",
            "grid_rows": 2, "grid_cols": 2,
            "cell_w_in": 18.0, "cell_h_in": 18.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 2.0, "border_1_style": "long_h",
            "border_2_in": 4.5, "border_2_style": "cornerstone",
            "border_3_in": 0.0, "border_3_style": "long_h",
            "binding_w_in": 0.25
        },
        {
            "name": "Baby Simple Square (6\" Blocks)",
            "description": "6x6 straight grid with no sashing or borders. Perfect for a quick, charming baby quilt.",
            "setting": "straight",
            "grid_rows": 6, "grid_cols": 6,
            "cell_w_in": 6.0, "cell_h_in": 6.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 0.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Baby Large Grid (10\" Blocks)",
            "description": "4x5 straight grid of larger 10\" blocks. Showcases large-scale prints beautifully.",
            "setting": "straight",
            "grid_rows": 5, "grid_cols": 4,
            "cell_w_in": 10.0, "cell_h_in": 10.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 0.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Baby Framed (12\" Blocks + Sashing)",
            "description": "3x3 straight grid of 12\" blocks framed with 2\" sashing and a 3\" outer border.",
            "setting": "straight",
            "grid_rows": 3, "grid_cols": 3,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 2.0, "cornerstones": True,
            "border_1_in": 3.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Baby On-Point (6\" Blocks)",
            "description": "4x4 on-point grid of 6\" blocks with a 2.75\" border. Finished size: approx 40\" x 40\".",
            "setting": "on-point",
            "grid_rows": 4, "grid_cols": 4,
            "cell_w_in": 6.0, "cell_h_in": 6.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 2.75, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        }
    ],
    "Toddler": [
        {
            "name": "Toddler Playtime (6\" Blocks)",
            "description": "6x9 straight grid of 6\" blocks. A classic rectangular size for toddlers.",
            "setting": "straight",
            "grid_rows": 9, "grid_cols": 6,
            "cell_w_in": 6.0, "cell_h_in": 6.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 0.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Toddler Cozy (10\" Blocks)",
            "description": "4x6 straight grid of 10\" blocks. Easy and fast to sew.",
            "setting": "straight",
            "grid_rows": 6, "grid_cols": 4,
            "cell_w_in": 10.0, "cell_h_in": 10.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 0.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Toddler Framed (8\" Blocks + Sashing)",
            "description": "4x6 grid of 8\" blocks with 1.5\" sashing and a 4\" outer border.",
            "setting": "straight",
            "grid_rows": 6, "grid_cols": 4,
            "cell_w_in": 8.0, "cell_h_in": 8.0,
            "sashing_w_in": 1.5, "cornerstones": True,
            "border_1_in": 4.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Toddler Squares (5.5\" Blocks)",
            "description": "8x10 grid of 5.5\" blocks with a 2.75\" border. Finished size: approx 50\" x 61\".",
            "setting": "straight",
            "grid_rows": 10, "grid_cols": 8,
            "cell_w_in": 5.5, "cell_h_in": 5.5,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 2.75, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Toddler On-Point (9\" Blocks)",
            "description": "3x4 on-point grid of 9\" blocks with a 3.75\" border. Finished size: approx 46\" x 59\".",
            "setting": "on-point",
            "grid_rows": 4, "grid_cols": 3,
            "cell_w_in": 9.0, "cell_h_in": 9.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 3.75, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        }
    ],
    "Twin": [
        {
            "name": "Twin Classic (10\" Blocks)",
            "description": "6x8 grid of 10\" blocks with a 2\" border. Finished size: 64\" x 84\".",
            "setting": "straight",
            "grid_rows": 8, "grid_cols": 6,
            "cell_w_in": 10.0, "cell_h_in": 10.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 2.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Twin Framed (12\" Blocks + Sashing)",
            "description": "5x7 grid of 12\" blocks with 2\" sashing and a 4\" outer border. Finished size: 78\" x 104\".",
            "setting": "straight",
            "grid_rows": 7, "grid_cols": 5,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 2.0, "cornerstones": True,
            "border_1_in": 4.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Twin Mosaic (6\" Blocks + Sashing)",
            "description": "10x14 grid of 6\" blocks with 1\" sashing and a 3\" outer border. Finished size: 75\" x 103\".",
            "setting": "straight",
            "grid_rows": 14, "grid_cols": 10,
            "cell_w_in": 6.0, "cell_h_in": 6.0,
            "sashing_w_in": 1.0, "cornerstones": True,
            "border_1_in": 3.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Twin On-Point (12\" Blocks)",
            "description": "3x4 on-point grid of 12\" blocks with a 5.75\" border. Finished size: approx 63\" x 80\".",
            "setting": "on-point",
            "grid_rows": 4, "grid_cols": 3,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 5.75, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        }
    ],
    "Full": [
        {
            "name": "Full Simple (12\" Blocks)",
            "description": "6x7 grid of 12\" blocks with a 3\" border. Finished size: 78\" x 90\".",
            "setting": "straight",
            "grid_rows": 7, "grid_cols": 6,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 3.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Full Framed (10\" Blocks + Sashing)",
            "description": "7x8 grid of 10\" blocks with 1.5\" sashing and a 4\" outer border. Finished size: 87.5\" x 99.5\".",
            "setting": "straight",
            "grid_rows": 8, "grid_cols": 7,
            "cell_w_in": 10.0, "cell_h_in": 10.0,
            "sashing_w_in": 1.5, "cornerstones": True,
            "border_1_in": 4.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Full On-Point (12\" Blocks)",
            "description": "4x5 on-point grid of 12\" blocks with a 4.75\" border. Finished size: approx 78\" x 95\".",
            "setting": "on-point",
            "grid_rows": 5, "grid_cols": 4,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 4.75, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        }
    ],
    "Queen": [
        {
            "name": "Queen Simple (12\" Blocks)",
            "description": "7x7 grid of 12\" blocks with a 3\" border. Finished size: 90\" x 90\".",
            "setting": "straight",
            "grid_rows": 7, "grid_cols": 7,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 3.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Queen Framed (10\" Blocks + Sashing)",
            "description": "8x8 grid of 10\" blocks with 1.5\" sashing and a 4\" outer border. Finished size: 99.5\" x 99.5\".",
            "setting": "straight",
            "grid_rows": 8, "grid_cols": 8,
            "cell_w_in": 10.0, "cell_h_in": 10.0,
            "sashing_w_in": 1.5, "cornerstones": True,
            "border_1_in": 4.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "Queen On-Point (12\" Blocks)",
            "description": "5x5 on-point grid of 12\" blocks with a 3.75\" border. Finished size: approx 93\" x 93\".",
            "setting": "on-point",
            "grid_rows": 5, "grid_cols": 5,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 3.75, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        }
    ],
    "King": [
        {
            "name": "King Simple (12\" Blocks)",
            "description": "8x8 grid of 12\" blocks with a 4\" border. Finished size: 104\" x 104\".",
            "setting": "straight",
            "grid_rows": 8, "grid_cols": 8,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 4.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "King Framed (10\" Blocks + Sashing)",
            "description": "9x9 grid of 10\" blocks with 2\" sashing and a 5\" outer border. Finished size: 118\" x 118\".",
            "setting": "straight",
            "grid_rows": 9, "grid_cols": 9,
            "cell_w_in": 10.0, "cell_h_in": 10.0,
            "sashing_w_in": 2.0, "cornerstones": True,
            "border_1_in": 5.0, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        },
        {
            "name": "King On-Point (12\" Blocks)",
            "description": "6x6 on-point grid of 12\" blocks with a 3.75\" border. Finished size: approx 110\" x 110\".",
            "setting": "on-point",
            "grid_rows": 6, "grid_cols": 6,
            "cell_w_in": 12.0, "cell_h_in": 12.0,
            "sashing_w_in": 0.0, "cornerstones": False,
            "border_1_in": 3.75, "border_2_in": 0.0, "border_3_in": 0.0,
            "binding_w_in": 0.25
        }
    ]
}

def scan_custom_layouts():
    found = []
    if not os.path.isdir(LAYOUT_DIR):
        return found
    for fn in os.listdir(LAYOUT_DIR):
        if fn.lower().endswith(".json"):
            path = os.path.join(LAYOUT_DIR, fn)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    spec = json.load(fh)
                    spec["path"] = path
                    found.append(spec)
            except Exception:
                pass
    return found

def save_layout(name, options):
    os.makedirs(LAYOUT_DIR, exist_ok=True)
    filename = "".join(c if (c.isalnum() or c in (" ", "-", "_")) else "_" for c in name).strip()
    path = os.path.join(LAYOUT_DIR, filename + ".json")
    spec = {
        "name": name,
        "description": f"Custom layout: Grid: {options.grid_rows}x{options.grid_cols}, Block: {options.cell_w_in}\"x{options.cell_h_in}\"",
        "setting": options.setting,
        "grid_rows": options.grid_rows,
        "grid_cols": options.grid_cols,
        "cell_w_in": options.cell_w_in,
        "cell_h_in": options.cell_h_in,
        "sashing_w_in": options.sashing_w_in,
        "cornerstones": options.cornerstones,
        "border_1_in": options.border_1_in,
        "border_1_style": options.border_1_style,
        "border_2_in": options.border_2_in,
        "border_2_style": options.border_2_style,
        "border_3_in": options.border_3_in,
        "border_3_style": options.border_3_style,
        "binding_w_in": options.binding_w_in
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)

class NewQuiltPlugin(inkex.Effect):
    # the very important pattern manager
    def _pick_layout_gtk(self):
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, Gdk
        except Exception:
            return self._pick_layout_tk()

        chosen = {"layout": None, "block_path": None}

        try:
            dialog = Gtk.Dialog(title="Quilt Tools - Select Quilt Layout")
            dialog.set_default_size(760, 600)
            content = dialog.get_content_area()
            content.set_spacing(6)

            header = Gtk.Label()
            header.set_markup(
                "<span size='large' weight='bold'>Choose Quilt Layout</span>\n"
                "Select a standard size or load a custom saved quilt layout."
            )
            header.set_justify(Gtk.Justification.CENTER)
            header.set_margin_top(8)
            content.pack_start(header, False, False, 0)

            notebook = Gtk.Notebook()
            content.pack_start(notebook, True, True, 0)

            customs = scan_custom_layouts()
            categories = ["Baby", "Toddler", "Twin", "Full", "Queen", "King", "Saved Layouts"]
            
            def make_select_cb(layout_data):
                def _cb(_btn):
                    chosen["layout"] = layout_data
                    dialog.response(Gtk.ResponseType.OK)
                return _cb

            for cat in categories:
                scroller = Gtk.ScrolledWindow()
                scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
                
                flow = Gtk.FlowBox()
                flow.set_valign(Gtk.Align.START)
                flow.set_max_children_per_line(2)
                flow.set_selection_mode(Gtk.SelectionMode.NONE)
                flow.set_row_spacing(10)
                flow.set_column_spacing(10)
                for side in ("top", "bottom", "start", "end"):
                    getattr(flow, f"set_margin_{side}")(12)

                if cat == "Saved Layouts":
                    items = customs
                else:
                    items = STANDARD_LAYOUTS.get(cat, [])

                for item in items:
                    btn = Gtk.Button()
                    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                    box.set_margin_top(8)
                    box.set_margin_bottom(8)
                    box.set_margin_start(8)
                    box.set_margin_end(8)

                    lbl_name = Gtk.Label()
                    lbl_name.set_markup(f"<span weight='bold' size='medium'>{item['name']}</span>")
                    lbl_name.set_halign(Gtk.Align.START)
                    box.pack_start(lbl_name, False, False, 0)

                    if item.get("setting") == "on-point":
                        S = item["cell_w_in"]
                        D_step = (S + item["sashing_w_in"]) * math.sqrt(2)
                        grid_w = item["grid_cols"] * D_step
                        grid_h = item["grid_rows"] * D_step
                    else:
                        grid_w = item["grid_cols"] * item["cell_w_in"] + (item["grid_cols"] - 1) * item["sashing_w_in"]
                        grid_h = item["grid_rows"] * item["cell_h_in"] + (item["grid_rows"] - 1) * item["sashing_w_in"]
                    total_border = item["border_1_in"] + item["border_2_in"] + item["border_3_in"] + item["binding_w_in"]
                    fin_w = grid_w + 2 * total_border
                    fin_h = grid_h + 2 * total_border

                    lbl_dims = Gtk.Label()
                    lbl_dims.set_markup(f"<span color='#0066cc' weight='bold'>Est. Finished Size: {fin_w:.1f}\" x {fin_h:.1f}\"</span>")
                    lbl_dims.set_halign(Gtk.Align.START)
                    box.pack_start(lbl_dims, False, False, 0)

                    desc_txt = (
                        f"{item['grid_rows']}x{item['grid_cols']} Grid • "
                        f"{item['cell_w_in']}\"x{item['cell_h_in']}\" Blocks"
                    )
                    if item["sashing_w_in"] > 0:
                        desc_txt += f" • {item['sashing_w_in']}\" Sashing"
                    if total_border > 0:
                        desc_txt += f" • {total_border}\" Border/Binding"
                    
                    lbl_spec = Gtk.Label(label=desc_txt)
                    lbl_spec.set_halign(Gtk.Align.START)
                    box.pack_start(lbl_spec, False, False, 0)

                    if item.get("description"):
                        lbl_desc = Gtk.Label(label=item["description"])
                        lbl_desc.set_line_wrap(True)
                        lbl_desc.set_max_width_chars(50)
                        lbl_desc.set_halign(Gtk.Align.START)
                        box.pack_start(lbl_desc, False, False, 0)

                    btn.add(box)
                    btn.connect("clicked", make_select_cb(item))
                    flow.add(btn)

                if cat == "Saved Layouts" and not customs:
                    empty_lbl = Gtk.Label(label="No custom layouts saved yet.\nClick 'Save Current Layout' below to save yours!")
                    empty_lbl.set_justify(Gtk.Justification.CENTER)
                    empty_lbl.set_margin_top(20)
                    scroller.add(empty_lbl)
                else:
                    scroller.add(flow)

                notebook.append_page(scroller, Gtk.Label(label=cat))

            action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            action_box.set_margin_top(8)
            action_box.set_margin_bottom(8)
            action_box.set_margin_start(10)
            action_box.set_margin_end(10)
            content.pack_start(action_box, False, False, 0)

            btn_override = Gtk.Button(label="Override with Block...")
            btn_override.set_tooltip_text("Use any FPP block shape as a custom layout.")
            
            def on_override_clicked(_btn):
                file_dialog = Gtk.FileChooserDialog(
                    title="Select FPP Block for Quilt Layout",
                    parent=dialog,
                    action=Gtk.FileChooserAction.OPEN
                )
                file_dialog.add_buttons(
                    "Cancel", Gtk.ResponseType.CANCEL,
                    "Open", Gtk.ResponseType.OK
                )
                filter_svg = Gtk.FileFilter()
                filter_svg.set_name("SVG files")
                filter_svg.add_mime_type("image/svg+xml")
                filter_svg.add_pattern("*.svg")
                file_dialog.add_filter(filter_svg)
                
                ext_dir = os.path.dirname(os.path.abspath(__file__))
                block_lib = os.path.join(ext_dir, "BlockLibrary")
                if os.path.isdir(block_lib):
                    file_dialog.set_current_folder(block_lib)
                    
                response = file_dialog.run()
                if response == Gtk.ResponseType.OK:
                    chosen["block_path"] = file_dialog.get_filename()
                    dialog.response(Gtk.ResponseType.OK)
                file_dialog.destroy()
                
            btn_override.connect("clicked", on_override_clicked)
            action_box.pack_start(btn_override, False, False, 0)

            btn_save = Gtk.Button(label="Save Current Layout...")
            btn_save.set_tooltip_text("Save the grid, sashing, and border settings from the dialog as a custom layout preset.")
            
            def on_save_clicked(_btn):
                entry_dialog = Gtk.MessageDialog(
                    transient_for=dialog,
                    modal=True,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.OK_CANCEL,
                    text="Enter a name for this custom layout:"
                )
                entry = Gtk.Entry()
                entry.set_text("My Custom Layout")
                entry_dialog.get_content_area().pack_end(entry, False, False, 0)
                entry_dialog.show_all()
                res = entry_dialog.run()
                if res == Gtk.ResponseType.OK:
                    name = entry.get_text().strip()
                    if name:
                        save_layout(name, self.options)
                        info_msg = Gtk.MessageDialog(
                            transient_for=dialog,
                            modal=True,
                            message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK,
                            text=f"Layout '{name}' saved successfully!"
                        )
                        info_msg.run()
                        info_msg.destroy()
                entry_dialog.destroy()
                
            btn_save.connect("clicked", on_save_clicked)
            action_box.pack_start(btn_save, False, False, 0)

            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.set_modal(True)
            dialog.set_keep_above(True)
            dialog.show_all()
            dialog.present()

            response = dialog.run()
            dialog.destroy()
            while Gtk.events_pending():
                Gtk.main_iteration()
                
            if response == Gtk.ResponseType.OK:
                return chosen
        except Exception as e:
            try:
                return self._pick_layout_tk()
            except Exception:
                inkex.utils.debug(f"Layout Picker Dialog error: {e}")
            
        return None

    def _pick_layout_tk(self):
        import tkinter as tk
        from tkinter import ttk, filedialog

        layouts = _discover_layouts()
        chosen = {"layout": None, "block_path": None}

        root = tk.Tk()
        root.title("Quilt Tools - Select Quilt Layout")
        root.geometry("680x520")
        root.minsize(540, 420)
        root.attributes("-topmost", True)

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        hdr_frame = ttk.Frame(root, padding=10)
        hdr_frame.pack(fill="x")
        ttk.Label(hdr_frame, text="Choose Quilt Layout", font=("sans-serif", 13, "bold")).pack()
        ttk.Label(hdr_frame, text="Select a standard layout or load a custom layout", foreground="#666666").pack()

        notebook = ttk.Notebook(root, padding=5)
        notebook.pack(fill="both", expand=True, padx=10, pady=5)

        selected_item = {"val": None}

        for cat, items in layouts.items():
            frame = ttk.Frame(notebook, padding=10)
            notebook.add(frame, text=cat)

            tree_scroller = ttk.Scrollbar(frame, orient="vertical")
            tree_view = ttk.Treeview(frame, columns=("dimensions", "description"), selectmode="browse", yscrollcommand=tree_scroller.set)
            tree_scroller.config(command=tree_view.yview)

            tree_view.heading("#0", text="Layout Name")
            tree_view.heading("dimensions", text="Block & Grid Size")
            tree_view.heading("description", text="Description")

            tree_view.column("#0", width=180)
            tree_view.column("dimensions", width=160)
            tree_view.column("description", width=240)

            tree_scroller.pack(side="right", fill="y")
            tree_view.pack(fill="both", expand=True)

            for item in items:
                name = item["name"]
                dims = f"{item['grid_rows']}x{item['grid_cols']} @ {item['cell_w_in']}x{item['cell_h_in']}\""
                desc = item.get("description", "")
                node_id = tree_view.insert("", "end", text=name, values=(dims, desc))
                tree_view.item(node_id, tags=(name,))

            def make_select_handler(tv, itms):
                def on_select(evt):
                    sel = tv.selection()
                    if sel:
                        item_text = tv.item(sel[0], "text")
                        for itm in itms:
                            if itm["name"] == item_text:
                                selected_item["val"] = itm
                                btn_ok.config(state="normal")
                                break
                return on_select

            tree_view.bind("<<TreeviewSelect>>", make_select_handler(tree_view, items))
            tree_view.bind("<Double-1>", lambda e: on_ok())

        btn_frame = ttk.Frame(root, padding=10)
        btn_frame.pack(fill="x", side="bottom")

        def on_ok():
            if selected_item["val"]:
                chosen["layout"] = selected_item["val"]
                root.destroy()

        def on_cancel():
            chosen["layout"] = None
            root.destroy()

        def on_override():
            fpath = filedialog.askopenfilename(title="Choose a Block SVG", filetypes=[("SVG Files", "*.svg")])
            if fpath:
                chosen["block_path"] = fpath
                if selected_item["val"]:
                    chosen["layout"] = selected_item["val"]
                root.destroy()

        btn_cancel = ttk.Button(btn_frame, text="Cancel", command=on_cancel)
        btn_cancel.pack(side="right", padx=5)

        btn_ok = ttk.Button(btn_frame, text="Select Layout", command=on_ok, state="disabled")
        btn_ok.pack(side="right", padx=5)

        btn_ov = ttk.Button(btn_frame, text="Override with Block...", command=on_override)
        btn_ov.pack(side="left", padx=5)

        root.protocol("WM_DELETE_WINDOW", on_cancel)
        root.mainloop()
        return chosen if chosen["layout"] or chosen["block_path"] else None

    def add_arguments(self, pars):
        pars.add_argument("--notebook", type=str, default="grid_page")
        pars.add_argument("--quilt_name", type=str, default="My New Quilt")
        pars.add_argument("--use_picker", type=inkex.Boolean, default=False)
        pars.add_argument("--setting", type=str, default="straight")
        pars.add_argument("--grid_rows", type=int, default=4)
        pars.add_argument("--grid_cols", type=int, default=4)
        pars.add_argument("--cell_w_in", type=float, default=12.0)
        pars.add_argument("--cell_h_in", type=float, default=12.0)
        pars.add_argument("--sashing_w_in", type=float, default=0.0)
        pars.add_argument("--cornerstones", type=inkex.Boolean, default=False)
        pars.add_argument("--border_1_in", type=float, default=0.0)
        pars.add_argument("--border_1_style", type=str, default="long_h")
        pars.add_argument("--border_2_in", type=float, default=0.0)
        pars.add_argument("--border_2_style", type=str, default="long_h")
        pars.add_argument("--border_3_in", type=float, default=0.0)
        pars.add_argument("--border_3_style", type=str, default="long_h")
        pars.add_argument("--binding_w_in", type=float, default=0.25)
        pars.add_argument("--resize_page", type=inkex.Boolean, default=True)
        pars.add_argument("--theme_override", type=str, default="")

    def parse_arguments(self, args):
        self.options, unknown = self.arg_parser.parse_known_args(args)

    def effect(self):
        theme = qtheme.resolve_active_theme(self.options)
        
        override_block_path = None
        if self.options.use_picker:
            choice = self._pick_layout_gtk()
            if choice is not None:
                if choice["block_path"]:
                    override_block_path = choice["block_path"]
                elif choice["layout"]:
                    lay = choice["layout"]
                    self.options.setting = lay["setting"]
                    self.options.grid_rows = lay["grid_rows"]
                    self.options.grid_cols = lay["grid_cols"]
                    self.options.cell_w_in = lay["cell_w_in"]
                    self.options.cell_h_in = lay["cell_h_in"]
                    self.options.sashing_w_in = lay["sashing_w_in"]
                    self.options.cornerstones = lay["cornerstones"]
                    self.options.border_1_in = lay["border_1_in"]
                    self.options.border_1_style = lay.get("border_1_style", "long_h")
                    self.options.border_2_in = lay["border_2_in"]
                    self.options.border_2_style = lay.get("border_2_style", "long_h")
                    self.options.border_3_in = lay["border_3_in"]
                    self.options.border_3_style = lay.get("border_3_style", "long_h")
                    self.options.binding_w_in = lay["binding_w_in"]
            else:
                return  # Cancelled

        for layer in list(self.svg.findall(f".//{{{core.SVG_NS}}}g")):
            if (layer.get(f"{{{core.INKSCAPE_NS}}}label") == "Quilt Layout" or 
                layer.get("id") == "quilttools-quilt-layer"):
                layer.getparent().remove(layer)

        borders = []
        if self.options.border_1_in > 0:
            borders.append({
                "width_in": self.options.border_1_in,
                "style": self.options.border_1_style,
                "color_ref": "border1"
            })
        if self.options.border_2_in > 0:
            borders.append({
                "width_in": self.options.border_2_in,
                "style": self.options.border_2_style,
                "color_ref": "border2"
            })
        if self.options.border_3_in > 0:
            borders.append({
                "width_in": self.options.border_3_in,
                "style": self.options.border_3_style,
                "color_ref": "border3"
            })

        spec = {
            "name": self.options.quilt_name,
            "setting": self.options.setting,
            "grid": {
                "rows": self.options.grid_rows,
                "cols": self.options.grid_cols,
                "cell_w_in": self.options.cell_w_in,
                "cell_h_in": self.options.cell_h_in
            },
            "sashing": {
                "width_in": self.options.sashing_w_in,
                "cornerstones": self.options.cornerstones if self.options.sashing_w_in > 0 else False,
                "color_ref": "sashing"
            },
            "borders": borders,
            "binding": {
                "width_in": self.options.binding_w_in,
                "color_ref": "binding"
            },
            "cells": {}
        }

        if override_block_path:
            try:
                block_doc = inkex.load_svg(override_block_path)
                block_g, block_data = core.find_fpp_group(block_doc.getroot())
                if block_g is not None and block_data is not None:
                    spec["setting"] = "straight"
                    spec["grid"]["rows"] = 1
                    spec["grid"]["cols"] = 1
                    spec["sashing"]["width_in"] = 0.0
                    spec["sashing"]["cornerstones"] = False
                    
                    leaf_regions = block_data.tree.leaf_regions()
                    xs = [pt[0] for r in leaf_regions for pt in r.polygon]
                    ys = [pt[1] for r in leaf_regions for pt in r.polygon]
                    min_x = min(xs) if xs else 0.0
                    max_x = max(xs) if xs else 0.0
                    min_y = min(ys) if ys else 0.0
                    max_y = max(ys) if ys else 0.0
                    
                    block_w = max_x - min_x
                    block_h = max_y - min_y
                    
                    spec["grid"]["cell_w_in"] = block_w / core.PX_PER_INCH
                    spec["grid"]["cell_h_in"] = block_h / core.PX_PER_INCH
                    
                    for r in leaf_regions:
                        local_poly = [(pt[0] - min_x, pt[1] - min_y) for pt in r.polygon]
                        spec["cells"][f"quilt-cell-block-{r.id}"] = {
                            "role": "block",
                            "state": "empty",
                            "polygon": local_poly,
                            "placed_block": None,
                            "label": r.label
                        }
                else:
                    return inkex.errormsg("The selected file is not a valid Quilt Tools FPP block.")
            except Exception as e:
                return inkex.errormsg(f"Failed to load block layout: {e}")
        
        quilt_data = qcore.QuiltData(spec)
        g_quilt = qcore.build_quilt_layer(quilt_data, theme)
        self.svg.append(g_quilt)

        if self.options.resize_page:
            quilt_w_px = quilt_data.finished_width_in * core.PX_PER_INCH
            quilt_h_px = quilt_data.finished_height_in * core.PX_PER_INCH
            self.svg.set('width', f"{quilt_w_px}px")
            self.svg.set('height', f"{quilt_h_px}px")
            self.svg.set('viewBox', f"0 0 {quilt_w_px} {quilt_h_px}")



if __name__ == "__main__":
    NewQuiltPlugin().run()
