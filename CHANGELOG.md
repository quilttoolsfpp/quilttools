# Quilt Tools FPP — Changelog

All notable changes to the Quilt Tools FPP suite for Inkscape. Newest releases
are listed first.

---

## Changes in v1.4 (Auto-Labeller Fragment Merging) - July 2026

### 🪡 Physical Sewability & Healed-Tree Repairs

* **Adjacency in the piece-order validator:** `virtual_sewing_validator` checked only straight-line separability, so it accepted physically impossible orders — e.g. "sewing" the two disconnected legs of a U-shaped section to each other before the bottom strip connected them. Each piece in the sequence must now share a seam of positive length with the unit it is sewn onto, so U/donut sections are correctly rejected while genuinely piecable shapes (a U *plus* its centre piece sewn centre-first) still pass. The auto-labeller inherits this, so it no longer produces U-shaped sections.
* **Orphan leaf adoption:** heal operations could leave a region parentless and unreachable from the tree root, making it invisible to the auto-labeller (never partitioned, merged or relabelled — and its stale label could collide with fresh ones, producing e.g. two different pieces both labelled J1). `auto_partition_and_label` now detects unreachable leaves, chains them back onto the root, and labels them normally.
* Combined result on the reported "Labelling Help" boat block: the illegal U section is gone, the orphaned centre square is adopted, and the labeller now emits the exact G+H+J+K combined section the user expected — 7 clean sections, no duplicate labels, Y-seam-free at both levels.

### 🧵 Honest Y-Seam Lint (Export)

* **Sound-geometry fallback in the assembly checker:** `calculate_section_sewing_order` built each section's outline with `get_polygon_union`, which silently returns partial geometry (or drops the section entirely) when pieces don't share exact edges — so the export lint could print "Valid Y-seam-free assembly sequence found" for layouts it never actually saw, e.g. a frame/ring section around a centre piece (an inset-seam construction). The checker now detects unsound unions and falls back to the section's convex hull — a conservative superset, so it can only produce extra warnings, never false assurance — and the lint additionally names any sections whose geometry could not be fully verified.
* **Template outline hardening:** the exporter's section outline (`sa_poly` in `_get_processed_sections`) used the same union and could silently print a partial template or drop a section; it now uses the same sound-or-hull fallback.
* Added `test_sewing_order.py` (ring-section warning, T-joint soundness, hull-fallback coverage).

### 🏷️ Auto-Label Merge Pass

* **Fragment absorption:** `auto_partition_and_label` now runs a merge pass after its guillotine partitioning. The slicer is greedy (it recurses on the first clean separating line it finds), which could shear off 1-2 piece fragments that sew perfectly well into a neighbouring section — users had to re-join them manually. Sections of up to 2 pieces are now absorbed into an adjacent section whenever the merged piece list still has a valid straight-seam piecing order (`virtual_sewing_validator`) AND the block's section-to-section assembly still solves with no Y-seam warning (`calculate_section_sewing_order`). Both guards must pass; curved selections never merge (the validator cannot genuinely verify them), and merges never cross structural-group boundaries, so deliberate boundary cuts (Four Patch style) and healed-tree boundaries are respected.
* **Sound-geometry guard:** the section-assembly solver relies on `get_polygon_union`, which silently returns partial geometry when a section's pieces don't share exact edges — making its Y-seam verdict meaningless for such sections. The merge pass therefore refuses any merge where a section union does not fully cover its pieces (union area must match the piece-area sum): if the geometry cannot be verified, the merge does not happen. Legitimately single pieces (e.g. framing pieces that must attach after a centre unit is assembled) now stay single.
* Result: on the imported EQ squirrel block the auto-labeller now produces the same 14-section partition an experienced user created manually — identical piece groupings, including the four framing pieces kept as single-piece sections — versus 19 fragmented sections before.

## Changes in v1.4 (EQ8 Import to Block Library) - July 2026

### 🐿️ EQ8 → Block Library

* **New action in Import EQ8 Block:** "Import blocks into the Block Library" converts EQ blocks straight into fully compatible Quilt Tools block SVGs — patch polygons become an FPP region tree (via the same rebuild path as crop), pieces are auto-partitioned and labelled, and the file is written with standard block metadata into `BlockLibrary/<subfolder>` (default "EQ Imports", with overwrite protection). Imported blocks work immediately in the thumbnail picker, visual catalogue, Fill Blocks, Import Into Region, and FPP export.
* **Real EQ8 file support:** The parser previously only understood legacy QA-style exports and found nothing in genuine EQ8 projects. It now decodes real EQ8 `.PJ8` records (flag byte `0x7f` marks the default sample blocks EQ bakes into every project; patch records follow the line table directly, with the legacy header/meta layout auto-detected). Scan mode classifies records as user block / EQ default / stencil, and "Import all" takes only user blocks — defaults and stencils can still be imported by explicit index.
* **Restored missing script:** `eqimport_to_guide.py` was absent from the extension folder (only its `.inx` was present, so the menu entry was broken); restored and extended. The guide-layer import action now also works on real EQ8 projects.
* Quilt (layout) import from EQ projects remains a possible future addition; this release covers blocks.

## Changes in v1.4 (True-Shape Nesting for Smart Pack) - July 2026

### 🧩 NFP Nesting Engine

* **True polygon nesting:** Created `quilttools_nesting.py`, a pure-Python No-Fit-Polygon (NFP) packing engine (Minkowski sums of convex hulls, bottom-left placement, octagon-inflation spacing). Smart Pack in `quilttools_fpp_export.py` now packs the actual seam-allowance shapes instead of bounding boxes, so triangles and wedges nest into each other's empty halves.
* **Rotation optimisation:** Whole sections try 0/90/180/270-degree placements; the chosen rotation is baked into the geometry (about the same centre as `best_angle`, keeping alignment ticks and mirroring consistent) so all text stays horizontal. Split parts also try all four rotations, applied as a group transform.
* **Split parts pack by content:** Each tile of an oversized section is nested by the convex hull of its visible content (sa polygon clipped to the tile cell, plus glue/align tab strips) rather than its full grid rectangle, and blank grid cells (e.g. the empty half of a diagonal section) are skipped entirely.
* **Middle-tile fix:** Sections split 3+ tiles wide/tall now shrink the tile core so middle tiles (which carry 0.5 in overlap padding on both sides) still fit the printable area instead of being forced onto their own page.
* **Big-first ordering:** Pieces are packed largest-first (calibration square pinned to the first page of its size) for tighter layouts.
* **Testing:** Added `test_nesting.py` (independent overlap/clearance verification via SAT + true convex-polygon distance). Example result: Hourglass block at 12 in dropped from 7 pages to 4.

### 🖨️ Template Copies

* **Multiple template sets:** New "Template Copies" option (Templates & Block Sizing tab, Step 2 Smart Pack only) exports up to 50 sets of templates per size in one document — e.g. two sets for a two-block project, or many sets for a full quilt pattern. All copies are nested together by the packing engine so identical pieces interlock across sets; section labels gain a "(Copy n)" suffix and glue-tab numbering stays unique across copies.
* **Fabric page note:** When copies > 1 the Fabric Requirements page states that quantities are per single block.
* **Scalability:** The nesting engine skips pages whose free area cannot hold the next piece and caps candidate generation on crowded pages, keeping large multi-copy exports fast (20 sets pack in under a second).

## Changes in v1.3 (Phase D: Placement Engine Extraction & Block Filling) - July 2026

### 📦 Placement Engine & Block Filling (Phase D)

* **Shared Placement Engine:** Extracted `quilttools_placement.py` as a central service to compute coordinate transforms, longest edge angles, and generate affine SVG transform matrices (`matrix()`) using a robust 3-point projection algorithm.
* **04. Fill Blocks from Library:** Created `quilttools_fill_blocks.inx` / `.py` to select layout cells and fill them with blocks from the BlockLibrary, automatically scaling, flipping, rotating, and mapping metadata.
* **Refactoring:** Refactored `import_block_into_region` inside `quilttools_patterns_core.py` to use `quilttools_placement.py` for point transformations.

### 🛠️ Gap Filling Bug Fix (DNA Quilt block import into.svg)

* **Edge Cutting Gap Filler:** Resolved a geometry gap bug where importing a rotated or non-fitting library block into an FPP region left blank space (uncovered by FPP pieces). The importer now detects the mapped outer edges of the library block, sequentially slices the target region using guillotine cuts, and automatically converts the outside leftover areas into plain fabric FPP gap-filling regions, keeping the sewing order fully validated.

## Changes in v1.3 (Phase C: Quilt Tree & New Quilt Layout) - July 2026

### 📐 Quilt Tree & New Quilt Layout (Phase C)

* **Central Quilt Core:** Created `quilttools_quilt_core.py` to serve as the data model and geometry generator for quilt layouts. Represents quilt cells (blocks, sashing, cornerstones, borders, and binding) as coordinates of arbitrary polygons and serializes the quilt spec as a JSON blob inside the SVG `<desc id="quilt-data-quilttools">` tag.
* **02. New Quilt Plugin:** Created `quilttools_new_quilt.inx` / `.py` under `Quilt Tools Pattern -> 02. New Quilt` to generate a straight-set quilt layout on the canvas. Features sashing width, cornerstone toggles, up to three layers of nesting borders, outer edge binding, active theme coloring, and canvas page resizing to fit the calculated quilt bounds.
* **Unit Testing:** Created `test_quilt_system.py` to assert correct polygon calculation, layer structure, and cell registry counts.

## Changes in v1.3 (Phase A & B: Shared Theme System & Menu Restructuring) - July 2026

### 🎨 Shared Theme System & Theme Manager (Phase A)

* **Central Theme Module:** Created a new module `quilttools_theme.py` to serve as the single source of truth for loading, validating, and inheriting theme configurations. Includes a fallback mechanism merging custom themes recursively on top of default `ifh` theme settings.
* **01. Theme Manager Plugin:** Created the `quilttools_theme_manager.inx` / `.py` plugin under `Quilt Tools Pattern -> 01. Theme Manager` supporting a notebook/tabbed user interface for Active Theme preference setting, schema validation (JSON format), system font installation checks, template cloning, and rendering visual color swatches / typeface cards onto the canvas.
* **Consumer Plugin Refactoring:** Simplified `quilttools_fabric_calculator`, `quilttools_metadata_blocks`, `quilttools_pattern_template`, and `quilttools_technique_library` to use the unified theme loader and replaced duplicate theme/custom_theme parameters with `theme_override`.

### ✂️ Fabric Cutting Layout Map Improvements

* **Triangular & Polygonal Shapes:** Replaced generic rectangular boxes on the fabric cutting map with actual FPP piece polygon paths (`polygon`) representing the exact shapes (e.g. triangles).
* **Block Cutting Boundaries:** Kept light dashed rectangles around each polygon to guide the user on the initial fabric strip block cuts.
* **Page Embedding (Overlap Fix):** Removed the separate, off-canvas layout map layer and integrated the visualization directly onto the Fabric Requirements page below the table. This displays the other export info (like headers, color codes, and table data) above the map instead of underneath or overlapping it.
* **Scale to Printable Width:** Automatically scales the WOF strip width to fit the page printable area (`avail_w`) exactly, keeping text labels and lines proportional.

### 🧩 Block Library Notebook Conversion (v2.0 UI Upgrade)

* **Tabbed Interface:** Converted the flat `7. Block Library` dialog in `quilttools_fpp_block_library.inx` into a notebook-tabbed interface with tabs for Load Block, Web Catalogue, Save Block, and Import Trace. This resolves screen height constraints, reducing the dialog size from ~20 stacked lines down to a clean ~6 lines.
* **CLI/Action Routing:** Updated `quilttools_fpp_block_library.py` to support the `--notebook` active tab parameter while retaining `--action` for backward-compatible CLI execution.

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
