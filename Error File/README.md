# Quilt Tools FPP

**Foundation Paper Piecing pattern design, inside Inkscape.**

Quilt Tools FPP is a suite of free, open-source Inkscape extensions for
designing Foundation Paper Piecing (FPP) quilt blocks. Draw a block, cut it
into pieces with guillotine cuts, label the sewing order, add seam
allowances, and export — to printable templates or straight into
Electric Quilt 8.

Built on guillotine cutting principles: every cut fully divides a section,
which guarantees your block can be sewn without Y-seams.

> Current release: **v1.2.0** · Licence: **GPLv3** · Requires: **Inkscape 1.3+**

---

## Why this exists

FPP designers have been stuck choosing between expensive proprietary
software, discontinued freeware, or drawing patterns by hand. Inkscape is a
world-class free vector editor — Quilt Tools FPP turns it into a purpose-built
FPP design studio while keeping every file as an ordinary SVG you own.

---

## The tools

All tools live under **Extensions → Quilt Tools** once installed.

### 1. New Block
Creates a fresh FPP block at any size, optionally pre-sectioned with a
rows × columns grid (grid lines are recorded as *boundary* cuts — the
foundation for section-based construction and multi-block export). Can also
scale a selected image or object to the block area as a tracing reference.

### 2. Guillotine Cut
The core design action. Draw a straight line across a piece, run the tool,
and the piece is split in two. Supports angle snapping, cutting several
drawn lines in one pass, undo, and a minimum-piece-size warning so you don't
design pieces too fiddly to sew.

### ⚡ Quick Cut (bind to a key)
A dialog-free variant of Guillotine Cut for a fast draw–press–cut rhythm:

1. Draw a straight line with the Pencil tool (**P**)
2. Press your chosen shortcut key
3. The line is consumed and the cut happens instantly — no dialog

**Setting up the shortcut (once):**
Edit → Preferences → Interface → Keyboard, search for *Quick Cut*, click in
the Shortcut column and press your preferred key combination (e.g.
`Ctrl+Shift+X`). Draw as many lines as you like — one keypress cuts them all.

Quick Cut uses the standard defaults (auto-detect the last drawn line,
15° angle snap). To change them, edit the values in
`quilttools_fpp_quick_cut.inx` — the file is commented.

### 3. Labels & Sections
Auto-labels every piece with its section letter and sewing order (A1, A2,
B1…), validated by a virtual sewing engine that guarantees the sequence can
be assembled without Y-seams. Manual controls let you define your own
sections, set the first piece of a section, or relabel individual pieces.

### 4. Display & Seam Allowance
Controls how the block renders: colour modes (per-piece palette, per-section,
photo-average sampling from a traced image), custom colour memory, and
¼″ (configurable) seam-allowance display.

### 5. Heal & Guides
Merge pieces back together (with sewability validation), convert a finished
block to a tracing guide layer, or clear the workspace of guides and grids.

### 6. Resize Block
Rescales the whole block — geometry and page — to new finished dimensions.

### 7. Block Library
Load ready-made guillotine-safe starter blocks (Four Patch, Nine Patch,
Half Square Triangle, Hourglass, Square in a Square, Flying Geese, Churn
Dash, Little House, and more) from the bundled `BlockLibrary/` folder as a
starting point for your own designs.

### 8. Export to Electric Quilt
Exports the current block as a native EQ8 project file (`.pj6` / `.pj8`).
Block size is auto-detected from your geometry; the file opens directly in
Electric Quilt 8 with every patch intact. The EQ EasyDraw binary format was
reverse-engineered for this project — as far as we know this is the only
open-source implementation.

---

## Installation

1. Download the latest release ZIP from the
   [Releases page](https://github.com/quilttoolsfpp/quilttools/releases).
2. Extract **all** `.py` and `.inx` files into your Inkscape user extensions
   folder:
   - **Windows:** `%APPDATA%\inkscape\extensions\`
   - **macOS:** `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/`
   - **Linux:** `~/.config/inkscape/extensions/`
   (Find yours in Edit → Preferences → System → *User extensions*.)
3. Copy the `BlockLibrary/` folder to the same location.
4. Restart Inkscape. The tools appear under **Extensions → Quilt Tools**.

`quilttools_fpp_core.py` and `quilttools_fpp_fabric.py` are shared libraries
used by the other tools — they must be present but have no menu entry of
their own.

---

## A typical workflow

1. **New Block** — 6″ × 6″, or larger with an initial grid for a multi-section
   design.
2. Draw a cutting line with the Pencil tool, then **Quick Cut** (or the full
   Guillotine Cut dialog). Repeat until the design is complete.
3. **Heal** anything you want to merge back; pieces are re-validated.
4. **Labels & Sections → Auto Label** for a guaranteed-sewable order.
5. **Display & SA** — colour the design and preview seam allowances.
6. **Export** — printable templates, or an EQ8 project file.

---

## Design philosophy

- **Guillotine-only cutting.** If the tool lets you draw it, you can sew it.
- **Validate before labelling.** Sewing order is computed, not guessed.
- **Non-destructive.** The full cut history lives inside the SVG; undo and
  heal are always available.
- **Plain SVG files.** No proprietary format. Your patterns are yours.

---

## Known issues

- The Heal tool can occasionally leave orphaned entries in the internal cut
  tree on complex blocks. Exports remain geometrically correct (the EQ
  exporter reconstructs lines from geometry, not the tree), but a repair
  pass is on the roadmap.
- EQ export supports straight-line (EasyDraw) blocks only; curved blocks
  are a future project.

## Roadmap

- Multi-block EQ export (grid-sectioned designs as `Name-row-col` sub-blocks)
- Colour/fabric export to EQ8
- Curved FPP support
- Sewing-order instruction generator and fabric estimation

---

## Credits

- **Arnout Cosman** — author of Quilt Assistant, whose work defined what
  free FPP software could be and inspired this project.
- Built with the assistance of AI pair-programming tools.

## Licence

GPLv3 — free to use, study, share, and improve. See [LICENSE](LICENSE).
