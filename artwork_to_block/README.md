# Artwork → Quilt Tools block

Turns a flat piece of vector artwork (a traced/low-poly picture where every
patch is its own filled path) into a Quilt Tools block SVG that the Block
Library, Import into Region and the FPP tools all accept.

Not an Inkscape extension — a two-step command-line pipeline, because the two
halves need different Pythons.

## Step 1 — clean the geometry (needs shapely, so system Python)

```
python convert.py <artwork.svg> <block_size_in> <pieces.json>
```

Rebuilds the artwork as a planar arrangement and fixes what tracing leaves
behind:

* **gaps** — traced art usually has hairline "grout" between patches. Each gap
  strip is given to the piece it runs along (the larger one, where two are
  equally close, so fine detail keeps its traced shape).
* **slivers** — anything under `MIN_AREA` (0.02 sq in) or narrower than
  `MIN_WIDTH` (0.09 in) is folded into its best neighbour, preferring one of
  the same colour.
* **enclosed shapes** — a piece ringing another (a nose, an eye) can't be
  sewn, so it's cut in two along the line of one of the enclosed shape's own
  edges.
* **vertex noise** — seams are simplified as shared arcs (never per piece), so
  both sides of a seam always stay identical. `SIMPLIFY` (0.03 in) is the most
  a seam may move; a pass is kept only if the block still verifies as an exact
  partition.

Artwork that already tiles the block exactly is passed through untouched — no
repair, no simplification, seam for seam.

The run prints a verification block. `coverage_gap`, `overlap`,
`pieces_with_holes` and `pieces_too_small` must all be 0 and `union_parts` 1.

## Step 2 — wrap it as a block (needs inkex, so Inkscape's Python)

```
PYTHONPATH="C:\Program Files\Inkscape\share\inkscape\extensions" \
  "C:\Program Files\Inkscape\bin\python.exe" \
  build_block.py <pieces.json> "<Block Name>" "<out.svg>"
```

Builds the region tree the way the Crop tool does (leaves under one
right-leaning chain of non-boundary internal nodes — a flat tree does NOT
work, `get_structural_groups` only walks `children[0]` and `children[1]`),
runs `auto_partition_and_label`, and writes the file through
`block_data_to_standalone_svg`. Artwork fills are carried over as
`custom_colors`.

It prints the FPP verdict per section: piece count, whether the section has a
straight-seam piecing order, and whether its pieces union soundly. A section
reporting `False` needs attention in Heal Block or Labels.

Drop the finished SVG anywhere under `BlockLibrary/` and the pickers find it.

## Checking a finished block

```
... build_block-style invocation ... roundtrip.py <block.svg> [...]
```

Loads each file the way the extension does and reports piece count, finished
size, total piece area, stored colours and any unsound sections.
