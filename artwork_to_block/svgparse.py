import re
from xml.etree import ElementTree as ET

SVG = "{http://www.w3.org/2000/svg}"


def parse_paths(path):
    """Every <path> in the artwork, as a point list plus its resolved fill."""
    root = ET.parse(path).getroot()
    out = []

    def walk(el, fill, gid):
        for ch in el:
            tag = ch.tag.split("}")[-1]
            if tag == "g":
                walk(ch, ch.get("fill") or fill, ch.get("id") or gid)
            elif tag == "path":
                pts = [(float(m.group(1)), float(m.group(2)))
                       for m in re.finditer(r"[ML]([-0-9.]+),([-0-9.]+)",
                                            ch.get("d", ""))]
                out.append({"pts": pts, "fill": ch.get("fill") or fill,
                            "group": gid or "?"})

    walk(root, None, None)
    return out
