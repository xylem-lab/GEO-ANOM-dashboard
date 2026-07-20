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

## Follow-up: a working classical CV detector (no ML training needed)

Since poultry houses and lagoons both have very distinctive, consistent visual
signatures — bright elongated rectangular roofs, and teal/turquoise water —
we tried plain color + shape filtering (OpenCV) as an alternative to a
learned model, instead of jumping straight to fine-tuning.

Script: `scripts/classical_cv_detector.py`. Output: `data/processed/detections/top10_classical_cv_detections.geojson`, annotated previews in `docs/imagery_experiment_assets/`.

**Result: 122 poultry houses found across all 10 tiles (vs. 0 from zero-shot YOLO-World), plus 2 correctly-identified water bodies.** Visual spot-checks confirm the boxes land on real structures — see `cv_annotated_site_00.png` for a clean example (all 15 houses across 3 clusters correctly boxed) and `cv_annotated_site_09.png`.

Known limitations, so these aren't overstated:
- **Poultry houses:** occasionally boxes bright roads/farm-track segments (same brightness/elongation signature). Precision is good but not perfect — worth a quick manual pass before treating counts as ground truth.
- **Lagoons:** tuned conservatively after an initial pass over-triggered on dark crop fields — current version only fires on clearly teal/turquoise water (confirmed correct both times it fired), so it likely **misses** darker, murkier, algae-covered lagoons rather than false-alarming on them. Recall is the open question here, not precision.

## Recommended next step

We now have two real options instead of one dead end:
1. **Ship the classical CV poultry-house detector as v0** — it already works, needs no training data, and just needs a false-positive pass (exclude road-shaped detections) and a recall check across more sites.
2. **Fine-tune YOLOv8** on a small hand-labeled set for a more general, learned solution — the classical detector's 122 boxes above are themselves usable as a first-pass label set, cutting most of the manual labeling work.

Either way, the "continue extraction work" task now has concrete, working output and a clear next step — not just a negative zero-shot result.
