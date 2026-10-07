# Geospatial File Measurement API

A production-ready FastAPI backend service designed to process, extract, and accurately measure geometries from uploaded Geospatial files (.zip Shapefiles and .kml). The project includes a high-end, dynamic Web UI for zero-touch interaction.

## Features
- **File Upload Engine**: Handles multi-part raw uploads for both Shapefiles (.zip format) and .kml directly via standard HTTP.
- **Dynamic Coordinate Projection**: Automatically estimates and re-projects generic EPSG:4326/WGS84 geometries into UTM coordinate systems dynamically prior to measuring to guarantee physical dimension accuracy natively.
- **Robust Feature Processing**: Uses powerful Geopandas/Shapely integrations.
- **State-of-the-Art UI**: Features a bespoke, dark-mode glassmorphic front-end that polls async task status securely without locking the browser.

## Minimum Requirements
- Python 3.9+
- Pip (Python Package Manager)

## Setup and Run Locally

### 1. Initialize Application
Clone or place the directory where preferred, then spawn a virtual environment:

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Launch the API & Web App
```bash
uvicorn main:app --reload
```
Once the server starts running, open a browser and go to your localhost:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

## API Documentation

### 1. Upload File
- **Method**: `POST`
- **URL**: `/api/files/`
- **Body**: Form-data with key `file` containing the `.zip` or `.kml`.
- **Response**:
```json
{
  "message": "File uploaded successfully",
  "id": "cd0b64d3-1250...",
  "status": "PROCESSING"
}
```

### 2. Check File Information
- **Method**: `GET`
- **URL**: `/api/files/{id}/`
- **Response**:
```json
{
  "id": "cd0b64d3...",
  "filename": "survey.zip",
  "feature_count": 12,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

### 3. Fetch Measurements
- **Method**: `GET`
- **URL**: `/api/files/{id}/measurements/`
- **Response**:
```json
{
  "id": "cd0b64d3...",
  "features": [
    {
      "feature_id": "0",
      "geometry_type": "Polygon",
      "geometry": { "type": "Polygon", "coordinates": [...] },
      "crs": "EPSG:4326",
      "properties": { "Name": "Tract A", "Value": "100" },
      "measurement": {
        "type": "Area",
        "value": 154032.55,
        "unit": "sq meters"
      }
    }
  ]
}
```

## Architecture
- **Application Structure**:
  - `main.py`: The single-entry FastAPI file containing configurations, file handlers, async processing background logic, and endpoints.
  - `static/`: Contains the frontend shell (`index.html`, `styles.css`, `app.js`) instantly served via FastAPI's `StaticFiles`.
- **File-Processing Flow**:
  1. The API ingests a file using `UploadFile` and writes it locally to a temporary OS-agnostic `/tmp` path concurrently. 
  2. A FastAPI `BackgroundTasks` executes `process_file_task` without holding API execution.
  3. The task extracts zips or parses KMLs directly into a Geodataframe using `geopandas` and `fiona`.
- **Measurement & CRS Handling Flow**:
  1. For geometries relying strictly on `EPSG:4326` (which causes `measurement.area` distortion in degrees), the engine verifies `.is_geographic`.
  2. If geographic, it invokes `.estimate_utm_crs()` against bounding coordinates.
  3. The geometry frame is `.to_crs(utm)` ensuring flat representation, computing real-world lengths and areas natively in square meters/meters.

## Design Decisions
1. **Background Tasks Engine**: Rather than implementing complex Celery+Redis integrations for what might only be a 5-6 second file process, FastAPI `BackgroundTasks` was used for high-efficiency, zero-overhead background job passing.
2. **KML Parsing**: KML natively possesses quirks. `Fiona` has been injected with `.supported_drivers['KML']='rw'` during API initialization. We trap parsing attempts globally backing onto `libkml` to guardrail failure states natively.
3. **Frontend decoupling**: The Web UI uses vanilla JS and pure modular CSS—avoiding weighty frameworks like React or Tailwind for an ultra-fast, premium standalone deliverable.

## Learning and Future Scope
- **Scalability**: While the mock `files_db` Python dictionary works magically here, deploying this live requires a permanent metadata store (e.g., PostgreSQL + PostGIS) caching the JSON/B features to avoid MemoryError crashes during extremely massive Shapefile uploads.
- **Worker Scaling**: True heavy GIS files require decoupling BackgroundTasks into a RabbitMQ queue consuming worker nodes across a Kubernetes cluster.
- **UI Enhancements**: Implementing a real-world map (e.g. Mapbox GL or Leaflet) inside the interface mapping the geometries dynamically onto a visual vector canvas!
