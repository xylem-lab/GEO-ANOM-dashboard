#!/usr/bin/env python3
"""
A real test of registry independence: take the 43 AFO-inspected-but-no-
CAFO-permit sites from the MDE compliance list Rafian shared (2026-10-01),
geocode them from their street address alone (US Census batch geocoder --
free, no key), pull NAIP imagery, and run the exact same U-Net + Tulbure
pipeline used on the registered 417 farms. These sites have no CAFO permit
at all, so if the pipeline finds real buildings on any of them, that's the
first actual evidence the detector works on something outside the registry
it was validated against -- as opposed to the registry-anchored data every
other run in this project has used.

Usage: python3 scripts/crosscheck_mde_inspection_list.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent

SITES_PATH = ROOT / "data/raw/external/mde_afo_inspection_no_permit_sites.json"
TILE_DIR = ROOT / "data/raw/naip_tiles_mde_inspection_crosscheck"
OUT_GEOJSON = ROOT / "data/processed/detections/mde_inspection_crosscheck_detections.geojson"
OUT_REPORT = ROOT / "docs/mde_inspection_crosscheck_2026-10-01.md"

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def geocode_census(sites: list[dict]) -> dict[str, tuple[float, float]]:
    """US Census Bureau batch geocoder. Free, no API key. Returns
    {site_no: (lon, lat)} for sites that matched."""
    rows = []
    for s in sites:
        if not s.get("street") or s["street"] == "None":
            continue
        street = s["street"].replace(",", " ")
        rows.append(f"{s['site_no']},{street},{s['city']},{s['state']},{s['zip']}")
    batch_content = "\n".join(rows)

    resp = requests.post(
        CENSUS_BATCH_URL,
        files={"addressFile": ("batch.csv", batch_content, "text/csv")},
        data={"benchmark": "Public_AR_Current"},
        timeout=120,
    )
    resp.raise_for_status()

    import csv
    import io

    geocoded = {}
    # The response is real quoted CSV -- the lon,lat field is itself a single
    # quoted column containing an embedded comma ("-75.80,38.17"), which a
    # naive str.split(",") silently misparses (shifts every later column by
    # one, so match_status reads as a coordinate and the real coordinates
    # are dropped) with no error at all. Confirmed by fetching the raw
    # response directly and comparing column-by-column before trusting this.
    reader = csv.reader(io.StringIO(resp.text))
    for parts in reader:
        if len(parts) < 6:
            continue
        site_no, _input_addr, match_status = parts[0], parts[1], parts[2]
        if match_status != "Match":
            continue
        try:
            lon_str, lat_str = parts[5].split(",")
            lon, lat = float(lon_str), float(lat_str)
        except (ValueError, IndexError):
            continue
        geocoded[site_no] = (lon, lat)
    return geocoded


def main():
    sites = json.loads(SITES_PATH.read_text())
    print(f"Loaded {len(sites)} no-permit AFO-inspection sites")

    geocoded = geocode_census(sites)
    print(f"Geocoded {len(geocoded)}/{len(sites)} via US Census batch geocoder")

    manifest = []
    for s in sites:
        coords = geocoded.get(str(s["site_no"]))
        if coords is None:
            continue
        lon, lat = coords
        manifest.append({**s, "farm_name": s["site_name"], "lon": lon, "lat": lat})

    (ROOT / "data/raw/external").mkdir(parents=True, exist_ok=True)
    geocode_out = ROOT / "data/raw/external/mde_afo_inspection_no_permit_geocoded.json"
    geocode_out.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"Saved geocoded manifest -> {geocode_out}")

    # ---- imagery acquisition ----
    from planetary_computer_naip import download_tile
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    tiled = []
    for i, site in enumerate(manifest):
        out_path = TILE_DIR / f"site_{site['site_no']}.tif"
        if out_path.exists():
            tiled.append({**site, "tile_path": str(out_path)})
            continue
        try:
            result = download_tile(site, out_path, session)
        except requests.exceptions.RequestException as e:
            # Transient (port exhaustion / reset) -- one retry on a fresh
            # session rather than losing the rest of the run, which is what
            # happened the first time this was run (died at site 27/38 with
            # OSError 49, "Can't assign requested address").
            print(f"  retrying {site['farm_name']} after connection error: {e}")
            time.sleep(2)
            session = requests.Session()
            try:
                result = download_tile(site, out_path, session)
            except requests.exceptions.RequestException as e2:
                print(f"  gave up on {site['farm_name']}: {e2}")
                result = None
        if result is not None:
            tiled.append(result)
        time.sleep(0.5)
        print(f"  [{i+1}/{len(manifest)}] {site['farm_name']:<45} "
              f"{'tile OK' if result is not None else 'NO TILE'}")

    tile_manifest_path = ROOT / "data/raw/external/mde_afo_inspection_no_permit_tiles.json"
    tile_manifest_path.write_text(json.dumps(tiled, indent=2, default=str))
    print(f"\n{len(tiled)}/{len(manifest)} sites got a NAIP tile -> {tile_manifest_path}")

    # ---- detection ----
    from unet_inference import load_model, run_inference_on_tile, mask_to_polygons
    from unet_detect import polygon_geo_stats, passes_tulbure_filter
    from pyproj import Transformer
    from shapely.geometry import mapping
    from shapely.ops import transform as shapely_transform
    import rasterio

    model, device = load_model()
    print(f"Model loaded on device={device}")

    all_features = []
    results_summary = []
    for site in tiled:
        tile_path = Path(site["tile_path"])
        with rasterio.open(tile_path) as src:
            tile_crs = src.crs
        to_wgs84 = Transformer.from_crs(tile_crs, "EPSG:4326", always_xy=True).transform

        mask, transform = run_inference_on_tile(model, device, tile_path)
        raw_polys = mask_to_polygons(mask, transform)

        kept = []
        for poly in raw_polys:
            stats = polygon_geo_stats(poly)
            if passes_tulbure_filter(stats, None, animal_type=None):
                kept.append((poly, stats))

        results_summary.append({
            "site_no": site["site_no"], "farm_name": site["farm_name"],
            "status": site.get("status"), "raw_candidates": len(raw_polys),
            "kept_detections": len(kept),
        })
        print(f"  {site['farm_name']:<45} raw={len(raw_polys):<3} kept={len(kept)}")

        for poly, stats in kept:
            poly_wgs84 = shapely_transform(to_wgs84, poly)
            all_features.append({
                "type": "Feature",
                "geometry": mapping(poly_wgs84),
                "properties": {
                    "class_name": "poultry_house",
                    "detector": "unet_robinson2022_tulbure2024filter",
                    "farm_name": site["farm_name"],
                    "site_no": site["site_no"],
                    "county": site.get("county"),
                    "area_m2": round(stats["area_m2"], 1),
                    "length_m": round(stats["long_side_m"], 1),
                    "width_m": round(stats["short_side_m"], 1),
                    "tile": tile_path.name,
                    "source": "mde_afo_inspection_no_permit_crosscheck",
                },
            })

    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": all_features}, indent=2))

    n_with_detections = sum(1 for r in results_summary if r["kept_detections"] > 0)
    report = [
        "# MDE AFO-Inspection List Crosscheck — 2026-10-01",
        "",
        f"Source: `AFO.csv.xlsx` (Rafian Aziz, 2026-10-01 email). {len(sites)} unique AFO-inspected "
        f"sites have no CAFO permit number on file. Geocoded {len(geocoded)}/{len(sites)} by street "
        f"address alone (US Census batch geocoder) -- no coordinates came from any registry we've used "
        f"before. {len(tiled)}/{len(manifest)} geocoded sites got a real NAIP tile. Ran the exact same "
        f"U-Net + Tulbure pipeline used on the 417 registered farms.",
        "",
        f"**{n_with_detections} of {len(tiled)} sites produced at least one kept building detection** "
        f"-- with zero registry lookup involved in finding them.",
        "",
        "| Site | Status | Raw candidates | Kept detections |",
        "|---|---|---|---|",
    ]
    for r in sorted(results_summary, key=lambda r: -r["kept_detections"]):
        report.append(f"| {r['farm_name']} | {r['status']} | {r['raw_candidates']} | {r['kept_detections']} |")
    OUT_REPORT.write_text("\n".join(report) + "\n")
    print(f"\nReport -> {OUT_REPORT}")
    print(f"Detections -> {OUT_GEOJSON}")


if __name__ == "__main__":
    main()
