"""Stage 2: wrap cleaned polygons as a Quilt Tools block SVG.

Runs on Inkscape's Python so it can use the extension's own core: the tree,
the auto-labeller and the sewing validator all come from quilttools, which is
what makes the output a real block file rather than a look-alike.

Usage: inkscape-python build_block.py <pieces.json> <name> <out.svg>
"""
import json
import os
import sys

EXT = r"C:\Users\Pritt\AppData\Roaming\inkscape\extensions\quilttoolsv2.0"
sys.path.insert(0, EXT)

from lxml import etree                      # noqa: E402
import quilttools_fpp_core as core          # noqa: E402
import quilttools_svg as qsvg               # noqa: E402


def build(pieces, name):
    xs = [p[0] for pc in pieces for p in pc["pts"]]
    ys = [p[1] for pc in pieces for p in pc["pts"]]
    outline = [(min(xs), min(ys)), (max(xs), min(ys)),
               (max(xs), max(ys)), (min(xs), max(ys))]

    # Same shape of tree the Crop tool rebuilds: leaves under one right-leaning
    # binary chain of non-boundary internal nodes, so the whole block reads as
    # a single structural group for the auto-labeller to partition.
    tree = core.RegionTree()
    colors = {}
    leaf_ids = []
    for pc in pieces:
        r = core.Region([tuple(p) for p in pc["pts"]])
        tree.regions[r.id] = r
        leaf_ids.append(r.id)
        colors[str(r.id)] = pc["fill"]
    tree.root_id = tree._chain_leaves(leaf_ids, outline)
    tree.sanitize_tree()

    tree.auto_partition_and_label()

    prefs = {
        "show_sa": False,
        "sa_in": 0.25,
        "color_mode": "piece",
        "custom_colors": {k: v for k, v in colors.items()
                          if k in {str(r.id) for r in tree.leaf_regions()}},
        "fill_opacity": 1.0,
        "block_kind": "fpp",
        "block_library_name": name,
    }
    return core.BlockData(tree, prefs)


def report(bd):
    tree = bd.tree
    leaves = tree.leaf_regions()
    secs = {}
    for r in leaves:
        secs.setdefault(r.label.rstrip("0123456789"), []).append(r)

    print(f"    pieces: {len(leaves)}   sections: {len(secs)} "
          f"({', '.join(sorted(secs))})")
    bad = []
    for letter, rs in sorted(secs.items()):
        ok, seq = tree.virtual_sewing_validator([r.id for r in rs])
        _, sound = qsvg.section_outline([r.polygon for r in rs])
        flag = "" if (ok and sound) else "  <-- PROBLEM"
        if not (ok and sound):
            bad.append(letter)
        print(f"      {letter}: {len(rs):>2} pieces  straight-seam order={ok} "
              f"union sound={sound}{flag}")
    steps, warn = qsvg.calculate_section_sewing_order(bd)
    print(f"    assembly: {' | '.join(steps) if steps else 'single section'}"
          f"{'  (WARNING: fallback join)' if warn else ''}")
    return bad


def main():
    src, name, out = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(src) as fh:
        pieces = json.load(fh)

    print(f"--- {name}")
    bd = build(pieces, name)
    bad = report(bd)

    svg = qsvg.block_data_to_standalone_svg(bd, name)
    xml = etree.tostring(svg, pretty_print=True, xml_declaration=True,
                         encoding="UTF-8")
    with open(out, "wb") as fh:
        fh.write(xml)
    print(f"    wrote {out} ({os.path.getsize(out)} bytes)"
          f"{'  [sections needing attention: %s]' % ','.join(bad) if bad else ''}")


if __name__ == "__main__":
    main()
