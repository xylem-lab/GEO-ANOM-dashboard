# Labelling guide for notebook 14 (one page)

For the two interpreters (Umesh Adari "UA", Monica "Monica"). Made from the protocol
(`docs/TASK1_ACCURACY_PROTOCOL.md` §2, §10.3). If this page and the protocol disagree, the
protocol wins: tell the other interpreter and Umesh, don't guess.

## What you see

- **Buildings:** two views of a 2023 aerial photo. Left: 500 m around a point. Right: a close-up.
  A **pink crosshair** marks the point. You are not told where the point came from (our map, the
  USGS tracing, another dataset), on purpose.
- **Squares (cells):** a 1 km square (white dashes) with every building we already know about
  outlined in **cyan**.
- The photo date is printed top-left. It's always 2023.

## The question

**Buildings:** *What is at the crosshair on the 2023 photo?* Judge the building the crosshair sits
on (or the nearest one if it's between two).

**Squares:** *How many standing poultry houses have their centre inside the dashed square and no
cyan outline?* Most squares are 0. In the note, say where (e.g. "NE ninth, 3 houses").

## What counts as a standing poultry house

All three:
1. **Shape:** long, narrow, single-storey; about 12–20 m wide and 100–200 m long; at least 5 times
   longer than wide (use the scale bar).
2. **Roof complete** on the 2023 photo.
3. **At least one poultry cue:** fans or doors on an end, feed bins along a side, two or more
   identical houses side by side, a manure shed or composter nearby.

Count it even if it looks idle or the roof is rusty (we can't tell idle from a photo).
Turkey and layer houses count.

## The five labels

| Label | Use when |
|---|---|
| **house** | It meets all three points above |
| **gone** | A house was clearly here but is demolished, roofless, or only a bare slab is left |
| **under construction** | A house frame or an unfinished roof (this counts as **not standing** in 2023) |
| **not a house** | Anything else: dairy barn, warehouse, shed, greenhouse/hoop house, road, field, nothing |
| **unsure** | You can't decide even after a careful look |

- **Low confidence:** tick it when you chose a label but aren't sure.
- **Poultry, other form:** tick it (with **not a house**) for a poultry building that doesn't fit
  the shape rule, e.g. a wide or multi-storey layer house or a short duck house.
- **Note:** optional. If you checked Google Earth Pro, write the image date you used.

## Common look-alikes

- **Dairy free-stall barn:** wider (often 30 m or more), open sides, silos, feed lanes, a lagoon
  nearby → **not a house**.
- **Long red- or green-roofed barn with no poultry cues** → **not a house**, or **unsure** with a note.
- **Warehouse or industrial building:** large, near roads or towns, parking lots → **not a house**.
- **Dark 2023 photo:** some flights are dark. Use the close-up; if still unclear, check Google Earth
  near 2023, note its date, and tick low confidence.

## Rules that keep the result valid

1. **Don't talk about labels** with the other interpreter until you have both finished a phase
   (calibration, then pilot, then the rest).
2. **Don't look up the item** in our map, the KMZ or notebook 07. Judge only from the photo
   (and Google Earth if needed).
3. **Use "← back"** if you clicked the wrong button. The last label you give counts.
4. **Take breaks.** You can stop any time: rerun the cell and it continues where you left off.

Order of work: calibration (30) → discuss with the other interpreter → pilot (75) → agreement
check (kappa must be ≥ 0.8) → the rest of the buildings → squares.
