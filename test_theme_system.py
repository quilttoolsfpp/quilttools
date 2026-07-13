import os
import unittest
import json
import quilttools_theme as qtheme

class TestThemeSystem(unittest.TestCase):
    def setUp(self):
        # Backup existing prefs if any
        self.prefs_backup = None
        if os.path.exists(qtheme.PREFS_FILE):
            try:
                with open(qtheme.PREFS_FILE, "r", encoding="utf-8") as f:
                    self.prefs_backup = f.read()
            except Exception:
                pass

    def tearDown(self):
        # Restore backup or clean up
        if self.prefs_backup is not None:
            try:
                with open(qtheme.PREFS_FILE, "w", encoding="utf-8") as f:
                    f.write(self.prefs_backup)
            except Exception:
                pass
        elif os.path.exists(qtheme.PREFS_FILE):
            os.remove(qtheme.PREFS_FILE)

    def test_discover_themes(self):
        themes = qtheme.discover_themes()
        self.assertIn("ifh", themes)
        self.assertIn("childrens_moments", themes)
        self.assertEqual(themes["ifh"]["name"], "In Familiar Hands")
        self.assertEqual(themes["childrens_moments"]["name"], "Children's Moments")

    def test_load_and_merge_theme(self):
        # Load childrens_moments and verify details
        theme = qtheme.load_theme("childrens_moments")
        
        # Verify custom font Nunito is loaded
        self.assertEqual(theme.font("body")["family"], "Nunito")
        
        # Verify fallback page size (A4) is inherited from ifh since it's not defined in childrens_moments
        self.assertEqual(theme["page"]["size"], "A4")

    def test_safe_accessors(self):
        theme = qtheme.load_theme("ifh")
        
        # Check fonts
        self.assertEqual(theme.font("heading")["family"], "Fraunces")
        self.assertEqual(theme.font("heading")["weight"], "600")
        
        # Check missing font fallback
        self.assertEqual(theme.font("missing_key")["family"], "sans-serif")
        
        # Check colors
        self.assertEqual(theme.colour("primary"), "#243B53")
        self.assertEqual(theme.color("primary"), "#243B53") # color alias
        self.assertEqual(theme.colour("missing_color"), "#000000") # fallback
        
        # Check type scale
        self.assertEqual(theme.type_pt("title"), 28)
        self.assertEqual(theme.type_pt("missing_size"), 10) # fallback

    def test_preferences_io(self):
        test_prefs = {"theme": "custom", "custom_theme": "my_test_theme"}
        qtheme.set_prefs(test_prefs)
        
        loaded = qtheme.get_prefs()
        self.assertEqual(loaded.get("theme"), "custom")
        self.assertEqual(loaded.get("custom_theme"), "my_test_theme")

    def test_resolve_active_theme(self):
        # 1. Test priority: explicit override
        class DummyOptions:
            theme_override = "childrens_moments"
            
        theme = qtheme.resolve_active_theme(DummyOptions())
        self.assertEqual(theme.font("body")["family"], "Nunito")
        
        # 2. Test priority: saved preference
        qtheme.set_prefs({"theme": "childrens_moments"})
        class EmptyOptions:
            theme_override = ""
        theme = qtheme.resolve_active_theme(EmptyOptions())
        self.assertEqual(theme.font("body")["family"], "Nunito")

        # 3. Test priority: fallback to ifh
        qtheme.set_prefs({})
        theme = qtheme.resolve_active_theme(EmptyOptions())
        self.assertEqual(theme.font("body")["family"], "Fraunces")

if __name__ == "__main__":
    unittest.main()
