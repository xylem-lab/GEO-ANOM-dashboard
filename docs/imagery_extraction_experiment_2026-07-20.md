# Imagery Extraction Experiment — 2026-07-20

**Task Tracker #2:** Continue AFO extraction/clustering work from satellite imagery

## What we ran

Picked the **10 highest-headcount AFO permits** from the existing MDE registry data (all broiler chicken operations, 315K–595K birds each — the sites most likely to have large, visually obvious poultry houses and manure lagoons). For each site:

1. Downloaded a fresh 1m-resolution NAIP tile (2km-wide, centered on the permit coordinates) from Maryland's public iMAP ImageServer — no auth needed, all 10 succeeded.
2. Ran the existing `YOLOWorldDetector` (zero-shot, `yolov8x-worldv2.pt`) prompted for exactly the classes we care about: `poultry house`, `chicken barn`, `manure lagoon`, `feedlot`, `grain silo`, `agricultural pond`.

Script: `scripts/top_headcount_imagery_test.py`. Raw output: `data/processed/detections/top10_yolo_world_detections.geojson`.

## What we found

**Result: 3 detections across all 10 tiles — all mislabeled as "grain silo," at 0.01–0.02 confidence. Zero poultry houses, zero lagoons, zero chicken barns detected.**

| Site | Farm | Headcount | Detections |
|---|---|---|---|
| 0 | Minh Vinh | 595,000 | 0 |
| 1 | Pebble Branch Farm | 400,000 | 0 |
| 2 | Alan C. Eck Farm | 370,500 | 0 |
| 3 | Newton Bui/Vina Cao | 354,500 | 1 (grain silo, conf 0.012) |
| 4 | Waqar Ahmed/Emaan and Eshal Farm | 352,000 | 1 (grain silo, conf 0.017) |
| 5 | Jason Lambertson/Amen Corner et al. | 346,000 | 0 |
| 6 | Chinh Nguyen/A,B,C Farms | 333,000 | 0 |
| 7 | Ishfaq Ahmed/APNA Farms | 328,000 | 0 |
| 8 | Moon Farm/Hassan Waheed | 320,000 | 1 (grain silo, conf 0.012) |
| 9 | Christopher Both | 315,000 | 0 |

**We visually confirmed this isn't a data problem.** Manually inspecting the raw tiles (site 0, site 8, etc.) shows textbook poultry houses — long parallel white/gray barns in clusters of 4-6 — clearly visible and unmistakable to the eye. The imagery is fine. The zero-shot model simply isn't finding them.

## A second finding, about the existing dashboard data

While digging into why the *old* 70-detection dataset (currently shown as "sample detections" in the dashboard/pipeline) skewed toward silos/feedlots/ponds instead of poultry houses, we found `configs/maryland.yaml` has:

```yaml
yolo_world:
  confidence_threshold: 0.01
```

That's a 1% confidence floor — low enough to let essentially random noise through. The existing 70 "detections" are not reliable signal; they're artifacts of an artificially low threshold. Worth flagging to the team before those numbers get used anywhere.

## Verdict

Off-the-shelf zero-shot detection (YOLO-World, no fine-tuning) does **not** work for finding poultry houses/lagoons in NAIP imagery, even on the largest, most obvious sites. This is a model-capability gap, not a data-availability gap — the signal is clearly there in the imagery.

## Recommended next step

Zero-shot isn't going to get us there. We need one of:
- **Fine-tune YOLOv8** on a small hand-labeled set (even 20-30 boxed poultry houses from tiles like these would likely be enough to start, since the shape is extremely regular/distinctive).
- Try a different / larger vision-language checkpoint or better prompt engineering as a cheaper first pass before committing to labeling.

Either way, the "continue extraction work" task now has a concrete, falsifiable next step instead of an open-ended "run the pipeline more" — and we have hard evidence to bring to the meeting rather than a vague status update.
