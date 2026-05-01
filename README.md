# ✂️ Quilt Tools for Inkscape

![Inkscape Compatibility](https://img.shields.io/badge/Inkscape-1.x%2B-blue)
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

## 🤝 Contributing & Issues
If you encounter a bug—especially a "Phantom Piece" or a Guillotine Cut failure—please open an issue and attach your raw `.svg` file. Because Quilt Tools relies on precise floating-point geometry, the raw file is required to diagnose locked loops or collinear alignment errors.

---

*Designed for Quilters, Powered by Math.*
