"""
Nutrient Supply Calculator.

Converts validated AFO polygons (from SAM2 + AlphaEarth) and MDE headcount
data into spatially-explicit nutrient supply volumes (N and P₂O₅).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from geo_anom.core.config import get_config, GeoAnomConfig, NutrientCoefficient
from geo_anom.core.geo_utils import meters_sq_to_acres
from geo_anom.core.logging import setup_logger

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
    ) -> gpd.GeoDataFrame:
        """
        Calculate nutrient supply by spatial-joining polygons with permits.

        Parameters
        ----------
        validated_polygons_gdf : GeoDataFrame
            Validated AFO polygons (from SAM2 + AlphaEarth filtering).
            Must have columns: geometry, class_name, area_m2, confidence.
        afo_permits_gdf : GeoDataFrame
            MDE permit data with columns: geometry, animal_type, headcount.
        max_join_distance_km : float
            Max distance (km) for nearest-neighbor spatial join.

        Returns
        -------
        GeoDataFrame
            One row per detected structure. `annual_N_lbs`/`annual_P2O5_lbs`
            are each structure's *apportioned share* of its farm's total,
            weighted by that structure's share of the farm's total detected
            floor area (falls back to an even 1/`n_structures_at_farm` split
            only if the farm's structures have no usable area data), so
            summing either column across all rows for one farm reconstructs
            the correct farm-level total, and summing across the whole
            output gives the correct statewide total -- not an overcount
            from farms with multiple detected structures, and not an
            even-split assumption that a bigger barn houses the same
            number of birds as a smaller one on the same farm.
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

        # Spatial join: nearest permit within max_join_distance
        max_dist_m = max_join_distance_km * 1000
        joined = gpd.sjoin_nearest(
            polygons_utm,
            permits_utm,
            how="left",
            max_distance=max_dist_m,
            distance_col="join_distance_m",
        )

        # A farm with N detected structures produces N rows here, all
        # matched to the same permit (same "index_right"). Farm-level
        # annual N/P must be divided across these rows before being
        # assigned to each one -- otherwise every structure gets the
        # *full* farm total, and summing annual_N_lbs across the output
        # (as this function's own summary below does) overcounts by a
        # factor of N. This was invisible against the old ~71-detection
        # dataset (rarely >1 polygon per permit); it's certain now that
        # real farms produce 5-20 detected barns routinely.
        #
        # The split is weighted by each structure's share of the farm's
        # total detected floor area, not divided evenly -- an even split
        # implicitly assumes every barn houses the same number of birds,
        # which task1_metrics.md's own headcount-vs-house-count analysis
        # found is a poor assumption (R^2=0.043): farms trade off house
        # count against house size, and floor area is a materially better
        # proxy for stocking capacity (R^2=0.256, log-log). Falls back to
        # an even split only if a farm's structures have no usable area
        # data (area sums to 0) -- can't weight by area that isn't there.
        structures_per_permit = joined.groupby("index_right").size()
        area_per_permit = joined.groupby("index_right")["area_m2"].sum()

        # Calculate nutrient supply for each matched row
        supply_records = []
        for idx, row in joined.iterrows():
            animal_type = self._normalize_animal_type(
                row.get("animal_type", "unknown")
            )
            hc_val = row.get("headcount", 0)
            if pd.isna(hc_val):
                hc_val = 0
            headcount = int(hc_val)

            area_m2 = float(row.get("area_m2", 0))

            permit_idx = row.get("index_right")
            n_structures = (
                int(structures_per_permit.get(permit_idx, 1))
                if pd.notna(permit_idx) else 1
            )
            farm_area_m2 = (
                float(area_per_permit.get(permit_idx, 0.0))
                if pd.notna(permit_idx) else area_m2
            )
            if farm_area_m2 > 0:
                area_share = area_m2 / farm_area_m2
            else:
                # No usable area data for this farm's structures -- fall
                # back to an even split rather than dividing by zero.
                area_share = 1.0 / n_structures

            # Look up nutrient coefficient
            coeff = self.config.nutrient_coefficients.get(animal_type)
            if coeff and headcount > 0:
                annual_n = headcount * coeff.N_lbs_per_head_per_year * coeff.flocks_per_year * area_share
                annual_p = headcount * coeff.P2O5_lbs_per_head_per_year * coeff.flocks_per_year * area_share
            else:
                annual_n = 0.0
                annual_p = 0.0
                if headcount > 0:
                    logger.warning(
                        "No nutrient coefficient for animal type '%s' (original: '%s')",
                        animal_type, row.get("animal_type", "unknown"),
                    )

            supply_records.append({
                "geometry": row.geometry,
                "class_name": row.get("class_name", "unknown"),
                "confidence": row.get("confidence", 0.0),
                "farm_name": row.get("farm_name", ""),
                "animal_type": animal_type,
                "headcount": headcount,
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
        logger.info(
            "Supply calculated: %d facilities, total N=%.0f lbs/yr, P₂O₅=%.0f lbs/yr",
            len(result), total_n, total_p,
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
