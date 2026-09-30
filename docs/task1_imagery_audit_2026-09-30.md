# Task 1 Imagery Audit — 2026-09-30

A hands-on pass while waiting on Stephanie's Extension farm list: render real crops
from tiles already on disk, actually look at them, and log what's true — not what the
pipeline reports. 33 new farms, chosen to fill the gaps the 2026-09-23 field guide's
23 figures didn't cover: every remaining dairy farm, every remaining laying-hen farm,
every "unknown species" registry entry, the second duck farm, and a random sample of
10 ordinary broiler farms never looked at before. All imagery is from
`data/raw/naip_tiles_pc_4band_full` (already downloaded, 417 farms, nothing new
fetched). Script: `scripts/render_species_audit_batch.py`, seed `20260930`, fixed
farm list printed in the script itself — reproducible.

33 crops rendered, side-by-side (clean | detections overlaid), 900m × 900m, at
`data/processed/species_audit_screenshots/`. 24 of the 33 were actually opened and
read this session; the remaining 9 poultry_random crops were rendered but not
individually reviewed — their detection counts are in `audit_manifest.json` if
needed later.

## 1. Dairy — full census now complete (14/14 farms reviewed)

Combined with the 5 dairy farms in the 2026-09-23 guide, all 14 registered dairy
farms have now been looked at directly. Corrected count: **13 of 14 return zero
building detections**, not "11 of ~14" as `labeling_guide.md` previously said — only
Oakland View Farms has any detection, and even that one is a partial outline of a
single barn.

What the missed structures actually look like, confirmed on-screen:

- **Wide, blocky, clustered barns**, not the long, narrow, evenly-spaced parallel
  houses the shape filter is tuned for. Matthew Hoff/Coldsprings Farms and David
  Pyle/Cow Comfort Inn Dairy are the clearest examples — real, large, obvious dairy
  operations, zero detections, because the building footprints simply don't match
  the target aspect ratio at all.
- **Round tower silos and round tanks are everywhere** at dairy sites and are
  correctly excluded by the aspect filter (as designed) — but that also means there
  is no class that *records* them. David Pyle has two visible round tanks next to
  the barns; Matthew Hoff has a large round silo. These come up often enough that
  "round tank near a barn cluster" is a real, recurring dairy signature worth its
  own detector, not just a rejected shape.
- **Real, visually obvious lagoon-type ponds the lagoon detector completely
  misses.** Teabow, Arbaugh's Flowering Springs, Patterson Farms, and Deerspring
  Dairy Farm all show a dark, rectangular, well-banked pond immediately next to the
  barns — exactly what a manure lagoon looks like — and none of them produced a
  lagoon candidate. These read as dark brownish-olive, not the bright teal the
  color check in `labeling_guide.md` was calibrated on. That's a plausible concrete
  reason the candidate-generation step never even proposes a box here: the color
  threshold may simply not fire on this shade of water.
- **Registry-point/real-structure mismatch happens on dairy too.** Mason Dixon
  Farms and My Lady's Manor Farm both have the registry coordinate sitting in open
  field or forest, with the real barn complex two to four hundred meters away —
  the same pattern already documented for Fry and Oak Bluff.
- **One farm, Whitelyn Farms, has no visible conventional dairy structure at all**
  within 450m of the registry point — no barns, no silos, just a house and what
  looks like a riding ring. This may be exactly the small, under-CAFO-threshold
  dairy operation Stephanie described in the Sept 9 meeting — worth a direct
  question to her rather than guessing.

## 2. "Unknown species" registry entries — 6 of 9 are easy, immediate fixes

All 9 registry entries with no recorded `animal_type` were reviewed. This is the
highest-value finding of this pass:

- **6 are unambiguous broiler/poultry operations**, confidently identifiable from
  the roofline alone, several with the model already detecting most or all houses
  correctly: Hannah Jones (8/9 houses detected), Bawi Hlun/Chan UK (9 detected),
  Adam Stanley/Deathly Hollows (7 detected), Eldwin Martin/Airview Farm (7
  detected), Muhammad Usman/H & N Farm (4 detected), Dustin Calloway/Clay Island
  Farm (19 detected, though see below). These are direct, confident registry
  corrections — `animal_type: unknown` → `chickens_not_laying_hens` — that don't
  need a site visit to confirm.
- **1 is not a standard livestock building at all.** Alan & Kristin Hudson's
  registry point sits on what looks like a nursery or composting/utility facility —
  gravel yards, a large mulch pile, a water tower, rows of nursery stock. No barn
  shape anywhere in view. "Unknown species" may be the *correct* label here, not a
  gap — this looks like a registry entry that doesn't fit the AFO categories at
  all, worth flagging to Alisha Mulkey/MDA rather than trying to force a species
  guess.
- **2 have no visible structure near the registry point at all** (Robert
  Rosado/Northwind Farm, Chasin Dreams Farm) — both points land in forest, with
  nothing identifiable within 450m. Same geocode-error pattern as Fry/Oak Bluff;
  can't determine species from imagery without a wider search or a corrected
  coordinate.
- **Dustin Calloway/Clay Island Farm** has real poultry houses in view, but the
  registry point sits at an open road junction between several separate clusters —
  the 19 detections likely span more than one farm. Worth resolving which cluster
  actually belongs to this permit before updating the registry.

## 3. Laying hens — a genuine, unexplained miss worth debugging directly

Of the two new laying-hen farms with real poultry-shaped buildings clearly present:

- **Sunnyside Poultry Farms**: real cluster of 3-4 long light-roofed layer houses
  ~200m from the registry point. Zero detections.
- **Cobb Heritage LLC/Pocomoke Farm #4**: a large, dense, textbook-clean complex of
  7-8 parallel long light-roofed houses directly at the registry point. Zero
  detections.

Cobb Heritage in particular doesn't fit the dairy/beef story at all — the shape is
exactly what the filter targets, at good resolution, with no obstruction. This
looks less like a shape-filter mismatch and more like a genuine model or
pipeline-coverage failure on an easy target, and it's worth checking directly
whether this farm's tile actually ran through inference at all, separate from
anything about the shape thresholds.

One farm, **VALO BioMedia North America LLC**, is registered under
`laying_hens_dry_manure` but its registry point sits on a modern industrial/lab
building with no poultry housing in view anywhere in a 900m radius — plausibly an
egg-based biologics/vaccine facility rather than a conventional layer farm. Worth
flagging to MDA as a possible registry miscategorization rather than trying to
explain it as a detection gap.

## 4. Confirmed: registry-point drift is not a dairy-only problem

Three of the ten randomly sampled ordinary broiler farms (not cherry-picked for any
known issue) had the registry coordinate sitting in a completely empty crop field
or forest, with no structure of any kind visible anywhere in the 900m × 900m crop:
Boi & Nawl Farm LLC, Maurice Blake, Smithville View Farm/Howard MacDonald. This
means the geocode-quality problem documented earlier for specific dairy farms is a
property of the registry generally, not a dairy-specific pattern — worth keeping in
mind for the un-anchored statewide search (Priority 4): a method that doesn't
depend on the registry point being accurate at all (e.g. the change-detection
approach in `task1_completion_criteria.md` §3) may actually be *more* robust here
than scaling up today's point-anchored tiling.

## 5. Updated building-type index

New entries confirmed this pass, added to `building_type_inventory.md`:

| Structure | Status | Evidence |
|---|---|---|
| Round manure tank (upright, concrete/steel) near dairy barns | Seen repeatedly, zero detection coverage | David Pyle/Cow Comfort Inn Dairy (2 tanks); Matthew Hoff/Coldsprings Farms (1 silo, ambiguous silo vs. tank) |
| Dark, rectangular, banked lagoon-type pond at dairy sites, brownish-olive not teal | Seen repeatedly, lagoon detector never fires | Teabow, Arbaugh's Flowering Springs, Patterson Farms, Deerspring Dairy Farm |
| Modern industrial/lab building registered as an AFO | One confirmed case, likely registry miscategorization | VALO BioMedia North America LLC |
| Non-farm utility/nursery site with an AFO-style registry entry | One confirmed case | Alan & Kristin Hudson |

## 6. Questions to bring to the AGNR team

These are the specific, concrete questions this pass surfaced — not general asks:

1. **Whitelyn Farms** (dairy, no visible structure within 450m): is this the kind
   of small, deliberately-under-CAFO-threshold dairy operation Stephanie described
   on Sept 9? What does that kind of site actually look like from the air, if
   anything?
2. **The dark, brownish-olive ponds at Teabow/Arbaugh's/Patterson/Deerspring**: do
   these read as real manure lagoons to someone who knows dairy operations, or
   could they be something else (irrigation ponds, sediment ponds)? This would
   directly validate or rule out the biggest single finding of this pass.
3. **Round tanks at David Pyle and similar sites**: are these manure storage, or
   could they be something else (water towers, feed storage)? Worth confirming
   before building a detector around them.
4. **Cobb Heritage LLC/Pocomoke Farm #4**: an ideal-looking target with zero
   detections — is there a reason to suspect this farm's imagery/tile might not
   have actually run through the pipeline, versus a genuine model failure worth
   debugging?
5. **VALO BioMedia and Alan & Kristin Hudson**: should these two registry entries
   be flagged to Alisha Mulkey/MDA as possible miscategorizations, or is there a
   legitimate AFO-adjacent reason they're listed this way?

## Reproducing this

```
python3 scripts/render_species_audit_batch.py
```

Outputs to `data/processed/species_audit_screenshots/`, plus `audit_manifest.json`
listing every farm, group, detection count, and output file.
