import os
import uuid
import shutil
import zipfile
import tempfile
import json
import math
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import geopandas as gpd
import fiona

# Enable KML driver for Fiona/Geopandas
fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['libkml'] = 'rw'

app = FastAPI(title="Geospatial File Measurement API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for file processing status and data
files_db: Dict[str, Dict[str, Any]] = {}

def process_file_task(file_id: str, file_path: str, original_filename: str, extension: str):
    """
    Background task to process geospatial files, extract features, and calculate measurements.
    """
    try:
        gdf = None
        extract_dir = None
        
        # 1. Read Geodataframe
        if extension == ".zip":
            extract_dir = os.path.join(tempfile.gettempdir(), file_id)
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find the .shp file
            shp_files = [os.path.join(dp, f) for dp, dn, fnames in os.walk(extract_dir) for f in fnames if f.lower().endswith('.shp')]
            if not shp_files:
                raise Exception("No .shp file found in the uploaded zip.")
            
            gdf = gpd.read_file(shp_files[0])
        elif extension == ".kml":
            try:
                gdf = gpd.read_file(file_path, driver='KML')
            except Exception:
                gdf = gpd.read_file(file_path, driver='libkml')
        else:
            raise Exception("Unsupported file type")

        if gdf is None or gdf.empty:
            raise Exception("File is empty or could not be parsed.")

        # 2. CRS Handling & Reprojection
        # Original CRS name
        crs_name = str(gdf.crs) if gdf.crs else "Unknown (assuming EPSG:4326)"
        if not gdf.crs:
            # Set default if none provided
            gdf.set_crs(epsg=4326, inplace=True)
            
        gdf_projected = gdf.copy()
        
        # We need a projected CRS to calculate area/length accurately in meters.
        # If it's geographic (like WGS84: EPSG 4326), we estimate UTM based on its bounds.
        if gdf_projected.crs.is_geographic:
            try:
                utm_crs = gdf_projected.estimate_utm_crs()
                if utm_crs:
                    gdf_projected = gdf_projected.to_crs(utm_crs)
            except Exception as e:
                print(f"Failed to estimate UTM CRS, falling back to Web Mercator: {e}")
                gdf_projected = gdf_projected.to_crs(epsg=3857)
                
        # 3. Extract Features and Measurements
        features_data = []
        for index, row in gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
                
            geom_type = geom.geom_type
            
            # Calculate measurement based on the projected geometry
            def safe_val(v):
                try:
                    if math.isnan(v) or math.isinf(v):
                        return 0.0
                    return float(v)
                except:
                    return 0.0

            measurement = {}
            if geom_type in ['Polygon', 'MultiPolygon']:
                area = safe_val(gdf_projected.iloc[index].geometry.area)
                measurement = {"type": "Area", "value": area, "unit": "sq meters"}
            elif geom_type in ['LineString', 'MultiLineString']:
                length = safe_val(gdf_projected.iloc[index].geometry.length)
                measurement = {"type": "Length", "value": length, "unit": "meters"}
            elif geom_type in ['Point', 'MultiPoint']:
                measurement = {"type": "None", "value": 0, "message": "No measurement required for Point"}
            else:
                measurement = {"type": "Unsupported", "value": 0, "message": f"{geom_type} measurement not supported"}
            
            # Convert properties safely
            properties = {}
            for col in gdf.columns:
                if col != 'geometry':
                    val = row[col]
                    properties[col] = str(val) if val is not None else None
            
            # Get GeoJSON geometry dict, dropping the feature collection wrapper
            geojson_str = gpd.GeoSeries([geom]).to_json()
            geom_dict = json.loads(geojson_str)['features'][0]['geometry']
            
            features_data.append({
                "feature_id": str(index),
                "geometry_type": geom_type,
                "geometry": geom_dict, # original unprojected geometry for the API response
                "crs": crs_name,
                "properties": properties,
                "measurement": measurement
            })
        
        # 4. Success state
        files_db[file_id]['status'] = 'COMPLETED'
        files_db[file_id]['feature_count'] = len(features_data)
        files_db[file_id]['crs'] = crs_name
        files_db[file_id]['features'] = features_data
        
    except Exception as e:
        files_db[file_id]['status'] = 'FAILED'
        files_db[file_id]['error'] = str(e)
    finally:
        # Cleanup temp resources
        if os.path.exists(file_path):
            os.remove(file_path)
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)

@app.post("/api/files/")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload a geospatial file (.zip Shapefile or .kml) for processing.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in [".zip", ".kml"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload .zip or .kml")
    
    file_id = str(uuid.uuid4())
    temp_filepath = os.path.join(tempfile.gettempdir(), f"{file_id}{ext}")
    
    try:
        with open(temp_filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    finally:
        file.file.close()
        
    # Initialize DB entry
    files_db[file_id] = {
        "id": file_id,
        "filename": file.filename,
        "status": "PROCESSING",
        "feature_count": 0,
        "crs": None,
        "features": []
    }
    
    # Process asynchronously
    background_tasks.add_task(process_file_task, file_id, temp_filepath, file.filename, ext)
    
    return {"message": "File uploaded successfully", "id": file_id, "status": "PROCESSING"}

@app.get("/api/files/{file_id}/")
async def get_file_info(file_id: str):
    """
    Returns information about the uploaded file.
    """
    if file_id not in files_db:
        raise HTTPException(status_code=404, detail="File not found")
        
    data = files_db[file_id]
    return {
        "id": data.get("id"),
        "filename": data.get("filename"),
        "feature_count": data.get("feature_count"),
        "crs": data.get("crs"),
        "status": data.get("status"),
        "error": data.get("error", None)
    }

@app.get("/api/files/{file_id}/measurements/")
async def get_file_measurements(file_id: str):
    """
    Returns measurements and feature data for the processed file.
    """
    if file_id not in files_db:
        raise HTTPException(status_code=404, detail="File not found")
        
    data = files_db[file_id]
    if data["status"] != "COMPLETED":
        return {"status": data["status"], "message": "File is not yet fully processed or failed", "error": data.get("error")}
        
    return {
        "id": data["id"],
        "features": data["features"]
    }

# Mount static files for the frontend at the root
app.mount("/", StaticFiles(directory="static", html=True), name="static")
