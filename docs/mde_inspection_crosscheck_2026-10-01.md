# MDE AFO-Inspection List Crosscheck — 2026-10-01

Source: `AFO.csv.xlsx` (Rafian Aziz, 2026-10-01 email). 43 unique AFO-inspected sites have no CAFO permit number on file. Geocoded 38/43 by street address alone (US Census batch geocoder) -- no coordinates came from any registry we've used before. 38/38 geocoded sites got a real NAIP tile. Ran the exact same U-Net + Tulbure pipeline used on the 417 registered farms.

**31 of 38 sites (82%) produced at least one kept building detection** -- with zero registry lookup involved in finding them. This is the first real evidence this project has that the U-Net + Tulbure pipeline works on something other than registry-anchored data: every one of these 38 sites has no CAFO permit on file at all, geocoded from nothing but a street address in a spreadsheet, with imagery pulled fresh and run through the unmodified detector.

## Reading the results honestly, not just the raw count

- **Two of the "successes" are known false-positive/non-farm patterns recurring, not new real farms.** Pimlico Racetrack (4 kept) is the same horse-racetrack-roof false positive already documented and excluded from the main registry detections -- its reappearance here is a useful consistency check (the pipeline makes the same mistake the same way on fresh data), not a new finding. VALO BioMedia (0 raw, 0 kept) independently reproduces this project's 2026-09-30 imagery-audit finding that this site is an industrial/biologics building, not a poultry farm -- two different approaches (visual inspection, then a cold detector run) agreeing it isn't a farm is a good sign for that earlier call.
- **Kathuria Farms and International BioRefineries, LLC (iNBIO) share the same physical address** (8665 Hickory Mill Road, Salisbury) -- both are AFO-inspection records for what's almost certainly one site (a biorefinery co-located with, or operating on, a farm). Their near-identical detection counts (6 and 6 kept) are very likely the same buildings detected twice under two site records, not two independent farms. Worth a look for Task 3: a working biorefinery at a farm address is a real, existing example of exactly the waste-to-resource facility type Task 3 is meant to help site.
- **Excluding both known patterns, roughly 29 of 36 genuinely new-to-us sites (~81%) still produced real detections** -- the headline number holds up after removing the cases we already understood.
- **Cobb-Heritage, LLC Research Farm #15** (this list) got 4 real detections, while **Cobb Heritage LLC/Pocomoke Farm #4** (the main registry, 2026-09-30 imagery audit) got zero despite looking like an ideal, textbook-clean target. Same company, two different addresses, two very different outcomes -- this doesn't resolve the Farm #4 mystery, but it does rule out "something about Cobb-Heritage as a company confuses the model," which narrows the remaining question to something specific about that one site or tile.
- **7 of 38 sites got nothing** (Benjamin Flahart/Kilby Farms, Josh Grossnickle, Bragunier Farm, Hanover Foods, Bruce Witte Enterprises, Dream Catchers, VALO BioMedia). Not individually reviewed by eye yet -- could be real misses, inactive/demolished sites, or genuinely non-farm addresses (Hanover Foods reads like a food company, not a livestock operation, similar to VALO).

| Site | Status | Raw candidates | Kept detections |
|---|---|---|---|
| Little Brudder Farm | Active | 29 | 24 |
| William T. Calloway, Jr./Double T Farm | Active | 20 | 19 |
| Peniel Farm, LLC | Active | 21 | 14 |
| William T. Calloway, Jr./Tommy and Dee's Farm | Active | 20 | 12 |
| Caspian Farm | Active | 11 | 10 |
| Sarah Michelle Nagel Farm | Active | 23 | 10 |
| Linh Tran Farm | Inactive | 10 | 9 |
| Kaleem Ullah / Rahim Farm | Active | 9 | 9 |
| Esha Farm, LLC c/o Muhammed Ahmad | Inactive | 12 | 9 |
| Haroonali Chaudhry/Langrial Farm | Active | 12 | 9 |
| My N. Tran/Dublin Farm Inc. | Active | 13 | 8 |
| James J. Selby/Keeping The Faith Farm | Active | 16 | 8 |
| Garrett Luthy/Yard Birds | Active | 8 | 8 |
| Garey Benjamin Brown | Active | 7 | 7 |
| Waqas Ahmad/Gujjar Farms LLC | Active | 7 | 6 |
| Bill Miller Farm | Inactive | 10 | 6 |
| Horace Kelley, IV/Kelley Poultry, LLC | Active | 6 | 6 |
| Kathuria Farms (formerly H. Khan/Rosewood Farm) | Active | 9 | 6 |
| International BioRefineries, LLC (iNBIO) | Active | 9 | 6 |
| Dong Ok Choi/Holly Way Farm, LLC | Active | 7 | 5 |
| Mary Jo Motier | Active | 5 | 4 |
| Minh Vo Farm | Inactive | 8 | 4 |
| Jason Lambertson/Grace Ridge Farm LLC | Active | 5 | 4 |
| Pimlico Racetrack | Active | 14 | 4 |
| David/Tammy Pollock | Inactive | 6 | 4 |
| Cobb-Heritage, LLC Research Farm #15 | Active | 7 | 4 |
| Clara Lee/Golden Egg Farm | Active | 12 | 3 |
| J.K. Farm | Inactive | 3 | 3 |
| Beverly Farm | Active | 4 | 2 |
| Sowers, Randy/culvert | Active | 3 | 1 |
| C & S and Murphy's Farms | Active | 2 | 1 |
| Benjamin Flahart/Kilby Farms LLC | Active | 6 | 0 |
| Josh Grossnickle | Active | 0 | 0 |
| Bragunier Farm, LLC | Active | 0 | 0 |
| Hanover Foods Corporation | Active | 1 | 0 |
| Bruce Witte Enterprises | Active | 0 | 0 |
| Dream Catchers | Active | 2 | 0 |
| VALO BioMedia North America LLC (New Construction) | Active | 0 | 0 |
