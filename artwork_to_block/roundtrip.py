"""Load each finished block back the way the extension does, and check it."""
import sys

EXT = r"C:\Users\Pritt\AppData\Roaming\inkscape\extensions\quilttoolsv2.0"
sys.path.insert(0, EXT)

from lxml import etree            # noqa: E402
import quilttools_svg as qsvg     # noqa: E402
import quilttools_geometry as qg  # noqa: E402

for path in sys.argv[1:]:
    root = etree.parse(path).getroot()
    bd = qsvg.extract_block_data_from_svg_root(root)
    print(f"--- {path}")
    if bd is None:
        print("    NOT a Quilt Tools block (no embedded data)")
        continue
    leaves = bd.tree.leaf_regions()
    area = sum(qg.polygon_area(r.polygon) for r in leaves) / (96.0 ** 2)
    b = qsvg.block_bounds(bd)
    w, h = (b[2] - b[0]) / 96.0, (b[3] - b[1]) / 96.0
    print(f"    loads OK: {len(leaves)} pieces, {w:.3f} x {h:.3f} in, "
          f"piece area {area:.4f} sq in (block {w * h:.4f})")
    print(f"    root attrs: block={root.get('data-quilttools-block')} "
          f"name={root.get('data-quilttools-name')!r} "
          f"viewBox={root.get('viewBox')}")
    print(f"    unsound sections: {qsvg.unsound_union_sections(bd) or 'none'}")
    colors = bd.prefs.get("custom_colors", {})
    print(f"    colours stored: {len(colors)} "
          f"({sorted(set(colors.values()))})")
    labels = sorted(r.label for r in leaves)
    print(f"    labels: {labels[0]} .. {labels[-1]}")
