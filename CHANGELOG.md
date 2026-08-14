# Quilt Tools FPP — Changelog

All notable changes to the Quilt Tools FPP suite for Inkscape. Newest releases
are listed first.

---

## Changes in v2.2 (Planned / Upcoming) - TBA

### 🎨 Applique Block Kind & Layering
* **Applique Block Kind**: A new block kind option to designate applique blocks, generating a backing fabric block base and calculating yardage for individual applique shapes.
* **Applique Backdrops & Scraping**: Applique blocks automatically render a background bounding polygon (`qt-block-bg`) on the canvas for direct coloring and automatic color scraping.
* **Applique Base Seam Extensions**: Implemented `resolve_appliques` to automatically union (`quilttools_geometry.get_polygon_union`) background pieces with the applique shapes they support, ensuring backing fabrics extend under applique shapes without raw gaps.

---

## Changes in v2.1 (Traditional Piecing, Colour Suite, Y-Seam Separability, SVG Importer) - July 2026

### 🧵 Seam-through validation & curve-aware labelling (antarctica regression)

* **The Y-seam detector had a serious hole:** the piecing validator only
  required a shared edge plus straight-line separability, so sections whose
  pieces grab each other by a FRACTION of an edge (e.g. a borderline-U piece
  attached by a 13px sliver of a 159px edge) passed validation — both in
  auto-labelling and when manually defined. Replaced the peel criterion with
  the SEAM-THROUGH rule: a piece may be sewn on only when its contact with
  the assembled unit is ONE contiguous seam, straight or smoothly curved
  (per-vertex turns ≤ 30°), whose two ends both reach the unit's outline;
  plus a final gate that the pieces union soundly IN SEWING ORDER (each seam
  a full shared edge — get_polygon_union is order-sensitive, and sew order
  is exactly the order in which it works).
* **Curved seams are now genuinely validated** — the blanket "selection
  contains a curve → auto-pass" bypass is gone. Smooth rotational curve runs
  (polyline arcs) validate as sequential chains, Define Section accepts them
  as one section, and the merge pass may reunite curve fragments (its
  curve-exclusion guard removed, and its no-worse assembly comparison lets
  fragments merge on blocks whose baseline assembly already warns).
* **Result on the reported block:** the invalid E/F sections are refused
  everywhere (auto-label, Define Section), the 6-piece rotational curve run
  groups as ONE section, and fully-auto labelling drops from 17 fragments to
  9 sections with several groups matching the hand-corrected reference
  exactly. Regression fixtures in test_labels.py (partial-edge neck,
  Y-junction, smooth curve chain).

### 👻 Ghost piece purge
* **Phantom pieces that kept coming back:** stale regions from earlier edit
  states can survive in the block tree with their interior fully covered by
  the real pieces - they draw UNDERNEATH the block, align with no current cut
  line, and deleting their canvas path cannot kill them because every tool
  redraws from the tree. `purge_ghost_leaves` now removes any leaf whose
  sampled interior is entirely covered by other leaves (one at a time, so a
  mutually-stacked pair keeps one copy); it runs at the start of Fully
  Auto-Label, reports what it removed, and works with 'preserve manual
  sections' so a hand-labelled block can be cleaned without relabelling.

### 🎨 Traditional Pieced Block Kind & Canvas Display
* **Block Kind Selector**: Added option in the Display Toggle dialog (`quilttools_fpp_display.py`) to classify blocks as Traditional Pieced (Templates) rather than FPP.
* **Block Fill Opacity Control**: Added a Block Fill Opacity slider (0.0 to 1.0, defaulting to 1.0 / opaque) to the Display Toggle dialog to let users customize transparency (e.g. for tracing background sketch layers) and prevent automatic resets to the legacy hardcoded `0.80` opacity.
* **Differentiated Seam Allowance Padding**: Traditionally pieced templates are estimated using exact $0.25″$ (24px) seam-allowance margins instead of the larger $0.75″$ (72px) FPP foundation padding.
* **Canvas `temp colours ON` Marker Badge**: Added a visual text indicator badge (`temp colours ON` in a high-contrast orange pill tag) off to the side of the block on the Inkscape canvas whenever temporary colors bypass is toggled ON (`bypass_custom_colors = True`), making it obvious to the user that the default palette display is active.
* **Save Colours with Bypass Active**: Updated Quick Save Colours (`quilttools_fpp_save_colors.py`) and Custom Block Colours (`quilttools_custom_colours.py`) so that saving, sampling, or quantizing colors while temporary colors overlay is ON correctly scrapes the canvas paint into `custom_colors`, disables `bypass_custom_colors`, and immediately activates and displays the saved custom colors on screen.
* **Calculator Normalization**: Single-block fabric calculations refactored to use `pieces_from_block`, bringing template-mode block kinds support to both single-block and whole-quilt calculations.

### 💻 Cross-Platform & macOS GUI Support
* **Universal Tkinter UI Fallbacks**: Added native Python Tkinter modal dialog fallbacks across all extensions (`quilttools_fpp_export.py`, `quilttools_fpp_block_library.py`, `quilttools_quilt_library.py`, `quilttools_fpp_import_into.py`, `quilttools_new_quilt.py`, and `quilttools_blockpicker.py`). On macOS (where Inkscape Python lacks PyGObject/GTK 3), the tools now open native macOS Tkinter windows for Export Setup, Block Library Picker, Quilt Library Picker, and Layout Selector—eliminating silent dialog skips and browser catalogue redirects.

### 📄 PDF Pattern Export & Sticky Settings
* **Sticky PDF Export Settings**: The Finalize Export dialog (`quilttools_fpp_export.py`) now remembers and defaults to the user's last selected page setups (such as paper size, orientation, margin, seam allowance, and drawing scale) across sessions by saving preferences to a local JSON file.
* **Precuts Optimization**: Added a "Fabric & Precuts" tab to the export dialog, enabling users to toggle a custom set of precuts (Mini Charm, Charm, Layer Cake, Jelly Roll, Fat 16th, Fat 8th, Fat Quarter). The fabric estimator automatically optimizes suggestions for the smallest fitting precut and displays cutting measurements relative to that precut (rather than hardcoding WOF). When disabled, it optimizes strictly for WOF strip length.
* **Australian Spelling & Swatch Default**: Updated "Template Fabric Color Fill" to "Template Fabric Colour Fill" (and swatches to "Colour Swatch") in the GTK setup dialog, and changed the fallback default to "Colour Swatch (Minimal ink)".
* **Small-Piece Fabric Codes**: Ensured that template export always includes the fabric code (e.g. `[FAB1]`) on small pieces (which are fully colored in colour swatch mode), adjusting coordinates and font sizes dynamically to prevent label overlap. Incremented the font size for small piece labels by one size up (from `caption` / $10\text{px}$ to `body` / $12\text{px}$) to increase legibility.
* **Large-Piece Swatch & Text Scaling**: Scaled up both the color swatch rects (by 50% to $36 \times 24$) and the labeling text fonts (by 50% to $18\text{px}$ for labels and $15\text{px}$ for codes) on large pieces to improve readability on exported pages. Increased vertical text coordinates (code to `y + 36`, label to `y - 22`) to clear the bottom of the scaled swatch box, and raised the `is_too_small` threshold boundaries (to $60\text{px} \times 60\text{px}$ or $7200\text{px}^2$) so smaller pieces are colored in full instead of getting swatches.
* **Horizontal Labeling for Wide Pieces**: Added an aspect-ratio detector (`pw_r > 1.8 * ph_r`) to identify wide, short pieces. On these shapes, the label, swatch box, fabric code, and secondary duplicates notes are aligned side-by-side on a single horizontal axis (`y = r_cy`) rather than stacked vertically, preventing height overflow.
* **Smart Packed Test Square Option**: Added a checkbox `Include 2nd test square on pattern pages (smart packed)` to the Page Setup & Styling dialog. This packs a second $1″ \times 1″$ scale calibration square dynamically onto the template sheets, allowing users to verify print scaling even if they skip printing the front cover sheet.
* **Page Boundaries Toggle**: Added a checkbox `Show printable page boundaries (blue dashed line & page labels)` to the Page Setup & Styling dialog. Toggling this off hides the blue dashed printable margins and blue page number text labels, producing clean, print-ready pages for distribution/shops.
* **Cover Page Spacing & Preview Scaling**: Scaled down the block preview on Page 1 from $65\%$ to $42\%$ of page height when the Section Map page is disabled, and dynamically calculated the height of the assembly sequence and legend to place the fabric color key grid exactly below them. This prevents any vertical clashing and avoids overflow.
* **Section Map Layout Center & Deconfliction**: Centered the Section Map block at the top of Page 2 ($42\%$ page height) when the Section Map page is enabled. The Recommended Assembly Sequence and Pattern Legend are drawn side-by-side underneath the map, and the fabric color key grid is drawn below them, ensuring perfect alignment and fit on both A4 and Letter pages.
* **Fabric Layout Map Pagination**: Added automatic height estimation (`estimate_fabric_layout_map_heights`) and pagination for fabric layout maps in both FPP and Template modes. When fabric layout maps exceed the available vertical height on the Fabric Requirements page, they automatically spill onto dedicated paginated `Cutting Layout Map` pages (`page 1 of N`), eliminating page overflow.
* **Outer Cut Dimensions on Layout Images**: Added explicit outer **Length** and **Width** cut dimensions to all fabric rectangles drawn on cutting layout pages (e.g., `Cut Strip: 42.0" Length (WOF) × 2.50" Width`, `Cut Piece: 21.0" Length × 18.00" Width (Fat Quarter)`), providing exact starting fabric cut dimensions for every strip and precut.
* **Long Assembly Separate Page Fallback**: Added auto-detection that automatically forces the Section Map page to be enabled if the Recommended Assembly Sequence has more than 20 steps, or if the calculated heights of the sequence, legend, test square, and color keys exceed the available vertical space below the scaled preview on Page 1. This prevents printing issues and clipping.
* **Native Inkscape Page Number Tags**: Added `<inkscape:page>` elements with `inkscape:label="1"`, `inkscape:label="2"`, etc. inside `<sodipodi:namedview>` during export and workspace generation. Inkscape 1.2+ now automatically renders native page number tag tabs (`1`, `2`, `3`...) at the top-left corner of each page frame on the canvas and enables native multi-page PDF exporting out-of-the-box.
* **Default Export Title & Filename**: Configured `sodipodi:docname` and `inkscape:export-filename` on the SVG document root and `<sodipodi:namedview>` to default to `{Block Name} Pattern.pdf` (e.g. `Uneven Log Cabin Pattern.pdf`), replacing Inkscape's generic `bitmap.pdf` fallback in Inkscape's built-in Export dialog (`File > Export...`).
* **Custom Colour Swatch Shapes**: Added a new `Colour Swatch Shape` dropdown to the Page Setup & Styling dialog. Users can now choose the icon shape for fabric color key swatches and template piece swatches across all exported pattern pages: `Rectangle (Default)`, `Love Heart ❤️`, `Circle ⚪`, or `Star ⭐`.
* **Unified Theme-Driven Export System**: Integrated pattern line weights (`0.75 pt`, `0.50 pt`, `0.35 pt`, `1.00 pt`), swatch shapes, footer branding options, header/footer divider lines, and font family settings directly into `quilttools_theme.py`. Themes now supply all default styling choices to exports automatically, giving users a true "one-press" export experience while allowing full customization via Theme Manager.
* **Export Settings Dialog Restructuring**: Resolved control overlaps in GTK and Tkinter dialogs by separating `Page Setup & Layout` and `Styling & Aesthetics` into distinct notebook tabs. Controls now feature dedicated non-overlapping row grids and generous spacing across 4 tabs (`Credits & Info`, `Page Setup & Layout`, `Styling & Aesthetics`, `Fabric & Precuts`).

### 🗂 Quilt Library (00. in Quilt Tools Pattern)
* **Save and re-open whole quilts** (`quilttools_quilt_library.py/.inx`): a
  QuiltLibrary folder beside the extensions stores full standalone-SVG
  snapshots, filed as Category/Name and browsed with the shared folder-view
  picker (thumbnails, search, [template] badges).
* **Two save kinds:** COMPLETE keeps placed blocks, custom colours and fabric
  pattern fills (referenced pattern defs are gathered into the file, following
  href chains, so fabrics travel with it); TEMPLATE strips placed content and
  resets every cell's registry to empty - a reusable layout for
  'Fill Blocks from Library'.
* **Loading** restores the saved page size, refuses to clobber an existing
  quilt layout unless 'Replace' is ticked, skips defs already present (same
  fabric embedded once), and tells you the next step for templates. Distinct
  from New Quilt's layout PRESETS, which store dialog settings only.

### 🌈 Quilt Tools Colour Suite
* **Unified Colour Menu & Keybind Actions**: Consolidated the fabric styling and randomizer tools under the dedicated `Quilt Tools Colour` submenu. The frequently used `Quick Save Colours` hotkey action was moved back to the `Quilt Tools Block` drafting menu as `05b. Quick Save Colours (bind to a key)` for design convenience.
* **Interactive Palette Generator**: Generate harmonious palettes using OKLCh color space calculations with interactive anchor color picking directly from Inkscape's color wheel, and export as GPL palettes.
* **Colour Randomiser & Reroll**: Instantly randomize block or quilt layout colors, featuring a streamlined Reroll action bindable to a hotkey for quick design iteration.
* **Smart Context Detection**: Integrated a standard-library canvas context detector (`quilttools_colour.py`) that classifies the canvas (block / quilt / both / none) without Inkex dependencies, protecting placed cells from accidental edits.

### 📐 Y-Seam Separability & Shape-Cut Policies
* **Shape Cut Bypass & Technique Badging**: Shape cuts permit Y-seams under an explicit "Allow Y-seams" bypass option. Unseparable shapes are automatically tagged with the `technique="y_seam"` attribute.
* **Technique badging**: Added a high-contrast orange (`#d35400`) "Y-Seam" badge to the legend markup catalog and review card.

### 📥 SVG Block Importer
* **Direct Vector Import**: Added a dedicated SVG Block Importer (`quilttools_fpp_import_svg.py` / `.inx`) supporting recursive polygon/path parsing, coordinate normalization, union outlines, Y-seam verification, and automatic sew-order labeling.

---

## Changes in v2.0 (Whole Quilt Layouts & Technique-Aware Cutting) - July 2026

### 🌐 Quilt Tree & Layout Engine
* **Grid Layout Core**: Implemented `quilttools_quilt_core.py` and `01. New Quilt` layout tool to construct block grids with custom rows, columns, sashing, cornerstones, borders, and bindings.
* **Placed Block Sizing**: Projects library blocks onto quilt layout cells using tiled affine transformations (fit, stretch, rotate, flip).
* **Fabric Aggregation**: Fabric requirement engine parses cell block instances to aggregate quilt-wide fabric totals.

### ✂️ Technique-Aware Fabric Cutting Plans
* **Exact Template Cutting Math**: Developed `quilttools_cutplan.py` to plan templates based on exact grain lines, strip-subcut nesting, HST pairs, and stitch-and-flip corners.
* **Mark Cutting Technique**: Tag pieces with techniques like stitch-and-flip, batch HSTs, and geese. Base shapes are automatically extended to cover corner flips.

---

## Changes in v1.7 (Quilt Tools Colour menu) - July 2026

### 🎨 Colour tools get their own top-level menu

### 🔧 Fixes

* **Palette Generator ran into two crashes:** its dialog's tab id
  (`--notebook`) was not declared by the script (usage error on Apply), and
  the swatch layer was appended via `self.svg.getroot()` (inkex's `self.svg`
  IS the root). Both fixed - generation, GPL export to the Inkscape palettes
  folder and canvas swatches verified end-to-end.
* **Palette Generator anchor picker:** the anchor colour can now be picked
  from Inkscape's colour widget (wheel/sliders) instead of typing a hex -
  an "Anchor Colour" combo chooses between typed hex (default, blank =
  random), the picked colour, or fully random; invalid hex input falls back
  to random with a message instead of failing.
* **Dialog/script drift audit:** every .inx parameter is now either declared
  by its script or tolerated via `parse_known_args` - the same latent crash
  was fixed in the Colour Randomiser (`--notebook`) and Pattern Template
  Scaffold (`--header_prefs`) before anyone hit it.

* **New menu taxonomy:** Extensions now organise as **Quilt Tools Block**
  (renamed from "Quilt Tools"), **Quilt Tools Colour** (new) and **Quilt Tools
  Pattern** — sorting alphabetically in that order. Colour tools serve BOTH
  block drafting and quilt layouts from one place; every menu label carries an
  explicit context tag: "(Blocks & Quilts)", "(Blocks only)", "(works anywhere)".
* **Quilt Tools Colour contents:** 00. Fabric Palette · 01. Palette Generator ·
  02. Colour Randomiser + 02b. Reroll (bind to a key) · 03. Custom Block
  Colours + 03b. Quick Save Colours (bind to a key).
* **Numbering convention:** standard tools use plain sequential numbers; a
  letter suffix is reserved for keybindable quick variants of the tool they
  accompany (02b Quick Cut, 02b Colour Reroll, 03b Quick Save Colours). The
  Block menu renumbered accordingly: 03 Heal · 04 Resize · 05 FPP Display ·
  06 Shape Cut · 07 Import into Region · 08 Import Block from SVG · 09 Add
  Plain Border · 10 Electric Quilt Export · 11 Labels & Guides · 12 Mark
  Cutting Technique · 13 Block Pattern Export.
* **FPP Display split:** Quilt Tools Block ▸ 05. FPP Display Toggle is now a
  pure design-assist tool — the one-click temporary bypass, default palette
  view (rainbow/section), seam-allowance preview and colour grouping. Nothing
  in it changes saved colours. The PERMANENT colour actions (save canvas
  colours, sample from traced image, quantize to N fabrics, palette export,
  clear) moved to **Quilt Tools Colour ▸ 03. Custom Block Colours**, with
  signposts in both dialogs. Legacy dialog params are still accepted so stale
  saved values never error.
* **Shared context detection** (`quilttools_colour.detect_context`): every
  colour tool now classifies the canvas (block / quilt / both / none) the same
  way — a block nested inside a placed quilt cell correctly counts as quilt
  artwork, not an editable block. Block-only tools refuse on quilt-only
  canvases with precise guidance (use Fabric Palette / Colour Randomiser for
  placed cells, or open the source block); completion messages always state
  what was acted on, and when a canvas holds BOTH contexts, what was not
  touched. Unit tests in test_colour_system.py.
* **Theme Manager parked in the Colour menu** as `x. Theme Manager (pattern
  PDF styling)` - the 'x.' prefix sorts it last, below the everyday tools
  (it styles pattern documents, so it lives with the colour/styling family
  without occupying a workflow number).
* **Pattern menu renumbered** after Fabric Palette and Theme Manager moved
  out: 01. New Quilt · 02. Fill Blocks · 03. Technique Library · 04. Fabric
  Requirements Table · 05. Text & Metadata · 06. Pattern Template Scaffold.
  Cross-references updated (colour-tool guidance and Fill Blocks messages now
  point at '01. New Quilt').


## Changes in v1.6.2 (Fill Blocks Fixes) - July 2026

### 🧩 Hybrid exports, HST templates, square opt-out, multi-page instructions

* **Always-FPP sections in Template exports:** tag any piece with the new
  "Always FPP" technique (09b. Mark Cutting Technique) and its WHOLE SECTION is
  delivered as an FPP foundation template inside a Template export — one export
  can now mix FPP foundations, single-piece templates, stitch-and-flip corner
  squares and batch HST/geese cutting maths. FPP sections are costed with the
  rough-cut ¾"-padded estimate, folded into each fabric's total and flagged on
  the instructions page. Stored as `prefs["fpp_sections"]` (section letters —
  note re-running the auto-labeller can change letters); FPP badges on canvas
  and a review-card line show what's opted in.
* **HST sewing-line templates:** Template exports now include one printable
  square per unique 2-at-a-time HST size — solid diagonal cut line, dashed seam
  lines ¼" either side, and layered-squares instructions. Optional
  ("Include HST sewing-line templates", default on).
* **Squares to the cutting list only:** a new export option omits printed
  templates for square/rectangular pieces — they are cut straight from the
  strip/subcut measurements (fussy-cut squares keep their templates).
  Independently, pieces consumed by technique squares (stitch-and-flip corners,
  batch HSTs, geese) no longer print useless shape templates at all; an
  instructions note says why.
* **Multi-page cutting instructions:** the instructions are flattened into a
  row stream and paginated across as many "Cutting Instructions (page k of n)"
  pages as needed, instead of truncating with "continued fabrics omitted".
* **The cutting layout map never overflows:** it used to be squeezed under the
  instructions and could run off the bottom of the page (its height cap only
  checked between fabrics). Per-fabric map heights are now estimated up front
  (`estimate_map_heights`): when the whole map fits in the space left under the
  final instructions page it stays INLINE there (simple blocks keep their
  one-page summary); otherwise it moves to dedicated "Cutting Layout Map
  (page k of n)" pages with fabrics binned to always fit. A per-strip safety
  cap truncates gracefully if an estimate is ever wrong.
* Blocks whose every piece is technique-consumed (e.g. an all-HST block) now
  export cleanly with instruction pages and no piece templates.

### ✂️ Stitch-and-flip fixes (Mark Cutting Technique)

* **Noisy triangles are recognised:** EQ-imported blocks carry near-collinear
  phantom vertices (seam endpoints sitting ~0.0001" off a piece's edge), which
  made real corner triangles classify as 5-sided shapes and the Mark tool
  reject them ("select the corner TRIANGLE"). The planner now strips vertices
  within cutting tolerance (0.015") of the line between their neighbours before
  classifying, finding hypotenuses, matching congruence, or extending seams.
* **Corners over three or more base pieces work:** seam extension previously
  clipped each base's cell independently, which overlaps (and falsely refuses)
  when 3+ bases meet the corner on different seam lines. Bases are now peeled
  off in hypotenuse order, splitting the footprint at each junction — with new
  explicit refusals when the selected bases leave a gap on the corner seam,
  overlap, or a junction's seams don't continue in one straight line.
* **Eighth-inch snapping tolerates wobble:** cut sizes round UP to the next
  1/8", but now ignore ~1/160" of numeric noise, so an 8.0002" extended base
  cuts at 8" instead of 8-1/8".
* Regression: piece E1 (4" corner over three pieced bases E2+E5+E10) now tags
  with all bases auto-detected and exports as a 4½" corner square + un-snowballed
  8" x 3" base rectangle.
* **Double-layer corners:** a stitch-and-flip corner that is itself partly
  covered by a LATER corner (sew corner 1, then corner 2 flips over the top of
  it) used to be rejected — only its visible sliver exists in the drawing, so
  its seam and size read wrong. Stitch-and-flip tags are now resolved in
  dependency order (`resolve_stitch_flips`): the outer corner's seam extension
  first restores the inner corner's full pre-trim footprint, and the inner
  corner is then analysed on that extended shape — in the Mark tool (which
  reports "double-layer" when it happens), the fabric planner, and the review
  card's corner sizes. Regression: A2 (1" corner sewn first, flipped over by
  2" corner A4) tags as a 1½" square onto A1, A4 as 2½", and base A1 cuts as
  the full un-snowballed square.

### 📁 Block Library browsing — folders by default, whole-library search

* **New shared browser** (`quilttools_blockpicker.py`) used by Block Library,
  Fill Blocks and Import into Region: the default view now browses the library
  BY SUBFOLDER — folder cards with block counts, a breadcrumb and an Up button —
  instead of one flat wall of every block. Typing in the search box instantly
  flattens to matching blocks from the WHOLE library (name or folder matches),
  each captioned with the folder it lives in; clearing the search returns to
  the folder you were browsing. Thumbnails are cached per dialog, and the three
  tools' previously copy-pasted picker code is now one implementation.

### 🎨 03. Fabric Palette — Recolour tab & block-scoped colour swapping

* **New "Recolour (Plain)" tab:** swap colours with a plain colour at three
  scopes — the selected piece(s) only, every piece of that colour in THE SAME
  BLOCK (the quilt cell or standalone block containing the selection), or every
  piece of that colour in the whole quilt/document.
* **"THIS BLOCK only" scope added to Colour-with-Fabric** too, so a fabric can
  be painted onto one block's colour without touching its neighbours.
* **Matching understands fabric fills:** the "same colour" scopes key on the
  piece's own fill whether it is a plain colour or a fabric pattern — select a
  fabric-filled piece and every piece wearing that fabric can be swapped to a
  new fabric or a plain colour. Recolouring to plain clears the piece's
  pre-fabric memory (so Remove Fabric can't resurrect the old colour) and
  garbage-collects patterns that are no longer used.
* Multi-selection matches the union of the selected pieces' colours.
* **Palette-first colour picking:** the Recolour tab's new-colour popup reads
  Inkscape's own session state — the colour on the tool indicator (eyedropper /
  paint-bucket / last palette click, from preferences.xml) is offered as the
  one-click default, and the swatch grid is the palette currently selected in
  Inkscape's swatches panel (.gpl parsed with swatch names as tooltips, e.g.
  Moda Bella Solids). A "Colour wheel…" button covers off-palette colours; an
  option switches back to the fixed colour button. Headless runs fall back to
  the tool colour automatically.
* **Whole-block clicks just work:** clicking a quilt block selects the whole
  cell group, so when the selection holds several colours a swatch chooser
  pops up listing them (with piece counts and fabric names) to tick which
  colour(s) to replace. An optional "Colour to replace (hex)" field skips the
  chooser entirely; Alt+click still selects individual pieces natively.

### 🧱 04. Fill Blocks from Library

* **Silent failure fixed:** a leftover debug `print()` wrote to stdout — the SVG
  stream returned to Inkscape — and Python's buffering flushed it AFTER `</svg>`,
  making the returned document invalid XML. Inkscape discarded the entire edit
  while the "Successfully filled N cell(s)" message (stderr) still appeared. The
  fill logic itself was fine; removing the print makes placements land again.
  Audited all other extensions for stray stdout prints: none found.
* **Blocks appeared as a corner sliver / cells looked unfilled:** the placed
  content group carried BOTH the placement matrix and the cell clip-path, but
  `userSpaceOnUse` clip coordinates are evaluated in the element's own
  (transformed) space — so the clip region itself was scaled/shifted by the
  placement matrix, clipping each block down to a sliver (or nothing). Placed
  content is now an untransformed outer group holding the clip (canvas coords)
  with the matrix on an inner group. Verified by rendering: blocks fill their
  cells edge-to-edge and re-filling replaces prior content cleanly.
* **"Target Blocks" option restored to the popup:** the Fill-all-blocks /
  Fill-empty-blocks-only combo is back in the GTK dialog (shown when nothing is
  selected; it still exists on the .inx dialog's "3. Options" tab and the popup
  defaults to that value). Verified: empty mode skips an already-full quilt with
  a clear message; all mode overwrites existing placements without duplicates.
* **Explicit-selection fills for borders & cornerstones:** with cells selected,
  Fill Blocks can now place library blocks into BORDER, CORNERSTONE, SASHING and
  SETTING-TRIANGLE cells (pieced borders etc.) — the Tile sizing modes tile the
  block along the strip. This is opt-in by selection only: bulk fills with no
  selection still target block cells exclusively, and binding cells are always
  refused (a folded strip cannot hold a pieced block). A tip fires when
  stretch-fitting into long strips where tiling usually looks better.
* Piece labels drawn by the FPP tools are now locked (`sodipodi:insensitive`) so
  canvas selection only ever grabs pieces, never their labels (v1.6.1 follow-up).

## Changes in v1.6.1 (Enclave Boundary Fix) - July 2026

### 🧩 Imported blocks no longer strand un-mergeable pieces

* **Root cause:** Import into Region / Fill Blocks marks the host region
  `split_boundary` while storing the imported pieces as a bookkeeping chain
  (`_chain_leaves`). The structural-group walk read that flag as "my two children
  are separate groups", so the FIRST imported piece landed alone in a one-piece
  structural group — the auto-labeller's merge pass silently refused to absorb it
  into any neighbouring section (each refusal invisible to the user, however often
  auto-label was re-run), Heal refused with the "structural grid boundary" error,
  and Reset-to-Boundaries produced an overlapping chain-node blob.
* **Fix:** `split_boundary` now distinguishes a real boundary CUT (children
  geometrically partition the node — grid lines, circle cuts, crop frames:
  behaviour unchanged) from an ENCLAVE (imported sub-block: the whole subtree is
  ONE structural group, sealed from outside). New imports write the explicit
  `"enclave"` value; legacy saved blocks are recognised geometrically (an internal
  child carrying the node's own polygon), so existing SVGs are fixed on load with
  no file changes. Consumers updated: `get_structural_groups`,
  `separated_by_boundary`, `smart_heal_regions` (healing within an imported block
  is allowed; healing across its edge still requires selecting the whole block),
  and `reset_to_boundaries` (an enclave collapses to one clean region).
* Regression tests in `test_labels.py` (legacy flag, explicit flag, real-cut
  separation still enforced, no false boundary between enclave members).

## Changes in v1.6 (Technique-Aware Cutting Plans) - July 2026

### ✂️ New: Template-mode Cutting Instructions (Block Pattern Export)

* **Exact-shape fabric requirements for Template exports.** When Export Pattern Type is
  *Template*, the Fabric Requirements page becomes a **Cutting Instructions** page driven
  by a new pure-python planner (`quilttools_cutplan.py`, unit-tested by `test_cutplan.py`):
  exact SA-offset template shapes, grouped into strip-and-subcut instructions
  ("Cut 1 strip 8½" × WOF; subcut 4 × 8½" squares"). FPP Foundation exports keep the
  generous ¾"-padded estimates unchanged.
* **Grain policy:** direction-free is the default (rotation in 90° steps only — edges stay
  on grain); squares/rectangles always cut square-to-grain even when set on point;
  direction-fixed and fussy-cut are per-piece opt-ins. Unusual shapes (>4 sides) may rotate
  freely when direction-free.
* **Triangle pairing:** leftover 45° right triangles nest two-up into squares/rectangles
  (the classic finished+⅞" HST square emerges from pure geometry) with a
  "cut in half on the diagonal" instruction; grain-locked triangles that cannot pair are
  reported.
* **Strips are only recommended at ≥50% utilisation**; below that, pieces are NFP-nested
  onto an open yardage panel (reusing the Smart Pack engine) with grain-constrained
  rotations.
* **Over-WOF pieces (borders):** pieced-strip plans — "cut N strips, join end-to-end,
  subcut to length" — with straight joins by default (long-armer friendly) and a diagonal
  option; same-width smaller pieces ride along in the run. `binding_plan()` provides
  quilt-level binding maths (2L + 2W + 10" slack, always diagonal joins) for the coming
  quilt export.
* **New export options:** *Cutting Math* (Use marked techniques / Templates only) and
  *Oversize batch units for trimming* (default on). The cutting layout map now draws real
  strips, subcut lines and diagonal cuts in template mode.
* **Duplicate Templates option (Template exports):** print a template for every piece
  (default, unchanged) or one template per unique SHAPE, labelled "A1 - cut 8" with a
  "for: A1, B2, ..." caption listing the pieces it covers. Colours are combined: when a
  shared template covers more than one fabric it prints uncoloured (no fill, no fabric
  code) with a "mixed fabrics - see layout page" caption, a note in the page header, and
  a run-time tip recommending the Section Map / layout page for fabric placement.
  Congruence is detected geometrically (rotation/translation only — mirrored pieces keep
  their own template) via `quilttools_cutplan.congruence_key`; e.g. Churn Dash prints 3
  templates instead of 17. Applies to Smart Pack, Open Canvas and Finalize; fabric
  estimates still count every piece.
* Removed dead/broken code from `quilttools_fpp_fabric.py` (unreachable duplicate helpers
  and a `fabric_estimate` that would have raised NameError; `verify_fabric.py` scratch
  harness deleted — superseded by `test_cutplan.py`).

### 🪡 New: 09b. Mark Cutting Technique (Quilt Tools menu)

* **Tag pieces with cutting techniques** stored in a new optional `piece_meta` key inside
  the block's JSON metadata — fully backwards compatible (legacy SVGs behave exactly as
  before; older tool versions round-trip the key untouched).
* **Stitch-and-flip corners** (applied ONLY from this tool, never automatically): select
  the corner triangle; base pieces are found along the seam automatically, validated with
  guillotine seam extension — pieced bases are supported by continuing every straight seam
  across the corner footprint, and non-guillotine layouts are refused with a clear
  message. Fabric consequences: corner square = finished leg + ½", base piece(s) cut
  un-snowballed (full footprint restored), bonus-HST note included.
* **Batch techniques:** 2-at-a-time HSTs (default cut = finished + 1" with up-front
  disclosure; exact ⅞" opt-out), 8-at-a-time HSTs (2×(finished+⅞"/1")), and 4-at-a-time
  no-waste flying geese (width+1¼"/height+⅞", oversized +1½"/+1") — tagged triangles are
  replaced by parent squares in the cut list, with remainder fallback warnings.
* **Auto-detect** scans the block for stitch-and-flip corner candidates and marks them
  "suggested" (dashed badges with '?') until confirmed or cleared.
* **Review card:** "Show review card" draws an annotation panel beside the block — mini
  block diagram with marked corners numbered plus a legend covering S&F corners, batch
  groups, and grain tags. Annotation only; never exported.
* Design record: `DESIGN_fabric_cutplan.md`.

---

## Changes in v1.5 (Fabric Palette) - July 2026

### 🧶 New: 03. Fabric Palette (Quilt Tools Pattern menu)

* **Colour layers with real fabric instead of hex codes.** A new `quilttools_fabric_palette.py` / `.inx` extension applies bitmap fabric images (photos/scans) as SVG `<pattern>` fills, always at true printed scale — a 2" check repeats every 2" on the page, so previews are life-accurate. Pattern tiles use `patternUnits="userSpaceOnUse"`, so the print flows continuously across adjacent patches like pieces cut from one cloth.
* **Import Fabric tab:** pick an image, name it (`Category/Name` filing supported), and enter the real width of fabric shown in the image; pixel dimensions are read from PNG/JPEG/GIF/BMP headers directly (no PIL dependency) and the true dpi/height are derived. Fabrics live in a `FabricLibrary/` folder beside the extensions with a JSON sidecar per image.
* **Colour with Fabric tab:** GTK thumbnail picker with search (browser-catalogue fallback, mirroring the Block Library UX). Apply to the selection, to *every shape with the same colour as the selection* (paint-pot recolouring of a whole quilt), or the whole current layer. Optional print scale % and rotation are applied as light-weight `<pattern xlink:href>` variants so the image is embedded only once per document. Images embed as base64 by default (portable SVGs), with a link-instead option.
* **Palette Sheet tab:** draws labelled true-scale swatches of the library (optionally filtered) on a "Fabric Palette" layer beside the page, so an SVG can carry its own fabric palette; works with Edit → Paste Style.
* **Remove Fabric tab:** every shape remembers its pre-fabric solid colour in `data-quilttools-orig-fill` and can be reverted (selection or whole document); unused fabric patterns and their embedded images are cleaned from `<defs>` afterwards.
* **Web Catalogue tab:** searchable browser gallery of the fabric library; clicking a fabric copies its name. A starter `Samples/Red Check` fabric ships in the library.

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
