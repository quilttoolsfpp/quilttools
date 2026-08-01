"""Tests for the heal/merge engine (July 2026 heal rework).

Covers: merge_leaf_set (iterative pairwise merge incl. T-junction partial
edges, absorb mode, boundary rules, curve refusal, phantom-ancestor
cleanup), heal_regions guards, smart-heal labelling, curve pruning, and
the backtracking virtual_sewing_validator.

Run: python test_heal.py (with inkex on PYTHONPATH)
"""

import quilttools_fpp_core as core
from quilttools_geometry import polygon_area, merge_adjacent_polygons

BOX = [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)]


def fresh():
    return core.RegionTree(root_polygon=list(BOX))


def leaf_area(tree):
    return sum(r.area_sq_in() for r in tree.leaf_regions())


def assert_sound(tree, msg=""):
    leaves = tree.leaf_regions()
    assert abs(leaf_area(tree) - (400 * 400) / 96.0 ** 2) < 0.05, \
        f"area not conserved {msg}: {leaf_area(tree)}"
    for r in leaves:
        assert tree.find_path(tree.root_id, r.id) is not None, \
            f"unreachable leaf {r.label} {msg}"


def test_same_piece_twice_is_refused():
    t = fresh()
    t.multi_guillotine_cut((200, -10), (200, 410))
    r = t.leaf_regions()[0]
    ok, msg = t.heal_regions(r.id, r.id)
    assert not ok and "DIFFERENT" in msg, msg
    print("ok same_piece_twice_is_refused")


def test_sibling_heal_reuses_parent_and_clears_boundary():
    t = fresh()
    t.multi_guillotine_cut((200, -10), (200, 410), is_boundary=True)
    a, b = t.leaf_regions()
    ok, msg = t.heal_regions(a.id, b.id)
    assert ok, msg
    assert len(t.leaf_regions()) == 1
    assert not t.leaf_regions()[0].split_boundary, \
        "healed leaf kept stale split_boundary"
    assert_sound(t)
    print("ok sibling_heal_reuses_parent_and_clears_boundary")


def test_heal_across_boundary_refused():
    t = fresh()
    t.multi_guillotine_cut((200, -10), (200, 410), is_boundary=True)
    t.multi_guillotine_cut((-10, 200), (410, 200))
    lv = t.leaf_regions()
    a = next(r for r in lv if all(p[0] <= 200.01 and p[1] <= 200.01
                                  for p in r.polygon))
    b = next(r for r in lv if all(p[0] >= 199.99 and p[1] <= 200.01
                                  for p in r.polygon))
    ok, msg = t.heal_regions(a.id, b.id)
    assert not ok and "boundary" in msg, msg
    # but consuming the whole boundary is allowed
    ok2, msg2, _ = t.merge_leaf_set({r.id for r in t.leaf_regions()})
    assert ok2, msg2
    assert_sound(t)
    print("ok heal_across_boundary_refused")


def test_t_junction_heal_merges():
    t = fresh()
    t.multi_guillotine_cut((200, -10), (200, 410))
    left = next(r for r in t.leaf_regions()
                if all(p[0] <= 200.01 for p in r.polygon))
    t.multi_guillotine_cut((-10, 200), (410, 200),
                           limit_to_region_id=left.id)
    lv = t.leaf_regions()
    lb = next(r for r in lv if all(p[0] <= 200.01 for p in r.polygon)
              and all(p[1] >= 199.99 for p in r.polygon))
    rh = next(r for r in lv if all(p[0] >= 199.99 for p in r.polygon))
    ok, msg = t.heal_regions(lb.id, rh.id)
    assert ok, f"partial-edge (T-junction) heal must merge: {msg}"
    assert len(t.leaf_regions()) == 2
    assert_sound(t)
    print("ok t_junction_heal_merges")


def test_absorb_bridges_gap():
    t = fresh()
    t.multi_guillotine_cut((133, -10), (133, 410))
    t.multi_guillotine_cut((266, -10), (266, 410))
    lv = sorted(t.leaf_regions(), key=lambda r: min(p[0] for p in r.polygon))
    left, mid, right = lv
    ok, msg, _ = t.merge_leaf_set({left.id, right.id}, absorb=False)
    assert not ok, "disconnected selection must refuse without absorb"
    ok, msg, guides = t.merge_leaf_set({left.id, right.id}, absorb=True)
    assert ok and "Absorbed 1" in msg, msg
    assert len(guides) == 3
    assert len(t.leaf_regions()) == 1
    assert_sound(t)
    print("ok absorb_bridges_gap")


def test_curved_heal_refused_and_curves_pruned():
    t = fresh()
    t.multi_circle_cut((200, 0), 100)
    assert len(t.curves) == 1
    a, b = t.leaf_regions()
    ok, msg = t.heal_regions(a.id, b.id)
    assert not ok and "curved" in msg, msg
    # smart heal may collapse it - and must prune the stale curve record
    ok2, _, _ = t.smart_heal_regions({a.id, b.id})
    assert ok2
    assert len(t.curves) == 0, "stale curve survived smart heal"
    # undo also prunes
    t2 = fresh()
    t2.multi_circle_cut((200, 0), 100)
    t2.undo_last_cut()
    assert len(t2.curves) == 0, "stale curve survived undo"
    print("ok curved_heal_refused_and_curves_pruned")


def test_non_sibling_heal_stays_reachable():
    t = fresh()
    t.multi_guillotine_cut((200, -10), (200, 410))
    t.multi_guillotine_cut((-10, 200), (410, 200))
    lv = t.leaf_regions()
    a = next(r for r in lv if all(p[0] <= 200.01 and p[1] <= 200.01
                                  for p in r.polygon))
    b = next(r for r in lv if all(p[0] >= 199.99 and p[1] <= 200.01
                                  for p in r.polygon))
    ok, msg = t.heal_regions(a.id, b.id)
    assert ok, msg
    assert_sound(t, "after non-sibling heal")
    groups = t.get_structural_groups()
    assert sum(len(g) for g in groups) == len(t.leaf_regions()), \
        "structural groups miss a healed piece"
    print("ok non_sibling_heal_stays_reachable")


def test_emptied_ancestors_leave_no_phantoms():
    # Cut a corner off, subdivide it, then merge the sub-pieces with an
    # outside piece: the corner's internal node empties and must vanish
    # instead of resurfacing as a phantom leaf.
    t = fresh()
    t.multi_guillotine_cut((200, -10), (200, 410))
    left = next(r for r in t.leaf_regions()
                if all(p[0] <= 200.01 for p in r.polygon))
    t.multi_guillotine_cut((-10, 200), (410, 200),
                           limit_to_region_id=left.id)
    lv = t.leaf_regions()
    lt = next(r for r in lv if all(p[0] <= 200.01 and p[1] <= 200.01
                                   for p in r.polygon))
    lb = next(r for r in lv if all(p[0] <= 200.01 for p in r.polygon)
              and all(p[1] >= 199.99 for p in r.polygon))
    ok, msg, _ = t.merge_leaf_set({lt.id, lb.id})
    assert ok, msg
    assert len(t.leaf_regions()) == 2
    assert_sound(t, "after subtree merge")
    print("ok emptied_ancestors_leave_no_phantoms")


def test_smart_heal_keeps_section_letter():
    t = fresh()
    t.multi_guillotine_cut((200, -10), (200, 410))
    ids = {r.id for r in t.leaf_regions()}
    ok, _, _ = t.smart_heal_regions(ids)
    assert ok
    t.rebuild_alphabet()
    labels = [r.label for r in t.leaf_regions()]
    assert all("TEMP" not in l.upper() for l in labels), labels
    print("ok smart_heal_keeps_section_letter")


def test_validator_backtracks_past_greedy_dead_end():
    # E/F regression shape: a big piece whose long edge carries two
    # T-junction neighbours plus a small cap. Greedy peeling could remove
    # the big piece first and strand the cap; backtracking must find the
    # valid order.
    polys = [
        [(0.0, 0.0), (100.0, 0.0), (100.0, 300.0), (0.0, 300.0)],   # big
        [(100.0, 0.0), (200.0, 0.0), (100.0, 150.0)],               # tri 1
        [(200.0, 0.0), (200.0, 300.0), (100.0, 300.0),
         (100.0, 150.0)],                                           # tri 2
        [(0.0, 0.0), (100.0, 0.0), (0.0, -80.0)],                   # cap on big only
    ]
    tree = core.RegionTree([(0, -80), (200, -80), (200, 300), (0, 300)])
    root = tree.regions[tree.root_id]
    ids = []
    for k, poly in enumerate(polys):
        r = core.Region(poly, label=f"T{k+1}", parent_id=root.id)
        tree.regions[r.id] = r
        root.children.append(r.id)
        ids.append(r.id)
    ok, seq = tree.virtual_sewing_validator(set(ids))
    assert ok, "backtracking validator must find the valid order"
    print("ok validator_backtracks_past_greedy_dead_end")


def test_merge_adjacent_polygons_basics():
    a = [(0, 0), (100, 0), (100, 100), (0, 100)]
    b = [(100, 0), (200, 0), (200, 100), (100, 100)]
    m = merge_adjacent_polygons(a, b)
    assert m is not None and abs(polygon_area(m) - 20000) < 1.0
    # disjoint
    c = [(300, 0), (400, 0), (400, 100), (300, 100)]
    assert merge_adjacent_polygons(a, c) is None
    # two separate contacts (pinch) must refuse
    u_shape = [(0, 0), (300, 0), (300, 300), (200, 300), (200, 100),
               (100, 100), (100, 300), (0, 300)]
    plug = [(100, 200), (200, 200), (200, 300), (100, 300)]
    assert merge_adjacent_polygons(u_shape, plug) is None, \
        "double-contact merge would self-touch"
    print("ok merge_adjacent_polygons_basics")


if __name__ == "__main__":
    test_same_piece_twice_is_refused()
    test_sibling_heal_reuses_parent_and_clears_boundary()
    test_heal_across_boundary_refused()
    test_t_junction_heal_merges()
    test_absorb_bridges_gap()
    test_curved_heal_refused_and_curves_pruned()
    test_non_sibling_heal_stays_reachable()
    test_emptied_ancestors_leave_no_phantoms()
    test_smart_heal_keeps_section_letter()
    test_validator_backtracks_past_greedy_dead_end()
    test_merge_adjacent_polygons_basics()
    print("ALL HEAL TESTS PASSED")
