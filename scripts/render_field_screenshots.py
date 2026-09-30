#!/usr/bin/env python3
"""
Renders the satellite figures for the field labeling guide + KMZ balloons and
writes data/processed/field_screenshots/manifest.json describing each one.

Overlay legend (kept consistent across every figure):
  green   = building detection kept by the pipeline
  orange  = raw model candidate the shape filter dropped
  blue    = recorded lagoon polygon (hand-labeled set); yellow = uncertain
  purple  = automated lagoon candidate; red = known false positive
  white ring/cross = MDE registry permit point
  white ring + label = analyst-annotated location (eyeballed from imagery,
                       NOT model output, +/- ~30 m)

Usage:  python scripts/render_field_screenshots.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from pyproj import Geod
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from field_imagery import (COLORS, PANEL_PX, ROOT, TileView, _font, draw_lonlat_polygon,  # noqa: E402
                           draw_marker, draw_native_polygon, draw_point, draw_scale_bar,
                           load_manifest, render, side_by_side)

OUT = ROOT / "data/processed/field_screenshots"
OUT.mkdir(parents=True, exist_ok=True)
GEOD = Geod(ellps="WGS84")

PC = load_manifest("pc")
IMAP = load_manifest("imap")
DET = json.loads((ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson").read_text())
SAM = json.loads((ROOT / "data/processed/detections/full_registry_sam_lagoon_detections.geojson").read_text())
PCL = json.loads((ROOT / "data/processed/detections/full_registry_pc_lagoon_detections.geojson").read_text())

DETS_BY_FARM: dict[str, list] = {}
for f in DET["features"]:
    DETS_BY_FARM.setdefault(f["properties"]["farm_name"], []).append(f)

FIGURES: list[dict] = []
SPOTTED: list[dict] = []
_model = None


def _get_model():
    global _model
    if _model is None:
        from unet_inference import load_model
        _model = load_model()
    return _model


def raw_candidates(farm: str):
    """Raw U-Net polygons (tile-native CRS) for the farm's tile."""
    from unet_inference import mask_to_polygons, run_inference_on_tile
    model, device = _get_model()
    tile = str(ROOT / PC[farm]["tile_path"])
    mask, tr = run_inference_on_tile(model, device, tile)
    return mask_to_polygons(mask, tr)


def compass(az: float) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(((az % 360) + 22.5) // 45) % 8]


def centroid_of(feats):
    cs = [shape(f["geometry"]).centroid for f in feats]
    return (sum(c.x for c in cs) / len(cs), sum(c.y for c in cs) / len(cs))


def offset_text(farm: str, feats) -> str:
    f = PC[farm]
    c = centroid_of(feats)
    az, _, d = GEOD.inv(f["lon"], f["lat"], c[0], c[1])
    return f"{d:,.0f} m {compass(az)} of the registry point"


def save(img: Image.Image, fid: str, section: str, title: str, caption: str, farm: str | None = None,
         lonlat: tuple | None = None):
    if img.width > 1400:
        img = img.resize((1400, round(img.height * 1400 / img.width)), Image.LANCZOS)
    name = f"{fid}.jpg"
    img.save(OUT / name, quality=80, optimize=True)
    FIGURES.append({"id": fid, "section": section, "title": title, "caption": caption,
                    "file": name, "farm": farm, "lonlat": lonlat})
    print("  wrote", name, img.size)


def dims(p):
    return f"{p['length_m']:.0f}x{p['width_m']:.0f} m"


# ------------------------------------------------------------------ figures --
def fig_dets(fid, section, title, farm, half, caption, raw=False, extra=None):
    f = PC[farm]
    feats = DETS_BY_FARM.get(farm, [])
    center = centroid_of(feats) if feats else (f["lon"], f["lat"])
    raws = raw_candidates(farm) if raw else []

    def draw(d, v):
        from unet_detect import passes_tulbure_filter, polygon_geo_stats
        for p in raws:
            st = polygon_geo_stats(p)
            if st["area_m2"] < 100:
                continue
            if passes_tulbure_filter(st, None, f["animal_type"]):
                continue
            draw_native_polygon(d, v, p, COLORS["rejected"], 3, f"{st['long_side_m']:.0f}x{st['short_side_m']:.0f} m (dropped)")
        for ft in feats:
            draw_lonlat_polygon(d, v, ft["geometry"], COLORS["detected"], 3, dims(ft["properties"]))
        draw_point(d, v, f["lon"], f["lat"])
        if extra:
            extra(d, v)

    img = render(f["tile_path"], center, half, draw)
    off = offset_text(farm, feats) if feats else "no detections"
    save(img, fid, section, title, caption.format(off=off, n=len(feats)), farm, center)


def fig_dairy_missed(fid, title, farm, spots, half, caption, crop_center_px=None):
    """Zero-detection dairy farm: analyst annotations.

    spots are pixel positions on the +/-1000 m overview centered on the registry point, unless
    crop_center_px is given: then the crop is centered on that overview pixel and spots are in
    that crop's own native pixel coordinates (more precise)."""
    f = PC[farm]
    ov = TileView(f["tile_path"], (f["lon"], f["lat"]), 1000)
    pts = {}
    if crop_center_px is not None:
        center = ov.lonlat(*crop_center_px)
        cv = TileView(f["tile_path"], center, half)
        for kind, plist in spots.items():
            pts[kind] = [cv.lonlat(*px) for px in plist]
    else:
        for kind, plist in spots.items():
            pts[kind] = [ov.lonlat(*px) for px in plist]
        allpts = [p for v in pts.values() for p in v]
        if half >= 900 or not allpts:
            center = (f["lon"], f["lat"])
        else:
            center = (sum(p[0] for p in allpts) / len(allpts), sum(p[1] for p in allpts) / len(allpts))
    for kind, plist in pts.items():
        for lon, lat in plist:
            SPOTTED.append({"farm": farm, "kind": kind, "lon": lon, "lat": lat})

    def draw(d, v):
        draw_point(d, v, f["lon"], f["lat"])
        for lon, lat in pts.get("barns", []):
            draw_marker(d, v, lon, lat, "barns (model: nothing)", (255, 255, 255))
        for i, (lon, lat) in enumerate(pts.get("lagoons", []), 1):
            draw_marker(d, v, lon, lat, f"lagoon {i}", (110, 200, 255))

    img = render(f["tile_path"], center, half, draw)
    save(img, fid, "A", title, caption, farm, center)


def fig_lagoon_record(fid, section, title, farm, half, caption, source, sam_idx=None, color="lagoon_confirmed",
                      label="recorded polygon", two_source=False):
    feats = [x for x in SAM["features"] if x["properties"]["farm_name"] == farm]
    near = feats[:2] if farm.startswith("Paul Aaron") else feats[:1]
    c = centroid_of(near)
    center = c

    def draw(d, v):
        for i, ft in enumerate(feats, 1):
            lab = label if len(feats) == 1 else f"{label} {i}"
            draw_lonlat_polygon(d, v, ft["geometry"], COLORS[color], 3, lab)

    if two_source:
        a = render(IMAP[farm]["tile_path"], center, half, draw, two_panel=False)
        b = render(PC[farm]["tile_path"], center, half, draw, two_panel=False)
        img = side_by_side(a, b)
    else:
        path = (IMAP if source == "imap" else PC)[farm]["tile_path"]
        img = render(path, center, half, draw)
    save(img, fid, section, title, caption, farm, center)


def fig_pc_candidates(fid, section, title, farm_names, half, caption, color="lagoon_candidate", center_farm=None):
    feats = [x for x in PCL["features"] if x["properties"]["farm_name"] in farm_names]
    c = centroid_of(feats)
    tile_farm = center_farm or farm_names[0]

    def draw(d, v):
        for ft in feats:
            p = ft["properties"]
            draw_lonlat_polygon(d, v, ft["geometry"], COLORS[color], 3, f"{p['area_m2']:.0f} m2")

    save(render(PC[tile_farm]["tile_path"], c, half, draw), fid, section, title, caption, tile_farm, c)


def fig_hite_pair():
    feats = [x for x in PCL["features"] if x["properties"]["farm_name"] in ("Todd Hite/Hite Farms, LLC", "Tue D. Nguyen")]
    south = [f for f in feats if shape(f["geometry"]).centroid.y < 38.047]
    north = [f for f in feats if shape(f["geometry"]).centroid.y >= 38.047]
    tile = PC["Todd Hite/Hite Farms, LLC"]["tile_path"]

    def panel(group):
        c = centroid_of(group)

        def draw(d, v):
            for ft in group:
                draw_lonlat_polygon(d, v, ft["geometry"], COLORS["lagoon_corroborated"], 3,
                                    f"{ft['properties']['area_m2']:.0f} m2")
        return render(tile, c, 150, draw, two_panel=False), c

    a, ca = panel(south)
    b, cb = panel(north)
    save(side_by_side(a, b), "B5_lagoon_hite", "B",
         "Hite / Nguyen (Worcester): 'CAFOSat-corroborated' candidates",
         "Left (south cluster): one polygon on a small white-roofed building at a forest edge, one on a lawn patch. "
         "Right (north cluster, ~850 m away): one on the end of a poultry-house roof, one on a small building. None "
         "of the four is water. The CAFOSat match was a loose 300 m patch-level check and does not confirm these "
         "specific polygons.",
         "Todd Hite/Hite Farms, LLC", ca)


def fig_grid(fid, section, title, farms, caption, half=350):
    cell, gap = 400, 10
    cols = 3
    rows = (len(farms) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell + (cols - 1) * gap, rows * cell + (rows - 1) * gap), (255, 255, 255))
    for i, farm in enumerate(farms):
        f = PC[farm]
        feats = DETS_BY_FARM.get(farm, [])
        center = centroid_of(feats) if feats else (f["lon"], f["lat"])

        def draw(d, v, feats=feats, f=f):
            for ft in feats:
                draw_lonlat_polygon(d, v, ft["geometry"], COLORS["detected"], 3)
            draw_point(d, v, f["lon"], f["lat"])

        tile = render(f["tile_path"], center, half, draw, two_panel=False).resize((cell, cell), Image.LANCZOS)
        d = ImageDraw.Draw(tile)
        label = f"{farm[:34]} | {f['county']} | {len(feats)} det."
        w = d.textlength(label, font=_font(13))
        d.rectangle([0, 0, w + 10, 20], fill=(0, 0, 0))
        d.text((5, 3), label, font=_font(13), fill=(255, 255, 255))
        sheet.paste(tile, ((i % cols) * (cell + gap), (i // cols) * (cell + gap)))
    save(sheet, fid, section, title, caption)


def main():
    print("Section A -- field priority")
    fig_dets("A1_beef_brandenburg", "A", "Beef: Dwight Brandenburg / Brandenburg Family LP (Frederick)",
             "Dwight Brandenburg/Brandenburg Family Limited Partnership", 120,
             "Detection added 2026-09-21 by the beef-specific shape exception. A real barn (~65 x 27 m) with silage bags "
             "and a round manure store -- but the green outline covers only about half of the roof. The barn is {off}; "
             "the permit point falls in a hay field, so the registry geocode is off for this farm. Left: clean "
             "imagery. Right: green = pipeline detection.", raw=True)
    fig_dets("A2_beef_panora", "A", "Beef: Panora Acres / Stacy Sellers (Carroll)",
             "Panora Acres Inc./Stacy Sellers", 120,
             "Second beef detection added 2026-09-21. This is a full livestock complex -- several large barns, feed "
             "silos, and TWO ROUND MANURE STORAGE TANKS (dark liquid). The pipeline outlined part of just one barn; the "
             "round tanks are a lagoon-type structure the lagoon detector is not built to find. The barn is {off}.", raw=True)
    fig_dets("A3_beef_bistate", "A", "Beef reference: Bistate Feeders (Caroline) -- the beef farm that already worked",
             "Bistate Feeders, LLC", 260,
             "{n} detections, all long narrow barns (111-153 m x 12-14 m). The Brandenburg/Panora barns are shorter "
             "and wider than these.", raw=False)

    fig_dairy_missed("A4_dairy_lester", "Dairy (model miss): Lester C. Jones & Sons (Kent)", "Lester C. Jones & Sons, Inc.",
                     {"barns": [(160, 462)], "lagoons": [(295, 458), (262, 515), (222, 578)]}, 450,
                     "Large conventional long-roof dairy barns and three manure lagoons sit ~620 m WSW of the permit "
                     "point (crosshair, top right). The model returned ZERO candidates for this whole 2 km tile. "
                     "Labels are analyst annotations from the imagery (+/- ~30 m), not model output.")
    fig_dairy_missed("A5_dairy_horizon", "Dairy (model miss): Horizon Organic Dairy (Kent)", "Horizon Organic Dairy, LLC",
                     {"barns": [(319, 233)], "lagoons": [(442, 449), (336, 547), (254, 465)]}, 300,
                     "A cross-shaped long barn with a light roof, three manure ponds, and other outbuildings right at the "
                     "permit location; the model returned ZERO candidates. Analyst annotations, +/- ~30 m.",
                     crop_center_px=(434, 425))
    fig_dairy_missed("A6_dairy_fry", "Dairy (geocode error): Matthew Fry / Fair Hill Farms (Kent)",
                     "Matthew Fry/Fair Hill Farms, Inc",
                     {"barns": [(12, 318)], "lagoons": [(22, 246)]}, 1000,
                     "Whole 2 km tile. The permit point (crosshair) is at an empty road junction; the only dairy-looking "
                     "complex (large blue-roof barn + dark lagoon) is ~1 km WEST at the tile edge. Likely a registry "
                     "geocoding error, not a model failure -- the real farm may extend outside this tile.")
    fig_dairy_missed("A7_dairy_oakbluff", "Dairy (geocode error): Oak Bluff Dairy Farms (Frederick)",
                     "Oak Bluff Dairy Farms", {}, 1000,
                     "Whole 2 km tile. No dairy operation is visible near the permit point (crosshair): wooded land, "
                     "a large quarry to the west, scattered houses. Likely a registry geocoding error; the farm is "
                     "probably elsewhere.")
    fig_dets("A8_dairy_oaklandview", "A", "Dairy reference: Oakland View Farms (Caroline) -- the one dairy that works",
             "Oakland View Farms LLC", 250,
             "{n} detection ({off}). Two long barns are visible; the green outline covers only about half of one and "
             "orange fragments (dropped by the filter) mark parts of the other. This is the one dairy where the "
             "pipeline produced a kept detection -- and even here the outline is partial.", raw=True)
    fig_lagoon_record("A9_lagoon_hutchison", "A", "Lagoon candidates: Paul Aaron Hutchison Sr. / Home Farm (Talbot)",
                      "Paul Aaron Hutchison Sr./Home Farm", 300,
                      "Recorded status 'uncertain' (3 candidates; #3 is ~400 m north, off this crop). On the imagery the "
                      "polygons sit on ordinary crop field -- no water, no structure. Likely false positives; a look on "
                      "the ground settles it. Yellow = uncertain. Black band = edge of the tile.", "imap", color="lagoon_uncertain",
                      label="candidate")

    print("Section B -- recorded lagoons vs. imagery")
    fig_lagoon_record("B1_lagoon_dulin", "B", "Dulin (Caroline): recorded 'confirmed' -- looks like a real lagoon",
                      "James Donald Dulin", 200,
                      "A clear teal, regular, banked pond ~380 m from the barns. Polygon aligns on both imagery sources. "
                      "This is the one recorded lagoon that looks right.", "pc", label="recorded lagoon")
    fig_lagoon_record("B2_lagoon_tran", "B", "Tran (Wicomico): recorded 'confirmed' -- polygon is on a poultry house roof",
                      "Hoa Tran/Morning Sun LLC", 200,
                      "The recorded lagoon polygon outlines a gray-blue metal roof with ridge lines -- a poultry house, "
                      "not water. The same on both imagery sources (black band = tile edge).", "pc",
                      label="recorded 'lagoon'")
    fig_lagoon_record("B3_lagoon_roland", "B", "Roland Todd (Dorchester): recorded 'confirmed' -- imagery sources disagree",
                      "Roland Todd/Roland's Roaster's", 250,
                      "Left: MD iMAP imagery -- the polygon outlines three poultry houses, not water. Right: Planetary "
                      "Computer -- the same coordinates are wood edge/field with no barns. The two sources disagree "
                      "about what is at this spot by several hundred meters, and neither shows a lagoon inside the "
                      "polygon. Status unverified -- the recorded 'confirmed' label is not supported by the imagery.",
                      "imap", label="recorded polygon", two_source=True)
    fig_lagoon_record("B4_lagoon_rahim", "B", "Rahim (Dorchester): recorded 'false positive' -- a pond beside a farmhouse",
                      "Jabar Rahim", 300,
                      "Small pond next to a house and pool, ~500 m from the barns, near a large river. Not a river "
                      "fragment as the labeling guide says, but also not lagoon-like by siting. Treat as false positive "
                      "unless the ground says otherwise.", "imap", color="lagoon_false", label="recorded polygon")
    fig_hite_pair()

    print("Section C -- reference detections")
    fig_dets("C1_poultry_butler", "C", "Poultry (broiler) reference: Alan Butler / A&P Farm", "Alan Butler/A&P Farm", 320,
             "{n} detections; the pipeline outlines each long broiler house.")
    fig_dets("C2_swine_grandview", "C", "Swine reference: Grand View Farm (Kent)", "Grand View Farm, LLC", 220,
             "Swine confinement barn -- same long enclosed roof shape as a poultry house. {n} detection.")
    fig_dets("C3_layers_calmaine", "C", "Layers reference: Cal-Maine Foods, Cecil County", "Cal-Maine Foods, Inc.-Layers", 320,
             "{n} detections on a layer complex.")
    fig_dets("C4_turkey_tuscarora", "C", "Turkeys reference: Jon Sewell / Tuscarora Farms (Frederick)",
             "Jon Sewell/Tuscarora Farms", 260, "{n} detections.")
    fig_dets("C5_duck_martin", "C", "Ducks reference: Isaac Martin (Washington)", "Isaac Martin", 260,
             "{n} detection; the sister duck farm (Eldwin D. Martin) has none.")

    print("Section D -- false-positive classes")
    fig_dets("D1_pimlico", "D", "False positive: Pimlico Race Course grandstand/stable roofs",
             "MD Jockey Club of Baltimore City, Inc./Pimlico Race Course", 380,
             "4 'poultry house' detections on a horse-racing venue (roofs share the long-roof shape). Excluded from "
             "the Task 1 output. Green = what the pipeline drew.")
    fig_pc_candidates("D2_darkroof_wolf", "D", "False positive: blue-gray metal barn roofs read as 'water' (Wolf Farm)",
                      ["Nathan Wolf/Wolf Farm"], 260,
                      "Purple = automated lagoon candidates. They outline the blue-gray metal roofs of poultry houses -- "
                      "the roof color reads as water to the color-based candidate step. This is the most common "
                      "lagoon false positive seen (also Tran, Roland Todd, Moore).", center_farm="Nathan Wolf/Wolf Farm")
    fig_pc_candidates("D3_shadow_moore", "D", "False positive: blue metal roofs again (William Moore, III)",
                      ["William Moore, III"], 260,
                      "Purple = automated lagoon candidates sitting on two blue metal-roofed buildings. (Forest-shadow-strip false "
                      "positives are documented in the labeling guide but none is shown here.)",
                      center_farm="William Moore, III")

    print("Section E -- unknown-species registry entries")
    unknown = [f["farm_name"] for f in PC.values() if f["animal_type"] == "unknown"]
    unknown.sort(key=lambda n: -len(DETS_BY_FARM.get(n, [])))
    fig_grid("E1_unknown_species", "E", "Registry entries with no animal type (9 farms)", unknown,
             "All nine have detected buildings (green) but no species/headcount on file. If you can tell what a farm "
             "raises, that is a direct fix to the registry.")

    (OUT / "manifest.json").write_text(json.dumps({"figures": FIGURES, "spotted": SPOTTED}, indent=2))
    print("manifest:", len(FIGURES), "figures,", len(SPOTTED), "analyst-spotted points")


if __name__ == "__main__":
    main()
