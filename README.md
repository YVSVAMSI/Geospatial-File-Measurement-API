# Geospatial File Measurement API

A FastAPI backend service that processes uploaded geospatial files (`.zip` Shapefiles and `.kml`), automatically re-projects geometries to an appropriate metric CRS, and returns per-feature area/length measurements. Ships with a dark-mode glassmorphic Web UI and a Leaflet map.

## Features

- **File Upload** — multipart upload for `.zip` Shapefiles and `.kml` files via standard HTTP
- **Dynamic CRS Reprojection** — auto-estimates the correct UTM zone from bounding coordinates; falls back to Web Mercator when estimation fails, ensuring physically accurate measurements in metres / sq metres
- **Async Processing** — FastAPI `BackgroundTasks` keeps the upload response instant while heavy GIS work runs in the background
- **Measurement Extraction** — area for polygons, length for linestrings, labelled "None" for points
- **Interactive Web UI** — polling status bar, sortable feature table, Leaflet map with geometry overlay
- **Automated Tests** — pytest suite with service-layer unit tests and HTTP integration tests via FastAPI `TestClient`
- **Docker support** — single `docker run` command; no local Python setup needed

## Project Structure

```
.
├── app/
│   ├── main.py      # FastAPI app factory, middleware, router mount
│   ├── routes.py    # API route handlers (/api/files/…)
│   ├── service.py   # Geospatial processing logic & in-memory store
│   └── models.py    # Pydantic request/response schemas
├── tests/
│   └── test_api.py  # pytest — unit tests + integration tests (TestClient)
├── static/          # Vanilla JS/CSS frontend (index.html, app.js, styles.css)
├── Dockerfile
├── requirements.txt
└── README.md
```

## Quick Start

### Option A — Docker (recommended)

```bash
docker build -t geospatial-api .
docker run -p 8000:8000 geospatial-api
```

Open [http://localhost:8000](http://localhost:8000).

### Option B — Local Python

```bash
# Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Running Tests

```bash
pytest tests/ -v
```

The suite runs without a live server — FastAPI `TestClient` handles everything.

## API Reference

### Upload a file

```
POST /api/files/
Content-Type: multipart/form-data
Body: file=<.zip|.kml>
```

**Response `202`**
```json
{ "message": "File uploaded successfully", "id": "cd0b64d3-…", "status": "PROCESSING" }
```

### Poll file status

```
GET /api/files/{id}/
```

```json
{ "id": "cd0b64d3-…", "filename": "survey.zip", "feature_count": 12, "crs": "EPSG:32643", "status": "COMPLETED" }
```

### Fetch measurements

```
GET /api/files/{id}/measurements/
```

```json
{
  "id": "cd0b64d3-…",
  "features": [
    {
      "feature_id": "0",
      "geometry_type": "Polygon",
      "geometry": { "type": "Polygon", "coordinates": […] },
      "crs": "EPSG:4326",
      "properties": { "Name": "Tract A" },
      "measurement": { "type": "Area", "value": 154032.55, "unit": "sq meters" }
    }
  ]
}
```

Interactive docs at [http://localhost:8000/docs](http://localhost:8000/docs).

## Architecture Notes

| Concern | Decision |
|---|---|
| Background processing | FastAPI `BackgroundTasks` — zero external deps for a sub-10 s job |
| CRS handling | `gdf.estimate_utm_crs()` → UTM; fallback to EPSG:3857 |
| KML parsing | Fiona with `KML` driver; fallback to `libkml` |
| Storage | In-memory `dict` — sufficient for a demo; swap for PostgreSQL/PostGIS in production |
| Frontend | Vanilla JS + CSS — no framework overhead; Leaflet for geometry rendering |

## Future Work

- Persistent metadata store (PostgreSQL + PostGIS) to survive restarts and handle large files
- Celery + Redis worker queue for heavy-file processing at scale
- Mapbox GL / Leaflet layer controls for richer geometry interaction
