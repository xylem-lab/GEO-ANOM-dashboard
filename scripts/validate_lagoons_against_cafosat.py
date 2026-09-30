#!/usr/bin/env python3
"""
Validate full_registry_pc_lagoon_detections.geojson (currently flagged as
"unverified candidates, not a trusted detection count" in docs/NEXT_SESSION.md)
against CAFOSat (Hoque et al., arXiv:2606.00548), an independently-labeled,
externally-sourced dataset with per-patch manure-pond annotations for MD/DE.

This does NOT retrain or replace the detector -- it produces a real, audited
precision/recall estimate for the existing 74-candidate full-scale run using
ground truth this project didn't have when that run was made.

Usage:
    python scripts/validate_lagoons_against_cafosat.py
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAFOSAT_CSV = Path.home() / ".cache/huggingface/hub/datasets--oishee3003--CAFOSat/snapshots/152f4c5885c16dd63eddf295a461890d3c761343/CAFOSat.csv"
CANDIDATES_GEOJSON = PROJECT_ROOT / "data/processed/detections/full_registry_pc_lagoon_detections.geojson"
MATCH_RADIUS_M = 300  # ~half a CAFOSat patch width (833px @ 0.6m =~500m), i.e. "same structure/area"

UTM18N = "EPSG:26918"


def load_cafosat_md_de():
    df = pd.read_csv(CAFOSAT_CSV)
    md_de = df[df["state"].isin(["MD", "DE"])].copy()
    md_de["geometry"] = md_de.apply(lambda r: Point(r["refined_x"], r["refined_y"]), axis=1)
    gdf = gpd.GeoDataFrame(md_de, geometry="geometry", crs=UTM18N)
    return gdf


def load_candidates():
    gdf = gpd.read_file(CANDIDATES_GEOJSON)
    gdf = gdf.to_crs(UTM18N)
    gdf["centroid"] = gdf.geometry.centroid
    return gdf


def main():
    cafosat = load_cafosat_md_de()
    candidates = load_candidates()

    print(f"CAFOSat MD/DE patches: {len(cafosat)}  (manure_pond>0: {(cafosat['manure_pond'] > 0).sum()})")
    print(f"Our full-scale candidates (unverified): {len(candidates)}")

    # --- Precision: for each of our candidates, is there independent CAFOSat
    # coverage nearby, and if so does it agree a pond is there? ---
    cafosat_sindex = cafosat.sindex
    precision_rows = []
    for idx, cand in candidates.iterrows():
        buf = cand["centroid"].buffer(MATCH_RADIUS_M)
        possible = list(cafosat_sindex.intersection(buf.bounds))
        nearby = cafosat.iloc[possible]
        nearby = nearby[nearby.geometry.within(buf)]
        if len(nearby) == 0:
            verdict = "no_cafosat_coverage"
        elif (nearby["manure_pond"] > 0).any():
            verdict = "supported"
        else:
            verdict = "contradicted"
        precision_rows.append({
            "farm_name": cand.get("farm_name"),
            "county": cand.get("county"),
            "tile": cand.get("tile"),
            "sam_score": cand.get("sam_score"),
            "verdict": verdict,
            "n_cafosat_nearby": len(nearby),
        })

    prec_df = pd.DataFrame(precision_rows)
    judged = prec_df[prec_df["verdict"] != "no_cafosat_coverage"]
    n_supported = (judged["verdict"] == "supported").sum()
    n_contradicted = (judged["verdict"] == "contradicted").sum()

    print("\n--- Precision (of our 74 candidates) ---")
    print(f"  No independent CAFOSat coverage nearby: {(prec_df['verdict'] == 'no_cafosat_coverage').sum()} / {len(prec_df)}")
    print(f"  Judged by CAFOSat: {len(judged)}")
    print(f"    Supported (CAFOSat also shows a pond within {MATCH_RADIUS_M}m): {n_supported}")
    print(f"    Contradicted (CAFOSat shows no pond there): {n_contradicted}")
    if len(judged) > 0:
        print(f"    CAFOSat-audited precision estimate: {n_supported}/{len(judged)} = {n_supported/len(judged):.1%}")

    # --- Recall: of CAFOSat's MD/DE manure_pond>0 patches, how many have one
    # of our candidates nearby? (caveat: many of these patches may not even
    # correspond to farms in our 417-farm active-permit registry at all --
    # this is a coverage check, not a same-population recall number) ---
    ponds = cafosat[cafosat["manure_pond"] > 0].copy()
    cand_sindex = candidates.set_geometry("centroid").sindex
    cand_geom = candidates.set_geometry("centroid")
    recall_hits = 0
    for idx, pond in ponds.iterrows():
        buf = pond.geometry.buffer(MATCH_RADIUS_M)
        possible = list(cand_sindex.intersection(buf.bounds))
        nearby = cand_geom.iloc[possible]
        nearby = nearby[nearby["centroid"].within(buf)]
        if len(nearby) > 0:
            recall_hits += 1

    print(f"\n--- Coverage check (of {len(ponds)} CAFOSat MD/DE patches with manure_pond>0) ---")
    print(f"  Matched by one of our 74 candidates within {MATCH_RADIUS_M}m: {recall_hits} / {len(ponds)}")
    print("  NOTE: this is NOT a same-population recall number -- CAFOSat's MD/DE")
    print("  patches were not built from our 417-farm active-permit registry, so a")
    print("  miss here may just mean the farm isn't in our registry/imagery footprint")
    print("  at all, not that our detector missed it. Reported as a coverage check,")
    print("  not a recall metric, to avoid overclaiming.")

    out = PROJECT_ROOT / "docs/cafosat_lagoon_validation_result.md"
    with open(out, "w") as f:
        f.write("# CAFOSat-audited validation of full_registry_pc_lagoon_detections.geojson\n\n")
        f.write(f"Generated by `scripts/validate_lagoons_against_cafosat.py`, 2026-09-15.\n\n")
        f.write(f"- CAFOSat MD/DE patches used as independent ground truth: {len(cafosat)} "
                f"(manure_pond>0: {int((cafosat['manure_pond'] > 0).sum())})\n")
        f.write(f"- Our unverified candidates checked: {len(candidates)}\n")
        f.write(f"- No independent CAFOSat coverage nearby: {(prec_df['verdict'] == 'no_cafosat_coverage').sum()}\n")
        f.write(f"- Judged by CAFOSat: {len(judged)}\n")
        f.write(f"  - Supported: {n_supported}\n")
        f.write(f"  - Contradicted: {n_contradicted}\n")
        if len(judged) > 0:
            f.write(f"  - **CAFOSat-audited precision estimate: {n_supported}/{len(judged)} = {n_supported/len(judged):.1%}**\n")
        f.write(f"\n- Coverage check: {recall_hits}/{len(ponds)} CAFOSat MD/DE manure-pond patches "
                f"matched by one of our candidates within {MATCH_RADIUS_M}m (not a same-population recall number -- see script comments).\n")
        f.write("\n## Per-candidate detail\n\n")
        cols = ["farm_name", "county", "tile", "sam_score", "verdict", "n_cafosat_nearby"]
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "|".join(["---"] * len(cols)) + "|\n")
        for _, row in prec_df.iterrows():
            f.write("| " + " | ".join(str(row[c]) for c in cols) + " |\n")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
