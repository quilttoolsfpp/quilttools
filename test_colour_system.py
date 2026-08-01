import unittest
import random
import os
import tempfile
import quilttools_colour as qcol

class TestColourSystem(unittest.TestCase):
    def test_oklch_roundtrip(self):
        # Verify sRGB -> OKLCh -> sRGB round-trip accuracy
        rng = random.Random(42)
        worst_channel_error = 0
        for _ in range(1000):
            # Generate random hex color
            h = '#{:06X}'.format(rng.randint(0, 0xFFFFFF))
            oklch = qcol.hex_to_oklch(h)
            back = qcol.oklch_to_hex(*oklch)
            
            # Compare color channels (R, G, B)
            for i in (1, 3, 5):
                c1 = int(h[i:i+2], 16)
                c2 = int(back[i:i+2], 16)
                worst_channel_error = max(worst_channel_error, abs(c1 - c2))
        
        # Reference implementation guarantees <= 1/255 worst-channel error
        self.assertLessEqual(worst_channel_error, 1)

    def test_shuffle(self):
        rng = random.Random(123)
        colors = ["#ff0000", "#00ff00", "#0000ff", "#ffff00"]
        
        # Lock indices 0 and 2 (#ff0000 and #0000ff)
        locked = {0, 2}
        shuffled = qcol.shuffle(colors, locked, rng)
        
        # Verify locked elements did not change
        self.assertEqual(shuffled[0], colors[0])
        self.assertEqual(shuffled[2], colors[2])
        
        # Verify multiset is identical (same colors, just shuffled)
        self.assertEqual(sorted(colors), sorted(shuffled))

    def test_from_palette(self):
        rng = random.Random(456)
        colors = ["#ffffff", "#ffffff", "#ffffff", "#ffffff"]
        palette = ["#111111", "#222222", "#333333", "#444444", "#555555"]
        
        # Lock index 1
        locked = {1}
        new_cols, repeats = qcol.from_palette(colors, palette, locked, rng)
        
        # Verify locked did not change
        self.assertEqual(new_cols[1], colors[1])
        
        # Verify elements are from the palette
        for i, c in enumerate(new_cols):
            if i not in locked:
                self.assertIn(c, palette)
                
        # Verify no repeats warning since palette size (5) >= unlocked count (3)
        self.assertFalse(repeats)

        # Test palette smaller than slots (should repeat and warn)
        small_palette = ["#999999"]
        new_cols_small, repeats_small = qcol.from_palette(colors, small_palette, set(), rng)
        self.assertEqual(new_cols_small, ["#999999", "#999999", "#999999", "#999999"])
        self.assertTrue(repeats_small)

    def test_full_random(self):
        rng = random.Random(789)
        colors = ["#111111", "#222222", "#333333"]
        locked = {0}
        randomized = qcol.full_random(colors, locked, rng)
        
        self.assertEqual(randomized[0], colors[0])
        self.assertNotEqual(randomized[1], colors[1])
        self.assertNotEqual(randomized[2], colors[2])
        
        # Check that outputs are valid 6-digit hex colors
        for c in randomized:
            self.assertTrue(c.startswith("#"))
            self.assertEqual(len(c), 7)
            # Should parse as hex
            int(c[1:], 16)

    def test_augmented_preserve_value(self):
        rng = random.Random(111)
        colors = ["#ff0000", "#00ff00", "#0000ff"] # original L: ~0.627, ~0.866, ~0.452
        locked = {0}
        
        # tolerance of 0.05 lightness units
        tolerance = 0.05
        randomized = qcol.augmented(colors, locked, rng, "preserve_value", tolerance, None)
        
        self.assertEqual(randomized[0], colors[0])
        
        # Check that unlocked slots' lightness is within tolerance
        for i in (1, 2):
            orig_L, _, _ = qcol.hex_to_oklch(colors[i])
            new_L, _, _ = qcol.hex_to_oklch(randomized[i])
            self.assertLessEqual(abs(orig_L - new_L), tolerance + 1e-4)

    def test_augmented_analogous(self):
        rng = random.Random(222)
        colors = ["#ff0000", "#00ff00", "#0000ff"]
        
        # Anchor on Red (#ff0000, hue ~29.2 deg)
        anchor = "#ff0000"
        tolerance = 15.0
        
        randomized = qcol.augmented(colors, set(), rng, "analogous", tolerance, anchor)
        
        anchor_hue = qcol.hex_to_oklch(anchor)[2]
        for c in randomized:
            L, C, h = qcol.hex_to_oklch(c)
            # Hue delta must be within tolerance
            self.assertLessEqual(qcol.hue_delta(h, anchor_hue), tolerance + 1e-4)

    def test_augmented_complementary(self):
        rng = random.Random(333)
        colors = ["#ff0000", "#00ff00", "#0000ff"]
        anchor = "#ff0000" # hue ~29.2 deg
        tolerance = 15.0
        
        randomized = qcol.augmented(colors, set(), rng, "complementary", tolerance, anchor)
        
        anchor_hue = qcol.hex_to_oklch(anchor)[2]
        for c in randomized:
            L, C, h = qcol.hex_to_oklch(c)
            d1 = qcol.hue_delta(h, anchor_hue)
            d2 = qcol.hue_delta(h, anchor_hue + 180)
            self.assertTrue(d1 <= tolerance + 1e-4 or d2 <= tolerance + 1e-4)

    def test_augmented_triad(self):
        rng = random.Random(444)
        colors = ["#ff0000", "#00ff00", "#0000ff"]
        anchor = "#ff0000" # hue ~29.2 deg
        tolerance = 15.0
        
        randomized = qcol.augmented(colors, set(), rng, "triad", tolerance, anchor)
        
        anchor_hue = qcol.hex_to_oklch(anchor)[2]
        for c in randomized:
            L, C, h = qcol.hex_to_oklch(c)
            d1 = qcol.hue_delta(h, anchor_hue)
            d2 = qcol.hue_delta(h, anchor_hue + 120)
            d3 = qcol.hue_delta(h, anchor_hue + 240)
            self.assertTrue(d1 <= tolerance + 1e-4 or d2 <= tolerance + 1e-4 or d3 <= tolerance + 1e-4)

    def test_augmented_high_contrast(self):
        rng = random.Random(555)
        colors = ["#ffffff", "#ffffff", "#ffffff", "#ffffff"]
        randomized = qcol.augmented(colors, set(), rng, "high_contrast", 0, None)
        
        # Check that L values are spread out
        Ls = sorted([qcol.hex_to_oklch(c)[0] for c in randomized])
        # The minimum distance between any two L values should be relatively high
        min_d = min(Ls[i+1] - Ls[i] for i in range(len(Ls) - 1))
        self.assertGreater(min_d, 0.08)

    def test_augmented_low_contrast(self):
        rng = random.Random(666)
        colors = ["#ffffff", "#ffffff", "#ffffff", "#ffffff"]
        tolerance = 0.05
        randomized = qcol.augmented(colors, set(), rng, "low_contrast", tolerance, None)
        
        # Check that all L values are close to each other
        Ls = [qcol.hex_to_oklch(c)[0] for c in randomized]
        base_L = sum(Ls) / len(Ls)
        for L in Ls:
            self.assertLessEqual(abs(L - base_L), tolerance * 2) # bound by twice the tolerance range

    def test_seeding_determinism(self):
        # Verify same seed produces byte-identical output, different seed produces different
        colors = ["#111111", "#222222", "#333333", "#444444"]
        
        rng1 = random.Random("my-fixed-seed")
        res1 = qcol.augmented(colors, set(), rng1, "analogous", 15.0, "#ff0000")
        
        rng2 = random.Random("my-fixed-seed")
        res2 = qcol.augmented(colors, set(), rng2, "analogous", 15.0, "#ff0000")
        
        self.assertEqual(res1, res2)
        
        rng3 = random.Random("different-seed")
        res3 = qcol.augmented(colors, set(), rng3, "analogous", 15.0, "#ff0000")
        
        self.assertNotEqual(res1, res3)

    def test_jitter(self):
        rng = random.Random(777)
        base = "#00ff00"
        base_L, base_C, base_h = qcol.hex_to_oklch(base)
        
        amount = 0.1
        jittered = qcol.jitter(base, amount, rng)
        jit_L, jit_C, jit_h = qcol.hex_to_oklch(jittered)
        
        # Hue must be held constant
        self.assertAlmostEqual(jit_h, base_h, places=4)
        # Lightness variation must be within amount
        self.assertLessEqual(abs(jit_L - base_L), amount)

    def test_gpl_parser(self):
        # Create a mock GPL file
        gpl_content = """GIMP Palette
Name: MockPalette
Columns: 4
#
  0 255   0\tGreen Color
255   0   0\tRed Color
  0   0 255\tBlue Color
"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.gpl') as temp:
            temp.write(gpl_content)
            temp_path = temp.name

        try:
            parsed = qcol.load_gpl(temp_path)
            self.assertEqual(parsed, ["#00ff00", "#ff0000", "#0000ff"])
        finally:
            os.remove(temp_path)

    def test_randomizer_integration_block(self):
        import lxml.etree as etree
        import inkex
        import quilttools_fpp_core as core
        from quilttools_colour_random import ColourRandomiserPlugin
        import unittest.mock as mock

        plugin = ColourRandomiserPlugin()
        class DummyOptions:
            action = "interactive"
            scope = "quilt"
            mode = "full_random"
            palette_source = "current"
            gpl_file = ""
            rule = "analogous"
            anchor = ""
            tolerance = 15.0
            block_variation = 0.05
            seed = "block-seed"
            locked_colors = ""
        plugin.options = DummyOptions()

        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="100", height="100")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        plugin.svg.get_current_layer = lambda: svg_root

        # Build mock block data
        g = etree.SubElement(svg_root, "{http://www.w3.org/2000/svg}g", id="fpp-quilttools-layer")
        desc = etree.SubElement(g, "{http://www.w3.org/2000/svg}desc", id=core.FPP_DATA_TAG_ID)
        poly = [(0, 0), (100, 0), (100, 100), (0, 100)]
        tree = core.RegionTree(poly)
        tree.multi_guillotine_cut((50, 0), (50, 100))
        block_data = core.BlockData(tree)
        desc.text = block_data.to_json()

        # Add paths
        for r in tree.leaf_regions():
            etree.SubElement(g, "{http://www.w3.org/2000/svg}path", **{
                core.FPP_REGION_ATTR: str(r.id),
                "style": "fill:#ff0000"
            })

        with mock.patch("inkex.utils.debug") as mock_debug:
            plugin.effect()
            self.assertTrue(mock_debug.called)

        # Retrieve updated block data and path styles
        new_desc = g.find(f".//{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
        self.assertIsNotNone(new_desc)
        updated_bd = core.BlockData.from_json(new_desc.text)
        custom_colors = updated_bd.prefs.get("custom_colors", {})
        self.assertEqual(len(custom_colors), 2)
        
        # Verify they are no longer red
        self.assertNotEqual(custom_colors[str(tree.leaf_regions()[0].id)].lower(), "#ff0000")

    def test_randomizer_integration_quilt(self):
        import lxml.etree as etree
        import inkex
        import quilttools_fpp_core as core
        import quilttools_quilt_core as qcore
        import quilttools_fpp_fabric as qfabric
        from quilttools_colour_random import ColourRandomiserPlugin
        import unittest.mock as mock

        plugin = ColourRandomiserPlugin()
        class DummyOptions:
            action = "interactive"
            scope = "quilt"
            mode = "full_random"
            palette_source = "current"
            gpl_file = ""
            rule = "analogous"
            anchor = ""
            tolerance = 15.0
            block_variation = 0.05
            seed = "quilt-seed"
            locked_colors = ""
        plugin.options = DummyOptions()

        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="500", height="500")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        plugin.svg.get_current_layer = lambda: svg_root

        # Build mock quilt layout
        g_quilt = etree.SubElement(svg_root, "{http://www.w3.org/2000/svg}g", id="quilttools-quilt-layer")
        desc = etree.SubElement(g_quilt, "{http://www.w3.org/2000/svg}desc", id=qcore.QUILT_DATA_TAG_ID)
        spec = {
            "name": "Test Quilt",
            "setting": "straight",
            "grid": {"rows": 1, "cols": 1, "cell_w_in": 10.0, "cell_h_in": 10.0},
            "sashing": {"width_in": 0.0, "cornerstones": False, "color_ref": ""},
            "borders": [],
            "binding": {"width_in": 0.0, "color_ref": ""}
        }
        qd = qcore.QuiltData(spec)
        cell_id = "quilt-cell-0-0"
        qd.cells[cell_id] = {
            "role": "block",
            "state": "placed",
            "polygon": [(0, 0), (960, 0), (960, 960), (0, 960)],
            "placed_block": {
                "source": "MockBlock.svg",
                "block_kind": "fpp",
                "rotation": 0.0,
                "flip": "none",
                "sizing_mode": "stretch"
            }
        }
        desc.text = qd.to_json()

        # Mock the block template document for fabric calculations
        poly = [(0, 0), (100, 0), (100, 100), (0, 100)]
        tree = core.RegionTree(poly)
        lib_bd = core.BlockData(tree)
        root_region = list(lib_bd.tree.regions.values())[0]
        region_id_str = str(root_region.id)

        # Add placed block content to cell
        g_cell = etree.SubElement(g_quilt, "{http://www.w3.org/2000/svg}g", id=cell_id)
        g_placed = etree.SubElement(g_cell, "{http://www.w3.org/2000/svg}g", id=f"{cell_id}-placed-0")
        path = etree.SubElement(g_placed, "{http://www.w3.org/2000/svg}path", **{
            core.FPP_REGION_ATTR: region_id_str,
            "style": "fill:#00ff00"
        })

        with mock.patch("inkex.utils.debug") as mock_debug:
            plugin.effect()
            self.assertTrue(mock_debug.called)

        # Check path fill color on canvas was updated
        style = path.get("style")
        self.assertIn("fill:", style)
        self.assertNotIn("fill:#00ff00", style)

        # Extract the randomized color
        import re
        m = re.search(r"fill:\s*(#[0-9a-fA-F]{6})", style)
        self.assertIsNotNone(m)
        randomized_color = m.group(1).lower()

        # Prepare mock block SVG for parse lookup
        mock_block_svg = etree.Element("{http://www.w3.org/2000/svg}svg")
        block_desc = etree.SubElement(mock_block_svg, "{http://www.w3.org/2000/svg}desc", id=core.FPP_DATA_TAG_ID)
        block_desc.text = lib_bd.to_json()

        class MockParseResult:
            def __init__(self, root):
                self.root = root
            def getroot(self):
                return self.root

        # Run fabric calculation and verify that it picks up the randomized color
        with mock.patch("os.path.exists", return_value=True), \
             mock.patch("lxml.etree.parse", return_value=MockParseResult(mock_block_svg)):
            plan = qfabric.calculate_quilt_fabric_requirements(qd, g_quilt, 40.0, None)
            
            # The piece should have the randomized color!
            self.assertIn(randomized_color, plan["fabrics"])
            # The original color #00ff00 should NOT be in the fabrics requirements plan!
            self.assertNotIn("#00ff00", plan["fabrics"])



class TestColourContext(unittest.TestCase):
    """detect_context drives every colour tool's block/quilt guidance."""

    NS = "{http://www.w3.org/2000/svg}"

    def _svg(self):
        from lxml import etree
        return etree.Element(self.NS + "svg")

    def _add_group(self, root, desc_id, parent=None):
        from lxml import etree
        g = etree.SubElement(parent if parent is not None else root,
                             self.NS + "g")
        d = etree.SubElement(g, self.NS + "desc", id=desc_id)
        d.text = "{}"
        return g

    def test_none(self):
        ctx = qcol.detect_context(self._svg())
        self.assertEqual(ctx["kind"], "none")

    def test_block_only(self):
        root = self._svg()
        self._add_group(root, qcol.BLOCK_DATA_TAG_ID)
        self.assertEqual(qcol.detect_context(root)["kind"], "block")

    def test_quilt_only(self):
        root = self._svg()
        self._add_group(root, qcol.QUILT_DATA_TAG_ID)
        self.assertEqual(qcol.detect_context(root)["kind"], "quilt")

    def test_both(self):
        root = self._svg()
        self._add_group(root, qcol.BLOCK_DATA_TAG_ID)
        self._add_group(root, qcol.QUILT_DATA_TAG_ID)
        ctx = qcol.detect_context(root)
        self.assertEqual(ctx["kind"], "both")
        self.assertIn("NOT changed", qcol.context_note(ctx, "quilt"))

    def test_block_inside_quilt_cell_is_quilt(self):
        # A library block deep-copied into a placed quilt cell must not
        # count as an editable standalone block.
        root = self._svg()
        quilt_g = self._add_group(root, qcol.QUILT_DATA_TAG_ID)
        self._add_group(root, qcol.BLOCK_DATA_TAG_ID, parent=quilt_g)
        self.assertEqual(qcol.detect_context(root)["kind"], "quilt")

if __name__ == "__main__":
    unittest.main()
