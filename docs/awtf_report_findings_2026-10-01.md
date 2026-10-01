# AWTF Final Report (Rafi/Stephanie's lab) — What It Means for Task 1

Source: "Maryland Animal Waste Technology Assessment and Strategy Planning,"
Final Report, September 2023, PI Stephanie Lansing. Shared by Rafian Aziz,
2026-10-01, pointing specifically to Topic 1A for methodology. Full PDF:
`ADA-AWTF Final Report.pdf` (not committed — large, request from Rafi's lab
directly if needed; this doc extracts the load-bearing numbers and methods).

## The headline finding: our species split was wrong, and now we know by how much

A few turns ago, a rough calculation from this project (registry headcount x
`configs/maryland.yaml` coefficients) put poultry at **93.6% of N and 94.5% of
P2O5** statewide. The AWTF report, built from three independent, much larger
data sources, says broilers are **51% of combined N+P** (2019), with all
cattle categories at **36%**, and the remainder from layers, horses, swine,
and other species.

That's not a small discrepancy — it's the difference between "poultry is
basically the whole story" and "poultry is about half, cattle is more than a
third." The reason is exactly the problem this project has been circling:
**our number only used farms in the MDE CAFO registry**, which is
overwhelmingly poultry. The AWTF team's number uses MDA's farmer-reported
Annual Implementation Reports (AIR) *and* the USDA NASS Census of
Agriculture *and* MDE permit data together — so it captures the dairy/beef
population the registry alone misses. This is independent, external
confirmation that relying on the registry doesn't just risk missing
*locations*, it measurably distorts the *species mix* of the whole nutrient
picture.

## Methodology (Topic 1a) — a real template for registry independence

Three sources, triangulated, not any one treated as ground truth alone:

1. **USDA NASS Census of Agriculture** (2017, 5-year intervals) — county-level
   livestock/poultry counts, independent of any registry.
2. **MDA's Nutrient Management Annual Implementation Reports (AIR)** —
   farmer-submitted annually, used to distribute the NASS statewide species
   total across counties for the intervening years. Notably, their own team
   was **not given poultry AIR data by MDA** and had to fall back to
   NASS/Census estimates for poultry specifically — even a funded state
   university team couldn't get complete farmer-reported poultry data.
3. **MDE's AFO Public Participation Process** (the same Socrata source this
   project pulls from) — permit-level point data: county, primary animal
   type, permitted headcount at one point in time.

Their explicit conclusion: *"Considering all data sources together provides
a clearer picture... than any single data source alone."* That's the
multi-source triangulation this project's Task 1 completion criteria (§3,
the PU-learning / Bayesian-audit framing) already pointed toward — this
report is a real, Maryland-specific precedent for doing it, just without
remote sensing in the mix.

**Table 1a.1 (Animal Unit conversion coefficients)** — a second, independently
sourced coefficient set worth cross-checking against `maryland.yaml`'s N/P
coefficients: Beef cow 1.0 AU, Dairy cow 1.4 AU, All other cattle 0.65 AU,
Broiler 0.007 AU, Layer 0.0047 AU, Swine growers 0.055 AU, Sows/boars 0.40 AU,
Horse 1.0 AU, Goats/Sheep 0.2 AU (1 AU = 1,000 lbs liveweight).

## Geographic concentration — where to prioritize detection effort

- **86.9% of poultry inventory** is in four Eastern Shore counties: Worcester
  (23.5%), Caroline (20.9%), Somerset (19.4%), Wicomico (19.4%) — matches
  where this project's detection already works best.
- **65.6% of cattle/cow inventory** is in four counties: Washington (23.8%),
  Frederick (21.4%), Carroll (11.8%), Garrett (8.7%) — **these are the
  counties where fixing dairy/beef detection would actually matter**, not a
  diffuse statewide problem.
- Highest total-nutrient counties (2019): Worcester (12%), Somerset (12%),
  Caroline (11%), Frederick (11%), Wicomico (9%), Washington (9%).

## A direct, independent clue about why our lagoon detector fails on poultry

Topic 1d: *"poultry waste storage ponds were installed historically in the
state; however, 100% of the cataloged capacity was retired as of 2021."*
Treatment lagoons still in use: poultry 4,050 AU, dairy 3,750 AU, beef 266 AU.

This independently corroborates this project's own 2026-09-23/30 findings
(1 of 7 recorded "confirmed" poultry-associated lagoons held up on imagery
review) — if most poultry waste ponds were already retired statewide by
2021, a detector built against older poultry-lagoon examples would be
expected to fail exactly this way. It also reframes where to look next:
dairy and beef treatment lagoons are still active infrastructure, which
matches this project's 2026-09-30 finding of real-looking lagoon ponds at
multiple dairy sites the detector never proposed a candidate for.

One more precedent worth knowing about: their team **manually digitized
lagoon surface area in ArcGIS Pro** ("polygons were traced around the
visible exterior of the ponds visible at registered CAFOs") — i.e., human
tracing, not an automated detector. They did not solve the automated
lagoon-detection problem either; they went around it by hand. That's useful
context for calibrating how hard this specific sub-problem actually is.

## Relevant to Task 3 (existing infrastructure to site around, not duplicate)

As of the report: 1 operating manure+food-waste digester, 1 food-waste-only
digester, 2 poultry-litter digesters (intermittently operated), plus 4 more
in construction/planning (2 dairy+food-waste, 1 poultry-litter+food-waste, 1
poultry-litter+cover-crop). One poultry-litter pyrolysis system under
construction; one combustion system decommissioned. Any location-allocation
siting model should treat these as already-claimed capacity, not open sites.

## Relevant to Objective 2 (the efficiency-gain metric that's never been scoped)

This report **is** the "current standard" county-level approach GEO-ANOM's
Objective 2 is supposed to be measured against. It's not hypothetical
anymore — there's a real, specific, Maryland-built baseline (county-level,
three-source-triangulated, published September 2023) to compare a farm-level
remote-sensing approach's resolution and accuracy gain against directly.
This should be the reference point when that metric finally gets defined.

## What this doesn't give us

Per Rafi's email: no exact site coordinates were published in the report
(privacy/scope reasons, presumably). It's a county-level resource, not a
farm-level one — useful for validating aggregate totals and prioritizing
where to focus, not for finding individual unregistered farms. That's still
what the MDE AFO-inspection list (separate finding, same email) is for.
