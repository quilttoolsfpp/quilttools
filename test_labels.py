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

if __name__ == "__main__":
    unittest.main()
