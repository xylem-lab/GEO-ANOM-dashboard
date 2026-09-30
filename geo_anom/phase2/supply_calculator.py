"""
Nutrient Supply Calculator.

Converts validated AFO polygons (from SAM2 + AlphaEarth) and MDE headcount
data into spatially-explicit nutrient supply volumes (N and P₂O₅).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from geo_anom.core.config import get_config, GeoAnomConfig, NutrientCoefficient
from geo_anom.core.geo_utils import meters_sq_to_acres
from geo_anom.core.logging import setup_logger
from geo_anom.phase2.species_capacity import is_poultry_type, model_metadata, predict_poultry_headcount

logger = setup_logger(__name__)


# Mapping from MDE animal type strings to config keys. Kept for any
# already-clean short-form input, but _normalize_animal_type() below no
# longer relies on this being an exhaustive exact-match table -- it wasn't:
# the registry's real animal_type values are raw Socrata column names
# (e.g. "chickens_not_laying_hens", "swine_55_lbs", "cattle_includes_heifers"),
# none of which matched any key here, so every broiler farm -- the dominant
# type in the live MD registry (303/329 in the active set) -- silently got
# annual_N_lbs=0. MDE's Socrata schema has already changed column names once
# (see the endpoint-ID comment in configs/maryland.yaml), so a fixed
# exact-match dict will keep breaking the same way; see the keyword-based
# classifier below instead.
_ANIMAL_TYPE_MAP: dict[str, str] = {
    "broiler": "broiler_chicken",
    "broiler chicken": "broiler_chicken",
    "broilers": "broiler_chicken",
    "chickens": "broiler_chicken",
    "chicken": "broiler_chicken",
    "layer": "layer_chicken",
    "layers": "layer_chicken",
    "layer chicken": "layer_chicken",
    "turkey": "turkey",
    "turkeys": "turkey",
    "dairy": "dairy_cattle",
    "dairy cattle": "dairy_cattle",
    "beef": "beef_cattle",
    "beef cattle": "beef_cattle",
    "cattle": "beef_cattle",
    "swine": "swine",
    "hog": "swine",
    "hogs": "swine",
    "pig": "swine",
    "pigs": "swine",
}

# Keyword classifier for raw Socrata-style column names. Order matters --
# "not_laying" must be checked before bare "laying"/"layer": the real
# registry column "chickens_not_laying_hens" means broilers (meat birds,
# explicitly NOT egg layers) but contains "laying" as a substring, so a
# naive laying-keyword check first would misclassify the dominant animal
# type in the registry as a layer operation.
_ANIMAL_TYPE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("not_laying", "not laying"), "broiler_chicken"),
    (("laying", "layer"), "layer_chicken"),
    (("chicken", "hen", "broiler", "poultry"), "broiler_chicken"),
    (("turkey",), "turkey"),
    (("dairy",), "dairy_cattle"),
    (("cattle", "beef", "heifer", "cow"), "beef_cattle"),
    (("swine", "hog", "pig"), "swine"),
]


class SupplyCalculator:
    """
    Calculates nutrient supply from validated AFO polygons + MDE permits.

    Combines SAM-derived lagoon/structure areas with MDE headcount data
    to produce annual nitrogen (N) and phosphorus (P₂O₅) generation
    volumes per facility.

    Parameters
    ----------
    config : GeoAnomConfig, optional
        Pipeline configuration with nutrient coefficients.
    """

    def __init__(self, config: GeoAnomConfig | None = None) -> None:
        self.config = config or get_config()

    # ------------------------------------------------------------------
    # Main calculation
    # ------------------------------------------------------------------

    def calculate_supply(
        self,
        validated_polygons_gdf: gpd.GeoDataFrame,
        afo_permits_gdf: gpd.GeoDataFrame,
        max_join_distance_km: float = 2.0,
        unmatched_cluster_distance_m: float = 300.0,
    ) -> gpd.GeoDataFrame:
        """
        Calculate nutrient supply from detected buildings, vision-first.

        Species and headcount used to be looked up from the nearest MDE
        permit every time -- meaning a detection with no permit within
        `max_join_distance_km` got `annual_N_lbs=0`, silently, regardless of
        whether it was a real farm. Since MDE's registry is estimated to
        cover a minority of actual facilities, that made the registry a
        hard runtime dependency for a pipeline whose point is supposed to
        be *reducing* that dependency. See docs/task1_completion_criteria.md
        and docs/species_capacity_model_metrics.md for the full reasoning.

        This version still spatial-joins to permits, but only to (a) recover
        a registry species/headcount for comparison and for the species the
        vision model can't yet handle, and (b) group a farm's structures
        together. Every poultry-shaped detected building -- registered or
        not -- gets its headcount from `species_capacity.predict_poultry_headcount()`,
        a model fit on floor area alone with no registry lookup at
        prediction time. Non-poultry species (dairy/beef/swine/etc.) have no
        such model yet -- the upstream U-Net mostly doesn't segment their
        roofs as buildings at all, so there's no detected shape to build one
        from -- and fall back to registry headcount where a permit match
        exists, explicitly flagged as `capacity_source="registry_fallback"`
        rather than presented as vision-derived. A detection with neither a
        registry match nor a poultry-shaped default produces no number,
        honestly, rather than a fabricated one.

        Parameters
        ----------
        validated_polygons_gdf : GeoDataFrame
            Validated AFO polygons (from SAM2 + AlphaEarth filtering).
            Must have columns: geometry, class_name, area_m2, confidence.
        afo_permits_gdf : GeoDataFrame
            MDE permit data with columns: geometry, animal_type, headcount.
        max_join_distance_km : float
            Max distance (km) for nearest-neighbor spatial join to a permit.
        unmatched_cluster_distance_m : float
            Detected buildings with no permit match within
            `max_join_distance_km` are grouped into synthetic farm
            complexes by proximity (DBSCAN, this many meters) so an
            unregistered cluster of barns is still treated as one farm for
            apportionment, the same way a registered farm's barns are.

        Returns
        -------
        GeoDataFrame
            One row per detected structure. `annual_N_lbs`/`annual_P2O5_lbs`
            are each structure's *apportioned share* of its farm/cluster's
            total, weighted by that structure's share of the group's total
            detected floor area (falls back to an even 1/`n_structures_at_farm`
            split only if the group's structures have no usable area data),
            so summing either column across all rows for one group
            reconstructs the correct group-level total, and summing across
            the whole output gives the correct statewide total.
            `capacity_source` records where the headcount came from
            ("vision_poultry_model", "registry_fallback", or "no_data");
            `registry_animal_type`/`registry_headcount` carry the permit's
            own values (when matched) alongside, for comparison, whichever
            source was actually used for the N/P numbers.
        """
        logger.info(
            "Calculating nutrient supply: %d polygons × %d permits",
            len(validated_polygons_gdf), len(afo_permits_gdf),
        )

        # Ensure both are in the same CRS
        polygons = validated_polygons_gdf.copy()
        permits = afo_permits_gdf.copy()

        if polygons.crs is None:
            polygons = polygons.set_crs("EPSG:4326")
        if permits.crs is None:
            permits = permits.set_crs("EPSG:4326")

        # Project to UTM 18N for distance-based join
        polygons_utm = polygons.to_crs("EPSG:32618")
        permits_utm = permits.to_crs("EPSG:32618")

        # Real detection files carry their own "farm_name"/"headcount"
        # properties (see unet_detect.py), which collide with the permit
        # table's columns of the same name. geopandas silently resolves
        # collisions with _left/_right suffixes, so an unqualified
        # row.get("headcount") below would return neither side's real
        # value -- a latent bug that only ever triggered against real
        # full-registry data, never the unit tests (whose fixture polygons
        # don't carry those columns). Renamed here so both sides are
        # unambiguous regardless of what the caller's polygon table has.
        permits_utm = permits_utm.rename(columns={
            "animal_type": "permit_animal_type",
            "headcount": "permit_headcount",
            "farm_name": "permit_farm_name",
        })

        # Spatial join: nearest permit within max_join_distance
        max_dist_m = max_join_distance_km * 1000
        joined = gpd.sjoin_nearest(
            polygons_utm,
            permits_utm,
            how="left",
            max_distance=max_dist_m,
            distance_col="join_distance_m",
        )

        # Buildings with no permit within range still need a group to be
        # apportioned within -- cluster them by proximity so a detected
        # complex of barns with no registry entry is treated as one farm,
        # not N isolated single-building "farms" each demanding its own
        # (impossible) even split. DBSCAN with min_samples=1 means every
        # unmatched point ends up in *some* cluster (possibly of size 1),
        # chained by mutual proximity rather than one fixed centroid.
        unmatched_mask = joined["index_right"].isna()
        group_id = pd.Series(
            [f"permit_{p}" if pd.notna(p) else None for p in joined["index_right"]],
            index=joined.index,
        )
        if unmatched_mask.any():
            centroids = np.array([
                (geom.centroid.x, geom.centroid.y) for geom in joined.loc[unmatched_mask].geometry
            ])
            labels = DBSCAN(eps=unmatched_cluster_distance_m, min_samples=1).fit_predict(centroids)
            group_id.loc[unmatched_mask] = [f"unmatched_{lbl}" for lbl in labels]
        joined = joined.assign(group_id=group_id)

        # Same apportionment logic as before (see the R^2=0.256 note in
        # docs/task1_metrics.md on why floor-area share, not an even split,
        # is the right way to divide a group's total across its buildings),
        # just keyed on group_id instead of only registered permits.
        structures_per_group = joined.groupby("group_id").size()
        area_per_group = joined.groupby("group_id")["area_m2"].sum()

        capacity_meta = None  # lazily fetched, only if any poultry prediction runs

        supply_records = []
        for idx, row in joined.iterrows():
            gid = row["group_id"]
            area_m2 = float(row.get("area_m2", 0))
            n_structures = int(structures_per_group.get(gid, 1))
            group_area_m2 = float(area_per_group.get(gid, 0.0))
            if group_area_m2 > 0:
                area_share = area_m2 / group_area_m2
            else:
                area_share = 1.0 / n_structures

            is_registered = pd.notna(row.get("index_right"))
            registry_animal_type_raw = row.get("permit_animal_type") if is_registered else None
            # is_poultry_type() matches against the RAW MDE registry strings
            # ("chickens_not_laying_hens", not "broiler_chicken") -- it must
            # be checked before _normalize_animal_type() rewrites them, or
            # this check silently always fails and the vision model never
            # fires for a single registered farm, which defeats the entire
            # point and very nearly shipped that way: the old test suite
            # kept passing even with that bug, because it happened to fall
            # through to the exact registry-lookup behavior it was written
            # to test in the first place. Checked directly against
            # is_poultry_type('broiler_chicken') before trusting the tests.
            registry_animal_type = (
                self._normalize_animal_type(registry_animal_type_raw) if is_registered else None
            )
            registry_hc_val = row.get("permit_headcount", 0)
            registry_headcount = (
                int(registry_hc_val) if pd.notna(registry_hc_val) and registry_hc_val else 0
            )

            # A matched permit with an explicit non-poultry species (dairy,
            # beef, swine, horses, ...) is the one case where the vision
            # model should NOT run -- it was never fit on those shapes, and
            # for most of them (dairy especially) the building usually
            # isn't even segmented, so there's nothing to measure anyway.
            # A missing/blank species on a matched permit (the 9 "unknown"
            # registry entries) is deliberately NOT treated as a known
            # non-poultry species: the 2026-09-30 imagery audit found 6 of
            # those 9 are visually ordinary poultry farms, so it gets the
            # vision model too, same as an unmatched detection would.
            registry_species_is_blank = (
                pd.isna(registry_animal_type_raw)
                or str(registry_animal_type_raw).strip().lower() in ("", "unknown")
            )
            matched_non_poultry = (
                is_registered
                and not registry_species_is_blank
                and not is_poultry_type(registry_animal_type_raw)
            )

            if matched_non_poultry:
                capacity_source = "registry_fallback" if registry_headcount > 0 else "no_data"
                animal_type = registry_animal_type
                headcount = registry_headcount
                predicted_headcount = None
                uncertainty_factor = None
            else:
                # Either unmatched (no permit at all -- default assumption:
                # a shape that passed the poultry-house filter is poultry-
                # shaped, see species_capacity_model_metrics.md) or matched
                # to a permit that's poultry-type, "unknown", or missing a
                # species -- in all of those cases headcount comes from the
                # vision model, not a registry lookup. If the registry DOES
                # give a specific poultry subtype (turkey/layer/broiler),
                # that's still used for which nutrient coefficient applies
                # -- using information that happens to be available isn't
                # the same as depending on it: an unmatched detection still
                # gets a real number, defaulting to broiler_chicken, the
                # dominant subtype statewide.
                predicted_headcount, uncertainty_factor = predict_poultry_headcount(
                    group_area_m2, n_structures
                )
                capacity_source = "vision_poultry_model"
                animal_type = (
                    registry_animal_type
                    if registry_animal_type and registry_animal_type != "unknown"
                    else "broiler_chicken"
                )
                headcount = predicted_headcount
                if capacity_meta is None:
                    capacity_meta = model_metadata()

            coeff = self.config.nutrient_coefficients.get(animal_type)
            if coeff and headcount and headcount > 0:
                annual_n = headcount * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year * area_share
                annual_p = headcount * coeff.P2O5_lbs_per_head_per_year * coeff.flocks_per_year * area_share
            else:
                annual_n = 0.0
                annual_p = 0.0
                if headcount and headcount > 0:
                    logger.warning(
                        "No nutrient coefficient for animal type '%s' (original: '%s')",
                        animal_type, registry_animal_type_raw,
                    )

            supply_records.append({
                "geometry": row.geometry,
                "class_name": row.get("class_name", "unknown"),
                "confidence": row.get("confidence", 0.0),
                "farm_name": row.get("farm_name", ""),
                "group_id": gid,
                "animal_type": animal_type,
                "headcount": round(headcount, 1) if headcount else 0,
                "capacity_source": capacity_source,
                "predicted_headcount": round(predicted_headcount, 1) if predicted_headcount else None,
                "predicted_headcount_uncertainty_factor": (
                    round(uncertainty_factor, 2) if uncertainty_factor else None
                ),
                "registry_animal_type": registry_animal_type,
                "registry_headcount": registry_headcount or None,
                "area_m2": area_m2,
                "area_acres": meters_sq_to_acres(area_m2),
                "n_structures_at_farm": n_structures,
                "annual_N_lbs": round(annual_n, 1),
                "annual_P2O5_lbs": round(annual_p, 1),
                "join_distance_m": row.get("join_distance_m", None),
            })

        result = gpd.GeoDataFrame(supply_records, crs="EPSG:32618")
        result = result.to_crs("EPSG:4326")

        # Summary stats
        total_n = result["annual_N_lbs"].sum()
        total_p = result["annual_P2O5_lbs"].sum()
        n_vision = (result["capacity_source"] == "vision_poultry_model").sum()
        n_fallback = (result["capacity_source"] == "registry_fallback").sum()
        n_nodata = (result["capacity_source"] == "no_data").sum()
        logger.info(
            "Supply calculated: %d structures, total N=%.0f lbs/yr, P₂O₅=%.0f lbs/yr "
            "(%d vision-model, %d registry-fallback, %d no-data%s)",
            len(result), total_n, total_p, n_vision, n_fallback, n_nodata,
            f", capacity model cv_r2={capacity_meta['cv_r2_mean']:.2f} n={capacity_meta['n_training_farms']}"
            if capacity_meta else "",
        )

        return result

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_supply_map(
        self,
        gdf: gpd.GeoDataFrame,
        output_path: Path | str,
        driver: str = "GPKG",
    ) -> Path:
        """
        Export the nutrient supply map to GeoPackage or GeoJSON.

        Parameters
        ----------
        gdf : GeoDataFrame
            Supply map from calculate_supply().
        output_path : Path
            Output file path.
        driver : str
            OGR driver ("GPKG" for GeoPackage, "GeoJSON" for JSON).

        Returns
        -------
        Path
            Path to the written file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        gdf.to_file(str(output_path), driver=driver)
        logger.info("Exported supply map → %s (%d features)", output_path, len(gdf))
        return output_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_animal_type(raw: str) -> str:
        """Map an MDE animal type string to a standardised config key.

        Tries the exact-match table first (for already-clean short-form
        input), then falls back to keyword matching against the raw
        Socrata-style column names the live registry actually produces
        (e.g. "chickens_not_laying_hens", "swine_55_lbs") -- see
        _ANIMAL_TYPE_KEYWORDS. Returns the normalized-but-unmapped string
        (not "unknown") when nothing matches, so a genuinely new/rare type
        (e.g. ducks -- no config coefficient exists for them) still shows
        up distinctly in the "no nutrient coefficient" warning instead of
        being silently lumped into "unknown".
        """
        if not raw or pd.isna(raw):
            return "unknown"
        normalized = raw.strip().lower()
        if normalized in _ANIMAL_TYPE_MAP:
            return _ANIMAL_TYPE_MAP[normalized]
        for keywords, mapped in _ANIMAL_TYPE_KEYWORDS:
            if any(kw in normalized for kw in keywords):
                return mapped
        return normalized
