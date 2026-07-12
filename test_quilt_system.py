import unittest
import json
import xml.etree.ElementTree as ET

# Add repository path to python path
import sys
sys.path.insert(0, ".")

import quilttools_quilt_core as qcore
import quilttools_theme as qtheme
import quilttools_fpp_core as core

class MockTheme:
    def font(self, name):
        return {"family": "sans-serif", "weight": "normal", "style": "normal"}
    def colour(self, name):
        return "#333333"

class TestQuiltSystem(unittest.TestCase):
    def test_quilt_data_serialization(self):
        spec = {
            "name": "My Testing Quilt",
            "setting": "straight",
            "grid": {"rows": 3, "cols": 4, "cell_w_in": 10.0, "cell_h_in": 12.0},
            "sashing": {"width_in": 1.5, "cornerstones": True, "color_ref": "sashing"},
            "borders": [{"width_in": 3.0, "color_ref": "b1"}, {"width_in": 1.0, "color_ref": "b2"}],
            "binding": {"width_in": 0.5, "color_ref": "binding"}
        }
        
        qd = qcore.QuiltData(spec)
        self.assertEqual(qd.name, "My Testing Quilt")
        self.assertEqual(qd.grid["rows"], 3)
        self.assertEqual(qd.borders[1]["width_in"], 1.0)
        
        json_str = qd.to_json()
        qd2 = qcore.QuiltData.from_json(json_str)
        self.assertEqual(qd2.name, "My Testing Quilt")
        self.assertEqual(qd2.grid["rows"], 3)
        self.assertEqual(qd2.borders[1]["width_in"], 1.0)

    def test_build_quilt_layer(self):
        spec = {
            "name": "Test Layer Quilt",
            "setting": "straight",
            "grid": {"rows": 2, "cols": 3, "cell_w_in": 10.0, "cell_h_in": 10.0},
            "sashing": {"width_in": 1.0, "cornerstones": True, "color_ref": "sashing"},
            "borders": [{"width_in": 2.0, "color_ref": "b1"}],
            "binding": {"width_in": 0.25, "color_ref": "binding"}
        }
        
        qd = qcore.QuiltData(spec)
        theme = MockTheme()
        
        g = qcore.build_quilt_layer(qd, theme)
        self.assertIsNotNone(g)
        self.assertEqual(g.tag, "{http://www.w3.org/2000/svg}g")
        
        # Grid width = 3 * 10" + 2 * 1" = 32" (3072px)
        # Grid height = 2 * 10" + 1 * 1" = 21" (2016px)
        # Total border width (each side) = 2" + 0.25" = 2.25"
        # Total width = 32" + 2 * 2.25" = 36.5" (3504px)
        # Total height = 21" + 2 * 2.25" = 25.5" (2448px)
        self.assertAlmostEqual(qd.finished_width_in, 36.5)
        self.assertAlmostEqual(qd.finished_height_in, 25.5)
        
        # Verify cell subgroups
        # Blocks: 2 * 3 = 6 cells
        # Sashing: (rows-1)*cols = 1*3 = 3 horizontal, rows*(cols-1) = 2*2 = 4 vertical
        # Cornerstones: (rows-1)*(cols-1) = 1*2 = 2
        # Borders: 4 cells per layer (1 layer) = 4
        # Binding: 4 cells
        # Total cells registered: 6 + 3 + 4 + 2 + 4 + 4 = 23
        self.assertEqual(len(qd.cells), 23)
        
        for cell_id, info in qd.cells.items():
            sub_g = g.find(f".//{{http://www.w3.org/2000/svg}}g[@id='{cell_id}']")
            self.assertIsNotNone(sub_g, f"Could not find group for {cell_id}")
            self.assertEqual(sub_g.get("data-quilt-role"), info["role"])
            self.assertEqual(sub_g.get("data-quilt-state"), info["state"])
            
            poly = sub_g.find("{http://www.w3.org/2000/svg}polygon")
            self.assertIsNotNone(poly, f"Could not find polygon for {cell_id}")
            self.assertTrue(poly.get("points"))

if __name__ == "__main__":
    unittest.main()
