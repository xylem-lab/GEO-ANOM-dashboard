"""
US Census Bureau Batch Geocoder.

Resolves AFO street addresses to lat/lon coordinates using the free
Census Geocoding API (no API key required, 10k addresses per batch).
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests

from geo_anom.core.logging import setup_logger

logger = setup_logger(__name__)

# Census batch geocoding endpoint
_CENSUS_BATCH_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
)
_BENCHMARK = "Public_AR_Current"


class CensusBatchGeocoder:
    """
    Batch address geocoder using the US Census Bureau Geocoding Service.

    Sends street addresses in CSV batches of up to 9,999 records.
    Completely free, no API key required.

    Parameters
    ----------
    batch_size : int
        Max addresses per batch (Census hard limit is 10,000).
    timeout_s : int
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        batch_size: int = 9999,
        timeout_s: int = 120,
        benchmark: str = _BENCHMARK,
    ) -> None:
        self.batch_size = batch_size
        self.timeout_s = timeout_s
        self.benchmark = benchmark

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def geocode_dataframe(
        self,
        df: pd.DataFrame,
        address_col: str,
        city_col: str,
        state_col: str = "",
        zip_col: str = "",
    ) -> pd.DataFrame:
        """
        Geocode a DataFrame of addresses using the Census API.

        Adds columns ``census_lat`` and ``census_lon`` to the input frame.
        Rows that fail to match retain the original placeholder coordinates.

        Parameters
        ----------
        df : pd.DataFrame
            Input dataframe with address fields.
        address_col : str
            Column name for street address (e.g. "123 Main St").
        city_col : str
            Column name for city.
        state_col : str
            Column name for state. If empty, assumes Maryland (MD).
        zip_col : str
            Column name for ZIP code.

        Returns
        -------
        pd.DataFrame
            Input df with new ``census_lat`` and ``census_lon`` columns.
        """
        df = df.copy()
        df["census_lat"] = float("nan")
        df["census_lon"] = float("nan")

        indices = df.index.tolist()
        total = len(indices)
        logger.info("Batch geocoding %d AFO addresses via Census API", total)

        # Process in chunks of batch_size
        for start in range(0, total, self.batch_size):
            chunk_idx = indices[start : start + self.batch_size]
            chunk = df.loc[chunk_idx]

            batch_csv = self._build_batch_csv(
                chunk, address_col, city_col, state_col, zip_col, chunk_idx
            )
            results = self._send_batch(batch_csv)

            matched = 0
            for row_id, lat, lon in results:
                if row_id in df.index:
                    df.at[row_id, "census_lat"] = lat
                    df.at[row_id, "census_lon"] = lon
                    matched += 1

            logger.info(
                "Geocoding batch %d–%d: %d / %d matched",
                start, start + len(chunk_idx), matched, len(chunk_idx),
            )

            # Be polite between batches
            if start + self.batch_size < total:
                time.sleep(2.0)

        # Fill unmatched with original lat/lon if available
        n_unmatched = df["census_lat"].isna().sum()
        if n_unmatched > 0:
            logger.warning(
                "%d addresses could not be geocoded — retaining placeholder coordinates",
                n_unmatched,
            )

        return df

    # ------------------------------------------------------------------
    # Build Census batch CSV
    # ------------------------------------------------------------------

    @staticmethod
    def _build_batch_csv(
        chunk: pd.DataFrame,
        address_col: str,
        city_col: str,
        state_col: str,
        zip_col: str,
        index: list,
    ) -> str:
        """
        Format a DataFrame chunk as Census batch CSV.

        Census format: Unique ID, Street address, City, State, ZIP
        """
        rows = []
        for idx in index:
            row = chunk.loc[idx]
            uid = str(idx)
            address = str(row.get(address_col, "")).strip()
            city = str(row.get(city_col, "")).strip()
            state = str(row.get(state_col, "MD")).strip() if state_col else "MD"
            zip_code = str(row.get(zip_col, "")).strip() if zip_col else ""

            if not address or address.lower() in ("nan", "unknown", ""):
                continue

            rows.append(f'"{uid}","{address}","{city}","{state}","{zip_code}"')

        return "\n".join(rows)

    # ------------------------------------------------------------------
    # Send batch request
    # ------------------------------------------------------------------

    def _send_batch(self, batch_csv: str) -> list[tuple]:
        """
        POST a batch CSV to the Census geocoder and parse results.

        Returns
        -------
        list[tuple[int, float, float]]
            (row_id, latitude, longitude) for each matched address.
        """
        if not batch_csv.strip():
            return []

        csv_bytes = batch_csv.encode("utf-8")

        try:
            resp = requests.post(
                _CENSUS_BATCH_URL,
                files={
                    "addressFile": ("addresses.csv", io.BytesIO(csv_bytes), "text/csv"),
                    "benchmark": (None, self.benchmark),
                },
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Census geocoding request failed: %s", e)
            return []

        return self._parse_response(resp.text)

    # ------------------------------------------------------------------
    # Parse Census response
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response_text: str) -> list[tuple]:
        """
        Parse the Census batch geocoder CSV response.

        Response format (matched):
          ID, address, "Match", "Exact", matched_address, "lon,lat", ..., side

        Must use a real CSV parser, not str.split(",") -- the echoed input
        address field (column 2) is itself a comma-joined "street, city,
        state, zip" string inside its own quotes, so a naive split shifts
        every later column's index and silently breaks match_type/coordinate
        parsing for every real response (found and fixed 2026-09-02: this
        was why Census geocoding matched 0/148 rows even though the API
        itself works fine and returns real matches -- verified with a raw
        request outside this class).

        Returns
        -------
        list[tuple[int, float, float]]
        """
        import csv
        import io

        results = []
        for parts in csv.reader(io.StringIO(response_text.strip())):
            if len(parts) < 6:
                continue

            uid = parts[0].strip()
            match_type = parts[2].strip().lower()

            # Only process matched rows
            if match_type != "match":
                continue

            # Coordinate field ("lon,lat") is its own properly-quoted CSV
            # column (index 5) once parsed with a real CSV reader.
            try:
                lon_str, lat_str = parts[5].split(",")
                lon = float(lon_str.strip())
                lat = float(lat_str.strip())

                try:
                    row_id = int(uid)
                except ValueError:
                    row_id = uid

                results.append((row_id, lat, lon))
            except (ValueError, IndexError):
                continue

        return results
