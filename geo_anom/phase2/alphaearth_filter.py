"""
AlphaEarth False-Positive Filter.

Uses Google's AlphaEarth Satellite Embedding V1 (via Earth Engine) to
distinguish true AFO infrastructure from false positives (natural ponds,
rooftops, shadows, etc.) based on 64-dimensional embedding similarity.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import geopandas as gpd
from shapely.geometry import Point, Polygon

from geo_anom.core.config import get_config, GeoAnomConfig
from geo_anom.core.logging import setup_logger

logger = setup_logger(__name__)


class AlphaEarthFilter:
    """
    False-positive filter using AlphaEarth Satellite Embedding V1.

    Compares embedding vectors of candidate AFO detections against a
    reference database of known AFOs to flag false positives.

    Parameters
    ----------
    year : int
        Year of annual embedding to use (2017–2024).
    """

    def __init__(
        self,
        year: int | None = None,
        config: GeoAnomConfig | None = None,
    ) -> None:
        self.config = config or get_config()
        self.year = year or self.config.alphaearth.default_year
        self._ee_initialized = False
        self._collection = None
        self._reference_embeddings: dict[str, np.ndarray] | None = None

    # ------------------------------------------------------------------
    # Earth Engine initialization
    # ------------------------------------------------------------------

    def _init_ee(self) -> None:
        """Initialize Earth Engine if not already done."""
        if self._ee_initialized:
            return

        try:
            import ee

            # Try service account auth first
            sa_email = self.config.env.ee_service_account_email
            sa_key = self.config.env.ee_service_account_key_path

            if sa_email and sa_key and Path(sa_key).exists():
                credentials = ee.ServiceAccountCredentials(sa_email, sa_key)
                ee.Initialize(credentials)
                logger.info("Earth Engine initialized with service account: %s", sa_email)
            else:
                # Fall back to interactive/default auth. Modern Earth Engine
                # requires an explicit registered Cloud project -- ee.Initialize()
                # with no args fails with "no project found" even with valid
                # cached credentials.
                project_id = self.config.env.gcs_project_id or None
                ee.Initialize(project=project_id)
                logger.info(
                    "Earth Engine initialized with default credentials (project=%s)",
                    project_id,
                )

            # Load the AlphaEarth collection. NOTE: images in this collection
            # have no "year" property (verified directly against the live
            # collection 2026-09-16: properties are system:time_start/time_end,
            # UTM_ZONE, MODEL_VERSION, DATASET_VERSION -- filtering by
            # ee.Filter.eq("year", ...) as this code previously did matches
            # zero images every time, silently. Filter by date range instead.
            # This is also a per-UTM-zone tiled global collection, not one
            # image per year -- filterBounds is required at query time, done
            # in get_embedding(), not here.
            self._collection = ee.ImageCollection(
                self.config.alphaearth.collection_id
            ).filterDate(f"{self.year}-01-01", f"{self.year + 1}-01-01")

            self._ee_initialized = True

        except Exception as e:
            logger.error("Failed to initialize Earth Engine: %s", e)
            logger.warning(
                "AlphaEarth filtering will be disabled. "
                "Run 'earthengine authenticate' or configure service account."
            )
            self._ee_initialized = False

    # ------------------------------------------------------------------
    # Embedding extraction
    # ------------------------------------------------------------------

    def get_embedding(
        self, geometry: Point | Polygon
    ) -> np.ndarray | None:
        """
        Extract the 64-dim AlphaEarth embedding for a location.

        Parameters
        ----------
        geometry : Point or Polygon
            Location or area to extract the embedding for.
            For Polygons, the centroid embedding is returned.

        Returns
        -------
        np.ndarray or None
            64-dimensional embedding vector, or None if unavailable.
        """
        self._init_ee()
        if not self._ee_initialized:
            return None

        import ee

        # Convert to centroid point
        if isinstance(geometry, Polygon):
            centroid = geometry.centroid
            lon, lat = centroid.x, centroid.y
        else:
            lon, lat = geometry.x, geometry.y

        point = ee.Geometry.Point([lon, lat])

        try:
            # This collection is tiled per UTM zone -- self._collection.first()
            # (previous behavior) grabbed an arbitrary tile that usually didn't
            # even cover this point, so sampling silently returned nothing.
            # Filter to tiles that actually cover this point first.
            image = self._collection.filterBounds(point).mosaic()
            sample = image.sample(
                region=point,
                scale=self.config.alphaearth.sample_scale,
                numPixels=1,
            )

            # Get the first (only) sample
            feature = sample.first()
            props = feature.getInfo()["properties"]

            # Real band names verified directly against the live collection
            # 2026-09-16: "A00".."A63", not "embedding_i"/"bi" as previously
            # assumed (which meant every extraction silently fell back to 0.0
            # for every dimension).
            embedding = np.array([
                props.get(f"A{i:02d}", 0.0)
                for i in range(self.config.alphaearth.embedding_dim)
            ], dtype=np.float32)

            return embedding

        except Exception as e:
            logger.warning("Failed to extract embedding at (%.4f, %.4f): %s", lon, lat, e)
            return None

    # ------------------------------------------------------------------
    # Reference database
    # ------------------------------------------------------------------

    def build_reference_db(
        self,
        known_afos_gdf: gpd.GeoDataFrame,
        non_afo_gdf: gpd.GeoDataFrame | None = None,
    ) -> dict[str, np.ndarray]:
        """
        Build reference embedding vectors for AFO vs non-AFO locations.

        Parameters
        ----------
        known_afos_gdf : GeoDataFrame
            Confirmed AFO locations (from MDE registry).
        non_afo_gdf : GeoDataFrame, optional
            Known non-AFO locations (natural ponds, etc.) for negative examples.

        Returns
        -------
        dict[str, np.ndarray]
            Mean embedding vectors keyed by "afo" and "non_afo".
        """
        logger.info("Building AlphaEarth reference database from %d AFO locations",
                     len(known_afos_gdf))

        # Collect AFO embeddings
        afo_embeddings = []
        for _, row in known_afos_gdf.iterrows():
            emb = self.get_embedding(row.geometry)
            if emb is not None:
                afo_embeddings.append(emb)

        if not afo_embeddings:
            logger.warning("No AFO embeddings extracted; filter will be disabled")
            return {}

        ref = {"afo": np.mean(afo_embeddings, axis=0)}
        logger.info("AFO reference: mean of %d embeddings", len(afo_embeddings))

        # Collect non-AFO embeddings if provided
        if non_afo_gdf is not None and len(non_afo_gdf) > 0:
            non_afo_embeddings = []
            for _, row in non_afo_gdf.iterrows():
                emb = self.get_embedding(row.geometry)
                if emb is not None:
                    non_afo_embeddings.append(emb)

            if non_afo_embeddings:
                ref["non_afo"] = np.mean(non_afo_embeddings, axis=0)
                logger.info("Non-AFO reference: mean of %d embeddings", len(non_afo_embeddings))

        self._reference_embeddings = ref
        return ref

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(
        self,
        candidates_gdf: gpd.GeoDataFrame,
        reference: dict[str, np.ndarray] | None = None,
    ) -> gpd.GeoDataFrame:
        """
        Score candidate detections against the reference AFO embeddings.

        Adds columns:
        - ``ae_score``: cosine similarity to AFO reference (0–1)
        - ``ae_is_afo``: True if score >= threshold
        - ``ae_filtered``: True if flagged as false positive

        Parameters
        ----------
        candidates_gdf : GeoDataFrame
            Candidate AFO polygons from SAM2 segmentation.
        reference : dict, optional
            Reference embeddings. Uses stored reference if not provided.

        Returns
        -------
        GeoDataFrame
            Input GDF with added AlphaEarth classification columns.
        """
        ref = reference or self._reference_embeddings
        if not ref or "afo" not in ref:
            logger.warning(
                "No reference embeddings available; skipping AlphaEarth classification. "
                "All candidates will be marked as AFO."
            )
            candidates_gdf = candidates_gdf.copy()
            candidates_gdf["ae_score"] = 1.0
            candidates_gdf["ae_is_afo"] = True
            candidates_gdf["ae_filtered"] = False
            return candidates_gdf

        threshold = self.config.alphaearth.similarity_threshold
        afo_ref = ref["afo"]

        scores = []
        for _, row in candidates_gdf.iterrows():
            emb = self.get_embedding(row.geometry)
            if emb is not None:
                score = self._cosine_similarity(emb, afo_ref)
            else:
                score = 0.5  # Neutral score if embedding unavailable
            scores.append(score)

        result = candidates_gdf.copy()
        result["ae_score"] = scores
        result["ae_is_afo"] = [s >= threshold for s in scores]
        result["ae_filtered"] = [s < threshold for s in scores]

        n_kept = sum(result["ae_is_afo"])
        n_filtered = sum(result["ae_filtered"])
        logger.info(
            "AlphaEarth classification: %d kept, %d filtered (threshold=%.2f)",
            n_kept, n_filtered, threshold,
        )

        return result

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
