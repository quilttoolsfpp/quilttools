# Quilt Tools FPP — Inkscape Extension Suite

Quilt Tools FPP is a vector-based extension suite for **Inkscape** designed for block drafting, whole-quilt layout design, color palette management, and pattern sheet generation. It supports Foundation Paper Piecing (FPP), Traditional Template Piecing, and Applique block kinds.

---

## 🚀 Features

### 1. Block Drafting (`Quilt Tools Block`)
* **Interactive Slicing**: Slice block polygons using straight-line **Guillotine Cuts** or curved **Shape Cuts**.
* **Auto-Labelling**: Re-label sewing sequences and sections automatically, ensuring proper sew-order.
* **Separability Policy & Y-Seams**: Enforces FPP piece-level separability checks on curved shape cuts, permitting them under a bypass option and automatically tagging unseparable pieces with `technique="y_seam"`. Guillotine straight cuts remain unaffected.
* **SVG Block Importer**: Load external SVG vector designs directly into standard FPP blocks with recursive geometry parsing, outlines extraction, and auto sew-ordering.

### 2. Colour & Palette Management (`Quilt Tools Colour`)
* **Unified Colour Menu**: Manage colors across blocks and quilts using a central menu.
* **Fabric Palette**: Sample colors directly from canvas selections or traced images, save custom block palettes, and export `.gpl` palettes.
* **Palette Generator**: Choose a primary color and automatically generate harmonious secondary values (monochrome, complementary, triadic, etc.) using OKLCh color models.
* **Colour Randomiser**: Rapidly randomize layout colors with keybindable rerolls to test palette options instantly.

### 3. Layout Grid & PDF Generation (`Quilt Tools Pattern`)
* **Quilt Layouts**: Generate grids with custom rows, columns, sashing, cornerstones, nested borders, and bindings.
* **Block Placement**: Tile and fit library blocks onto layout cells using rotation, flipping, and scaling.
* **Technique-Aware Fabric Planning**: Generate exact fabric templates, paired HST cutting plans, stitch-and-flip corner restorations, sashing strips, and binding calculations.
* **Applique Layering**: Supports overlapping applique templates, automatically unioning background pieces under applique layers so fabrics overlap without gaps.
* **Scaffolding & PDF Export**: Output ready-to-print PDF pattern sheets complete with assembly maps, cutting instructions, and template pages.

---

## 🛠️ Installation & Requirements

### 1. Requirements & System Dependencies
* **Windows**: Works out-of-the-box. Inkscape's bundled Python includes all required libraries.
* **macOS**: Works out-of-the-box. Uses native macOS Tkinter windows bundled with Inkscape.
* **Linux (Ubuntu / Debian / WSL)**: Secondary popup dialogs (Block Picker, Export Linting, Theme Manager) require Python GTK3 and Tkinter packages. Install them via:
  ```bash
  sudo apt update
  sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 python3-tk
  ```

### 2. Installing the Extension
1. Copy all `.py` and `.inx` files (along with `BlockLibrary`, `FabricLibrary`, `LayoutLibrary`, and `themes`) into your Inkscape user extensions directory:
   * **Windows**: `%APPDATA%\inkscape\extensions`
   * **macOS/Linux**: `~/.config/inkscape/extensions/quilttools`
   *(Note for WSL users: Copy files into the native Linux filesystem path `~/.config/inkscape/extensions/quilttools` rather than symlinking over `/mnt/c`)*
2. Restart Inkscape. The tools will appear under the `Extensions` menu in three submenus:
   * **Quilt Tools Block**
   * **Quilt Tools Colour**
   * **Quilt Tools Pattern**


---

## 🧪 Developer Testing

The suite is backed by an automated unit test suite. Run tests using Inkscape's bundled Python environment:

```powershell
# Set Inkscape extensions path to PYTHONPATH and run unit tests
$env:PYTHONPATH="C:\Program Files\Inkscape\share\inkscape\extensions"; & "C:\Program Files\Inkscape\bin\python.exe" -m unittest discover
```
