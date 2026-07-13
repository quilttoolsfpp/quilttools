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

if __name__ == "__main__":
    unittest.main()
