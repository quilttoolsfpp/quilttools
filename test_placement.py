import unittest
import math
import re

import sys
sys.path.insert(0, ".")

import quilttools_placement as qplace

class TestPlacement(unittest.TestCase):
    def test_placement_matrix_equivalence(self):
        # Source polygon (10x10 square)
        src_poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        
        # Target polygon (arbitrary quadrilateral stretched, offset, and rotated)
        # Offset to start at (50, 60), rotated roughly 30 deg, size ~20x20
        dst_poly = [(50, 60), (70, 70), (60, 90), (40, 80)]
        
        # 1. Stretch Mode
        map_pt, matrix_str = qplace.calculate_placement_transform(
            src_poly, dst_poly, sizing_mode="stretch", rotation=45.0, flip="horizontal", auto_align=True
        )
        
        # Parse matrix(a,b,c,d,e,f)
        match = re.match(r"matrix\(([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^)]+)\)", matrix_str)
        self.assertIsNotNone(match)
        a, b, c, d, e, f = map(float, match.groups())
        
        # Test 5 arbitrary test points inside the source block
        test_points = [(0, 0), (5, 5), (10, 10), (2.5, 7.5), (8.0, 1.0)]
        
        for pt in test_points:
            mapped_pt = map_pt(pt)
            
            # Apply affine matrix manually
            mx = a * pt[0] + c * pt[1] + e
            my = b * pt[0] + d * pt[1] + f
            
            self.assertAlmostEqual(mapped_pt[0], mx, places=5)
            self.assertAlmostEqual(mapped_pt[1], my, places=5)

    def test_longest_edge_angle(self):
        # Horizontal line pointing right: angle 0
        poly1 = [(0, 0), (10, 0), (10, 5), (0, 5)]
        angle1 = qplace.get_longest_edge_angle(poly1)
        self.assertAlmostEqual(angle1, 0.0)
        
        # Line at 45 deg: angle 45
        poly2 = [(0, 0), (10, 10), (5, 15), (-5, 5)]
        angle2 = qplace.get_longest_edge_angle(poly2)
        self.assertAlmostEqual(angle2, 45.0)

    def test_tiled_placement_transforms(self):
        src_poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        dst_poly = [(0, 0), (30, 0), (30, 10), (0, 10)]
        map_pt_list, matrix_str_list = qplace.calculate_tiled_placement_transforms(
            src_poly, dst_poly, sizing_mode="tile_stretch", rotation=0.0, flip="none", auto_align=False
        )
        self.assertEqual(len(map_pt_list), 3)
        self.assertEqual(len(matrix_str_list), 3)

if __name__ == "__main__":
    unittest.main()
