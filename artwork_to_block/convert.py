"""Stage 1: turn traced artwork SVG into a clean planar partition of the block.

Reads the artwork, rebuilds it as a planar arrangement (so every seam is shared
exactly by the two pieces that meet along it), fills tracing gaps, and absorbs
pieces too small/thin to sew.  Emits JSON polygons in SVG px (96/in) for stage 2.

Usage: python convert.py <artwork.svg> <block_in> <out.json>
"""
import json
import sys

from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid

from svgparse import parse_paths

PX_PER_INCH = 96.0
MIN_AREA = 0.02      # sq in - below this a piece cannot be handled at the machine
MIN_WIDTH = 0.09     # in    - narrowest finished width we allow
GROUT = 0.04         # in    - widest tracing gap we treat as "not real"
SIMPLIFY = 0.03      # in    - seam deviation we accept when dropping vertices
EPS_LEN = 1e-6


def too_small(geom):
    return geom.area < MIN_AREA or geom.buffer(-MIN_WIDTH / 2.0).is_empty


def as_polygons(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def shared_length(a, b):
    if not a.intersects(b):
        return 0.0
    inter = a.exterior.intersection(b.exterior)
    return getattr(inter, "length", 0.0)


def build(path, block_in):
    items = parse_paths(path)
    blk = box(0, 0, block_in, block_in)

    sources = []
    for it in items:
        p = Polygon(it["pts"])
        if not p.is_valid:
            p = make_valid(p)
        parts = as_polygons(p)
        if not parts:
            continue
        keep = max(parts, key=lambda g: g.area)
        keep = keep.intersection(blk)
        for q in as_polygons(keep):
            if q.area > 1e-9:
                sources.append({"geom": q, "fill": it["fill"]})

    # Does the artwork already tile the block exactly? Then it only needs
    # translating, and nothing below should be allowed to move a seam.
    art = unary_union([s["geom"] for s in sources])
    gap_area = blk.difference(art).area
    overlap_area = sum(s["geom"].area for s in sources) - art.area
    exact = gap_area < 1e-9 and abs(overlap_area) < 1e-9

    # Planar arrangement: node every boundary against every other, then rebuild
    # the faces.  Faces that come out of one arrangement share exact edges.
    # Outward offsets of each piece are noded in as well: they are what cuts
    # the connected web of tracing gaps into one strip per seam.
    lines = [s["geom"].exterior for s in sources] + [blk.exterior]
    if not exact:
        for s in sources:
            grown = s["geom"].buffer(GROUT, join_style=2, mitre_limit=5.0)
            for g in as_polygons(grown.intersection(blk)):
                lines.append(g.exterior)
    faces = list(polygonize(unary_union(lines)))

    pieces = []
    for f in faces:
        if f.area < 1e-9:
            continue
        rp = f.representative_point()
        owner = None
        best = 0.0
        for idx, s in enumerate(sources):
            if s["geom"].contains(rp):
                # nested/overlapping source art: smallest containing wins
                if owner is None or s["geom"].area < best:
                    owner, best = idx, s["geom"].area
        if owner is None:
            # A gap strip. It belongs to a piece it runs along; where two are
            # equally close, the larger one grows so fine detail keeps its
            # traced shape.
            dists = [(s["geom"].distance(rp), i) for i, s in enumerate(sources)]
            near = min(d for d, _ in dists)
            close = [i for d, i in dists if d <= near + GROUT]
            if close:
                owner = max(close, key=lambda i: sources[i]["geom"].area)
        pieces.append({
            "geom": f,
            "fill": sources[owner]["fill"] if owner is not None else None,
            "owner": owner,
        })

    # Faces belonging to the same source piece rejoin into one piece.
    merged = []
    by_owner = {}
    for p in pieces:
        if p["owner"] is None:
            merged.append(p)
        else:
            by_owner.setdefault(p["owner"], []).append(p)
    for owner, group in by_owner.items():
        u = unary_union([g["geom"] for g in group])
        for part in as_polygons(u):
            merged.append({"geom": part, "fill": group[0]["fill"], "owner": owner})

    stats = {
        "source_paths": len(sources),
        "already_exact": exact,
        "art_gap_area": round(gap_area, 5),
        "art_overlap_area": round(overlap_area, 5),
        "faces": len(pieces),
        "gap_strips": sum(1 for p in pieces if p["owner"] is None),
    }

    if exact:
        # Nothing to repair: keep the artwork's own seams, vertex for vertex.
        stats.update(pieces=len(merged), simplify_passes=[],
                     verts_before=max(len(p["geom"].exterior.coords) - 1
                                      for p in merged))
        stats["verts_after"] = stats["verts_before"]
        return merged, stats

    pieces = settle(absorb(merged))
    stats["verts_before"] = max(len(p["geom"].exterior.coords) - 1 for p in pieces)

    # Work up to the full tolerance rather than starting there: gentle passes
    # clear the tracing noise first, so the last pass judges real geometry.
    applied = []
    for tol in [SIMPLIFY / 4.0, SIMPLIFY / 2.0, SIMPLIFY, SIMPLIFY]:
        pieces2, ok = simplify_partition(pieces, tol, blk)
        if ok:
            pieces = settle(pieces2)
            applied.append(tol)
    stats["simplify_passes"] = applied

    stats["pieces"] = len(pieces)
    stats["verts_after"] = max(len(p["geom"].exterior.coords) - 1 for p in pieces)
    return pieces, stats


def settle(pieces):
    """Absorb and hole-split alternately until neither changes anything."""
    for _ in range(8):
        n = len(pieces)
        pieces = absorb(split_holes(pieces))
        if len(pieces) == n:
            break
    return pieces


def absorb(pieces):
    """Fold gap faces and unsewably small pieces into their best neighbour.

    Gaps go first (they are tracing artefacts, not design), then real pieces
    smallest-first, so a sliver always merges into the largest thing it can.
    """
    for p in pieces:
        # "stuck" only means "found no partner among the pieces as they were
        # last time"; splitting and simplifying since then may have given it
        # a neighbour.
        p.pop("stuck", None)
    while True:
        todo = [p for p in pieces
                if not p.get("stuck")
                and (p["fill"] is None or too_small(p["geom"]))]
        if not todo:
            break
        todo.sort(key=lambda p: (p["fill"] is not None, p["geom"].area))
        victim = todo[0]

        cands = []
        for other in pieces:
            if other is victim:
                continue
            ln = shared_length(victim["geom"], other["geom"])
            if ln > EPS_LEN:
                same = other["fill"] is not None and other["fill"] == victim["fill"]
                real = other["fill"] is not None
                cands.append((same, real, ln, other))
        cands.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)

        moved = False
        # Strict pass keeps merges hole-free; if nothing works, a merge that
        # rings a hole is still better than an unsewable sliver - split_holes
        # runs afterwards and cuts the ring open again.
        for allow_holes in (False, True):
            for _same, _real, _ln, other in cands:
                u = unary_union([victim["geom"], other["geom"]])
                if not isinstance(u, Polygon):
                    continue
                if list(u.interiors) and not allow_holes:
                    continue
                other["geom"] = u
                other.pop("stuck", None)
                if other["fill"] is None:
                    other["fill"] = victim["fill"]
                pieces.remove(victim)
                moved = True
                break
            if moved:
                break

        if not moved:
            # Isolated - nothing shares a boundary with it. Keep it as its own
            # piece and stop reconsidering it.
            victim["stuck"] = True
            if victim["fill"] is None:
                victim["fill"] = "#cccccc"
    return pieces


def split_holes(pieces):
    """A piece that rings an enclosed detail (the nose, the ear) can't be
    sewn as one patch. Cut it in two along the line of one of the enclosed
    shape's own edges - the seam then runs off a facet of the detail, which
    is how a piecer would draft it anyway."""
    out = []
    for p in pieces:
        geom = p["geom"]
        guard = 0
        stack = [geom]
        while stack:
            g = stack.pop()
            if not list(g.interiors) or guard > 40:
                out.append({**p, "geom": g})
                continue
            guard += 1
            best = None
            for ring in g.interiors:
                cs = list(ring.coords)
                for a, b in zip(cs, cs[1:]):
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    ln = (dx * dx + dy * dy) ** 0.5
                    if ln < 1e-9:
                        continue
                    big = 100.0
                    cut = LineString([
                        (a[0] - dx / ln * big, a[1] - dy / ln * big),
                        (b[0] + dx / ln * big, b[1] + dy / ln * big)])
                    parts = _split_by(g, cut)
                    if len(parts) < 2:
                        continue
                    score = (max(len(list(q.interiors)) for q in parts),
                             -min(q.area for q in parts))
                    if best is None or score < best[0]:
                        best = (score, parts)
            if best is None:
                out.append({**p, "geom": g})
                continue
            stack.extend(best[1])
    return out


def _split_by(poly, line):
    """The pieces `poly` falls into when cut by `line` (holes respected)."""
    faces = polygonize(unary_union([poly.boundary, line]))
    return [f for f in faces
            if f.area > 1e-9 and poly.contains(f.representative_point())]


def renode(pieces, blk):
    """Rebuild every piece out of one shared arrangement, so a seam carries
    the same vertices on both sides (needed before chains can be simplified
    without tearing the block apart)."""
    lines = [p["geom"].exterior for p in pieces] + [blk.exterior]
    faces = [f for f in polygonize(unary_union(lines)) if f.area > 1e-12]
    out = []
    for p in pieces:
        mine = [f for f in faces if p["geom"].contains(f.representative_point())]
        if not mine:
            out.append(p)
            continue
        for part in as_polygons(unary_union(mine)):
            out.append({**p, "geom": part})
    return out


def arcs_of(rings):
    """Break the block's linework into arcs: runs of segments carrying the
    same pieces on either side, ending wherever a third piece joins in.

    An arc is one physical seam, stored once and shared by the two pieces
    that sew it - which is what lets a seam be simplified without the two
    sides drifting apart.
    """
    owners = {}
    for i, ring in enumerate(rings):
        for a, b in zip(ring, ring[1:] + ring[:1]):
            owners.setdefault(tuple(sorted((a, b))), set()).add(i)

    inc = {}
    for k in owners:
        for v in k:
            inc.setdefault(v, []).append(k)

    def walkable(v, used):
        ks = inc[v]
        if len(ks) != 2 or owners[ks[0]] != owners[ks[1]]:
            return None                      # junction: the arc ends here
        nxt = [k for k in ks if k not in used]
        return nxt[0] if len(nxt) == 1 else None

    arcs, arc_of = [], {}
    for seed in owners:
        if seed in arc_of:
            continue
        chain = [seed[0], seed[1]]
        used = {seed}
        while chain[-1] != chain[0]:
            k = walkable(chain[-1], used)
            if k is None:
                break
            used.add(k)
            chain.append(k[0] if k[1] == chain[-1] else k[1])
        while chain[-1] != chain[0]:
            k = walkable(chain[0], used)
            if k is None:
                break
            used.add(k)
            chain.insert(0, k[0] if k[1] == chain[0] else k[1])
        for k in used:
            arc_of[k] = len(arcs)
        arcs.append(chain)
    return arcs, arc_of


def simplify_partition(pieces, tol, blk):
    """Drop vertices that only describe tracing noise, seam by seam.

    Each arc is simplified once and both pieces sharing it are rebuilt from
    that one result, so the block stays an exact partition. Falls back to the
    input if the result doesn't verify.
    """
    pieces = renode(pieces, blk)

    def rd(p):
        return (round(p[0], 9), round(p[1], 9))

    rings = [[rd(c) for c in list(p["geom"].exterior.coords)[:-1]]
             for p in pieces]
    arcs, arc_of = arcs_of(rings)

    # Every segment in the block, so a seam can check that straightening it
    # doesn't sweep across anything else.
    segs = []
    for ring in rings:
        segs += [LineString([a, b]) for a, b in zip(ring, ring[1:] + ring[:1])]
    seg_tree = STRtree(segs)

    def safe(chain, simp):
        if len(simp) >= len(chain):
            return True
        swept = Polygon(list(chain) + list(simp)[::-1]).buffer(0)
        if swept.is_empty:
            return True
        own = set(chain)
        for i in seg_tree.query(swept):
            s = segs[i]
            a, b = s.coords[0], s.coords[1]
            if a in own and b in own:
                continue
            if swept.intersection(s).length > 1e-9:
                return False
        return True

    simplified = []
    for chain in arcs:
        best = list(chain)
        if len(chain) > 2 and chain[0] != chain[-1]:
            for t in (tol, tol / 2.0, tol / 4.0):
                cand = [tuple(c) for c in LineString(chain).simplify(t).coords]
                if safe(chain, cand):
                    best = cand
                    break
        simplified.append(best)

    rebuilt = []
    for p, ring in zip(pieces, rings):
        # Which arc each of this ring's segments belongs to.
        segs_ring = [tuple(sorted((a, b)))
                     for a, b in zip(ring, ring[1:] + ring[:1])]
        ids = [arc_of[s] for s in segs_ring]
        starts = [i for i in range(len(ids)) if ids[i - 1] != ids[i]]
        if not starts:
            rebuilt.append(p)          # a ring that is a single closed arc
            continue
        ring = ring[starts[0]:] + ring[:starts[0]]
        ids = ids[starts[0]:] + ids[:starts[0]]

        new = []
        i = 0
        while i < len(ids):
            j = i
            while j + 1 < len(ids) and ids[j + 1] == ids[i]:
                j += 1
            simp = simplified[ids[i]]
            if simp[0] != ring[i]:
                simp = simp[::-1]
            new.extend(simp[:-1] if simp[0] != simp[-1] else simp)
            i = j + 1
        if len(new) >= 3:
            g = Polygon(new)
            if g.is_valid and g.area > 0:
                rebuilt.append({**p, "geom": g})
                continue
        rebuilt.append(p)

    v = verify(rebuilt, blk.bounds[2])
    ok = (abs(v["coverage_gap"]) < 1e-6 and v["overlap"] < 1e-6
          and v["pieces_with_holes"] == 0 and v["union_parts"] == 1)
    return (rebuilt, True) if ok else (pieces, False)


def verify(pieces, block_in):
    total = sum(p["geom"].area for p in pieces)
    u = unary_union([p["geom"] for p in pieces])
    ov = 0.0
    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            a, b = pieces[i]["geom"], pieces[j]["geom"]
            if a.intersects(b):
                ov += a.intersection(b).area
    holes = sum(1 for p in pieces if list(p["geom"].interiors))
    thin = sum(1 for p in pieces if too_small(p["geom"]))
    return {
        "piece_area_total": total,
        "block_area": block_in * block_in,
        "coverage_gap": block_in * block_in - u.area,
        "overlap": ov,
        "pieces_with_holes": holes,
        "pieces_too_small": thin,
        "union_parts": len(as_polygons(u)),
    }


def main():
    src, block_in, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    pieces, stats = build(src, block_in)
    v = verify(pieces, block_in)

    print(f"--- {src}")
    for k, val in {**stats, **v}.items():
        print(f"    {k}: {val}")

    data = []
    for p in sorted(pieces, key=lambda q: (-q["geom"].area,)):
        g = orient(p["geom"], 1.0).simplify(0)
        pts = [[round(x * PX_PER_INCH, 5), round(y * PX_PER_INCH, 5)]
               for x, y in list(g.exterior.coords)[:-1]]
        data.append({"pts": pts, "fill": p["fill"],
                     "area_sq_in": round(p["geom"].area, 5)})
    with open(out, "w") as fh:
        json.dump(data, fh)
    print(f"    wrote {len(data)} pieces -> {out}")


if __name__ == "__main__":
    main()
