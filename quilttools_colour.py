# quilttools_colour.py — Color Randomiser core logic, stdlib only.
# No inkex imports (fully unit-testable).

import math
import os
import re
import random

# ----------------------------------------------------------- sRGB <-> OKLCh --
def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def _linear_to_srgb(c):
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

def linear_rgb_to_oklab(r, g, b):
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1/3), v) for v in (l, m, s))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)

def oklab_to_linear_rgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)

def hex_to_oklch(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    L, a, bb = linear_rgb_to_oklab(*(_srgb_to_linear(v) for v in (r, g, b)))
    C = math.hypot(a, bb)
    hue = math.degrees(math.atan2(bb, a)) % 360
    return (L, C, hue)

def _in_gamut(rgb, eps=1e-4):
    return all(-eps <= v <= 1 + eps for v in rgb)

def oklch_to_hex(L, C, hue, gamut='reduce'):
    rad = math.radians(hue)
    def rgb_at(c):
        return oklab_to_linear_rgb(L, c * math.cos(rad), c * math.sin(rad))
    rgb = rgb_at(C)
    if gamut == 'reduce' and not _in_gamut(rgb):
        lo, hi = 0.0, C
        for _ in range(24):
            mid = (lo + hi) / 2
            if _in_gamut(rgb_at(mid)):
                lo = mid
            else:
                hi = mid
        rgb = rgb_at(lo)
    out = []
    for v in rgb:
        v = _linear_to_srgb(max(0.0, min(1.0, v)))
        out.append(max(0, min(255, round(v * 255))))
    return '#{:02X}{:02X}{:02X}'.format(*out)

def hue_delta(h1, h2):
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)

def lightness(hex_str):
    return hex_to_oklch(hex_str)[0]

def delta_L(hex_a, hex_b):
    return abs(lightness(hex_a) - lightness(hex_b))

# ------------------------------------------------------------- GPL Palette --
def load_gpl(path):
    """Loads a list of hex color strings from a GIMP/Inkscape GPL file path.
    Also searches in user and system palettes directories if path is relative."""
    candidates = []
    if os.path.isabs(path):
        candidates.append(path)
    else:
        candidates.append(path)
        candidates.append(path + ".gpl")
        for base in (
            os.path.join(os.environ.get("APPDATA", ""), "inkscape", "palettes"),
            r"C:\\Program Files\\Inkscape\\share\\inkscape\\palettes",
        ):
            candidates.append(os.path.join(base, path))
            candidates.append(os.path.join(base, path + ".gpl"))
    
    actual_path = next((c for c in candidates if os.path.isfile(c)), None)
    if not actual_path:
        raise FileNotFoundError(f"GPL Palette file not found: {path}")

    swatches = []
    with open(actual_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line.lower().startswith("gimp") or line.lower().startswith("name:") or line.lower().startswith("columns:") or line.startswith("#"):
                continue
            m = re.match(r"^(\d+)\s+(\d+)\s+(\d+)\s*(.*)$", line)
            if m:
                r, g, b = (min(255, int(v)) for v in m.groups()[:3])
                swatches.append("#%02x%02x%02x" % (r, g, b))
    return swatches

# ------------------------------------------------------- Palette Generator --
def generate_palette(n, rule, anchor_hex, tolerance, rng):
    """Generates N hex colors under harmony rules without any document context.
    tolerance parameter is expected to be degrees for hue rules, or fraction for lightness rules."""
    if anchor_hex:
        anchor_L, anchor_C, anchor_h = hex_to_oklch(anchor_hex)
    else:
        anchor_h = rng.uniform(0, 360)
        anchor_L = rng.uniform(0.35, 0.9)
        anchor_C = rng.uniform(0.04, 0.18)

    palette = []
    rule = rule.lower()

    if rule == "high_contrast":
        # Spread lightness values
        L_values = [0.35 + (0.9 - 0.35) * i / max(1, n - 1) for i in range(n)]
        for i in range(n):
            h = rng.uniform(0, 360)
            C = rng.uniform(0.04, 0.18)
            palette.append(oklch_to_hex(L_values[i], C, h))
    elif rule == "low_contrast" or rule == "preserve_value":
        # Keep lightness values close
        base_L = anchor_L
        tol_val = tolerance if tolerance <= 1.0 else tolerance / 360.0
        for _ in range(n):
            L = max(0.35, min(0.9, base_L + rng.uniform(-tol_val, tol_val)))
            h = rng.uniform(0, 360)
            C = rng.uniform(0.04, 0.18)
            palette.append(oklch_to_hex(L, C, h))
    elif rule == "analogous":
        for _ in range(n):
            h = (anchor_h + rng.uniform(-tolerance, tolerance)) % 360
            L = rng.uniform(0.35, 0.9)
            C = rng.uniform(0.04, 0.18)
            palette.append(oklch_to_hex(L, C, h))
    elif rule == "complementary":
        for _ in range(n):
            target = anchor_h if rng.choice([True, False]) else anchor_h + 180
            h = (target + rng.uniform(-tolerance, tolerance)) % 360
            L = rng.uniform(0.35, 0.9)
            C = rng.uniform(0.04, 0.18)
            palette.append(oklch_to_hex(L, C, h))
    elif rule == "triad":
        for _ in range(n):
            target = anchor_h + rng.choice([0, 120, 240])
            h = (target + rng.uniform(-tolerance, tolerance)) % 360
            L = rng.uniform(0.35, 0.9)
            C = rng.uniform(0.04, 0.18)
            palette.append(oklch_to_hex(L, C, h))
    else: # Fallback to full random
        for _ in range(n):
            L = rng.uniform(0.35, 0.9)
            C = rng.uniform(0.04, 0.18)
            h = rng.uniform(0, 360)
            palette.append(oklch_to_hex(L, C, h))

    return palette

# ------------------------------------------------------------- Random Modes --
def shuffle(colours, locked_idx, rng):
    """Shuffles the unlocked slot colors among themselves.
    Enforces non-identity permutation when possible."""
    new_colours = list(colours)
    unlocked_indices = [i for i in range(len(colours)) if i not in locked_idx]
    if len(unlocked_indices) < 2:
        return new_colours

    original_unlocked = [colours[i] for i in unlocked_indices]
    
    # Bounded retry to avoid identity permutation if there are different colors
    has_different = len(set(original_unlocked)) > 1
    shuffled = list(original_unlocked)
    for _ in range(100):
        rng.shuffle(shuffled)
        if not has_different or shuffled != original_unlocked:
            break

    for idx, orig_pos in enumerate(unlocked_indices):
        new_colours[orig_pos] = shuffled[idx]
    return new_colours

def from_palette(colours, palette, locked_idx, rng):
    """Draws colors from the palette to assign to unlocked slots.
    Returns (new_colours, has_repeats)."""
    new_colours = list(colours)
    unlocked_indices = [i for i in range(len(colours)) if i not in locked_idx]
    if not unlocked_indices or not palette:
        return new_colours, False

    num_unlocked = len(unlocked_indices)
    has_repeats = False

    if len(palette) >= num_unlocked:
        drawn = rng.sample(palette, num_unlocked)
    else:
        drawn = list(palette)
        has_repeats = True
        while len(drawn) < num_unlocked:
            drawn.append(rng.choice(palette))
        rng.shuffle(drawn)

    for idx, orig_pos in enumerate(unlocked_indices):
        new_colours[orig_pos] = drawn[idx]
    return new_colours, has_repeats

def full_random(colours, locked_idx, rng):
    """Generates uniform random OKLCh colors for unlocked slots."""
    new_colours = list(colours)
    for i in range(len(colours)):
        if i not in locked_idx:
            L = rng.uniform(0.35, 0.9)
            C = rng.uniform(0.04, 0.18)
            h = rng.uniform(0, 360)
            new_colours[i] = oklch_to_hex(L, C, h)
    return new_colours

def augmented(colours, locked_idx, rng, rule, tolerance, anchor_hex):
    """Generates colors using harmony rules relative to an anchor color or seed.
    Locked slots act as constraint inputs if anchor is not specified."""
    new_colours = list(colours)
    unlocked_indices = [i for i in range(len(colours)) if i not in locked_idx]
    if not unlocked_indices:
        return new_colours

    # Determine anchor hue
    if anchor_hex:
        _, _, anchor_h = hex_to_oklch(anchor_hex)
        anchor_L = hex_to_oklch(anchor_hex)[0]
    elif locked_idx:
        # Use first locked slot as the anchor
        first_locked = list(locked_idx)[0]
        anchor_L, _, anchor_h = hex_to_oklch(colours[first_locked])
    else:
        anchor_h = rng.uniform(0, 360)
        anchor_L = rng.uniform(0.35, 0.9)

    rule = rule.lower()

    if rule == "high_contrast":
        # Optimization: generate 100 sets of L-values and pick the one with max min-distance
        best_set = []
        best_score = -1.0
        
        locked_Ls = [hex_to_oklch(colours[i])[0] for i in locked_idx]
        
        for _ in range(100):
            candidate_Ls = [rng.uniform(0.35, 0.9) for _ in range(len(unlocked_indices))]
            all_Ls = locked_Ls + candidate_Ls
            
            # Score is the minimum distance between any two L values
            all_Ls.sort()
            min_d = 1.0
            if len(all_Ls) > 1:
                min_d = min(all_Ls[j+1] - all_Ls[j] for j in range(len(all_Ls) - 1))
            else:
                min_d = 1.0
                
            if min_d > best_score:
                best_score = min_d
                best_set = candidate_Ls

        for idx, orig_pos in enumerate(unlocked_indices):
            h = rng.uniform(0, 360)
            C = rng.uniform(0.04, 0.18)
            new_colours[orig_pos] = oklch_to_hex(best_set[idx], C, h)

    elif rule == "low_contrast":
        # Keep L values close
        tol_val = tolerance if tolerance <= 1.0 else tolerance / 360.0
        base_L = anchor_L
        for idx in unlocked_indices:
            L = max(0.35, min(0.9, base_L + rng.uniform(-tol_val, tol_val)))
            h = rng.uniform(0, 360)
            C = rng.uniform(0.04, 0.18)
            new_colours[idx] = oklch_to_hex(L, C, h)

    elif rule == "preserve_value":
        tol_val = tolerance if tolerance <= 1.0 else tolerance / 360.0
        for idx in unlocked_indices:
            orig_L, _, _ = hex_to_oklch(colours[idx])
            L = max(0.35, min(0.9, orig_L + rng.uniform(-tol_val, tol_val)))
            h = rng.uniform(0, 360)
            C = rng.uniform(0.04, 0.18)
            new_colours[idx] = oklch_to_hex(L, C, h)

    elif rule == "analogous":
        for idx in unlocked_indices:
            h = (anchor_h + rng.uniform(-tolerance, tolerance)) % 360
            L = rng.uniform(0.35, 0.9)
            C = rng.uniform(0.04, 0.18)
            new_colours[idx] = oklch_to_hex(L, C, h)

    elif rule == "complementary":
        for idx in unlocked_indices:
            target = anchor_h if rng.choice([True, False]) else anchor_h + 180
            h = (target + rng.uniform(-tolerance, tolerance)) % 360
            L = rng.uniform(0.35, 0.9)
            C = rng.uniform(0.04, 0.18)
            new_colours[idx] = oklch_to_hex(L, C, h)

    elif rule == "triad":
        for idx in unlocked_indices:
            target = anchor_h + rng.choice([0, 120, 240])
            h = (target + rng.uniform(-tolerance, tolerance)) % 360
            L = rng.uniform(0.35, 0.9)
            C = rng.uniform(0.04, 0.18)
            new_colours[idx] = oklch_to_hex(L, C, h)

    return new_colours

# ------------------------------------------------------- Second Level Jitter --
def jitter(base_hex, amount, rng):
    """Jitters the lightness (L) and slightly chroma (C) of a base color while keeping hue constant."""
    L, C, h = hex_to_oklch(base_hex)
    L_new = max(0.0, min(1.0, L + rng.uniform(-amount, amount)))
    # Vary chroma slightly (20% of L variation) to prevent flat color clusters
    C_new = max(0.0, min(0.3, C + rng.uniform(-amount * 0.2, amount * 0.2)))
    return oklch_to_hex(L_new, C_new, h)

# ------------------------------------------------------------ Canvas context --
# Colour tools live in their own menu (Quilt Tools Colour) and serve BOTH
# block drafting and quilt layouts, so every tool must state clearly which
# context it found and how to reach the one it needs. Pure lxml/stdlib -
# no inkex import - so this module stays unit-testable anywhere.

SVG_NS = "http://www.w3.org/2000/svg"
BLOCK_DATA_TAG_ID = "fpp-tree-data-quilttools"
QUILT_DATA_TAG_ID = "quilt-data-quilttools"

CONTEXT_HELP = {
    "need_block": (
        "This action works on a BLOCK (it edits the block's saved colours). "
        "No Quilt Tools block was found on this canvas.\n"
        "- On a quilt layout, open the source block file from the Block "
        "Library instead, or use a Blocks & Quilts tool (Fabric Palette / "
        "Colour Randomiser) which recolours placed quilt cells directly.\n"
        "- To start a block: Quilt Tools Block > 01. New Block."
    ),
    "need_quilt": (
        "This action works on a QUILT LAYOUT. None was found on this "
        "canvas.\n- Create one first: Quilt Tools Pattern > 01. New Quilt, "
        "then place blocks with 02. Fill Blocks from Library."
    ),
    "need_any": (
        "Nothing to colour here: no Quilt Tools block or quilt layout was "
        "found on this canvas.\n- Start a block: Quilt Tools Block > 01. "
        "New Block, or a quilt: Quilt Tools Pattern > 01. New Quilt."
    ),
}


def _find_group_with_desc(svg_root, desc_id):
    for desc in svg_root.iter("{%s}desc" % SVG_NS):
        if desc.get("id") == desc_id and (desc.text or "").strip():
            parent = desc.getparent()
            if parent is not None:
                return parent
    return None


def detect_context(svg_root):
    """Classify the canvas for colour tools.

    Returns {"kind": "block"|"quilt"|"both"|"none",
             "block_g": <g or None>, "quilt_g": <g or None>}.
    kind == "both" means a quilt layout AND a standalone block coexist -
    tools should say which one they acted on (quilt tools usually prefer
    the quilt; block-only tools use the block)."""
    block_g = _find_group_with_desc(svg_root, BLOCK_DATA_TAG_ID)
    quilt_g = _find_group_with_desc(svg_root, QUILT_DATA_TAG_ID)
    # A block INSIDE a placed quilt cell is part of the quilt's artwork,
    # not a standalone editable block: ignore block groups nested in the
    # quilt layer.
    if block_g is not None and quilt_g is not None:
        anc = block_g.getparent()
        inside_quilt = False
        while anc is not None:
            if anc is quilt_g:
                inside_quilt = True
                break
            anc = anc.getparent()
        if inside_quilt:
            block_g = None
    if block_g is not None and quilt_g is not None:
        kind = "both"
    elif block_g is not None:
        kind = "block"
    elif quilt_g is not None:
        kind = "quilt"
    else:
        kind = "none"
    return {"kind": kind, "block_g": block_g, "quilt_g": quilt_g}


def context_note(ctx, acted_on):
    """Standard one-line suffix for completion messages, e.g.
    'Acted on: the BLOCK on this canvas.' Tools pass acted_on as
    'block' or 'quilt'."""
    where = "the standalone BLOCK" if acted_on == "block" else \
        "the QUILT layout"
    extra = ""
    if ctx["kind"] == "both":
        other = "quilt layout" if acted_on == "block" else "standalone block"
        extra = (" (this canvas also holds a %s, which was NOT changed)"
                 % other)
    return "Acted on: %s%s." % (where, extra)
