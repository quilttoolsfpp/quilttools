# QuiltTools FPP — Phased Roadmap & Status Report

This report provides a comprehensive summary of our current project status, completed phases, remaining roadmap objectives, and the active implementation plan as we prepare to start a fresh context window.

---

## 1. Project Status & Versioning
*   **Current Codebase Version**: v1.4.0
*   **Current Branch**: `test` (clean, fully tested, all 19 unit tests passing)
*   **Active Features Deployed**: 
    *   Unified theme system (`01. Theme Manager`)
    *   Straight and on-point quilt layout generator (`02. New Quilt`) with custom nested and cornerstone borders
    *   Block catalog browser and selection-empty target auto-filling (`04. Fill Blocks from Library`) with tiling and clipping masks
    *   True-shape nesting for Smart Pack (`10. Block Pattern Export`)
    *   EQ8 block library import utility (`09. Import EQ8 Block`)

---

## 2. Completed Phases

### Phase 0 & 1: Core Geometry Foundations
*   **Arbitrary Closed-Path Block Boundaries**: Refactored the core block model to support arbitrary polygon/triangle/hexagon boundaries rather than only axis-aligned rectangles.
*   **Curve Handling**: Defined curve cuts as non-FPP boundary elements, ensuring that the auto-slicing engine respects curves.

### Phase A: Shared Theme System
*   **Theme Module (`quilttools_theme.py`)**: Centralized module for recursive theme inheritance and local configuration preferences.
*   **Theme Manager (`01. Theme Manager`)**: Graphical preference tool for setting themes, verifying fonts, and outputting color palettes.

### Phase B: Menu Hygiene & UI Notebooks
*   **Notebook Layout Picker**: Converted flat dialogs to tabbed interfaces, resolving vertical screen height limitations.
*   **Plugin Renumbering**: Prefixed all extension names with zero-padded numbers to guarantee correct ASCII sorting order in Inkscape.

### Phase C & E: Quilt Core & On-Point Layouts
*   **Central Quilt Registry (`quilttools_quilt_core.py`)**: Serializes full layout specifications (sashing, borders, binding, cells) as a JSON payload inside the SVG.
*   **Corrected On-Point Geometry**: Implemented the mathematical EQ8 diagonal-step grid ($D = (S + W_s)\sqrt{2}$) and generated corner/side setting triangles for rotated diamond grids.
*   **Advanced Border Styles**: Added horizontal-first (`long_h`), vertical-first (`long_v`), and cornerstone (`cornerstone`) border layouts (matching the requested **Baby Star Bloom** cornerstone layout).
*   **Preset Opt-In Dialog**: Restored the visual GTK preset library, configured it to be strictly opt-in via a checkbox parameter, and corrected GTK size preview maths.

### Phase D: Placement & Block Filling Upgrades
*   **Placement Engine (`quilttools_placement.py`)**: Extracted a centralized 3-point affine projection transformation module.
*   **Fill Blocks Plugin (`04. Fill Blocks from Library`)**: 
    *   Allows filling selected blocks, sashing, or borders.
    *   Prompts with fill options (Fill All vs. Fill Empty Blocks) when selection is empty.
    *   Supports advanced **tiling** (`tile_stretch` and `tile_ratio`).
    *   **Settings Pre-loading**: Pre-selects block path, rotation, sizing, and flip options when editing an already placed block.
    *   **Boundary Clipping**: Generates and applies SVG `<clipPath>` definitions to keep oversized/rotated/tiled blocks perfectly masked inside cell bounds.

---

## 3. Remaining Phases

### Phase F (Current Active Phase): Whole-Quilt Fabric Aggregation
*   **Objective**: Extend `quilttools_fabric_calculator.py` to recognize when it is running on a quilt layout. It will parse the layout's cell structure, load FPP pieces for placed blocks, scale them to fit their cells, resolve sashing/border colors, and compute aggregate fabric yardage requirements for the entire quilt.

### Phase 4: Block-Shape Frontier (Clothing FPP)
*   **Objective**: Expand block boundaries to arbitrary closed paths (including curves) to allow paper-piecing clothing pattern templates directly from SVG garment outlines.

### Phase 5: Hardening & User Testing
*   **Objective**: Stress-test large complex blocks, multi-block compositions, and gather feedback for documentation refinements.

---

## 4. Current Implementation Plan (Phase F)

### Goal
Extend `quilttools_fabric_calculator.py` to support whole-quilt layouts:

1.  **Quilt Detection**: Use `qcore.find_quilt_group(self.svg)` to check for a quilt layout.
2.  **Aggregation Logic**:
    *   Iterate through all cell records in `quilt_data.cells`.
    *   For **placed blocks**, load their source block SVG, scale their FPP regions to fit the cell bounds (supporting tiling, flip, and rotation), and register their fabric pieces.
    *   For **plain fabric regions** (sashing, borders, binding, setting triangles, empty blocks), convert their polygon coordinates from pixels to inches and resolve their color codes via the active theme palette.
3.  **Calculation & Rendering**: Pass all pieces to the existing `fabric.fabric_estimate` module and render a unified aggregated yardage table directly on the canvas.
4.  **Fallback**: Fall back to the standard single-block FPP calculation if no quilt layout is present.
