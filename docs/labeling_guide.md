# Task 1 Detection Labeling Guide

Working reference for what the pipeline should and shouldn't count as a poultry
house or a manure lagoon. Built from real examples found and verified in this
project's own detection output (not hypothetical cases) — grounded in the
2026-09-09 team meeting's request for shared decision rules, and in Stephanie
Lansing's domain guidance from that meeting (color, shape, and context cues
for lagoons; language guidance on "illegal" vs. "not CAFO-registered").

Each entry: what it is, the decision, and the real farm it was found on so it
can be pulled up again if useful.

## Buildings (elongated, light-roofed structures)

| Shape | Decision | Evidence |
|---|---|---|
| Broiler/poultry house (~55-300m long, ~10-30m wide, aspect 2.5-18) | **YES** | The core detection target — 2,724 confirmed across the registry |
| Turkey house | **YES** | Same architectural signature as broiler houses; correctly detected on Jon Sewell/Tuscarora Farms (registered as `turkeys`) |
| Duck house | **YES** | Same signature; correctly detected on Isaac Martin (registered as `ducks_liquid_manure`) |
| Swine barn | **YES** | Same signature; correctly detected on Grand View Farm (registered as `swine_55_lbs`) |
| Cattle/heifer confinement barn | **YES** | Modern confined heifer housing uses the same long, light-roofed barn shape; 7 correctly detected on Bistate Feeders (registered as `cattle_includes_heifers`) |
| Dairy free-stall / hay barn | **YES**, with caution | Correctly detected on Oakland View Farms — but not all dairy barns look like this. Corrected 2026-09-30 after a full census of all 14 registered dairy farms: **13 of 14** show zero detections; Oakland View is the only one with any output, and even that is a partial outline. The failure mode is consistent across the 13: wide, blocky, clustered barn footprints that don't match the long-narrow-parallel shape the filter targets, not a threshold-tuning issue. Don't assume this generalizes broadly to dairy — verify per farm. |
| Silo (round grain/feed storage) | **NO (correctly excluded)** | Aspect ratio ~1 (roughly circular), fails the `ASPECT_MIN=2.5` filter automatically — confirmed visually next to detected swine/dairy barns, never itself detected |
| Warehouse / distribution center / grandstand / stable (non-farm context) | **NO — real false-positive class** | Confirmed on the Pimlico Race Course (MD Jockey Club) tile: 4 false detections on grandstand and stable roofs, purely because they share the long-light-roof shape. **This risk is currently suppressed only because every tile we process is centered on a known registry permit — it becomes a real, active risk once Priority 4 (unpermitted-farm search) runs un-anchored tiles across the whole state.** No fix built yet; flagging for that phase. |

## Water bodies (lagoon candidates)

| Shape | Decision | Evidence |
|---|---|---|
| Regular oval/rectangular pond, brownish/teal color, dark liner visible, directly adjacent to detected barns | **YES** | James Donald Dulin, Roland Todd, Hoa Tran — all confirmed by direct visual overlay. Real measured stats: area 2,025-12,557 m² (mean 6,548 m², 1.62 acres), solidity 0.86-0.95, aspect ratio 1.1-3.2:1 |
| Round/irregular pond in a forest clearing, no barns anywhere on the same farm | **NO** | Brian Harding's 3 candidates — that farm has zero detected barns *and* zero 2016/17 ground-truth houses anywhere on its entire tile, so 3 real manure lagoons there was never plausible. Natural ponds can still pass the solidity check (SAM's mask is only checked locally, not against the whole feature) |
| Water body with visible tan/white disturbed ground around it (excavated material) | **NO — quarry/borrow pit** | Christopher Both's lagoon candidate — same farm also had the one confirmed false-positive house detection this session |
| Winding, branching water body, only part of it visible in the tile | **NO — river/tidal creek** | Jabar Rahim — a section of a much larger river read as locally "solid" because SAM's mask only sees what's inside the cropped candidate box, not the whole feature's true shape. Caught by `MAX_AREA_M2=20000` (real lagoons never approach this) |
| Small, very regular, bright blue pond near a house/driveway, not part of a farm complex | **NO — residential pool** | Found during recall-widening testing near Roland Todd's farm (257m from a barn, small enough to pass a loose area check). **This is the exact case Stephanie and Catherine raised in the meeting** (bright uniform blue vs. lagoon's brownish/teal color, checked via the g-r/b-r color channels). Implemented as `mask_is_water_colored()` in `sam_lagoon_refine.py` — checks the *segmented mask's own* mean color (b-r > 15 is the real discriminator; g-r alone doesn't separate a pool from dense dark cropland). **Confirmed working**: re-running the pipeline after this fix, this exact pool candidate no longer appears. |
| Stormwater retention pond on a farm property | **UNRESOLVED — flagged by Stephanie, not yet built** | She named this as a real, distinct confusion class from manure lagoons (farms sometimes have both). No discriminating feature identified or tested yet — needs either a labeled example from a farm visit, or a rule based on typical stormwater pond siting (near buildings/parking, not near barns) |
| Water body inside dense forest canopy shadow | **UNRESOLVED — known gap** | Full-scale testing of the loosened recall-widening candidate set found dense forest canopy can pass the same color check that correctly rejects cropland — one farm (Ishtiaq Ahmed Chaudhry) still returned false candidates after the color fix. This is why recall-widening stays off by default. |
| Dark building rooftop (metal/asphalt, blue-gray tint) | **NO — new false-positive class, found 2026-09-14** | Nathan Wolf/Wolf Farm: a residential-looking garage's dark roof measured as "water-colored" and high-solidity on Planetary Computer imagery. Not seen as a false-positive class on MD iMAP — a real example of a threshold not transferring between imagery sources with different color processing. |
| Forest-edge/hedgerow shadow strip (dark, elongated, along a field boundary) | **NO — new false-positive class, found 2026-09-14** | William Moore, III (0/3 candidates real) and the "Roland Todd" candidate this pipeline's own recalibration mistakenly labeled as real (see task1_metrics.md §5) — a solid-canopy shadow strip with no water, high enough solidity to pass even a raised (0.90) threshold. |
| River/tidal-wetland fragment near, but distinct from, the farm | **NO — same class as Jabar Rahim, recurring on PC imagery** | Van Boi, Joseph E. Chisholm Jr./Big Mill Pond Farm — small isolated-looking segments of a much larger winding river/wetland visible elsewhere in the same tile. `MAX_AREA_M2` catches the largest instances but not small fragments. |
| Real lagoon shaded by adjacent tree canopy (partial shadow, not full cover) | **NEW FAILURE MODE — false negative, found 2026-09-14** | Roland Todd's actual, previously-confirmed real lagoon: on Planetary Computer imagery its shaded portion reads as near-black (g-r≈0, b-r≈4 at the darkest pixel), well below any tested color threshold, so `detect_lagoons()` never generated a candidate box there at all. This is a *recall* gap, not a precision one — the opposite direction from every other row in this table, and a genuinely new problem discovered while rebuilding on the new imagery source, not present (or not previously noticed) on MD iMAP. |

**Overall finding from the 2026-09-14 rebuild**: a stratified 10-candidate
audit of the full-scale (417-farm) Planetary-Computer-sourced run found
only ~1/10 confirmed real — see `task1_metrics.md` §5 for full detail.
The registration-bug fix (moving lagoons onto the same imagery source as
houses) is confirmed correct and necessary, but color+shape-based
candidate generation itself has not generalized reliably across two
different imagery sources despite an honest recalibration attempt.
Treat `full_registry_pc_lagoon_detections.geojson` as unverified
candidates, not a trusted count.

## Temporal / context rules discussed at the meeting, not yet implemented

- **Abandoned/demolished lagoons**: Stephanie showed a real example (a farm with both an old unused lagoon and a current one). Suggested as its own label class with a time tag, to avoid conflating "used to be a lagoon" with "isn't a lagoon." Not built — would need either a second imagery vintage per candidate or a texture/vegetation-overgrowth signal.
- **Time-series pool exclusion**: pools get drained/covered seasonally; a real lagoon doesn't. Not implemented — would need multi-date imagery per candidate, which the current single-snapshot pipeline doesn't fetch.
- **Pasture-layer cross-reference**: Catherine's suggestion — a water body sitting inside a classified pasture parcel is more likely a farm pond than a lagoon. Not implemented — would need a land-cover layer join, not yet built.

## Language guidance (from Stephanie, applies to all Task 1 output/framing)

- Never call a farm or structure "illegal" for not appearing in the MDE CAFO registry — many real, fully legal operations (especially dairy) deliberately stay under the animal-unit threshold that triggers CAFO registration. "Not registered" ≠ "in violation."
- Avoid enforcement/"gotcha" framing generally. The stated goal is understanding nutrient translocation (where supply and demand are), not identifying non-compliant farms.
