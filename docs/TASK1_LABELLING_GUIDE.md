# Labelling guide for notebook 14 (revision 2, 2026-11-10)

For the two interpreters (Umesh Adari "UA", Monica "Monica"). The same text, with
example photos, is in notebook 14 under **How to decide**. If this page and the
protocol (`docs/TASK1_ACCURACY_PROTOCOL.md` §2) disagree, the protocol wins.

**Slow down.** About 10 seconds a photo is normal. Look at the close-up and write a
note whenever you tick *check later*. In round 1 we averaged 1.5–2.6 s a photo,
and the pilot failed.

## What you see

- **Buildings:** a 2023 aerial photo, 500 m around a point (left) and a close-up
  (right). A **pink crosshair** marks the point. You aren't told where the point
  came from, on purpose.
- **Squares (cells):** a 1 km square (white dashes) with every building we already
  know about outlined in **cyan**.

## The question

**Buildings:** *What is at the crosshair on the 2023 photo?* Judge the building the
crosshair sits on (or the nearest one if it's between two).

**Squares:** *How many standing poultry houses have their centre inside the dashed
square and no cyan outline?* Most squares are 0. In the note, say where (e.g. "NE
ninth, 3 houses").

## A standing poultry house has all three

1. **Shape:** long, narrow, single-storey; about 12–20 m wide and 100–200 m long; at
   least 5 times longer than wide (use the scale bar).
2. **Roof complete** on the 2023 photo.
3. **At least one poultry cue:** fans or doors on an end, feed bins along a side,
   two or more identical houses side by side, a manure shed or composter nearby.

Idle or rusty houses count. Turkey and layer houses count.

## Pick one label (always)

| Label | Use when |
|---|---|
| **house** | All three points above |
| **gone** | A house was clearly here: bare slab, scar or roofless frame |
| **under construction** | Frame or unfinished roof |
| **not a house** | Anything else, including look-alikes: equipment sheds, greenhouses / hoop houses, manure sheds, long barns with no poultry cues, dairy barns, warehouses, roads, fields |
| **can't tell: photo unreadable** | The photo doesn't show the ground at the crosshair: cloud or haze, heavy blur, black or cut-off tile edge, no 2023 photo loaded |

**If you can see the building but can't decide what it is, "can't tell" is the
wrong label.** Pick the label you think is most likely and tick **check later**.

## Ticks and note

- **Check later:** tick if you're not sure, or want this photo looked at again. It
  doesn't change your label; your label still counts. Say why in the note.
- **Poultry, other form:** tick it (with **not a house**) for a poultry building
  that doesn't fit the shape rule, e.g. a wide or multi-storey layer house or a
  short duck house.
- **Note:** why you ticked check later; the Google Earth date if you used it.

## Common look-alikes

- **Dairy free-stall barn:** wider (often 30 m or more), open sides, silos, feed
  lanes, a lagoon → **not a house**.
- **Long barn with no poultry cues** → **not a house**; tick check later if unsure.
- **Bare rectangle where a house stood** → **gone**.
- **Dark 2023 photo:** use the close-up. If the building is visible, label it; if
  the ground really can't be seen, **can't tell**.

## Rules that keep the result valid

1. **Don't talk about labels** with the other interpreter until you've both
   finished a phase.
2. **Don't look up the item** in our map, the KMZ or notebook 07.
3. **Use "← back"** if you clicked the wrong button. Your last label counts.
4. **Take breaks.** Rerun the cell and it continues where you left off.

Order: calibration (30) → discuss → pilot (74) → gate (kappa ≥ 0.8) → the rest →
squares.
