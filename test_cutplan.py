"""Tests for quilttools_cutplan (technique-aware cutting planner).

Run with any Python 3: python test_cutplan.py
All dimensions in inches; polygons are FINISHED size (no seam allowance).
"""

import math

import quilttools_cutplan as cp

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    if not cond:
        print("FAIL: %s %s" % (name, detail))


def approx(a, b, tol=1e-3):
    return abs(a - b) <= tol


def sq(side, x=0, y=0):
    return [(x, y), (x + side, y), (x + side, y + side), (x, y + side)]


def rect(w, h, x=0, y=0):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def rot(poly, deg, cx=0.0, cy=0.0):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [((p[0] - cx) * c - (p[1] - cy) * s + cx,
             (p[0] - cx) * s + (p[1] - cy) * c + cy) for p in poly]


def tri45(leg, x=0, y=0):
    return [(x, y), (x + leg, y), (x, y + leg)]


def piece(pid, poly, fabric="F1", qty=1, label=None, meta=None):
    return {"id": pid, "polygon": poly, "fabric": fabric, "qty": qty,
            "label": label or ("P%s" % pid), "meta": meta or {}}


def ops_of(plan, fabric, kind=None):
    ops = plan["fabrics"][fabric]["ops"]
    return [o for o in ops if kind is None or o["op"] == kind]


# --- classification -------------------------------------------------------

def test_classify():
    c = cp.classify_piece(sq(4))
    check("classify square", c["kind"] == "square" and approx(c["w"], 4))
    c = cp.classify_piece(rot(sq(4), 45))
    check("classify on-point square",
          c["kind"] == "square" and approx(c["w"], 4),
          "got %s w=%.3f" % (c["kind"], c["w"]))
    c = cp.classify_piece(rect(6, 2))
    check("classify rect", c["kind"] == "rect"
          and approx(c["w"], 6) and approx(c["h"], 2))
    c = cp.classify_piece(tri45(3))
    check("classify tri45", c["kind"] == "tri" and c["is45"]
          and approx(c["legs"][0], 3))
    c = cp.classify_piece([(0, 0), (6, 0), (0, 2)])
    check("classify HRT", c["kind"] == "tri" and not c["is45"])
    hexagon = [(1, 0), (3, 0), (4, 1.7), (3, 3.4), (1, 3.4), (0, 1.7)]
    c = cp.classify_piece(hexagon)
    check("classify hexagon", c["kind"] == "other" and c["n"] == 6)


# --- template expansion / grain ------------------------------------------

def test_template_defaults():
    # Legacy piece with no meta: free grain, cut = finished + 2*SA.
    plan = cp.plan_cutting([piece(1, sq(8), qty=4)])
    strips = ops_of(plan, "F1", "strip")
    check("squares make one strip", len(strips) == 1,
          str(plan["fabrics"]["F1"]["ops"]))
    if strips:
        s = strips[0]
        check("strip height 8.5", approx(s["height"], 8.5))
        check("strip consumed 34", approx(s["consumed"], 34.0))
        check("subcut qty 4", sum(x["qty"] for x in s["subcuts"]) == 4)
        check("strip util 100%", s["util"] > 0.999)
    check("total = strip height",
          approx(plan["fabrics"]["F1"]["total_length_in"], 8.5))


def test_on_point_square_cut_to_grain():
    # A 4" square set on point must cut 4.5 x 4.5, not its 5.66 bbox.
    plan = cp.plan_cutting([piece(1, rot(sq(4), 45))])
    s = ops_of(plan, "F1", "strip")[0]
    check("on-point square strips at 4.5", approx(s["height"], 4.5))
    check("on-point square width 4.5", approx(s["subcuts"][0]["w"], 4.5))


def test_snap_eighth():
    # 3.3" finished + 0.5 = 3.8 -> snaps UP to 3.875 (3 7/8).
    plan = cp.plan_cutting([piece(1, sq(3.3))])
    s = ops_of(plan, "F1", "strip")[0]
    check("snap to eighth", approx(s["height"], 3.875))
    check("fmt_in eighths", cp.fmt_in(3.875) == '3⅞"', cp.fmt_in(3.875))
    check("fmt_in half", cp.fmt_in(8.5) == '8½"', cp.fmt_in(8.5))


# --- triangle pairing ------------------------------------------------------

def test_pairing_free():
    plan = cp.plan_cutting([piece(i, tri45(3)) for i in range(4)])
    strips = ops_of(plan, "F1", "strip")
    check("paired tris strip", len(strips) == 1)
    if strips:
        sc = strips[0]["subcuts"][0]
        check("2 pair rectangles", sc["qty"] == 2 and sc["contains"] == 2)
        check("pair secondary mentions diagonal",
              "diagonal" in (sc["secondary"] or ""))
        check("pair util ~100%", strips[0]["util"] > 0.999,
              "%.3f" % strips[0]["util"])


def test_pairing_fixed_blocked():
    meta = {"grain": "fixed"}
    plan = cp.plan_cutting([piece(1, tri45(3), meta=meta),
                            piece(2, tri45(3), meta=meta)])
    warn = " ".join(plan["fabrics"]["F1"]["warnings"])
    check("fixed same-orientation blocked", "could not be paired" in warn,
          warn)
    check("blocked tris go to panel",
          len(ops_of(plan, "F1", "panel")) == 1)


def test_pairing_fixed_complementary():
    meta = {"grain": "fixed"}
    plan = cp.plan_cutting([
        piece(1, tri45(3), meta=meta),
        piece(2, rot(tri45(3), 180, 1.0, 1.0), meta=meta)])
    strips = ops_of(plan, "F1", "strip")
    check("complementary fixed tris pair", len(strips) == 1
          and strips[0]["subcuts"][0]["contains"] == 2,
          str(plan["fabrics"]["F1"]))


# --- batch techniques ------------------------------------------------------

def test_hst2():
    pieces = ([piece(i, tri45(3), "A", meta={"technique": "hst2"})
               for i in range(4)]
              + [piece(10 + i, tri45(3), "B", meta={"technique": "hst2"})
                 for i in range(4)])
    plan = cp.plan_cutting(pieces)  # oversize default ON
    for fab in ("A", "B"):
        s = ops_of(plan, fab, "strip")
        check("hst2 %s one strip" % fab, len(s) == 1)
        if s:
            check("hst2 %s square = finished+1" % fab,
                  approx(s[0]["subcuts"][0]["w"], 4.0),
                  "%.3f" % s[0]["subcuts"][0]["w"])
            check("hst2 %s qty 2" % fab, s[0]["subcuts"][0]["qty"] == 2)
    note = " ".join(plan["notes"])
    check("hst2 oversize disclosed", "trimming allowance" in note, note)

    plan = cp.plan_cutting(pieces, {"oversize_batch": False})
    s = ops_of(plan, "A", "strip")[0]
    check("hst2 exact = finished+7/8", approx(s["subcuts"][0]["w"], 3.875))


def test_hst8():
    pieces = [piece(i, tri45(3), "A", meta={"technique": "hst8"})
              for i in range(16)]
    plan = cp.plan_cutting(pieces, {"oversize_batch": False})
    s = ops_of(plan, "A", "strip")[0]
    # 16 tris -> 2 grids of 2*(3+7/8) = 7.75
    check("hst8 grid size", approx(s["subcuts"][0]["w"], 7.75),
          "%.3f" % s["subcuts"][0]["w"])
    check("hst8 qty 2", s["subcuts"][0]["qty"] == 2)

    plan = cp.plan_cutting(
        [piece(i, tri45(3), "A", meta={"technique": "hst8"})
         for i in range(10)], {"oversize_batch": False})
    warn = " ".join(plan["warnings"])
    check("hst8 remainder falls back", "2-at-a-time" in warn, warn)


def test_fg4():
    goose = [(0, 0), (6, 0), (3, 3)]  # finished 6 x 3, right angle at apex
    sky = tri45(3)
    pieces = ([piece(i, goose, "G",
                     meta={"technique": "fg4", "batch_group": "g1"})
               for i in range(4)]
              + [piece(10 + i, sky, "S",
                       meta={"technique": "fg4", "batch_group": "g1"})
                 for i in range(8)])
    plan = cp.plan_cutting(pieces)  # oversize ON
    sg = ops_of(plan, "G", "strip")[0]["subcuts"][0]
    check("fg4 goose square oversize = 7.5", approx(sg["w"], 7.5),
          "%.3f" % sg["w"])
    check("fg4 goose qty 1", sg["qty"] == 1)
    ss = ops_of(plan, "S", "strip")[0]["subcuts"][0]
    check("fg4 sky square oversize = 4", approx(ss["w"], 4.0),
          "%.3f" % ss["w"])
    check("fg4 sky qty 4", ss["qty"] == 4)

    plan = cp.plan_cutting(pieces, {"oversize_batch": False})
    sg = ops_of(plan, "G", "strip")[0]["subcuts"][0]
    check("fg4 goose exact = 7.25", approx(sg["w"], 7.25), "%.3f" % sg["w"])
    ss = ops_of(plan, "S", "strip")[0]["subcuts"][0]
    check("fg4 sky exact = 3.875", approx(ss["w"], 3.875))


def test_templates_only_override():
    pieces = [piece(i, tri45(3), "A", meta={"technique": "hst2"})
              for i in range(4)]
    plan = cp.plan_cutting(pieces, {"use_techniques": False})
    s = ops_of(plan, "A", "strip")
    check("templates-only pairs instead of batches",
          len(s) == 1 and s[0]["subcuts"][0]["contains"] == 2,
          str(plan["fabrics"]["A"]["ops"]))


# --- stitch and flip -------------------------------------------------------

def test_snowball_plain_base():
    # 6x4 unit, corner triangle leg 2 at top-right.
    tri = [(4, 0), (6, 0), (6, 2)]
    base = [(0, 0), (4, 0), (6, 2), (6, 4), (0, 4)]
    ext, err = cp.snowball_extend(tri, [base])
    check("snowball plain: ok", err is None, str(err))
    if not err:
        c = cp.classify_piece(ext[0])
        check("snowball plain: base restored to 6x4 rect",
              c["kind"] == "rect" and approx(c["w"], 6)
              and approx(c["h"], 4), str(c))

    plan = cp.plan_cutting([
        piece("t", tri, "C", meta={"technique": "stitch_flip",
                                   "sf_bases": ["b"]}),
        piece("b", base, "M")])
    sc = ops_of(plan, "C", "strip")[0]["subcuts"][0]
    check("snowball corner square 2.5", approx(sc["w"], 2.5))
    sm = ops_of(plan, "M", "strip")[0]["subcuts"][0]
    check("snowball base cut 6.5", approx(sm["w"], 6.5), "%.3f" % sm["w"])
    check("snowball bonus note",
          any("bonus HST" in n for n in plan["notes"]))


def test_snowball_pieced_base():
    # 6x4 unit split at x=5; corner triangle leg 2 at top-right spans both.
    tri = [(4, 0), (6, 0), (6, 2)]
    b1 = [(0, 0), (4, 0), (5, 1), (5, 4), (0, 4)]
    b2 = [(5, 1), (6, 2), (6, 4), (5, 4)]
    ext, err = cp.snowball_extend(tri, [b1, b2])
    check("snowball pieced: ok", err is None, str(err))
    if not err:
        c1 = cp.classify_piece(ext[0])
        c2 = cp.classify_piece(ext[1])
        check("snowball pieced: b1 -> 5x4 rect",
              c1["kind"] == "rect" and approx(c1["w"], 5)
              and approx(c1["h"], 4), str(c1))
        check("snowball pieced: b2 -> 4x1 rect",
              c2["kind"] == "rect" and approx(c2["w"], 4)
              and approx(c2["h"], 1), str(c2))


def test_snowball_refusal():
    # Missing one base: cells cannot tile the corner -> refuse.
    tri = [(4, 0), (6, 0), (6, 2)]
    b2 = [(5, 1), (6, 2), (6, 4), (5, 4)]
    ext, err = cp.snowball_extend(tri, [b2])
    check("snowball refuses partial base set", ext is None and err,
          str(err))

    plan = cp.plan_cutting([
        piece("t", tri, "C", meta={"technique": "stitch_flip",
                                   "sf_bases": ["b2"]}),
        piece("b2", b2, "M")])
    warn = " ".join(plan["warnings"])
    check("snowball refusal warns + falls back",
          "not applied" in warn, warn)


def test_noisy_triangle_classification():
    # EQ-import wobble: extra near-collinear vertices on the hypotenuse
    # (real regression: block piece E1 with two seam endpoints on the
    # diagonal, off-line by ~0.0001").
    noisy = [(4.0, 6.0), (8.0, 6.0), (5.5, 8.5001), (5.25, 8.7499),
             (4.0, 10.0)]
    c = cp.classify_piece(noisy)
    check("noisy tri classifies as tri", c["kind"] == "tri", str(c))
    check("noisy tri is45", c["is45"])
    check("noisy tri legs 4", approx(c["legs"][0], 4.0, 0.01))
    check("noisy congruence matches clean",
          cp.congruence_key(noisy, tol=0.01)
          == cp.congruence_key([(4, 6), (8, 6), (4, 10)], tol=0.01))


def test_snowball_three_bases():
    # A 4" corner triangle flipping onto THREE pieces along its seam
    # (real regression: E1 over E2 + E5 + E10). Guillotine junctions:
    # y=8.5 between E2/E5, x=5.25 between E5/E10.
    tri = [(4.0, 6.0), (8.0, 6.0), (5.5, 8.5), (5.25, 8.75), (4.0, 10.0)]
    e2 = [(8.0, 6.0), (11.5, 6.0), (11.5, 8.5), (5.5, 8.5)]
    e5 = [(5.25, 10.1667), (5.25, 8.75), (5.5, 8.5), (6.9168, 8.5),
          (6.9168, 10.1667)]
    e10 = [(5.25, 8.75), (5.25, 13.5), (4.0, 13.5), (4.0, 10.0)]
    ext, err = cp.snowball_extend(tri, [e2, e5, e10])
    check("3-base snowball ok", err is None, str(err))
    if not err:
        kinds = [cp.classify_piece(x)["kind"] for x in ext]
        check("3-base extensions all rects",
              all(k in ("rect", "square") for k in kinds), str(kinds))
        c2 = cp.classify_piece(ext[0])
        check("E2 extended to 7.5 x 2.5",
              approx(c2["w"], 7.5, 0.01) and approx(c2["h"], 2.5, 0.01),
              str(c2))
    # Missing one base -> seam not covered -> clear refusal
    ext, err = cp.snowball_extend(tri, [e2, e10])
    check("missing base refused with guidance",
          ext is None and "every piece" in (err or ""), str(err))


def test_snowball_double_layer():
    # Double-layer corner (real regression, A unit): A2 (1" corner) is
    # sewn onto square A1 FIRST, then A4 (2" corner) flips over the top,
    # leaving only a 0.7"-leg sliver of A2 visible. A2's tag must be
    # analysed on its extended pre-trim footprint (restored by processing
    # A4's tag first), regardless of piece order in the list.
    a1 = [(10, 1), (10, 2), (8, 2), (9.5, 0.5)]
    a2 = [(10, 1), (9.5, 0.5), (10, 0)]
    a4 = [(8, 0), (10, 0), (9.5, 0.5), (8, 2)]
    pieces = [
        piece("a2", a2, "C2", label="A2",
              meta={"technique": "stitch_flip", "sf_bases": ["a1"]}),
        piece("a1", a1, "M", label="A1"),
        piece("a4", a4, "C4", label="A4",
              meta={"technique": "stitch_flip", "sf_bases": ["a1", "a2"]}),
    ]
    corners, overrides, warns = cp.resolve_stitch_flips(pieces)
    check("double-layer: no warnings", not warns, str(warns))
    check("double-layer: both corners resolved",
          set(corners) == {"a2", "a4"}, str(set(corners)))
    if "a2" in corners:
        check("double-layer: A2 legs restored to 1\"",
              approx(corners["a2"]["legs"][0], 1.0, 0.02),
              str(corners["a2"]["legs"]))
    c1 = cp.classify_piece(overrides.get("a1", a1))
    check("double-layer: A1 restored to full 2\" square",
          c1["kind"] == "square" and approx(c1["w"], 2.0, 0.02), str(c1))

    plan = cp.plan_cutting(pieces)
    sq = {}
    for fab in ("M", "C2", "C4"):
        ops = ops_of(plan, fab, "strip")
        if ops:
            sq[fab] = ops[0]["subcuts"][0]["w"]
    check("double-layer: A1 cuts 2.5 sq", approx(sq.get("M", 0), 2.5),
          str(sq))
    check("double-layer: A2 cuts 1.5 sq", approx(sq.get("C2", 0), 1.5),
          str(sq))
    check("double-layer: A4 cuts 2.5 sq", approx(sq.get("C4", 0), 2.5),
          str(sq))


def test_snowball_detect():
    tri = [(4, 0), (6, 0), (6, 2)]
    base = [(0, 0), (4, 0), (6, 2), (6, 4), (0, 4)]
    outline = rect(6, 4)
    ids = cp.detect_snowball_candidates(
        [piece("t", tri), piece("b", base)], outline)
    check("detect finds corner tri", ids == ["t"], str(ids))


# --- 50% utilisation rule --------------------------------------------------

def test_util_rule():
    # Thin L-shape (6 vertices, ~10% of bbox) rides in the square's strip
    # and drags utilisation below 50% -> whole strip dissolves to panel.
    lshape = [(0, 0), (8, 0), (8, 4), (7.8, 4), (7.8, 0.2), (0, 0.2)]
    plan = cp.plan_cutting([piece(1, sq(4)), piece(2, lshape)])
    fab = plan["fabrics"]["F1"]
    check("low-util strip dissolves",
          len([o for o in fab["ops"] if o["op"] == "strip"]) == 0,
          str(fab["ops"]))
    check("dissolved pieces on panel",
          len([o for o in fab["ops"] if o["op"] == "panel"]) == 1)
    check("dissolve note", any("utilisation" in n for n in fab["notes"]),
          str(fab["notes"]))


def test_util_rule_keeps_good_strip():
    hexagon = [(1, 0), (3, 0), (4, 1.7), (3, 3.4), (1, 3.4), (0, 1.7)]
    plan = cp.plan_cutting([piece(1, sq(4), qty=3), piece(2, hexagon)])
    fab = plan["fabrics"]["F1"]
    strips = [o for o in fab["ops"] if o["op"] == "strip"]
    check("good strip survives with odd shape aboard",
          len(strips) == 1 and strips[0]["util"] >= 0.5,
          str(fab["ops"]))


# --- pieced strips (over-WOF) & binding -------------------------------------

def test_pieced_strips():
    # 2" finished border on a 50x54 quilt: 2 x 50.5 + 2 x 54.5 cut pieces.
    pieces = [piece(1, rect(50.0, 2.0), "B", qty=2, label="side"),
              piece(2, rect(54.0, 2.0), "B", qty=2, label="topbot")]
    plan = cp.plan_cutting(pieces)
    ps = ops_of(plan, "B", "pieced_strip")
    check("one pieced strip group", len(ps) == 1, str(plan["fabrics"]["B"]))
    if ps:
        op = ps[0]
        check("pieced width 2.5", approx(op["width"], 2.5))
        check("pieced strips = 6", op["strips"] == 6, str(op["strips"]))
        check("pieced join straight", op["join"] == "straight")
        check("pieced run 210", approx(op["run"], 210.0))
    note = " ".join(plan["fabrics"]["B"]["notes"])
    check("straight-join note mentions long-arm", "long-arm" in note, note)

    plan = cp.plan_cutting(pieces, {"border_join": "diagonal"})
    op = ops_of(plan, "B", "pieced_strip")[0]
    check("diagonal join allowance", op["join_allow"] == 2.5)


def test_pieced_strip_riders():
    # A 2.5"-cut square (2" finished) shares the border strips.
    pieces = [piece(1, rect(50.0, 2.0), "B", qty=2),
              piece(2, sq(2.0), "B", qty=4)]
    plan = cp.plan_cutting(pieces)
    fab = plan["fabrics"]["B"]
    ps = [o for o in fab["ops"] if o["op"] == "pieced_strip"]
    check("riders merge into pieced strips",
          len(ps) == 1 and len([o for o in fab["ops"]
                                if o["op"] == "strip"]) == 0,
          str(fab["ops"]))
    if ps:
        total_cuts = sum(c["qty"] for c in ps[0]["cuts"])
        check("rider cuts included", total_cuts == 6, str(ps[0]["cuts"]))


def test_binding():
    b = cp.binding_plan(50.0, 54.0)  # run = 218
    check("binding run", approx(b["run"], 218.0))
    check("binding strips", b["strips"] == 6, str(b["strips"]))
    check("binding diagonal", b["join"] == "diagonal")
    check("binding text", "diagonal" in b["text"], b["text"])


# --- fussy + fpp-vs-template margins ----------------------------------------

def test_fussy():
    plan = cp.plan_cutting(
        [piece(1, rot(sq(4), 45), meta={"grain": "fussy"})])
    fab = plan["fabrics"]["F1"]
    panels = [o for o in fab["ops"] if o["op"] == "panel"]
    check("fussy goes to panel", len(panels) == 1
          and len([o for o in fab["ops"] if o["op"] == "strip"]) == 0,
          str(fab["ops"]))
    if panels:
        pl = panels[0]["placements"][0]
        check("fussy keeps design rotation", pl["rot"] == 0.0)
        w, h = (max(p[0] for p in pl["poly"]) - min(p[0] for p in pl["poly"]),
                max(p[1] for p in pl["poly"]) - min(p[1] for p in pl["poly"]))
        # on-point 4" square bbox = 5.657 + 2*SA*sqrt(2) miters ~ 6.36
        check("fussy uses SA-only margin", 5.9 < w < 6.6, "%.3f" % w)


def test_congruence_key():
    k1 = cp.congruence_key(sq(4))
    k2 = cp.congruence_key(rot(sq(4), 45, 2, 2), tol=0.01)
    check("congruence: rotated square matches",
          cp.congruence_key(sq(4), tol=0.01) == k2)
    check("congruence: translated square matches",
          k1 == cp.congruence_key(sq(4, x=7, y=3)))
    check("congruence: different size differs",
          cp.congruence_key(sq(4)) != cp.congruence_key(sq(3)))
    check("congruence: rect vs rotated rect",
          cp.congruence_key(rect(6, 2), tol=0.01)
          == cp.congruence_key(rot(rect(6, 2), 90), tol=0.01))
    hrt = [(0, 0), (6, 0), (0, 2)]
    hrt_mirror = [(0, 0), (-6, 0), (0, 2)]
    check("congruence: mirror differs (needs own template)",
          cp.congruence_key(hrt, tol=0.01)
          != cp.congruence_key(hrt_mirror, tol=0.01))
    check("congruence: same tri45 matches at any rotation",
          cp.congruence_key(tri45(3), tol=0.01)
          == cp.congruence_key(rot(tri45(3), 135, 1, 1), tol=0.01))


def test_format_text():
    plan = cp.plan_cutting([piece(1, sq(8), qty=4)])
    lines = cp.format_ops_text(plan["fabrics"]["F1"])
    check("format text strip line",
          any("Cut 1 strip" in l and "8½" in l for l in lines), str(lines))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        raise SystemExit(1)
