"""
MDE AFO Public Registry Downloader.

Downloads and processes the Maryland Department of the Environment (MDE)
Animal Feeding Operation permit registry from the Socrata Open Data portal.
Produces a GeoDataFrame of active AFO locations for targeting NAIP downloads.
"""

from __future__ import annotations

import io
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from geo_anom.core.config import get_config, GeoAnomConfig
from geo_anom.core.geo_utils import BBox
from geo_anom.core.logging import setup_logger
from geo_anom.phase1.census_geocoder import CensusBatchGeocoder

logger = setup_logger(__name__)


class AFORegistryClient:
    """
    Client for the MDE AFO Public Search data on opendata.maryland.gov.

    Attributes
    ----------
    config : GeoAnomConfig
        Pipeline configuration (endpoints, filtering rules, etc.).
    """

    def __init__(self, config: GeoAnomConfig | None = None) -> None:
        self.config = config or get_config()

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_csv(self, output_dir: Path | str | None = None) -> Path:
        """
        Download the full AFO permit registry as CSV.

        Parameters
        ----------
        output_dir : Path, optional
            Directory to save the CSV. Defaults to ``data/raw/afo_permits/``.

        Returns
        -------
        Path
            Path to the saved CSV file.
        """
        output_dir = Path(output_dir) if output_dir else self.config.raw_dir / "afo_permits"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "mde_afo_permits.csv"

        url = self.config.endpoints.afo_registry_csv
        logger.info("Downloading MDE AFO registry from %s", url)

        resp = requests.get(url, timeout=60)
        resp.raise_for_status()

        output_path.write_bytes(resp.content)
        logger.info("Saved %d bytes → %s", len(resp.content), output_path)
        return output_path

    def download_json(self, limit: int = 50000) -> list[dict]:
        """
        Download AFO records via the Socrata JSON API.

        Parameters
        ----------
        limit : int
            Max records to retrieve (Socrata default is 1000).

        Returns
        -------
        list[dict]
            Raw JSON records.
        """
        url = self.config.endpoints.afo_registry_json
        params = {"$limit": limit}
        logger.info("Fetching AFO JSON from %s (limit=%d)", url, limit)

        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
            records = resp.json()
            logger.info("Retrieved %d AFO records", len(records))
            return records
        except requests.exceptions.HTTPError as e:
            logger.error("Failed to download AFO registry: %s", e)
            raise

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_permits(self, data: Path | str | list[dict]) -> gpd.GeoDataFrame:
        """
        Parse downloaded AFO data (CSV or JSON list) into a GeoDataFrame.

        The MDE dataset columns vary, so we normalise the key fields:
        - farm_name, farm_designation (CAFO/MAFO), primary_animal_type,
          number_of_animals, status, farm_city, farm_county, farm_zip

        Geocoding is approximate: we use the farm zip code centroid.

        Returns
        -------
        gpd.GeoDataFrame
            With Point geometry from geocoded zip centroids.
        """
        if isinstance(data, list):
            logger.info("Parsing %d AFO permits from JSON records", len(data))
            df = pd.DataFrame(data).astype(str)
        else:
            csv_path = Path(data)
            logger.info("Parsing AFO permits from CSV: %s", csv_path)
            df = pd.read_csv(csv_path, dtype=str)

        # Normalise column names to snake_case
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # The new Socrata format splits animal counts into separate columns 
        # (e.g., "horses", "dairy_cattle", "poultry").
        # We find the column with the largest number and treat it as the primary type.
        animal_keywords = [
            "horse", "cattle", "swine", "poultry", "broiler", "layer", 
            "hen", "chicken", "sheep", "goat", "duck", "turkey", "veal", "pig", "cow"
        ]
        
        # Identify numeric animal columns
        animal_cols = [
            c for c in df.columns 
            if any(k in c.lower() for k in animal_keywords)
            and not any(x in c.lower() for x in ["qty", "building", "acres", "date", "noi", "status"])
        ]
        
        df["headcount"] = 0
        df["animal_type"] = "unknown"
        
        # Check standard columns first
        headcount_col = self._find_column(df, ["number_of_animals", "headcount", "animal_count", "animal_headcount"])
        animal_col = self._find_column(df, ["primary_animal_type", "animal_type", "primary_type_of_animal"])
        
        # Check if standard headcount column actually has data
        has_standard_data = False
        if headcount_col:
            temp_hc = pd.to_numeric(df[headcount_col], errors="coerce").fillna(0).sum()
            if temp_hc > 0:
                has_standard_data = True

        if headcount_col and animal_col and has_standard_data:
            logger.info("Using standard headcount column: %s", headcount_col)
            df["headcount"] = pd.to_numeric(df[headcount_col], errors="coerce").fillna(0).astype(int)
            df["animal_type"] = df[animal_col].str.strip().str.lower()
        elif animal_cols:
            logger.info("Using animal-specific columns: %s", animal_cols)
            # Ensure they are numeric
            for col in animal_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            
            # For each row, take the max count among animal columns
            df["headcount"] = df[animal_cols].max(axis=1)
            # Find the index (column name) of the max value
            df["animal_type"] = df[animal_cols].idxmax(axis=1)
            
            # Reset to unknown if max is 0
            df.loc[df["headcount"] == 0, "animal_type"] = "unknown"
            
            n_non_zero = (df["headcount"] > 0).sum()
            logger.info("Extracted %d non-zero animal headcounts from %d columns", n_non_zero, len(animal_cols))
        else:
            logger.warning("No animal columns matching keywords in schema. Columns: %s", list(df.columns)[:20])

        # Status
        status_col = self._find_column(df, ["status", "permit_status"])
        if status_col:
            df["status"] = df[status_col].str.strip()
        else:
            df["status"] = "Unknown"

        # Farm designation
        desig_col = self._find_column(df, ["farm_designation", "designation"])
        if desig_col:
            df["designation"] = df[desig_col].str.strip().str.upper()
        else:
            df["designation"] = "UNKNOWN"

        # Location columns
        county_col = self._find_column(df, ["farm_county", "county"])
        city_col = self._find_column(df, ["farm_city", "city"])
        zip_col = self._find_column(df, ["farm_zip", "zip_code", "farm_zip_code"])
        city_state_zip_col = self._find_column(df, ["city_state_zip"])

        df["county"] = df[county_col].str.strip() if county_col else "Unknown"
        
        # Extract City
        if city_col:
            df["city"] = df[city_col].str.strip()
        elif city_state_zip_col:
            df["city"] = df[city_state_zip_col].str.split(',').str[0].str.strip()
        else:
            df["city"] = "Unknown"
            
        # Extract Zip Code
        if zip_col:
            df["zip_code"] = df[zip_col].str.strip().str[:5]
        elif city_state_zip_col:
            df["zip_code"] = df[city_state_zip_col].str.extract(r'(\d{5})')[0]
        else:
            df["zip_code"] = "00000"

        # Farm name
        name_col = self._find_column(df, ["farm_name", "name"])
        df["farm_name"] = df[name_col].str.strip() if name_col else "Unknown Farm"

        # Step 1: Use existing lat/lon if present
        df = self._geocode_by_zip(df)

        # Step 2: Refine with Census batch geocoder where lat/lon is placeholder
        address_col = self._find_column(df, ["farm_address", "address", "street_address"])
        if address_col:
            df = self.geocode_with_census(df, address_col, "city", "zip_code")
        else:
            logger.info(
                "No street address column found — using zip centroid approximation"
            )

        # Build GeoDataFrame
        gdf = gpd.GeoDataFrame(
            df[["farm_name", "designation", "animal_type", "headcount",
                "status", "city", "county", "zip_code", "latitude", "longitude"]],
            geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
            crs="EPSG:4326",
        )

        logger.info("Parsed %d AFO permits → GeoDataFrame", len(gdf))
        return gdf

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter_active_permits(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Filter to permits with active statuses as defined in config.

        Returns
        -------
        gpd.GeoDataFrame
            Subset of active permits.
        """
        active = self.config.afo_targeting.active_statuses
        mask = gdf["status"].isin(active)
        result = gdf[mask].copy()
        logger.info(
            "Filtered %d → %d active permits (statuses: %s)",
            len(gdf), len(result), active,
        )
        return result

    def filter_by_county(self, gdf: gpd.GeoDataFrame, county: str) -> gpd.GeoDataFrame:
        """Filter permits by county name (case-insensitive partial match)."""
        mask = gdf["county"].str.lower().str.contains(county.lower(), na=False)
        result = gdf[mask].copy()
        logger.info("Filtered to %d permits in county '%s'", len(result), county)
        return result

    # ------------------------------------------------------------------
    # Target bbox generation
    # ------------------------------------------------------------------

    def get_target_bboxes(
        self, gdf: gpd.GeoDataFrame, buffer_km: float | None = None
    ) -> list[BBox]:
        """
        Create analysis bounding boxes around each AFO location.

        Parameters
        ----------
        gdf : GeoDataFrame
            AFO locations with Point geometries.
        buffer_km : float, optional
            Buffer radius in km. Defaults to config value (2.0 km).

        Returns
        -------
        list[BBox]
            One bounding box per AFO, suitable for NAIP tile requests.
        """
        buffer_km = buffer_km or self.config.afo_targeting.buffer_km
        bboxes = []
        for _, row in gdf.iterrows():
            pt = row.geometry
            if pt is None or pt.is_empty:
                continue
            bb = BBox.from_point(lon=pt.x, lat=pt.y, buffer_km=buffer_km)
            bboxes.append(bb)

        logger.info("Generated %d target bboxes (buffer=%.1f km)", len(bboxes), buffer_km)
        return bboxes

    # ------------------------------------------------------------------
    # Geocoding
    # ------------------------------------------------------------------

    def geocode_with_census(
        self,
        df: pd.DataFrame,
        address_col: str,
        city_col: str,
        zip_col: str = "",
    ) -> pd.DataFrame:
        """
        Improve geocoding accuracy using the Census Batch Geocoder.

        Attempts geocoding for rows where lat/lon are missing (NaN -- the
        live MDE registry has genuine gaps here, not just placeholder rows)
        as well as rows where lat/lon equal the Maryland centroid placeholder
        (lat≈38.80, lon≈-75.80). Originally this only checked the placeholder
        value, which never matched true NaN (NaN.round(2) == 38.80 is always
        False in pandas), so the ~22% of live registry rows with no lat/lon
        at all silently skipped Census geocoding entirely and fell through as
        permanently un-locatable -- found and fixed 2026-09-02.

        Parameters
        ----------
        df : DataFrame
            Permit dataframe (already processed by _geocode_by_zip).
        address_col : str
            Column name with street address.
        city_col : str
            Column name with city.
        zip_col : str
            Column name with ZIP code.

        Returns
        -------
        pd.DataFrame
            DataFrame with improved lat/lon for matched addresses.
        """
        geocoder = CensusBatchGeocoder(
            batch_size=self.config.geocoding.batch_size,
            timeout_s=self.config.geocoding.timeout_s,
            benchmark=self.config.geocoding.census_benchmark,
        )

        # Geocode rows using the centroid placeholder OR missing lat/lon
        # entirely (true NaN from the live registry) -- see docstring.
        is_placeholder = (
            (df["latitude"].round(2) == 38.80) &
            (df["longitude"].round(2) == -75.80)
        )
        is_missing = df["latitude"].isna() | df["longitude"].isna()
        needs_geocoding = is_placeholder | is_missing
        logger.info(
            "%d / %d AFO records need Census geocoding (%d placeholder, %d missing)",
            needs_geocoding.sum(), len(df), is_placeholder.sum(), is_missing.sum(),
        )

        if not needs_geocoding.any():
            return df

        subset = df[needs_geocoding].copy()
        geocoded = geocoder.geocode_dataframe(
            subset, address_col=address_col, city_col=city_col,
            state_col="", zip_col=zip_col,
        )

        # Update main dataframe with census results
        matched = geocoded["census_lat"].notna()
        df.loc[geocoded[matched].index, "latitude"] = geocoded.loc[matched, "census_lat"]
        df.loc[geocoded[matched].index, "longitude"] = geocoded.loc[matched, "census_lon"]

        logger.info(
            "Census geocoder matched %d / %d placeholder records",
            matched.sum(), needs_geocoding.sum(),
        )
        return df

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        """Return the first column name from candidates that exists in df."""
        for c in candidates:
            if c in df.columns:
                return c
        return None

    @staticmethod
    def _geocode_by_zip(df: pd.DataFrame) -> pd.DataFrame:
        """
        Approximate geocoding using Maryland zip code centroids.

        This is a lightweight fallback; for production, use a proper geocoding
        service or the MDE's own lat/lon columns if available.
        """
        # Check if lat/lon columns already exist
        lat_col = None
        lon_col = None
        for c in df.columns:
            cl = c.lower()
            if "latitude" in cl or cl == "lat":
                lat_col = c
            elif "longitude" in cl or cl == "lon" or cl == "lng":
                lon_col = c

        if lat_col and lon_col:
            df["latitude"] = pd.to_numeric(df[lat_col], errors="coerce")
            df["longitude"] = pd.to_numeric(df[lon_col], errors="coerce")
            logger.info("Using existing lat/lon columns: %s, %s", lat_col, lon_col)
        else:
            # Fallback: centre of Maryland Eastern Shore as placeholder
            logger.warning(
                "No lat/lon columns found; using Maryland centroid as placeholder. "
                "Consider adding a geocoding service for accurate locations."
            )
            df["latitude"] = 38.80
            df["longitude"] = -75.80

        return df
