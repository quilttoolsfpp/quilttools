#!/usr/bin/env python3
"""03. Fabric Palette

Colour your quilt with *fabric* instead of flat colours.

Fabrics are bitmap images (photos or scans of real fabric) kept in a
``FabricLibrary`` folder that sits beside the Quilt Tools extension files.
Each fabric knows its real-world size ("this image shows 4 inches of
fabric"), so when it is applied as a fill the print repeats at true scale
on the page - a 12" block filled with a 1" gingham really shows 12 checks.

Applying a fabric turns it into an SVG <pattern> stored inside the
document itself, so a saved SVG carries its own fabrics and opens
correctly on any computer.
"""
import base64
import html as _html
import json
import os
import re
import struct
import urllib.parse
import webbrowser

import inkex
from lxml import etree

import quilttools_svg as qsvg

SVG_NS = qsvg.SVG_NS
INKSCAPE_NS = qsvg.INKSCAPE_NS
XLINK_NS = "http://www.w3.org/1999/xlink"

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
FABRIC_DIR = os.path.join(EXT_DIR, "FabricLibrary")
CATALOGUE_FILE = "_catalogue.html"

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

PALETTE_LAYER_LABEL = "Fabric Palette"
ORIG_FILL_ATTR = "data-quilttools-orig-fill"
FABRIC_PATTERN_ATTR = "data-quilttools-fabric"
SHAPE_TAGS = {"path", "rect", "circle", "ellipse", "polygon", "polyline"}


# ----------------------------------------------------------------------
# Image header readers (no PIL needed - Inkscape's Python may not ship it)
# ----------------------------------------------------------------------
def image_pixel_size(path):
    """Return (width_px, height_px) for PNG/JPEG/GIF/BMP, or (None, None)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(26)
            if len(head) < 10:
                return (None, None)
            # PNG
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", head[16:24])
                return (int(w), int(h))
            # GIF
            if head[:6] in (b"GIF87a", b"GIF89a"):
                w, h = struct.unpack("<HH", head[6:10])
                return (int(w), int(h))
            # BMP
            if head[:2] == b"BM":
                fh.seek(18)
                w, h = struct.unpack("<ii", fh.read(8))
                return (int(w), abs(int(h)))
            # JPEG - walk the markers until a start-of-frame
            if head[:2] == b"\xff\xd8":
                fh.seek(2)
                while True:
                    marker = fh.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return (None, None)
                    code = marker[1]
                    if code in (0xD8, 0x01) or 0xD0 <= code <= 0xD7:
                        continue
                    seg_len = struct.unpack(">H", fh.read(2))[0]
                    if code in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        fh.read(1)  # bit depth
                        h, w = struct.unpack(">HH", fh.read(4))
                        return (int(w), int(h))
                    fh.seek(seg_len - 2, os.SEEK_CUR)
    except Exception:
        pass
    return (None, None)


# ----------------------------------------------------------------------
# Fabric library on disk
# ----------------------------------------------------------------------
def _safe_filename(name):
    name = (name or "").strip()
    keep = [ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_" for ch in name]
    cleaned = "".join(keep).strip().strip(".")
    return cleaned or "Untitled Fabric"


def _slug(name):
    s = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "fabric"


def scan_fabrics():
    """Return a sorted list of fabric dicts:
    {label, img_path, name, width_in, height_in, px_w, px_h, tags}.
    label includes any subfolder, e.g. 'Florals/Rose Red'."""
    found = []
    if not os.path.isdir(FABRIC_DIR):
        return found
    for dirpath, _dirs, files in os.walk(FABRIC_DIR):
        for fn in files:
            base, ext = os.path.splitext(fn)
            if ext.lower() not in IMAGE_EXTS:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, FABRIC_DIR)
            label = os.path.splitext(rel)[0].replace(os.sep, "/")
            meta = {}
            meta_path = os.path.join(dirpath, base + ".json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as fh:
                        meta = json.load(fh)
                except Exception:
                    meta = {}
            px_w = meta.get("px_w") or None
            px_h = meta.get("px_h") or None
            if not (px_w and px_h):
                px_w, px_h = image_pixel_size(full)
            width_in = float(meta.get("width_in") or 4.0)
            if meta.get("height_in"):
                height_in = float(meta["height_in"])
            elif px_w and px_h:
                height_in = width_in * float(px_h) / float(px_w)
            else:
                height_in = width_in
            found.append({
                "label": label,
                "img_path": full,
                "name": meta.get("name") or os.path.basename(label),
                "width_in": width_in,
                "height_in": height_in,
                "px_w": px_w,
                "px_h": px_h,
                "tags": meta.get("tags") or [],
            })
    found.sort(key=lambda f: f["label"].lower())
    return found


def find_fabric(fabrics, query):
    """Find a fabric by name: exact label, exact name, then substring."""
    q = (query or "").strip().lower()
    if not q:
        return None
    for f in fabrics:
        if f["label"].lower() == q or f["name"].lower() == q:
            return f
    hits = [f for f in fabrics if q in f["label"].lower() or q in f["name"].lower()]
    return hits[0] if len(hits) >= 1 else None


# ----------------------------------------------------------------------
# Main plugin
# ----------------------------------------------------------------------
class FabricPalettePlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--notebook", type=str, default="apply")
        # Apply tab
        pars.add_argument("--fabric_name", type=str, default="")
        pars.add_argument("--apply_to", type=str, default="selection")
        # Recolour tab
        pars.add_argument("--plain_colour", type=str, default="0x888888ff")
        pars.add_argument("--recolour_scope", type=str, default="selection")
        pars.add_argument("--colour_source", type=str, default="ask")
        # Shared by recolour + fabric apply: explicit colour to match for
        # the "same colour" scopes (blank = derive from selection, asking
        # via a swatch chooser when the selection holds several colours).
        pars.add_argument("--match_colour", type=str, default="")
        pars.add_argument("--scale_pct", type=float, default=100.0)
        pars.add_argument("--rotation", type=float, default=0.0)
        pars.add_argument("--embed", type=inkex.Boolean, default=True)
        # Import tab
        pars.add_argument("--image_file", type=str, default="")
        pars.add_argument("--fabric_name_new", type=str, default="")
        pars.add_argument("--real_width_in", type=float, default=4.0)
        pars.add_argument("--tags", type=str, default="")
        pars.add_argument("--overwrite", type=inkex.Boolean, default=False)
        # Palette sheet tab
        pars.add_argument("--sheet_filter", type=str, default="")
        pars.add_argument("--sheet_size_in", type=float, default=2.0)
        # Remove tab
        pars.add_argument("--revert_scope", type=str, default="selection")

    def effect(self):
        page = (self.options.notebook or "apply").strip().strip('"')
        if page == "import":
            return self._import_fabric()
        if page == "sheet":
            return self._palette_sheet()
        if page == "revert":
            return self._revert()
        if page == "catalogue":
            return self._catalogue()
        if page == "recolour":
            return self._recolour()
        return self._apply()

    # ------------------------------------------------------------------
    # Unit helpers
    # ------------------------------------------------------------------
    def _uu_per_inch(self):
        try:
            v = float(self.svg.unittouu("1in"))
            if v > 0:
                return v
        except Exception:
            pass
        return 96.0

    def _page_size_uu(self):
        vb = self.svg.get("viewBox")
        if vb:
            try:
                parts = [float(x) for x in vb.replace(",", " ").split()]
                if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
                    return parts[2], parts[3]
            except Exception:
                pass
        w = qsvg.safe_float_unit(self.svg, self.svg.get("width"))
        h = qsvg.safe_float_unit(self.svg, self.svg.get("height"))
        return (w or 816.0), (h or 1056.0)

    # ------------------------------------------------------------------
    # Pattern plumbing
    # ------------------------------------------------------------------
    def _get_defs(self):
        try:
            return self.svg.defs
        except Exception:
            pass
        d = self.svg.find(f"{{{SVG_NS}}}defs")
        if d is None:
            d = etree.SubElement(self.svg, f"{{{SVG_NS}}}defs")
        return d

    def _image_href(self, fabric):
        path = fabric["img_path"]
        ext = os.path.splitext(path)[1].lower()
        if self.options.embed:
            mime = MIME_BY_EXT.get(ext, "image/png")
            with open(path, "rb") as fh:
                data = base64.b64encode(fh.read()).decode("ascii")
            return f"data:{mime};base64,{data}"
        try:
            import pathlib
            return pathlib.Path(path).as_uri()
        except Exception:
            return "file:///" + path.replace("\\", "/")

    def _ensure_base_pattern(self, fabric):
        """Create (or reuse) the real-scale pattern for this fabric.
        Returns the pattern id."""
        pid = "qtfabric-" + _slug(fabric["label"])
        existing = self.svg.getElementById(pid)
        if existing is not None:
            return pid
        uu_in = self._uu_per_inch()
        w_uu = fabric["width_in"] * uu_in
        h_uu = fabric["height_in"] * uu_in
        defs = self._get_defs()
        pat = etree.SubElement(defs, f"{{{SVG_NS}}}pattern")
        pat.set("id", pid)
        pat.set("patternUnits", "userSpaceOnUse")
        pat.set("width", f"{w_uu:.4f}")
        pat.set("height", f"{h_uu:.4f}")
        pat.set(FABRIC_PATTERN_ATTR, fabric["label"])
        img = etree.SubElement(pat, f"{{{SVG_NS}}}image")
        img.set("x", "0")
        img.set("y", "0")
        img.set("width", f"{w_uu:.4f}")
        img.set("height", f"{h_uu:.4f}")
        img.set("preserveAspectRatio", "none")
        img.set(f"{{{XLINK_NS}}}href", self._image_href(fabric))
        return pid

    def _pattern_for(self, fabric, scale_pct, rotation):
        """Base pattern, or a light-weight variant that references it with a
        patternTransform (the image is only embedded once)."""
        base_id = self._ensure_base_pattern(fabric)
        s = max(scale_pct, 0.1) / 100.0
        if abs(s - 1.0) < 1e-6 and abs(rotation) < 1e-6:
            return base_id
        suffix = f"s{s:g}-r{rotation:g}".replace(".", "_").replace("-", "m")
        vid = f"{base_id}-{suffix}"
        if self.svg.getElementById(vid) is not None:
            return vid
        defs = self._get_defs()
        pat = etree.SubElement(defs, f"{{{SVG_NS}}}pattern")
        pat.set("id", vid)
        pat.set(f"{{{XLINK_NS}}}href", f"#{base_id}")
        pat.set("patternTransform", f"rotate({rotation:g}) scale({s:g})")
        pat.set(FABRIC_PATTERN_ATTR, fabric["label"])
        return vid

    # ------------------------------------------------------------------
    # Fill helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _own_fill(el):
        """The element's own fill (style property first, then attribute)."""
        style = el.get("style") or ""
        m = re.search(r"(?:^|;)\s*fill\s*:\s*([^;]+)", style)
        if m:
            return m.group(1).strip()
        return (el.get("fill") or "").strip() or None

    @staticmethod
    def _set_fill(el, value, remember_original=True):
        old = FabricPalettePlugin._own_fill(el)
        if (remember_original and old and not old.lower().startswith("url(")
                and old.lower() != "none" and not el.get(ORIG_FILL_ATTR)):
            el.set(ORIG_FILL_ATTR, old)
        style = el.get("style") or ""
        if re.search(r"(?:^|;)\s*fill\s*:", style):
            style = re.sub(r"((?:^|;)\s*fill\s*:\s*)[^;]+", r"\g<1>" + value, style)
        else:
            style = (style.rstrip(";") + ";" if style.strip() else "") + "fill:" + value
        el.set("style", style)
        if el.get("fill") is not None:
            del el.attrib["fill"]

    @staticmethod
    def _norm_colour(c):
        if not c:
            return None
        c = c.strip().lower()
        m = re.match(r"^#([0-9a-f])([0-9a-f])([0-9a-f])$", c)
        if m:
            return "#" + "".join(ch * 2 for ch in m.groups())
        return c

    def _in_palette_layer(self, el):
        cur = el
        while cur is not None:
            if cur.get(f"{{{INKSCAPE_NS}}}label") == PALETTE_LAYER_LABEL:
                return True
            cur = cur.getparent()
        return False

    def _all_shapes(self, root=None):
        root = root if root is not None else self.svg
        out = []
        for el in root.iter():
            tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
            if tag not in SHAPE_TAGS:
                continue
            # Skip anything living inside <defs> (pattern contents etc.)
            anc = el
            skip = False
            while anc is not None:
                atag = anc.tag.split("}")[-1] if isinstance(anc.tag, str) else ""
                if atag in ("defs", "pattern", "clipPath", "mask", "marker"):
                    skip = True
                    break
                anc = anc.getparent()
            if not skip:
                out.append(el)
        return out

    def _selected_elements(self):
        try:
            sel = list(self.svg.selection.values())
        except Exception:
            try:
                sel = list(self.svg.selected.values())
            except Exception:
                sel = []
        return sel

    def _selected_shapes(self):
        """Selected shapes, descending into selected groups/layers."""
        out = []
        for el in self._selected_elements():
            tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
            if tag in SHAPE_TAGS:
                out.append(el)
            else:
                out.extend(self._all_shapes(el))
        return out

    # ------------------------------------------------------------------
    # APPLY - colour objects with a fabric
    # ------------------------------------------------------------------
    def _apply(self):
        fabrics = scan_fabrics()
        if not fabrics:
            return inkex.errormsg(
                "Your fabric library is empty.\n\n"
                "Open the 'Import Fabric' tab first and add a photo or scan "
                "of a fabric.\n\nLibrary folder:\n  " + FABRIC_DIR
            )

        fabric = None
        typed = (self.options.fabric_name or "").strip()
        if typed:
            fabric = find_fabric(fabrics, typed)
            if fabric is None:
                names = "\n".join("  - " + f["label"] for f in fabrics[:40])
                return inkex.errormsg(
                    f'No fabric called "{typed}" was found.\n\n'
                    "Fabrics in your library:\n" + names
                )
        else:
            fabric = self._pick_fabric_gtk(fabrics)
            if fabric is None:
                return  # cancelled, or a message was already shown

        targets, scope_note = self._gather_targets()
        if targets is None:
            return  # colour chooser cancelled
        if not targets:
            return inkex.errormsg(
                "Nothing to colour.\n\n"
                "Select one or more shapes first (or pick a different "
                "'Apply the fabric to' choice), then run the tool again."
            )

        pid = self._pattern_for(fabric, self.options.scale_pct, self.options.rotation)
        for el in targets:
            self._set_fill(el, f"url(#{pid})")

        extras = []
        if abs(self.options.scale_pct - 100.0) > 1e-6:
            extras.append(f"scale {self.options.scale_pct:g}%")
        if abs(self.options.rotation) > 1e-6:
            extras.append(f"rotated {self.options.rotation:g}°")
        extra_txt = " (" + ", ".join(extras) + ")" if extras else ""
        inkex.utils.debug(
            f'Coloured {len(targets)} object(s) with "{fabric["name"]}" '
            f'- true size {fabric["width_in"]:.2f}" x {fabric["height_in"]:.2f}" '
            f"per repeat{extra_txt}; {scope_note}.\n\n"
            "Changed your mind? The 'Remove Fabric' tab puts the original "
            "colours back."
        )

    @staticmethod
    def _block_root(el):
        """Nearest ancestor that represents ONE block: a quilt layout cell
        (carries data-quilt-role) or a standalone FPP block layer. None if
        the element is not inside either."""
        cur = el
        while cur is not None:
            if cur.get("data-quilt-role") is not None or \
                    cur.get("id") == "fpp-quilttools-layer":
                return cur
            cur = cur.getparent()
        return None

    def _ref_fill(self, el):
        """Match key for 'same colour' scopes: the element's own fill —
        a plain colour OR a fabric pattern url — normalised."""
        return self._norm_colour(
            self._own_fill(el) or qsvg.resolve_element_fill(el))

    def _resolve_match_refs(self, selected):
        """Which colour(s) should the 'same colour' scopes match?

        Clicking a quilt block in Inkscape selects the WHOLE cell group, so
        the selection often holds many colours. Resolution order:
          1. an explicit --match_colour (hex) if given;
          2. the selection's single colour, when it only has one;
          3. otherwise a swatch chooser listing the selection's colours
             (and fabrics) so the user picks which to replace.
        Returns a set of normalised fills, empty set (nothing matchable) or
        None if the user cancelled the chooser."""
        explicit = (getattr(self.options, "match_colour", "") or "").strip()
        if explicit:
            c = self._parse_colour_opt(explicit) or self._norm_colour(explicit)
            return {c} if c else set()

        counts = {}
        for s in selected:
            ref = self._ref_fill(s)
            if ref and ref != "none":
                counts[ref] = counts.get(ref, 0) + 1
        if len(counts) <= 1:
            return set(counts)
        picked = self._pick_match_colours_gtk(counts)
        if picked is None:
            return None
        return picked or set(counts)

    def _pick_match_colours_gtk(self, counts):
        """Swatch chooser: tick the colour(s)/fabric(s) to replace.
        Returns a set (possibly empty = treat as all), or None on cancel.
        Falls back to matching every colour when GTK is unavailable."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, GdkPixbuf
        except Exception:
            inkex.utils.debug(
                "Colour chooser unavailable - matching every colour in the "
                "selection. Tip: Alt+click in Inkscape selects a single "
                "piece inside a block.")
            return set(counts)

        dialog = Gtk.Dialog(title="Which colour do you want to replace?")
        dialog.set_default_size(380, 90 + 34 * min(len(counts), 12))
        content = dialog.get_content_area()
        content.set_spacing(4)
        info = Gtk.Label(label="Your selection contains several colours.\n"
                               "Tick the one(s) to replace:")
        info.set_margin_top(8)
        content.pack_start(info, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for side in ("top", "bottom", "start", "end"):
            getattr(listbox, f"set_margin_{side}")(10)
        scroller.add(listbox)
        content.pack_start(scroller, True, True, 0)

        checks = []
        for ref in sorted(counts, key=lambda r: -counts[r]):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            chk = Gtk.CheckButton()
            m = re.match(r"^#([0-9a-f]{6})$", ref)
            if m:
                pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True,
                                          8, 22, 22)
                pb.fill(int(m.group(1), 16) << 8 | 0xFF)
                row.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
                label_txt = ref
            else:
                fm = re.match(r"url\(#qtfabric-([a-z0-9-]+)", ref)
                label_txt = ("fabric: " + fm.group(1).replace("-", " ")
                             if fm else ref)
            lbl = Gtk.Label(label=f"{label_txt}   ({counts[ref]} piece"
                                  f"{'s' if counts[ref] != 1 else ''})")
            lbl.set_halign(Gtk.Align.START)
            row.pack_start(chk, False, False, 0)
            row.pack_start(lbl, False, False, 0)
            listbox.pack_start(row, False, False, 0)
            checks.append((chk, ref))

        dialog.add_button("Replace ticked colour(s)", Gtk.ResponseType.OK)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.set_modal(True)
        dialog.set_keep_above(True)
        dialog.show_all()
        dialog.present()
        resp = dialog.run()
        picked = {ref for chk, ref in checks if chk.get_active()}
        dialog.destroy()
        if resp != Gtk.ResponseType.OK:
            return None
        return picked

    def _gather_targets(self, mode=None):
        mode = (mode if mode is not None
                else (self.options.apply_to or "selection")).strip()
        if mode == "layer":
            layer = self.svg.get_current_layer()
            shapes = [s for s in self._all_shapes(layer) if not self._in_palette_layer(s)]
            return shapes, "everything on the current layer"

        selected = self._selected_shapes()
        if mode in ("same_fill", "same_fill_block"):
            if not selected:
                return [], ""
            refs = self._resolve_match_refs(selected)
            if refs is None:
                return None, "cancelled"  # user closed the swatch chooser
            if not refs:
                return selected, "the selected object(s) only (no colour to match)"
            if mode == "same_fill_block":
                # Limit matching to the block(s)/cell(s) the selection is in.
                roots = []
                for s in selected:
                    r = self._block_root(s)
                    if r is not None and not any(r is x for x in roots):
                        roots.append(r)
                if not roots:
                    return selected, ("the selected object(s) only (not "
                                      "inside a quilt cell or block)")
                pool = []
                for r in roots:
                    pool.extend(self._all_shapes(r))
                note = "every object coloured %s within %d block(s)" % (
                    "/".join(sorted(refs)), len(roots))
            else:
                pool = self._all_shapes()
                note = "every object coloured %s in the document" % (
                    "/".join(sorted(refs)))
            seen = set()
            matches = []
            for s in pool:
                if id(s) in seen or self._in_palette_layer(s):
                    continue
                if self._ref_fill(s) in refs:
                    seen.add(id(s))
                    matches.append(s)
            return (matches or selected), note

        return selected, "the selected object(s)"

    # ------------------------------------------------------------------
    # RECOLOUR - plain colour replacement (piece / block / quilt scopes)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_colour_opt(raw):
        """Inkscape colour params arrive as a (possibly negative) 32-bit
        RGBA integer or 0x... string; accept plain hex too."""
        s = str(raw or "").strip()
        try:
            if re.match(r"^-?\d+$", s):
                rgba = int(s) & 0xFFFFFFFF
            elif re.match(r"^0x[0-9a-fA-F]+$", s):
                rgba = int(s, 16) & 0xFFFFFFFF
            else:
                s = s.lstrip("#").lower()
                if re.match(r"^[0-9a-f]{6}$", s):
                    return "#" + s
                if re.match(r"^[0-9a-f]{3}$", s):
                    return "#" + "".join(ch * 2 for ch in s)
                return None
            return "#%02x%02x%02x" % ((rgba >> 24) & 255,
                                      (rgba >> 16) & 255,
                                      (rgba >> 8) & 255)
        except Exception:
            return None

    # -- Inkscape session state (last colour, active palette) -----------

    _CSS_BASIC = {"black": "#000000", "white": "#ffffff", "red": "#ff0000",
                  "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00",
                  "cyan": "#00ffff", "magenta": "#ff00ff", "gray": "#808080",
                  "grey": "#808080", "orange": "#ffa500", "purple": "#800080"}

    @staticmethod
    def _inkscape_prefs():
        try:
            profile = os.environ.get("INKSCAPE_PROFILE_DIR") or \
                os.path.join(os.environ.get("APPDATA", ""), "inkscape")
            path = os.path.join(profile, "preferences.xml")
            if os.path.isfile(path):
                return etree.parse(path).getroot()
        except Exception:
            pass
        return None

    def _last_used_colour(self):
        """The colour on Inkscape's paint indicator (last style applied via
        palette / eyedropper / fill dialog), from preferences.xml."""
        prefs = self._inkscape_prefs()
        if prefs is None:
            return None
        for gid in ("desktop", "paintbucket"):
            for el in prefs.iter():
                if el.get("id") == gid and el.get("style"):
                    m = re.search(r"fill\s*:\s*([^;]+)", el.get("style"))
                    if not m:
                        continue
                    val = m.group(1).strip().lower()
                    if val in ("none", "currentcolor"):
                        continue
                    val = self._CSS_BASIC.get(val, val)
                    c = self._norm_colour(val)
                    if c and re.match(r"^#[0-9a-f]{6}$", c):
                        return c
        return None

    def _active_palette(self):
        """(name, [(hex, swatch name), ...], columns) for the palette
        currently selected in Inkscape's swatches panel, or None."""
        prefs = self._inkscape_prefs()
        if prefs is None:
            return None
        pal_ref = None
        for el in prefs.iter():
            if el.get("id") == "swatches" and el.get("palette"):
                pal_ref = el.get("palette")
        if not pal_ref:
            return None
        candidates = []
        if os.path.isabs(pal_ref):
            candidates.append(pal_ref)
        else:
            for base in (
                os.path.join(os.environ.get("APPDATA", ""), "inkscape", "palettes"),
                r"C:\Program Files\Inkscape\share\inkscape\palettes",
            ):
                candidates.append(os.path.join(base, pal_ref))
                candidates.append(os.path.join(base, pal_ref + ".gpl"))
        path = next((c for c in candidates if os.path.isfile(c)), None)
        if path is None:
            return None
        name = os.path.splitext(os.path.basename(path))[0]
        cols = 8
        swatches = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if line.lower().startswith("name:"):
                        name = line[5:].strip() or name
                    elif line.lower().startswith("columns:"):
                        try:
                            cols = max(4, int(line[8:].strip()))
                        except ValueError:
                            pass
                    else:
                        m = re.match(r"^(\d+)\s+(\d+)\s+(\d+)\s*(.*)$", line)
                        if m:
                            r_, g_, b_ = (min(255, int(v))
                                          for v in m.groups()[:3])
                            swatches.append(("#%02x%02x%02x" % (r_, g_, b_),
                                             m.group(4).strip()))
        except Exception:
            return None
        return (name, swatches, cols) if swatches else None

    def _pick_new_colour_gtk(self, default_hex):
        """Palette-first colour picker: the active Inkscape palette as the
        grid, the current tool colour as the one-click default, and a
        'Colour wheel...' escape hatch. Returns hex or None (cancelled)."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, GdkPixbuf, Gdk
        except Exception:
            return default_hex  # headless: fall back to the given default

        pal = self._active_palette()
        picked = {"hex": None}

        dialog = Gtk.Dialog(title="New colour")
        dialog.set_default_size(560, 460)
        content = dialog.get_content_area()
        content.set_spacing(6)

        def swatch_pixbuf(hex_col, size=22):
            pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                      size, size)
            pb.fill(int(hex_col[1:], 16) << 8 | 0xFF)
            return pb

        if default_hex:
            cur_btn = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.pack_start(Gtk.Image.new_from_pixbuf(
                swatch_pixbuf(default_hex, 26)), False, False, 4)
            box.pack_start(Gtk.Label(
                label=f"Use current tool colour  {default_hex}"),
                False, False, 0)
            cur_btn.add(box)

            def use_current(_b):
                picked["hex"] = default_hex
                dialog.response(Gtk.ResponseType.OK)
            cur_btn.connect("clicked", use_current)
            cur_btn.set_margin_top(8)
            cur_btn.set_margin_start(10)
            cur_btn.set_margin_end(10)
            content.pack_start(cur_btn, False, False, 0)

        if pal:
            pal_name, swatches, cols = pal
            content.pack_start(Gtk.Label(label=f"Palette: {pal_name}"),
                               False, False, 0)
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER,
                                Gtk.PolicyType.AUTOMATIC)
            scroller.set_vexpand(True)
            grid = Gtk.FlowBox()
            grid.set_max_children_per_line(cols)
            grid.set_min_children_per_line(min(cols, 8))
            grid.set_selection_mode(Gtk.SelectionMode.NONE)
            for side in ("top", "bottom", "start", "end"):
                getattr(grid, f"set_margin_{side}")(10)

            def make_pick(hex_col):
                def _cb(_btn):
                    picked["hex"] = hex_col
                    dialog.response(Gtk.ResponseType.OK)
                return _cb

            for hex_col, sw_name in swatches:
                btn = Gtk.Button()
                btn.set_relief(Gtk.ReliefStyle.NONE)
                btn.add(Gtk.Image.new_from_pixbuf(swatch_pixbuf(hex_col, 26)))
                btn.set_tooltip_text(f"{sw_name or hex_col}  {hex_col}")
                btn.connect("clicked", make_pick(hex_col))
                grid.add(btn)
            scroller.add(grid)
            content.pack_start(scroller, True, True, 0)
        else:
            content.pack_start(Gtk.Label(
                label="(No Inkscape palette found - use the colour wheel)"),
                True, True, 0)

        dialog.add_button("Colour wheel…", 101)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.set_modal(True)
        dialog.set_keep_above(True)
        dialog.show_all()
        dialog.present()
        while True:
            resp = dialog.run()
            if resp == 101:
                cc = Gtk.ColorChooserDialog(title="New colour", parent=dialog)
                cc.set_use_alpha(False)
                if default_hex:
                    rgba = Gdk.RGBA()
                    rgba.parse(default_hex)
                    cc.set_rgba(rgba)
                if cc.run() == Gtk.ResponseType.OK:
                    rgba = cc.get_rgba()
                    picked["hex"] = "#%02x%02x%02x" % (
                        int(rgba.red * 255 + 0.5),
                        int(rgba.green * 255 + 0.5),
                        int(rgba.blue * 255 + 0.5))
                    cc.destroy()
                    dialog.destroy()
                    return picked["hex"]
                cc.destroy()
                continue
            dialog.destroy()
            return picked["hex"] if resp == Gtk.ResponseType.OK else None

    def _recolour(self):
        if (self.options.colour_source or "ask").strip() == "fixed":
            colour = self._parse_colour_opt(self.options.plain_colour)
        else:
            default_hex = self._last_used_colour() or \
                self._parse_colour_opt(self.options.plain_colour)
            colour = self._pick_new_colour_gtk(default_hex)
            if colour is None:
                return  # picker cancelled
        if colour is None:
            return inkex.errormsg("Could not read the chosen colour.")
        targets, scope_note = self._gather_targets(self.options.recolour_scope)
        if targets is None:
            return  # colour chooser cancelled
        if not targets:
            return inkex.errormsg(
                "Nothing to recolour.\n\nSelect one or more pieces first "
                "(any scope except 'current layer' starts from the "
                "selection), then run the tool again.")
        had_fabric = False
        for el in targets:
            if (self._own_fill(el) or "").lower().startswith("url("):
                had_fabric = True
            # The new plain colour IS the colour now: don't remember the
            # old one, and drop any pre-fabric memory so 'Remove Fabric'
            # cannot resurrect it over the top.
            self._set_fill(el, colour, remember_original=False)
            if el.get(ORIG_FILL_ATTR):
                del el.attrib[ORIG_FILL_ATTR]
        if had_fabric:
            self._remove_unused_patterns()
        inkex.utils.debug(
            f"Recoloured {len(targets)} object(s) to {colour}; {scope_note}.")

    # ------------------------------------------------------------------
    # GTK visual picker (mirrors the Block Library picker)
    # ------------------------------------------------------------------
    def _pick_fabric_gtk(self, fabrics):
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, GdkPixbuf
        except Exception:
            self._catalogue(
                note="(The visual fabric picker needs GTK, which isn't "
                "available in this build. Opened the browser catalogue "
                "instead - copy a fabric name from there into the "
                "'Fabric name' box and Apply again.)"
            )
            return None

        chosen = {"fab": None}
        try:
            dialog = Gtk.Dialog(title="Quilt Tools - Fabric Palette")
            dialog.set_default_size(760, 600)
            content = dialog.get_content_area()
            content.set_spacing(6)

            search = Gtk.SearchEntry()
            search.set_placeholder_text("Search fabrics by name, category, or tag...")
            search.set_margin_top(8)
            search.set_margin_start(10)
            search.set_margin_end(10)
            content.pack_start(search, False, False, 0)

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
            for side in ("top", "bottom", "start", "end"):
                getattr(flow, f"set_margin_{side}")(10)
            scroller.add(flow)

            empty = Gtk.Label(label="No fabrics match your search.")
            empty.set_no_show_all(True)
            content.pack_start(empty, False, False, 4)

            search_text = {}

            def make_click(f):
                def _cb(_btn):
                    chosen["fab"] = f
                    dialog.response(Gtk.ResponseType.OK)
                return _cb

            for fab in fabrics:
                btn = Gtk.Button()
                btn.set_relief(Gtk.ReliefStyle.NONE)
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        fab["img_path"], 140, 140, True)
                    box.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
                except Exception:
                    pass
                cap = f'{fab["label"]}\n{fab["width_in"]:.1f}" x {fab["height_in"]:.1f}"'
                lbl = Gtk.Label(label=cap)
                lbl.set_line_wrap(True)
                lbl.set_max_width_chars(18)
                lbl.set_justify(Gtk.Justification.CENTER)
                box.pack_start(lbl, False, False, 0)
                btn.add(box)
                btn.set_tooltip_text(fab["label"])
                btn.connect("clicked", make_click(fab))
                flow.add(btn)
                search_text[btn.get_parent()] = (
                    fab["label"] + " " + " ".join(fab["tags"])).lower()

            def do_filter(child):
                q = search.get_text().strip().lower()
                return (not q) or (q in search_text.get(child, ""))

            flow.set_filter_func(do_filter)

            def on_search(_w):
                flow.invalidate_filter()
                empty.set_visible(not any(do_filter(c) for c in search_text))

            search.connect("search-changed", on_search)

            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.set_modal(True)
            dialog.set_keep_above(True)
            dialog.show_all()
            dialog.present()
            search.grab_focus()
            dialog.run()
            dialog.destroy()
        except Exception as e:
            inkex.errormsg(
                f"The fabric picker window failed to open ({e}).\n"
                "Type the fabric's name in the 'Fabric name' box instead."
            )
            return None

        if chosen["fab"] is None:
            inkex.utils.debug("No fabric selected.")
        return chosen["fab"]

    # ------------------------------------------------------------------
    # IMPORT - add a fabric image to the library
    # ------------------------------------------------------------------
    def _crop_fabric_gtk(self, src):
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, GdkPixbuf, Gdk
        except Exception:
            return None

        px_w, px_h = image_pixel_size(src)
        if not px_w or not px_h:
            return None

        crop_values = {
            "left": 0,
            "right": px_w,
            "top": 0,
            "bottom": px_h,
            "success": False
        }

        try:
            dialog = Gtk.Dialog(title="Quilt Tools - Crop Fabric Image")
            dialog.set_default_size(600, 650)
            content = dialog.get_content_area()
            content.set_spacing(8)

            header = Gtk.Label()
            header.set_markup(
                "<span size='large' weight='bold'>Crop Fabric Photo / Scan</span>\n"
                "Adjust the crop margins to remove borders, rulers, or background."
            )
            header.set_justify(Gtk.Justification.CENTER)
            header.set_margin_top(8)
            content.pack_start(header, False, False, 0)

            scale_w = 450
            scale_h = 450
            if px_w > px_h:
                scale_h = int(450 * px_h / px_w)
            else:
                scale_w = int(450 * px_w / px_h)

            preview_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(src, scale_w, scale_h, True)

            area = Gtk.DrawingArea()
            area.set_size_request(450, 450)

            crop_left = 0
            crop_right = px_w
            crop_top = 0
            crop_bottom = px_h

            def draw_callback(widget, cr):
                alloc = widget.get_allocation()
                aw, ah = alloc.width, alloc.height
                pw, ph = preview_pb.get_width(), preview_pb.get_height()

                x = (aw - pw) / 2.0
                y = (ah - ph) / 2.0

                cr.set_source_rgb(0.95, 0.95, 0.95)
                cr.paint()

                Gdk.cairo_set_source_pixbuf(cr, preview_pb, x, y)
                cr.paint()

                scale_factor = pw / px_w
                cl_pre = crop_left * scale_factor
                cr_pre = crop_right * scale_factor
                ct_pre = crop_top * scale_factor
                cb_pre = crop_bottom * scale_factor

                cx1 = x + cl_pre
                cy1 = y + ct_pre
                cx2 = x + cr_pre
                cy2 = y + cb_pre

                cr.set_source_rgba(0.0, 0.0, 0.0, 0.5)
                if cy1 > y:
                    cr.rectangle(x, y, pw, cy1 - y)
                    cr.fill()
                if cy2 < y + ph:
                    cr.rectangle(x, cy2, pw, (y + ph) - cy2)
                    cr.fill()
                if cx1 > x:
                    cr.rectangle(x, cy1, cx1 - x, cy2 - cy1)
                    cr.fill()
                if cx2 < x + pw:
                    cr.rectangle(cx2, cy1, (x + pw) - cx2, cy2 - cy1)
                    cr.fill()

                cr.set_source_rgba(0.0, 0.8, 1.0, 0.8)
                cr.set_line_width(2.0)
                cr.rectangle(cx1, cy1, cx2 - cx1, cy2 - cy1)
                cr.stroke()
                return True

            area.connect("draw", draw_callback)

            frame = Gtk.AspectFrame(label=None, xalign=0.5, yalign=0.5, ratio=1.0, obey_child=False)
            frame.add(area)
            content.pack_start(frame, True, True, 0)

            grid = Gtk.Grid()
            grid.set_row_spacing(6)
            grid.set_column_spacing(12)
            grid.set_halign(Gtk.Align.CENTER)

            lbl_top = Gtk.Label(label="Top Crop (px):")
            lbl_top.set_halign(Gtk.Align.END)
            spin_top = Gtk.SpinButton.new_with_range(0, px_h - 2, 1)
            spin_top.set_value(0)
            grid.attach(lbl_top, 0, 0, 1, 1)
            grid.attach(spin_top, 1, 0, 1, 1)

            lbl_bottom = Gtk.Label(label="Bottom Crop (px):")
            lbl_bottom.set_halign(Gtk.Align.END)
            spin_bottom = Gtk.SpinButton.new_with_range(1, px_h, 1)
            spin_bottom.set_value(px_h)
            grid.attach(lbl_bottom, 2, 0, 1, 1)
            grid.attach(spin_bottom, 3, 0, 1, 1)

            lbl_left = Gtk.Label(label="Left Crop (px):")
            lbl_left.set_halign(Gtk.Align.END)
            spin_left = Gtk.SpinButton.new_with_range(0, px_w - 2, 1)
            spin_left.set_value(0)
            grid.attach(lbl_left, 0, 1, 1, 1)
            grid.attach(spin_left, 1, 1, 1, 1)

            lbl_right = Gtk.Label(label="Right Crop (px):")
            lbl_right.set_halign(Gtk.Align.END)
            spin_right = Gtk.SpinButton.new_with_range(1, px_w, 1)
            spin_right.set_value(px_w)
            grid.attach(lbl_right, 2, 1, 1, 1)
            grid.attach(spin_right, 3, 1, 1, 1)

            content.pack_start(grid, False, False, 4)

            size_lbl = Gtk.Label(label=f"Original: {px_w} x {px_h} px  -->  Cropped: {px_w} x {px_h} px")
            size_lbl.set_margin_top(4)
            content.pack_start(size_lbl, False, False, 0)

            def on_spin_changed(_spin):
                nonlocal crop_left, crop_right, crop_top, crop_bottom
                l = int(spin_left.get_value())
                r = int(spin_right.get_value())
                t = int(spin_top.get_value())
                b = int(spin_bottom.get_value())

                if l >= r:
                    l = r - 1
                    spin_left.set_value(l)
                if t >= b:
                    t = b - 1
                    spin_top.set_value(t)

                crop_left, crop_right, crop_top, crop_bottom = l, r, t, b
                size_lbl.set_text(f"Original: {px_w} x {px_h} px  -->  Cropped: {r - l} x {b - t} px")
                area.queue_draw()

            spin_left.connect("value-changed", on_spin_changed)
            spin_right.connect("value-changed", on_spin_changed)
            spin_top.connect("value-changed", on_spin_changed)
            spin_bottom.connect("value-changed", on_spin_changed)

            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button("Crop & Import", Gtk.ResponseType.OK)
            dialog.set_modal(True)
            dialog.set_keep_above(True)
            dialog.show_all()
            dialog.present()
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                crop_values["left"] = crop_left
                crop_values["right"] = crop_right
                crop_values["top"] = crop_top
                crop_values["bottom"] = crop_bottom
                crop_values["success"] = True

            dialog.destroy()
            while Gtk.events_pending():
                Gtk.main_iteration()
        except Exception as err:
            inkex.utils.debug(f"GTK Crop Dialog error: {err}")
            return None

        return crop_values

    def _import_fabric(self):
        src = (self.options.image_file or "").strip().strip('"')
        if not (src and os.path.isfile(src)):
            return inkex.errormsg(
                "Browse to a fabric image first (a photo or scan of the "
                "fabric, .png or .jpg)."
            )
        ext = os.path.splitext(src)[1].lower()
        if ext not in IMAGE_EXTS:
            return inkex.errormsg(
                f"'{os.path.basename(src)}' isn't a supported image.\n"
                "Please use a PNG, JPG, GIF, or BMP file."
            )

        px_w, px_h = image_pixel_size(src)
        if not (px_w and px_h):
            return inkex.errormsg(
                "Could not read that image's size. The file may be damaged - "
                "try re-saving it as a PNG or JPG."
            )

        # Show visual crop dialog
        crop = self._crop_fabric_gtk(src)
        if crop is not None:
            if not crop["success"]:
                return  # Cancelled by user
            crop_left = crop["left"]
            crop_right = crop["right"]
            crop_top = crop["top"]
            crop_bottom = crop["bottom"]
        else:
            crop_left = 0
            crop_right = px_w
            crop_top = 0
            crop_bottom = px_h

        cropped_w = crop_right - crop_left
        cropped_h = crop_bottom - crop_top

        width_in = float(self.options.real_width_in or 0)
        if width_in <= 0:
            return inkex.errormsg(
                "Please enter the real width of the fabric shown in the "
                "image, in inches.\n\nTip: lay a ruler beside the fabric "
                "when you photograph it, then crop the photo to a known "
                "width (say exactly 4 inches of fabric)."
            )
        height_in = width_in * float(cropped_h) / float(cropped_w)

        raw = (self.options.fabric_name_new or "").strip()
        if not raw:
            raw = os.path.splitext(os.path.basename(src))[0]
        raw = raw.replace("\\", "/")
        parts = [p for p in raw.split("/") if p.strip()]
        sub = [_safe_filename(p) for p in parts[:-1]]
        fname = _safe_filename(parts[-1])
        out_dir = os.path.join(FABRIC_DIR, *sub)
        img_out = os.path.join(out_dir, fname + ext)
        meta_out = os.path.join(out_dir, fname + ".json")

        if os.path.isfile(img_out) and not self.options.overwrite:
            return inkex.errormsg(
                f"A fabric named '{parts[-1]}' already exists:\n  {img_out}\n\n"
                "Tick 'Overwrite if it already exists' to replace it."
            )

        # Crop and copy image
        try:
            os.makedirs(out_dir, exist_ok=True)
            if crop_left > 0 or crop_right < px_w or crop_top > 0 or crop_bottom < px_h:
                from PIL import Image
                img = Image.open(src)
                cropped_img = img.crop((crop_left, crop_top, crop_right, crop_bottom))
                cropped_img.save(img_out)
            else:
                with open(src, "rb") as fi, open(img_out, "wb") as fo:
                    fo.write(fi.read())
        except Exception as e:
            # Fallback to copy original if PIL fails
            inkex.utils.debug(f"PIL crop failed ({e}), copying original uncropped image instead.")
            try:
                os.makedirs(out_dir, exist_ok=True)
                with open(src, "rb") as fi, open(img_out, "wb") as fo:
                    fo.write(fi.read())
                cropped_w = px_w
                cropped_h = px_h
                height_in = width_in * float(px_h) / float(px_w)
            except Exception as e2:
                return inkex.errormsg(f"Could not copy the image into the library:\n{e2}")

        tags = [t.strip().lower() for t in (self.options.tags or "").split(",") if t.strip()]
        meta = {
            "name": parts[-1],
            "width_in": width_in,
            "height_in": height_in,
            "px_w": cropped_w,
            "px_h": cropped_h,
            "tags": tags,
            "source_file": os.path.basename(src),
        }
        try:
            with open(meta_out, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2)
        except Exception as e:
            return inkex.errormsg(f"Could not write the fabric's details:\n{e}")

        try:
            self._build_catalogue_html()
        except Exception:
            pass

        dpi = cropped_w / width_in
        label = "/".join(sub + [fname]) if sub else fname
        size_desc = f"{cropped_w} x {cropped_h} pixels"
        if cropped_w != px_w or cropped_h != px_h:
            size_desc += f" (cropped from {px_w} x {px_h})"

        inkex.utils.debug(
            f'Added "{parts[-1]}" to your fabric library.\n\n'
            f'  Image: {size_desc}\n'
            f'  Real size: {width_in:.2f}" wide x {height_in:.2f}" high '
            f"({dpi:.0f} dpi)\n"
            f"  Saved as: {label}\n\n"
            "Use the 'Colour with Fabric' tab to paint it onto your quilt."
        )

    # ------------------------------------------------------------------
    # PALETTE SHEET - labelled swatches drawn into this document
    # ------------------------------------------------------------------
    def _palette_sheet(self):
        fabrics = scan_fabrics()
        filt = (self.options.sheet_filter or "").strip().lower()
        if filt:
            fabrics = [
                f for f in fabrics
                if filt in f["label"].lower()
                or any(filt in t for t in f["tags"])
            ]
        if not fabrics:
            return inkex.errormsg(
                "No fabrics to draw."
                + (f" (Nothing matched '{filt}'.)" if filt else
                   " Import some fabrics first on the 'Import Fabric' tab.")
            )

        uu_in = self._uu_per_inch()
        sw = max(self.options.sheet_size_in, 0.5) * uu_in
        gap = 0.35 * uu_in
        label_h = 0.30 * uu_in
        page_w, page_h = self._page_size_uu()

        # Reuse (and clear) an existing palette layer so re-running updates it.
        layer = None
        for g in self.svg.findall(f"{{{SVG_NS}}}g"):
            if g.get(f"{{{INKSCAPE_NS}}}label") == PALETTE_LAYER_LABEL:
                layer = g
                break
        if layer is None:
            layer = etree.SubElement(self.svg, f"{{{SVG_NS}}}g")
            layer.set(f"{{{INKSCAPE_NS}}}label", PALETTE_LAYER_LABEL)
            layer.set(f"{{{INKSCAPE_NS}}}groupmode", "layer")
            layer.set("id", "fabric-palette-layer")
        else:
            for child in list(layer):
                layer.remove(child)

        per_col = max(1, int((page_h - gap) // (sw + label_h + gap)))
        x0 = page_w + gap * 2
        for idx, fab in enumerate(fabrics):
            col, row = divmod(idx, per_col)
            x = x0 + col * (sw + gap)
            y = gap + row * (sw + label_h + gap)
            pid = self._ensure_base_pattern(fab)
            rect = etree.SubElement(layer, f"{{{SVG_NS}}}rect")
            rect.set("x", f"{x:.2f}")
            rect.set("y", f"{y:.2f}")
            rect.set("width", f"{sw:.2f}")
            rect.set("height", f"{sw:.2f}")
            rect.set("style", f"fill:url(#{pid});stroke:#333333;stroke-width:1;")
            txt = etree.SubElement(layer, f"{{{SVG_NS}}}text")
            txt.set("x", f"{x + sw / 2:.2f}")
            txt.set("y", f"{y + sw + label_h * 0.6:.2f}")
            txt.set("style",
                    "font-size:11px;font-family:sans-serif;text-anchor:middle;"
                    "fill:#333333;")
            txt.text = fab["name"]

        inkex.utils.debug(
            f"Drew {len(fabrics)} fabric swatch(es) on a '{PALETTE_LAYER_LABEL}' "
            "layer just to the right of your page. Each swatch shows the "
            "fabric at its true printed size.\n\n"
            "Tip: to copy a swatch's fabric onto another shape, click the "
            "swatch, press Ctrl+C, then select your shape and use "
            "Edit > Paste Style (Ctrl+Shift+V)."
        )

    # ------------------------------------------------------------------
    # REVERT - put the original solid colours back
    # ------------------------------------------------------------------
    def _revert(self):
        scope = (self.options.revert_scope or "selection").strip()
        if scope == "document":
            shapes = [s for s in self._all_shapes() if not self._in_palette_layer(s)]
        else:
            shapes = self._selected_shapes()
            if not shapes:
                return inkex.errormsg(
                    "Select the shapes you want to change back first "
                    "(or choose 'Whole document')."
                )

        n = 0
        for el in shapes:
            fill = self._own_fill(el) or ""
            if "url(#qtfabric-" not in fill.replace(" ", ""):
                continue
            orig = el.get(ORIG_FILL_ATTR) or "#cccccc"
            self._set_fill(el, orig, remember_original=False)
            if el.get(ORIG_FILL_ATTR):
                del el.attrib[ORIG_FILL_ATTR]
            n += 1

        removed = self._remove_unused_patterns()
        if n == 0:
            return inkex.utils.debug("No fabric fills were found there.")
        inkex.utils.debug(
            f"Put the original colour back on {n} object(s)."
            + (f" Cleaned up {removed} unused fabric pattern(s)." if removed else "")
        )

    def _remove_unused_patterns(self):
        """Delete qtfabric patterns nothing references any more (frees the
        embedded image data). Variants count as references to their base."""
        doc_txt = etree.tostring(self.svg, encoding="unicode")
        removed = 0
        # Two passes: variants first, then bases freed by their removal.
        for _ in range(2):
            defs = self._get_defs()
            doc_txt = etree.tostring(self.svg, encoding="unicode")
            for pat in list(defs.findall(f"{{{SVG_NS}}}pattern")):
                pid = pat.get("id") or ""
                if not pid.startswith("qtfabric-"):
                    continue
                refs = doc_txt.count(f"#{pid}") - doc_txt.count(f'id="{pid}"')
                # Count url(#pid) and href="#pid" references, excluding
                # accidental prefix matches from longer variant ids.
                real = len(re.findall(
                    r"(?:url\(#|href=\"#)" + re.escape(pid) + r"[\)\"]", doc_txt))
                if real == 0 and refs <= 0:
                    pat.getparent().remove(pat)
                    removed += 1
        return removed

    # ------------------------------------------------------------------
    # CATALOGUE - browsable thumbnail gallery in the web browser
    # ------------------------------------------------------------------
    def _build_catalogue_html(self):
        fabrics = scan_fabrics()
        cards = []
        for fab in fabrics:
            rel = os.path.relpath(fab["img_path"], FABRIC_DIR).replace(os.sep, "/")
            src = urllib.parse.quote(rel)
            size_txt = f'{fab["width_in"]:.2f}" x {fab["height_in"]:.2f}" per repeat'
            tags_html = ""
            if fab["tags"]:
                pills = "".join(
                    f'<span class="tag">{_html.escape(t)}</span>' for t in fab["tags"])
                tags_html = f'<div class="tags">{pills}</div>'
            name_js = fab["label"].replace("\\", "\\\\").replace("'", "\\'")
            cards.append(
                f'<figure class="card" data-name="{_html.escape(fab["label"])}" '
                f'data-tags="{_html.escape(",".join(fab["tags"]))}" '
                f'onclick="pick(\'{name_js}\')" title="Click to copy the name">'
                f'<div class="thumb"><img src="{src}" alt="{_html.escape(fab["label"])}" loading="lazy"></div>'
                f'<figcaption><span class="nm">{_html.escape(fab["label"])}</span>'
                f'<span class="mt">{_html.escape(size_txt)}</span>'
                f"{tags_html}</figcaption></figure>"
            )
        grid = "\n".join(cards) or "<p>No fabrics in the library yet.</p>"
        page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quilt Tools - Fabric Library</title>
<style>
  :root {{ --ink:#1F3A5F; --accent:#7A9AB8; --muted:#7A7268; --paper:#FAF6EE; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--paper); color:var(--ink); }}
  header {{ padding:18px 24px 14px; border-bottom:2px solid var(--ink);
            position:sticky; top:0; background:var(--paper); z-index:5; }}
  header h1 {{ margin:0 0 4px; font-size:20px; }}
  header p {{ margin:0 0 10px; color:var(--muted); font-size:13px; }}
  #q {{ width:100%; max-width:420px; padding:9px 12px; font-size:14px;
        border:1px solid var(--accent); border-radius:8px; }}
  .grid {{ display:grid; gap:16px; padding:24px;
           grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); }}
  .card {{ margin:0; background:#fff; border:1px solid #e3ddd0; border-radius:10px;
           overflow:hidden; cursor:pointer; transition:transform .08s, box-shadow .08s; }}
  .card:hover {{ transform:translateY(-2px); box-shadow:0 6px 18px rgba(31,58,95,.14);
                 border-color:var(--accent); }}
  .thumb {{ display:flex; align-items:center; justify-content:center;
            height:170px; background:#fcfaf5; overflow:hidden; }}
  .thumb img {{ width:100%; height:100%; object-fit:cover; }}
  figcaption {{ padding:10px 12px; border-top:1px solid #efeae0; }}
  .nm {{ display:block; font-weight:600; font-size:14px; }}
  .mt {{ display:block; color:var(--muted); font-size:12px; margin-top:2px; }}
  .tags {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }}
  .tag {{ font-size:10px; background:#e1e9f5; color:#1F3A5F; padding:2px 6px; border-radius:4px; font-weight:bold; }}
  #none {{ padding:0 24px 24px; color:var(--muted); display:none; }}
  #toast {{ position:fixed; left:50%; bottom:24px; transform:translateX(-50%);
            background:var(--ink); color:#fff; padding:10px 16px; border-radius:8px;
            font-size:13px; opacity:0; transition:opacity .2s; pointer-events:none; }}
  #toast.show {{ opacity:1; }}
</style></head>
<body>
<header>
  <h1>Quilt Tools - Fabric Library</h1>
  <p>{len(fabrics)} fabric(s). Click a fabric to copy its name, then paste it
     into the Fabric Palette tool (Extensions &rarr; Quilt Tools Pattern &rarr;
     03. Fabric Palette).</p>
  <input id="q" type="search" placeholder="Search by name, category, or tag..." oninput="flt()" autofocus>
</header>
<div class="grid" id="grid">
{grid}
</div>
<p id="none">No fabrics match your search.</p>
<div id="toast"></div>
<script>
function flt(){{
  var q=document.getElementById('q').value.trim().toLowerCase(), shown=0;
  document.querySelectorAll('.card').forEach(function(c){{
    var n=c.getAttribute('data-name').toLowerCase();
    var t=c.getAttribute('data-tags').toLowerCase();
    var ok=(!q || n.indexOf(q)>=0 || t.indexOf(q)>=0);
    c.style.display=ok?'':'none'; if(ok) shown++;
  }});
  document.getElementById('none').style.display=shown?'none':'block';
}}
function pick(n){{
  if (navigator.clipboard) navigator.clipboard.writeText(n).catch(function(){{}});
  var t=document.getElementById('toast');
  t.textContent='Copied: '+n; t.classList.add('show');
  setTimeout(function(){{ t.classList.remove('show'); }}, 1400);
}}
</script>
</body></html>"""
        os.makedirs(FABRIC_DIR, exist_ok=True)
        out_path = os.path.join(FABRIC_DIR, CATALOGUE_FILE)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(page)
        return out_path, len(fabrics)

    def _catalogue(self, note=""):
        try:
            out_path, count = self._build_catalogue_html()
        except Exception as e:
            return inkex.errormsg(f"Could not build the fabric catalogue:\n{e}")
        opened = False
        try:
            import pathlib
            webbrowser.open(pathlib.Path(out_path).as_uri())
            opened = True
        except Exception:
            opened = False
        msg = note + ("\n\n" if note else "")
        if opened:
            msg += f"Opened the fabric library ({count} fabric(s)) in your browser."
        else:
            msg += (
                f"Built the fabric library page ({count} fabric(s)) but could "
                f"not open a browser automatically. Open this file manually:\n"
                f"  {out_path}"
            )
        inkex.utils.debug(msg)


if __name__ == "__main__":
    FabricPalettePlugin().run()
