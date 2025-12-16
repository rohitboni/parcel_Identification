"""
Geometry utility functions for ETL pipeline.

Handles geometry cleaning, normalization, simplification, and label point computation.

These are LOW-LEVEL functions that work on single Shapely geometry objects.
For GeoDataFrame operations, see transform.py which wraps these functions.

Architecture:
- geometry_utils.py: Pure geometry operations (single geometries)
- transform.py: ETL-specific transformations (GeoDataFrames, uses geometry_utils)
"""

from shapely.geometry import MultiPolygon, Point
from shapely.ops import transform as shapely_transform
import geopandas as gpd


def clean_geometry(geom):
    """
    Clean and normalize geometry.
    
    - Fixes invalid geometries using buffer(0)
    - Converts Polygon to MultiPolygon for consistency
    - Returns None for null/invalid geometries
    
    Args:
        geom: Shapely geometry object
        
    Returns:
        Cleaned MultiPolygon or None
    """
    if geom is None:
        return None
    
    try:
        # Fix invalid geometries
        if not geom.is_valid:
            geom = geom.buffer(0)
        
        # Normalize Polygon to MultiPolygon
        if geom.geom_type == "Polygon":
            return MultiPolygon([geom])
        
        return geom
    except Exception:
        return None


def compute_label_point(geom):
    """
    Compute a point on the surface of a geometry for label placement.
    
    Uses Shapely's point_on_surface (equivalent to PostGIS ST_PointOnSurface).
    This ensures the point is always inside the polygon.
    
    Args:
        geom: Shapely geometry (Polygon or MultiPolygon)
        
    Returns:
        Point geometry or None
    """
    if geom is None:
        return None
    
    try:
        from shapely.constructive import point_on_surface
        label_point = point_on_surface(geom)
        
        # Ensure it's a Point (point_on_surface should return Point, but verify)
        if label_point.geom_type == "Point" and not label_point.is_empty:
            return label_point
        return None
    except Exception:
        return None


def simplify_geometry(geom, tolerance=0.00008, preserve_topology=True):
    """
    Simplify geometry using Douglas-Peucker algorithm.
    
    Args:
        geom: Shapely geometry
        tolerance: Simplification tolerance in degrees
        preserve_topology: Whether to preserve topology
        
    Returns:
        Simplified geometry or None
    """
    if geom is None:
        return None
    
    try:
        return geom.simplify(tolerance, preserve_topology=preserve_topology)
    except Exception:
        return None


def ensure_crs(gdf, target_crs="EPSG:4326"):
    """
    Ensure GeoDataFrame is in the target CRS.
    
    Args:
        gdf: GeoDataFrame
        target_crs: Target coordinate reference system
        
    Returns:
        GeoDataFrame in target CRS
    """
    if gdf.crs is None:
        gdf.set_crs(target_crs, inplace=True)
    elif gdf.crs != target_crs:
        gdf = gdf.to_crs(target_crs)
    
    return gdf

