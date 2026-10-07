# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install system-level GDAL/GEOS/PROJ dependencies required by geopandas & fiona.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
        gdal-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer-cached unless requirements.txt changes).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source.
COPY app/       ./app/
COPY static/    ./static/

EXPOSE 8000

# Run with a single command — no shell gymnastics required.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
