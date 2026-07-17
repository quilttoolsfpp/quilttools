# Project Context — Quilt Tools Pattern & FPP Suite

This document tracks the current state of the repository, completed phases, and immediate next steps for pair programming sessions.

---

## Current Status

* **Branch:** `test` (clean, up-to-date with remote)
* **Current Version:** v1.3.0
* **Last Updated:** July 2026

---

## Phase Log

### Phase A: Shared Theme System (Completed)
* **Goal**: Centralise theme loading, validation, and preference settings, refactoring the four consumer plugins and removing duplicated code.
* **Deliverables**:
  - `quilttools_theme.py`: Base module with recursive loading/merging of custom themes over default `ifh` theme structure and central `quilttools_pattern_prefs.json` I/O.
  - `quilttools_theme_manager.inx` / `.py`: Tabbed manager registered in `Quilt Tools Pattern` for setting the active theme, validating schemas & system fonts, creating new themes, and rendering visual swatch cards.
  - `themes/README.md`: Schema definition documentation.
  - Consumer Refactoring: Streamlined theme selectors and loaders in `quilttools_fabric_calculator`, `quilttools_metadata_blocks`, `quilttools_pattern_template`, and `quilttools_technique_library` to use `quilttools_theme.resolve_active_theme`.
  - Bug Fixes: Resolved font mismatch/drift bug in `quilttools_technique_library.inx` by replacing hardcoded UI combos.
  - Renamed `CHANGLOG.md` to `CHANGELOG.md`.

### Phase B: Menu Restructure & Repo Hygiene (Completed)
* **Goal**: Renumber and zero-pad all extensions under `Quilt Tools` and `Quilt Tools Pattern` to prevent ASCII sorting bugs in Inkscape. Convert the flat `Block Library` dialog to a notebook-tabbed interface to resolve vertical screen limitations.
* **Deliverables**:
  - Alphabetical Zero-padded prefix (`00` through `10` for Drafting, `01` / `05` through `08` for Pattern Development) added to all `.inx` files.
  - `02. Quick Cut (bind to a key)` integrated as a dialog-free variant alongside Guillotine Cut.
  - `Import into Region` moved from `Quilt Tools Pattern` back to the drafting submenu as `07. Import into Region`.
  - Integrated theme overrides in `10. Block Pattern Export` (`quilttools_fpp_export.py` / `.inx`) so that PDF page headers, footers, tables, and typography match the resolved theme style.
  - Removed lingering diagnostic files from the repository and destination.

### Phase C: Quilt Tree & New Quilt Layout (Completed)
* **Goal**: Implement the walking skeleton of the whole-quilt design pipeline by creating the quilt-level grid layout engine, sashing, cornerstones, borders, binding, and metadata registry.
* **Deliverables**:
  - `quilttools_quilt_core.py`: Peer module to `quilttools_fpp_core.py`. Holds the `QuiltData` model (name, settings, sashing, borders, binding) and cell registry, drawing all elements as polygon cells with their role/state metadata, and storing the JSON serialization inside the SVG `<desc id="quilt-data-quilttools">` tag.
  - `02. New Quilt` (`quilttools_new_quilt.py` / `.inx`): Dialog-tabbed interface under the `Quilt Tools Pattern` menu. Allows creating straight grid quilt layouts with configurable blocks, sashing, cornerstones, nested borders, binding, and page resizing.
  - `test_quilt_system.py`: Unit tests validating polygon maths, layer structure, and cell registry counts.

### Phase E: Technique-Aware Fabric Cutting (Completed — July 2026)
* **Goal**: Template-mode exports produce real cutting instructions (strips/subcuts,
  paired triangles, stitch-and-flip, batch HSTs/geese) instead of padded bounding boxes;
  FPP mode unchanged. Full design in `DESIGN_fabric_cutplan.md`.
* **Deliverables**:
  - `quilttools_cutplan.py` + `test_cutplan.py`: pure planner (classification, grain
    policy, snowball guillotine extension, batch maths, 50% strip rule, pieced strips for
    over-WOF pieces, `binding_plan`, NFP panel fallback via `quilttools_nesting`).
  - `quilttools_fpp_fabric.py`: dead-code cleanup; `pieces_from_block`,
    `calculate_template_requirements`, `draw_cutting_plan_map`.
  - `quilttools_fpp_export.py/.inx`: Cutting Instructions page in template mode; new
    options `cutting_math` (techniques/templates_only) and `oversize_batch`.
  - `12. Mark Cutting Technique` (`quilttools_fpp_mark_technique.py/.inx`): tagging,
    S&F auto-base detection + autodetect pass, batch grouping, review card; tags stored
    in `BlockData.prefs["piece_meta"]` (backwards compatible; `piece_meta()` /
    `set_piece_meta()` accessors in core).
* **Still open for the quilt-export phase**: aggregate CutPieces across block instances ×
  counts, surface binding + border pieced-strips on the quilt fabric page.

### Phase F: Quilt Tools Colour menu (Completed — July 2026)
* **Goal**: Consolidate the growing colour toolset (Fabric Palette, Palette
  Generator, Colour Randomiser/Reroll, custom-colour actions, quick save) into
  a top-level `Quilt Tools Colour` menu serving both block and quilt contexts,
  with explicit context tags and shared canvas-context detection.
* **Deliverables**: menu taxonomy Block/Colour/Pattern (drafting menu renamed
  `Quilt Tools Block`); `quilttools_custom_colours.py/.inx` split from FPP
  Display (which is now display-assist only, keeping the one-click bypass
  toggle); `quilttools_colour.detect_context` + CONTEXT_HELP guidance strings
  used by all block-only colour tools; Pattern menu renumbered 03–07;
  context tests in `test_colour_system.py`.

---

## Next Steps

### Phase D: Fill Blocks from Library (Prerequisites & Engine)
* **Placement Engine Extraction**: Extract stretch-to-fit/cover proportional scale sizing, auto-alignment, rotation, and flip algorithms into `quilttools_placement.py` for shared use.
* **Block Kind Schema Extension**: Extend the block schema to support `pieced` and `applique` block kinds alongside FPP.
* **Fill Blocks tool (`04. Fill Blocks from Library`)**: Create the plugin to select quilt placeholder cells and fill them with library blocks.
