import re
import math
import os
import json
import base64
import io
import urllib.parse
from lxml import etree
import inkex

from quilttools_geometry import *

INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SVG_NS = "http://www.w3.org/2000/svg"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
FPP_REGION_ATTR = "data-fpp-region-id"
FPP_DATA_TAG_ID = "fpp-tree-data-quilttools"

PIECE_COLORS = [
    "#d6eaf8", "#d5f5e3", "#fef9e7", "#f9ebea", "#f4ecf7",
    "#eaf4fb", "#fdfefe", "#e8f8f5", "#fdf2f8", "#e9f7ef",
    "#fef5e4", "#eaecee", "#d7bde2", "#a9cce3", "#a9dfbf"
]

SECTION_PALETTE = {
    "A": "#ffadad", "B": "#a0c4ff", "C": "#caffbf", "D": "#fdffb6",
    "E": "#bdb2ff", "F": "#ffd6a5", "G": "#ffc6ff", "H": "#9bf6ff",
    "I": "#e5e5e5", "J": "#ffb5a7", "K": "#a8dadc", "L": "#f1faee"
}
SECTION_PALETTE_LIST = list(SECTION_PALETTE.values())


def find_fpp_group(svg):
    # Avoid circular import at runtime
    from quilttools_fpp_core import BlockData
    for g in svg.findall(f".//{{{SVG_NS}}}g"):
        desc = g.find(f"{{{SVG_NS}}}desc[@id='{FPP_DATA_TAG_ID}']")
        if desc is not None and desc.text:
            return g, BlockData.from_json(desc.text)
    return None, None


def get_color_for_label(label, mode, idx):
    if mode == "section":
        match = re.search(r"^([A-Za-z]+)", label)
        if match and not match.group(0).startswith("TEMP"):
            char = match.group(0).upper()
            pal_idx = (ord(char[0]) - 65) % len(SECTION_PALETTE)
            return SECTION_PALETTE.get(char[0], SECTION_PALETTE_LIST[pal_idx])
    return PIECE_COLORS[idx % len(PIECE_COLORS)]


def build_fpp_layer(block_data):
    g = etree.Element(
        "{%s}g" % SVG_NS,
        id="fpp-quilttools-layer",
        **{
            f"{{{INKSCAPE_NS}}}label": "Quilt Tools FPP Regions",
            f"{{{INKSCAPE_NS}}}groupmode": "layer",
        },
    )
    refresh_layer(g, block_data)
    return g


def refresh_layer(g, block_data, scrape=True):
    tree, prefs = block_data.tree, block_data.prefs
    color_mode = prefs.get("color_mode", "piece")
    custom_colors = prefs.setdefault("custom_colors", {})
    
    # Check if we should scrape: either custom_colors is not empty,
    # or at least one canvas path has a color different from its default color.
    should_scrape = scrape and len(custom_colors) > 0
    if scrape and not should_scrape:
        leafs = sorted(tree.leaf_regions(), key=lambda r: r.label)
        for idx, region in enumerate(leafs):
            path = g.find(f".//{{{SVG_NS}}}path[@id='region-{region.label}']")
            if path is not None:
                color = resolve_element_fill(path)
                if color:
                    default_color = get_color_for_label(region.label, color_mode, idx)
                    if color.strip().lower() != default_color.strip().lower():
                        should_scrape = True
                        break
                        
    if should_scrape and not prefs.get("bypass_custom_colors", False):
        for path in g.findall(f".//{{{SVG_NS}}}path"):
            rid = path.get(FPP_REGION_ATTR)
            if rid:
                color = resolve_element_fill(path)
                if color:
                    custom_colors[str(rid)] = color
        # Scrape background color for applique blocks
        bg_el = g.find(f".//{{{SVG_NS}}}path[@id='qt-block-bg']")
        if bg_el is not None:
            bg_color = resolve_element_fill(bg_el)
            if bg_color:
                custom_colors["bg"] = bg_color
                prefs["bg_color"] = bg_color

    for child in list(g):
        g.remove(child)
        
    sa_px = (
        prefs.get("sa_in", 0.25) * PX_PER_INCH if prefs.get("show_sa", False) else 0.0
    )
    color_mode = prefs.get("color_mode", "piece")
    custom_colors = prefs.get("custom_colors", {}) if not prefs.get("bypass_custom_colors", False) else {}
    group_by_color = prefs.get("group_by_color", False)
    fill_opacity = prefs.get("fill_opacity", 0.80)
    
    # Render background for applique blocks
    block_kind = prefs.get("block_kind", "fpp")
    if block_kind == "applique":
        bg_color = prefs.get("bg_color", "#ffffff")
        if not prefs.get("bypass_custom_colors", False):
            bg_color = custom_colors.get("bg", bg_color)
        
        outline = tree.regions[tree.root_id].polygon
        if outline:
            bg_d = (
                "M {:.4f},{:.4f} ".format(*outline[0])
                + " ".join("L {:.4f},{:.4f}".format(*p) for p in outline[1:])
                + " Z"
            )
            etree.SubElement(
                g,
                "{%s}path" % SVG_NS,
                d=bg_d,
                id="qt-block-bg",
                style=f"fill:{bg_color};stroke:#333333;stroke-width:1.0;stroke-linejoin:round;stroke-dasharray:none;",
                **{
                    "data-fpp-ignore": "true"
                }
            )

    color_groups = {}

    for idx, region in enumerate(sorted(tree.leaf_regions(), key=lambda r: r.label)):
        fill_color = custom_colors.get(str(region.id))
        if not fill_color:
            fill_color = get_color_for_label(region.label, color_mode, idx)

        if group_by_color:
            if fill_color not in color_groups:
                clean_hex = fill_color.lstrip("#")
                color_g = etree.SubElement(
                    g,
                    "{%s}g" % SVG_NS,
                    id=f"color-group-{clean_hex}",
                    style=f"fill:{fill_color}",
                    **{
                        f"{{{INKSCAPE_NS}}}label": f"Fabric {fill_color}",
                        f"{{{INKSCAPE_NS}}}groupmode": "group",
                    }
                )
                color_groups[fill_color] = color_g
            container = color_groups[fill_color]
        else:
            container = g
        path_fill = fill_color

        if sa_px > 0:
            sa_poly = offset_polygon(region.polygon, sa_px, miter_limit=2.0)
            if sa_poly:
                sa_d = (
                    "M {:.4f},{:.4f} ".format(*sa_poly[0])
                    + " ".join("L {:.4f},{:.4f}".format(*p) for p in sa_poly[1:])
                    + " Z"
                )
                sa_attribs = {
                    "d": sa_d,
                    "id": f"sa-{region.label}",
                    "style": "fill:none;stroke:#cc0000;stroke-width:0.6;stroke-dasharray:4,2;opacity:0.7;pointer-events:none;",
                    f"{{{SODIPODI_NS}}}insensitive": "true",
                }
                etree.SubElement(container, "{%s}path" % SVG_NS, **sa_attribs)

        path_el = etree.SubElement(
            container,
            "{%s}path" % SVG_NS,
            d=region.path_d(),
            id=f"region-{region.label}",
            style=f"fill:{path_fill};fill-opacity:{fill_opacity:.2f};stroke:#222222;stroke-width:1.0;stroke-linejoin:round",
        )
        path_el.set(FPP_REGION_ATTR, str(region.id))

        cx, cy = polygon_centroid(region.polygon)
        txt = etree.SubElement(
            container,
            "{%s}text" % SVG_NS,
            x=f"{cx:.2f}",
            y=f"{cy:.2f}",
            style="font-size:11px;font-family:sans-serif;text-anchor:middle;dominant-baseline:middle;fill:#333333;pointer-events:none",
            # Locked (Inkscape object lock) so click/rubber-band selection
            # only ever grabs the pieces, never their labels.
            **{f"{{{SODIPODI_NS}}}insensitive": "true"},
        )
        txt.text = region.label

    desc = etree.SubElement(g, "{%s}desc" % SVG_NS, id=FPP_DATA_TAG_ID)
    desc.text = block_data.to_json()

    if prefs.get("bypass_custom_colors", False):
        all_pts = [pt for r in tree.leaf_regions() for pt in r.polygon]
        if all_pts:
            max_x = max(pt[0] for pt in all_pts)
            min_y = min(pt[1] for pt in all_pts)
            marker_x = max_x + 15.0
            marker_y = min_y + 12.0
            
            badge_g = etree.SubElement(
                g,
                "{%s}g" % SVG_NS,
                id="qt-temp-colors-marker",
                style="pointer-events:none;",
                **{
                    "data-fpp-ignore": "true",
                    f"{{{SODIPODI_NS}}}insensitive": "true"
                }
            )
            etree.SubElement(
                badge_g,
                "{%s}rect" % SVG_NS,
                x=f"{marker_x:.2f}",
                y=f"{marker_y - 14.0:.2f}",
                width="135",
                height="22",
                rx="4",
                ry="4",
                style="fill:#e65100;fill-opacity:0.92;stroke:#b71c1c;stroke-width:1.0;stroke-dasharray:none;"
            )
            badge_txt = etree.SubElement(
                badge_g,
                "{%s}text" % SVG_NS,
                x=f"{marker_x + 67.5:.2f}",
                y=f"{marker_y + 1.0:.2f}",
                style="font-size:11px;font-family:sans-serif;font-weight:bold;text-anchor:middle;dominant-baseline:middle;fill:#ffffff;"
            )
            badge_txt.text = "temp colours ON"


def invert_transform(t):
    t = inkex.Transform(t)
    a, b, c, d, e, f = t.a, t.b, t.c, t.d, t.e, t.f
    det = a * d - b * c
    if abs(det) < 1e-9:
        return inkex.Transform()
    inv_a = d / det
    inv_b = -b / det
    inv_c = -c / det
    inv_d = a / det
    inv_e = (c * f - d * e) / det
    inv_f = (b * e - a * f) / det
    return inkex.Transform(((inv_a, inv_c, inv_e), (inv_b, inv_d, inv_f)))


def parse_svg_dim(val, default):
    if not val:
        return default
    m = re.match(r"^\s*([0-9.]+)\s*([a-zA-Z]*)", val)
    if m:
        num = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "in":
            return num * 96.0
        elif unit == "pt":
            return num * (96.0 / 72.0)
        elif unit == "mm":
            return num * (96.0 / 25.4)
        elif unit == "cm":
            return num * (96.0 / 2.54)
        return num
    return default


def resolve_element_fill(el):
    current = el
    while current is not None:
        if current.get("id") == "fpp-quilttools-layer" or current.get(f"{{{INKSCAPE_NS}}}groupmode") == "layer":
            break
            
        style = current.get("style", "")
        m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+)", style)
        if m:
            fill_val = m.group(1)
            if fill_val not in ["none", "currentColor", "inherit"]:
                return fill_val
        
        fill_attr = current.get("fill")
        if fill_attr and fill_attr not in ["none", "currentColor", "inherit"]:
            return fill_attr
            
        current = current.getparent()
    return None


def safe_float_unit(el, val_str):
    if not val_str:
        return 0.0
    if hasattr(el, "unittouu"):
        try:
            return float(el.unittouu(val_str))
        except Exception:
            pass
    m = re.match(r"^\s*([0-9.-]+)\s*([a-zA-Z]*)", val_str)
    if m:
        num = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "in":
            return num * 96.0
        elif unit == "pt":
            return num * (96.0 / 72.0)
        elif unit == "mm":
            return num * (96.0 / 25.4)
        elif unit == "cm":
            return num * (96.0 / 2.54)
        return num
    return 0.0


def estimate_element_bbox(el):
    tag = el.tag.split("}")[-1]
    pts = []
    
    if tag == "rect":
        try:
            x = safe_float_unit(el, el.get("x", "0"))
            y = safe_float_unit(el, el.get("y", "0"))
            w = safe_float_unit(el, el.get("width", "0"))
            h = safe_float_unit(el, el.get("height", "0"))
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        except Exception:
            pass
    elif tag in ["circle", "ellipse"]:
        try:
            cx = safe_float_unit(el, el.get("cx", "0"))
            cy = safe_float_unit(el, el.get("cy", "0"))
            r = el.get("r")
            if r:
                rx = ry = safe_float_unit(el, r)
            else:
                rx = safe_float_unit(el, el.get("rx", "0"))
                ry = safe_float_unit(el, el.get("ry", "0"))
            pts = [(cx - rx, cy - ry), (cx + rx, cy - ry), (cx + rx, cy + ry), (cx - rx, cy + ry)]
        except Exception:
            pass
    elif tag == "polygon":
        try:
            raw_pts = [float(v) for v in re.split(r"[,\s]+", el.get("points", "")) if v]
            if raw_pts:
                pts = list(zip(raw_pts[0::2], raw_pts[1::2]))
        except Exception:
            pass
    elif tag == "path":
        try:
            d = el.get("d", "")
            raw_pts = [float(val) for val in re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", d)]
            if raw_pts:
                pts = list(zip(raw_pts[0::2], raw_pts[1::2]))
        except Exception:
            pass

    if not pts:
        return None

    try:
        t = el.composed_transform()
        trans_pts = [t.apply_to_point(pt) for pt in pts]
    except Exception:
        trans_pts = pts

    xs = [pt[0] for pt in trans_pts]
    ys = [pt[1] for pt in trans_pts]
    
    class SimpleBBox:
        def __init__(self, x0, y0, x1, y1):
            self.left = x0
            self.right = x1
            self.top = y0
            self.bottom = y1
            self.width = x1 - x0
            self.height = y1 - y0
            
    return SimpleBBox(min(xs), min(ys), max(xs), max(ys))


def extract_vector_shapes(root_el):
    shapes = []
    for el in root_el.xpath("//*[local-name()='path' or local-name()='rect' or local-name()='circle' or local-name()='ellipse' or local-name()='polygon']"):
        color = resolve_element_fill(el)
        if not color:
            continue
            
        bbox = estimate_element_bbox(el)
        if bbox:
            w = bbox.width
            h = bbox.height
            if w > 0 and h > 0:
                shapes.append(((bbox.left, bbox.top, bbox.right, bbox.bottom), color, w * h))
    return shapes


def sample_image_colors(svg, block_data):
    custom_colors = block_data.prefs.setdefault("custom_colors", {})
    regions = block_data.tree.leaf_regions()
    sampled_count = 0

    try:
        from PIL import Image
        images = svg.findall(f".//{{{SVG_NS}}}image")
    except ImportError:
        images = []
        Image = None

    for img_el in images:
        href = img_el.get("href") or img_el.get(f"{{{SVG_NS}}}href") or img_el.get("{http://www.w3.org/1999/xlink}href")
        if not href:
            continue

        try:
            is_svg = False
            ext_svg = None
            
            if href.startswith("data:image/svg+xml"):
                is_svg = True
                header, encoded = href.split(";base64,", 1)
                data = base64.b64decode(encoded).decode("utf-8")
                ext_svg = etree.fromstring(data.encode("utf-8"))
            elif href.lower().endswith(".svg") or ".svg?" in href.lower() or ".svg#" in href.lower():
                is_svg = True
                if href.startswith("file:///"):
                    filepath = urllib.parse.unquote(href[8:])
                    if (filepath[1] == ":" or filepath[2] == ":") and filepath[0] == "/":
                        filepath = filepath[1:]
                elif href.startswith("file://"):
                    filepath = urllib.parse.unquote(href[7:])
                else:
                    filepath = href
                    docname = svg.get(f"{{{SODIPODI_NS}}}docname") or svg.get("sodipodi:docname")
                    if docname:
                        base_dir = os.path.dirname(docname)
                        candidate = os.path.join(base_dir, href)
                        if os.path.exists(candidate):
                            filepath = candidate
                ext_svg = etree.parse(filepath).getroot()

            if is_svg and ext_svg is not None:
                ext_w = parse_svg_dim(ext_svg.get("width"), 100.0)
                ext_h = parse_svg_dim(ext_svg.get("height"), 100.0)
                viewbox = ext_svg.get("viewBox")
                if viewbox:
                    parts = viewbox.split()
                    if len(parts) == 4:
                        try:
                            ext_w = float(parts[2])
                            ext_h = float(parts[3])
                        except ValueError:
                            pass
                
                bg_shapes = extract_vector_shapes(ext_svg)
                if bg_shapes:
                    x_attr = float(svg.unittouu(img_el.get("x", "0")))
                    y_attr = float(svg.unittouu(img_el.get("y", "0")))
                    w_attr = float(svg.unittouu(img_el.get("width", "0")))
                    h_attr = float(svg.unittouu(img_el.get("height", "0")))
                    if w_attr > 0 and h_attr > 0:
                        img_t = img_el.composed_transform()
                        inv_t = invert_transform(img_t)
                        
                        for r in regions:
                            if str(r.id) in custom_colors:
                                continue
                            cx, cy = polygon_centroid(r.polygon)
                            local_cx, local_cy = inv_t.apply_to_point((cx, cy))
                            u = (local_cx - x_attr) / w_attr
                            v = (local_cy - y_attr) / h_attr
                            
                            if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                                ext_cx = u * ext_w
                                ext_cy = v * ext_h
                                
                                matching = []
                                for bbox, color, area in bg_shapes:
                                    if bbox[0] <= ext_cx <= bbox[2] and bbox[1] <= ext_cy <= bbox[3]:
                                        matching.append((color, area))
                                if matching:
                                    matching.sort(key=lambda x: x[1])
                                    custom_colors[str(r.id)] = matching[0][0]
                                    sampled_count += 1
            else:
                if Image is None:
                    continue
                if href.startswith("data:image/"):
                    header, encoded = href.split(";base64,", 1)
                    data = base64.b64decode(encoded)
                    pil_img = Image.open(io.BytesIO(data))
                else:
                    if href.startswith("file:///"):
                        filepath = urllib.parse.unquote(href[8:])
                        if (filepath[1] == ":" or filepath[2] == ":") and filepath[0] == "/":
                            filepath = filepath[1:]
                    elif href.startswith("file://"):
                        filepath = urllib.parse.unquote(href[7:])
                    else:
                        filepath = href
                        docname = svg.get(f"{{{SODIPODI_NS}}}docname") or svg.get("sodipodi:docname")
                        if docname:
                            base_dir = os.path.dirname(docname)
                            candidate = os.path.join(base_dir, href)
                            if os.path.exists(candidate):
                                filepath = candidate
                    pil_img = Image.open(filepath)

                x_attr = float(svg.unittouu(img_el.get("x", "0")))
                y_attr = float(svg.unittouu(img_el.get("y", "0")))
                w_attr = float(svg.unittouu(img_el.get("width", "0")))
                h_attr = float(svg.unittouu(img_el.get("height", "0")))
                if w_attr <= 0 or h_attr <= 0:
                    continue

                img_t = img_el.composed_transform()
                inv_t = invert_transform(img_t)

                for r in regions:
                    if str(r.id) in custom_colors:
                        continue
                    cx, cy = polygon_centroid(r.polygon)
                    local_cx, local_cy = inv_t.apply_to_point((cx, cy))
                    u = (local_cx - x_attr) / w_attr
                    v = (local_cy - y_attr) / h_attr

                    if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                        px_x = int(u * pil_img.width)
                        px_y = int(v * pil_img.height)
                        colors = []
                        for dx in range(-1, 2):
                            for dy in range(-1, 2):
                                xx = min(max(0, px_x + dx), pil_img.width - 1)
                                yy = min(max(0, px_y + dy), pil_img.height - 1)
                                color = pil_img.getpixel((xx, yy))
                                if isinstance(color, tuple):
                                    colors.append(color[:3])
                                else:
                                    colors.append((color, color, color))
                        r_vals = sorted([c[0] for c in colors])
                        g_vals = sorted([c[1] for c in colors])
                        b_vals = sorted([c[2] for c in colors])
                        median_rgb = (r_vals[len(r_vals)//2], g_vals[len(g_vals)//2], b_vals[len(b_vals)//2])
                        hex_color = "#{:02x}{:02x}{:02x}".format(*median_rgb)
                        custom_colors[str(r.id)] = hex_color
                        sampled_count += 1

        except Exception:
            continue

    # 2. Try to sample from vector background shapes (SVG tracing mode)
    bg_shapes = []
    for tag in ["path", "rect", "circle", "ellipse", "polygon"]:
        for el in svg.findall(f".//{{{SVG_NS}}}{tag}"):
            parent = el.getparent()
            is_fpp = False
            while parent is not None:
                pid = parent.get("id")
                if pid in ["fpp-quilttools-layer", "fpp-layout-layer"]:
                    is_fpp = True
                    break
                parent = parent.getparent()
            if is_fpp:
                continue

            color = resolve_element_fill(el)
            if color:
                bbox = estimate_element_bbox(el)
                if bbox and bbox.width > 0 and bbox.height > 0:
                    area = bbox.width * bbox.height
                    bg_shapes.append((bbox, color, area))

    if bg_shapes:
        for r in regions:
            if str(r.id) in custom_colors:
                continue
            cx, cy = polygon_centroid(r.polygon)
            matching = []
            for bbox, color, area in bg_shapes:
                if bbox.left <= cx <= bbox.right and bbox.top <= cy <= bbox.bottom:
                    matching.append((color, area))
            if matching:
                matching.sort(key=lambda x: x[1])
                custom_colors[str(r.id)] = matching[0][0]
                sampled_count += 1
    return sampled_count


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def classify_color_family(hex_str):
    import colorsys
    try:
        r, g, b = hex_to_rgb(hex_str)
    except Exception:
        return "GY"
    h, l, s = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
    hue = h * 360.0
    
    if l >= 0.95:
        return "WT"
    if l <= 0.08:
        return "BK"
    if s <= 0.10:
        return "GY"
        
    if hue < 15 or hue >= 345:
        return "RD"
    elif 15 <= hue < 45:
        if l < 0.35 or s < 0.35:
            return "BR"
        return "OR"
    elif 45 <= hue < 70:
        return "YL"
    elif 70 <= hue < 165:
        return "GR"
    elif 165 <= hue < 195:
        return "TL"
    elif 195 <= hue < 255:
        return "BL"
    elif 255 <= hue < 290:
        return "PU"
    else:
        return "PK"


def assign_color_codes(colors, overrides_str=""):
    import colorsys
    overrides = {}
    if overrides_str:
        for item in overrides_str.split(","):
            if ":" in item:
                parts = item.split(":", 1)
                h_val = parts[0].strip().lower()
                code_val = parts[1].strip().upper()
                if h_val and code_val:
                    overrides[h_val] = code_val

    family_groups = {}
    assigned = {}
    
    for c in colors:
        c_clean = c.strip().lower()
        if c_clean in overrides:
            assigned[c] = overrides[c_clean]
            
    remaining_colors = [c for c in colors if c not in assigned]
    
    for c in remaining_colors:
        family = classify_color_family(c)
        try:
            r, g, b = hex_to_rgb(c)
        except Exception:
            r, g, b = 128, 128, 128
        h_val, l_val, s_val = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
        
        if family not in family_groups:
            family_groups[family] = []
        family_groups[family].append((c, l_val, h_val))
        
    for family, items in family_groups.items():
        items.sort(key=lambda x: (x[1], x[2]))
        for idx, (c, _, _) in enumerate(items, 1):
            assigned[c] = f"{family}{idx}"
            
    return assigned


def quantize_block_colors(block_data, N, locked_hex_list):
    custom_colors = block_data.prefs.setdefault("custom_colors", {})
    regions = block_data.tree.leaf_regions()
    if not regions:
        return

    locked_rgbs = []
    for h in locked_hex_list:
        if h.strip():
            try:
                locked_rgbs.append(hex_to_rgb(h.strip()))
            except Exception:
                pass

    color_mode = block_data.prefs.get("color_mode", "piece")
    region_colors = {}
    for idx, r in enumerate(sorted(regions, key=lambda x: x.label)):
        c = custom_colors.get(str(r.id))
        if not c:
            c = get_color_for_label(r.label, color_mode, idx)
        try:
            region_colors[r.id] = hex_to_rgb(c)
        except Exception:
            region_colors[r.id] = (214, 234, 248)

    unique_colors = list(set(region_colors.values()))
    if len(unique_colors) <= N:
        for rid, rgb in region_colors.items():
            custom_colors[str(rid)] = rgb_to_hex(rgb)
        return

    # Helper functions for CIELAB color theory based distance
    def rgb_to_lab(rgb):
        r, g, b = [val / 255.0 for val in rgb]
        def to_linear(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        r_l, g_l, b_l = to_linear(r), to_linear(g), to_linear(b)
        x = r_l * 0.4124564 + g_l * 0.3575761 + b_l * 0.1804375
        y = r_l * 0.2126729 + g_l * 0.7151522 + b_l * 0.0721750
        z = r_l * 0.0193339 + g_l * 0.1191920 + b_l * 0.9503041
        xn, yn, zn = 0.950489, 1.000000, 1.088840
        xr, yr, zr = x / xn, y / yn, z / zn
        def f(t):
            return t ** (1/3) if t > 0.008856 else 7.787 * t + 16/116
        fx, fy, fz = f(xr), f(yr), f(zr)
        l_star = 116 * fy - 16
        a_star = 500 * (fx - fy)
        b_star = 200 * (fy - fz)
        return (l_star, a_star, b_star)

    lab_cache = {}
    def get_lab(rgb):
        if rgb not in lab_cache:
            lab_cache[rgb] = rgb_to_lab(rgb)
        return lab_cache[rgb]

    def dist_lab(c1, c2):
        l1, a1, b1 = get_lab(c1)
        l2, a2, b2 = get_lab(c2)
        return math.hypot(l1-l2, a1-a2, b1-b2)

    L = len(locked_rgbs)
    if L >= N:
        centroids = locked_rgbs[:N]
        for rid, rgb in region_colors.items():
            best_c = min(centroids, key=lambda c: dist_lab(rgb, c))
            custom_colors[str(rid)] = rgb_to_hex(best_c)
        return

    # Agglomerative clustering based on perceptual CIELAB distances
    clusters = []
    for rgb in unique_colors:
        is_locked = rgb in locked_rgbs
        count = sum(1 for c in region_colors.values() if c == rgb)
        clusters.append({
            'color': rgb,
            'count': count,
            'locked': is_locked,
            'original_colors': {rgb}
        })

    # Add any locked colors not present in the block as their own clusters
    for rgb in locked_rgbs:
        if rgb not in unique_colors:
            clusters.append({
                'color': rgb,
                'count': 0,
                'locked': True,
                'original_colors': {rgb}
            })

    while len(clusters) > N:
        min_d = float('inf')
        best_pair = None
        for i in range(len(clusters)):
            for j in range(i+1, len(clusters)):
                if clusters[i]['locked'] and clusters[j]['locked']:
                    continue
                d = dist_lab(clusters[i]['color'], clusters[j]['color'])
                if d < min_d:
                    min_d = d
                    best_pair = (i, j)

        if best_pair is None:
            break

        i, j = best_pair
        c1, c2 = clusters[i], clusters[j]

        # Merge c2 into c1
        if c1['locked']:
            new_color = c1['color']
        elif c2['locked']:
            new_color = c2['color']
        else:
            total_count = c1['count'] + c2['count']
            if total_count > 0:
                new_r = int((c1['color'][0]*c1['count'] + c2['color'][0]*c2['count']) / total_count)
                new_g = int((c1['color'][1]*c1['count'] + c2['color'][1]*c2['count']) / total_count)
                new_b = int((c1['color'][2]*c1['count'] + c2['color'][2]*c2['count']) / total_count)
                new_color = (new_r, new_g, new_b)
            else:
                new_color = c1['color']

        c1['color'] = new_color
        c1['count'] = c1['count'] + c2['count']
        c1['locked'] = c1['locked'] or c2['locked']
        c1['original_colors'].update(c2['original_colors'])

        clusters.pop(j)

    # Build mapping from original color to quantized color
    color_map = {}
    for c in clusters:
        for orig in c['original_colors']:
            color_map[orig] = c['color']

    # Assign new colors to regions
    for rid, rgb in region_colors.items():
        quantized_rgb = color_map.get(rgb, rgb)
        custom_colors[str(rid)] = rgb_to_hex(quantized_rgb)


def mirror_block_geometry(block_data):
    root = block_data.tree.regions.get(block_data.tree.root_id)
    if not root:
        return
    xs = [p[0] for p in root.polygon]
    cx = (min(xs) + max(xs)) / 2.0
    for r in block_data.tree.regions.values():
        r.polygon = [(2.0 * cx - p[0], p[1]) for p in r.polygon]
    block_data.tree.sanitize_tree()


def translate_block_geometry(block_data, dx, dy):
    for r in block_data.tree.regions.values():
        r.polygon = [(p[0] + dx, p[1] + dy) for p in r.polygon]


def scale_block_geometry(block_data, sx, sy):
    for r in block_data.tree.regions.values():
        r.polygon = [(p[0] * sx, p[1] * sy) for p in r.polygon]


def block_bounds(block_data):
    pts = [p for r in block_data.tree.leaf_regions() for p in r.polygon]
    if not pts:
        return None
    return (
        min(p[0] for p in pts),
        min(p[1] for p in pts),
        max(p[0] for p in pts),
        max(p[1] for p in pts),
    )


def normalize_block_to_origin(block_data):
    b = block_bounds(block_data)
    if b is None:
        return (0.0, 0.0)
    min_x, min_y, max_x, max_y = b
    translate_block_geometry(block_data, -min_x, -min_y)
    return (max_x - min_x, max_y - min_y)


def block_data_to_standalone_svg(block_data, name=None):
    b = block_bounds(block_data)
    if b is None:
        min_x = min_y = 0.0
        w = h = PX_PER_INCH
    else:
        min_x, min_y, max_x, max_y = b
        w, h = (max_x - min_x), (max_y - min_y)

    nsmap = {None: SVG_NS, "inkscape": INKSCAPE_NS, "sodipodi": SODIPODI_NS}
    svg = etree.Element("{%s}svg" % SVG_NS, nsmap=nsmap)
    svg.set("width", f"{w}")
    svg.set("height", f"{h}")
    svg.set("viewBox", f"{min_x} {min_y} {w} {h}")
    svg.set("data-quilttools-block", "1")
    if name:
        svg.set("data-quilttools-name", str(name))
        title = etree.SubElement(svg, "{%s}title" % SVG_NS)
        title.text = str(name)

    svg.append(build_fpp_layer(block_data))
    return svg


def extract_block_data_from_svg_root(root):
    for desc in root.iter("{%s}desc" % SVG_NS):
        if desc.get("id") == FPP_DATA_TAG_ID and desc.text:
            try:
                from quilttools_fpp_core import BlockData
                return BlockData.from_json(desc.text)
            except Exception:
                return None
    return None


def section_outline(polys):
    """Outline polygon for a section's pieces plus a soundness flag.

    get_polygon_union only merges polygons that share exact edges and
    silently returns partial geometry otherwise (it can even drop pieces).
    A valid FPP section always unions soundly (each seam spans the unit),
    so an unsound union marks a suspicious section. In that case fall back
    to the convex hull of all pieces: a superset of the true outline, so
    any check built on it is conservative — it can flag extra problems but
    never hide one.
    Returns (outline_polygon, is_sound).
    """
    total = sum(polygon_area(p) for p in polys)
    union = get_polygon_union(polys)
    ua = polygon_area(union) if union else 0.0
    if union and abs(ua - total) <= max(0.01 * total, 1.0):
        return union, True
    return convex_hull([pt for p in polys for pt in p]), False


def unsound_union_sections(block_data):
    """Section prefixes whose piece geometry cannot be soundly unioned."""
    sec_polys = {}
    for r in block_data.tree.leaf_regions():
        match = re.match(r"^([A-Za-z_]+)", r.label)
        prefix = match.group(1).upper() if match else "A"
        sec_polys.setdefault(prefix, []).append(r.polygon)
    out = []
    for prefix, polys in sec_polys.items():
        if len(polys) < 2:
            continue
        _, sound = section_outline(polys)
        if not sound:
            out.append(prefix)
    return sorted(out)


def calculate_section_sewing_order(block_data):
    tree = block_data.tree
    regions = tree.leaf_regions()
    if not regions:
        return [], False

    sec_regions = {}
    for r in regions:
        match = re.match(r"^([A-Za-z_]+)", r.label)
        prefix = match.group(1).upper() if match else "A"
        if prefix not in sec_regions:
            sec_regions[prefix] = []
        sec_regions[prefix].append(r)

    section_polys = {}
    section_areas = {}
    for prefix, grp in sec_regions.items():
        polys = [r.polygon for r in grp]
        outline, _sound = section_outline(polys)
        if outline and len(outline) >= 3:
            section_polys[prefix] = outline
            section_areas[prefix] = max(polygon_area(outline), 1.0)

    section_names = list(section_polys.keys())
    if len(section_names) <= 1:
        return [], False
    if len(section_names) > 12:
        steps = []
        curr = section_names[0]
        for nxt in section_names[1:]:
            steps.append(f"Join {curr} + {nxt} -> {curr}{nxt}")
            curr = f"{curr}{nxt}"
        return steps, False

    has_warning = [False]

    def solve_assembly(names):
        if len(names) <= 1:
            return list(names)[0]

        best_split = None
        best_score = -1.0

        for name in names:
            poly = section_polys[name]
            n = len(poly)
            for i in range(n):
                p1, p2 = poly[i], poly[(i + 1) % n]
                d = vec_sub(p2, p1)
                l_d = vec_len(d)
                if l_d < 1e-4:
                    continue
                nd = (d[0] / l_d, d[1] / l_d)

                cuts = False
                g1, g2 = [], []
                for other in names:
                    other_poly = section_polys[other]
                    side_pos = False
                    side_neg = False
                    for pt in other_poly:
                        v = vec_sub(pt, p1)
                        dist = nd[0]*v[1] - nd[1]*v[0]
                        if dist > 1.5:
                            side_pos = True
                        elif dist < -1.5:
                            side_neg = True

                    if side_pos and side_neg:
                        cuts = True
                        break
                    elif side_pos:
                        g1.append(other)
                    elif side_neg:
                        g2.append(other)
                    else:
                        g1.append(other)

                if not cuts and g1 and g2:
                    area_g1 = sum(section_areas[n] for n in g1)
                    area_g2 = sum(section_areas[n] for n in g2)
                    total_area = area_g1 + area_g2
                    balance = 1.0 - abs(area_g1 - area_g2) / total_area
                    score = l_d * balance
                    if score > best_score:
                        best_score = score
                        best_split = (g1, g2)

        if best_split:
            g1, g2 = best_split
            return (solve_assembly(g1), solve_assembly(g2))
        else:
            has_warning[0] = True
            names_list = sorted(list(names))
            g1 = names_list[:len(names_list)//2]
            g2 = names_list[len(names_list)//2:]
            return (solve_assembly(g1), solve_assembly(g2))

    split_tree = solve_assembly(section_names)

    steps = []
    def flatten_tree(node):
        if isinstance(node, str):
            return node
        left, right = node
        l_name = flatten_tree(left)
        r_name = flatten_tree(right)
        joined_name = "".join(sorted(list(set(l_name + r_name))))
        steps.append(f"Join {l_name} + {r_name} -> {joined_name}")
        return joined_name

    flatten_tree(split_tree)
    return steps, has_warning[0]
