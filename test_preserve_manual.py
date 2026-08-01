"""Tests for preserve-manual mode in Fully Auto-Label (July 2026).

Manual work is stamped by the Labels tool: Define Section -> manual_tag
(+ manual_first on its #1), Set First -> manual_first, Relabel ->
manual_label. auto_partition_and_label(preserve_manual=True) pins tagged
sections (keeps letter, renumbers honoring the start piece) unless the
pure-auto partition of that area uses strictly FEWER sections; hand
labels are never touched. Cuts and merges inside a section inherit tags.

Run: python test_preserve_manual.py (with inkex on PYTHONPATH)
"""

import re

import quilttools_fpp_core as core

BOX = [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)]


def four_patch():
    """2x2 grid: full-auto needs two sections (rows or columns)."""
    t = core.RegionTree(root_polygon=list(BOX))
    t.multi_guillotine_cut((200, -10), (200, 410))
    t.multi_guillotine_cut((-10, 200), (410, 200))
    return t


def quad(t, x_right, y_bottom):
    from quilttools_geometry import polygon_centroid
    return next(
        r for r in t.leaf_regions()
        if (polygon_centroid(r.polygon)[0] > 200.0) == x_right
        and (polygon_centroid(r.polygon)[1] > 200.0) == y_bottom
    )


def define_section(t, ids_in_order, letter):
    """Simulate the Labels tool's Define Section stamping."""
    tag = 1 + max(
        (r.manual_tag for r in t.regions.values() if r.manual_tag is not None),
        default=0,
    )
    for i, nid in enumerate(ids_in_order):
        r = t.regions[nid]
        r.label = f"{letter}{i + 1}"
        r.manual_tag = tag
        r.manual_first = i == 0
    return tag


def prefixes(t):
    out = {}
    for r in t.leaf_regions():
        m = re.match(r"^([A-Za-z]+)", r.label)
        out.setdefault(m.group(1) if m else "?", []).append(r)
    return out


def test_defined_section_survives_auto_relabel():
    t = four_patch()
    tl, bl = quad(t, False, False), quad(t, False, True)
    define_section(t, [tl.id, bl.id], "Q")
    t.auto_partition_and_label(preserve_manual=True)
    secs = prefixes(t)
    assert "Q" in secs and {r.id for r in secs["Q"]} == {tl.id, bl.id}, \
        f"defined section broken apart: { {k: [r.label for r in v] for k, v in secs.items()} }"
    assert t.regions[tl.id].label == "Q1", "manual start piece must stay #1"
    print("ok defined_section_survives_auto_relabel")


def test_preserve_off_reflows():
    t = four_patch()
    tl, bl = quad(t, False, False), quad(t, False, True)
    define_section(t, [tl.id, bl.id], "Q")
    t.auto_partition_and_label(preserve_manual=False)
    assert "Q" not in prefixes(t), "preserve OFF must allow a full reflow"
    print("ok preserve_off_reflows")


def test_auto_wins_when_strictly_fewer_sections():
    # Two single-piece manual sections in a plain two-strip block: auto
    # can do it in ONE section, so the manual grouping yields.
    t = core.RegionTree(root_polygon=list(BOX))
    t.multi_guillotine_cut((200, -10), (200, 410))
    a, b = t.leaf_regions()
    define_section(t, [a.id], "Q")
    define_section(t, [b.id], "R")
    t.auto_partition_and_label(preserve_manual=True)
    assert len(prefixes(t)) == 1, \
        f"auto (1 section) must beat manual (2): {sorted(r.label for r in t.leaf_regions())}"
    print("ok auto_wins_when_strictly_fewer_sections")


def test_manual_kept_on_tie():
    # 4-patch, manual left column: manual+rest = 2 sections, full-auto =
    # 2 sections -> tie -> manual grouping is kept.
    t = four_patch()
    tl, bl = quad(t, False, False), quad(t, False, True)
    define_section(t, [tl.id, bl.id], "Q")
    t.auto_partition_and_label(preserve_manual=True)
    secs = prefixes(t)
    assert "Q" in secs and {r.id for r in secs["Q"]} == {tl.id, bl.id}
    assert len(secs) == 2
    print("ok manual_kept_on_tie")


def test_cut_inside_section_stays_in_section():
    t = four_patch()
    tl, bl = quad(t, False, False), quad(t, False, True)
    define_section(t, [tl.id, bl.id], "Q")
    # cut the bottom-left piece in half
    t.multi_guillotine_cut((-10, 300), (210, 300), limit_to_region_id=bl.id)
    t.auto_partition_and_label(preserve_manual=True)
    secs = prefixes(t)
    assert "Q" in secs and len(secs["Q"]) == 3, \
        f"cut children must stay in the defined section: { {k: len(v) for k, v in secs.items()} }"
    labels = sorted(r.label for r in secs["Q"])
    assert labels == ["Q1", "Q2", "Q3"], f"pinned section must renumber cleanly: {labels}"
    print("ok cut_inside_section_stays_in_section")


def test_merge_inside_section_keeps_tag():
    t = four_patch()
    tl, bl = quad(t, False, False), quad(t, False, True)
    tag = define_section(t, [tl.id, bl.id], "Q")
    ok, msg, _ = t.merge_leaf_set({tl.id, bl.id})
    assert ok, msg
    merged = next(r for r in t.leaf_regions() if r.area_sq_in() > 5)
    assert merged.manual_tag == tag, "merged piece must inherit the section tag"
    assert merged.manual_first, "merged piece absorbs the start marker"
    print("ok merge_inside_section_keeps_tag")


def test_hand_label_never_touched():
    t = four_patch()
    tl = quad(t, False, False)
    tl.label = "SKY"
    tl.manual_label = True
    t.auto_partition_and_label(preserve_manual=True)
    assert t.regions[tl.id].label == "SKY", t.regions[tl.id].label
    t.auto_partition_and_label(preserve_manual=False)
    assert t.regions[tl.id].label != "SKY", "preserve OFF may relabel"
    print("ok hand_label_never_touched")


def test_set_first_survives_rebuild_alphabet():
    t = core.RegionTree(root_polygon=list(BOX))
    t.multi_guillotine_cut((133, -10), (133, 410))
    t.multi_guillotine_cut((266, -10), (266, 410))
    strips = sorted(t.leaf_regions(), key=lambda r: min(p[0] for p in r.polygon))
    right = strips[2]
    for r in t.leaf_regions():
        r.manual_first = r.id == right.id
    t.rebuild_alphabet()
    assert re.match(r"^[A-Za-z]+1$", right.label), \
        f"manual start piece must stay #1 after rebuild: {right.label}"
    print("ok set_first_survives_rebuild_alphabet")


def test_markers_survive_serialization():
    t = four_patch()
    tl, bl = quad(t, False, False), quad(t, False, True)
    tag = define_section(t, [tl.id, bl.id], "Q")
    bd = core.BlockData(t)
    bd2 = core.BlockData.from_json(bd.to_json())
    r2 = bd2.tree.regions[tl.id]
    assert r2.manual_tag == tag and r2.manual_first, \
        "manual markers lost in serialization round-trip"
    print("ok markers_survive_serialization")


def test_legacy_untagged_doc_falls_back_to_heuristic():
    t = four_patch()
    tl, bl = quad(t, False, False), quad(t, False, True)
    # legacy doc: user section labels exist but no manual stamps
    tl.label, bl.label = "Q1", "Q2"
    t.auto_partition_and_label(preserve_manual=True)
    secs = prefixes(t)
    assert "Q" in secs and {r.id for r in secs["Q"]} == {tl.id, bl.id}, \
        "legacy non-A sections must still be preserved by the heuristic"
    print("ok legacy_untagged_doc_falls_back_to_heuristic")


if __name__ == "__main__":
    test_defined_section_survives_auto_relabel()
    test_preserve_off_reflows()
    test_auto_wins_when_strictly_fewer_sections()
    test_manual_kept_on_tie()
    test_cut_inside_section_stays_in_section()
    test_merge_inside_section_keeps_tag()
    test_hand_label_never_touched()
    test_set_first_survives_rebuild_alphabet()
    test_markers_survive_serialization()
    test_legacy_untagged_doc_falls_back_to_heuristic()
    print("ALL PRESERVE-MANUAL TESTS PASSED")
