"""
Ad-hoc experiment: pull NAIP tiles for the top-headcount AFO permits and run
YOLO-World zero-shot detection prompted for poultry houses / manure lagoons.

Goal: find out whether zero-shot detection can actually surface the two
feature classes the project cares about, on sites most likely to have them
(largest broiler operations), before investing in fine-tuning or scaling up.
"""

from __future__ import annotations

import json
from pathlib import Path

from geo_anom.core.config import get_config
from geo_anom.core.geo_utils import BBox
from geo_anom.phase1.naip_downloader import NAIPDownloader
from geo_anom.phase2.yolo_world_detector import YOLOWorldDetector

ROOT = Path(__file__).resolve().parent.parent
ASSIGNMENTS_PATH = ROOT / "data/processed/optimization_realistic/afo_assignments_realistic.geojson"
TILE_DIR = ROOT / "data/raw/naip_tiles_top10"
OUT_GEOJSON = ROOT / "data/processed/detections/top10_yolo_world_detections.geojson"
MANIFEST_PATH = TILE_DIR / "manifest.json"
N_SITES = 10


def select_top_sites() -> list[dict]:
    data = json.loads(ASSIGNMENTS_PATH.read_text())
    feats = data["features"]
    top = sorted(feats, key=lambda f: f["properties"]["headcount"], reverse=True)[:N_SITES]
    sites = []
    for f in top:
        p = f["properties"]
        sites.append({
            "farm_name": p["farm_name"],
            "county": p["county"],
            "animal_type": p["animal_type"],
            "headcount": p["headcount"],
            "lat": p["latitude"],
            "lon": p["longitude"],
        })
    return sites


def download_tiles(sites: list[dict]) -> list[dict]:
    config = get_config()
    downloader = NAIPDownloader(config=config)
    TILE_DIR.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, site in enumerate(sites):
        bbox = BBox.from_point(lon=site["lon"], lat=site["lat"], buffer_km=1.0)
        tile_path = TILE_DIR / f"site_{i:02d}.tif"
        try:
            downloader.export_tile(bbox, tile_path)
            print(f"  [{i}] downloaded {tile_path.name} for {site['farm_name']}")
            manifest.append({**site, "tile_path": str(tile_path), "bbox": bbox.as_tuple})
        except Exception as e:
            print(f"  [{i}] FAILED for {site['farm_name']}: {e}")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    return manifest


def run_detection(manifest: list[dict]) -> None:
    detector = YOLOWorldDetector(device="cpu")
    all_dets = []

    for site in manifest:
        tile_path = Path(site["tile_path"])
        dets = detector.detect_tile(tile_path)
        print(f"  {site['farm_name']}: {len(dets)} detections")
        for d in dets:
            print(f"      {d.class_name:<20} conf={d.confidence:.3f}")
        all_dets.extend([(d, site) for d in dets])

    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for det, site in all_dets:
        if det.bbox_geo is None:
            continue
        w, s, e, n = det.bbox_geo
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
            },
            "properties": {
                "class_name": det.class_name,
                "confidence": round(float(det.confidence), 4),
                "detector": "yolo-world",
                "farm_name": site["farm_name"],
                "county": site["county"],
                "headcount": site["headcount"],
                "tile": Path(det.tile_path).name,
                "bbox_px": [int(x) for x in det.bbox_px],
            },
        })

    with open(OUT_GEOJSON, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)
    print(f"\nSaved {len(features)} detections -> {OUT_GEOJSON}")


if __name__ == "__main__":
    print(f"Selecting top {N_SITES} AFO permits by headcount...")
    sites = select_top_sites()

    print("\nDownloading NAIP tiles...")
    manifest = download_tiles(sites)

    print("\nRunning YOLO-World detection...")
    run_detection(manifest)
