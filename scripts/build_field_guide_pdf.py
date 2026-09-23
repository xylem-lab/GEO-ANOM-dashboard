#!/usr/bin/env python3
"""
Builds docs/Task1_Field_Labeling_Guide_2026-09-23.pdf: decision rules, the
farms worth checking in person (with real structure coordinates), and every
satellite screenshot from scripts/render_field_screenshots.py.

Run render_field_screenshots.py first.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image as PILImage
from pyproj import Geod
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (HRFlowable, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "data/processed/field_screenshots"
OUT = ROOT / "docs/Task1_Field_Labeling_Guide_2026-09-23.pdf"
G = Geod(ellps="WGS84")

FOREST = colors.HexColor("#2C5F2D")
CREAM = colors.HexColor("#E7EFDD")
OFFWHITE = colors.HexColor("#F4F5F0")
INK = colors.HexColor("#2B2B2B")
MUTED = colors.HexColor("#6B7566")
RED = colors.HexColor("#A63A2E")
AMBER = colors.HexColor("#FBEFD5")
WHITE = colors.white

PC = {f["farm_name"]: f for f in json.loads((ROOT / "data/raw/naip_tiles_pc_4band_full/manifest.json").read_text())}
DET = json.loads((ROOT / "data/processed/detections/full_registry_unet_tulbure_detections.geojson").read_text())
SAM = json.loads((ROOT / "data/processed/detections/full_registry_sam_lagoon_detections.geojson").read_text())
SM = json.loads((SHOTS / "manifest.json").read_text())
FIGS = SM["figures"]
SPOT = SM["spotted"]

ss = getSampleStyleSheet()
ss.add(ParagraphStyle("DocTitle", fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=FOREST, spaceAfter=6))
ss.add(ParagraphStyle("DocSub", fontName="Helvetica", fontSize=10.5, textColor=MUTED, spaceAfter=10, leading=14))
ss.add(ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=15, textColor=FOREST, spaceBefore=14, spaceAfter=6))
ss.add(ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11.5, textColor=INK, spaceBefore=8, spaceAfter=3))
ss.add(ParagraphStyle("Body", fontName="Helvetica", fontSize=9.6, textColor=INK, leading=13, spaceAfter=4))
ss.add(ParagraphStyle("Small", fontName="Helvetica", fontSize=8.4, textColor=MUTED, leading=11))
ss.add(ParagraphStyle("Cap", fontName="Helvetica", fontSize=8.6, textColor=INK, leading=11.4, spaceAfter=10))
ss.add(ParagraphStyle("Cell", fontName="Helvetica", fontSize=8.3, textColor=INK, leading=10.4))
ss.add(ParagraphStyle("CellHead", fontName="Helvetica-Bold", fontSize=8.3, textColor=WHITE, leading=10.4))
ss.add(ParagraphStyle("FigTitle", fontName="Helvetica-Bold", fontSize=10.2, textColor=FOREST, spaceBefore=4, spaceAfter=3))


def P(t, st="Cell"):
    return Paragraph(t, ss[st])


def table(header, rows, widths, head_bg=FOREST):
    data = [[P(h, "CellHead") for h in header]] + [[P(str(c)) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), head_bg),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, OFFWHITE]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D8DED2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def box(paragraphs, bg=AMBER, border=colors.HexColor("#E0B860")):
    t = Table([[paragraphs]], colWidths=[7.2 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


# ------------------------------------------------------------ coordinates ---
def det_centroid(farm):
    cs = [shape(f["geometry"]).centroid for f in DET["features"] if f["properties"]["farm_name"] == farm]
    return (sum(c.x for c in cs) / len(cs), sum(c.y for c in cs) / len(cs)) if cs else None


def spotted(farm, kind="barns"):
    pts = [(s["lon"], s["lat"]) for s in SPOT if s["farm"] == farm and s["kind"] == kind]
    return pts[0] if pts else None


def ll(lon, lat):
    return f"{lat:.5f}, {lon:.5f}"


def offset(farm, lonlat):
    f = PC[farm]
    az, _, d = G.inv(f["lon"], f["lat"], lonlat[0], lonlat[1])
    return f"{d:,.0f} m {['N','NE','E','SE','S','SW','W','NW'][int(((az % 360) + 22.5)//45) % 8]}"


def build():
    story = []
    W = 7.2 * inch

    story.append(Paragraph("GEO-ANOM Task 1 — Field Labeling Guide", ss["DocTitle"]))
    story.append(Paragraph(
        "Decision rules, the specific farms worth checking in person (with the <b>real structure "
        "coordinates</b>), and the satellite screenshots behind every call. Updated 2026-09-23. "
        "Companion file: GEO-ANOM_Task1_Field_Map.kmz (same layers, offline in Google Earth).", ss["DocSub"]))

    story.append(box([
        P("<b>What changed in this version — read first</b>", "Body"),
        P("&bull; <b>Registry permit points are often hundreds of meters off.</b> Most beef/dairy farms checked were "
          "400-860 m from their real barns (Brandenburg 861 m, Bistate 845 m, Lester Jones 618 m, Oakland View 615 m, "
          "Panora 423 m; Horizon was close at 94 m) and two dairy permits do not sit on a dairy at all. Navigate to the "
          "structure coordinates in \u00a74, not the permit pin.", "Cell"),
        P("&bull; <b>Detection outlines are often partial.</b> Brandenburg's outline covers about half its barn; Panora's "
          "covers part of one barn in a complex of several. Floor-area numbers for non-poultry farms are underestimates.", "Cell"),
        P("&bull; <b>Lagoon records were checked against imagery and mostly do not hold up.</b> Of the 7 hand-recorded "
          "lagoons only Dulin looks real. Tran and Roland Todd (recorded 'confirmed') are roofs / not visible; "
          "Rahim is a house pond; Hutchison is crop field. The most common false positive is a blue-gray metal roof.", "Cell"),
        P("&bull; <b>Two dairy farms are true model misses</b> (Lester Jones, Horizon: big conventional barns + lagoons "
          "at the location, zero output), <b>two are registry errors</b> (Fry, Oak Bluff).", "Cell"),
    ]))
    story.append(Spacer(1, 6))

    # ---- legend
    story.append(Paragraph("How to read the pictures", ss["H1"]))
    sw = lambda rgb: Table([[""]], colWidths=[0.42 * inch], rowHeights=[0.16 * inch],
                           style=[("BACKGROUND", (0, 0), (-1, -1), colors.Color(*[c / 255 for c in rgb])),
                                  ("BOX", (0, 0), (-1, -1), 0.6, colors.black)])
    leg = [
        (sw((60, 255, 90)), "Building detection kept by the pipeline (label = length x width)"),
        (sw((255, 150, 0)), "Raw model candidate that the shape filter dropped"),
        (sw((30, 144, 255)), "Hand-recorded lagoon polygon ('confirmed' in the file)"),
        (sw((255, 225, 0)), "Hand-recorded lagoon polygon, 'uncertain'"),
        (sw((200, 150, 255)), "Automated lagoon candidate"),
        (sw((120, 220, 255)), "Automated candidate marked 'CAFOSat-corroborated'"),
        (sw((255, 60, 60)), "Known false positive"),
        (P("+"), "White crosshair = MDE registry permit point (geocoded address; may be far from the barns)"),
        (P("o"), "White ring + label = analyst annotation eyeballed from the imagery (+/- ~30 m), not model output"),
    ]
    lt = Table([[a, P(b)] for a, b in leg], colWidths=[0.6 * inch, 6.5 * inch])
    lt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(lt)
    story.append(Paragraph("Imagery: 2023 NAIP (Planetary Computer, ~1 m/px) unless a figure says MD iMAP. Left panel of "
                           "each pair is clean imagery — judge it before looking at the boxes.", ss["Small"]))

    # ---- 1. tracking
    story.append(Paragraph("1. What We're Tracking Right Now", ss["H1"]))
    story.append(table(["Species", "Farm-level coverage", "Status (with today's caveats)"], [
        ["Poultry", "358 / 389 farms", "Validated: R²=0.655 vs. ground truth, 99.7% precision, 0.9% true-miss rate"],
        ["Swine", "1 / 1 farms", "Detected -- one barn outlined"],
        ["Beef", "3 / 3 farms", "Detected, but outlines are partial and 2 came from a threshold exception on 2026-09-21; "
                              "both now confirmed to be real barns on imagery (§5 A1-A2)"],
        ["Dairy", "1 / 14 farms", "Open. Lester Jones + Horizon: real barns and lagoons, zero model output. Fry + Oak Bluff: "
                                "permit point is not on a dairy. Other 10: not yet reviewed."],
        ["Lagoons", "1 of 7 recorded looks real", "Automated list ~10% precise; dominant error = blue metal roofs read as water"],
    ], [0.9 * inch, 1.5 * inch, 4.8 * inch]))

    # ---- 2. building rules
    story.append(Paragraph("2. Decision Rules — Buildings", ss["H1"]))
    story.append(table(["Structure seen on the ground", "Call", "Why / evidence"], [
        ["Broiler house (long, enclosed gray/white roof)", "YES", "The pipeline's home case -- §5 C1"],
        ["Layer / turkey / duck house", "YES", "Same signature; layers 7/7 on Cal-Maine (C3), turkeys (C4), ducks (C5)"],
        ["Swine confinement barn", "YES", "Same signature (Grand View, C2)"],
        ["Beef/heifer confinement barn", "YES, outline partial", "Bistate is fully outlined (A3); Brandenburg/Panora only partly (A1, A2)"],
        ["Dairy free-stall barn", "MOSTLY MISSED", "Conventional long-roof barns at Lester Jones and Horizon returned nothing (A4, A5); "
                                                  "Oakland View gets a partial outline (A8)"],
        ["Round grain/feed silo", "NO (correct)", "Circular shape fails the aspect-ratio floor"],
        ["Grandstand / stable / warehouse (non-farm)", "NO -- false positive", "Pimlico Race Course, 4 detections (D1); removed from Task 1 output"],
    ], [2.3 * inch, 1.3 * inch, 3.6 * inch]))

    # ---- 3. water rules
    story.append(Paragraph("3. Decision Rules — Water Bodies (Lagoons)", ss["H1"]))
    story.append(table(["What the imagery shows", "Call", "Example / note"], [
        ["Regular banked pond, teal/brown/dark, next to barns", "YES", "Dulin (B1); Lester Jones's three lagoons and Horizon's three ponds (A4, A5)"],
        ["Blue-gray metal roof (barn or shed)", "NO -- #1 false positive", "Tran (B2), Wolf Farm (D2), Moore (D3), Hite/Nguyen (B5): roof color reads as water"],
        ["Pond beside a house / pool", "NO", "Rahim (B4) -- not the 'river fragment' the older guide says"],
        ["Ordinary crop field", "NO", "Hutchison's three candidates (A9)"],
        ["ROUND concrete manure tank (dark liquid)", "REAL, currently invisible", "Two at Panora (A2). Lagoon-type storage the rectangular-pond detector is not built to find"],
        ["Natural pond in a forest clearing; quarry/borrow pit; river fragment", "NO", "Documented in docs/labeling_guide.md; none of these is pictured here"],
        ["Stormwater retention pond on a farm", "UNRESOLVED", "Flagged as a real confusion class, no rule yet -- if you see one, note its position relative to barns"],
    ], [2.5 * inch, 1.4 * inch, 3.3 * inch]))
    story.append(Paragraph(
        "The lagoon step keeps only candidates near detected barns, so a farm whose barns are missed (Lester Jones, "
        "Horizon) also loses its lagoons.", ss["Small"]))

    story.append(PageBreak())

    # ---- 4. field priority
    story.append(Paragraph("4. Field Priority — Where To Go and What To Check", ss["H1"]))
    story.append(Paragraph(
        "Coordinates are lat, lon of the <b>actual structures</b> (detected or eyeballed), followed by how far the "
        "registry permit point is. Screenshot numbers refer to §5.", ss["Body"]))

    story.append(Paragraph("4a. Beef — are the two added detections real barns?", ss["H2"]))
    b1 = det_centroid("Dwight Brandenburg/Brandenburg Family Limited Partnership")
    b2 = det_centroid("Panora Acres Inc./Stacy Sellers")
    b3 = det_centroid("Bistate Feeders, LLC")
    story.append(table(["Farm", "County", "Go to (structure)", "Structure is, from permit pt", "What to check"], [
        ["Dwight Brandenburg /\nBrandenburg Family LP", "Frederick", ll(*b1), offset("Dwight Brandenburg/Brandenburg Family Limited Partnership", b1),
         "Imagery shows a real ~65x27 m barn, silage bags, a round manure store (A1). Species? Head count? What is the round tank?"],
        ["Panora Acres /\nStacy Sellers", "Carroll", ll(*b2), offset("Panora Acres Inc./Stacy Sellers", b2),
         "Large complex: several barns, silos, two round manure tanks (A2). Beef or dairy? How many barns? Tank contents?"],
        ["Bistate Feeders (reference)", "Caroline", ll(*b3), offset("Bistate Feeders, LLC", b3),
         "Already fully detected (A3). Long narrow barns 111-153 m -- unlike the two above."],
    ], [1.3 * inch, 0.7 * inch, 1.1 * inch, 1.1 * inch, 3.0 * inch]))

    story.append(Paragraph("4b. Dairy — model misses vs. registry errors", ss["H2"]))
    l_b = spotted("Lester C. Jones & Sons, Inc.")
    h_b = spotted("Horizon Organic Dairy, LLC")
    f_b = spotted("Matthew Fry/Fair Hill Farms, Inc")
    ov = det_centroid("Oakland View Farms LLC")
    ob = PC["Oak Bluff Dairy Farms"]
    story.append(table(["Farm", "County", "Go to", "Structure is, from permit pt", "What to check"], [
        ["Lester C. Jones & Sons\n(3,300 head)", "Kent", ll(*l_b) + " (eyeballed)", offset("Lester C. Jones & Sons, Inc.", l_b),
         "MODEL MISS. 4 large long-roof barns + 3 lagoons (A4). Roof type/material? Barn width? Is it open-sided or ridge-vented?"],
        ["Horizon Organic Dairy\n(544 head)", "Kent", ll(*h_b) + " (eyeballed)", offset("Horizon Organic Dairy, LLC", h_b),
         "MODEL MISS. Cross-shaped light-roof barn + 3 ponds at the permit location (A5). Same questions."],
        ["Matthew Fry / Fair Hill\n(1,050 head)", "Kent", ll(*f_b) + " (eyeballed, tile edge)", offset("Matthew Fry/Fair Hill Farms, Inc", f_b),
         "REGISTRY ERROR? Permit point is at an empty road junction (A6). Where is the real farm address?"],
        ["Oak Bluff Dairy Farms\n(1,280 head)", "Frederick", ll(ob["lon"], ob["lat"]) + " (permit pt)", "--",
         "REGISTRY ERROR? No dairy visible near the point; large quarry to the west (A7). Where is the farm?"],
        ["Oakland View Farms\n(reference)", "Caroline", ll(*ov), offset("Oakland View Farms LLC", ov),
         "The one dairy with a kept detection -- two long barns, partial outline (A8). Compare its roof with Lester Jones's."],
    ], [1.3 * inch, 0.7 * inch, 1.5 * inch, 1.05 * inch, 2.65 * inch]))
    story.append(Paragraph("The other 9 dairy permits (Teabow, Mason Dixon, Coldsprings, Whitelyn, Cow Comfort Inn, "
                           "Patterson, My Lady's Manor, Deerspring, Arbaugh's) have not been checked on imagery yet.", ss["Small"]))

    story.append(Paragraph("4c. Lagoons — recorded records worth a real look", ss["H2"]))
    hut = [shape(x["geometry"]).centroid for x in SAM["features"] if x["properties"]["farm_name"].startswith("Paul Aaron")]
    hc = (sum(c.x for c in hut[:2]) / 2, sum(c.y for c in hut[:2]) / 2)
    rol = shape(next(x for x in SAM["features"] if x["properties"]["farm_name"].startswith("Roland"))["geometry"]).centroid
    tran = shape(next(x for x in SAM["features"] if x["properties"]["farm_name"].startswith("Hoa Tran"))["geometry"]).centroid
    story.append(table(["Record", "County", "Go to", "What to check"], [
        ["Roland Todd -- 'confirmed'", "Dorchester", ll(rol.x, rol.y),
         "Imagery sources disagree by several hundred meters and neither shows a lagoon (B3). Is there a lagoon on this farm? Where?"],
        ["Hoa Tran -- 'confirmed'", "Wicomico", ll(tran.x, tran.y),
         "Polygon sits on a poultry-house roof (B2). Any lagoon anywhere on this farm?"],
        ["Paul Aaron Hutchison Sr. (3 candidates)", "Talbot", ll(*hc), "Crop field, no water visible (A9). Any pond here at all?"],
        ["Dulin -- 'confirmed' (reference)", "Caroline", "see KMZ", "The one that looks right (B1): what does a real one look like from the ground?"],
    ], [1.9 * inch, 0.8 * inch, 1.15 * inch, 3.35 * inch]))
    story.append(Paragraph("Hand-recorded lagoons were registered on older MD iMAP imagery: in Google Earth their position "
                           "can be off by up to ~100 m.", ss["Small"]))

    story.append(Paragraph("4d. Registry entries with no animal type", ss["H2"]))
    story.append(Paragraph("All nine have detected buildings and every one looks like a broiler farm (§5 E1). If you "
                           "can confirm what a farm raises, that is a direct fix to the registry.", ss["Body"]))
    unk = [f for f in PC.values() if f["animal_type"] == "unknown"]
    cnt = {}
    for f in DET["features"]:
        cnt[f["properties"]["farm_name"]] = cnt.get(f["properties"]["farm_name"], 0) + 1
    unk.sort(key=lambda f: -cnt.get(f["farm_name"], 0))
    story.append(table(["Farm", "County", "Permit point (lat, lon)", "Buildings"],
                        [[f["farm_name"], f["county"], ll(f["lon"], f["lat"]), cnt.get(f["farm_name"], 0)] for f in unk],
                        [2.7 * inch, 1.0 * inch, 2.4 * inch, 1.1 * inch]))

    story.append(PageBreak())

    # ---- 5. pictures
    story.append(Paragraph("5. Satellite Screenshots", ss["H1"]))
    sec_titles = {"A": "A. Field priority", "B": "B. The recorded lagoons vs. the imagery",
                  "C": "C. What correct detections look like", "D": "D. False positives",
                  "E": "E. Registry entries with no animal type"}
    cur = None
    for fig in FIGS:
        path = SHOTS / fig["file"]
        w, h = PILImage.open(path).size
        width = W if w > h * 1.2 else 5.6 * inch
        img = Image(str(path), width=width, height=width * h / w)
        head = []
        if fig["section"] != cur:
            cur = fig["section"]
            head.append(Paragraph(sec_titles[cur], ss["H2"]))
        story.append(KeepTogether(head + [
            Paragraph(f"[{fig['id'].split('_')[0]}] {fig['title']}", ss["FigTitle"]), img,
            Spacer(1, 3), Paragraph(fig["caption"], ss["Cap"])]))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=CREAM, spaceAfter=6))
    story.append(Paragraph(
        "GEO-ANOM Task 1 Field Labeling Guide, 2026-09-23. Screenshots regenerate with scripts/render_field_screenshots.py; "
        "the KMZ with scripts/build_field_kmz.py; this PDF with scripts/build_field_guide_pdf.py. Technical background: "
        "docs/labeling_guide.md, docs/research_log.md.", ss["Small"]))

    def footer(c, d):
        c.saveState()
        c.setFont("Helvetica", 8)
        c.setFillColor(MUTED)
        c.drawString(0.65 * inch, 0.38 * inch, "GEO-ANOM Task 1 - Field Labeling Guide - 2026-09-23")
        c.drawRightString(7.85 * inch, 0.38 * inch, f"{d.page}")
        c.restoreState()

    doc = SimpleDocTemplate(str(OUT), pagesize=letter, topMargin=0.55 * inch, bottomMargin=0.65 * inch,
                            leftMargin=0.65 * inch, rightMargin=0.65 * inch,
                            title="GEO-ANOM Task 1 Field Labeling Guide", author="GEO-ANOM")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    build()
