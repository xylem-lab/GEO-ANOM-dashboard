# Proposal: protocol v1.2 — a statewide count (for approval, 2026-11-05)

Status: **approved 2026-11-06 (recommended design) → written into
`docs/TASK1_ACCURACY_PROTOCOL.md` §10, which governs.** Kept as the design
record. Reviews protocol v1.1
(frozen) and PAPER_STANDARD draft v0 against the goal "In 2023, Maryland had
N poultry houses (95% CI) … covering X km² of roof (CI)". Every number below is
either a fact read from the repo / shared drive (source given) or **design
arithmetic** (frame sizes, weights, bounds). None is a result. No labels exist
(`Task1_results/accuracy_v1/` holds only `frame.geojson` and `sample_meta.json`).

## 0. Bottom line

1. **A statewide count with a 95% CI is achievable in time; a statewide CI of
   ±5% that honestly includes houses no source has is not** — and, under the
   frozen v1.1 design, **not on the Eastern Shore either** (§3.1). The limit is
   the random 1 km cells: a cell stratum with zero hits gives an exact upper
   bound of hundreds of houses, and the code currently turns zero hits into a
   zero-width interval (falsely narrow).
2. Recommended: **v1.2 = list frames + a declared residual.** Count, recall and
   roof become statewide sums over list frames that a person checks
   (map, tracing, every western detector candidate, permit sites, long-building
   footprints). Houses on no list are reported as a separate line with its own
   bound, not hidden in the CI. The ±5% target (T2/T3) applies to the list-frame
   total.
3. West of the Bay is small in every independent source (§2), so it adds little
   variance; the risk there is coverage (houses the detector never proposed),
   not sampling error.
4. Extra labelling: **~4.6 h per interpreter** (≈12.5 h each in total), or
   ~3.2 h without the footprint download.

## 1. Facts

### 1a. How the western false positives were removed

- **By eye only; no road rule.** Notebook 11 §5 (cell 16) builds the western
  houses from `conf07` = notebook 07 detections that *every* reviewer called
  "poultry house", outside the Eastern Shore. The road rule is a "tested, not
  adopted" step on the Eastern Shore only (nb 11 §4; `docs/TASK1_RESULTS.md`).
  Western county runs had `use_road_filter: false`
  (`county_frederick/county_summary.json`, `run.use_road_filter`).
- **The western map is the published model + one reviewer, nothing else.**
  Notebook 11 runs rectangles, brightening and SAM for `C.EASTERN_SHORE` only.
  The 26 western outlines are step-0 detections (Robinson U-Net + shape filter:
  length 55–300 m, width 10–30 m, aspect 2.5–18), rectangled.
- **The "417 → 36" figure is not western.** `review/unverified_by_county.csv`:
  417 = all detections outside the traced area, including 24 on the Eastern
  Shore (Cecil 18, Queen Anne's 4, Dorchester 1, Worcester 1). Of the 36 called
  poultry, 10 are Eastern Shore. **West of the Bay: 393 detections → 26
  confirmed, 359 rejected, 8 unsure** (UA only). The "373 rejected" = 359 west
  + 14 Eastern Shore. The 8 western `unsure` are in neither the map nor a
  rejected list: nobody has decided them.
- Released west (release_v1): Frederick 21, Carroll 2, Washington 2, Harford 1.

### 1b. Did notebook 05 cover every western county with 2023 NAIP?

All 15 western counties (incl. Baltimore City) have a run folder,
`county_summary.json` and `run_meta.json`; `accuracy` is null (no tracing).
Tile completeness and NAIP year per county (`county.tile_status` +
`tiles_done/*.json` → `naip_datetimes`):

| County | 2 km tiles | done | no photo | missing | NAIP item dates used (counts are items, a tile can mosaic several) |
|---|---|---|---|---|---|
| Allegany | 423 | 423 | 0 | 0 | 2023 ×478, 2022 ×3 |
| Anne Arundel | 433 | 433 | 0 | 0 | 2023 ×507, 2017–2021 ×5 |
| Baltimore County | 603 | 603 | 0 | 0 | 2023 only |
| Baltimore City | 84 | 84 | 0 | 0 | 2023 only |
| Calvert | 239 | 239 | 0 | 0 | 2023 ×291, 2017–2021 ×41 |
| Carroll | 425 | 425 | 0 | 0 | 2023 only |
| Charles | 467 | 467 | 0 | 0 | 2023 only |
| Frederick | 618 | 618 | 0 | 0 | 2023 only |
| Garrett | 607 | 607 | 0 | 0 | 2023 ×696, 2022 ×3 |
| Harford | 426 | 418 | 8 | 0 | 2023 ×431, 2017–2018 ×14 |
| Howard | 248 | 248 | 0 | 0 | 2023 only |
| Montgomery | 482 | 482 | 0 | 0 | 2023 only |
| Prince George's | 476 | 476 | 0 | 0 | 2023 only |
| St. Mary's | 393 | 393 | 0 | 0 | 2023 ×462, 2017–2021 ×11 |
| Washington | 469 | 469 | 0 | 0 | 2023 only |

**No tile gaps** (0 missing everywhere; Harford's 8 have no NAIP photo at all).
2023 flights span 2023-05-18 to 2023-11-13. **Not entirely 2023:** tiles in
Calvert, Anne Arundel, St. Mary's, Harford, Allegany and Garrett mosaic some
2017–2022 items where the newest photo doesn't cover the whole tile (likely
Bay water or the state line — not checked). A house sitting on one of those
patches was seen on older imagery. Fix for v1.2: the response design already
uses NAIP 2023 only, so labels are 2023 even where the detector wasn't; list
these tiles in the run record and report it.

### 1c. Detector recall with the western settings

The western map uses step 0, so the comparable Eastern Shore recall is the
**published model, 0.670** (2,038 / 3,040 traced; `release_v1/ladder.csv`),
range 0.58 (Worcester, darkest flights) to 0.80 (Caroline, Queen Anne's) —
not 0.805. Western recall is further capped by one reviewer's confirmation.

Reasons western recall could be **lower**, none measured:
- **Other house types.** The western poultry permits are layers (Carroll,
  ~451k head, 2 permits), ducks (Washington, 2), a turkey and a broiler farm
  (Frederick) (`data/reference/mde_afo_registry_snapshot.json`). Layer houses
  can be wider or multi-storey; duck houses shorter. Some may fall outside the
  detector's shape filter **and outside protocol §2's definition**
  (12–20 m × 100–200 m, ≥5:1).
- **Training domain.** The checkpoint was trained on Delmarva-type broiler
  farms; the Piedmont/Ridge-and-Valley has terrain, shadow and many long
  look-alike barns (dairy free-stalls, equipment sheds) — 359 of 393 western
  detections were rejected.
- **Flights.** Not tone-matched in the west (brightening was Eastern Shore only).

Reason it could be **higher**: none known. So no Eastern Shore recall can be
transferred west.

## 2. Independent sources for western omissions

| Source | Licence | Date | Can show | Can't show |
|---|---|---|---|---|
| MDE AFO/CAFO registry (Md. Open Data s4e3-7tuu; snapshot in repo) | Public | 2026 pull | **6 western poultry permits** (Frederick 2, Carroll 2, Washington 2); 49 1 km cells lie within 1 km of one | Farms below permit thresholds; points can be 100s of m off |
| USDA Census of Agriculture 2017 (AWTF Table 1a.3, in repo) / 2022 (NASS Vol. 1 county tables, to pull) | Public domain | 2017 / 2022 | Western broiler+layer inventory 2017: ~0.20 M birds of ~59.5 M statewide (~0.3%); MDE CAFO 2017 adds Carroll 0.45 M. Number of farms with poultry (2022) | House counts or locations; (D) suppression in small counties (Carroll 1,060 birds vs MDE 451,380 shows it) |
| Microsoft US Building Footprints (MD ~1.66 M) | ODbL (attribution, share-alike for derived databases) | Bing imagery ~2012–2021, per-feature date where known | A list of every long, narrow building, made by a **different model on different imagery** → candidates our detector never proposed | Buildings after its imagery date; its own misses; whether a building is a poultry house |
| Overture buildings (OSM + Esri + Microsoft + Google) | ODbL | Monthly releases | Same, with better coverage where OSM/Esri exist | Same |
| Maryland iMAP building footprints | State terms (derived from Microsoft; acknowledge the State) | — | Same as Microsoft | Same |
| Extension (poultry specialist) | — | Current | Where western farms are; which house types | Not a probability measure; can't go in a CI |
| Robinson et al. national predictions | — | ~2016–18 | — | **Not independent** (same model) |

Licences and dates: Microsoft/Overture from their READMEs/release notes
(checked 2026-11-05); the 2022 Census county values are not yet pulled.

**Design planning value (not a result):** at roughly 25–30k broilers per house,
the western bird totals point to tens of houses, not hundreds. Statewide ±5% of
~3,000–3,500 houses is ±150–175 houses. So the west matters for coverage, not
for variance — **if** it can be bounded.

## 3. Design options

### 3.1 The rare-event limit (applies to the Eastern Shore too)

A random cell stratum of N cells with n sampled and **zero** hits has a 95%
upper bound of about N·(1 − 0.05^(1/n)) ≈ 3N/n cells with a missed house. At
1–3 houses per positive cell (farms cluster), design arithmetic:

| Stratum | N | n | Upper bound, cells | Upper bound, houses (1–3/cell) |
|---|---|---|---|---|
| ES S6A (v1.1) | 1,137 | 150 | 23 | 23–68 |
| ES S6B (v1.1) | 2,748 | 150 | 54 | 54–163 |
| ES S6C (v1.1) | 5,476 | 100 | 162 | 162–485 |
| West, cells with a detection | ~240 | 40 | 17 | 17–52 |
| West, within 1 km of a detection | ~1,090 | 60 | 53 | 53–160 |
| West, everything else | ~15,900 | 100 | 470 | 470–1,400 |

One hit is as bad: a single 3-house cell in ES S6C adds ~164 houses with a
95% half-width of ~±320. **So v1.1's T2 (±5%) can only be met if zero-hit cell
strata are given zero width — which is what `accuracy.estimate` does today**
(the bootstrap of an all-zero sample has no spread). Protocol §5 promises the
exact bound but the code doesn't implement it. Footprints (S5) do not shrink
these bounds: a zero-hit bound depends only on n and N. To bound West "everything
else" to ~30 houses would take ~1,500–4,500 cells (17–50 h each). Not feasible.

### 3.2 The options asked about

| Option | What | Hours / interpreter | What it buys | Limit |
|---|---|---|---|---|
| **a** | Extend S6 cells west, stratified: near permit / contains a detection / within 1 km / farmland (CDL) / other | 300 cells ≈ 3.3 h | Unbiased in principle | Upper bound 600–1,700 houses from the low-prior strata; one hit ruins the CI. **Fails ±5% by design.** |
| **b** | The 367 undecided western detections (359 rejected + 8 unsure) | census 1.5 h (sample 120: 0.5 h, bound ~9 houses at 0 found) | Checks the single-reviewer rejection blind; gives the published model's western precision (D1, west) for free | Only houses the detector proposed |
| **c** | S5-style long, narrow footprints not touching any detection or outline | ≤200 items ≈ 0.8 h (size known only after download) | The only efficient way to find houses the detector never proposed | Needs download approval; misses houses the footprint model missed or built after its imagery |
| **d** | Census of the 6 western poultry permits (49 cells within 1 km) | 49 cells ≈ 0.55 h | Covers the known commercial sites (layers, ducks, turkeys) | Only permitted farms |

### 3.3 Recommended: v1.2 = list frames + declared residual

**Strata added (west unless noted); existing S1–S4, S6 frames and sample
unchanged:**

| Stratum | Frame | N | n | Hours |
|---|---|---|---|---|
| S7 | Western detections (notebook 05) not in release_v1 | 367 | all | 1.5 |
| S8 | 1 km cells within 1 km of a western poultry permit | 49 | all | 0.55 |
| S5 (turned on, both regions) | Footprints ≥ 60 m long, aspect ≥ 4, touching no outline, traced house or 05 detection | tbd | all if ≤150 per region, else 150 (ES) / 200 (west), by county | ≤1.4 |
| S6W | Western cells within 1 km of a detection or released house, not in S8: A (contains one) / B (near) | ~240 / ~1,090 | 40 / 60 | 1.1 |

Total added ≈ **4.6 h** per interpreter (S5 at its cap); v1.1 ≈ 8 h → ≈ 12.5 h.

**Estimates.**
- List-frame total (design-based, 95% CI; T2/T3 apply here):
  T̂_lists = Ĉ_ES + M̂ + F̂_ES + C_W + R̂_W + F̂_W + P_W, where C_W = S3 west
  (census), R̂_W = S7 (census), F̂ = S5, P_W = S8 counts.
- **Residual = houses on no list** (not mapped, traced, detected or in the
  footprints), reported on its own line two ways: (i) design, from S6 / S6W
  cells, as an estimate plus an exact one-sided bound per zero-hit stratum;
  (ii) model, the footprint layer's miss rate on the 3,040 traced houses
  (pure geometry, no labels) times T̂_lists, with its transfer assumption stated.
- Statewide recall = (Ĉ_ES + C_W) / T̂_lists, reported with the residual shown
  as a sensitivity row (recall if the residual were at its bound). Roof the
  same way, statewide.

**What the paper can then say:**

> On 2023 NAIP imagery, Maryland had [T̂_lists] standing poultry houses
> (95% CI […]) on the map, the 2016/17 tracing, the detector's candidates,
> permit sites or a building-footprint inventory, covering [X] km² of roof
> (95% CI […]); houses on none of these are estimated at [R] (upper bound
> [R_u]). [West] of them are west of the Chesapeake Bay. The map finds
> [recall] (95% CI […]).

**Alternatives.** Lean (no footprint download): S7 + S8 + S6W, ~3.2 h; the
residual has only the cell bound (§3.1), so it will be large and the claim
weaker. Minimal: S7 + S8 only, ~2 h; claim stays as PAPER_STANDARD draft v0
(Eastern Shore count; statewide precision) plus "west: every detector
candidate and permit site checked, [n] houses found; omissions elsewhere not
assessed" — a lower bound for the west, not an estimate.

## 4. Amendment text (proposed §9 row and new sections)

> **v1.2 (date of approval).** Scope extended to Maryland. Added strata S7
> (all 367 western notebook-05 detections not in release_v1), S8 (all 1 km
> cells within 1 km of a western MDE poultry permit), S6W (western cells within
> 1 km of a detection or released house: A 40, B 60, proportional by county,
> min 5) and turned S5 on in both regions (Microsoft US Building Footprints,
> ODbL, SHA-256 recorded; filter length ≥ 60 m, length/width ≥ 4, touching no
> release outline, traced house or notebook-05 detection; census if ≤ 150 per
> region, else 150 Eastern Shore / 200 west, proportional by county). New
> strata drawn with seed 20261106 into `frame_v1.2.geojson`; `frame.geojson`
> and its sample are unchanged. Cells count houses with no outline among
> release ∪ tracing ∪ western detections ∪ S5 frame (all drawn on the photo).
> Primary total T̂ is over list frames; houses on no list are a separately
> reported residual with exact one-sided bounds for zero-hit cell strata;
> the bootstrap no longer gives zero width to a zero-hit stratum. A poultry
> building outside §2's dimensions is labelled `not a house` with the note
> `poultry, other form` and counted in a separate row. Made before any label
> was recorded.

PAPER_STANDARD (still draft v0) changes: §1 claim → statewide template above;
P1/P2/P4 → statewide list-frame totals + residual line; T2/T3 apply to the
list-frame total; D4 replaced.

## 5. Notebook 14 / `accuracy.py` changes (for the notebook-14 chat)

New or changed:
- `frames_west(...)`: S7 from `county_<west>/buildings.geojson` via
  `county_buildings` minus release outlines; S8 and S6W cells from the
  registry snapshot and the same 1 km grid as `frames()`.
- `frames_footprints(...)`: S5 from the footprint file (download + SHA-256 in
  `env.py`).
- `draw_addendum(...)`: draws only new strata, seed 20261106, writes
  `frame_v1.2.geojson` + `sample_meta_v1.2.json`; refuses if labels exist for
  new strata.
- `SIZES`, `STRATUM_NAMES`, `OBJECT_STRATA`, `CELL_STRATA` extended.
- `_totals` / `_derived`: statewide sums; list-frame total and residual
  separate; roof statewide; western mean roof for unmatched houses taken from
  S7/S5 west houses, not S4.
- `estimate` / `stratum_table`: exact one-sided bound for zero-hit cell strata
  (fixes the gap with protocol §5).
- `render_cell`: `known` layer includes western detections and S5 frame.
- Notebook 14: new frame/draw cells after §2, phases `west` and `west cells` in
  the queue, estimates table with the residual rows.

Reused unchanged: response design and labels, `render_object`, `Store`,
`queue`, calibration, pilot and kappa gate (S1/S2/S4), agreement,
adjudication, the bootstrap machinery, the v1.1 frame, sample, seed and
reserve.

## 6. Risks

- **Interpreter time:** 12.5 h each instead of 8 h; S7 is the same blind
  object task (fast), cells are the slow part.
- **Blindness:** UA labelled all 393 western detections in notebook 07, so S7
  repeats S2's problem; report Monica vs adjudicated separately.
- **Notebook-14 chat on the same branch:** these changes touch `accuracy.py`
  and notebook 14; one writer at a time — hand the §5 list to that chat, or
  pause it, before anyone codes.
- **D1 (published-model baseline):** the west is free (S3 west + S7 = every
  western published-model detection). The Eastern Shore still needs its own
  stratum if D1 is approved.
- **Footprint download:** ~400 MB, ODbL share-alike applies to any derived
  database we publish; per-feature imagery dates may be old.
- **Still not supportable after v1.2:** a CI that includes houses on no list;
  western recall of the detector alone at a useful precision (few western
  houses); per-county western estimates; house types outside §2's dimensions;
  anything on stocking (idle houses count as standing).
