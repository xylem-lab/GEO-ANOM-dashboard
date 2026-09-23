#!/usr/bin/env python3
"""
Builds data/processed/detections/GEO-ANOM_Task1_Field_Map.kmz for use in Google
Earth (desktop/mobile), including offline:

  * every detected building as a footprint polygon + a point icon, one icon
    shape/color per kind (broiler, layers/turkeys/ducks, swine, beef, dairy,
    unknown-species farm, known false positive)
  * every MDE registry permit as a pin (registry points can be hundreds of
    meters off -- the description says how far the detected structures are)
  * lagoon records, sorted by what the imagery actually shows (2026-09-23 review)
  * a FIELD PRIORITY folder at the real structure locations, with the
    satellite screenshots embedded in the balloons

Icons are generated here and embedded in the KMZ (no network needed).
Run scripts/render_field_screenshots.py first (needs its manifest.json).
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw
from pyproj import Geod
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/processed/detections/GEO-ANOM_Task1_Field_Map.kmz"
SHOTS = ROOT / "data/processed/field_screenshots"
GEOD = Geod(ellps="WGS84")

PC = {f["farm_name"]: f for f in json.loads((ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json").read_text())}
DET = json.loads((ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson").read_text())
SAM = json.loads((ROOT / "data/processed/detections/full_registry_sam_lagoon_detections.geojson").read_text())
PCL = json.loads((ROOT / "data/processed/detections/full_registry_pc_lagoon_detections.geojson").read_text())
SHOT_MANIFEST = json.loads((SHOTS / "manifest.json").read_text())
FIG = {f["id"]: f for f in SHOT_MANIFEST["figures"]}
SPOTTED = SHOT_MANIFEST["spotted"]

POULTRY = {"chickens_not_laying_hens"}
POULTRY_OTHER = {"laying_hens_dry_manure", "turkeys", "ducks_liquid_manure"}
EXCLUDED = {"horses"}


# ------------------------------------------------------------------- icons --
def _canvas():
    S = 4
    return Image.new("RGBA", (64 * S, 64 * S), (0, 0, 0, 0)), S


def _finish(img, S):
    return img.resize((64, 64), Image.LANCZOS)


def icon(kind: str, color, outline=(255, 255, 255)) -> Image.Image:
    img, S = _canvas()
    d = ImageDraw.Draw(img)
    c, r = 32 * S, 24 * S
    col, out = tuple(color) + (255,), tuple(outline) + (255,)
    w = 4 * S
    if kind == "circle":
        d.ellipse([c - r, c - r, c + r, c + r], fill=col, outline=out, width=w)
    elif kind == "ring":
        d.ellipse([c - r, c - r, c + r, c + r], outline=col, width=6 * S)
    elif kind == "square":
        d.rectangle([c - r + 3 * S, c - r + 3 * S, c + r - 3 * S, c + r - 3 * S], fill=col, outline=out, width=w)
    elif kind == "diamond":
        d.polygon([(c, c - r - 3 * S), (c + r + 3 * S, c), (c, c + r + 3 * S), (c - r - 3 * S, c)], fill=col, outline=out)
    elif kind == "triangle":
        d.polygon([(c, c - r - 2 * S), (c + r + 3 * S, c + r), (c - r - 3 * S, c + r)], fill=col, outline=out)
    elif kind == "x":
        d.line([c - r, c - r, c + r, c + r], fill=(0, 0, 0, 255), width=12 * S)
        d.line([c - r, c + r, c + r, c - r], fill=(0, 0, 0, 255), width=12 * S)
        d.line([c - r, c - r, c + r, c + r], fill=col, width=8 * S)
        d.line([c - r, c + r, c + r, c - r], fill=col, width=8 * S)
    elif kind == "star":
        import math
        pts = []
        for i in range(10):
            ang = math.radians(-90 + i * 36)
            rr = (r + 6 * S) if i % 2 == 0 else (r - 4 * S) * 0.62 + 4 * S
            pts.append((c + rr * math.cos(ang), c + rr * math.sin(ang)))
        d.polygon(pts, fill=col, outline=out)
    elif kind == "pin":
        d.ellipse([c - 18 * S, 6 * S, c + 18 * S, 42 * S], fill=col, outline=out, width=w)
        d.polygon([(c - 13 * S, 34 * S), (c + 13 * S, 34 * S), (c, 60 * S)], fill=col, outline=out)
        d.ellipse([c - 6 * S, 18 * S, c + 6 * S, 30 * S], fill=(255, 255, 255, 255))
    elif kind == "flag":
        d.ellipse([c - 22 * S, 4 * S, c + 22 * S, 48 * S], fill=col, outline=(0, 0, 0, 255), width=w)
        d.polygon([(c - 15 * S, 40 * S), (c + 15 * S, 40 * S), (c, 62 * S)], fill=col, outline=(0, 0, 0, 255))
        d.rectangle([c - 3 * S, 13 * S, c + 3 * S, 30 * S], fill=(255, 255, 255, 255))
        d.ellipse([c - 4 * S, 33 * S, c + 4 * S, 41 * S], fill=(255, 255, 255, 255))
    return _finish(img, S)


# key -> (icon shape, RGB color, label, point icon scale)
KINDS = {
    "poultry":        ("circle", (44, 140, 60), "Poultry house (broiler)", 0.55),
    "poultry_other":  ("diamond", (27, 163, 156), "Layers / turkeys / ducks house", 0.6),
    "swine":          ("triangle", (214, 64, 159), "Swine barn", 0.8),
    "beef":           ("square", (139, 90, 43), "Beef barn (2026-09-21 detections)", 0.8),
    "dairy":          ("square", (47, 111, 222), "Dairy barn", 0.8),
    "unknown":        ("circle", (122, 122, 122), "Building at a farm with no animal type on file", 0.55),
    "excluded":       ("x", (192, 57, 43), "Known false positive (horse track)", 0.8),
    "lag_real":       ("star", (21, 101, 192), "Looks like a real lagoon (imagery-reviewed)", 1.0),
    "lag_recheck":    ("star", (242, 194, 0), "Recorded 'confirmed' but imagery does NOT support it", 1.0),
    "lag_fp":         ("x", (106, 27, 154), "Likely false positive (imagery-reviewed)", 0.7),
    "lag_spotted":    ("star", (79, 195, 247), "Analyst-spotted lagoon (eyeballed, not model output)", 0.9),
    "lag_unrev":      ("ring", (140, 120, 210), "Automated lagoon candidate, not reviewed (~10% precision)", 0.5),
    "spot_barn":      ("diamond", (255, 255, 255), "Analyst-spotted barns (eyeballed, not model output)", 0.9),
    "farm_poultry":   ("pin", (44, 140, 60), "Registry permit -- poultry", 0.75),
    "farm_other":     ("pin", (27, 163, 156), "Registry permit -- layers/turkeys/ducks", 0.75),
    "farm_swine":     ("pin", (214, 64, 159), "Registry permit -- swine", 0.85),
    "farm_beef":      ("pin", (139, 90, 43), "Registry permit -- beef", 0.85),
    "farm_dairy":     ("pin", (47, 111, 222), "Registry permit -- dairy", 0.85),
    "farm_unknown":   ("pin", (122, 122, 122), "Registry permit -- no animal type", 0.75),
    "farm_excluded":  ("pin", (192, 57, 43), "Registry permit -- horses (not a Task 1 species)", 0.75),
    "priority":       ("flag", (245, 124, 0), "FIELD PRIORITY", 1.25),
}
ICONS = {k: icon(v[0], v[1]) for k, v in KINDS.items()}


def kml_color(rgb, alpha=255) -> str:
    r, g, b = rgb
    return f"{alpha:02x}{b:02x}{g:02x}{r:02x}"


def styles_xml() -> str:
    out = []
    for k, (shape_, rgb, _label, scale) in KINDS.items():
        out.append(
            f'<Style id="s_{k}"><IconStyle><scale>{scale}</scale><Icon><href>files/ic_{k}.png</href></Icon>'
            f'<hotSpot x="0.5" y="{0.05 if shape_ in ("pin", "flag") else 0.5}" xunits="fraction" yunits="fraction"/></IconStyle>'
            f'<LabelStyle><scale>{0.7 if k in ("priority",) or k.startswith("lag_") or k == "spot_barn" else 0}</scale></LabelStyle>'
            f'<LineStyle><color>{kml_color(rgb, 255)}</color><width>2</width></LineStyle>'
            f'<PolyStyle><color>{kml_color(rgb, 70)}</color></PolyStyle>'
            f'<BalloonStyle><text><![CDATA[$[description]]]></text></BalloonStyle></Style>'
        )
    return "\n".join(out)


# -------------------------------------------------------------- helpers ----
def compass(az: float) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(((az % 360) + 22.5) // 45) % 8]


def poly_kml(geom: dict, simplify_deg: float = 2.5e-6) -> str:
    g = shape(geom).simplify(simplify_deg, preserve_topology=True)
    polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
    parts = []
    for p in polys:
        if p.is_empty:
            continue
        coords = " ".join(f"{x:.7f},{y:.7f},0" for x, y in p.exterior.coords)
        parts.append(f"<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{coords}"
                     f"</coordinates></LinearRing></outerBoundaryIs></Polygon>")
    return "".join(parts)


def point_kml(lon, lat) -> str:
    return f"<Point><coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>"


def placemark(name, desc_html, style, geometry, extra="") -> str:
    return (f"<Placemark><name>{escape(name)}</name><description><![CDATA[{desc_html}]]></description>"
            f"<styleUrl>#s_{style}</styleUrl>{extra}{geometry}</Placemark>")


def folder(name, children, open_=False, desc=None) -> str:
    d = f"<description><![CDATA[{desc}]]></description>" if desc else ""
    return f'<Folder><name>{escape(name)}</name><open>{1 if open_ else 0}</open>{d}{"".join(children)}</Folder>'


def kind_for(animal_type: str) -> str:
    if animal_type in POULTRY:
        return "poultry"
    if animal_type in POULTRY_OTHER:
        return "poultry_other"
    if animal_type == "swine_55_lbs":
        return "swine"
    if animal_type == "cattle_includes_heifers":
        return "beef"
    if animal_type == "dairy_cattle":
        return "dairy"
    if animal_type in EXCLUDED:
        return "excluded"
    return "unknown"


def img_tag(fig_id: str, width=560) -> str:
    return f'<br><img src="files/img/{fig_id}.jpg" width="{width}"><br>' if fig_id in FIG else ""


# ------------------------------------------------------------------ data ---
DETS_BY_FARM: dict[str, list] = {}
for f in DET["features"]:
    DETS_BY_FARM.setdefault(f["properties"]["farm_name"], []).append(f)


def farm_centroid(farm: str):
    cs = [shape(f["geometry"]).centroid for f in DETS_BY_FARM.get(farm, [])]
    return (sum(c.x for c in cs) / len(cs), sum(c.y for c in cs) / len(cs)) if cs else None


def offset_text(farm: str) -> str:
    c = farm_centroid(farm)
    if not c:
        return "no structures detected"
    f = PC[farm]
    az, _, d = GEOD.inv(f["lon"], f["lat"], c[0], c[1])
    tag = " <b style='color:#c0392b'>(registry point is far off)</b>" if d > 400 else ""
    return f"detected structures are {d:,.0f} m {compass(az)} of the registry point{tag}"


# --------------------------------------------------------------- sections ---
def buildings_folders() -> tuple[list[str], dict]:
    groups: dict[str, dict[str, list]] = {}
    for farm, feats in DETS_BY_FARM.items():
        f = PC[farm]
        k = kind_for(f["animal_type"])
        for ft in feats:
            p = ft["properties"]
            c = shape(ft["geometry"]).centroid
            desc = (f"<b>{escape(farm)}</b><br>County: {escape(f['county'])}<br>"
                    f"Registry species: {escape(f['animal_type'])} &middot; headcount {f['headcount']:,}<br>"
                    f"Detected footprint: {p['area_m2']:,.0f} m&sup2; ({p['length_m']:.0f} x {p['width_m']:.0f} m)<br>"
                    f"<small>Pipeline detection on 2023 NAIP. Outline can cover only part of a roof. "
                    f"{offset_text(farm)}.</small>")
            geom = f"<MultiGeometry>{poly_kml(ft['geometry'])}{point_kml(c.x, c.y)}</MultiGeometry>"
            groups.setdefault(k, {}).setdefault(f["county"], []).append(
                placemark(f"{farm[:40]} ({p['length_m']:.0f}x{p['width_m']:.0f} m)", desc, k, geom))
    order = ["poultry", "poultry_other", "swine", "beef", "dairy", "unknown", "excluded"]
    titles = {"poultry": "Buildings - Poultry (broiler)", "poultry_other": "Buildings - Layers / turkeys / ducks",
              "swine": "Buildings - Swine", "beef": "Buildings - Beef", "dairy": "Buildings - Dairy",
              "unknown": "Buildings - farms with NO animal type on file (all look like broiler houses)",
              "excluded": "Buildings - KNOWN FALSE POSITIVES (Pimlico Race Course)"}
    folders, counts = [], {}
    for k in order:
        if k not in groups:
            continue
        n = sum(len(v) for v in groups[k].values())
        counts[k] = n
        subs = [folder(f"{county} ({len(pm)})", pm) for county, pm in sorted(groups[k].items())]
        folders.append(folder(f"{titles[k]} ({n})", subs))
    return folders, counts


def farms_folder() -> tuple[str, int]:
    by_kind: dict[str, list] = {}
    # iterate the manifest list (not the name-keyed dict): two permits share a name
    # ("Chaudhry Farm, LLC/Pervaiz Akhtar", two farms 13 km apart) and both need a pin.
    for f in json.loads((ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json").read_text()):
        farm = f["farm_name"]
        k = "farm_" + {"poultry": "poultry", "poultry_other": "other", "swine": "swine", "beef": "beef",
                       "dairy": "dairy", "unknown": "unknown", "excluded": "excluded"}[kind_for(f["animal_type"])]
        n = len(DETS_BY_FARM.get(farm, []))
        dup = " (name shared by two permits; count is for both)" if farm == "Chaudhry Farm, LLC/Pervaiz Akhtar" else ""
        desc = (f"<b>{escape(farm)}</b><br>County: {escape(f['county'])}<br>"
                f"Registry species: {escape(f['animal_type'])} &middot; headcount {f['headcount']:,} &middot; {escape(f['status'])}<br>"
                f"Buildings detected: {n}{dup}<br><small>MDE permit coordinate (geocoded from the address) &mdash; "
                f"{offset_text(farm)}.</small>")
        by_kind.setdefault(k, []).append(placemark(farm[:45], desc, k, point_kml(f["lon"], f["lat"])))
    labels = {"farm_poultry": "Poultry", "farm_other": "Layers / turkeys / ducks", "farm_swine": "Swine",
              "farm_beef": "Beef", "farm_dairy": "Dairy", "farm_unknown": "No animal type on file",
              "farm_excluded": "Horses (not a Task 1 species)"}
    subs = [folder(f"{labels[k]} ({len(v)})", v) for k, v in by_kind.items()]
    total = sum(len(v) for v in by_kind.values())
    return folder(f"Registry permit points ({total}) -- points can be far off, see each balloon", subs), total


REVIEW = {
    # farm -> (style, headline, what the imagery shows)
    "James Donald Dulin": ("lag_real", "Looks like a real lagoon",
                           "Clear teal, regular, banked pond; polygon aligns on both imagery sources."),
    "Hoa Tran/Morning Sun LLC": ("lag_recheck", "Recorded 'confirmed' -- polygon is on a poultry-house roof",
                                 "Gray-blue metal roof with ridge lines, not water."),
    "Roland Todd/Roland's Roaster's": ("lag_recheck", "Recorded 'confirmed' -- imagery does not show a lagoon here",
                                       "On MD iMAP imagery the polygon outlines three poultry houses; on Planetary "
                                       "Computer the same spot is field/wood edge. Sources disagree; unverified."),
    "Jabar Rahim": ("lag_fp", "Likely false positive -- small pond beside a farmhouse",
                    "Pond next to a house and pool, ~500 m from barns; not lagoon-like by siting."),
    "Paul Aaron Hutchison Sr./Home Farm": ("lag_fp", "Likely false positive -- sits on crop field",
                                           "No water and no structure visible; ground check would settle it."),
}
PC_REVIEWED = {
    "Todd Hite/Hite Farms, LLC": "Sits on a building roof / lawn patch, not water",
    "Tue D. Nguyen": "Sits on a building roof / lawn patch, not water",
    "Nathan Wolf/Wolf Farm": "Outlines blue-gray metal barn roofs (roof color reads as water)",
    "William Moore, III": "Outlines blue metal roofs of two buildings",
}


def lagoon_folders() -> tuple[list[str], dict]:
    buckets: dict[str, list] = {"lag_real": [], "lag_recheck": [], "lag_fp": [], "lag_spotted": [], "lag_unrev": []}
    fig_for = {"James Donald Dulin": "B1_lagoon_dulin", "Hoa Tran/Morning Sun LLC": "B2_lagoon_tran",
               "Roland Todd/Roland's Roaster's": "B3_lagoon_roland", "Jabar Rahim": "B4_lagoon_rahim",
               "Paul Aaron Hutchison Sr./Home Farm": "A9_lagoon_hutchison"}
    sam_centroids = []
    for ft in SAM["features"]:
        p = ft["properties"]
        farm = p["farm_name"]
        style, head, shows = REVIEW[farm]
        c = shape(ft["geometry"]).centroid
        sam_centroids.append(c)
        desc = (f"<b>{escape(head)}</b><br>{escape(farm)} ({escape(p['county'])})<br>"
                f"Area {p['area_m2']:,.0f} m&sup2; &middot; solidity {p['solidity']}<br>"
                f"<b>Recorded status:</b> {escape(str(p.get('qa_status')))}<br>"
                f"<b>Imagery review (2026-09-23):</b> {escape(shows)}<br>"
                f"<small>Hand-labeled set, registered on older MD iMAP imagery: position can be off by up to "
                f"~100 m in Google Earth.</small>{img_tag(fig_for.get(farm, ''))}")
        geom = f"<MultiGeometry>{poly_kml(ft['geometry'])}{point_kml(c.x, c.y)}</MultiGeometry>"
        buckets[style].append(placemark(f"{farm[:32]} ({p['area_m2']:,.0f} m2)", desc, style, geom))

    for ft in PCL["features"]:
        p = ft["properties"]
        c = shape(ft["geometry"]).centroid
        if any(GEOD.inv(c.x, c.y, s.x, s.y)[2] < 40 for s in sam_centroids):
            continue  # same lagoon as a hand-labeled record
        farm = p["farm_name"]
        if farm in PC_REVIEWED:
            style = "lag_fp"
            head = "Likely false positive (imagery-reviewed)"
            body = PC_REVIEWED[farm]
        else:
            style = "lag_unrev"
            head = "Automated candidate, NOT reviewed"
            body = "Full automated lagoon list has ~10% precision (CAFOSat and manual audits agree)."
        desc = (f"<b>{head}</b><br>{escape(farm)} ({escape(str(p.get('county')))})<br>"
                f"Area {p['area_m2']:,.0f} m&sup2; &middot; solidity {p['solidity']} &middot; SAM score {p['sam_score']}<br>"
                f"{escape(body)}<br><small>Planetary Computer-registered (aligned with the building layers).</small>")
        geom = f"<MultiGeometry>{poly_kml(ft['geometry'])}{point_kml(c.x, c.y)}</MultiGeometry>"
        buckets[style].append(placemark(f"{farm[:32]} ({p['area_m2']:,.0f} m2)", desc, style, geom))

    labels = {"lag_real": "Lagoons - looks real (imagery-reviewed)",
              "lag_recheck": "Lagoons - recorded 'confirmed' but imagery does NOT support it (recheck)",
              "lag_fp": "Lagoons - likely false positives (imagery-reviewed)",
              "lag_spotted": "Lagoons - analyst-spotted, NOT model output (eyeballed +/- 30 m)",
              "lag_unrev": "Lagoons - automated candidates, not reviewed (~10% precision)"}
    return buckets, labels


def spotted_placemarks() -> tuple[list[str], list[str]]:
    lag, barns = [], []
    fig_for = {"Lester C. Jones & Sons, Inc.": "A4_dairy_lester", "Horizon Organic Dairy, LLC": "A5_dairy_horizon",
               "Matthew Fry/Fair Hill Farms, Inc": "A6_dairy_fry"}
    counters: dict = {}
    for s in SPOTTED:
        farm, kind = s["farm"], s["kind"]
        counters[(farm, kind)] = counters.get((farm, kind), 0) + 1
        n = counters[(farm, kind)]
        f = PC[farm]
        note = ("<small>Eyeballed from the 2023 NAIP imagery (+/- ~30 m). NOT model output -- the pipeline "
                "returned nothing for this farm.</small>")
        if kind == "lagoons":
            desc = (f"<b>Manure lagoon {n} (analyst-spotted)</b><br>{escape(farm)} ({escape(f['county'])})<br>{note}"
                    f"{img_tag(fig_for.get(farm, ''))}")
            lag.append(placemark(f"{farm[:28]} lagoon {n}", desc, "lag_spotted", point_kml(s["lon"], s["lat"])))
        else:
            extra = ""
            if farm == "Matthew Fry/Fair Hill Farms, Inc":
                extra = "<br>Complex is at the very edge of the tile -- may extend further west."
            desc = (f"<b>Dairy barns (analyst-spotted)</b><br>{escape(farm)} ({escape(f['county'])})<br>{note}{extra}"
                    f"{img_tag(fig_for.get(farm, ''))}")
            barns.append(placemark(f"{farm[:28]} barns", desc, "spot_barn", point_kml(s["lon"], s["lat"])))
    return lag, barns


def priority_folder() -> str:
    pm = []

    def add(name, lon, lat, body_html, fig_id=None):
        desc = f"{body_html}{img_tag(fig_id) if fig_id else ''}"
        pm.append(placemark("* " + name, desc, "priority", point_kml(lon, lat)))

    def det_loc(farm):
        return farm_centroid(farm)

    b = "Brandenburg"
    c = det_loc("Dwight Brandenburg/Brandenburg Family Limited Partnership")
    add("BEEF: Brandenburg (Frederick) - real barn, verify", *c,
        "<b>Dwight Brandenburg / Brandenburg Family LP</b><br>Detection added 2026-09-21 (52 x 23 m outline, real "
        "barn is ~65 x 27 m). Silage bags and a round manure store next to it.<br><b>Check:</b> is this an "
        "active beef/heifer barn? How many head? What is the round tank?<br>"
        f"<small>The registry permit point is {offset_text('Dwight Brandenburg/Brandenburg Family Limited Partnership')}.</small>",
        "A1_beef_brandenburg")
    c = det_loc("Panora Acres Inc./Stacy Sellers")
    add("BEEF: Panora Acres (Carroll) - big complex, verify", *c,
        "<b>Panora Acres / Stacy Sellers</b><br>Full livestock complex: several large barns, silos, and TWO ROUND "
        "MANURE TANKS. Pipeline outlined part of just one barn.<br><b>Check:</b> species (beef? dairy?), barn count, "
        "what the round tanks hold, any lagoon.<br>"
        f"<small>{offset_text('Panora Acres Inc./Stacy Sellers')}.</small>", "A2_beef_panora")
    c = det_loc("Bistate Feeders, LLC")
    add("BEEF ref: Bistate Feeders (Caroline) - already detected", *c,
        "<b>Bistate Feeders</b> - 7 long narrow barns detected (111-153 m x 12-14 m). For comparison with the two "
        "beef farms above.", "A3_beef_bistate")

    spot_barn = {s["farm"]: (s["lon"], s["lat"]) for s in SPOTTED if s["kind"] == "barns"}
    lon, lat = spot_barn["Lester C. Jones & Sons, Inc."]
    add("DAIRY: Lester Jones (Kent) - big dairy the model missed", lon, lat,
        "<b>Lester C. Jones &amp; Sons</b> (3,300 head)<br>Four large long-roof barns + THREE manure lagoons; the model "
        "returned zero candidates for the whole tile.<br><b>Check:</b> roof type/material (open-sided? ridge vents?), "
        "barn dimensions, what the lagoons look like from the ground.<br>"
        f"<small>Permit point is ~620 m ENE of these barns.</small>", "A4_dairy_lester")
    lon, lat = spot_barn["Horizon Organic Dairy, LLC"]
    add("DAIRY: Horizon Organic (Kent) - model missed", lon, lat,
        "<b>Horizon Organic Dairy</b> (544 head)<br>Cross-shaped light-roof barn, three manure ponds. Zero model "
        "candidates.<br><b>Check:</b> roof material vs. a poultry house; pond contents.", "A5_dairy_horizon")
    lon, lat = spot_barn["Matthew Fry/Fair Hill Farms, Inc"]
    add("DAIRY: Fry / Fair Hill (Kent) - permit point is WRONG", lon, lat,
        "<b>Matthew Fry / Fair Hill Farms</b> (1,050 head)<br>The permit point is at an empty road junction; the "
        "only dairy-looking complex is ~1 km WEST at the tile edge (this pin, approximate).<br><b>Check:</b> which "
        "is the real farm address?", "A6_dairy_fry")
    f = PC["Oak Bluff Dairy Farms"]
    add("DAIRY: Oak Bluff (Frederick) - no dairy at permit point", f["lon"], f["lat"],
        "<b>Oak Bluff Dairy Farms</b> (1,280 head)<br>No dairy operation visible near the permit point (woods, a big "
        "quarry to the west). Registry geocode likely wrong.<br><b>Check:</b> where is the actual farm?",
        "A7_dairy_oakbluff")
    c = det_loc("Oakland View Farms LLC")
    add("DAIRY ref: Oakland View (Caroline) - the one that works", *c,
        "<b>Oakland View Farms</b> - two long barns; the pipeline outlines about half of one. For comparison.",
        "A8_dairy_oaklandview")
    hut = [shape(x["geometry"]).centroid for x in SAM["features"] if x["properties"]["farm_name"].startswith("Paul Aaron")]
    add("LAGOON: Hutchison (Talbot) - 3 candidates, likely none", sum(c.x for c in hut[:2]) / 2,
        sum(c.y for c in hut[:2]) / 2,
        "<b>Paul Aaron Hutchison Sr. / Home Farm</b><br>Three 'uncertain' lagoon candidates; on the imagery they "
        "sit on crop field with no water.<br><b>Check:</b> is there any pond/lagoon here?"
        "<br><small>MD iMAP-registered: position can be off by up to ~100 m.</small>", "A9_lagoon_hutchison")
    c = shape(next(x for x in SAM["features"] if x["properties"]["farm_name"].startswith("Roland"))["geometry"]).centroid
    add("LAGOON: Roland Todd (Dorchester) - 'confirmed' but imagery disagrees", c.x, c.y,
        "<b>Roland Todd</b> - recorded as a confirmed lagoon, but the imagery shows poultry houses (iMAP) or "
        "field (Planetary Computer) at this spot.<br><b>Check:</b> is there a lagoon on this farm, and where?",
        "B3_lagoon_roland")
    return folder("* FIELD PRIORITY - start here (see PDF)", pm, open_=True,
                  desc="Pins are at the real structure locations, not the registry permit points. Balloons hold "
                       "the satellite screenshots and what to check.")


def main():
    b_folders, counts = buildings_folders()
    farms, n_farms = farms_folder()
    lag_buckets, lag_labels = lagoon_folders()
    spot_lag, spot_barns = spotted_placemarks()
    lag_buckets["lag_spotted"] = spot_lag
    lag_folders = [folder(f"{lag_labels[k]} ({len(v)})", v) for k, v in lag_buckets.items() if v]
    spot_folder = folder(f"Analyst-spotted dairy barns the model missed ({len(spot_barns)})", spot_barns)

    legend_rows = "".join(
        f'<tr><td><img src="files/ic_{k}.png" width="24"></td><td>{escape(v[2])}</td></tr>'
        for k, v in KINDS.items() if k != "priority")
    doc_desc = (
        "<h3>GEO-ANOM Task 1 field map (2026-09-23)</h3>"
        "<p>Building footprints from the U-Net pipeline (2,726), registry permit pins, lagoon records, and a "
        "FIELD PRIORITY folder. <b>Read first:</b><br>"
        "&bull; Registry permit points are geocoded addresses and can be ~1 km off; use the building layers.<br>"
        "&bull; Outlines can cover only part of a roof (Brandenburg: about half).<br>"
        "&bull; Lagoon layers are unreliable: of the 7 hand-recorded lagoons only one (Dulin) looks real on the "
        "imagery; the automated list is ~10% precise.<br>"
        "&bull; 'Analyst-spotted' items were eyeballed from imagery (+/- 30 m) and are NOT model output.</p>"
        f"<table>{legend_rows}</table>")

    kml = ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           '<name>GEO-ANOM Task 1 Field Map</name>'
           f'<description><![CDATA[{doc_desc}]]></description>{styles_xml()}'
           + priority_folder() + spot_folder + "".join(lag_folders) + "".join(b_folders) + farms
           + '</Document></kml>')

    # sanity: well-formed XML
    import xml.etree.ElementTree as ET
    root = ET.fromstring(kml.encode("utf-8"))
    n_pm = len(list(root.iter("{http://www.opengis.net/kml/2.2}Placemark")))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("doc.kml", kml)
        for k, im in ICONS.items():
            buf = io.BytesIO()
            im.save(buf, "PNG")
            z.writestr(f"files/ic_{k}.png", buf.getvalue())
        used = {fid for fid in FIG}
        for fid in used:
            z.write(SHOTS / FIG[fid]["file"], f"files/img/{fid}.jpg")

    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB), {n_pm} placemarks")
    print("buildings:", counts, "| farm pins:", n_farms, "| lagoon groups:", {k: len(v) for k, v in lag_buckets.items()})


if __name__ == "__main__":
    main()
