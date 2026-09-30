# Building & Structure Type Inventory (Task 1)

What every tile actually shows, versus what the pipeline is built to look for.
Built for the Path B decision (invest in labeled data for dairy + manure
storage type) — grounded in the 23 farms reviewed 2026-09-23
(`data/processed/field_screenshots/manifest.json`, `docs/labeling_guide.md`)
and the two detector scripts. No invented categories below; every row cites
the farm it was seen on.

## The pipeline tracks exactly two classes, full stop

| Detector | Output class | What it actually is |
|---|---|---|
| `unet_detect.py` (U-Net + Tulbure shape filter) | `"poultry_house"` | One class name for every long, light-roofed barn that passes the shape filter — poultry, turkey, duck, swine, beef, **and** dairy barns all come out labeled `poultry_house`. The pipeline does not know or record which species a detected building belongs to; that only comes from which farm's tile it's on. |
| `sam_lagoon_refine.py` (color + shape candidate + SAM) | `"manure_lagoon"` | One class for any water-colored, roughly-solid blob near a farm. No distinction between a manure lagoon, a farm pond, a stormwater pond, or a house pond. |

Everything else on every tile — regardless of how obviously farm-relevant —
is invisible to the pipeline. It's either silently ignored (nothing looks
for it) or accidentally caught and then filtered back out as noise.

## Full inventory of what's actually on the tiles

### Tracked, and it works reasonably well

| Structure | Tracked as | Evidence |
|---|---|---|
| Poultry/turkey/duck broiler-style house | `poultry_house` | Core target, 2,724 detections; C1 Butler, C4 Tuscarora, C5 Martin |
| Swine confinement barn | `poultry_house` | Same shape signature; C2 Grand View Farm |
| Beef confinement barn (long, narrow) | `poultry_house` | Bistate Feeders (A3) — 7/7, clean |
| Layer/breeder house | `poultry_house` | C3 Cal-Maine (though the PDF's "7/7" claim for this farm was never verified against the image and should be re-checked) |

### Tracked, but poorly — this is the Path B gap

| Structure | Tracked as | What goes wrong | Evidence |
|---|---|---|---|
| Dairy free-stall / hay barn | `poultry_house`, sometimes | 11 of ~14 dairy farms return **zero** detections — the shape/roofline doesn't match the poultry-house template at all. Even the one dairy farm that does get a detection (Oakland View, A8) only gets half a barn outlined. | A4 Lester (0 detections, barns + 3 lagoons clearly visible), A5 Horizon (0 detections), A8 Oakland View (partial) |
| Beef barn, short/wide variant | `poultry_house`, sometimes | Needed a species-specific filter exception to detect at all (2026-09-02 fix); even then the outline covers roughly half the roof | A1 Brandenburg, A2 Panora |
| Manure lagoon (real) | `manure_lagoon`, sometimes | Of 7 farms with a recorded lagoon, only 1 (Dulin, B1) is confirmed real on the imagery. The rest are misclassified poultry-house roofs, an unresolved cross-source disagreement, or a house pond. Real lagoons in shadow are also missed outright (recall gap, not just precision). | B1 Dulin (real), B2 Tran / B3 Roland / B5 Hite (roof, not water), B4 Rahim (house pond) |

### Seen on tiles, not tracked at all — no detector looks for these

| Structure | Why it matters for Path B | Evidence |
|---|---|---|
| **Round manure storage tank** (steel/concrete, circular, dark liquid) | This is a manure-storage type distinct from a lagoon — round tanks vs. open lined ponds is exactly the "storage type" distinction Task 2's feedstock question needs, and the current lagoon detector's shape assumptions (oval/rectangular, `ASPECT_MIN`-style solidity) won't catch a circular tank. | Panora Acres (A2); also seen at David Pyle/Cow Comfort Inn Dairy (2 tanks) in the 2026-09-30 imagery audit — recurring across both beef and dairy, not a one-off |
| **Dark, rectangular, brownish-olive lagoon-type pond at dairy sites** | Looks exactly like a manure lagoon on sight — banked, regular, adjacent to barns — but the color reads brownish-olive, not the bright teal the existing color check was calibrated on. Plausible root cause for why candidate generation never proposes a box here at all. | Teabow, Arbaugh's Flowering Springs, Patterson Farms, Deerspring Dairy Farm — 4 independent sightings, 2026-09-30 imagery audit |
| **Modern industrial/lab building registered as an AFO** | A registry entry (`laying_hens_dry_manure`) whose coordinate sits on what looks like a biologics/vaccine facility, not a poultry barn — likely a registry miscategorization rather than a detection gap | VALO BioMedia North America LLC, 2026-09-30 imagery audit |
| **Non-farm utility/nursery site with an AFO-style registry entry** | Gravel yards, a mulch pile, a water tower, nursery rows — no barn shape anywhere nearby; "unknown species" may be the *correct* label here, not a gap to fix | Alan & Kristin Hudson, 2026-09-30 imagery audit |
| **Silage bag / silage bunker** | Common on beef/dairy sites, visible as long white or dark plastic-wrapped mounds; not farm waste storage but a strong visual co-occurrence cue for livestock (vs. crop-only) operations | Brandenburg (A1) |
| **Feed/grain silo (round)** | Explicitly and correctly excluded by the shape filter (aspect ≈1) — this one is working as intended, not a gap, but it's worth recording as "seen and deliberately not tracked" rather than "never considered" | Noted in `labeling_guide.md`, seen next to swine/dairy barns |
| **Other farm outbuildings** (small sheds, equipment barns, unlabeled small roofs) | Not distinguished from noise; no attempt made to classify these at all | Horizon Organic (A5) — "other outbuildings" mentioned but not itemized |
| **Farmhouse / residence** | Relevant mainly as a confuser — a pond beside a house reads similarly to a lagoon at a distance | Rahim (B4) |
| **Residential swimming pool** | Explicitly identified as a false-positive class and suppressed via a color-channel rule (`b-r > 15`); tracked only in the negative sense (filtered out), never itself labeled | Found near Roland Todd's farm during recall-widening testing |
| **Quarry / borrow pit** | False-positive water/disturbed-ground signature; suppressed, not labeled | Christopher Both |
| **Stormwater retention pond** | Named by Stephanie Lansing as a real, distinct confusion class from manure lagoons — **no rule exists to tell them apart at all**, unresolved | `labeling_guide.md`, not yet observed+confirmed in our own sample |
| **River / tidal wetland fragment** | False-positive water signature (a small visible piece of a much larger river reads as "solid" locally); caught inconsistently by an area cap, not a real discriminator | Jabar Rahim originally, also Van Boi, Chisholm/Big Mill Pond Farm |
| **Forest-edge/hedgerow shadow strip** | Not a real object at all — a shadow artifact that passes the water-color check; suppressed inconsistently | William Moore III, one Roland Todd candidate |
| **Non-farm long-roof buildings** (grandstand, stable, warehouse) | Same shape signature as a poultry house; currently only excluded because every tile is centered on a *known* CAFO permit. This becomes a live false-positive source the moment un-anchored, whole-state tiles are scanned for unpermitted farms. | Pimlico Race Course (D1) — 4 false detections |

## What this means for Path B

The pipeline currently answers one question well: *"is there a long
light-roofed barn here, and roughly where."* It does not currently answer,
and has no code path even attempting to answer:

- What species is in a detected barn (dairy vs. beef vs. poultry) — inferred
  today only from which farm's permit the tile is centered on, so it's
  registry-derived, not vision-derived.
- What manure storage type a farm uses — lagoon vs. round tank vs. none
  visible — which is the direct Task 2 feedstock-type input.
- Whether a detected water body is a manure lagoon, farm pond, stormwater
  pond, or something else — right now these are all lumped into one
  low-precision class.

If Path B is the direction, the labeling priority in order of what would
close the biggest gap per unit of labeling effort is probably:
1. Dairy barn shape/roofline (11 of 14 dairy farms are currently blind spots)
2. Round manure tank as its own detector class (currently zero coverage,
   not even attempted)
3. A lagoon vs. farm-pond vs. stormwater-pond discriminator (currently one
   undifferentiated class with ~1/7 precision on our own recorded examples)

This list is only as good as the 23 tiles it's drawn from — it is not a
statistically representative sample of the ~420-farm registry, just what
we've actually looked at with our own eyes so far.
