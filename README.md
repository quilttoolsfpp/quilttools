# Quilt Tools FPP for Inkscape
**An advanced, open-source Foundation Paper Piecing (FPP) pattern design suite for Inkscape.**

Created by quilting enthusiast, this plugin suite bridges the gap between raw vector graphics and the physical constraints of quilt piecing.

Unlike standard drawing tools, Quilt Tools FPP understands how fabric is actually sewn together. It features a custom "Virtual Sewing Machine" geometric engine that mathematically prevents Y-seams, dynamically generates true-offset seam allowances, and automatically calculates structurally perfect sewing sequences for complex blocks (like Log Cabins and spiraling stars).

## ✨ Features
Currently, the extension is split into four modular tools located under **Extensions > Quilt Tools**:

* **1. New Block:** Generate perfectly scaled base grids. Includes a non-destructive scaling engine to import background images, resize them (Fit, Crop, Stretch), and automatically clip them to your block dimensions for easy tracing.
* **2. Guillotine Cut:** A strictly FPP-compliant cutting tool. Draw lines across shapes and cleanly slice them using infinite-ray projection math. Made a mistake? Use the **Heal** action to mathematically weld two pieces back together.
* **3. Labels & Guides:** The brain of the operation.
    * **Fully Auto-Label:** Uses an "Inside-Out" heuristic to automatically find the center of your block and perfectly sequence it outward without Y-seams.
    * **Define Section:** Manually group pieces into Sections (e.g., Section B). The tool runs a geometric validation check to ensure your selection is actually sewable before labeling it.
    * **Convert to Guides:** Instantly transform your finished block into blue Inkscape guide paths for layout and template generation.
* **4. Display & SA:** A smart-block management panel. Toggle 1/4" true-geometric seam allowances (with automated miter-limits for sharp points) and swap between Rainbow Piece coloring or Section-based coloring.

## 📥 Installation

1. Download or clone this repository. You should have 9 files:
   * `quilttools_fpp_core.py` (The shared mathematical library)
   * `quilttools_fpp_new_block.inx` / `.py`
   * `quilttools_fpp_cut.inx` / `.py`
   * `quilttools_fpp_labels.inx` / `.py`
   * `quilttools_fpp_display.inx` / `.py`
2. Open Inkscape.
3. Go to **Edit > Preferences > System**.
4. Find the **User extensions** folder path and click the "Open" icon next to it.
5. Copy all 9 files directly into that folder.
6. Restart Inkscape. The tools will now appear under **Extensions > Quilt Tools**.

## 🛠️ How to Use

### Step 1: Start a Block
Go to **Extensions > Quilt Tools > 1. New Block**. Define your block size in inches. If you want to trace an image, import your photo into Inkscape, select it, and choose "Crop to fit" in the extension menu. The tool will generate your block and seamlessly mask your image inside it.

### Step 2: Draft your Pattern
Use the Inkscape Pen/Bezier tool to draw lines across your block where you want your seams to be.
Select the line(s), then go to **Extensions > Quilt Tools > 2. Guillotine Cut** and hit Apply. The block will automatically shatter along those lines.
* *Note: To heal a cut, select exactly two adjacent pieces, change the Action to "Heal", and hit Apply.*

### Step 3: Sequence and Label
Go to **Extensions > Quilt Tools > 3. Labels & Guides**.
* Choose **Fully Auto-Label** to let the algorithm mathematically sort your pieces into printable FPP sections (A1, A2, B1, B2, etc.).
* To manually group a section, select the pieces you want, choose **Define Section from Selection**, and hit Apply. The tool will check for Y-seams and re-alphabetize the board around your choices.

### Step 4: Appearance
Go to **Extensions > Quilt Tools > 4. Display & SA**. Here you can turn your 1/4" Seam Allowances on or off, and change the block colors to help you visualize your sewing sections. Hit Apply, and the block will instantly redraw to match your preferences.

## 📄 License & Reuse
This project is open-source and licensed under the **GNU General Public License v3.0 (GPLv3)**.

We strongly believe in keeping tools accessible for makers and creators. You are completely free to use this extension to design commercial quilt patterns, modify the code for your own workflow, and share it. Our only requirement is that if you alter and distribute this code, your version must also remain open-source and free for the community.

Happy quilting! 🧵✨
