#!/usr/bin/env python3
"""7. Block Library

A shared, on-disk library of Quilt Tools FPP blocks. Blocks are stored as
self-contained SVG files (each carrying its embedded RegionTree JSON) inside a
``BlockLibrary`` folder that sits directly beside this extension's scripts.

Selection options, in order of friendliness:
  * "Browse visual library" - an in-Inkscape thumbnail picker (GTK). Click a
    block to load it. Its file browser is pinned to the BlockLibrary folder.
    Falls back to the browser catalogue if GTK is unavailable.
  * "Open visual library"    - a thumbnail catalogue in your web browser.
  * "Choose a block" dropdown - populated from the library; run "Refresh
    library dropdown" after adding/removing blocks to update it.
"""
import os
import copy
import webbrowser
import urllib.parse
import html as _html

import inkex
from lxml import etree

import quilttools_fpp_core as core

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(EXT_DIR, "BlockLibrary")
INX_PATH = os.path.join(EXT_DIR, "quilttools_fpp_block_library.inx")
EXT_NS = "http://www.inkscape.org/namespace/inkscape/extension"
CATALOGUE_FILE = "_catalogue.html"


def _safe_filename(name):
    name = (name or "").strip()
    keep = []
    for ch in name:
        keep.append(ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_")
    cleaned = "".join(keep).strip().strip(".")
    return cleaned or "Untitled Block"


def _scan_library():
    """Return a sorted list of (relative_label, full_path) for every .svg in
    the library (recursively)."""
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


def _find_in_library(name):
    name = (name or "").strip()
    if not name:
        return None
    target = name[:-4] if name.lower().endswith(".svg") else name
    target_norm = target.replace("\\", "/").lower()
    for label, full in _scan_library():
        if label.lower() == target_norm or os.path.basename(label).lower() == target_norm:
            return full
    return None


def _block_info(full_path):
    """Return (piece_count, width_in, height_in) for a block SVG, or Nones."""
    try:
        doc = etree.parse(full_path)
        bd = core.extract_block_data_from_svg_root(doc.getroot())
        if bd is None:
            return (None, None, None)
        n = len(bd.tree.leaf_regions())
        b = core.block_bounds(bd)
        if b is None:
            return (n, None, None)
        return (n, (b[2] - b[0]) / core.PX_PER_INCH, (b[3] - b[1]) / core.PX_PER_INCH)
    except Exception:
        return (None, None, None)


class BlockLibraryPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="load")
        pars.add_argument("--lib_block", type=str, default="")
        pars.add_argument("--svg_file", type=str, default="")
        pars.add_argument("--save_name", type=str, default="")
        pars.add_argument("--resize_page", type=inkex.Boolean, default=True)
        pars.add_argument("--overwrite", type=inkex.Boolean, default=False)
        pars.add_argument("--import_w_in", type=float, default=6.0)

    def effect(self):
        a = self.options.action
        if a == "save":
            return self._save()
        if a == "catalogue":
            return self._catalogue()
        if a == "refresh":
            return self._refresh()
        if a == "import_trace":
            return self._import_trace()
        if a == "browse_visual":
            return self._browse_visual()
        return self._load()

    # ------------------------------------------------------------------
    def _set_page(self, w_px, h_px):
        self.svg.set("width", f"{w_px}")
        self.svg.set("height", f"{h_px}")
        self.svg.set("viewBox", f"0 0 {w_px} {h_px}")
        namedview = self.svg.find(f".//{{{core.SODIPODI_NS}}}namedview")
        if namedview is not None:
            pages = namedview.findall(f"{{{core.INKSCAPE_NS}}}page")
            if pages:
                pages[0].set("x", "0")
                pages[0].set("y", "0")
                pages[0].set("width", str(w_px))
                pages[0].set("height", str(h_px))

    # ------------------------------------------------------------------
    # LOAD / REPLACE
    # ------------------------------------------------------------------
    def _load(self):
        f = (self.options.svg_file or "").strip()
        if f and os.path.isfile(f):
            return self._load_path(f)

        choice = (self.options.lib_block or "").strip()
        if not choice:
            return inkex.errormsg(
                "No block chosen.\n\n"
                "Pick one from the 'Choose a block' dropdown, or browse to an "
                "SVG with 'SVG file'.\n\n"
                "Tip: try Action = 'Browse visual library' for a thumbnail "
                "picker, or 'Refresh library dropdown' if the dropdown looks "
                "out of date."
            )
        path = _find_in_library(choice)
        if path is None:
            return inkex.errormsg(
                f"Could not find '{choice}' in the library.\n\n"
                "Run Action = 'Refresh library dropdown' and reopen this dialog."
            )
        return self._load_path(path)

    def _load_path(self, path):
        try:
            doc = etree.parse(path)
        except Exception as e:
            return inkex.errormsg(f"Could not read SVG file:\n  {path}\n{e}")

        new_bd = core.extract_block_data_from_svg_root(doc.getroot())
        if new_bd is None:
            return inkex.errormsg(
                "That SVG is not a Quilt Tools block (no embedded block data).\n\n"
                "To bring a plain/foreign FPP SVG in for tracing, use "
                "Action = 'Import external SVG as tracing background'."
            )

        g_old, _ = core.find_fpp_group(self.svg)
        if g_old is not None and g_old.getparent() is not None:
            parent = g_old.getparent()
            parent.remove(g_old)
        else:
            parent = self.svg.get_current_layer()

        w_px, h_px = core.normalize_block_to_origin(new_bd)
        parent.append(core.build_fpp_layer(new_bd))
        if self.options.resize_page:
            self._set_page(w_px, h_px)

        n = len(new_bd.tree.leaf_regions())
        inkex.utils.debug(
            f'Loaded "{os.path.basename(path)}" '
            f'({w_px / core.PX_PER_INCH:.2f}" x {h_px / core.PX_PER_INCH:.2f}", '
            f"{n} pieces). Your previous block was replaced."
        )

    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------
    def _save(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found to save.")

        raw = (self.options.save_name or "").strip()
        if not raw:
            return inkex.errormsg("Please enter a name in 'Save as (block name)'.")

        raw = raw.replace("\\", "/")
        parts = [p for p in raw.split("/") if p.strip()]
        sub = [_safe_filename(p) for p in parts[:-1]]
        fname = _safe_filename(parts[-1]) + ".svg"
        out_dir = os.path.join(LIB_DIR, *sub)
        out_path = os.path.join(out_dir, fname)

        if os.path.isfile(out_path) and not self.options.overwrite:
            return inkex.errormsg(
                f"A block named '{parts[-1]}' already exists here:\n  {out_path}\n\n"
                "Tick 'Overwrite if it already exists' to replace it."
            )

        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            return inkex.errormsg(f"Could not create library folder:\n  {out_dir}\n{e}")

        save_bd = core.BlockData.from_json(block_data.to_json())
        core.normalize_block_to_origin(save_bd)
        svg_root = core.block_data_to_standalone_svg(save_bd, name=parts[-1])
        try:
            etree.ElementTree(svg_root).write(
                out_path, pretty_print=True, xml_declaration=True, encoding="UTF-8"
            )
        except Exception as e:
            return inkex.errormsg(f"Could not write block file:\n  {out_path}\n{e}")

        n = len(save_bd.tree.leaf_regions())
        b = core.block_bounds(save_bd)
        w_in = (b[2] - b[0]) / core.PX_PER_INCH if b else 0
        h_in = (b[3] - b[1]) / core.PX_PER_INCH if b else 0
        inkex.utils.debug(
            f'Saved "{parts[-1]}" ({w_in:.2f}" x {h_in:.2f}", {n} pieces) to:\n'
            f"  {out_path}\n\n"
            "Run Action = 'Refresh library dropdown' and reopen this dialog to "
            "see it in the dropdown."
        )

    # ------------------------------------------------------------------
    # REFRESH DROPDOWN (rewrite this extension's own .inx)
    # ------------------------------------------------------------------
    def _refresh(self):
        blocks = _scan_library()
        try:
            doc = etree.parse(INX_PATH)
        except Exception as e:
            return inkex.errormsg(
                f"Could not read the extension's .inx to refresh the dropdown:\n"
                f"  {INX_PATH}\n{e}"
            )
        root = doc.getroot()
        param = None
        for p in root.iter("{%s}param" % EXT_NS):
            if p.get("name") == "lib_block":
                param = p
                break
        if param is None:
            return inkex.errormsg("Could not find the dropdown parameter in the .inx.")

        for opt in list(param):
            param.remove(opt)
        ph = etree.SubElement(param, "{%s}option" % EXT_NS)
        ph.set("value", "")
        ph.text = "\u2014 choose a block \u2014"
        for label, _ in blocks:
            o = etree.SubElement(param, "{%s}option" % EXT_NS)
            o.set("value", label)
            o.text = label

        try:
            doc.write(INX_PATH, xml_declaration=True, encoding="UTF-8")
        except Exception as e:
            return inkex.errormsg(
                f"Could not write the updated .inx (is the extensions folder "
                f"writable?):\n  {INX_PATH}\n{e}"
            )

        listing = "\n".join(f"  - {lbl}" for lbl, _ in blocks) or "  (none yet)"
        inkex.utils.debug(
            f"Dropdown refreshed with {len(blocks)} block(s):\n{listing}\n\n"
            "IMPORTANT: close and reopen this extension dialog to see the "
            "updated dropdown. If it still looks stale, restart Inkscape "
            "(Inkscape only reloads extension menus on start-up)."
        )

    # ------------------------------------------------------------------
    # VISUAL CATALOGUE (browser)
    # ------------------------------------------------------------------
    def _build_catalogue_html(self):
        blocks = _scan_library()
        cards = []
        for label, full in blocks:
            rel = os.path.relpath(full, LIB_DIR).replace(os.sep, "/")
            src = urllib.parse.quote(rel)
            n, w_in, h_in = _block_info(full)
            meta = []
            if w_in and h_in:
                meta.append(f'{w_in:.2f}" x {h_in:.2f}"')
            if n is not None:
                meta.append(f"{n} pieces")
            meta_txt = _html.escape(" &middot; ".join(meta)) if meta else ""
            name_js = label.replace("\\", "\\\\").replace("'", "\\'")
            cards.append(
                f'<figure class="card" onclick="pick(\'{name_js}\')" title="Click to copy the name">'
                f'<div class="thumb"><img src="{src}" alt="{_html.escape(label)}" loading="lazy"></div>'
                f'<figcaption><span class="nm">{_html.escape(label)}</span>'
                f'<span class="mt">{meta_txt}</span></figcaption></figure>'
            )
        grid = "\n".join(cards) or "<p>No blocks in the library yet.</p>"
        page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quilt Tools - Block Library</title>
<style>
  :root {{ --ink:#1F3A5F; --accent:#7A9AB8; --muted:#7A7268; --paper:#FAF6EE; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--paper); color:var(--ink); }}
  header {{ padding:20px 24px; border-bottom:2px solid var(--ink); }}
  header h1 {{ margin:0 0 4px; font-size:20px; }}
  header p {{ margin:0; color:var(--muted); font-size:13px; }}
  .grid {{ display:grid; gap:16px; padding:24px;
           grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); }}
  .card {{ margin:0; background:#fff; border:1px solid #e3ddd0; border-radius:10px;
           overflow:hidden; cursor:pointer; transition:transform .08s, box-shadow .08s; }}
  .card:hover {{ transform:translateY(-2px); box-shadow:0 6px 18px rgba(31,58,95,.14);
                 border-color:var(--accent); }}
  .thumb {{ display:flex; align-items:center; justify-content:center;
            height:170px; padding:14px; background:#fcfaf5; }}
  .thumb img {{ max-width:100%; max-height:100%; }}
  figcaption {{ padding:10px 12px; border-top:1px solid #efeae0; }}
  .nm {{ display:block; font-weight:600; font-size:14px; }}
  .mt {{ display:block; color:var(--muted); font-size:12px; margin-top:2px; }}
  #toast {{ position:fixed; left:50%; bottom:24px; transform:translateX(-50%);
            background:var(--ink); color:#fff; padding:10px 16px; border-radius:8px;
            font-size:13px; opacity:0; transition:opacity .2s; pointer-events:none; }}
  #toast.show {{ opacity:1; }}
</style></head>
<body>
<header>
  <h1>Quilt Tools - Block Library</h1>
  <p>Click a block to copy its name, then load it from the
     <strong>Choose a block</strong> dropdown in Inkscape ({len(blocks)} block(s)).</p>
</header>
<div class="grid">
{grid}
</div>
<div id="toast"></div>
<script>
function pick(n){{
  if (navigator.clipboard) navigator.clipboard.writeText(n).catch(()=>{{}});
  var t=document.getElementById('toast');
  t.textContent='Copied: '+n;
  t.classList.add('show');
  setTimeout(function(){{ t.classList.remove('show'); }}, 1400);
}}
</script>
</body></html>"""
        out_path = os.path.join(LIB_DIR, CATALOGUE_FILE)
        os.makedirs(LIB_DIR, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(page)
        return out_path, len(blocks)

    def _catalogue(self, note=""):
        try:
            out_path, count = self._build_catalogue_html()
        except Exception as e:
            return inkex.errormsg(f"Could not build the visual catalogue:\n{e}")
        opened = False
        try:
            webbrowser.open(_path_to_uri(out_path))
            opened = True
        except Exception:
            opened = False
        msg = note + ("\n\n" if note else "")
        if opened:
            msg += f"Opened the visual library ({count} block(s)) in your browser."
        else:
            msg += (
                f"Built the visual library ({count} block(s)) but could not open a "
                f"browser automatically. Open this file manually:\n  {out_path}"
            )
        inkex.utils.debug(msg)

    # ------------------------------------------------------------------
    # IN-INKSCAPE VISUAL PICKER (GTK, experimental, with fallback)
    # ------------------------------------------------------------------
    def _browse_visual(self):
        blocks = _scan_library()
        if not blocks:
            return inkex.errormsg(
                f"The library is empty.\nLibrary folder:\n  {LIB_DIR}"
            )
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, GdkPixbuf
        except Exception:
            return self._catalogue(
                note="(In-Inkscape thumbnail window isn't available in this "
                "build, so the browser catalogue was opened instead.)"
            )

        chosen = {"path": None}
        try:
            dialog = Gtk.Dialog(title="Quilt Tools - Block Library")
            dialog.set_default_size(720, 560)
            content = dialog.get_content_area()

            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_vexpand(True)
            content.pack_start(scroller, True, True, 0)

            flow = Gtk.FlowBox()
            flow.set_valign(Gtk.Align.START)
            flow.set_max_children_per_line(4)
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_row_spacing(8)
            flow.set_column_spacing(8)
            flow.set_margin_top(10)
            flow.set_margin_bottom(10)
            flow.set_margin_start(10)
            flow.set_margin_end(10)
            scroller.add(flow)

            def make_click(p):
                def _cb(_btn):
                    chosen["path"] = p
                    dialog.response(Gtk.ResponseType.OK)
                return _cb

            for label, full in blocks:
                btn = Gtk.Button()
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(full, 150, 150, True)
                    box.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
                except Exception:
                    pass
                lbl = Gtk.Label(label=label)
                lbl.set_line_wrap(True)
                lbl.set_max_width_chars(18)
                box.pack_start(lbl, False, False, 0)
                btn.add(box)
                btn.connect("clicked", make_click(full))
                flow.add(btn)

            browse_btn = dialog.add_button("Browse files\u2026", 100)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.show_all()

            while True:
                resp = dialog.run()
                if resp == 100:
                    # Native file chooser, pinned to the library folder.
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
                        break
                    continue
                break
            dialog.destroy()
        except Exception as e:
            return self._catalogue(
                note=f"(Thumbnail window error: {e}. Opened the browser "
                "catalogue instead.)"
            )

        if not chosen["path"]:
            return inkex.utils.debug("No block selected.")
        return self._load_path(chosen["path"])

    # ------------------------------------------------------------------
    # IMPORT FOREIGN SVG (tracing background)
    # ------------------------------------------------------------------
    def _import_trace(self):
        f = (self.options.svg_file or "").strip()
        path = f if (f and os.path.isfile(f)) else _find_in_library(self.options.lib_block)
        if path is None:
            return inkex.errormsg("Browse to an SVG file with 'SVG file' first.")
        try:
            doc = etree.parse(path)
        except Exception as e:
            return inkex.errormsg(f"Could not read SVG file:\n  {path}\n{e}")
        root = doc.getroot()

        if core.extract_block_data_from_svg_root(root) is not None:
            return self._load_path(path)

        vb = root.get("viewBox")
        if vb:
            try:
                vx, vy, vw, vh = [float(x) for x in vb.replace(",", " ").split()]
            except Exception:
                vx = vy = vw = vh = 0.0
        else:
            vx = vy = 0.0
            vw = core.parse_svg_dim(root.get("width"), 0.0)
            vh = core.parse_svg_dim(root.get("height"), 0.0)
        if vw <= 0 or vh <= 0:
            vx = vy = 0.0
            vw = vh = self.options.import_w_in * core.PX_PER_INCH

        scale = (self.options.import_w_in * core.PX_PER_INCH) / vw
        wrapper = etree.SubElement(
            self.svg.get_current_layer(),
            "{%s}g" % core.SVG_NS,
            id=self.svg.get_unique_id("fpp-trace-bg"),
            transform=f"translate({-vx * scale},{-vy * scale}) scale({scale})",
            **{
                f"{{{core.INKSCAPE_NS}}}label": "FPP Trace Background",
                f"{{{core.INKSCAPE_NS}}}groupmode": "layer",
                f"{{{core.SODIPODI_NS}}}insensitive": "true",
            },
        )
        skip = {"defs", "namedview", "metadata", "title", "desc"}
        copied = 0
        for child in list(root):
            tag = etree.QName(child).localname if isinstance(child.tag, str) else ""
            if tag in skip:
                continue
            try:
                wrapper.append(copy.deepcopy(child))
                copied += 1
            except Exception:
                pass
        if copied == 0:
            if wrapper.getparent() is not None:
                wrapper.getparent().remove(wrapper)
            return inkex.errormsg("Nothing importable was found in that SVG.")

        inkex.utils.debug(
            f'Imported "{os.path.basename(path)}" as a locked tracing background '
            f'(~{self.options.import_w_in:.2f}" wide). Use New Block + Guillotine '
            "Cut to trace it. (This brings the artwork in for tracing; it does "
            "not auto-detect pieces.)"
        )


def _path_to_uri(path):
    try:
        import pathlib

        return pathlib.Path(path).as_uri()
    except Exception:
        return "file://" + path


if __name__ == "__main__":
    BlockLibraryPlugin().run()
