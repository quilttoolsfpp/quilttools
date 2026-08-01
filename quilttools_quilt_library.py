#!/usr/bin/env python3
"""00. Quilt Library (Quilt Tools Pattern).

Save whole quilts into a QuiltLibrary folder and load them back later:

* COMPLETE quilts - saved verbatim: placed blocks, custom colours and
  fabric pattern fills all travel with the file.
* TEMPLATES - the layout only: placed blocks are stripped and every cell
  registry entry reset to empty, ready to be re-filled with
  'Fill Blocks from Library'.

(Distinct from New Quilt's layout PRESETS, which store only dialog
settings - a library entry is a full document snapshot.)

Files are standalone SVGs (openable directly in Inkscape too) stored as
QuiltLibrary/<Category>/<Name>.svg with metadata on the root element.
"""
import copy
import os
import re
import sys

from lxml import etree
import inkex

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import quilttools_fpp_core as core
import quilttools_quilt_core as qcore

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(EXT_DIR, "QuiltLibrary")
QUILT_KIND_ATTR = "data-quilttools-quilt-kind"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _safe_filename(name):
    return "".join(c if c.isalnum() or c in ("-", "_", " ") else "_"
                   for c in name).strip() or "Quilt"


def scan_quilt_library():
    """[(label 'Category/Name [template]', full_path), ...] sorted."""
    found = []
    if not os.path.isdir(LIB_DIR):
        return found
    for dirpath, _dirs, files in os.walk(LIB_DIR):
        for fn in files:
            if not fn.lower().endswith(".svg"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, LIB_DIR)[:-4].replace(os.sep, "/")
            kind = ""
            try:
                with open(full, "rb") as fh:
                    head = fh.read(4096).decode("utf-8", "replace")
                m = re.search(QUILT_KIND_ATTR + r'="([^"]+)"', head)
                if m:
                    kind = m.group(1)
            except Exception:
                pass
            label = rel + (" [template]" if kind == "template" else "")
            found.append((label, full))
    found.sort(key=lambda x: x[0].lower())
    return found


def _referenced_def_ids(scope_el):
    """All ids referenced via url(#...) or xlink:href within scope."""
    ids = set()
    for el in scope_el.iter():
        for attr in ("style", "fill", "stroke", "clip-path", "mask",
                     "filter"):
            v = el.get(attr)
            if v:
                ids.update(re.findall(r"url\(#([^)]+)\)", v))
        href = el.get(f"{{{XLINK_NS}}}href") or el.get("href")
        if href and href.startswith("#"):
            ids.add(href[1:])
    return ids


def gather_defs(src_root, scope_el):
    """Def elements (deep copies) needed by scope_el, following pattern
    href chains (fabric variants reference base patterns, which embed the
    image)."""
    by_id = {}
    for el in src_root.iter():
        el_id = el.get("id")
        if el_id and el_id not in by_id:
            by_id[el_id] = el
    needed, queue = [], list(_referenced_def_ids(scope_el))
    seen = set()
    while queue:
        did = queue.pop()
        if did in seen:
            continue
        seen.add(did)
        el = by_id.get(did)
        if el is None:
            continue
        # Skip anything already inside the scope (e.g. the quilt layer's
        # own <defs> travels with the layer copy).
        anc = el
        inside = False
        while anc is not None:
            if anc is scope_el:
                inside = True
                break
            anc = anc.getparent()
        if inside:
            continue
        needed.append(el)
        queue.extend(_referenced_def_ids(el))
        href = el.get(f"{{{XLINK_NS}}}href") or el.get("href")
        if href and href.startswith("#"):
            queue.append(href[1:])
    return needed


class QuiltLibraryPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--notebook", type=str, default="load_page")
        pars.add_argument("--action", type=str, default="load")
        pars.add_argument("--svg_file", type=str, default="")
        pars.add_argument("--replace_existing", type=inkex.Boolean,
                          default=False)
        pars.add_argument("--save_name", type=str, default="")
        pars.add_argument("--save_kind", type=str, default="complete")
        pars.add_argument("--overwrite", type=inkex.Boolean, default=False)

    def parse_arguments(self, args):
        self.options, _unknown = self.arg_parser.parse_known_args(args)

    def effect(self):
        if self.options.action == "save":
            return self._save()
        return self._load()

    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------
    def _save(self):
        g_quilt, quilt_data = qcore.find_quilt_group(self.svg)
        if g_quilt is None:
            return inkex.errormsg(
                "No Quilt Layout found on this canvas to save.\n"
                "Create one with Quilt Tools Pattern > 01. New Quilt.")

        raw = (self.options.save_name or "").strip().replace("\\", "/")
        if not raw:
            return inkex.errormsg(
                "Please enter a name in 'Save as (quilt name)'. Use "
                "Category/Name to file it in a subfolder.")
        parts = [p for p in raw.split("/") if p.strip()]
        sub = [_safe_filename(p) for p in parts[:-1]]
        fname = _safe_filename(parts[-1]) + ".svg"
        out_dir = os.path.join(LIB_DIR, *sub)
        out_path = os.path.join(out_dir, fname)
        as_template = self.options.save_kind == "template"

        if os.path.isfile(out_path) and not self.options.overwrite:
            return inkex.errormsg(
                f"A quilt named '{parts[-1]}' already exists here:\n"
                f"  {out_path}\n\nTick 'Overwrite if it already exists' "
                "to replace it.")
        os.makedirs(out_dir, exist_ok=True)

        layer = copy.deepcopy(g_quilt)

        if as_template:
            # Strip placed content and reset the registry so the saved
            # layout is ready for fresh fills.
            for placed in layer.findall(
                    f".//{{{core.SVG_NS}}}g[@class='placed-block-content']"):
                placed.getparent().remove(placed)
            desc = layer.find(
                f"{{{core.SVG_NS}}}desc[@id='{qcore.QUILT_DATA_TAG_ID}']")
            if desc is not None and desc.text:
                saved_qd = qcore.QuiltData.from_json(desc.text)
                for cid, info in saved_qd.cells.items():
                    if info.get("placed_block") is not None:
                        info["placed_block"] = None
                        if info.get("role") == "block":
                            info["state"] = "empty"
                desc.text = saved_qd.to_json()

        # Standalone document: keep the page size so loading restores it.
        w = self.svg.get("width") or "1000"
        h = self.svg.get("height") or "1000"
        viewbox = self.svg.get("viewBox") or f"0 0 {w} {h}"
        nsmap = {None: core.SVG_NS, "inkscape": core.INKSCAPE_NS,
                 "sodipodi": core.SODIPODI_NS, "xlink": XLINK_NS}
        root = etree.Element("{%s}svg" % core.SVG_NS, nsmap=nsmap)
        root.set("width", str(w))
        root.set("height", str(h))
        root.set("viewBox", viewbox)
        root.set("data-quilttools-quilt", "1")
        root.set("data-quilttools-name", parts[-1])
        root.set(QUILT_KIND_ATTR,
                 "template" if as_template else "complete")
        title = etree.SubElement(root, "{%s}title" % core.SVG_NS)
        title.text = parts[-1]

        # Fabric patterns etc. referenced from outside the layer (only
        # relevant for complete saves; templates lost their fills' users
        # but stray refs on plain cells are still honoured).
        defs_needed = gather_defs(self.svg, layer)
        if defs_needed:
            defs = etree.SubElement(root, "{%s}defs" % core.SVG_NS)
            for el in defs_needed:
                defs.append(copy.deepcopy(el))

        root.append(layer)
        etree.ElementTree(root).write(out_path, pretty_print=True,
                                      xml_declaration=True,
                                      encoding="UTF-8")
        inkex.utils.debug(
            "Saved %s '%s' to the Quilt Library:\n  %s" % (
                "TEMPLATE (layout only, blocks stripped)" if as_template
                else "COMPLETE quilt", parts[-1], out_path))

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------
    def _load(self):
        path = (self.options.svg_file or "").strip()
        if not path or not os.path.isfile(path):
            picked = self._pick_gtk()
            if picked is None:
                return  # cancelled or message already shown
            path = picked

        try:
            doc = etree.parse(path)
        except Exception as e:
            return inkex.errormsg(f"Could not read quilt file:\n  {path}\n{e}")
        src_root = doc.getroot()
        g_src, _qd = qcore.find_quilt_group(src_root)
        if g_src is None:
            return inkex.errormsg(
                "That file does not contain a Quilt Tools quilt layout:\n"
                f"  {path}")

        g_cur, _cur = qcore.find_quilt_group(self.svg)
        if g_cur is not None:
            if not self.options.replace_existing:
                return inkex.errormsg(
                    "This canvas already has a Quilt Layout.\n"
                    "Tick 'Replace the quilt already on this canvas' to "
                    "swap it for the loaded one (blocks/colours on the "
                    "current quilt will be discarded), or load into a "
                    "new empty document.")
            g_cur.getparent().remove(g_cur)

        # Copy referenced defs (fabric patterns etc.), skipping ids that
        # already exist here (same fabric already embedded).
        needed = gather_defs(src_root, g_src)
        if needed:
            cur_defs = self.svg.find(f"{{{core.SVG_NS}}}defs")
            if cur_defs is None:
                cur_defs = etree.SubElement(self.svg,
                                            "{%s}defs" % core.SVG_NS)
            existing = {el.get("id") for el in self.svg.iter()
                        if el.get("id")}
            for el in needed:
                if el.get("id") not in existing:
                    cur_defs.append(copy.deepcopy(el))

        self.svg.append(copy.deepcopy(g_src))

        # Restore the saved page size.
        w, h = src_root.get("width"), src_root.get("height")
        if w and h:
            self.svg.set("width", w)
            self.svg.set("height", h)
            self.svg.set("viewBox",
                         src_root.get("viewBox") or f"0 0 {w} {h}")

        kind = src_root.get(QUILT_KIND_ATTR) or "complete"
        name = src_root.get("data-quilttools-name") or \
            os.path.basename(path)[:-4]
        nxt = ("Fill it with Quilt Tools Pattern > 02. Fill Blocks from "
               "Library." if kind == "template" else
               "Blocks, colours and fabrics loaded as saved.")
        inkex.utils.debug(f"Loaded {kind} quilt '{name}'. {nxt}")

    # ------------------------------------------------------------------
    def _pick_gtk(self):
        quilts = scan_quilt_library()
        if not quilts:
            inkex.errormsg(
                "The Quilt Library is empty.\n\nSave the quilt on your "
                f"canvas first (Save tab), or place SVGs under:\n  {LIB_DIR}")
            return None
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, GdkPixbuf
            import quilttools_blockpicker as qpick
        except Exception:
            try:
                import quilttools_blockpicker as qpick
                return qpick.pick_block_tk("Quilt Tools - Quilt Library", quilts)
            except Exception:
                names = "\n".join("  - " + l for l, _ in quilts[:40])
                inkex.errormsg(
                    "Set 'Quilt file to load' to one of these paths instead:\n" + names)
                return None

        chosen = {"path": None}
        dialog = Gtk.Dialog(title="Quilt Tools - Quilt Library")
        dialog.set_default_size(820, 620)
        content = dialog.get_content_area()

        def on_pick(p):
            chosen["path"] = p
            dialog.response(Gtk.ResponseType.OK)

        browser = qpick.build_block_browser(
            Gtk, GdkPixbuf, quilts, on_pick, thumb=170, columns=3,
            label_chars=20)
        content.pack_start(browser["widget"], True, True, 0)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.show_all()
        resp = dialog.run()
        dialog.destroy()
        if resp != Gtk.ResponseType.OK or not chosen["path"]:
            return None
        return chosen["path"]


if __name__ == "__main__":
    QuiltLibraryPlugin().run()
