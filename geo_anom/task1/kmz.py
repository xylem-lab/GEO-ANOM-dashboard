"""
Google Earth (KMZ) export, one marker style per animal type.

Layout of the KMZ:
    Detected buildings/
        <species group>/      footprint polygon + centroid icon per building
    Rejected candidates/      (hidden by default) what the shape filter threw
                              out, with the reason -- for checking misses
    Registry permits/         one pin per site, colored by species

Icons are drawn here and embedded, so the KMZ works offline. Species comes
from the registry permit the tile was pulled for (see species.py), not from
the detector.
"""

from __future__ import annotations

import io
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw
from shapely.geometry import shape

from geo_anom.task1.species import GROUPS, species_group

# group -> icon shape
ICON_SHAPES = {
    "broiler": "circle",
    "poultry_other": "diamond",
    "swine": "triangle",
    "beef": "square",
    "dairy": "square",
    "unknown": "circle",
    "excluded": "x",
}
REJECT_RGB = (230, 60, 50)


def _icon_png(kind: str, rgb: tuple) -> bytes:
    S = 4
    img = Image.new("RGBA", (64 * S, 64 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, r = 32 * S, 24 * S
    col, out = tuple(rgb) + (255,), (255, 255, 255, 255)
    if kind == "circle":
        d.ellipse([c - r, c - r, c + r, c + r], fill=col, outline=out, width=4 * S)
    elif kind == "square":
        d.rectangle([c - r + 3 * S, c - r + 3 * S, c + r - 3 * S, c + r - 3 * S], fill=col, outline=out, width=4 * S)
    elif kind == "diamond":
        d.polygon([(c, c - r - 3 * S), (c + r + 3 * S, c), (c, c + r + 3 * S), (c - r - 3 * S, c)], fill=col, outline=out)
    elif kind == "triangle":
        d.polygon([(c, c - r - 2 * S), (c + r + 3 * S, c + r), (c - r - 3 * S, c + r)], fill=col, outline=out)
    elif kind == "x":
        for w, f in ((12 * S, (0, 0, 0, 255)), (8 * S, col)):
            d.line([c - r, c - r, c + r, c + r], fill=f, width=w)
            d.line([c - r, c + r, c + r, c - r], fill=f, width=w)
    elif kind == "pin":
        d.ellipse([c - 18 * S, 6 * S, c + 18 * S, 42 * S], fill=col, outline=out, width=4 * S)
        d.polygon([(c - 13 * S, 34 * S), (c + 13 * S, 34 * S), (c, 60 * S)], fill=col, outline=out)
        d.ellipse([c - 6 * S, 18 * S, c + 6 * S, 30 * S], fill=(255, 255, 255, 255))
    buf = io.BytesIO()
    img.resize((64, 64), Image.LANCZOS).save(buf, "PNG")
    return buf.getvalue()


def _kml_color(rgb: tuple, alpha: int = 255) -> str:
    r, g, b = rgb
    return f"{alpha:02x}{b:02x}{g:02x}{r:02x}"  # KML is aabbggrr


def _styles() -> tuple[str, dict]:
    """KML <Style> blocks and the icon files they reference."""
    xml, files = [], {}
    for group, (_, rgb) in GROUPS.items():
        files[f"icons/{group}.png"] = _icon_png(ICON_SHAPES[group], rgb)
        files[f"icons/pin_{group}.png"] = _icon_png("pin", rgb)
        xml.append(
            f'<Style id="b_{group}"><IconStyle><scale>0.6</scale><Icon><href>icons/{group}.png</href></Icon></IconStyle>'
            f'<LabelStyle><scale>0</scale></LabelStyle>'
            f'<LineStyle><color>{_kml_color(rgb)}</color><width>2.5</width></LineStyle>'
            f'<PolyStyle><color>{_kml_color(rgb, 70)}</color></PolyStyle></Style>'
            f'<Style id="pin_{group}"><IconStyle><scale>0.8</scale><Icon><href>icons/pin_{group}.png</href></Icon>'
            f'<hotSpot x="0.5" y="0" xunits="fraction" yunits="fraction"/></IconStyle></Style>'
        )
    files["icons/rejected.png"] = _icon_png("x", REJECT_RGB)
    xml.append(
        f'<Style id="rejected"><IconStyle><scale>0.45</scale><Icon><href>icons/rejected.png</href></Icon></IconStyle>'
        f'<LabelStyle><scale>0</scale></LabelStyle>'
        f'<LineStyle><color>{_kml_color(REJECT_RGB)}</color><width>1.5</width></LineStyle>'
        f'<PolyStyle><fill>0</fill></PolyStyle></Style>'
    )
    return "".join(xml), files


def _ring(coords) -> str:
    return " ".join(f"{x:.7f},{y:.7f},0" for x, y in coords)


def _geometry_kml(geom) -> str:
    """Footprint polygon(s) + a centroid point, as one MultiGeometry."""
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    parts = []
    for p in polys:
        p = p.simplify(2.5e-6)
        inner = "".join(
            f"<innerBoundaryIs><LinearRing><coordinates>{_ring(i.coords)}</coordinates></LinearRing></innerBoundaryIs>"
            for i in p.interiors
        )
        parts.append(
            f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{_ring(p.exterior.coords)}"
            f"</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>"
        )
    c = geom.centroid
    parts.append(f"<Point><coordinates>{c.x:.7f},{c.y:.7f},0</coordinates></Point>")
    return f"<MultiGeometry>{''.join(parts)}</MultiGeometry>"


def _description(p: dict) -> str:
    rows = [
        ("Farm (registry)", p.get("farm_name")),
        ("County", p.get("county")),
        ("Registry animal type", p.get("animal_type")),
        ("Registry headcount", f"{p['headcount']:,}" if p.get("headcount") else None),
        ("Footprint", f"{p.get('area_m2')} m² · {p.get('length_m')} × {p.get('width_m')} m"),
        ("Model confidence (mean prob.)", p.get("mean_prob")),
        ("Rejected because", p.get("reject_reasons")),
        ("Imagery date", (p.get("naip_datetime") or "")[:10] or None),
        ("Candidate id", p.get("candidate_id")),
    ]
    return "<br>".join(f"<b>{escape(k)}:</b> {escape(str(v))}" for k, v in rows if v is not None)


def _placemark(name: str, style: str, desc: str, geom_kml: str) -> str:
    return (f"<Placemark><name>{escape(name)}</name><styleUrl>#{style}</styleUrl>"
            f"<description><![CDATA[{desc}]]></description>{geom_kml}</Placemark>")


def _folder(name: str, children: list, visible: bool = True, open_: bool = False) -> str:
    return (f"<Folder><name>{escape(name)}</name><visibility>{int(visible)}</visibility>"
            f"<open>{int(open_)}</open>{''.join(children)}</Folder>")


def write_kmz(features: list[dict], out_path: Path, sites: list[dict] | None = None,
              title: str = "GEO-ANOM Task 1 buildings") -> Path:
    """Write detections (kept and, if present, rejected) to a KMZ.

    `features` are GeoJSON features as produced by detect.detect_site();
    a feature with properties.kept == False goes to the hidden
    "Rejected candidates" folder. `sites` (manifest entries) adds registry pins.
    """
    styles, files = _styles()

    by_group = defaultdict(list)
    rejected = []
    for f in features:
        p = f["properties"]
        geom = shape(f["geometry"])
        group = p.get("species_group") or species_group(p.get("animal_type"))
        if p.get("kept", True):
            by_group[group].append(_placemark(
                f"{GROUPS[group][0]} – {p.get('farm_name', '')}", f"b_{group}", _description(p), _geometry_kml(geom)))
        else:
            rejected.append(_placemark(
                f"Rejected – {p.get('farm_name', '')}", "rejected", _description(p), _geometry_kml(geom)))

    folders = [_folder(
        "Detected buildings",
        [_folder(f"{GROUPS[g][0]} ({len(by_group[g])})", by_group[g], open_=False)
         for g in GROUPS if by_group[g]],
        open_=True,
    )]
    if rejected:
        folders.append(_folder(f"Rejected candidates ({len(rejected)}) – filter reasons in balloon",
                               rejected, visible=False))
    if sites:
        pins = defaultdict(list)
        for s in sites:
            g = species_group(s.get("animal_type"))
            desc = _description({
                "farm_name": s["farm_name"], "county": s.get("county"),
                "animal_type": s.get("animal_type"), "headcount": s.get("headcount"),
                "naip_datetime": s.get("naip_datetime"),
            }) + "<br><i>Registry points can be hundreds of meters from the real barns.</i>"
            pins[g].append(_placemark(s["farm_name"], f"pin_{g}", desc,
                                      f"<Point><coordinates>{s['lon']:.7f},{s['lat']:.7f},0</coordinates></Point>"))
        folders.append(_folder("Registry permits",
                               [_folder(f"{GROUPS[g][0]} ({len(pins[g])})", pins[g]) for g in GROUPS if pins[g]]))

    kml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           f"<name>{escape(title)}</name>{styles}{''.join(folders)}</Document></kml>")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
        for name, data in files.items():
            z.writestr(name, data)
    return out_path
