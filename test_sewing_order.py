"""Tests for the section-assembly (Y-seam) checker's geometry soundness.

get_polygon_union silently returns partial geometry for sections whose
pieces don't share exact edges; calculate_section_sewing_order used to
validate assembly against that phantom geometry and could report a clean
Y-seam-free sequence for layouts that need inset seams. It now falls back
to a conservative convex-hull outline and must warn instead.

Run: python test_sewing_order.py (with inkex on PYTHONPATH)
"""

import quilttools_fpp_core as core
import quilttools_svg as qsvg


def build_block(labelled_pieces):
    box = [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)]
    tree = core.RegionTree(root_polygon=box)
    tree._rebuild_from_pieces([p for p, _ in labelled_pieces], box)
    leaves = sorted(tree.leaf_regions(), key=lambda r: r.id)
    for r, (_, label) in zip(leaves, labelled_pieces):
        r.label = label
    return core.BlockData(tree)


def test_ring_section_warns():
    """A 4-strip frame labelled as ONE section around a centre piece is an
    inset-seam construction: the checker must warn, not green-tick it."""
    bd = build_block([
        ([(0, 0), (400, 0), (400, 100), (0, 100)], "A1"),        # top strip
        ([(0, 300), (400, 300), (400, 400), (0, 400)], "A2"),    # bottom strip
        ([(0, 100), (100, 100), (100, 300), (0, 300)], "A3"),    # left strip
        ([(300, 100), (400, 100), (400, 300), (300, 300)], "A4"),  # right strip
        ([(100, 100), (300, 100), (300, 300), (100, 300)], "B1"),  # centre
    ])
    unsound = qsvg.unsound_union_sections(bd)
    assert unsound == ["A"], f"expected ring section A flagged, got {unsound}"
    steps, warn = qsvg.calculate_section_sewing_order(bd)
    assert warn, "ring-around-centre must produce a Y-seam warning"
    print("ok ring_section_warns")


def test_clean_two_sections_stay_clean():
    """Two half-blocks of two pieces each: sound unions, clean assembly."""
    bd = build_block([
        ([(0, 0), (200, 0), (200, 400), (0, 400)], "A1"),
        ([(200, 0), (300, 0), (300, 400), (200, 400)], "A2"),
        ([(300, 0), (400, 0), (400, 200), (300, 200)], "B1"),
        ([(300, 200), (400, 200), (400, 400), (300, 400)], "B2"),
    ])
    assert qsvg.unsound_union_sections(bd) == []
    steps, warn = qsvg.calculate_section_sewing_order(bd)
    assert not warn, "straight-seam layout must stay warning-free"
    assert steps, "expected join steps"
    print("ok clean_two_sections_stay_clean")


def test_t_joint_section_is_sound():
    """A piece spanning two neighbours (T-joint) unions soundly through
    iterative merging and must not be flagged."""
    bd = build_block([
        ([(0, 200), (200, 200), (200, 400), (0, 400)], "A1"),
        ([(200, 200), (400, 200), (400, 400), (200, 400)], "A2"),
        ([(0, 0), (400, 0), (400, 200), (0, 200)], "A3"),  # spans A1+A2
    ])
    assert qsvg.unsound_union_sections(bd) == []
    print("ok t_joint_section_is_sound")


def test_section_outline_fallback_covers_pieces():
    ring = [
        [(0, 0), (400, 0), (400, 100), (0, 100)],
        [(0, 300), (400, 300), (400, 400), (0, 400)],
        [(0, 100), (100, 100), (100, 300), (0, 300)],
        [(300, 100), (400, 100), (400, 300), (300, 300)],
    ]
    outline, sound = qsvg.section_outline(ring)
    assert not sound
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    assert min(xs) == 0 and max(xs) == 400 and min(ys) == 0 and max(ys) == 400, \
        "fallback outline must cover every piece"
    print("ok section_outline_fallback_covers_pieces")


def test_u_section_rejected_by_validator():
    """A U-shaped section's legs only meet through the bottom strip; there
    is no straight-seam order with physically connected intermediates, so
    the piece-order validator must reject it (previously it accepted
    'sewing' the two disconnected legs together)."""
    bd = build_block([
        ([(0, 0), (100, 0), (100, 400), (0, 400)], "K1"),      # left leg
        ([(300, 0), (400, 0), (400, 400), (300, 400)], "K2"),  # right leg
        ([(0, 300), (100, 300), (100, 400), (0, 400)], "X1"),  # (filler, unused)
    ])
    tree = bd.tree
    # Build the actual U out of clean pieces: legs + bottom strip
    bd2 = build_block([
        ([(0, 0), (100, 0), (100, 300), (0, 300)], "K1"),        # left leg
        ([(300, 0), (400, 0), (400, 300), (300, 300)], "K2"),    # right leg
        ([(0, 300), (400, 300), (400, 400), (0, 400)], "K3"),    # bottom strip
        ([(100, 0), (300, 0), (300, 300), (100, 300)], "J1"),    # centre
    ])
    t = bd2.tree
    ids = {r.label: r.id for r in t.leaf_regions()}
    ok, _ = t.virtual_sewing_validator([ids["K1"], ids["K2"], ids["K3"]])
    assert not ok, "U-shaped section must be rejected"
    ok2, seq = t.virtual_sewing_validator([ids["K1"], ids["K2"], ids["K3"], ids["J1"]])
    assert ok2, "U plus its centre is a plain rectangle build and must pass"
    print("ok u_section_rejected_by_validator")


def test_orphan_leaf_adopted():
    """A leaf left parentless (heal artefact) must be adopted into the tree
    by auto_partition_and_label and receive a fresh label."""
    bd = build_block([
        ([(0, 0), (200, 0), (200, 400), (0, 400)], "A1"),
        ([(200, 0), (400, 0), (400, 400), (200, 400)], "A2"),
    ])
    t = bd.tree
    # Orphan the second piece: detach it from its parent entirely
    ids = {r.label: r.id for r in t.leaf_regions()}
    orphan_id = ids["A2"]
    parent = t.regions[t.regions[orphan_id].parent_id]
    parent.children = [c for c in parent.children if c != orphan_id]
    t.regions[orphan_id].parent_id = None
    t.regions[orphan_id].label = "Z9"  # stale label that must not survive

    t.auto_partition_and_label()
    labels = sorted(r.label for r in t.leaf_regions())
    assert len(labels) == 2, f"orphan lost: {labels}"
    assert "Z9" not in labels, f"orphan not relabelled: {labels}"
    assert len(set(labels)) == len(labels), f"duplicate labels: {labels}"
    # and it must be reachable from the root again
    reachable = set()
    stack = [t.root_id]
    while stack:
        nid = stack.pop()
        reachable.add(nid)
        stack.extend(t.regions[nid].children)
    assert orphan_id in reachable, "orphan not re-attached to the tree"
    print("ok orphan_leaf_adopted")


if __name__ == "__main__":
    test_ring_section_warns()
    test_clean_two_sections_stay_clean()
    test_t_joint_section_is_sound()
    test_section_outline_fallback_covers_pieces()
    test_u_section_rejected_by_validator()
    test_orphan_leaf_adopted()
    print("ALL SEWING ORDER TESTS PASSED")
