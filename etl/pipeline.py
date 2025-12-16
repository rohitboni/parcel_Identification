#!/usr/bin/env python3
"""
ETL Pipeline Orchestrator

Main entry point for the ETL pipeline. Coordinates extract, transform, validate, and load steps.

Usage:
    python pipeline.py --config config/vellore_mapping.yaml
"""
import os

import argparse
import yaml
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.extract import load_data, inspect_schema, validate_source_columns
from modules.transform import prepare_for_master_table, prepare_for_simplified_table
from modules.validate import validate_schema, validate_geometries, validate_required_fields, report_quality
from modules.load import connect_db, setup_partitioned_tables, load_master, load_simplified

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path):
    """Load YAML configuration file."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def run_pipeline(config_path, db_config):
    """
    Run the complete ETL pipeline.
    
    Args:
        config_path: Path to YAML configuration file
        db_config: Database connection configuration
    """
    logger.info("=" * 60)
    logger.info("ETL Pipeline Starting")
    logger.info("=" * 60)
    
    logger.info("Step 1: Loading configuration...")
    config = load_config(config_path)
    logger.info(f"Configuration loaded: {config['dataset']['name']}")
    
    logger.info("\nStep 2: Extracting data...")
    source_path = config['dataset']['source_path']
    gdf = load_data(source_path)
    logger.info(f"Loaded {len(gdf)} rows from {source_path}")
    
    schema = inspect_schema(gdf)
    logger.info(f"Columns: {len(schema['columns'])}, CRS: {schema['crs']}")
    
    required_source_fields = list(config.get('field_mapping', {}).keys())
    transform_sources = [
        v.get('source') 
        for v in config.get('transforms', {}).values()
        if v.get('source') is not None
    ]
    required_source_fields.extend(transform_sources)
    is_valid, missing = validate_source_columns(gdf, required_source_fields)
    if not is_valid:
        logger.error(f"Missing required source columns: {missing}")
        return False
    logger.info("Source columns validated")
    
    logger.info("\nStep 3: Validating source data...")
    geom_validation = validate_geometries(gdf)
    logger.info(f"Valid geometries: {geom_validation['valid_count']}, "
                f"Invalid: {geom_validation['invalid_count']}, "
                f"Null: {geom_validation['null_count']}")
    
    if geom_validation['invalid_count'] > 0:
        logger.warning(f"Found {geom_validation['invalid_count']} invalid geometries (will be fixed)")
    
    logger.info("\nStep 4: Transforming data...")
    logger.info("Preparing for parcels_master...")
    gdf_master = prepare_for_master_table(gdf, config)
    logger.info(f"Master table data prepared: {len(gdf_master)} rows")
    
    logger.info("Preparing for parcels_simplified...")
    gdf_simplified = prepare_for_simplified_table(gdf_master, config)
    logger.info(f"Simplified table data prepared: {len(gdf_simplified)} rows")
    
    logger.info("\nStep 5: Validating transformed data...")
    
    master_required = ['geom', 'state', 'state_code', 'district_code', 'district_name', 'survey_num']
    is_valid, missing, extra = validate_schema(gdf_master, master_required)
    if not is_valid:
        logger.error(f"Missing columns in master data: {missing}")
        return False
    logger.info("Master table schema validated")
    
    required_fields = config.get('required_fields', [])
    field_validation = validate_required_fields(gdf_master, required_fields)
    if not field_validation['is_valid']:
        logger.error("Required fields validation failed:")
        logger.error(f"Missing fields: {field_validation['missing_fields']}")
        logger.error(f"Null values: {field_validation['null_counts']}")
        return False
    logger.info("Required fields validated")
    
    geom_validation = validate_geometries(gdf_master, geometry_column='geom')
    if geom_validation['invalid_count'] > 0:
        logger.warning(f"Still have {geom_validation['invalid_count']} invalid geometries after cleaning")
    logger.info(f"Geometry validation: {geom_validation['valid_count']} valid geometries")
    
    logger.info("\nStep 6: Loading data into database...")
    conn = connect_db(db_config)

    try:
        logger.info("Setting up partitioned tables...")
        setup_partitioned_tables(conn)

        logger.info("Loading parcels_master...")
        master_count = load_master(conn, gdf_master)
        logger.info(f"Inserted {master_count} rows into parcels_master")

        logger.info("Loading parcels_simplified...")
        simplified_count = load_simplified(conn, gdf_master, gdf_simplified)
        logger.info(f"Inserted {simplified_count} rows into parcels_simplified")

    except Exception as e:
        logger.error(f"Error during database load: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    logger.info("\n" + "=" * 60)
    logger.info("ETL Pipeline Complete!")
    logger.info("=" * 60)
    logger.info(f"Processed {len(gdf)} source rows")
    logger.info(f"Inserted {master_count} rows into parcels_master")
    logger.info(f"Inserted {simplified_count} rows into parcels_simplified")
    
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='ETL Pipeline for Parcel Data')
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Path to YAML configuration file'
    )
    parser.add_argument(
        '--db-host',
        type=str,
        default='127.0.0.1',
        help='Database host (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--db-port',
        type=int,
        default=5432,
        help='Database port (default: 5432)'
    )
    parser.add_argument(
        '--db-name',
        type=str,
        default='parcels_db',
        help='Database name (default: parcels_db)'
    )
    parser.add_argument(
        '--db-user',
        type=str,
        default='postgres',
        help='Database user (default: postgres)'
    )
    parser.add_argument(
        '--db-password',
        type=str,
        default='postgres',
        help='Database password (default: postgres)'
    )
    
    args = parser.parse_args()
    
    # Use CLI args if provided, otherwise require environment variables
    db_config = {
        'host': args.db_host or os.getenv('DB_HOST'),
        'port': args.db_port or int(os.getenv('DB_PORT')),
        'database': args.db_name or os.getenv('DB_NAME'),
        'user': args.db_user or os.getenv('DB_USER'),
        'password': args.db_password or os.getenv('DB_PASSWORD')
    }
    
    missing = [key for key, value in db_config.items() if value is None]
    if missing:
        print(f"Missing database configuration: {', '.join(missing)}", file=sys.stderr)
        print("Please set environment variables or provide CLI arguments", file=sys.stderr)
        sys.exit(1)
    
    success = run_pipeline(args.config, db_config)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

