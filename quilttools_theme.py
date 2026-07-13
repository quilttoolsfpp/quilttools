import os
import json
import glob
import sys

THEMES_DIR = os.path.join(os.path.dirname(__file__), "themes")
PREFS_FILE = os.path.join(os.path.dirname(__file__), "quilttools_pattern_prefs.json")

class Theme(dict):
    """
    Theme class representing a parsed theme configuration.
    Inherits from dict to ensure 100% backward compatibility with plugins
    using dict style access, while adding safe accessors.
    """
    def font(self, key):
        """Safe accessor for a font dictionary. Returns a fallback if missing."""
        fonts = self.get("fonts", {})
        f = fonts.get(key)
        if isinstance(f, dict):
            return f
        # Fallbacks
        return {"family": "sans-serif", "weight": "normal", "style": "normal"}

    def colour(self, key):
        """Safe accessor for a palette color (Australian spelling). Returns fallback if missing."""
        palette = self.get("palette", {})
        val = palette.get(key)
        if val is not None:
            return val
        # Check alias
        if key == "color":
            return palette.get("primary", "#000000")
        return "#000000"

    def color(self, key):
        """Alias for colour() accessor."""
        return self.colour(key)

    def type_pt(self, key):
        """Safe accessor for type scale size in points. Returns fallback if missing."""
        ts = self.get("type_scale_pt", {})
        return ts.get(key, 10)


def merge_dicts(base, override):
    """Recursively merges override dictionary onto base dictionary."""
    for k, v in override.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            merge_dicts(base[k], v)
        else:
            base[k] = v
    return base


def get_prefs() -> dict:
    """Reads preferences from the central JSON file."""
    if os.path.exists(PREFS_FILE):
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def set_prefs(prefs: dict):
    """Writes preferences to the central JSON file."""
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not save preferences: {e}\n")


def discover_themes() -> dict:
    """
    Globs themes/*.json and returns a dict of discovered themes:
    { theme_id: { "name": name, "description": description } }
    """
    discovered = {}
    if not os.path.exists(THEMES_DIR):
        return discovered
    
    pattern = os.path.join(THEMES_DIR, "*.json")
    for filepath in glob.glob(pattern):
        theme_id = os.path.splitext(os.path.basename(filepath))[0]
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                discovered[theme_id] = {
                    "name": data.get("name", theme_id),
                    "description": data.get("description", "")
                }
        except Exception:
            pass
    return discovered


def load_theme(theme_id: str) -> Theme:
    """
    Loads default ifh.json and merges target theme_id over it.
    Warns on unknown schema version but does not crash.
    """
    # 1. Load default IFH
    ifh_path = os.path.join(THEMES_DIR, "ifh.json")
    base_theme = {}
    if os.path.exists(ifh_path):
        try:
            with open(ifh_path, "r", encoding="utf-8") as f:
                base_theme = json.load(f)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to load default IFH theme: {e}\n")

    # 2. If loaded theme is IFH, we are done
    if theme_id == "ifh" or not theme_id:
        return Theme(base_theme)

    # 3. Load override theme
    theme_path = os.path.join(THEMES_DIR, f"{theme_id}.json")
    if not os.path.exists(theme_path):
        # Graceful fallback: return base IFH theme if override not found
        sys.stderr.write(f"Warning: Theme '{theme_id}' not found. Falling back to IFH.\n")
        return Theme(base_theme)

    try:
        with open(theme_path, "r", encoding="utf-8") as f:
            override_data = json.load(f)
            
            # Check schema version
            schema_ver = override_data.get("schema_version", 1)
            if schema_ver != 1:
                sys.stderr.write(f"Warning: Theme '{theme_id}' has unknown schema version {schema_ver}.\n")
                
            # Merge
            merged = merge_dicts(base_theme, override_data)
            return Theme(merged)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to load theme '{theme_id}': {e}. Falling back to IFH.\n")
        return Theme(base_theme)


def resolve_active_theme(options) -> Theme:
    """
    Resolves the active theme based on priority chain:
    1. theme_override in options (explicit override)
    2. saved preference in quilttools_pattern_prefs.json
    3. default 'ifh'
    """
    # 1. Check explicit override in options
    override = getattr(options, "theme_override", None)
    if override and override.strip():
        return load_theme(override.strip())

    # 2. Check saved preference
    prefs = get_prefs()
    theme_id = prefs.get("theme", "ifh")
    if theme_id == "custom":
        theme_id = prefs.get("custom_theme", "ifh")

    return load_theme(theme_id)
