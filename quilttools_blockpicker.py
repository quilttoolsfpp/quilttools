"""Shared Block Library browser widget (GTK).

One browsing behaviour for every tool that picks a block (Block Library,
Fill Blocks, Import into Region):

* DEFAULT VIEW - browse by subfolder: the current folder's subfolders are
  shown as folder cards (with block counts), followed by the blocks that
  live directly in that folder. Click a folder to enter it; ".. up" and
  the breadcrumb take you back.
* SEARCH - typing in the search box instantly switches to a flat view of
  every matching block in the WHOLE library (name or folder matches),
  each card captioned with the folder it lives in. Clearing the search
  returns to the folder view where you were.

The widget is pure GTK construction - no Inkscape/inkex dependency - so
callers pass in the Gtk/GdkPixbuf modules they already imported.
"""


def build_block_browser(Gtk, GdkPixbuf, blocks, on_pick,
                        on_activate=None, Gdk=None,
                        thumb=120, columns=3, label_chars=15):
    """Build the browser.

    blocks:      [(label 'Folder/Sub/Name', full_path), ...]
    on_pick:     called with full_path on single click of a block card
    on_activate: called with full_path on double click (optional; when
                 omitted, single click is the only action)
    Gdk:         required only when on_activate is used (double-click
                 detection needs Gdk event types)

    Returns {"widget": <Gtk.Box>, "search": <Gtk.SearchEntry>}.
    """
    # ---- folder tree ------------------------------------------------
    tree = {}   # folder tuple -> {"dirs": set, "blocks": [(name,label,path)]}

    def node(folder):
        if folder not in tree:
            tree[folder] = {"dirs": set(), "blocks": []}
        return tree[folder]

    node(())
    for label, full in blocks:
        parts = label.split("/")
        folder = tuple(parts[:-1])
        for depth in range(len(folder)):
            node(folder[:depth + 1])
            node(folder[:depth])["dirs"].add(folder[depth])
        node(folder)["blocks"].append((parts[-1], label, full))

    def count_blocks(folder):
        n = len(node(folder)["blocks"])
        for d in sorted(node(folder)["dirs"]):
            n += count_blocks(folder + (d,))
        return n

    state = {"folder": (), "show_all": False}
    pixbuf_cache = {}

    # ---- widgets -----------------------------------------------------
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    search = Gtk.SearchEntry()
    search.set_placeholder_text(
        "Search the whole library... (blank = browse folders)")
    search.set_margin_top(8)
    search.set_margin_start(10)
    search.set_margin_end(10)
    vbox.pack_start(search, False, False, 0)

    crumb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    crumb_box.set_margin_start(10)
    crumb_box.set_margin_end(10)
    crumb = Gtk.Label(label="Library")
    crumb.set_halign(Gtk.Align.START)
    
    up_btn = Gtk.Button(label="⬆ Up")
    up_btn.set_relief(Gtk.ReliefStyle.NONE)
    
    show_all_btn = Gtk.Button(label="🗂 Show All")
    show_all_btn.set_relief(Gtk.ReliefStyle.NONE)
    
    crumb_box.pack_start(up_btn, False, False, 0)
    crumb_box.pack_start(show_all_btn, False, False, 0)
    crumb_box.pack_start(crumb, False, False, 0)
    vbox.pack_start(crumb_box, False, False, 0)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    flow = Gtk.FlowBox()
    flow.set_valign(Gtk.Align.START)
    flow.set_max_children_per_line(columns)
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_row_spacing(8)
    flow.set_column_spacing(8)
    for side in ("top", "bottom", "start", "end"):
        getattr(flow, f"set_margin_{side}")(10)
    scroller.add(flow)
    vbox.pack_start(scroller, True, True, 0)

    empty = Gtk.Label(label="No blocks match your search.")
    empty.set_no_show_all(True)
    vbox.pack_start(empty, False, False, 4)

    # ---- cards --------------------------------------------------------
    def thumb_image(full):
        if full not in pixbuf_cache:
            try:
                pixbuf_cache[full] = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    full, thumb, thumb, True)
            except Exception:
                pixbuf_cache[full] = None
        pb = pixbuf_cache[full]
        return Gtk.Image.new_from_pixbuf(pb) if pb is not None else None

    def block_card(name, label, full, caption=None):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        img = thumb_image(full)
        if img is not None:
            box.pack_start(img, False, False, 0)
        lbl = Gtk.Label(label=name)
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(label_chars)
        lbl.set_justify(Gtk.Justification.CENTER)
        box.pack_start(lbl, False, False, 0)
        if caption:
            cap = Gtk.Label(label=caption)
            cap.set_max_width_chars(label_chars + 4)
            try:
                from gi.repository import Pango
                cap.set_ellipsize(Pango.EllipsizeMode.END)
            except Exception:
                pass
            cap.get_style_context().add_class("dim-label")
            box.pack_start(cap, False, False, 0)
        btn.add(box)
        btn.set_tooltip_text(label)
        btn.connect("clicked", lambda _b: on_pick(full))
        if on_activate is not None and Gdk is not None:
            def _dbl(_b, event, path=full):
                if event.button == 1 and \
                        event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
                    on_activate(path)
                    return True
                return False
            btn.connect("button-press-event", _dbl)
        return btn

    def folder_card(folder_name, target):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        icon = Gtk.Image.new_from_icon_name("folder", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(max(48, thumb // 2))
        box.pack_start(icon, False, False, 6)
        n = count_blocks(target)
        lbl = Gtk.Label(label=f"{folder_name}\n({n} block"
                              f"{'s' if n != 1 else ''})")
        lbl.set_justify(Gtk.Justification.CENTER)
        box.pack_start(lbl, False, False, 0)
        btn.add(box)

        def enter(_b):
            state["folder"] = target
            rebuild()
        btn.connect("clicked", enter)
        return btn

    # ---- rebuild ------------------------------------------------------
    def rebuild():
        for child in list(flow.get_children()):
            flow.remove(child)
        q = search.get_text().strip().lower()
        shown = 0
        if q:
            crumb_box.hide()
            for label, full in blocks:
                if q in label.lower():
                    parts = label.split("/")
                    folder_txt = "/".join(parts[:-1]) or "(library root)"
                    flow.add(block_card(parts[-1], label, full,
                                        caption="in " + folder_txt))
                    shown += 1
        elif state.get("show_all"):
            crumb_box.show()
            up_btn.hide()
            show_all_btn.set_label("📁 Browse Folders")
            crumb.set_text("All Blocks (Alphabetical)")

            flat_blocks = []
            for label, full in blocks:
                parts = label.split("/")
                name = parts[-1]
                folder_txt = "/".join(parts[:-1]) or "(library root)"
                flat_blocks.append((name, label, full, folder_txt))

            flat_blocks.sort(key=lambda b: b[0].lower())
            for name, label, full, folder_txt in flat_blocks:
                flow.add(block_card(name, label, full, caption="in " + folder_txt))
                shown += 1
        else:
            crumb_box.show()
            up_btn.show()
            show_all_btn.set_label("🗂 Show All")

            folder = state["folder"]
            up_btn.set_sensitive(bool(folder))
            crumb.set_text("Library" + "".join(
                "  ▸ " + p for p in folder))
            for d in sorted(node(folder)["dirs"], key=str.lower):
                flow.add(folder_card(d, folder + (d,)))
                shown += 1
            for name, label, full in sorted(node(folder)["blocks"],
                                            key=lambda b: b[0].lower()):
                flow.add(block_card(name, label, full))
                shown += 1
        empty.set_visible(shown == 0)
        flow.show_all()

    def go_up(_b):
        if state["folder"]:
            state["folder"] = state["folder"][:-1]
            rebuild()
            
    def toggle_show_all(_b):
        state["show_all"] = not state.get("show_all")
        rebuild()

    up_btn.connect("clicked", go_up)
    show_all_btn.connect("clicked", toggle_show_all)
    search.connect("search-changed", lambda _w: rebuild())

    # First build happens after show_all(); calling here as well is safe.
    rebuild()
    return {"widget": vbox, "search": search, "rebuild": rebuild}


def pick_block_tk(title, blocks, thumb_size=120, columns=4):
    """
    Tkinter modal block/quilt browser dialog for cross-platform support (macOS, Windows, Linux).
    blocks: [(label 'Folder/Sub/Name', full_path), ...]
    Returns selected full_path (str) or None if cancelled.
    """
    import os
    import tkinter as tk
    from tkinter import ttk

    tree = {}
    def get_node(folder):
        if folder not in tree:
            tree[folder] = {"dirs": set(), "blocks": []}
        return tree[folder]

    get_node(())
    for label, full in blocks:
        parts = label.replace("\\", "/").split("/")
        folder = tuple(parts[:-1])
        for depth in range(len(folder)):
            get_node(folder[:depth + 1])
            get_node(folder[:depth])["dirs"].add(folder[depth])
        get_node(folder)["blocks"].append((parts[-1], label, full))

    def count_blocks(folder):
        n = len(get_node(folder)["blocks"])
        for d in sorted(get_node(folder)["dirs"]):
            n += count_blocks(folder + (d,))
        return n

    state = {
        "folder": (),
        "show_all": False,
        "selected_path": None,
        "selected_btn": None
    }
    img_cache = {}

    root = tk.Tk()
    root.title(title)
    root.geometry("740x600")
    root.minsize(580, 450)
    root.attributes("-topmost", True)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    result = {"path": None}

    # Top Search & Nav Frame
    top_frame = ttk.Frame(root, padding=8)
    top_frame.pack(fill="x")

    search_var = tk.StringVar()
    search_entry = ttk.Entry(top_frame, textvariable=search_var, width=35)
    search_entry.pack(side="left", padx=5)

    placeholder_text = "Search by name or category..."
    search_entry.insert(0, placeholder_text)
    search_entry.config(foreground="grey")

    def on_entry_click(event):
        if search_entry.get() == placeholder_text:
            search_entry.delete(0, "end")
            search_entry.config(foreground="black")

    def on_focusout(event):
        if search_entry.get() == "":
            search_entry.insert(0, placeholder_text)
            search_entry.config(foreground="grey")

    search_entry.bind("<FocusIn>", on_entry_click)
    search_entry.bind("<FocusOut>", on_focusout)

    crumb_var = tk.StringVar(value="Library")
    crumb_lbl = ttk.Label(top_frame, textvariable=crumb_var, font=("sans-serif", 10, "bold"))
    crumb_lbl.pack(side="left", padx=10)

    btn_up = ttk.Button(top_frame, text="⬆ Up", width=6)
    btn_up.pack(side="right", padx=2)

    btn_all = ttk.Button(top_frame, text="🗂 Show All", width=12)
    btn_all.pack(side="right", padx=2)

    # Scrollable Main Canvas Frame
    main_frame = ttk.Frame(root, padding=5)
    main_frame.pack(fill="both", expand=True)

    canvas = tk.Canvas(main_frame, bg="#f5f5f7", highlightthickness=0)
    scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    grid_frame = ttk.Frame(canvas, padding=10)

    grid_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas_window = canvas.create_window((0, 0), window=grid_frame, anchor="nw")

    def on_canvas_configure(event):
        canvas.itemconfig(canvas_window, width=event.width)

    canvas.bind("<Configure>", on_canvas_configure)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Mousewheel binding
    def _on_mousewheel(event):
        if event.delta:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num in (4, 5):
            canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    canvas.bind_all("<Button-4>", _on_mousewheel)
    canvas.bind_all("<Button-5>", _on_mousewheel)

    # Bottom Action Bar
    bottom_frame = ttk.Frame(root, padding=10)
    bottom_frame.pack(fill="x", side="bottom")

    status_var = tk.StringVar(value="")
    status_lbl = ttk.Label(bottom_frame, textvariable=status_var, foreground="#666666")
    status_lbl.pack(side="left", padx=5)

    def cleanup_mousewheel():
        try:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        except Exception:
            pass

    def on_cancel():
        cleanup_mousewheel()
        result["path"] = None
        root.destroy()

    def on_ok():
        cleanup_mousewheel()
        result["path"] = state["selected_path"]
        root.destroy()

    btn_cancel = ttk.Button(bottom_frame, text="Cancel", command=on_cancel)
    btn_cancel.pack(side="right", padx=5)

    btn_ok = ttk.Button(bottom_frame, text="Load Selected", command=on_ok, state="disabled")
    btn_ok.pack(side="right", padx=5)

    # Thumbnail Loader
    def get_thumbnail(full_path):
        if full_path in img_cache:
            return img_cache[full_path]

        png_candidates = []
        base_no_ext = os.path.splitext(full_path)[0]
        png_candidates.append(base_no_ext + ".png")

        dirname = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        png_name = os.path.splitext(filename)[0] + ".png"
        png_candidates.append(os.path.join(dirname, "_previews", png_name))
        png_candidates.append(os.path.join(dirname, "Thumbnails", png_name))

        img = None
        for candidate in png_candidates:
            if os.path.exists(candidate):
                try:
                    photo = tk.PhotoImage(file=candidate)
                    w, h = photo.width(), photo.height()
                    if w > thumb_size or h > thumb_size:
                        factor = max(1, int(max(w, h) / thumb_size))
                        photo = photo.subsample(factor)
                    img = photo
                    break
                except Exception:
                    pass

        img_cache[full_path] = img
        return img

    def select_item(path, frame_widget):
        state["selected_path"] = path
        btn_ok.config(state="normal")
        if state["selected_btn"] and state["selected_btn"].winfo_exists():
            state["selected_btn"].config(relief="flat", bg="#ffffff")
        state["selected_btn"] = frame_widget
        try:
            frame_widget.config(relief="solid", bg="#e3f2fd")
        except Exception:
            pass

    def render_cards():
        for widget in grid_frame.winfo_children():
            widget.destroy()

        q = search_var.get().strip().lower()
        if q == placeholder_text.lower():
            q = ""

        current = state["folder"]
        node_info = get_node(current)

        if current:
            crumb_var.set("Library > " + " > ".join(current))
            btn_up.config(state="normal")
        else:
            crumb_var.set("Library (Root)")
            btn_up.config(state="disabled")

        items_to_render = []

        if q:
            crumb_var.set(f"Search Results for '{q}'")
            for lbl, full in blocks:
                if q in lbl.lower():
                    parts = lbl.replace("\\", "/").split("/")
                    name = parts[-1]
                    cap = "in " + ("/".join(parts[:-1]) or "root")
                    items_to_render.append(("block", name, lbl, full, cap))
        elif state["show_all"]:
            crumb_var.set("All Items (Alphabetical)")
            btn_all.config(text="📁 Folders")
            flat = []
            for lbl, full in blocks:
                parts = lbl.replace("\\", "/").split("/")
                flat.append(("block", parts[-1], lbl, full, "in " + ("/".join(parts[:-1]) or "root")))
            flat.sort(key=lambda x: x[1].lower())
            items_to_render = flat
        else:
            btn_all.config(text="🗂 Show All")
            # Folders first
            for d in sorted(node_info["dirs"]):
                cnt = count_blocks(current + (d,))
                items_to_render.append(("folder", d, current + (d,), cnt))
            # Blocks next
            for name, lbl, full in node_info["blocks"]:
                items_to_render.append(("block", name, lbl, full, None))

        status_var.set(f"Showing {len(items_to_render)} item(s)")

        col = 0
        row = 0
        max_cols = columns

        for item in items_to_render:
            if item[0] == "folder":
                fname, target_folder, count = item[1], item[2], item[3]
                card = tk.Frame(grid_frame, bg="#ffffff", bd=1, relief="flat", padx=8, pady=8, width=thumb_size+20, height=thumb_size+30)
                card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
                card.grid_propagate(False)

                lbl_icon = tk.Label(card, text="📁", font=("sans-serif", 28), bg="#ffffff")
                lbl_icon.pack(pady=(4, 2))

                lbl_title = tk.Label(card, text=fname, font=("sans-serif", 9, "bold"), bg="#ffffff", wraplength=thumb_size)
                lbl_title.pack()

                lbl_cnt = tk.Label(card, text=f"{count} item{'s' if count!=1 else ''}", font=("sans-serif", 8), fg="#777777", bg="#ffffff")
                lbl_cnt.pack()

                def make_enter(tf):
                    return lambda e: enter_folder(tf)
                def enter_folder(tf):
                    state["folder"] = tf
                    search_var.set("")
                    render_cards()

                card.bind("<Button-1>", make_enter(target_folder))
                lbl_icon.bind("<Button-1>", make_enter(target_folder))
                lbl_title.bind("<Button-1>", make_enter(target_folder))
                lbl_cnt.bind("<Button-1>", make_enter(target_folder))

            else:
                bname, blabel, bfull, caption = item[1], item[2], item[3], item[4]
                card = tk.Frame(grid_frame, bg="#ffffff", bd=1, relief="flat", padx=6, pady=6, width=thumb_size+20, height=thumb_size+45)
                card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
                card.grid_propagate(False)

                img = get_thumbnail(bfull)
                if img:
                    lbl_img = tk.Label(card, image=img, bg="#ffffff")
                    lbl_img.pack(pady=2)
                else:
                    cv = tk.Canvas(card, width=thumb_size-10, height=thumb_size-30, bg="#eef2f5", highlightthickness=0)
                    cv.pack(pady=2)
                    cv.create_rectangle(10, 10, thumb_size-20, thumb_size-40, fill="#ffffff", outline="#4a90e2", width=2)
                    cv.create_text((thumb_size-15)//2, (thumb_size-40)//2, text="📄", font=("sans-serif", 20))

                lbl_title = tk.Label(card, text=bname, font=("sans-serif", 9, "bold"), bg="#ffffff", wraplength=thumb_size+10)
                lbl_title.pack()

                if caption:
                    lbl_cap = tk.Label(card, text=caption, font=("sans-serif", 7), fg="#888888", bg="#ffffff", wraplength=thumb_size+10)
                    lbl_cap.pack()

                def make_select(p, c):
                    return lambda e: (select_item(p, c), on_ok())
                def make_dbl(p):
                    return lambda e: (select_item(p, card), on_ok())

                card.bind("<Button-1>", make_select(bfull, card))
                card.bind("<Double-Button-1>", make_dbl(bfull))
                for child in card.winfo_children():
                    child.bind("<Button-1>", make_select(bfull, card))
                    child.bind("<Double-Button-1>", make_dbl(bfull))

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def go_up():
        if state["folder"]:
            state["folder"] = state["folder"][:-1]
            render_cards()

    def toggle_all():
        state["show_all"] = not state["show_all"]
        render_cards()

    btn_up.config(command=go_up)
    btn_all.config(command=toggle_all)
    search_var.trace_add("write", lambda *args: render_cards())

    render_cards()
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()
    return result["path"]
