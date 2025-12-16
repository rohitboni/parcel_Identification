"""
Transform module for ETL pipeline.

Handles field mapping, transformations, and geometry processing.
Uses low-level geometry functions from geometry_utils.py.
"""

import geopandas as gpd
import pandas as pd
import logging
from .geometry_utils import clean_geometry, compute_label_point, simplify_geometry, ensure_crs

logger = logging.getLogger(__name__)


def map_fields(gdf, field_mapping):
    """
    Map source columns to target column names.
    
    Args:
        gdf: Source GeoDataFrame
        field_mapping: Dictionary mapping source_column -> target_column
        
    Returns:
        GeoDataFrame with renamed columns
    """
    # Create rename dictionary (only for columns that exist)
    rename_dict = {
        src: tgt 
        for src, tgt in field_mapping.items() 
        if src in gdf.columns
    }
    
    gdf = gdf.rename(columns=rename_dict)
    
    return gdf


def apply_transforms(gdf, transform_config):
    """
    Apply transformations to create new columns.
    
    Args:
        gdf: GeoDataFrame
        transform_config: Dictionary of transform definitions
            Example: {
                'state_code': {
                    'source': 'FID_Tamiln',
                    'transform': 'string'
                }
            }
        
    Returns:
        GeoDataFrame with transformed columns added
    """
    for target_col, transform_def in transform_config.items():
        source_col = transform_def.get('source')
        transform_type = transform_def.get('transform', 'string')
        
        if transform_type == 'constant':
            # Set constant value (no source column needed)
            constant_value = transform_def.get('value', '')
            gdf[target_col] = str(constant_value)
        elif source_col is None or source_col not in gdf.columns:
            # Skip if source column doesn't exist (unless it's a constant)
            continue
        elif transform_type == 'string':
            # Convert to string
            gdf[target_col] = gdf[source_col].astype(str)
        elif transform_type == 'uppercase':
            # Convert to uppercase string
            gdf[target_col] = gdf[source_col].astype(str).str.upper()
        elif transform_type == 'lowercase':
            # Convert to lowercase string
            gdf[target_col] = gdf[source_col].astype(str).str.lower()
        else:
            # Default: just copy as string
            gdf[target_col] = gdf[source_col].astype(str)
    
    return gdf


def clean_geometries(gdf, geometry_column='geometry'):
    """
    Clean all geometries in the GeoDataFrame.
    
    This is a high-level wrapper that applies geometry_utils.clean_geometry()
    to each geometry in the GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        geometry_column: Name of geometry column
        
    Returns:
        GeoDataFrame with cleaned geometries, invalid geometries filtered out
    """
    # Clean geometries using geometry_utils.clean_geometry() for each row
    gdf['clean_geom'] = gdf[geometry_column].apply(clean_geometry)
    
    # Filter out null geometries
    gdf = gdf[~gdf['clean_geom'].isnull()].copy()
    
    # Replace geometry column with cleaned version
    # Get the current geometry column name
    old_geo_col = gdf._geometry_column_name
    
    # Set clean_geom as the new geometry column (using recommended approach to avoid FutureWarning)
    gdf = gdf.set_geometry('clean_geom')
    
    # Drop the old geometry column if it exists and is different from clean_geom
    if old_geo_col != 'clean_geom' and old_geo_col in gdf.columns:
        gdf = gdf.drop(columns=[old_geo_col])
    
    # If target name is different from current geometry name, rename it
    # But first check if target name exists as a regular column and drop it
    if geometry_column in gdf.columns and geometry_column != gdf._geometry_column_name:
        gdf = gdf.drop(columns=[geometry_column])
    
    # Now rename the geometry column to target name
    if gdf._geometry_column_name != geometry_column:
        gdf = gdf.rename_geometry(geometry_column)
    
    return gdf


def compute_label_points(gdf, geometry_column='geometry'):
    """
    Compute label points for all geometries.
    
    This is a high-level wrapper that applies geometry_utils.compute_label_point()
    to each geometry in the GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        geometry_column: Name of geometry column
        
    Returns:
        GeoDataFrame with 'label_point' column added
    """
    # Compute label points using geometry_utils.compute_label_point() for each row
    gdf['label_point'] = gdf[geometry_column].apply(compute_label_point)
    
    return gdf


def simplify_geometries(gdf, tolerance=0.00008, geometry_column='geometry'):
    """
    Simplify geometries for faster rendering.
    
    This is a high-level wrapper that applies geometry_utils.simplify_geometry()
    to each geometry in the GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        tolerance: Simplification tolerance in degrees
        geometry_column: Name of geometry column
        
    Returns:
        GeoDataFrame with simplified geometries in 'geom_simplified' column
    """
    # Simplify geometries using geometry_utils.simplify_geometry() for each row
    gdf['geom_simplified'] = gdf[geometry_column].apply(
        lambda g: simplify_geometry(g, tolerance)
    )
    
    return gdf


def prepare_for_master_table(gdf, config):
    """
    Prepare GeoDataFrame for parcels_master table.
    
    This includes:
    - Field mapping
    - Transformations
    - Geometry cleaning
    - Label point computation
    - CRS normalization
    - Filter out rows with null required fields
    
    Args:
        gdf: Source GeoDataFrame
        config: Configuration dictionary from YAML
        
    Returns:
        GeoDataFrame ready for parcels_master insertion
    """
    # Ensure correct CRS
    target_crs = config.get('geometry', {}).get('target_crs', 'EPSG:4326')
    gdf = ensure_crs(gdf, target_crs)
    
    # Map fields
    field_mapping = config.get('field_mapping', {})
    gdf = map_fields(gdf, field_mapping)
    
    # Apply transformations
    transform_config = config.get('transforms', {})
    gdf = apply_transforms(gdf, transform_config)
    
    # Clean geometries
    gdf = clean_geometries(gdf)
    
    # Compute label points
    if config.get('geometry', {}).get('compute_label_point', False):
        gdf = compute_label_points(gdf)
    
    # Filter out rows with null values in required fields
    required_fields = config.get('required_fields', [])
    for field in required_fields:
        if field in gdf.columns:
            null_count = gdf[field].isnull().sum()
            if null_count > 0:
                logger.warning(f"Filtering out {null_count} rows with null {field}")
                gdf = gdf[~gdf[field].isnull()].copy()

    # Rename geometry column to 'geom' for database
    gdf = gdf.rename_geometry('geom')
    
    return gdf


def prepare_for_simplified_table(gdf_master, config):
    """
    Prepare GeoDataFrame for parcels_simplified table.
    
    This takes the master table data and:
    - Copies the original geometry (NO simplification - using original geom as-is)
    - Copies label points from master (no recomputation needed)
    
    Note: We're NOT simplifying geometries. The simplified table contains
    the same original geometry as the master table. This table is used
    for tile generation, and we want to preserve the original geometry precision.
    
    Args:
        gdf_master: GeoDataFrame from master table preparation
        config: Configuration dictionary
        
    Returns:
        GeoDataFrame ready for parcels_simplified insertion
    """
    # Copy the master data - we're NOT simplifying, just using original geometry
    # Select only the columns needed for simplified table
    required_cols = ['state_code', 'district_code', 'survey_num']
    
    # Filter to only columns that exist
    available_cols = [col for col in required_cols if col in gdf_master.columns]
    
    # Include label_point if it exists (copy from master, no recomputation)
    if 'label_point' in gdf_master.columns:
        available_cols.append('label_point')
    
    # IMPORTANT: Preserve the geometry explicitly
    # Get the geometry series before selecting columns
    geometry_series = gdf_master['geom'].copy()
    
    # Select data columns (this creates a regular DataFrame, losing geometry)
    selected_data = gdf_master[available_cols].copy()
    
    # Create new GeoDataFrame with selected columns and preserved original geometry
    gdf = gpd.GeoDataFrame(selected_data, geometry=geometry_series, crs=gdf_master.crs)
    
    # Ensure geometry column is named 'geom' for consistency
    if gdf._geometry_column_name != 'geom':
        gdf = gdf.rename_geometry('geom')
    
    return gdf

