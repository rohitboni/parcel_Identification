"""
Extract module for ETL pipeline.

Handles data extraction from shapefiles/GeoPackages and initial inspection.
"""

import geopandas as gpd
import pandas as pd
from pathlib import Path


def load_data(source_path):
    """
    Load spatial data from shapefile or GeoPackage.
    
    Args:
        source_path: Path to shapefile (.shp) or GeoPackage (.gpkg)
        
    Returns:
        GeoDataFrame with loaded data
        
    Raises:
        FileNotFoundError: If source file doesn't exist
        ValueError: If file format is not supported
    """
    source_path = Path(source_path)
    
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    
    # Load with GeoPandas
    gdf = gpd.read_file(str(source_path))
    
    return gdf


def inspect_schema(gdf):
    """
    Inspect schema of GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        
    Returns:
        Dictionary with schema information:
        - columns: List of column names
        - dtypes: Dictionary of column names to data types
        - geometry_column: Name of geometry column
        - crs: Coordinate reference system
        - row_count: Number of rows
    """
    return {
        "columns": list(gdf.columns),
        "dtypes": gdf.dtypes.to_dict(),
        "geometry_column": gdf.geometry.name,
        "crs": str(gdf.crs) if gdf.crs else None,
        "row_count": len(gdf)
    }


def sample_data(gdf, n=5):
    """
    Get sample rows from GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        n: Number of sample rows
        
    Returns:
        GeoDataFrame with first n rows
    """
    return gdf.head(n)


def validate_source_columns(gdf, required_fields):
    """
    Validate that required source columns exist in the GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        required_fields: List of required field names
        
    Returns:
        Tuple (is_valid, missing_fields)
        - is_valid: Boolean indicating if all fields exist
        - missing_fields: List of missing field names
    """
    existing_columns = set(gdf.columns)
    required_set = set(required_fields)
    missing = required_set - existing_columns
    
    return (len(missing) == 0, list(missing))

