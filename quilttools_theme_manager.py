#!/usr/bin/env python3
import json
import os
import shutil
import sys
from lxml import etree
import inkex

import quilttools_theme as qtheme

class ThemeManagerPlugin(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--notebook", type=str, default="active_theme_tab")
        pars.add_argument("--active_theme_id", type=str, default="ifh")
        pars.add_argument("--list_themes", type=inkex.Boolean, default=False)
        pars.add_argument("--validate_theme_id", type=str, default="")
        pars.add_argument("--swatch_theme_id", type=str, default="")
        pars.add_argument("--new_theme_id", type=str, default="my_custom_theme")

    def effect(self):
        # Open interactive GUI by default if interactive environment
        gui_success = self._show_theme_manager_gui()
        if not gui_success:
            # Fallback to headless tab actions if GUI skipped
            tab = self.options.notebook
            if tab == "active_theme_tab":
                self.run_active_theme()
            elif tab == "validate_theme_tab":
                self.run_validate_theme()
            elif tab == "render_swatch_tab":
                self.run_render_swatch()
            elif tab == "new_theme_tab":
                self.run_new_theme()

    def get_system_fonts(self):
        """Helper to get a list of system font names on Windows."""
        fonts = set(["Fraunces", "IBM Plex Mono", "Inter", "Arial", "Times New Roman", "Courier New", "Georgia", "Verdana", "Trebuchet MS"])
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
            for i in range(10000):
                try:
                    name, _, _ = winreg.EnumValue(key, i)
                    clean_name = name.split(" (")[0].strip()
                    if clean_name:
                        fonts.add(clean_name)
                except OSError:
                    break
        except Exception:
            pass
            
        try:
            user_fonts = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
            if os.path.exists(user_fonts):
                for f in os.listdir(user_fonts):
                    name, _ = os.path.splitext(f)
                    if name:
                        fonts.add(name.replace("-", " ").title())
        except Exception:
            pass
            
        return sorted(list(fonts))

    def _show_theme_manager_gui(self):
        """Launches GTK3 or Tkinter interactive Theme Manager dialog."""
        try:
            return self._show_gtk_theme_gui()
        except Exception:
            try:
                return self._show_tk_theme_gui()
            except Exception:
                return False

    def _show_gtk_theme_gui(self):
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        discovered_themes = qtheme.discover_themes()
        prefs = qtheme.get_prefs()
        active_tid = prefs.get("theme", "ifh")
        if active_tid == "custom":
            active_tid = prefs.get("custom_theme", "ifh")
        if active_tid not in discovered_themes:
            active_tid = "ifh"

        active_theme_obj = qtheme.load_theme(active_tid)
        system_fonts = self.get_system_fonts()

        dialog = Gtk.Dialog(
            title="Quilt Tools — Pattern Theme Manager & Customizer",
            flags=0,
            buttons=(
                "Render Swatch Card", 101,
                "Validate Theme", 102,
                "Cancel", Gtk.ResponseType.CANCEL,
                "Save & Set Active Theme", Gtk.ResponseType.OK,
            )
        )
        dialog.set_default_size(620, 520)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_keep_above(True)

        content_area = dialog.get_content_area()
        content_area.set_spacing(10)
        content_area.set_margin_start(15)
        content_area.set_margin_end(15)
        content_area.set_margin_top(15)
        content_area.set_margin_bottom(15)

        # Header: Active Theme Selection
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_top = Gtk.Label(label="Active Theme:")
        lbl_top.set_halign(Gtk.Align.START)
        top_box.pack_start(lbl_top, False, False, 0)

        combo_theme_sel = Gtk.ComboBoxText()
        for tid, info in discovered_themes.items():
            combo_theme_sel.append(tid, f"{info['name']} [{tid}]")
        combo_theme_sel.set_active_id(active_tid)
        top_box.pack_start(combo_theme_sel, True, True, 0)

        content_area.pack_start(top_box, False, False, 0)

        # Notebook Tabs
        notebook = Gtk.Notebook()
        content_area.pack_start(notebook, True, True, 0)

        # TAB 1: Typography & System Fonts
        grid_fonts = Gtk.Grid()
        grid_fonts.set_column_spacing(12)
        grid_fonts.set_row_spacing(10)
        grid_fonts.set_margin_start(15)
        grid_fonts.set_margin_end(15)
        grid_fonts.set_margin_top(15)

        fonts_cfg = active_theme_obj.get("fonts", {})
        
        # Heading Font
        grid_fonts.attach(Gtk.Label(label="Heading Font Family:"), 0, 0, 1, 1)
        combo_head_font = Gtk.ComboBoxText()
        for f in system_fonts:
            combo_head_font.append(f, f)
        combo_head_font.set_active_id(fonts_cfg.get("heading", {}).get("family", "Fraunces"))
        grid_fonts.attach(combo_head_font, 1, 0, 1, 1)

        # Body Font
        grid_fonts.attach(Gtk.Label(label="Body Text Font Family:"), 0, 1, 1, 1)
        combo_body_font = Gtk.ComboBoxText()
        for f in system_fonts:
            combo_body_font.append(f, f)
        combo_body_font.set_active_id(fonts_cfg.get("body", {}).get("family", "Fraunces"))
        grid_fonts.attach(combo_body_font, 1, 1, 1, 1)

        # Mono Font
        grid_fonts.attach(Gtk.Label(label="Monospace / Dimension Font:"), 0, 2, 1, 1)
        combo_mono_font = Gtk.ComboBoxText()
        for f in system_fonts:
            combo_mono_font.append(f, f)
        combo_mono_font.set_active_id(fonts_cfg.get("mono", {}).get("family", "IBM Plex Mono"))
        grid_fonts.attach(combo_mono_font, 1, 2, 1, 1)

        notebook.append_page(grid_fonts, Gtk.Label(label="Typography & Fonts"))

        # TAB 2: Line Weights & Swatches
        grid_lines = Gtk.Grid()
        grid_lines.set_column_spacing(12)
        grid_lines.set_row_spacing(10)
        grid_lines.set_margin_start(15)
        grid_lines.set_margin_end(15)
        grid_lines.set_margin_top(15)

        grid_lines.attach(Gtk.Label(label="Stitch Line Weight (pt):"), 0, 0, 1, 1)
        spin_stitch_lw = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=active_theme_obj.line_weight("stitch_line"), lower=0.1, upper=3.0, step_increment=0.05), climb_rate=0.05, digits=2)
        grid_lines.attach(spin_stitch_lw, 1, 0, 1, 1)

        grid_lines.attach(Gtk.Label(label="Cut Line Weight (pt):"), 0, 1, 1, 1)
        spin_cut_lw = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=active_theme_obj.line_weight("cut_line"), lower=0.1, upper=3.0, step_increment=0.05), climb_rate=0.05, digits=2)
        grid_lines.attach(spin_cut_lw, 1, 1, 1, 1)

        grid_lines.attach(Gtk.Label(label="Border Line Weight (pt):"), 0, 2, 1, 1)
        spin_border_lw = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=active_theme_obj.line_weight("border"), lower=0.1, upper=5.0, step_increment=0.1), climb_rate=0.1, digits=2)
        grid_lines.attach(spin_border_lw, 1, 2, 1, 1)

        grid_lines.attach(Gtk.Label(label="Colour Swatch Shape:"), 0, 3, 1, 1)
        combo_swatch_sh = Gtk.ComboBoxText()
        combo_swatch_sh.append("rectangle", "Rectangle (Default)")
        combo_swatch_sh.append("heart", "Love Heart ❤️")
        combo_swatch_sh.append("circle", "Circle ⚪")
        combo_swatch_sh.append("star", "Star ⭐")
        combo_swatch_sh.set_active_id(active_theme_obj.swatch_shape())
        grid_lines.attach(combo_swatch_sh, 1, 3, 1, 1)

        grid_lines.attach(Gtk.Label(label="Join/Glue Tab Style:"), 0, 4, 1, 1)
        combo_tab_st = Gtk.ComboBoxText()
        combo_tab_st.append("grey", "Grey Fill (Default)")
        combo_tab_st.append("outline", "Outline Only (Ink-Saver)")
        combo_tab_st.append("crosshatch", "Black & White Crosshatch")
        combo_tab_st.set_active_id(active_theme_obj.tab_style())
        grid_lines.attach(combo_tab_st, 1, 4, 1, 1)

        grid_lines.attach(Gtk.Label(label="Small Pieces Colour Mode:"), 0, 5, 1, 1)
        combo_sp_m = Gtk.ComboBoxText()
        combo_sp_m.append("fill", "Solid Colour Fill (Default)")
        combo_sp_m.append("code_only", "Colour Code Badge Only (Ink-Saver)")
        combo_sp_m.set_active_id(active_theme_obj.small_pieces_mode())
        grid_lines.attach(combo_sp_m, 1, 5, 1, 1)

        notebook.append_page(grid_lines, Gtk.Label(label="Line Weights & Swatches"))

        # TAB 3: Footer & Shop Branding
        grid_footer = Gtk.Grid()
        grid_footer.set_column_spacing(12)
        grid_footer.set_row_spacing(10)
        grid_footer.set_margin_start(15)
        grid_footer.set_margin_end(15)
        grid_footer.set_margin_top(15)

        footer_cfg = active_theme_obj.footer_config()

        grid_footer.attach(Gtk.Label(label="Default Designer Name:"), 0, 0, 1, 1)
        entry_des_name = Gtk.Entry()
        entry_des_name.set_text(self.options.designer_name or "")
        grid_footer.attach(entry_des_name, 1, 0, 1, 1)

        grid_footer.attach(Gtk.Label(label="Custom Shop Footer Text:"), 0, 1, 1, 1)
        entry_custom_ft = Gtk.Entry()
        entry_custom_ft.set_text(footer_cfg.get("footer_text_custom", ""))
        grid_footer.attach(entry_custom_ft, 1, 1, 1, 1)

        chk_show_des = Gtk.CheckButton(label="Show Designer Credit in Footer")
        chk_show_des.set_active(footer_cfg.get("show_designer", True))
        grid_footer.attach(chk_show_des, 0, 2, 2, 1)

        chk_show_cr = Gtk.CheckButton(label="Show Copyright Notice in Footer")
        chk_show_cr.set_active(footer_cfg.get("show_copyright", True))
        grid_footer.attach(chk_show_cr, 0, 3, 2, 1)

        chk_h_div = Gtk.CheckButton(label="Show Top Header Divider Line")
        chk_h_div.set_active(footer_cfg.get("show_header_divider", True))
        grid_footer.attach(chk_h_div, 0, 4, 2, 1)

        chk_f_div = Gtk.CheckButton(label="Show Bottom Footer Divider Line")
        chk_f_div.set_active(footer_cfg.get("show_footer_divider", True))
        grid_footer.attach(chk_f_div, 0, 5, 2, 1)

        notebook.append_page(grid_footer, Gtk.Label(label="Footer & Shop Branding"))

        # TAB 4: Palette Colors
        grid_pal = Gtk.Grid()
        grid_pal.set_column_spacing(12)
        grid_pal.set_row_spacing(10)
        grid_pal.set_margin_start(15)
        grid_pal.set_margin_end(15)
        grid_pal.set_margin_top(15)

        pal = active_theme_obj.get("palette", {})

        grid_pal.attach(Gtk.Label(label="Background Color (Hex):"), 0, 0, 1, 1)
        entry_bg_col = Gtk.Entry()
        entry_bg_col.set_text(pal.get("background", "#EFE5D0"))
        grid_pal.attach(entry_bg_col, 1, 0, 1, 1)

        grid_pal.attach(Gtk.Label(label="Primary Accent Color (Hex):"), 0, 1, 1, 1)
        entry_pri_col = Gtk.Entry()
        entry_pri_col.set_text(pal.get("primary", "#243B53"))
        grid_pal.attach(entry_pri_col, 1, 1, 1, 1)

        grid_pal.attach(Gtk.Label(label="Ink Text Color (Hex):"), 0, 2, 1, 1)
        entry_ink_col = Gtk.Entry()
        entry_ink_col.set_text(pal.get("ink", "#1F1A14"))
        grid_pal.attach(entry_ink_col, 1, 2, 1, 1)

        grid_pal.attach(Gtk.Label(label="Muted Color (Hex):"), 0, 3, 1, 1)
        entry_mut_col = Gtk.Entry()
        entry_mut_col.set_text(pal.get("muted", "#8A7F6E"))
        grid_pal.attach(entry_mut_col, 1, 3, 1, 1)

        notebook.append_page(grid_pal, Gtk.Label(label="Palette Colors"))

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK or response == 101 or response == 102:
            sel_tid = combo_theme_sel.get_active_id() or "ifh"
            
            # Mutate active theme dictionary
            active_theme_obj["fonts"] = {
                "heading": {"family": combo_head_font.get_active_id() or "Fraunces", "weight": "600", "style": "normal"},
                "subtitle": {"family": combo_head_font.get_active_id() or "Fraunces", "weight": "400", "style": "italic"},
                "body": {"family": combo_body_font.get_active_id() or "Fraunces", "weight": "400", "style": "normal"},
                "mono": {"family": combo_mono_font.get_active_id() or "IBM Plex Mono", "weight": "400", "style": "normal"}
            }

            active_theme_obj["line_weights"] = {
                "stitch_line": spin_stitch_lw.get_value(),
                "cut_line": spin_cut_lw.get_value(),
                "border": spin_border_lw.get_value(),
                "divider": 0.5,
                "grid": 0.5
            }

            active_theme_obj["swatch"] = {
                "shape": combo_swatch_sh.get_active_id() or "rectangle"
            }

            active_theme_obj["tabs"] = {
                "style": combo_tab_st.get_active_id() or "grey"
            }

            active_theme_obj["small_pieces"] = {
                "mode": combo_sp_m.get_active_id() or "fill"
            }

            active_theme_obj["footer"] = {
                "footer_enabled": True,
                "show_designer": chk_show_des.get_active(),
                "show_copyright": chk_show_cr.get_active(),
                "show_page_numbers": True,
                "show_block_size": True,
                "footer_text_custom": entry_custom_ft.get_text().strip(),
                "show_footer_divider": chk_f_div.get_active(),
                "show_header_divider": chk_h_div.get_active(),
                "footer_font_size_pt": 10.0
            }

            active_theme_obj["palette"] = {
                "primary": entry_pri_col.get_text().strip() or "#243B53",
                "background": entry_bg_col.get_text().strip() or "#EFE5D0",
                "ink": entry_ink_col.get_text().strip() or "#1F1A14",
                "accent": entry_pri_col.get_text().strip() or "#243B53",
                "muted": entry_mut_col.get_text().strip() or "#8A7F6E",
                "warning": "#8C3B2E"
            }

            # Save theme file
            qtheme.save_theme(sel_tid, active_theme_obj)

            # Update sticky preference
            prefs["theme"] = sel_tid if sel_tid in ["ifh", "childrens_moments"] else "custom"
            if sel_tid not in ["ifh", "childrens_moments"]:
                prefs["custom_theme"] = sel_tid
            qtheme.set_prefs(prefs)

            if response == 101: # Render Swatch Card
                self.options.swatch_theme_id = sel_tid
                self.run_render_swatch()
            elif response == 102: # Validate Theme
                self.options.validate_theme_id = sel_tid
                self.run_validate_theme()

            dialog.destroy()
            return True

        dialog.destroy()
        return False

    def _show_tk_theme_gui(self):
        import tkinter as tk
        from tkinter import ttk, messagebox

        discovered_themes = qtheme.discover_themes()
        prefs = qtheme.get_prefs()
        active_tid = prefs.get("theme", "ifh")
        if active_tid == "custom":
            active_tid = prefs.get("custom_theme", "ifh")
        if active_tid not in discovered_themes:
            active_tid = "ifh"

        active_theme_obj = qtheme.load_theme(active_tid)
        system_fonts = self.get_system_fonts()

        root = tk.Tk()
        root.title("Quilt Tools — Pattern Theme Manager")
        root.geometry("600x500")
        root.attributes("-topmost", True)

        main_frame = ttk.Frame(root, padding=12)
        main_frame.pack(fill="both", expand=True)

        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(top_frame, text="Active Theme:").pack(side="left", padx=5)
        combo_theme_sel = ttk.Combobox(top_frame, values=list(discovered_themes.keys()), state="readonly", width=25)
        combo_theme_sel.set(active_tid)
        combo_theme_sel.pack(side="left", padx=5)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True)

        # TAB 1: Typography
        page1 = ttk.Frame(notebook, padding=12)
        notebook.add(page1, text="Typography & Fonts")

        fonts_cfg = active_theme_obj.get("fonts", {})
        ttk.Label(page1, text="Heading Font Family:").grid(row=0, column=0, sticky="w", pady=6)
        combo_head_font = ttk.Combobox(page1, values=system_fonts, state="readonly", width=28)
        combo_head_font.set(fonts_cfg.get("heading", {}).get("family", "Fraunces"))
        combo_head_font.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(page1, text="Body Text Font Family:").grid(row=1, column=0, sticky="w", pady=6)
        combo_body_font = ttk.Combobox(page1, values=system_fonts, state="readonly", width=28)
        combo_body_font.set(fonts_cfg.get("body", {}).get("family", "Fraunces"))
        combo_body_font.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Label(page1, text="Monospace Font:").grid(row=2, column=0, sticky="w", pady=6)
        combo_mono_font = ttk.Combobox(page1, values=system_fonts, state="readonly", width=28)
        combo_mono_font.set(fonts_cfg.get("mono", {}).get("family", "IBM Plex Mono"))
        combo_mono_font.grid(row=2, column=1, sticky="w", pady=6)

        # TAB 2: Line Weights & Swatches
        page2 = ttk.Frame(notebook, padding=12)
        notebook.add(page2, text="Line Weights & Swatches")

        ttk.Label(page2, text="Stitch Line Weight (pt):").grid(row=0, column=0, sticky="w", pady=6)
        spin_stitch_lw = ttk.Spinbox(page2, from_=0.1, to=3.0, increment=0.05, width=10)
        spin_stitch_lw.set(str(active_theme_obj.line_weight("stitch_line")))
        spin_stitch_lw.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(page2, text="Cut Line Weight (pt):").grid(row=1, column=0, sticky="w", pady=6)
        spin_cut_lw = ttk.Spinbox(page2, from_=0.1, to=3.0, increment=0.05, width=10)
        spin_cut_lw.set(str(active_theme_obj.line_weight("cut_line")))
        spin_cut_lw.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Label(page2, text="Colour Swatch Shape:").grid(row=2, column=0, sticky="w", pady=6)
        shape_map = {"rectangle": "Rectangle (Default)", "heart": "Love Heart ❤️", "circle": "Circle ⚪", "star": "Star ⭐"}
        shape_reverse = {v: k for k, v in shape_map.items()}
        combo_swatch_sh = ttk.Combobox(page2, values=list(shape_map.values()), state="readonly", width=28)
        combo_swatch_sh.set(shape_map.get(active_theme_obj.swatch_shape(), "Rectangle (Default)"))
        combo_swatch_sh.grid(row=2, column=1, sticky="w", pady=6)

        ttk.Label(page2, text="Join/Glue Tab Style:").grid(row=3, column=0, sticky="w", pady=6)
        tab_map = {"grey": "Grey Fill (Default)", "outline": "Outline Only (Ink-Saver)", "crosshatch": "Black & White Crosshatch"}
        tab_reverse = {v: k for k, v in tab_map.items()}
        combo_tab_st = ttk.Combobox(page2, values=list(tab_map.values()), state="readonly", width=28)
        combo_tab_st.set(tab_map.get(active_theme_obj.tab_style(), "Grey Fill (Default)"))
        combo_tab_st.grid(row=3, column=1, sticky="w", pady=6)

        ttk.Label(page2, text="Small Pieces Colour Mode:").grid(row=4, column=0, sticky="w", pady=6)
        sp_map = {"fill": "Solid Colour Fill (Default)", "code_only": "Colour Code Badge Only (Ink-Saver)"}
        sp_reverse = {v: k for k, v in sp_map.items()}
        combo_sp_m = ttk.Combobox(page2, values=list(sp_map.values()), state="readonly", width=28)
        combo_sp_m.set(sp_map.get(active_theme_obj.small_pieces_mode(), "Solid Colour Fill (Default)"))
        combo_sp_m.grid(row=4, column=1, sticky="w", pady=6)

        # TAB 3: Footer & Shop Branding
        page3 = ttk.Frame(notebook, padding=12)
        notebook.add(page3, text="Footer & Shop Branding")

        footer_cfg = active_theme_obj.footer_config()
        ttk.Label(page3, text="Custom Shop Footer Text:").grid(row=0, column=0, sticky="w", pady=6)
        entry_custom_ft = ttk.Entry(page3, width=32)
        entry_custom_ft.insert(0, footer_cfg.get("footer_text_custom", ""))
        entry_custom_ft.grid(row=0, column=1, sticky="w", pady=6)

        var_show_des = tk.BooleanVar(value=bool(footer_cfg.get("show_designer", True)))
        ttk.Checkbutton(page3, text="Show Designer Credit in Footer", variable=var_show_des).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)

        var_show_cr = tk.BooleanVar(value=bool(footer_cfg.get("show_copyright", True)))
        ttk.Checkbutton(page3, text="Show Copyright Notice in Footer", variable=var_show_cr).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)

        result = {"success": False, "action": "save"}

        def on_save():
            sel_tid = combo_theme_sel.get() or "ifh"
            active_theme_obj["fonts"] = {
                "heading": {"family": combo_head_font.get(), "weight": "600", "style": "normal"},
                "subtitle": {"family": combo_head_font.get(), "weight": "400", "style": "italic"},
                "body": {"family": combo_body_font.get(), "weight": "400", "style": "normal"},
                "mono": {"family": combo_mono_font.get(), "weight": "400", "style": "normal"}
            }
            try:
                st_val = float(spin_stitch_lw.get())
                cut_val = float(spin_cut_lw.get())
            except Exception:
                st_val, cut_val = 0.75, 0.75

            active_theme_obj["line_weights"] = {"stitch_line": st_val, "cut_line": cut_val, "border": 1.0, "divider": 0.5, "grid": 0.5}
            active_theme_obj["swatch"] = {"shape": shape_reverse.get(combo_swatch_sh.get(), "rectangle")}
            active_theme_obj["tabs"] = {"style": tab_reverse.get(combo_tab_st.get(), "grey")}
            active_theme_obj["small_pieces"] = {"mode": sp_reverse.get(combo_sp_m.get(), "fill")}
            active_theme_obj["footer"] = {
                "footer_enabled": True, "show_designer": var_show_des.get(), "show_copyright": var_show_cr.get(),
                "show_page_numbers": True, "show_block_size": True, "footer_text_custom": entry_custom_ft.get().strip(),
                "show_footer_divider": True, "show_header_divider": True, "footer_font_size_pt": 10.0
            }

            qtheme.save_theme(sel_tid, active_theme_obj)

            prefs["theme"] = sel_tid if sel_tid in ["ifh", "childrens_moments"] else "custom"
            if sel_tid not in ["ifh", "childrens_moments"]:
                prefs["custom_theme"] = sel_tid
            qtheme.set_prefs(prefs)

            result["success"] = True
            root.destroy()

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(10, 0))

        ttk.Button(btn_frame, text="Cancel", command=root.destroy).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Save & Set Active Theme", command=on_save).pack(side="right", padx=5)

        root.mainloop()
        return result["success"]

    def run_active_theme(self):
        theme_id = (self.options.active_theme_id or "").strip()
        if not theme_id:
            inkex.errormsg("Please enter a valid Theme ID.")
            return

        theme_path = os.path.join(qtheme.THEMES_DIR, f"{theme_id}.json")
        if not os.path.exists(theme_path):
            inkex.errormsg(f"Error: Theme file '{theme_id}.json' not found in themes/ folder.")
            return

        prefs = qtheme.get_prefs()
        if theme_id in ["ifh", "childrens_moments"]:
            prefs["theme"] = theme_id
            if "custom_theme" in prefs:
                del prefs["custom_theme"]
        else:
            prefs["theme"] = "custom"
            prefs["custom_theme"] = theme_id
            
        qtheme.set_prefs(prefs)
        
        msg = f"Active theme set to: '{theme_id}'\n"
        if self.options.list_themes:
            themes = qtheme.discover_themes()
            msg += "\nDiscovered Themes:\n"
            for tid, info in themes.items():
                active_marker = " (Active)" if tid == theme_id else ""
                msg += f"- {info['name']}{active_marker} [ID: {tid}]\n  {info['description']}\n"
        
        inkex.utils.debug(msg)

    def run_validate_theme(self):
        theme_id = (self.options.validate_theme_id or "").strip()
        if not theme_id:
            prefs = qtheme.get_prefs()
            theme_id = prefs.get("theme", "ifh")
            if theme_id == "custom":
                theme_id = prefs.get("custom_theme", "ifh")

        theme_path = os.path.join(qtheme.THEMES_DIR, f"{theme_id}.json")
        if not os.path.exists(theme_path):
            inkex.errormsg(f"Error: Theme file '{theme_id}.json' not found.")
            return

        report = [f"Theme Validation Report for '{theme_id}':"]
        errors = 0
        
        try:
            with open(theme_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            report.append("[✓] JSON Syntax: Valid")
        except Exception as e:
            report.append(f"[✗] JSON Syntax: Invalid ({e})")
            inkex.errormsg("\n".join(report))
            return

        required_fields = ["schema_version", "name", "id", "fonts", "palette", "type_scale_pt", "page", "rules"]
        for f in required_fields:
            if f in data:
                report.append(f"[✓] Required Field '{f}': Present")
            else:
                report.append(f"[✗] Required Field '{f}': Missing")
                errors += 1

        req_fonts = data.get("required_fonts", [])
        if req_fonts:
            report.append("\nRequired Fonts Check:")
            installed_fonts = self.get_system_fonts()
            for font in req_fonts:
                found = any(font.lower() in f_name.lower() for f_name in installed_fonts)
                if found:
                    report.append(f"  [✓] Font '{font}': Installed")
                else:
                    report.append(f"  [!] Font '{font}': NOT found on system (Warning)")
                    
        if errors == 0:
            report.append("\nTheme is fully valid and ready to use!")
        else:
            report.append(f"\nTheme has {errors} schema error(s). Please fix before exporting.")

        inkex.utils.debug("\n".join(report))

    def run_render_swatch(self):
        theme_id = (self.options.swatch_theme_id or "").strip()
        if not theme_id:
            prefs = qtheme.get_prefs()
            theme_id = prefs.get("theme", "ifh")
            if theme_id == "custom":
                theme_id = prefs.get("custom_theme", "ifh")

        theme = qtheme.load_theme(theme_id)
        
        layer = self.svg.get_current_layer()
        g = etree.SubElement(layer, inkex.addNS("g", "svg"), id=f"theme-swatch-{theme_id}")
        g.set("transform", "translate(50, 50)")
        
        palette = theme.get("palette", {})
        fonts = theme.get("fonts", {})
        
        bg_col = palette.get("background", "#FFFFFF")
        primary_col = palette.get("primary", "#000000")
        
        etree.SubElement(g, inkex.addNS("rect", "svg"), {
            "x": "0", "y": "0", "width": "500", "height": "300",
            "style": f"fill:{bg_col}; stroke:{primary_col}; stroke-width:1.5; rx:10; ry:10;"
        })
        
        heading_font = fonts.get("heading", {}).get("family", "Fraunces")
        title_text = etree.SubElement(g, inkex.addNS("text", "svg"), {
            "x": "20", "y": "40",
            "style": f"font-family:{heading_font}; font-size:18pt; font-weight:bold; fill:{primary_col};"
        })
        title_text.text = theme.get("name", theme_id)

        inkex.utils.debug(f"Rendered swatch card for theme '{theme_id}' onto the canvas.")

    def run_new_theme(self):
        new_id = (self.options.new_theme_id or "").strip()
        if not new_id:
            inkex.errormsg("Please specify a new Theme ID.")
            return

        new_id_clean = "".join(c for c in new_id if c.isalnum() or c == "_").lower()
        if not new_id_clean:
            inkex.errormsg("Theme ID contains invalid characters.")
            return

        dest_path = os.path.join(qtheme.THEMES_DIR, f"{new_id_clean}.json")
        if os.path.exists(dest_path):
            inkex.errormsg(f"A theme with ID '{new_id_clean}' already exists at:\n  {dest_path}")
            return

        src_path = os.path.join(qtheme.THEMES_DIR, "ifh.json")
        if not os.path.exists(src_path):
            inkex.errormsg("Could not locate the template theme 'ifh.json'.")
            return

        try:
            with open(src_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            data["id"] = new_id_clean
            data["name"] = new_id_clean.replace("_", " ").title()
            data["description"] = f"Custom theme cloned from IFH template."
            
            qtheme.save_theme(new_id_clean, data)
            inkex.utils.debug(f"New theme cloned successfully!\nFile location:\n  {dest_path}\n\nYou can edit this theme directly via Theme Manager.")
        except Exception as e:
            inkex.errormsg(f"Failed to clone theme template: {e}")

if __name__ == "__main__":
    ThemeManagerPlugin().run()
