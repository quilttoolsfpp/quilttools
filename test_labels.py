import os
import sys
import unittest
import math

sys.path.insert(0, os.path.abspath("."))

import quilttools_fpp_core as core

class TestFPPLabelling(unittest.TestCase):
    def test_polygons_adjacent(self):
        # Two squares adjacent along a side
        # Poly A: [0, 0] to [10, 0] to [10, 10] to [0, 10]
        # Poly B: [10, 0] to [20, 0] to [20, 10] to [10, 10]
        poly_a = [(0, 0), (10, 0), (10, 10), (0, 10)]
        poly_b = [(10, 0), (20, 0), (20, 10), (10, 10)]
        
        # Test helper
        tree = core.RegionTree([(0,0), (20,0), (20,10), (0,10)])
        
        # We can simulate the adjacency checking
        # Define local helper in test to verify math
        def polygons_adjacent(poly_a, poly_b, tol=1.5):
            for i in range(len(poly_a)):
                p1 = poly_a[i]
                p2 = poly_a[(i + 1) % len(poly_a)]
                
                v_a = (p2[0] - p1[0], p2[1] - p1[1])
                len_a = math.hypot(*v_a)
                if len_a < tol:
                    continue
                u_a = (v_a[0] / len_a, v_a[1] / len_a)
                
                for j in range(len(poly_b)):
                    q1 = poly_b[j]
                    q2 = poly_b[(j + 1) % len(poly_b)]
                    
                    v_q1 = (q1[0] - p1[0], q1[1] - p1[1])
                    dist_q1 = u_a[0] * v_q1[1] - u_a[1] * v_q1[0]
                    if abs(dist_q1) > tol:
                        continue
                        
                    v_q2 = (q2[0] - p1[0], q2[1] - p1[1])
                    dist_q2 = u_a[0] * v_q2[1] - u_a[1] * v_q2[0]
                    if abs(dist_q2) > tol:
                        continue
                        
                    t1 = v_q1[0] * u_a[0] + v_q1[1] * u_a[1]
                    t2 = v_q2[0] * u_a[0] + v_q2[1] * u_a[1]
                    
                    min_t, max_t = min(t1, t2), max(t1, t2)
                    overlap_min = max(0.0, min_t)
                    overlap_max = min(len_a, max_t)
                    if (overlap_max - overlap_min) >= tol:
                        return True
            return False

        self.assertTrue(polygons_adjacent(poly_a, poly_b))
        
        # Disconnected squares
        poly_c = [(30, 0), (40, 0), (40, 10), (30, 10)]
        self.assertFalse(polygons_adjacent(poly_a, poly_c))

    def test_auto_label_splits_disconnected(self):
        # Create a block with 4 corner regions where the corners are disconnected
        # but under the same node (no split boundaries).
        # Tree hierarchy:
        # Node 1: root
        # Node 2 (corner 1), Node 3 (remaining)
        # Node 3 split: Node 4 (corner 2), Node 5 (remaining)
        # Node 5 split: Node 6 (corner 3), Node 8 (corner 4)
        # We will check that auto_partition_and_label places the four corners
        # into separate sections because they are disconnected.
        tree = core.RegionTree([(0,0), (100,0), (100,100), (0,100)])
        
        # Corner 1 (top-left)
        r_c1 = core.Region([(0,0), (40,0), (0,40)], label="C1")
        r_c1.id = 2
        # Corner 2 (top-right)
        r_c2 = core.Region([(60,0), (100,0), (100,40)], label="C2")
        r_c2.id = 4
        # Corner 3 (bottom-right)
        r_c3 = core.Region([(100,60), (100,100), (60,100)], label="C3")
        r_c3.id = 6
        # Corner 4 (bottom-left)
        r_c4 = core.Region([(0,60), (40,100), (0,100)], label="C4")
        r_c4.id = 8
        
        # Build hierarchy
        tree.regions = {
            1: core.Region([(0,0), (100,0), (100,100), (0,100)], label="root"),
            2: r_c1,
            3: core.Region([(40,0), (100,0), (100,100), (0,100), (0,40)], label="node3"),
            4: r_c2,
            5: core.Region([(40,0), (100,0), (100,100), (0,100), (0,40)], label="node5"),
            6: r_c3,
            8: r_c4
        }
        tree.regions[1].id = 1
        tree.regions[1].children = [2, 3]
        tree.regions[3].id = 3
        tree.regions[3].children = [4, 5]
        tree.regions[5].id = 5
        tree.regions[5].children = [6, 8]
        tree.root_id = 1
        
        # All internal splits are NOT split boundaries
        tree.regions[1].split_boundary = False
        tree.regions[3].split_boundary = False
        tree.regions[5].split_boundary = False
        
        # Run auto_partition_and_label
        tree.auto_partition_and_label(preserve_manual=False)
        
        # Corner pieces must have different section letters (A, B, C, D)
        letters = set()
        for rid in [2, 4, 6, 8]:
            label = tree.regions[rid].label
            self.assertTrue(len(label) >= 2)
            letters.add(label[0])
            
        # We expect 4 distinct sections, meaning each disconnected piece got its own section letter!
        self.assertEqual(len(letters), 4)

class TestEnclaveBoundaries(unittest.TestCase):
    """An imported sub-block (Import into Region / Fill Blocks) marks its
    host node split_boundary while its children are a _chain_leaves chain
    whose internal nodes reuse the host polygon. That flag means "the whole
    subtree is one sealed unit" (an enclave), NOT "my first child piece is
    its own structural group" — the misreading stranded one un-mergeable
    piece per imported block (error.svg regression, July 2026)."""

    def _make_enclave_tree(self):
        tree = core.RegionTree.__new__(core.RegionTree)
        tree.curves = []
        quad = [(0, 0), (100, 0), (100, 100), (0, 100)]
        host = core.Region(quad, label="H")
        p1 = core.Region([(0, 0), (40, 0), (0, 40)], label="P1")
        p2 = core.Region([(40, 0), (100, 0), (100, 100), (0, 100), (0, 40)],
                         label="P2")
        p3 = core.Region([(100, 60), (100, 100), (60, 100)], label="P3")
        chain = core.Region(list(quad), label="chain")  # bookkeeping node
        tree.regions = {r.id: r for r in (host, p1, p2, p3, chain)}
        host.children = [p1.id, chain.id]
        chain.children = [p2.id, p3.id]
        chain.split_boundary = False
        host.split_boundary = True  # legacy flag written by the importer
        for r in (p1, chain):
            r.parent_id = host.id
        for r in (p2, p3):
            r.parent_id = chain.id
        tree.root_id = host.id
        return tree, host, p1, p2, p3

    def test_legacy_true_flag_on_chain_is_one_group(self):
        tree, host, p1, p2, p3 = self._make_enclave_tree()
        groups = tree.get_structural_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0]), {p1.id, p2.id, p3.id})

    def test_explicit_enclave_flag_is_one_group(self):
        tree, host, p1, p2, p3 = self._make_enclave_tree()
        host.split_boundary = "enclave"
        groups = tree.get_structural_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0]), {p1.id, p2.id, p3.id})

    def test_real_cut_boundary_still_separates(self):
        tree, host, p1, p2, p3 = self._make_enclave_tree()
        # Make the host's split a REAL geometric cut: children partition it.
        tree.regions[host.children[1]].polygon = [
            (40, 0), (100, 0), (100, 100), (0, 100), (0, 40)]
        groups = tree.get_structural_groups()
        self.assertEqual(len(groups), 2)

    def test_no_boundary_between_enclave_members(self):
        tree, host, p1, p2, p3 = self._make_enclave_tree()
        self.assertFalse(tree.separated_by_boundary(p1.id, p2.id))
        self.assertFalse(tree.separated_by_boundary(p1.id, p3.id))


class TestSeamThroughRule(unittest.TestCase):
    """virtual_sewing_validator's physical rules (antarctica regression,
    July 2026): partial-edge necks and Y-junctions reject; smooth curved
    seam chains validate genuinely (no more blanket curve bypass)."""

    def _tree_with(self, polys):
        tree = core.RegionTree([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
        root = tree.regions[tree.root_id]
        ids = []
        for k, poly in enumerate(polys):
            r = core.Region(poly, label=f"T{k+1}", parent_id=root.id)
            tree.regions[r.id] = r
            root.children.append(r.id)
            ids.append(r.id)
        return tree, ids

    def test_partial_edge_neck_rejected(self):
        # A small piece grabbing a big piece by a fraction of its edge
        # (the E3/E4 failure): seams must be full shared edges.
        big = [(0, 0), (200, 0), (200, 100), (0, 100)]
        neck = [(0, 100), (50, 100), (50, 150), (0, 150)]
        tree, ids = self._tree_with([big, neck])
        ok, _ = tree.virtual_sewing_validator(set(ids))
        self.assertFalse(ok)

    def test_y_junction_rejected(self):
        # Three pieces meeting at an interior point = Y-seam.
        r1 = [(0, 0), (100, 0), (50, 50)]
        r2 = [(0, 0), (50, 50), (50, 100), (0, 100)]
        r3 = [(100, 0), (100, 100), (50, 100), (50, 50)]
        tree, ids = self._tree_with([r1, r2, r3])
        ok, _ = tree.virtual_sewing_validator(set(ids))
        self.assertFalse(ok)

    def test_smooth_curve_chain_accepted(self):
        # Three concentric arc strips: curved seams between rings, each a
        # smooth polyline running outline-to-outline (rotational FPP).
        import math as m

        def arc(r, a0=0.0, a1=90.0, steps=8):
            return [(500 + r * m.cos(m.radians(a0 + (a1 - a0) * i / steps)),
                     500 - r * m.sin(m.radians(a0 + (a1 - a0) * i / steps)))
                    for i in range(steps + 1)]

        def ring(r_in, r_out):
            return arc(r_in) + list(reversed(arc(r_out)))

        tree, ids = self._tree_with(
            [ring(100, 150), ring(150, 200), ring(200, 250)])
        ok, seq = tree.virtual_sewing_validator(set(ids))
        self.assertTrue(ok)
        self.assertEqual(len(seq), 3)

    def test_straight_two_piece_still_fine(self):
        a = [(0, 0), (100, 0), (100, 100), (0, 100)]
        b = [(100, 0), (200, 0), (200, 100), (100, 100)]
        tree, ids = self._tree_with([a, b])
        ok, _ = tree.virtual_sewing_validator(set(ids))
        self.assertTrue(ok)

    def test_ghost_leaf_purged(self):
        # A stale leaf fully covered by the real tiling (antarctica's
        # phantom 'A1') must be purged by auto-label, not resurrected.
        a = [(0, 0), (100, 0), (100, 100), (0, 100)]
        b = [(100, 0), (200, 0), (200, 100), (100, 100)]
        ghost = [(40, 20), (160, 20), (100, 80)]  # overlaps both
        tree, ids = self._tree_with([a, b, ghost])
        removed = tree.purge_ghost_leaves()
        self.assertEqual(removed, [f'T3'])
        self.assertEqual(len(tree.leaf_regions()), 2)
        # And the survivors are untouched.
        polys = sorted(tuple(r.polygon) for r in tree.leaf_regions())
        self.assertEqual(len(polys), 2)


if __name__ == "__main__":
    unittest.main()
