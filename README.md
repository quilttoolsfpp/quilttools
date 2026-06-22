# ✂️ Quilt Tools for Inkscape

![Inkscape Compatibility](https://img.shields.io/badge/Inkscape-1.3%2B-blue)
![License](https://img.shields.io/badge/License-GPLv3-green) 
![Version](https://img.shields.io/badge/Version-1.0.0-orange)

**Quilt Tools** is a commercial-grade CAD-to-CAM pipeline built directly into Inkscape. It allows quilt pattern designers to transform complex vector artwork into mathematically perfect, ready-to-print Foundation Paper Piecing (FPP) templates.

Instead of manually offsetting seam allowances, guessing sewing orders, and fighting with page boundaries, Quilt Tools treats your artwork as a "Live Object Model." It understands the physical properties of fabric, paper, and the geometric laws of the sewing machine.

---

## ✨ Core Features

*   **Top-Down Auto-Labelling:** Uses a recursive binary tree to mathematically reverse-engineer your block, guaranteeing a perfectly sewable A1, A2, A3 sequence.
*   **The Guillotine Law Engine:** Validates every cut using edge-to-edge ray-casting. It actively prevents "locked loops" and purges micro-slivers, ensuring no impossible Y-seams make it to your printer.
*   **Smart Heal & Culling:** Accidentally split a piece? The Smart Heal tool dissolves the internal Y-seam, collapsing dead branches in the topological tree to restore a clean, sewable polygon.
*   **Miter-Limited Seam Allowances:** Automatically generates physical overlap boundaries (default 0.25") with mathematically clamped "dog-ears" to prevent sharp star points from creating infinite miter spikes.
*   **Dynamic Gluestick Tiling:** Automatically slices oversized sections across page boundaries, generating precisely mated "Glue Tabs" and "Align Tabs" matched to the exact angle of the cut line.

---

## 🛠️ Installation

1. Download the latest release from the [Releases page](../../releases).
2. Extract the `.zip` file. You should have 15 files: this is pairs `quilttools_fpp_xxx.inx` and `quilttools_fpp_xxx.py` (along with the core `.py` engine).
3. Open Inkscape and go to **Edit > Preferences > System**.
4. Find the **User extensions** folder path.
5. Copy the extracted files directly into that folder.
6. Restart Inkscape. You will now find the suite under **Extensions > Quilt Tools**.

---

## 🚀 The Export Workflow

Quilt Tools features two distinct export strategies depending on your needs.

### Strategy A: Smart Pack (Fully Automated)
Best for standard blocks and quick testing.
1. Go to **Extensions > Quilt Tools > 6. Export & Layout**.
2. Select **Step 1: Generate Layout** and choose **Smart Pack**.
3. The engine will extract your pieces, auto-rotate them to minimize paper waste, bin-pack them onto your chosen page size, and automatically slice/tab any pieces that are too large.
4. Save as PDF.

### Strategy B: Open Canvas (WYSIWYG Manual Layout)
Best for commercial pattern designers who want absolute control over where pieces sit on the printed page.

**Phase 1: The Canvas**
1. Select **Step 1: Generate Layout** and choose **Open Canvas**.
2. The plugin will generate a contiguous grid of blue dashed boxes representing your physical pages.
3. Freely drag, drop, and rotate your pattern pieces across the grid. Put them exactly where you want them. 

**Phase 2: The Slicer**
4. Once arranged, go back to the menu and select **Step 2: Finalize Open Canvas**.
5. The engine will calculate the exact transformation matrix of every piece. If you dragged a piece across a blue dashed page line, it will mathematically slice the geometry, drop the pieces onto their respective PDF pages, and generate custom "Glue/Align" tabs perfectly sized to the cut.

---

## 🧠 Under the Hood (For Developers)

Quilt Tools relies heavily on an immutable JSON "brain" injected into the SVG's `<desc>` tag. 
*   **Immutable Geometry Pipeline:** During export, the master JSON tree is strictly read-only. We clone and manipulate coordinate dictionaries to prevent render-time rotation desyncs.
*   **Matrix Math:** Uses modern Inkscape 1.x `inkex.Transform` API with `@` matrix multiplication to ensure WYSIWYG placement perfectly translates from Open Canvas to the final clipping masks.
*   **Topological Sanitization:** The core engine runs aggressive collinear simplification passes to scrub redundant vertices, preventing "phantom duplicates" during polygon union operations.

---
# Quilt Tools FPP — Changelog

All notable changes to the Quilt Tools FPP suite for Inkscape. Newest releases
are listed first.

---

## Changes in v1.2

### 🧩 Block Library (new module — *7. Block Library*)

* **Shared on-disk library:** Added a brand-new module that stores blocks as self-contained SVG files in a `BlockLibrary` folder sitting directly beside the Quilt Tools extension scripts. Blocks shipped with the suite and blocks you save both live there, so the same library is available to every user from a fresh install.
* **Load / Replace block:** Replace the block in your current document with one from the library — either by typing its name or by browsing straight to an SVG file. The loaded block is rebuilt at the page origin with full fidelity (every seam, label, and section is preserved), and the page can optionally resize itself to match.
* **Save current block to library:** Saves your active block into the library, normalised to the origin and with its complete region tree embedded in the file. Supports `Category/Name` to file blocks into subfolders, and warns before overwriting an existing block unless you explicitly opt in.
* **List library blocks:** Prints every block currently in the library (including subfolders) plus the exact folder path, so the catalogue stays discoverable even though Inkscape menus can't list files dynamically.
* **Import external SVG as tracing background:** For plain or third-party FPP SVGs that aren't Quilt Tools blocks, this brings the artwork in as a locked, scaled background layer ready to be traced with *New Block* + *Guillotine Cut*.
* **Round-trip-safe block format:** Library blocks are ordinary SVGs that carry their own block data in a `<desc>` element — they open and preview normally in Inkscape, yet reload into the system with zero loss. This also lays the groundwork for the upcoming multi-block "blocks onto a page" layout workflow.
* **Five starter blocks included:** Four Patch, Nine Patch, Half Square Triangle, Flying Geese, and Square in a Square ship in the library so the feature is usable the moment you install.

### 🪡 Electric Quilt Export (new module — *9. EQ Export*)

* **Export to EQ6 / EQ8:** Added a module that exports the current FPP block as an Electric Quilt EasyDraw project file that opens directly in EQ6 or EQ8. After opening in EQ8 the block appears under *Libraries → Block Library → Sketchbook*, where you can recolour it, resize it, and drop it into any quilt layout.
* **Native binary format, reverse-engineered:** The `.pj6` / `.pj8` format was reverse-engineered from genuine Quilt Assistant output and validated byte-for-byte against real EQ files, so blocks land in EQ with correct geometry rather than as a lossy trace.
* **Two output formats:** Choose **PJ6** (EQ6 format, recommended — EQ8 opens it natively with identical geometry) or **PJ8** (EQ8's native format).
* **Automatic size detection:** Block size is read straight from your block geometry, with manual width/height fields available only as a fallback if auto-detection can't run.
* **Flexible save location:** Defaults to saving `[block name].pj6` in your Documents folder, but accepts a filename or a full custom path, and reports the exact path it wrote so the file is easy to find.

### ✂️ Resize — Crop to Shape (new action)

* **Crop to Shape:** Added a dedicated *Crop to Shape* action to the *Resize Block* module, fully separate from the existing Resize / Stretch behaviour. Draw a rectangle over your block, select it, and the managed block is reshaped to exactly match that rectangle.
* **Grow for borders (non-destructive):** When the rectangle is larger than the block, your existing pieces and labels are left completely untouched and the surplus margin is filled with clean "spacing" pieces arranged as a picture frame in their own new section — ideal for dialling in border spacing.
* **Crop to trim:** When the rectangle cuts into the block, pieces are clipped to the rectangle, pieces that fall entirely outside are removed, any leftover margin is filled with spacing pieces, and the block is rebuilt and re-labelled.
* **Handles awkward cases:** Asymmetric (off-centre) borders, mixed grow/shrink in one go (e.g. wider but shorter), and corner crops all resolve correctly, with block area conserved exactly.
* **Sensible controls:** Options to set the minimum piece area before a sliver is dropped, to keep or regenerate labels after a crop, and to automatically delete the crop rectangle when finished. The page and view box resize to the crop automatically.

---

## Changes in v1.1

### 🎨 Color & Paint Workflows

* **Canvas Grouping by Color:** Added a preference to group FPP pieces by fabric color. Child paths utilize `fill:inherit` so you can recolor all matching pieces at once in Inkscape simply by selecting the group and clicking a palette color.
* **Selection-Based Color Locking:** During color quantization (fabric minimization), selecting pieces on the canvas will automatically lock their colors, eliminating the need to copy-paste hex codes.
* **Inkscape Palette Export:** Added a command to export the block's current colors as a native Inkscape/GIMP palette (`.gpl`) file. It saves directly to your local palettes folder for easy paint bucket recoloring.
* **SVG Background Color Sampling:** Upgraded the image color sampler to support natively traced vector path groups and linked/embedded external SVGs (including resolving colors inherited from parent XML groups).

### 📄 Exporter & Layout Adjustments

* **Tabbed Export Dialog:** Restructured the vertically long Export & Layout menu into a compact, four-tab interface (Workflow, Document Settings, Template Styling, and Metadata) to comfortably fit all screen sizes.
* **Optional Page 2 Fabric Requirements:** Added a toggle to include or omit the Fabric Requirements page. When enabled, fabric info is moved to Page 2, allowing a much larger, premium cover page block preview (62% page width) on Page 1.
* **Automatic Overlap Resolver:** Finalizing an Open Canvas layout now automatically relocates any overlapping sections to dedicated, centered pages at the back of the PDF while retaining their custom manual rotation.
* **Improved Template Swatches:** Doubled the color-tag swatch sizes to `24x16` pixels and optimized text offsets for better print readability.
* **Validation & UX:** Demoted page boundary warnings from blocking `CRITICAL` errors to `WARNINGS` and added a friendly error dialog reminding you to label your block before exporting.

---

## 🤝 Contributing & Issues
If you encounter a bug—especially a "Phantom Piece" or a Guillotine Cut failure—please open an issue and attach your raw `.svg` file. Because Quilt Tools relies on precise floating-point geometry, the raw file is required to diagnose locked loops or collinear alignment errors.

---

*Designed for Quilters, Powered by Math.*
