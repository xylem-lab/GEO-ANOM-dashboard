# Knowledge-sharing workshop, 2026-10-07 — notes and decisions

Source: Zoom transcript (`GEO-ANOM Knowledge-Sharing Workshop's transcript.txt`,
user's Downloads; not committed). Most in-room speech is attributed to "Umesh Adari"
because it came through one laptop mic; speakers below are inferred from content
(poultry/dairy operations and Extension contacts = Stephanie Lansing; chunking,
publishing, privacy, multi-source data = Catherine Nakalembe; LCA = Rafian Aziz).

## Decisions

1. **Poultry first, statewide, then other species.** Run the detector over the whole
   state, not just registry farms, county by county ("chunking"), and verify each
   chunk. Output: a poultry-house density map with a metrics table — the first
   tangible, publishable result (Catherine; Monica can help with the GIS density
   map). Dairy/beef/swine are added afterwards.
2. **Nutrients for poultry: treat every poultry house as broiler** (MD is ~98%
   broilers; hatchery/pullets/layers are a small share — Stephanie). Use a standard
   birds-per-house figure, flocks of ~50 days with ~2 weeks between, litter cleaned
   out every 1–2 years → report a long-run (e.g. 10-year) annual average, not the
   clean-out cycle. Poultry litter is field-applied mainly in spring; dairy manure in
   spring and fall (winter spreading ban).
3. **Check the numbers with poultry Extension experts before computing N/P:**
   Ginny Rhodes (Extension + poultry farmer) and John Moyle (poultry specialist),
   both on the AWTF report. Stephanie will send a poll for an online meeting. Ask:
   birds per house, litter per house per year (wagons per clean-out), N/P per ton.
   Standard poultry-litter tables exist (Stephanie has them).
4. **Validate county totals against the AWTF report appendices** (birds per county
   from MDA reporting) — compare mapped totals county by county.
5. **Then heat maps:** N and P density from the mapped houses → where waste
   technologies make sense, and against cropland (mostly corn) for translocation of
   nutrients (Task 2 link).

## Dairy — ideas raised

- Dairy barns are about as long as poultry houses but **wider** → try a second
  width band for dairy (roughly 35–65 m discussed) and check what it catches.
- Multi-source cues: USDA Cropland Data Layer has pasture and hay/grassland
  classes. But milking herds stay in the barn; pasture (for dry/pregnant cows) may
  not be next to the milking barn, and hay is often a rotation crop — so it's a
  weak cue on its own.
- A dairy almost always has **barns + a lagoon + corn fields** (plus silage
  towers; no hay barns). Catherine: combine such features into rules that give
  higher confidence, then measure accuracy at scale before hand-labelling one by one.
- Data: a detailed list of Washington County dairies (no addresses — findable by
  name on Google Maps); NASS Census of Agriculture has farm counts by herd size.
  Most dairies are west of the Bay (Washington County is the largest).
- Registry/Google points can land on the farm office or equipment yard, not the
  dairy (seen live at one farm).

## Lagoons

- Find lagoons **next to identified barns** rather than searching every water body
  (pools came up before). Since lagoons are mainly dairy, dairy detection and lagoon
  detection are linked. Shapes seen: round concrete tanks and oval/rectangular ponds.

## Privacy / publishing

- Don't publish farm names. Exact coordinates and building outlines may also be
  sensitive: options are offsetting or aggregating (e.g. counts per 10 × 10 km
  block). Fine for internal research; decide before anything public.

## Detection notes from the live demo

- Rejected house (#22 at Hite): merged with the small computer-control shed beside
  it (controls fans/heat), so it failed the width rule.
- Improve outline area (green vs. hand-labelled orange) — area drives N/P estimates.
- Suggested slide: why poultry houses are long (cross-ventilation to clear ammonia;
  chicks are heated, older birds need fans), with a photo of a house interior.

## Rafian's LCA (their "objective 2": best pathway for poultry litter)

- Maryland Manure Transport Program: cost share up to $28/ton (up to 50%), litter
  moved ≥ 7 miles, receiving land must meet the soil-phosphorus criteria; mostly
  broiler litter; ~99% of transported litter is piled, not composted.
- Four scenarios: baseline land application; composting (windrows, turner,
  concrete pad and cover — expensive); pyrolysis (biochar, bio-oil, syngas →
  electricity; still immature); anaerobic digestion (mixing, CHP, solids as
  fertilizer).
- Assumptions: 10,000 t litter/yr per facility (5% of ~200,000 t/yr from three
  Eastern Shore counties); 50 km storage→facility + 50 km facility→field;
  sensitivity analysis on distance (e.g. 200 km).
- Rough ranking: economics → composting; sustainability → digestion.
- A GIS layer of existing digesters/compost sites exists from the AWTF report
  (needs updating). **Integration point:** our density map + facility locations →
  transport distances for their scenarios.

## Action items

| Who | What |
|---|---|
| Stephanie | Poll + online meeting with Ginny Rhodes and John Moyle |
| Umesh | Statewide poultry run, county by county, with per-county metrics |
| Umesh | Compare county totals with AWTF appendix (birds per county) |
| Umesh | Dairy width-band experiment; lagoon search next to detected barns |
| Umesh | Share slides + notebook (done at the meeting) |
| Rafi / ENST | Updated GIS of digester/compost sites |
| All | Privacy approach before publishing any map |
