# Quilt Tools FPP — Block Library

This folder is the shared block library for the **7. Block Library** extension.
Every block is a self-contained `.svg` file that carries its own Quilt Tools
block data (the seam/region tree) embedded in a `<desc>` element, so it can be
loaded back into any document with full fidelity and then resized, edited, and
exported like any other managed block.

## How it works

- **Load block (replace current)** — pick a block by name (or browse to any
  block SVG) and it replaces the block in your current document.
- **Save current block to library** — writes your current block here as
  `<name>.svg`. Use `Category/Name` to file it into a subfolder.
- **List library blocks** — prints everything currently in this folder.
- **Import external SVG as tracing background** — for plain/foreign FPP SVGs
  that are *not* Quilt Tools blocks: brings the artwork in as a locked
  background layer so you can trace it with New Block + Guillotine Cut.

## Adding blocks

Either save them from inside Inkscape (recommended), or drop in any SVG that
contains a Quilt Tools FPP block. Blocks are matched by file name, so keep
names distinct. Subfolders are supported and become `Subfolder/Name`.

## ⚠️ A note on updates

Because this folder lives *inside* the extension directory, re-installing or
updating Quilt Tools by overwriting the extension folder can replace or remove
files here. If you keep your own saved blocks alongside the shipped ones,
back them up (or keep personal blocks in a clearly named subfolder) before
updating.

## Shipped starter blocks

- Four Patch (6")
- Nine Patch (6")
- Half Square Triangle (6")
- Flying Geese (6" × 3")
- Square in a Square (6")
