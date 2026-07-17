# Design: Technique-Aware Fabric Requirements & Cutting Plans

Status: IMPLEMENTED (v1.6, July 2026) — see CHANGELOG. Quilt-level wiring (§5 quilt
export aggregation, §2.6 binding surfacing) remains open until the quilt export tool
exists; `binding_plan()` and the qty-aware planner are already in place for it.

Addendum 2 (v1.6.3): hybrid exports — sections tagged "Always FPP"
(`prefs["fpp_sections"]`, set via the Mark tool) print as FPP foundation
templates inside a Template export and are costed with the padded FPP estimate
folded into each fabric's total. HST sewing-line templates (one per unique
2-at-a-time square size) print optionally; square/rect pieces can be demoted to
cutting-list-only; technique-consumed pieces (S&F corners, batch triangles)
never print shape templates; cutting instructions paginate across multiple
pages via a cached row stream.

Addendum (same release): template PAGES gained a "Duplicate Templates" option — print
every piece, or one template per unique SHAPE labelled "cut N" with the covered piece
labels. Colours combine: a shared template spanning multiple fabrics prints uncoloured
("mixed fabrics - see layout page" caption + page-header note + run-time tip to print
the Section Map page). Mirrored pieces always keep their own template. Dedupe affects
printed templates only; cutting instructions and fabric totals always account for every
piece.
Scope: fabric requirements / cutting layout for **both** single Block Pattern Export and
quilt-level pattern export (shared engine).

---

## 1. Goal

Fabric requirements should reflect **how the piece will actually be cut**, which depends on
the construction technique, not just the piece's finished geometry:

| Export type (existing option) | Fabric requirement style |
|---|---|
| `fpp` (FPP Foundation) | **Unchanged.** Generous padded bounding boxes (current ¾" pad), because FPP pieces are rough-cut oversize. |
| `template` | **New.** Exact template shapes (finished + seam allowance), grouped into strip-and-subcut instructions, technique-aware (stitch-and-flip, 2/8-at-a-time HST, 4-at-a-time flying geese, fussy cut). |

No new required inputs: an un-annotated legacy SVG must export exactly as today in `fpp`
mode, and produce a sensible default cut plan in `template` mode.

---

## 2. Cutting rules the engine must encode

### 2.1 Grain / rotation policy

**DECIDED: `free` is the default; `fixed` is the opt-in** (for directional prints etc.).

| Grain tag | Squares / rects / triangles | Unusual shapes (>4 sides) |
|---|---|---|
| `free` (default) | Rotations of **0/90/180/270 only** — keeps edges on grain, never bias | **Any rotation** allowed (helps panel nesting) |
| `fixed` (opt-in) | Design orientation only (0°) | "Top of block is up" is the correct orientation |
| `fussy` (user-defined, not normal) | Placed at exact design rotation, excluded from strips, individually boxed | same |

- **Squares / rectangles**: always cut square-to-grain (axis-aligned), even if set on point
  in the design. On-point cutting is fussy cutting, opt-in only.
- **45° right triangles** (HST/QST halves): cut with legs on grain, hypotenuse on bias
  (standard practice); under `free` they rotate in 90° steps for pairing/nesting.
- **Fussy cut margin**: same as every other piece for the active export mode —
  SA-only in template mode, +¾" pad in FPP mode. No special margin.

### 2.2 Technique formulas (verified against standard references, ¼" SA)

- **Plain template**: finished shape + SA offset (existing `core.offset_polygon` with
  `sa_in`, replacing the FPP ¾" pad in template mode).

- **Stitch-and-flip (snowball) corner**: both fabrics cover the full corner footprint
  before trimming:
  - corner square cut = finished corner leg + ½" (2×SA);
  - the base is cut **UN-snowballed** — see §2.3 for the pieced-base case;
  - primarily a 45° technique. Permit on rectangles (half-rectangle corners) but emit a
    "template method usually preferred" warning;
  - optional note line in output: bonus HSTs available from the trimmed corners.

- **2-at-a-time HST** (per unit): 1 square of *each* fabric.
  - **DECIDED default: finished + 1" (oversize & trim).** The fabric page states up front:
    "HST squares include ⅛" extra for trimming — disable 'Oversize batch units' to cut
    exact (finished + ⅞")."
- **8-at-a-time HST** (per 8 units): 1 square of each fabric at 2 × (finished + ⅞");
  oversized variant 2 × (finished + 1").
- **4-at-a-time flying geese** (per 4 geese, no-waste): 1 large square = finished width
  + 1¼" (goose fabric); 4 small squares = finished height + ⅞" (sky fabric).
  - **Oversized-for-trimming variant (option, same low-waste method): large = finished
    width + 1½", small = finished height + 1"** (standard published oversize; +¼" / +⅛"
    over exact). Geese are 2:1; validate and warn otherwise.

- One export option **"Oversize batch units for trimming" (default ON)** governs all three
  batch techniques; the fabric page always states which sizing is in effect so the user
  can opt out.

- Batch techniques replace the individual triangle templates with parent squares in the
  cut list — quantities must be consistent (e.g. hst8 needs triangle count ≡ 0 mod 8 per
  fabric pairing; remainder falls back to hst2 or plain templates with a report line).

### 2.3 Stitch-and-flip over a PIECED base (guillotine seam extension)

A S&F corner may land on a unit that is itself pieced — the corner footprint can cover
parts of **several** pieces. Every affected piece must be extended so the assembled base
still covers the full footprint before the corner is trimmed.

Mechanism (guillotine logic):

1. Take the corner triangle's footprint and the set of neighbour pieces whose edges touch
   it.
2. Every straight seam that terminates on the corner's hypotenuse is **continued straight**
   until it exits the corner footprint (or hits another continued seam). This partitions
   the footprint guillotine-style.
3. Each partition cell is assigned to the piece whose seam line bounds it; that piece's
   cut shape = union(original region, its cells) + SA.
4. **Stop condition**: if a continued seam would intersect the interior of a piece that is
   not adjacent along that seam (non-guillotine layout), the tool refuses the tag with a
   clear message ("corner overlaps pieced seam that cannot be extended cleanly — use a
   template for this corner") rather than guessing.

Single-piece bases are just the trivial case (no seams to extend → union restores the
plain rectangle). `sf_base` therefore becomes `sf_bases: [region_id, ...]`, computed and
stored by the Mark tool at tagging time (with the partition geometry re-derived at export
so resizing works).

### 2.4 Strip & subcut grouping (template mode)

1. Per fabric (colour group, as today), classify every cut unit; identical-height units
   group into a **strip**: `Cut 1 strip H × WOF; subcut N × (shape)`. Secondary
   instructions supported (e.g. square → "cut once on the diagonal" for paired triangles).
2. **Pairing pass**: leftover same-size 45° triangles on the same fabric nest in pairs,
   180° hypotenuse-to-hypotenuse, into a 2-template rectangle (computed geometrically from
   the SA-offset templates, not by formula). Pairs then join strips like any rectangle.
   Default `free` grain (90° increments) makes most triangles pairable; **pieces tagged
   `fixed` can only pair when their design orientations already complement**, so the
   planner reports pairs it could NOT form because of grain locks.
3. **Odd shapes** (≥5 sides): try to fit inside an existing strip's subcut segments
   (their SA-offset bbox height ≤ strip height); otherwise cut separately.
4. **50% utilization rule** (accepted, subject to review in practice): only recommend a
   strip if placed template area ≥ 50% of (strip height × consumed strip length). Below
   that, place those pieces on the open yardage panel via the existing NFP nester
   (`quilttools_nesting.py`) with rotations per the grain policy ({0,90,180,270} free /
   {0} fixed / free-angle for >4-sided free pieces / design angle for fussy).
5. Strips sort tallest-first from the cut edge; the yardage panel sits after the last
   strip; total requirement = strips + panel height (+ existing suggested-purchase
   rounding).

### 2.5 Pieces longer than usable WOF (borders, rails) — pieced strips

Reserved design space; needed the moment quilt-level export lands (e.g. 2" finished border
on a 50" quilt → cut pieces of 2½" × 50½"/54½" against ~40" usable WOF).

- Any required rectangle **longer than usable WOF** routes to the **pieced-strip
  planner** for its strip-width group:
  1. Total run = Σ(piece lengths) + join allowance per seam. **DECIDED: straight joins
     are the default for borders** (½" per seam) — long-armers prefer them; a
     "diagonal joins" option exists per fabric run (costs strip-width extra per join).
     Mitered-corner borders are out of scope here and will be handled separately.
  2. `strips_needed = ceil(total_run / usable_WOF)`; lengths are shared across strips by
     first-fit-decreasing so each long piece carries as few joins as possible and joins
     land away from piece ends where the packing allows.
  3. Output `CutOp` type `pieced_strip`: "Cut 6 strips 2½" × WOF; join end-to-end with
     straight seams; subcut 2 × 54½", 2 × 50½"."
- Under-WOF pieces in the same width group may ride along in these strips when it saves a
  strip (they count toward the same utilization figure).

### 2.6 Binding (quilt-level line item)

Quilt-level fabric requirements include a dedicated binding entry:

- Required run = **2 × quilt length + 2 × quilt width + 10" slack** (the 10" "fat" is an
  adjustable option).
- **Joins are ALWAYS diagonal for binding** (opposite of borders) — each join consumes
  strip-width extra, included in the strip count.
- `strips_needed = ceil(run_with_joins / usable_WOF)` at the user's binding strip width
  (default 2½", option); output: "Binding: cut 7 strips 2½" × WOF; join with diagonal
  seams; makes ~270" of binding."
- Lives in the cutplan module as a pure helper so the quilt export and the Fabric
  Calculator both use it; block-level export never shows it.

---

## 3. Data model: how techniques are recorded (backwards compatible)

**Source of truth**: a new optional key inside the existing `BlockData.prefs` JSON blob
(stored in `<desc id=FPP_DATA_TAG_ID>`):

```json
"piece_meta": {
  "<region_id>": {
    "grain":     "free" | "fixed" | "fussy",       // default free
    "technique": "template" | "stitch_flip" | "hst2" | "hst8" | "fg4",  // default template
    "sf_bases":  [<region_id>, ...],  // stitch_flip only: pieces extended under the corner
    "batch_group": "hst-red-3in-1",   // hst2/hst8/fg4: pieces cut from the same parent square(s)
    "suggested": true                 // set by auto-detect, cleared when user confirms
  }
}
```

Why this is safe:
- Old SVGs simply lack the key → every piece defaults to `template`/`free` → geometry
  identical to today (rotation freedom only affects the new template-mode planner).
- Old tool versions round-trip `prefs` as a dict and ignore unknown keys → forward
  compatible.
- Region ids are already stable and already exposed on canvas paths as
  `data-fpp-region-id`, so selection-based tagging needs no new SVG markup.
- On load, `BlockData` prunes `piece_meta` entries whose region id no longer exists
  (piece deleted/re-split), so stale tags can't corrupt a plan.

No change to `Region`/`RegionTree` serialization.

---

## 4. User workflow for tagging: new tool "Mark Cutting Technique"

New extension `quilttools_fpp_mark_technique.py/.inx` (menu: Quilt Tools, after Labels).
Selection-based, same interaction style as Save Colors:

1. User selects region path(s) on canvas (mapped via `data-fpp-region-id`).
2. Dialog options:
   - **Technique**: Default (template) / Stitch-and-flip corner / HST 2-at-a-time /
     HST 8-at-a-time / Flying geese 4-at-a-time / Fussy cut / Clear tags.
   - **Grain**: Keep default (free) / Direction fixed / Fussy (use design rotation).
   - **Show marked corners** (action): renders the review card, see below.
   - **Auto-detect candidates in whole block** (bool, ignores selection).
3. Writes `piece_meta`, then decorates the canvas with small marker glyphs (diagonal
   "flip" arrow for S&F, "×4"/"×8" badges for batches) on a dedicated annotation layer that
   export ignores — visual confirmation without touching pattern geometry.

### Stitch-and-flip pairing logic

**DECIDED: S&F is applied ONLY via the Mark tool** (never auto-applied at export) — it is
the one technique that rewrites neighbouring pieces' cut shapes, so it stays deliberate.

- User selects the **triangle**; the tool finds the base pieces automatically via the
  guillotine seam-extension analysis of §2.3 (adjacency on the hypotenuse + straight seam
  continuation). Result stored as `sf_bases`.
- Validation before accepting: triangle has two ~90° legs on the parent unit's outline and
  a 45° hypotenuse; the seam extension terminates cleanly (§2.3 stop condition). Ambiguous
  or non-guillotine → refuse with a specific message; the user can select triangle + base
  pieces together to assert the pairing explicitly, which is then re-validated.
- **Auto-detect mode** scans all leaf regions for corner triangles meeting the same
  criteria, writes tags with `"suggested": true`, and reports what it found. Export treats
  suggested tags as active but lists them on the fabric page as "auto-detected — verify".

### Marked-corner review visual

Because `.inx` dialogs are static, the "little text box" is a **review card drawn on the
annotation layer** next to the block (plus a plain-text summary via the message stream):
a mini outline of the block with every marked S&F corner shaded and numbered, and a
legend line per corner: `1: corner sq 2½" (Fabric B) flips onto A3+A4 [auto — verify]`.
**The card covers ALL technique tags**, one section per technique: S&F corners, HST
2/8-at-a-time batch groups, flying-geese groups, fussy-cut and grain-fixed pieces.
Re-running "Show marked corners" refreshes the card; it is never exported.

### Batch techniques (hst2/hst8/fg4)

- User selects the matching triangles (any number); tool groups them by (fabric pair,
  finished size), assigns `batch_group` ids, and reports the parent-square yield
  ("12 triangles → 2 × 8-at-a-time squares per fabric, 4 left as pairs").
- Flying geese: select goose (QST) triangles; sky corners are matched by adjacency.

---

## 5. One engine, two entry points (block export AND quilt export)

`quilttools_cutplan.py` is pure data-in/data-out. Canonical input is a flat list:

```
CutPiece(polygon_finished, fabric_key, qty, meta, source_label)
```

- **Block Pattern Export** feeds it one block's leaf regions (qty = template_copies).
- **Quilt pattern export** (when quilt-level export lands) aggregates CutPieces across
  `QuiltData`: every block instance × its count (piece_meta travels with the library
  block), plus sashing, cornerstones, binding, and border rectangles — the latter flowing
  through the §2.5 pieced-strip planner. Larger piece populations are exactly where the
  strip/batch logic pays off, so nothing in the planner may assume "one block's worth" of
  pieces (no per-block state, quantities always explicit).
- The Fabric Calculator tool can call the same function later for a text-only estimate.

---

## 6. Code changes

| File | Change |
|---|---|
| `quilttools_cutplan.py` (new) | Pure-python planner, unit-testable like `quilttools_nesting.py`: shape classification (square/rect/45-triangle/other + design rotation vs grain), technique expansion (S&F guillotine extension, batch parent squares incl. oversize variants), strip builder with 50% rule + pairing pass, pieced-strip planner for over-WOF lengths, NFP fallback for the yardage panel. Outputs structured `CutOp` list (strip / subcut / diagonal-cut / pieced_strip / individual / panel placement) + totals + warnings (incl. pairs blocked by `fixed` grain). No SVG. |
| `quilttools_fpp_fabric.py` | Refactor (removing the dead code after `calculate_fabric_requirements`'s return at line 170 and the broken `fabric_estimate`). Keep FPP padded-box path as-is; add `calculate_template_requirements(pieces, wof, sa_in, options)` delegating to cutplan; new `draw_cutting_plan_map` rendering strips, subcut lines, diagonal cuts, pieced-strip joins and exact template outlines. |
| `quilttools_fpp_mark_technique.py/.inx` (new) | Tagging tool per §4, incl. S&F guillotine analysis and the marked-corner review card. |
| `quilttools_fpp_core.py` | `piece_meta` accessors + prune-on-load; polygon adjacency + seam-extension helpers (shared with auto-labeller adjacency family). |
| `quilttools_fpp_export.py` | Fabric Requirements page keys off existing `export_type`: `fpp` → current table + note that padding is included; `template` → cutting-instruction table + cut-plan map, up-front note on batch oversizing, footnote listing technique tags in effect. New options: "Oversize batch units for trimming" (bool, default true) and **"Cutting math" combo: *Use marked techniques* (default) / *Templates only*** — the latter ignores all technique tags for this export (S&F corners revert to their exact clipped template shapes, batch triangles cut individually), for block-only exports of a block that is tagged for use inside larger quilts. Grain tags still apply. No breaking `.inx` changes. |
| `test_cutplan.py` (new) | Classification snapping; S&F expansion on plain AND pieced bases (guillotine cases + refusal case); hst2 (1" default / ⅞" exact), hst8, fg4 exact & oversized vs published tables; 50% rule boundary; grain-constrained rotations incl. fixed-blocked pairing; pieced-strip border maths (50" quilt example, straight vs diagonal join costs); binding run/strip count (2L+2W+10"); templates-only override strips all technique expansion; legacy-SVG defaults. |

Suggested build order: cutplan module + tests → fabric refactor + export template page →
mark-technique tool (incl. review card) → auto-detect pass → quilt-level wiring when the
quilt export tool exists.

---

## 7. Decisions log / remaining open items

Decided this round:
- Grain default is `free` (90° increments; any angle for >4-sided pieces); `fixed` opt-in;
  fussy = user-defined, uncommon.
- HST2 default cut = finished + 1" with up-front disclosure and an opt-out to exact ⅞";
  FG4 gets an oversized low-waste variant (+1½"/+1") behind the same option.
- S&F only ever applied from the Mark tool; review card visual for marked corners.
- S&F must handle pieced bases via guillotine seam extension, refusing non-guillotine
  overlaps.
- Fussy pieces use the standard margin for the export mode (SA in template, ¾" in FPP).
- 50% utilization definition accepted pending real-world review.
- Engine must serve both block and quilt export; over-WOF pieces get pieced-strip plans.
- Border strip joins: straight by default (long-armer preference), diagonal as an option;
  mitered-corner borders handled separately later.
- Binding added as a quilt-level line item: 2L + 2W + 10" slack (adjustable), always
  diagonal joins, own strip-count output.
- Review card lists all technique tags, one section per technique.
- Export gains a "Templates only" override that ignores technique tags for a block-only
  export while keeping grain tags.

Still open: none — ready to build pending final review.
