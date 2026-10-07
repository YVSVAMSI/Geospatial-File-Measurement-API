"""
Geospatial processing service.

Handles file reading (Shapefile zip / KML), CRS reprojection, and
measurement extraction.  Intentionally kept framework-agnostic so it
can be unit-tested without starting a FastAPI server.
"""

import json
import math
import os
import shutil
import tempfile
import zipfile
from typing import Dict, Any, List

import fiona
import geopandas as gpd

# Enable KML driver globally when this module is imported.
fiona.drvsupport.supported_drivers["KML"] = "rw"
fiona.drvsupport.supported_drivers["libkml"] = "rw"


# ---------------------------------------------------------------------------
# In-memory store  (dict[file_id -> dict])
# ---------------------------------------------------------------------------

files_db: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float:
    """Return *value* as float, or 0.0 for NaN / Inf / non-numeric."""
    try:
        f = float(value)
        return 0.0 if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return 0.0


def _read_geodataframe(file_path: str, extension: str, file_id: str):
    """
    Load a GeoDataFrame from *file_path*.

    Supported extensions:
      - ``.zip`` — zipped Shapefile
      - ``.kml`` — Keyhole Markup Language
    """
    if extension == ".zip":
        extract_dir = os.path.join(tempfile.gettempdir(), file_id)
        with zipfile.ZipFile(file_path, "r") as zf:
            zf.extractall(extract_dir)

        shp_files = [
            os.path.join(dp, f)
            for dp, _, fnames in os.walk(extract_dir)
            for f in fnames
            if f.lower().endswith(".shp")
        ]
        if not shp_files:
            shutil.rmtree(extract_dir, ignore_errors=True)
            raise ValueError("No .shp file found in the uploaded zip.")

        gdf = gpd.read_file(shp_files[0])
        shutil.rmtree(extract_dir, ignore_errors=True)
        return gdf

    if extension == ".kml":
        try:
            return gpd.read_file(file_path, driver="KML")
        except Exception:
            return gpd.read_file(file_path, driver="libkml")

    raise ValueError(f"Unsupported file extension: {extension}")


def _reproject_for_measurement(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Return a copy of *gdf* projected to a metric CRS suitable for
    area / length calculations.

    Priority:
      1. Auto-estimated UTM zone (best accuracy)
      2. Web Mercator EPSG:3857 (fallback)
    """
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)

    if not gdf.crs.is_geographic:
        return gdf.copy()

    try:
        utm = gdf.estimate_utm_crs()
        if utm:
            return gdf.to_crs(utm)
    except Exception:
        pass

    return gdf.to_crs(epsg=3857)


def _extract_features(gdf: gpd.GeoDataFrame, gdf_projected: gpd.GeoDataFrame, crs_name: str) -> List[Dict[str, Any]]:
    """Build the list of feature dicts from paired original / projected GDFs."""
    features: List[Dict[str, Any]] = []

    for index, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue

        geom_type = geom.geom_type
        proj_geom = gdf_projected.iloc[index].geometry  # type: ignore[call-overload]

        # Measurement
        if geom_type in ("Polygon", "MultiPolygon"):
            measurement = {
                "type": "Area",
                "value": _safe_float(proj_geom.area),
                "unit": "sq meters",
            }
        elif geom_type in ("LineString", "MultiLineString"):
            measurement = {
                "type": "Length",
                "value": _safe_float(proj_geom.length),
                "unit": "meters",
            }
        elif geom_type in ("Point", "MultiPoint"):
            measurement = {
                "type": "None",
                "value": 0,
                "message": "No measurement required for Point",
            }
        else:
            measurement = {
                "type": "Unsupported",
                "value": 0,
                "message": f"{geom_type} measurement not supported",
            }

        # Properties (stringify everything for consistent serialisation)
        properties = {
            col: (str(row[col]) if row[col] is not None else None)
            for col in gdf.columns
            if col != "geometry"
        }

        # Original (unprojected) geometry as GeoJSON dict
        geom_dict = json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]

        features.append(
            {
                "feature_id": str(index),
                "geometry_type": geom_type,
                "geometry": geom_dict,
                "crs": crs_name,
                "properties": properties,
                "measurement": measurement,
            }
        )

    return features


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_file_task(file_id: str, file_path: str, original_filename: str, extension: str) -> None:
    """
    Background task: parse *file_path*, compute measurements, and store
    results (or an error) in ``files_db[file_id]``.

    Called via FastAPI ``BackgroundTasks`` — must not raise.
    """
    try:
        gdf = _read_geodataframe(file_path, extension, file_id)

        if gdf is None or gdf.empty:
            raise ValueError("File is empty or could not be parsed.")

        # Preserve the original CRS label for display purposes.
        crs_name = str(gdf.crs) if gdf.crs else "Unknown (assuming EPSG:4326)"

        gdf_projected = _reproject_for_measurement(gdf)
        features = _extract_features(gdf, gdf_projected, crs_name)

        files_db[file_id]["status"] = "COMPLETED"
        files_db[file_id]["feature_count"] = len(features)
        files_db[file_id]["crs"] = crs_name
        files_db[file_id]["features"] = features

    except Exception as exc:
        files_db[file_id]["status"] = "FAILED"
        files_db[file_id]["error"] = str(exc)

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
