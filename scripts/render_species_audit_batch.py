#!/usr/bin/env python3
"""
Render clean|overlay crops for a stratified sample of farms not covered by
the 2026-09-23 field guide's 23 figures, to index building types and species
that the pipeline handles badly or not at all: the remaining dairy farms, the
laying-hen farms, the second duck farm, and the 9 registry entries with no
recorded animal_type -- plus a small random sample of ordinary broiler farms,
to catch confuser buildings the earlier, deliberately-cherry-picked sample
didn't surface.

Farm list and random seed are fixed and printed at the top of the manifest,
so this run is reproducible.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from field_imagery import TileView, draw_native_polygon, draw_point, draw_scale_bar, COLORS
from PIL import ImageDraw
from shapely.geometry import shape
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
PC_MANIFEST = ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json"
BUILDING_DET = ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson"
LAGOON_DET = ROOT / "data/processed/detections/full_registry_sam_lagoon_detections.geojson"
OUT_DIR = ROOT / "data/processed/species_audit_screenshots"
HALF_M = 450.0
RANDOM_SEED = 20260930

DAIRY = [
    "Matthew Hoff/Coldsprings Farms", "Mason Dixon Farms, Inc", "Teabow, Incorporated",
    "Arbaugh's Flowering Springs Inc./Home Farm", "My Lady's Manor Farm, Inc.",
    "Patterson Farms, Inc/Home Farm", "Deerspring Dairy Farm, LLC",
    "Whitelyn Farms, Inc.", "David Pyle/Cow Comfort Inn Dairy",
]
LAYERS = [
    "Sunnyside Poultry Farms", "Cobb Heritage LLC/Pocomoke Farm #4",
    "VALO BioMedia North America LLC (New Construction)", "Cal-Maine Foods, LLC Pullets",
]
UNKNOWN = [
    "Hannah Jones", "Dustin Calloway/Clay Island Farm", "Alan & Kristin Hudson",
    "Bawi Hlun/ Chan UK", "Robert Rosado/Northwind Farm", "Adam Stanley/Deathly Hollows",
    "Chasin Dreams Farm", "Eldwin Martin/Airview Farm", "Muhammad Usman/H & N Farm, LLC",
]
DUCK = ["Eldwin D. Martin"]

GROUPS = {"dairy": DAIRY, "layers": LAYERS, "unknown_species": UNKNOWN, "duck": DUCK}


def safe_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_")[:60]


def main():
    manifest = {s["farm_name"]: s for s in json.loads(PC_MANIFEST.read_text())}
    buildings = json.loads(BUILDING_DET.read_text())["features"]
    lagoons = json.loads(LAGOON_DET.read_text())["features"]

    broilers = [s["farm_name"] for s in manifest.values() if s.get("animal_type") == "chickens_not_laying_hens"]
    already_reviewed_broilers = {"Alan Butler/A&P Farm", "James Donald Dulin", "Hoa Tran/Morning Sun LLC",
                                  "Roland Todd/Roland's Roaster's", "Jabar Rahim", "Todd Hite/Hite Farms, LLC",
                                  "Paul Aaron Hutchison Sr./Home Farm", "Nathan Wolf/Wolf Farm",
                                  "William Moore, III"}
    pool = [n for n in broilers if n not in already_reviewed_broilers]
    random.Random(RANDOM_SEED).shuffle(pool)
    GROUPS["poultry_random"] = sorted(pool[:10])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_out = {"seed": RANDOM_SEED, "half_m": HALF_M, "groups": {}, "figures": []}

    for group, names in GROUPS.items():
        manifest_out["groups"][group] = names
        for name in names:
            site = manifest.get(name)
            if site is None:
                print(f"SKIP (no tile): {name}")
                continue
            tile_path = site["tile_path"]
            center = (site["lon"], site["lat"])
            try:
                view = TileView(tile_path, center, HALF_M)
            except Exception as e:
                print(f"SKIP (tile open failed) {name}: {e}")
                continue
            clean = view.image()
            overlay = clean.copy()
            d = ImageDraw.Draw(overlay)

            to_native = Transformer.from_crs("EPSG:4326", view.crs, always_xy=True) if not view.geographic else None
            n_b = 0
            for feat in buildings:
                if feat["properties"].get("farm_name") != name:
                    continue
                geom = shape(feat["geometry"])  # lon/lat
                poly_native = shape({"type": geom.geom_type, "coordinates": geom.__geo_interface__["coordinates"]})
                if to_native is not None:
                    from shapely.ops import transform as shp_transform
                    poly_native = shp_transform(lambda x, y: to_native.transform(x, y), geom)
                else:
                    poly_native = geom
                draw_native_polygon(d, view, poly_native, COLORS["detected"])
                n_b += 1

            n_l = 0
            for feat in lagoons:
                if feat["properties"].get("farm_name") != name:
                    continue
                draw_native_polygon.__globals__  # no-op, keep linter quiet
                from field_imagery import draw_lonlat_polygon
                draw_lonlat_polygon(d, view, feat["geometry"], COLORS["lagoon_candidate"])
                n_l += 1

            draw_point(d, view, *center)
            draw_scale_bar(d, view)

            out = OUT_DIR / f"{group}__{safe_name(name)}.jpg"
            combo = clean.copy()
            combo_w = clean.width * 2 + 12
            from PIL import Image
            panel = Image.new("RGB", (combo_w, clean.height), (255, 255, 255))
            panel.paste(clean, (0, 0))
            panel.paste(overlay, (clean.width + 12, 0))
            panel.save(out, quality=88)

            manifest_out["figures"].append({
                "group": group, "farm": name, "animal_type": site.get("animal_type"),
                "headcount": site.get("headcount"), "county": site.get("county"),
                "file": out.name, "n_building_detections": n_b, "n_lagoon_detections": n_l,
                "lonlat": center,
            })
            print(f"{group:16s} {name:45s} buildings={n_b} lagoons={n_l} -> {out.name}")

    (OUT_DIR / "audit_manifest.json").write_text(json.dumps(manifest_out, indent=2))
    print(f"\n{len(manifest_out['figures'])} figures -> {OUT_DIR}")


if __name__ == "__main__":
    main()
