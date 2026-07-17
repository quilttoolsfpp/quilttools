#!/usr/bin/env python3
# eqimport_to_guide.py
#
# Inkscape extension to import blocks from an Electric Quilt 8 (.pj8) or
# Electric Quilt 6 (.pj6) project file as guide layers in the current SVG.
#
# Each block in the source file becomes its own Inkscape layer containing:
#   - A rectangular block outline
#   - The interior cut lines as SVG line elements
#   - Optionally the patch polygons as translucent fills (for visual reference)
#
# All elements are marked data-fpp-ignore="true" so the Quilt Tools heal
# function will treat them as guides rather than as block geometry.
#
# The scan and guide-import actions are intentionally STAND-ALONE from the
# Quilt Tools suite (no Quilt Tools imports) and registered under their own
# menu entry ("Quilt Importer"). The optional "import into Block Library"
# action lazily imports quilttools_fpp_core to build fully compatible
# library block SVGs; it degrades with a clear error if the suite is absent.

import os
import struct
import inkex
from lxml import etree


SVG_NS      = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"

PX_PER_INCH    = 96.0       # Standard SVG/Inkscape scaling
EQ_MAX_COORD   = 20160      # EQ stores coordinates in 0..20160 per block axis
HUNDREDTHS     = 100.0      # Block dimensions stored as hundredths-of-inch

# Pre-defined colour palette for guide lines. RGB chosen to be visually
# distinct from the Quilt Tools internal-guide colour (cyan #00ffff).
LINE_COLOURS = {
    "blue":  "#0066cc",
    "red":   "#cc0000",
    "green": "#009933",
}


# ----------------------------------------------------------------------------
# File-format parsing
# ----------------------------------------------------------------------------

class EQParseError(Exception):
    """Raised when the EQ file is malformed or uses an unsupported feature."""


def detect_format(data):
    """
    Inspect the magic bytes to determine PJ6 vs PJ8.
    Returns ('pj6', header_size) or ('pj8', header_size).
    """
    if len(data) < 16:
        raise EQParseError("File too small to be a valid EQ project.")

    magic = data[0:8]
    if magic.startswith(b"EQ8PJ8"):
        return ("pj8", 0xc0)   # 192-byte header
    if magic.startswith(b"EQ-PJ6") or magic.startswith(b"EQ-PJ7"):
        return ("pj6", 0x90)   # 144-byte header
    raise EQParseError(
        "Unrecognised file format. Expected EQ8PJ8 or EQ-PJ6 magic bytes; "
        "got {!r}.".format(magic)
    )


def find_block_records(data, fmt, header_size):
    """
    Walk the file looking for BLOK markers and decode each block record's
    config region into a structured dict.

    Returns a list of dicts, one per block, with keys:
      - 'index'         : 1-based position in the file
      - 'config_start'  : byte offset of the 56-byte config region
      - 'blok_offset'   : byte offset of the BLOK marker
      - 'block_w_in'    : finished block width in inches
      - 'block_h_in'    : finished block height in inches
      - 'line_count'    : number of interior lines
      - 'patch_count'   : number of patches
      - 'is_empty'      : True if this is an EQ "blank" block
      - 'name'          : best-effort decoded block name (may be empty)
    """
    blocks = []
    pos = 0
    while True:
        blok_pos = data.find(b"BLOK", pos)
        if blok_pos < 0:
            break

        # Sanity: the BLOK marker should be preceded by a 56-byte config region.
        config_start = blok_pos - 56
        if config_start < header_size:
            # Stray "BLOK" too close to file header — skip it.
            pos = blok_pos + 4
            continue

        try:
            block = _decode_block_config(data, config_start, blok_pos, fmt)
            block["index"] = len(blocks) + 1
            blocks.append(block)
        except (struct.error, EQParseError):
            # Couldn't decode this region as a block — false-positive BLOK match.
            pass

        pos = blok_pos + 4

    # Attempt to extract block names by scanning each record's tail bytes.
    _extract_block_names(data, blocks)

    return blocks


def _decode_block_config(data, config_start, blok_pos, fmt):
    """Decode the 56-byte config region preceding a BLOK marker.

    Layout (offsets relative to config_start, verified against real EQ8
    projects and Quilt Tools EQ exports):
      +0x00  uint32 record length
      +0x04  4 flag bytes. The byte at +0x07 is 0x7f for the EQ built-in
             default blocks (baked into every project), 0x01 for blocks the
             user added to the sketchbook, 0x80 in legacy QA-style exports.
      +0x08  type byte: 0x41 drawn block, 0x42 stencil, 0x43 legacy block
      +0x10  line_count uint16
      +0x16  patch_count uint16
      +0x1c  block width  (float32 hundredths-of-inch in PJ8, uint32 in PJ6)
      +0x20  block height (same encoding)
      +0x24  legacy patch_count uint32 (0 in real EQ8 files)
    """
    flag_byte = data[config_start + 7]
    type_byte = data[config_start + 8]
    if type_byte not in (0x41, 0x42, 0x43):
        raise EQParseError("Unknown block type byte")

    line_count  = struct.unpack("<H", data[config_start + 0x10:config_start + 0x12])[0]
    patch_uint16 = struct.unpack("<H", data[config_start + 0x16:config_start + 0x18])[0]
    patch_uint32 = struct.unpack("<I", data[config_start + 0x24:config_start + 0x28])[0]
    if patch_uint32 > 10000:
        patch_uint32 = 0   # garbage in that slot — real EQ8 leaves it 0
    patch_count = max(patch_uint16, patch_uint32)

    if line_count > 10000 or patch_count > 10000:
        raise EQParseError("Implausible line/patch counts")

    if fmt == "pj8":
        block_w_hu = struct.unpack("<f", data[config_start + 0x1c:config_start + 0x20])[0]
        block_h_hu = struct.unpack("<f", data[config_start + 0x20:config_start + 0x24])[0]
    else:
        block_w_hu = struct.unpack("<I", data[config_start + 0x1c:config_start + 0x20])[0]
        block_h_hu = struct.unpack("<I", data[config_start + 0x20:config_start + 0x24])[0]

    # Defensive: clamp to reasonable bounds. EQ blocks should be 0.5"-120".
    block_w_in = block_w_hu / HUNDREDTHS
    block_h_in = block_h_hu / HUNDREDTHS
    if not (0.1 <= block_w_in <= 240 and 0.1 <= block_h_in <= 240):
        raise EQParseError("Dimensions out of plausible range")

    return {
        "config_start": config_start,
        "blok_offset":  blok_pos,
        "block_w_in":   block_w_in,
        "block_h_in":   block_h_in,
        "line_count":   line_count,
        "patch_count":  patch_count,
        "is_empty":     patch_count <= 1,
        "is_builtin":   flag_byte == 0x7f,
        "is_stencil":   type_byte == 0x42,
        "name":         "",   # Filled in by _extract_block_names
    }


def _extract_block_names(data, blocks):
    """
    Look for UTF-16LE block names in each block's tail region.
    Names appear after the sentinel + padding zeros. We probe each block's
    territory looking for a plausible UTF-16LE string.
    """
    for i, block in enumerate(blocks):
        # Search range: from BLOK marker to start of next block (or end of file).
        start = block["blok_offset"]
        end = blocks[i + 1]["config_start"] if i + 1 < len(blocks) else len(data)

        block["name"] = _find_first_utf16_string(data[start:end])


def _find_first_utf16_string(buf, min_len=2, max_len=64):
    """
    Heuristic: find the first run of "ASCII byte, 0x00" pairs that looks like
    a printable UTF-16LE string. Returns the decoded string, or "" if none.
    """
    i = 0
    while i < len(buf) - 4:
        # Look for printable ASCII followed by 0x00
        if (32 <= buf[i] < 127) and buf[i + 1] == 0x00:
            # Try to read a run
            j = i
            chars = []
            while j < len(buf) - 1 and (32 <= buf[j] < 127) and buf[j + 1] == 0x00:
                chars.append(chr(buf[j]))
                j += 2
                if len(chars) >= max_len:
                    break
            if len(chars) >= min_len:
                text = "".join(chars).strip()
                # Filter out generated boilerplate
                if text and "Generated by" not in text and "QuiltAssistant" not in text:
                    return text
            i = j + 1
        else:
            i += 1
    return ""


def decode_block_geometry(data, block, fmt):
    """
    Read the line table and patch list for a single block.
    Returns dict with 'lines' (list of (x1,y1,x2,y2) in 0..20160 raw coords)
    and 'patches' (list of polygons, each a list of (x,y) raw coords).
    Both are in EQ raw integer coordinates.
    """
    line_count  = block["line_count"]
    patch_count = block["patch_count"]

    # Line table starts at BLOK + 8 (after BLOK marker + 4 zero bytes)
    line_table_start = block["blok_offset"] + 8
    line_table_end   = line_table_start + line_count * 8

    if line_table_end > len(data):
        raise EQParseError(
            "Line table extends past end of file (block {}).".format(block["index"]))

    # Decode lines
    lines = []
    for i in range(line_count):
        offset = line_table_start + i * 8
        x1, y1, x2, y2 = struct.unpack("<4H", data[offset:offset + 8])
        lines.append((x1, y1, x2, y2))

    # Patch extra: starts after line table
    patches = _decode_patch_extra(
        data, line_table_end, patch_count, block["index"]
    )

    return {"lines": lines, "patches": patches}


def _decode_patch_extra(data, start, patch_count, block_index):
    """
    Parse the patch section that follows the line table. Two layouts exist:

    A) Real EQ8 projects and current Quilt Tools EQ exports: the patch
       records start immediately —
         for each patch:
             uint16(1) uint16(vcount)
             vcount * (uint16 x, uint16 y)

    B) Legacy QA-style exports prefix the records with a header and a
       meta index list —
         uint16(0) uint16(1)                        <- header
         uint16(i) for i in range(2, patch_count)   <- meta index list
         ...then the same per-patch records as layout A.

    The header pair (0, 1) can never be a valid record marker (which is
    always 1 followed by a 3..200 vertex count), so the layout is sniffed
    from the first two uint16s.
    """
    pos = start
    patches = []

    if patch_count < 1 or pos + 4 > len(data):
        return patches

    a, b = struct.unpack("<HH", data[pos:pos + 4])
    if (a, b) == (0, 1) and patch_count >= 2:
        # Layout B: skip header + meta index list
        pos += 4 + 2 * max(0, patch_count - 2)

    for p in range(patch_count):
        if pos + 4 > len(data):
            break
        marker, vcount = struct.unpack("<HH", data[pos:pos + 4])
        if marker != 1 or vcount < 3 or vcount > 200:
            # End of patch records (padding/sentinel reached)
            break
        pos += 4
        verts = []
        ok = True
        for _ in range(vcount):
            if pos + 4 > len(data):
                ok = False
                break
            x, y = struct.unpack("<2H", data[pos:pos + 4])
            verts.append((x, y))
            pos += 4
        if ok:
            patches.append(verts)
        else:
            break

    return patches


# ----------------------------------------------------------------------------
# SVG generation
# ----------------------------------------------------------------------------

def make_layer(layer_id, layer_label, transform=None):
    """Build an empty Inkscape layer group."""
    g = etree.Element(
        "{%s}g" % SVG_NS,
        id=layer_id,
    )
    g.set("{%s}label" % INKSCAPE_NS, layer_label)
    g.set("{%s}groupmode" % INKSCAPE_NS, "layer")
    if transform:
        g.set("transform", transform)
    return g


def make_block_outline(block_w_px, block_h_px, line_colour):
    """A solid rectangle showing the block boundary."""
    rect = etree.Element(
        "{%s}rect" % SVG_NS,
        x="0",
        y="0",
        width="{:.4f}".format(block_w_px),
        height="{:.4f}".format(block_h_px),
    )
    rect.set("style",
        "fill:none;stroke:{};stroke-width:1.5;opacity:0.9;"
        "vector-effect:non-scaling-stroke;pointer-events:none;".format(line_colour))
    rect.set("data-fpp-ignore", "true")
    return rect


def make_cut_line(p1_px, p2_px, line_colour):
    """A dashed line representing one EQ interior cut."""
    el = etree.Element(
        "{%s}line" % SVG_NS,
        x1="{:.4f}".format(p1_px[0]),
        y1="{:.4f}".format(p1_px[1]),
        x2="{:.4f}".format(p2_px[0]),
        y2="{:.4f}".format(p2_px[1]),
    )
    el.set("style",
        "fill:none;stroke:{};stroke-width:1.2;stroke-dasharray:5,3;"
        "opacity:0.85;vector-effect:non-scaling-stroke;"
        "pointer-events:none;".format(line_colour))
    el.set("data-fpp-ignore", "true")
    return el


def make_patch_fill(polygon_px, line_colour):
    """A translucent fill showing one patch polygon."""
    if len(polygon_px) < 3:
        return None
    d = "M {:.4f},{:.4f}".format(*polygon_px[0])
    for pt in polygon_px[1:]:
        d += " L {:.4f},{:.4f}".format(*pt)
    d += " Z"
    el = etree.Element("{%s}path" % SVG_NS, d=d)
    el.set("style",
        "fill:{};fill-opacity:0.12;stroke:none;"
        "pointer-events:none;".format(line_colour))
    el.set("data-fpp-ignore", "true")
    return el


def raw_to_px(raw, block_size_px):
    """Convert an EQ 0..20160 raw coordinate to SVG pixels."""
    return raw / EQ_MAX_COORD * block_size_px


# ----------------------------------------------------------------------------
# Inkscape extension entry point
# ----------------------------------------------------------------------------

class EQImportPlugin(inkex.Effect):

    def add_arguments(self, pars):
        pars.add_argument("--action",       type=str, default="scan")
        pars.add_argument("--source_file",  type=str, default="")
        pars.add_argument("--import_all",   type=inkex.Boolean, default=True)
        pars.add_argument("--block_indexes", type=str, default="")
        pars.add_argument("--draw_mode",    type=str, default="lines_and_patches")
        pars.add_argument("--line_colour",  type=str, default="blue")
        pars.add_argument("--placement",    type=str, default="stack")
        pars.add_argument("--library_subfolder", type=str, default="EQ Imports")
        pars.add_argument("--library_overwrite", type=inkex.Boolean, default=False)

    # --------------------------------------------------------------------
    # Main entry
    # --------------------------------------------------------------------

    def effect(self):
        path = self.options.source_file.strip()
        if not path:
            return inkex.errormsg(
                "No file selected.\n\n"
                "Please pick a .pj8 or .pj6 file in the dialog.")

        if not os.path.isfile(path):
            return inkex.errormsg(
                "File not found:\n  {}\n\n"
                "Check the path and try again.".format(path))

        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception as e:
            return inkex.errormsg("Could not read file:\n  {}\n{}".format(path, e))

        try:
            fmt, header_size = detect_format(data)
        except EQParseError as e:
            return inkex.errormsg(str(e))

        try:
            blocks = find_block_records(data, fmt, header_size)
        except EQParseError as e:
            return inkex.errormsg("Failed to parse file:\n{}".format(e))

        if not blocks:
            return inkex.errormsg(
                "No blocks found in this file.\n\n"
                "The file may be malformed, or may contain only project "
                "data without any block records.")

        if self.options.action == "scan":
            self._scan_and_report(blocks, fmt, path)
        elif self.options.action == "import_library":
            self._import_to_library(data, fmt, blocks, path)
        else:
            self._import_blocks(data, fmt, blocks)

    # --------------------------------------------------------------------
    # Scan mode
    # --------------------------------------------------------------------

    def _scan_and_report(self, blocks, fmt, path):
        """Print a list of blocks with their indexes, names, and dimensions."""
        lines = []
        lines.append("Scanned: {}".format(os.path.basename(path)))
        lines.append("Format: {}".format(fmt.upper()))
        lines.append("Found {} block(s):".format(len(blocks)))
        lines.append("")
        for b in blocks:
            if b["is_stencil"]:
                kind = "STENCIL"
            elif b["is_builtin"]:
                kind = "EQ default"
            elif b["is_empty"]:
                kind = "EMPTY"
            else:
                kind = "user block"
            name = b["name"] if b["name"] else "(unnamed)"
            lines.append(
                "  {idx:>3}. {name:<40} {w:>5.2f}\" x {h:>5.2f}\"  "
                "lines={ln}, patches={pn} ({kind})".format(
                    idx=b["index"],
                    name=name[:40],
                    w=b["block_w_in"],
                    h=b["block_h_in"],
                    ln=b["line_count"],
                    pn=b["patch_count"],
                    kind=kind,
                ))
        lines.append("")
        lines.append("'EQ default' records are the sample blocks EQ8 bakes into every")
        lines.append("project; 'Import all' skips them (and stencils). To import one")
        lines.append("anyway, enter its index explicitly.")
        lines.append("")
        lines.append("To import: re-run the extension, choose an import action, and")
        lines.append("enter the indexes you want (or check 'Import all blocks').")

        inkex.utils.debug("\n".join(lines))

    # --------------------------------------------------------------------
    # Import mode
    # --------------------------------------------------------------------

    def _select_blocks(self, blocks):
        """Resolve which blocks to import. 'Import all' means all *user*
        blocks — the EQ default samples baked into every project and any
        stencils are skipped unless explicitly requested by index."""
        if not self.options.import_all:
            return self._parse_block_selection(blocks)
        selected = [b for b in blocks if not (b["is_builtin"] or b["is_stencil"])]
        if not selected:
            inkex.errormsg(
                "No user blocks found in this file — only EQ default sample "
                "blocks and stencils.\n\nRun 'Scan' to list every record; you "
                "can import EQ defaults by entering their indexes explicitly.")
        return selected

    def _import_blocks(self, data, fmt, blocks):
        # Resolve which blocks to import
        selected = self._select_blocks(blocks)
        if not selected:
            return  # message already shown

        line_colour = LINE_COLOURS.get(
            self.options.line_colour.lower(), LINE_COLOURS["blue"])
        draw_patches = (self.options.draw_mode == "lines_and_patches")
        placement    = self.options.placement

        # Where to insert layers
        root = self.svg.getroot() if hasattr(self.svg, "getroot") else self.svg
        # Inkscape Effect.svg already exposes the root in modern inkex; use directly.
        svg_root = self.svg

        imported = 0
        skipped  = 0
        errors   = []

        # Figure out a starting x-offset for grid placement
        grid_cursor_x = 0.0
        grid_padding_px = 20.0   # ~0.2 inches of space between blocks

        for b in selected:
            try:
                geom = decode_block_geometry(data, b, fmt)
            except EQParseError as e:
                errors.append("Block {}: {}".format(b["index"], e))
                skipped += 1
                continue

            layer = self._build_block_layer(
                b, geom, line_colour, draw_patches
            )

            # Position the layer
            if placement == "grid":
                tx = grid_cursor_x
                layer.set("transform", "translate({:.4f},0)".format(tx))
                grid_cursor_x += b["block_w_in"] * PX_PER_INCH + grid_padding_px

            svg_root.append(layer)
            imported += 1

        # Summary
        summary = [
            "Import complete.",
            "",
            "  Blocks imported: {}".format(imported),
        ]
        if skipped:
            summary.append("  Blocks skipped:  {}".format(skipped))
            summary.append("")
            for err in errors:
                summary.append("  ! " + err)
        summary.extend([
            "",
            "Each imported block is a separate layer named",
            "'EQ Import: <block name>'. Toggle visibility in the",
            "Layers panel to focus on one block at a time.",
        ])
        inkex.utils.debug("\n".join(summary))

    def _parse_block_selection(self, blocks):
        """Parse the comma-separated indexes field. Returns list of blocks."""
        raw = self.options.block_indexes.strip()
        if not raw:
            inkex.errormsg(
                "No block indexes specified.\n\n"
                "Either check 'Import all blocks' or enter a comma-separated\n"
                "list of indexes like:  1,3,7")
            return []

        try:
            indexes = []
            for token in raw.split(","):
                token = token.strip()
                if not token:
                    continue
                indexes.append(int(token))
        except ValueError:
            inkex.errormsg(
                "Couldn't parse block indexes.\n"
                "Use a comma-separated list of whole numbers, e.g. 1,3,7\n"
                "Got: {}".format(raw))
            return []

        by_index = {b["index"]: b for b in blocks}
        out = []
        for idx in indexes:
            if idx in by_index:
                out.append(by_index[idx])
            else:
                inkex.utils.debug(
                    "Warning: block index {} doesn't exist in this file; skipping.".format(idx))
        return out

    # --------------------------------------------------------------------
    # Block Library import mode (requires the Quilt Tools FPP suite)
    # --------------------------------------------------------------------

    @staticmethod
    def _safe_filename(name):
        name = (name or "").strip()
        keep = [ch if (ch.isalnum() or ch in (" ", "-", "_")) else "_" for ch in name]
        cleaned = "".join(keep).strip().strip(".")
        return cleaned or "Untitled Block"

    def _import_to_library(self, data, fmt, blocks, source_path):
        """Convert selected EQ blocks into fully compatible Quilt Tools block
        SVGs (auto-labelled FPP region tree + metadata) inside BlockLibrary."""
        try:
            import quilttools_fpp_core as core
        except ImportError:
            return inkex.errormsg(
                "Importing into the Block Library requires the Quilt Tools FPP "
                "suite (quilttools_fpp_core.py) in the same extensions folder.\n"
                "Use 'Import blocks as guide layers' for stand-alone use.")

        selected = self._select_blocks(blocks)
        if not selected:
            return

        lib_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "BlockLibrary")
        sub = self._safe_filename(self.options.library_subfolder) \
            if self.options.library_subfolder.strip() else ""
        out_dir = os.path.join(lib_dir, sub) if sub else lib_dir
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            return inkex.errormsg(
                "Could not create library folder:\n  {}\n{}".format(out_dir, e))

        imported, skipped = 0, 0
        report = []
        used_names = set()

        for b in selected:
            try:
                geom = decode_block_geometry(data, b, fmt)
            except EQParseError as e:
                report.append("  ! Block {}: {}".format(b["index"], e))
                skipped += 1
                continue

            w_px = b["block_w_in"] * PX_PER_INCH
            h_px = b["block_h_in"] * PX_PER_INCH

            # EQ patches (finished pieces) -> cleaned px polygons
            polys = []
            for patch in geom["patches"]:
                pts = [(raw_to_px(x, w_px), raw_to_px(y, h_px)) for x, y in patch]
                pts = core.simplify_polygon(pts)
                # Drop degenerate slivers (under ~0.02 inch square)
                if len(pts) >= 3 and core.polygon_area(pts) > 4.0:
                    polys.append(pts)

            box = [(0.0, 0.0), (w_px, 0.0), (w_px, h_px), (0.0, h_px)]
            tree = core.RegionTree(root_polygon=box)
            label_note = ""
            if polys:
                # Natural sew order: top-to-bottom, then left-to-right (same
                # convention the crop/rebuild path uses).
                polys.sort(key=lambda p: (
                    core.polygon_centroid(p)[1], core.polygon_centroid(p)[0]))
                tree._rebuild_from_pieces(polys, box)
                try:
                    tree.auto_partition_and_label()
                except Exception as e:
                    label_note = "  (auto-labelling failed: {}; default labels kept)".format(e)
                    tree.rebuild_alphabet()
            # An EQ "empty" block with no usable patches stays a single A1 region.

            name = b["name"] or "EQ Block {}".format(b["index"])
            base, k = name, 2
            while name.lower() in used_names:
                name = "{} ({})".format(base, k)
                k += 1
            used_names.add(name.lower())

            block_data = core.BlockData(tree)
            block_data.prefs["description"] = "Imported from {} (block {})".format(
                os.path.basename(source_path), b["index"])
            block_data.prefs["tags"] = ["eq-import"]

            core.normalize_block_to_origin(block_data)
            svg_root = core.block_data_to_standalone_svg(block_data, name=name)

            out_path = os.path.join(out_dir, self._safe_filename(name) + ".svg")
            if os.path.isfile(out_path) and not self.options.library_overwrite:
                report.append(
                    "  ! Skipped '{}': a block with this name already exists. "
                    "Tick 'Overwrite' to replace it.".format(name))
                skipped += 1
                continue

            try:
                etree.ElementTree(svg_root).write(
                    out_path, pretty_print=True,
                    xml_declaration=True, encoding="UTF-8")
            except Exception as e:
                report.append("  ! Block {} ('{}'): could not write file: {}".format(
                    b["index"], name, e))
                skipped += 1
                continue

            n_pieces = len(tree.leaf_regions())
            report.append('  {}  ({:.2f}" x {:.2f}", {} pieces){}'.format(
                name, b["block_w_in"], b["block_h_in"], n_pieces, label_note))
            imported += 1

        summary = [
            "Block Library import complete.",
            "",
            "  Saved to: {}".format(out_dir),
            "  Blocks imported: {}".format(imported),
        ]
        if skipped:
            summary.append("  Blocks skipped:  {}".format(skipped))
        summary.append("")
        summary.extend(report)
        summary.extend([
            "",
            "The blocks are fully compatible Quilt Tools blocks: they appear",
            "in the Block Library picker/visual catalogue and can be used with",
            "Fill Blocks, Import Into Region, and the FPP export.",
        ])
        inkex.utils.debug("\n".join(summary))

    def _build_block_layer(self, block, geom, line_colour, draw_patches):
        """Build the Inkscape layer for one block."""
        name = block["name"] if block["name"] else "Block {}".format(block["index"])
        layer_label = "EQ Import: {}".format(name)
        layer_id    = "eq-import-{:03d}".format(block["index"])

        layer = make_layer(layer_id, layer_label)

        block_w_px = block["block_w_in"] * PX_PER_INCH
        block_h_px = block["block_h_in"] * PX_PER_INCH

        # 1. Patch fills (drawn FIRST so they sit underneath lines)
        if draw_patches:
            for patch in geom["patches"]:
                poly_px = [
                    (raw_to_px(x, block_w_px), raw_to_px(y, block_h_px))
                    for x, y in patch
                ]
                el = make_patch_fill(poly_px, line_colour)
                if el is not None:
                    layer.append(el)

        # 2. Block outline
        layer.append(make_block_outline(block_w_px, block_h_px, line_colour))

        # 3. Cut lines on top
        for x1, y1, x2, y2 in geom["lines"]:
            p1 = (raw_to_px(x1, block_w_px), raw_to_px(y1, block_h_px))
            p2 = (raw_to_px(x2, block_w_px), raw_to_px(y2, block_h_px))
            layer.append(make_cut_line(p1, p2, line_colour))

        return layer


if __name__ == "__main__":
    EQImportPlugin().run()
