"""
Application entry point.

Run with:
    uvicorn app.main:app --reload
or via Docker:
    docker run -p 8000:8000 geospatial-api
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes import router

app = FastAPI(
    title="Geospatial File Measurement API",
    description="Upload .zip Shapefiles or .kml files and receive per-feature area / length measurements.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve the frontend SPA — must come AFTER the API router.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
