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
