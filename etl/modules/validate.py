"""
Validate module for ETL pipeline.

Handles data quality validation and schema checks.
"""

import geopandas as gpd
import pandas as pd


def validate_schema(gdf, expected_columns):
    """
    Validate that GeoDataFrame has expected columns.
    
    Args:
        gdf: GeoDataFrame
        expected_columns: List of expected column names
        
    Returns:
        Tuple (is_valid, missing_columns, extra_columns)
    """
    existing_columns = set(gdf.columns)
    expected_set = set(expected_columns)
    
    missing = expected_set - existing_columns
    extra = existing_columns - expected_set
    
    return (len(missing) == 0, list(missing), list(extra))


def validate_geometries(gdf, geometry_column='geometry'):
    """
    Validate geometries in GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        geometry_column: Name of geometry column
        
    Returns:
        Dictionary with validation results:
        - valid_count: Number of valid geometries
        - invalid_count: Number of invalid geometries
        - null_count: Number of null geometries
        - invalid_indices: List of indices with invalid geometries
    """
    geom_series = gdf[geometry_column]
    
    valid_mask = geom_series.notna() & geom_series.is_valid
    invalid_mask = geom_series.notna() & ~geom_series.is_valid
    null_mask = geom_series.isna()
    
    return {
        "valid_count": valid_mask.sum(),
        "invalid_count": invalid_mask.sum(),
        "null_count": null_mask.sum(),
        "invalid_indices": gdf[invalid_mask].index.tolist(),
        "null_indices": gdf[null_mask].index.tolist()
    }


def validate_required_fields(gdf, required_fields):
    """
    Validate that required fields are not null.
    
    Args:
        gdf: GeoDataFrame
        required_fields: List of required field names
        
    Returns:
        Dictionary with validation results:
        - is_valid: Boolean indicating if all required fields are present
        - missing_fields: Fields that don't exist
        - null_counts: Dictionary of field -> count of null values
    """
    missing_fields = []
    null_counts = {}
    
    for field in required_fields:
        if field not in gdf.columns:
            missing_fields.append(field)
        else:
            null_count = gdf[field].isnull().sum()
            if null_count > 0:
                null_counts[field] = null_count
    
    is_valid = len(missing_fields) == 0 and len(null_counts) == 0
    
    return {
        "is_valid": is_valid,
        "missing_fields": missing_fields,
        "null_counts": null_counts
    }


def report_quality(gdf, required_fields=None):
    """
    Generate a comprehensive data quality report.
    
    Args:
        gdf: GeoDataFrame
        required_fields: Optional list of required fields
        
    Returns:
        Dictionary with quality metrics
    """
    report = {
        "row_count": len(gdf),
        "column_count": len(gdf.columns),
        "geometry_validation": validate_geometries(gdf)
    }
    
    if required_fields:
        report["required_fields_validation"] = validate_required_fields(gdf, required_fields)
    
    # Missing values summary
    missing = gdf.isnull().sum()
    report["missing_values"] = {
        col: int(count) 
        for col, count in missing.items() 
        if count > 0
    }
    
    return report

