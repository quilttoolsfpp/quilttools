import os
import sys
import unittest

# Add current directory to path
sys.path.insert(0, os.path.abspath("."))

import quilttools_fabric_calculator as fc
import quilttools_metadata_blocks as mb
import quilttools_pattern_template as pt
import quilttools_technique_library as tl

class TestConsumerPlugins(unittest.TestCase):
    def test_fabric_calculator_args(self):
        plugin = fc.FabricCalculatorPlugin()
        class DummyParser:
            def add_argument(self, *args, **kwargs):
                pass
        # Should not raise any exception
        plugin.add_arguments(DummyParser())
        self.assertIsNotNone(plugin)

    def test_fabric_calculator_effect_block(self):
        plugin = fc.FabricCalculatorPlugin()
        class DummyOptions:
            def __init__(self):
                self.calc_mode = "fpp"
                self.cutting_math = "techniques"
                self.share_techniques = True
                self.usable_wof = 41.0
                self.theme_override = ""
                self.manual_input = ""
        plugin.options = DummyOptions()

        import lxml.etree as etree
        import quilttools_fpp_core as core
        import inkex
        import unittest.mock as mock

        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="100", height="100")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        plugin.svg.get_current_layer = lambda: svg_root

        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        tree = core.RegionTree(poly)
        block_data = core.BlockData(tree)
        desc = etree.SubElement(svg_root, "{http://www.w3.org/2000/svg}desc", id=core.FPP_DATA_TAG_ID)
        desc.text = block_data.to_json()

        with mock.patch("inkex.utils.debug") as mock_debug:
            plugin.effect()
            self.assertTrue(mock_debug.called)

        table_g = svg_root.find(".//{http://www.w3.org/2000/svg}g")
        self.assertIsNotNone(table_g)

    def test_fabric_calculator_effect_manual(self):
        plugin = fc.FabricCalculatorPlugin()
        class DummyOptions:
            def __init__(self):
                self.calc_mode = "manual"
                self.cutting_math = "techniques"
                self.share_techniques = True
                self.usable_wof = 41.0
                self.theme_override = ""
                self.manual_input = "2.5,4.0; 2.5,4.0"
        plugin.options = DummyOptions()

        import lxml.etree as etree
        import inkex
        import unittest.mock as mock

        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="100", height="100")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        plugin.svg.get_current_layer = lambda: svg_root

        with mock.patch("inkex.utils.debug") as mock_debug:
            plugin.effect()
            self.assertTrue(mock_debug.called)

        table_g = svg_root.find(".//{http://www.w3.org/2000/svg}g")
        self.assertIsNotNone(table_g)

    def test_fabric_calculator_effect_quilt(self):
        plugin = fc.FabricCalculatorPlugin()
        class DummyOptions:
            def __init__(self):
                self.calc_mode = "fpp"
                self.cutting_math = "techniques"
                self.share_techniques = True
                self.usable_wof = 41.0
                self.theme_override = ""
                self.manual_input = ""
        plugin.options = DummyOptions()

        import lxml.etree as etree
        import inkex
        import quilttools_quilt_core as qcore
        import quilttools_theme as qtheme
        import unittest.mock as mock

        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="500", height="500")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        plugin.svg.get_current_layer = lambda: svg_root

        theme = qtheme.resolve_active_theme(plugin.options)
        quilt_data = qcore.QuiltData()
        quilt_data.grid = {"rows": 1, "cols": 1, "cell_w_in": 10.0, "cell_h_in": 10.0}
        quilt_data.sashing = {"width_in": 1.0, "cornerstones": False, "color_ref": ""}
        quilt_data.borders = []
        quilt_data.binding = {"width_in": 0.25, "color_ref": ""}

        g_quilt = qcore.build_quilt_layer(quilt_data, theme)
        svg_root.append(g_quilt)

        with mock.patch("inkex.utils.debug") as mock_debug:
            plugin.effect()
            self.assertTrue(mock_debug.called)

        table_g = None
        for g in svg_root.findall(".//{http://www.w3.org/2000/svg}g"):
            if g.get("id") != "quilttools-quilt-layer" and g.find(".//{http://www.w3.org/2000/svg}text") is not None:
                table_g = g
                break
        self.assertIsNotNone(table_g)

    def test_metadata_blocks_args(self):
        plugin = mb.MetadataBlocksPlugin()
        class DummyParser:
            def add_argument(self, *args, **kwargs):
                pass
        plugin.add_arguments(DummyParser())
        self.assertIsNotNone(plugin)

    def test_pattern_template_args(self):
        plugin = pt.PatternTemplatePlugin()
        class DummyParser:
            def add_argument(self, *args, **kwargs):
                pass
        plugin.add_arguments(DummyParser())
        self.assertIsNotNone(plugin)

    def test_technique_library_args(self):
        plugin = tl.TechniqueLibraryPlugin()
        class DummyParser:
            def add_argument(self, *args, **kwargs):
                pass
        plugin.add_arguments(DummyParser())
        self.assertIsNotNone(plugin)

    def test_export_plugin_args(self):
        import quilttools_fpp_export as xp
        plugin = xp.ExportPlugin()
        class DummyParser:
            def add_argument(self, *args, **kwargs):
                pass
        plugin.add_arguments(DummyParser())
        self.assertIsNotNone(plugin)

    def test_export_plugin_stitch_flip_extension(self):
        import quilttools_fpp_export as xp
        import lxml.etree as etree
        import inkex
        import quilttools_fpp_core as core
        
        plugin = xp.ExportPlugin()
        class DummyOptions:
            def __init__(self):
                self.export_type = "template"
                self.page_size = "letter"
                self.orientation = "portrait"
                self.margin_in = 0.5
                self.sa_in = 0.25
                self.block_name = "Test"
                self.designer_name = ""
                self.copyright_notice = ""
                self.template_copies = 1
                self.template_color_mode = "full"
                self.show_section_labels = True
                self.cutting_math = "techniques"
                self.template_dedupe = "unique"
                self.mirror_templates = False
                self.squares_cutting_list_only = False
                
        plugin.options = DummyOptions()
        
        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="500", height="500")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        
        tree = core.RegionTree()
        r_root = core.Region([(0,0), (100,0), (100,100), (0,100)])
        tree.regions[r_root.id] = r_root
        tree.root_id = r_root.id
        
        r1 = core.Region([(0,0), (100,0), (100,80), (80,100), (0,100)], label="A1")
        r2 = core.Region([(100,80), (100,100), (80,100)], label="A2")
        r1.id = 1
        r2.id = 2
        tree.regions[1] = r1
        tree.regions[2] = r2
        r_root.children = [1, 2]
        r1.parent_id = r_root.id
        r2.parent_id = r_root.id
        
        prefs = {
            "piece_meta": {
                "2": {
                    "technique": "stitch_flip",
                    "sf_bases": [1]
                }
            }
        }
        block_data = core.BlockData(tree, prefs)
        
        g = etree.SubElement(svg_root, "{http://www.w3.org/2000/svg}g", id="qt-fpp-block")
        desc = etree.SubElement(g, "{http://www.w3.org/2000/svg}desc", id=core.FPP_DATA_TAG_ID)
        desc.text = block_data.to_json()
        etree.SubElement(g, "{http://www.w3.org/2000/svg}path", **{core.FPP_REGION_ATTR: "1", "style": "fill:#ffffff"})
        etree.SubElement(g, "{http://www.w3.org/2000/svg}path", **{core.FPP_REGION_ATTR: "2", "style": "fill:#ff0000"})
        
        _, _, processed = plugin._get_processed_sections(finished_size_in=10.0, allow_rotate=True)
        self.assertIsNotNone(processed)
        
        a1_item = None
        for item in processed:
            if item["prefix"] == "A1":
                a1_item = item
                break
        self.assertIsNotNone(a1_item)
        self.assertEqual(len(a1_item["regions"][0]["polygon"]), 4)
        
        a2_item = None
        for item in processed:
            if item["prefix"] == "A2":
                a2_item = item
                break
        self.assertIsNone(a2_item)

    def test_new_block_plugin_selection_path(self):
        import quilttools_fpp_new_block as nb
        import lxml.etree as etree
        import inkex
        import unittest.mock as mock
        
        plugin = nb.NewBlockPlugin()
        class DummyOptions:
            def __init__(self):
                self.use_selection_path = True
                self.use_page_size = False
                self.resize_page = True
                self.scale_mode = "none"
                self.grid_rows = 1
                self.grid_cols = 1
                
        plugin.options = DummyOptions()
        
        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="500", height="500")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        
        layer = etree.SubElement(svg_root, "{http://www.w3.org/2000/svg}g", id="layer1")
        plugin.svg.get_current_layer = lambda: layer
        
        path_el = etree.SubElement(layer, "{http://www.w3.org/2000/svg}path", id="path1")
        path_el.set("d", "M 10,10 C 20,20 30,20 40,10 L 40,40 L 10,40 Z")
        plugin.svg.selection = {"path1": path_el}
        
        with mock.patch("inkex.utils.debug") as mock_debug:
            plugin.effect()
            self.assertTrue(mock_debug.called)
            
        g_block = layer.find(".//{http://www.w3.org/2000/svg}g[@id='fpp-quilttools-layer']")
        self.assertIsNotNone(g_block)
        self.assertIsNone(layer.find(".//{http://www.w3.org/2000/svg}path[@id='path1']"))

    def test_load_basic_library_shapes(self):
        import quilttools_fpp_core as core
        import lxml.etree as etree
        
        tri_doc = etree.parse(r"C:\Users\Pritt\AppData\Roaming\inkscape\extensions\quilttoolsv2.0\BlockLibrary\Basics\Triangle.svg")
        desc = tri_doc.find(".//{http://www.w3.org/2000/svg}desc[@id='fpp-tree-data-quilttools']")
        self.assertIsNotNone(desc)
        block_data = core.BlockData.from_json(desc.text)
        self.assertEqual(len(block_data.tree.leaf_regions()), 1)
        self.assertEqual(block_data.tree.leaf_regions()[0].label, "A1")
        
        hex_doc = etree.parse(r"C:\Users\Pritt\AppData\Roaming\inkscape\extensions\quilttoolsv2.0\BlockLibrary\Basics\Hexagon.svg")
        desc = hex_doc.find(".//{http://www.w3.org/2000/svg}desc[@id='fpp-tree-data-quilttools']")
        self.assertIsNotNone(desc)
        block_data = core.BlockData.from_json(desc.text)
        self.assertEqual(len(block_data.tree.leaf_regions()), 1)
        self.assertEqual(block_data.tree.leaf_regions()[0].label, "A1")

    def test_import_svg_block_plugin(self):
        import quilttools_fpp_import_svg as imp
        import lxml.etree as etree
        import inkex
        import unittest.mock as mock
        
        plugin = imp.ImportSVGBlockPlugin()
        class DummyOptions:
            def __init__(self):
                self.svg_file = r"C:\Users\Pritt\AppData\Roaming\inkscape\extensions\quilttoolsv2.0\import tests\1025-5.svg"
                self.resize_page = True
                
        plugin.options = DummyOptions()
        
        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="500", height="500")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        
        layer = etree.SubElement(svg_root, "{http://www.w3.org/2000/svg}g", id="layer1")
        plugin.svg.get_current_layer = lambda: layer
        
        with mock.patch("inkex.utils.debug") as mock_debug, \
             mock.patch("inkex.errormsg") as mock_error:
            plugin.effect()
            self.assertTrue(mock_debug.called)
            
        g_block = layer.find(".//{http://www.w3.org/2000/svg}g[@id='fpp-quilttools-layer']")
        self.assertIsNotNone(g_block)
        
        desc = g_block.find(".//{http://www.w3.org/2000/svg}desc[@id='fpp-tree-data-quilttools']")
        self.assertIsNotNone(desc)

    def test_shape_cut_y_seams(self):
        import quilttools_fpp_shape_cut as sc
        import lxml.etree as etree
        import inkex
        import quilttools_fpp_core as core
        import unittest.mock as mock
        
        plugin = sc.ShapeCutPlugin()
        class DummyOptions:
            def __init__(self):
                self.action = "shape_cut"
                self.min_piece_area = 0.25
                self.subdivisions = 4
                self.allow_y_seams = False
                
        plugin.options = DummyOptions()
        
        svg_root = etree.Element("{http://www.w3.org/2000/svg}svg", width="500", height="500")
        plugin.svg = inkex.SvgDocumentElement(svg_root)
        
        tree = core.RegionTree([(0,0), (100,0), (100,100), (0,100)])
        block_data = core.BlockData(tree)
        
        def mock_multi_path_cut(points, man_id):
            tree.regions.clear()
            r_root = core.Region([(0,0), (100,0), (100,100), (0,100)])
            tree.regions[r_root.id] = r_root
            tree.root_id = r_root.id
            
            r1 = core.Region([(0,0), (100,0), (50,50)], label="A1")
            r2 = core.Region([(0,0), (50,50), (50,100), (0,100)], label="A2")
            r3 = core.Region([(100,0), (100,100), (50,100), (50,50)], label="A3")
            
            r1.parent_id = r_root.id
            r2.parent_id = r_root.id
            r3.parent_id = r_root.id
            r_root.children = [r1.id, r2.id, r3.id]
            
            tree.regions[r1.id] = r1
            tree.regions[r2.id] = r2
            tree.regions[r3.id] = r3
            return 1
            
        tree.multi_path_cut = mock_multi_path_cut
        
        g = etree.SubElement(svg_root, "{http://www.w3.org/2000/svg}g", id="fpp-quilttools-layer")
        desc = etree.SubElement(g, "{http://www.w3.org/2000/svg}desc", id=core.FPP_DATA_TAG_ID)
        desc.text = block_data.to_json()
        
        path_el = etree.SubElement(g, "{http://www.w3.org/2000/svg}path", id="guide_path")
        path_el.set("d", "M 0,50 L 100,50")
        plugin.svg.selection = {"guide_path": path_el}
        
        with mock.patch("inkex.errormsg") as mock_error, \
             mock.patch("quilttools_fpp_core.find_fpp_group", return_value=(g, block_data)):
            plugin.effect()
            self.assertTrue(mock_error.called)
            desc_after = g.find(f"{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
            bd_after = core.BlockData.from_json(desc_after.text)
            self.assertEqual(len(bd_after.tree.leaf_regions()), 1)
            
        plugin.options.allow_y_seams = True
        with mock.patch("inkex.utils.debug") as mock_debug, \
             mock.patch("quilttools_fpp_core.find_fpp_group", return_value=(g, block_data)):
            plugin.effect()
            self.assertTrue(mock_debug.called)
            desc_after = g.find(f"{{{core.SVG_NS}}}desc[@id='{core.FPP_DATA_TAG_ID}']")
            bd_after = core.BlockData.from_json(desc_after.text)
            self.assertEqual(len(bd_after.tree.leaf_regions()), 3)
            meta = bd_after.piece_meta()
            y_seam_tagged = [rid for rid, m in meta.items() if m.get("technique") == "y_seam"]
            self.assertTrue(len(y_seam_tagged) > 0)

    def test_block_kinds_fabric_calculations(self):
        import quilttools_fpp_fabric as fabric
        import quilttools_fpp_core as core
        
        # 1. Test Pieced Block Kind
        tree = core.RegionTree([(0,0), (10,0), (10,10), (0,10)])
        block_data = core.BlockData(tree)
        block_data.prefs["block_kind"] = "pieced"
        
        pieces, colors = fabric.pieces_from_block(block_data, 10.0)
        self.assertEqual(len(pieces), 1)
        self.assertTrue(pieces[0]["meta"].get("is_pieced"))
        
        # 2. Test Applique Block Kind
        block_data.prefs["block_kind"] = "applique"
        block_data.prefs["bg_color"] = "#00ff00"
        
        pieces_app, colors_app = fabric.pieces_from_block(block_data, 10.0)
        self.assertEqual(len(pieces_app), 2) # Background + Leaf region
        
        bg_piece = next(p for p in pieces_app if p["id"] == "bg")
        self.assertEqual(bg_piece["label"], "BG")
        self.assertEqual(bg_piece["fabric"], "#00ff00")
        self.assertTrue(bg_piece["meta"].get("is_bg"))
        
        leaf_piece = next(p for p in pieces_app if p["id"] != "bg")
        self.assertTrue(leaf_piece["meta"].get("is_applique"))
        
        # 3. Test fabric_estimate with metadata padding rules
        fpp_piece = ([(0,0), (5,0), (5,5), (0,5)], "#ff0000", {})
        app_piece = ([(0,0), (5,0), (5,5), (0,5)], "#00ff00", {"is_applique": True})
        
        estimates = fabric.fabric_estimate([fpp_piece, app_piece], usable_wof=40.0)
        self.assertIn("#ff0000", estimates)
        self.assertIn("#00ff00", estimates)
        
        self.assertGreater(estimates["#ff0000"]["fixed_in"], estimates["#00ff00"]["fixed_in"])

        # 4. Test applique base extensions (layering)
        import quilttools_cutplan as cutplan
        pieces = [
            {"id": "A1", "label": "A1", "polygon": [(0,0), (5,0), (5,5), (0,5)], "fabric": "#000", "meta": {}},
            {"id": "C1", "label": "C1", "polygon": [(5,0), (10,0), (10,5), (5,5)], "fabric": "#fff", "meta": {"technique": "applique", "app_bases": ["A1"]}}
        ]
        overrides = cutplan.resolve_appliques(pieces)
        self.assertIn("A1", overrides)
        extended_poly = overrides["A1"]
        xs = [p[0] for p in extended_poly]
        self.assertEqual(min(xs), 0)
        self.assertEqual(max(xs), 10)

if __name__ == "__main__":
    unittest.main()
