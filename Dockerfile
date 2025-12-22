FROM python:3.11-slim

# Install system dependencies for geospatial libraries
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    binutils \
    postgresql-client \
    python3-gdal \
    g++ \
    build-essential \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for GDAL/GEOS
ENV GDAL_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgdal.so
ENV GEOS_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgeos_c.so

WORKDIR /app

# Set PYTHONPATH to include backend directory for imports
ENV PYTHONPATH=/app/backend:/app:$PYTHONPATH

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create symlink for system GDAL Python bindings
RUN ln -s /usr/lib/python3/dist-packages/osgeo /usr/local/lib/python3.11/site-packages/osgeo || true

# Copy application code
COPY . .

# Create cache directory
RUN mkdir -p /app/cache

# Expose ports (will be overridden by docker-compose)
EXPOSE 8000 8001 8002 8003

# Default command (will be overridden by docker-compose)
CMD ["uvicorn", "backend.services.api_gateway:app", "--host", "0.0.0.0", "--port", "8000"]
