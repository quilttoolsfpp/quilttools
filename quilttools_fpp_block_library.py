#!/usr/bin/env python3
"""7. Block Library

A shared, on-disk library of Quilt Tools FPP blocks. Blocks are stored as
self-contained SVG files (each carrying its embedded RegionTree JSON) inside a
``BlockLibrary`` folder that sits directly beside this extension's scripts.

Actions:
  * load   - Replace the current block with one from the library.
  * save   - Save the current block into the library.
  * list   - List every block currently in the library.
  * import_trace - Bring a foreign (non-Quilt-Tools) SVG in as a locked
                   tracing background so it can be traced with New Block + Cut.
"""
import os
import copy

import inkex
from lxml import etree

import quilttools_fpp_core as core

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(EXT_DIR, "BlockLibrary")


def _safe_filename(name):
    name = (name or "").strip()
    keep = []
    for ch in name:
        if ch.isalnum() or ch in (" ", "-", "_"):
            keep.append(ch)
        else:
            keep.append("_")
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
                label = rel[:-4].replace(os.sep, "/")  # drop .svg, unixy
                found.append((label, full))
    found.sort(key=lambda x: x[0].lower())
    return found


def _find_in_library(name):
    """Resolve a block name (with or without subfolder / extension) to a path."""
    name = (name or "").strip()
    if not name:
        return None
    target = name[:-4] if name.lower().endswith(".svg") else name
    target_norm = target.replace("\\", "/").lower()
    for label, full in _scan_library():
        if label.lower() == target_norm or os.path.basename(label).lower() == target_norm:
            return full
    return None


class BlockLibraryPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="load")
        pars.add_argument("--block_name", type=str, default="")
        pars.add_argument("--svg_file", type=str, default="")
        pars.add_argument("--resize_page", type=inkex.Boolean, default=True)
        pars.add_argument("--overwrite", type=inkex.Boolean, default=False)
        pars.add_argument("--import_w_in", type=float, default=6.0)

    def effect(self):
        a = self.options.action
        if a == "save":
            return self._save()
        if a == "list":
            return self._list()
        if a == "import_trace":
            return self._import_trace()
        return self._load()

    # ------------------------------------------------------------------
    def _resolve_source_path(self):
        f = (self.options.svg_file or "").strip()
        if f and os.path.isfile(f):
            return f
        return _find_in_library(self.options.block_name)

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
    # LIST
    # ------------------------------------------------------------------
    def _list(self):
        blocks = _scan_library()
        if not blocks:
            return inkex.utils.debug(
                "The block library is empty.\n"
                f"Library folder:\n  {LIB_DIR}\n\n"
                "Use Action = 'Save current block to library' to add blocks, "
                "or drop Quilt Tools SVG files into that folder."
            )
        lines = [f"Block Library ({len(blocks)} block(s)) at:", f"  {LIB_DIR}", ""]
        lines.extend(f"  - {label}" for label, _ in blocks)
        lines.append("")
        lines.append(
            "To load one, run Action = 'Load block' and type its name into "
            "'Library block name' (or browse to its SVG file)."
        )
        inkex.utils.debug("\n".join(lines))

    # ------------------------------------------------------------------
    # LOAD / REPLACE
    # ------------------------------------------------------------------
    def _load(self):
        path = self._resolve_source_path()
        if path is None:
            return inkex.errormsg(
                "No block found to load.\n\n"
                "Either type an existing block name into 'Library block name', "
                "or browse to an SVG file with 'SVG file'.\n\n"
                f"Library folder:\n  {LIB_DIR}\n\n"
                "Tip: run Action = 'List library blocks' to see what's available."
            )

        try:
            doc = etree.parse(path)
        except Exception as e:
            return inkex.errormsg(f"Could not read SVG file:\n  {path}\n{e}")

        new_bd = core.extract_block_data_from_svg_root(doc.getroot())
        if new_bd is None:
            return inkex.errormsg(
                "That SVG is not a Quilt Tools block (it has no embedded block "
                "data).\n\nTo bring a plain/foreign FPP SVG in for tracing, use "
                "Action = 'Import external SVG as tracing background' instead."
            )

        # Remove the existing managed block (if any) and remember where it lived.
        g_old, _ = core.find_fpp_group(self.svg)
        if g_old is not None and g_old.getparent() is not None:
            parent = g_old.getparent()
            parent.remove(g_old)
        else:
            parent = self.svg.get_current_layer()

        w_px, h_px = core.normalize_block_to_origin(new_bd)
        new_g = core.build_fpp_layer(new_bd)
        parent.append(new_g)

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

        raw = (self.options.block_name or "").strip()
        if not raw:
            return inkex.errormsg(
                "Please enter a name for the block in 'Library block name'."
            )

        # Allow a subfolder via "Category/Block Name".
        raw = raw.replace("\\", "/")
        parts = [p for p in raw.split("/") if p.strip()]
        sub = [_safe_filename(p) for p in parts[:-1]]
        fname = _safe_filename(parts[-1]) + ".svg"
        out_dir = os.path.join(LIB_DIR, *sub)
        out_path = os.path.join(out_dir, fname)

        if os.path.isfile(out_path) and not self.options.overwrite:
            return inkex.errormsg(
                f"A block named '{parts[-1]}' already exists here:\n  {out_path}\n\n"
                "Tick 'Overwrite if it already exists' to replace it, or choose "
                "another name."
            )

        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            return inkex.errormsg(f"Could not create library folder:\n  {out_dir}\n{e}")

        # Deep-copy via JSON so we never disturb the live block, then normalise.
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
            f'Saved "{parts[-1]}" ({w_in:.2f}" x {h_in:.2f}", {n} pieces) to the '
            f"block library:\n  {out_path}"
        )

    # ------------------------------------------------------------------
    # IMPORT FOREIGN SVG (tracing background)
    # ------------------------------------------------------------------
    def _import_trace(self):
        path = self._resolve_source_path()
        if path is None:
            return inkex.errormsg(
                "Browse to an SVG file with 'SVG file' (or type a library name)."
            )
        try:
            doc = etree.parse(path)
        except Exception as e:
            return inkex.errormsg(f"Could not read SVG file:\n  {path}\n{e}")
        root = doc.getroot()

        # If it's actually a native block, loading it outright is better.
        if core.extract_block_data_from_svg_root(root) is not None:
            return self._load()

        # Work out the foreign coordinate system.
        vb = root.get("viewBox")
        if vb:
            try:
                vx, vy, vw, vh = [float(x) for x in vb.replace(",", " ").split()]
            except Exception:
                vx = vy = 0.0
                vw = vh = 0.0
        else:
            vx = vy = 0.0
            vw = core.parse_svg_dim(root.get("width"), 0.0)
            vh = core.parse_svg_dim(root.get("height"), 0.0)

        if vw <= 0 or vh <= 0:
            vx = vy = 0.0
            vw = vh = self.options.import_w_in * core.PX_PER_INCH

        target_w = self.options.import_w_in * core.PX_PER_INCH
        scale = target_w / vw

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
            return inkex.errormsg(
                "Nothing importable was found in that SVG."
            )

        inkex.utils.debug(
            f'Imported "{os.path.basename(path)}" as a locked tracing background '
            f'(~{self.options.import_w_in:.2f}" wide).\n\n'
            "Next: run '1. New Block' (with the trace visible) to lay down a "
            "managed block, then use '2. Guillotine Cut' to trace the seam "
            "lines. Note: this brings the artwork in for tracing; it does not "
            "yet auto-detect pieces."
        )


if __name__ == "__main__":
    BlockLibraryPlugin().run()
