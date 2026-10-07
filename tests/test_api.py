"""
Pytest test suite for the Geospatial File Measurement API.

Tests cover:
  - Service-layer helpers (_safe_float, _reproject_for_measurement, etc.)
  - API endpoints via FastAPI TestClient (no live server required)
  - File upload validation (bad extension, missing file)
  - 404 for unknown file IDs
  - Full upload-and-poll happy path using the bundled sample KML
"""

import io
import os
import time

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Import the app and the service helpers directly so both layers are tested.
# ---------------------------------------------------------------------------
from app.main import app
from app.service import _safe_float, _reproject_for_measurement, files_db
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString

client = TestClient(app)

SAMPLE_KML = os.path.join(os.path.dirname(__file__), "..", "sample.kml")
SAMPLE_ZIP = os.path.join(os.path.dirname(__file__), "..", "ne_110m_admin_0_countries.zip")


# ===========================================================================
# Service-layer unit tests
# ===========================================================================

class TestSafeFloat:
    def test_normal_value(self):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_nan_returns_zero(self):
        assert _safe_float(float("nan")) == 0.0

    def test_inf_returns_zero(self):
        assert _safe_float(float("inf")) == 0.0

    def test_string_number(self):
        assert _safe_float("42.5") == pytest.approx(42.5)

    def test_non_numeric_string(self):
        assert _safe_float("not-a-number") == 0.0

    def test_none(self):
        assert _safe_float(None) == 0.0


class TestReprojectForMeasurement:
    def test_geographic_crs_is_reprojected(self):
        """A GDF in WGS-84 should come back in a projected (metric) CRS."""
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(77.0, 28.0)]},
            crs="EPSG:4326",
        )
        result = _reproject_for_measurement(gdf)
        assert not result.crs.is_geographic, "Expected a projected (metric) CRS"

    def test_already_projected_crs_unchanged(self):
        """A GDF already in a projected CRS must not be transformed."""
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(500_000, 3_100_000)]},
            crs="EPSG:32643",
        )
        result = _reproject_for_measurement(gdf)
        assert result.crs == gdf.crs

    def test_no_crs_defaults_to_4326_then_reprojects(self):
        """A CRS-less GDF should get EPSG:4326 assigned and then reprojected."""
        gdf = gpd.GeoDataFrame({"geometry": [Point(77.0, 28.0)]})
        result = _reproject_for_measurement(gdf)
        assert not result.crs.is_geographic


# ===========================================================================
# API endpoint tests
# ===========================================================================

class TestUploadValidation:
    def test_missing_file_rejected(self):
        resp = client.post("/api/files/")
        assert resp.status_code == 422  # Unprocessable Entity (no file field)

    def test_unsupported_extension_rejected(self):
        resp = client.post(
            "/api/files/",
            files={"file": ("data.csv", io.BytesIO(b"a,b,c"), "text/csv")},
        )
        assert resp.status_code == 422
        assert "Unsupported" in resp.json()["detail"]

    def test_valid_zip_accepted(self):
        """A minimal (invalid) zip still gets a 202 PROCESSING response."""
        resp = client.post(
            "/api/files/",
            files={"file": ("test.zip", io.BytesIO(b"PK"), "application/zip")},
        )
        # The upload itself succeeds; processing will fail in background.
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "PROCESSING"
        assert "id" in body


class TestFileInfo:
    def test_unknown_id_returns_404(self):
        resp = client.get("/api/files/does-not-exist/")
        assert resp.status_code == 404

    def test_unknown_measurements_returns_404(self):
        resp = client.get("/api/files/does-not-exist/measurements/")
        assert resp.status_code == 404


class TestKmlHappyPath:
    """End-to-end test using the sample.kml bundled with the project."""

    @pytest.fixture(autouse=True)
    def skip_if_no_kml(self):
        if not os.path.exists(SAMPLE_KML):
            pytest.skip("sample.kml not present — skipping integration test")

    def test_upload_and_complete(self):
        with open(SAMPLE_KML, "rb") as f:
            resp = client.post(
                "/api/files/",
                files={"file": ("sample.kml", f, "application/vnd.google-earth.kml+xml")},
            )

        assert resp.status_code == 202
        file_id = resp.json()["id"]

        # Poll until COMPLETED or FAILED (max ~5 s for a tiny KML)
        status = "PROCESSING"
        for _ in range(20):
            info = client.get(f"/api/files/{file_id}/").json()
            status = info["status"]
            if status != "PROCESSING":
                break
            time.sleep(0.25)

        assert status == "COMPLETED", f"Processing did not complete; error: {info.get('error')}"
        assert info["feature_count"] > 0

    def test_measurements_endpoint(self):
        """Upload KML, wait, then verify measurements structure."""
        with open(SAMPLE_KML, "rb") as f:
            resp = client.post(
                "/api/files/",
                files={"file": ("sample.kml", f, "application/vnd.google-earth.kml+xml")},
            )

        file_id = resp.json()["id"]

        for _ in range(20):
            info = client.get(f"/api/files/{file_id}/").json()
            if info["status"] != "PROCESSING":
                break
            time.sleep(0.25)

        meas = client.get(f"/api/files/{file_id}/measurements/").json()
        assert "features" in meas
        for feature in meas["features"]:
            assert "geometry_type" in feature
            assert "measurement" in feature
            assert feature["measurement"]["type"] in (
                "Area", "Length", "None", "Unsupported"
            )
