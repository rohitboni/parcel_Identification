#!/usr/bin/env python3
"""
Setup Local Database Schema

Creates a new database and partitioned tables for local PostgreSQL.
This creates a new schema structure with 2 partitioned tables.

Usage:
    python setup_neon_db.py
    
    # Or with custom database name
    DB_NAME=parcels_db_new python setup_neon_db.py
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Local Database Connection (for creating database)
# Force localhost to ensure we're creating a local database
LOCAL_DB_CONFIG = {
    "host": "127.0.0.1",  # Force localhost
    "port": 5432,  # Default PostgreSQL port
    "user": "postgres",  # Default PostgreSQL user
    "password": os.getenv("DB_PASSWORD", "postgres")  # Only use password from env if set
}

# Database name to create - use environment variable or default
NEW_DB_NAME = os.getenv("NEW_DB_NAME", "parcels_db_new")


def create_database(db_name):
    """Create a new database if it doesn't exist."""
    # Connect to postgres database to create new database
    config = LOCAL_DB_CONFIG.copy()
    config['database'] = 'postgres'  # Connect to default postgres database
    
    try:
        conn = psycopg2.connect(**config)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Check if database exists
        cur.execute("""
            SELECT 1 FROM pg_database WHERE datname = %s;
        """, (db_name,))
        
        exists = cur.fetchone()
        
        if exists:
            logger.info(f"Database '{db_name}' already exists. Using existing database.")
        else:
            logger.info(f"Creating new database '{db_name}'...")
            cur.execute(f'CREATE DATABASE {db_name};')
            logger.info(f"Database '{db_name}' created successfully!")
        
        cur.close()
        conn.close()
        
    except psycopg2.Error as e:
        logger.error(f"Error creating database: {e}")
        raise


def setup_local_schema():
    """Create partitioned tables in local database."""
    # First, create the database
    create_database(NEW_DB_NAME)
    
    # Now connect to the new database
    db_config = LOCAL_DB_CONFIG.copy()
    db_config['database'] = NEW_DB_NAME
    
    logger.info("=" * 60)
    logger.info("Setting up Local Database Schema")
    logger.info("=" * 60)
    logger.info(f"Connecting to local database...")
    logger.info(f"Host: {db_config['host']}, Database: {db_config['database']}")
    
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        
        logger.info("Enabling PostGIS extension...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        
        logger.info("Creating parcels_master partitioned table...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS parcels_master (
            parcel_uuid           UUID NOT NULL DEFAULT gen_random_uuid(),
            geom                  geometry(MultiPolygon, 4326) NOT NULL,
            label_point           geometry(Point, 4326),
            state                 TEXT NOT NULL,
            state_code            TEXT NOT NULL,
            district_code         TEXT NOT NULL,
            district_name         TEXT NOT NULL,
            sub_district_name     TEXT,
            village_name          TEXT,
            survey_num            TEXT NOT NULL,
            created_at            TIMESTAMP DEFAULT now(),
            source_gid            INTEGER,
            PRIMARY KEY (state_code, district_code, parcel_uuid)
        ) PARTITION BY LIST (state_code);
        """)
        
        logger.info("Creating parcels_simplified partitioned table...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS parcels_simplified (
            parcel_uuid     UUID NOT NULL,
            geom            geometry(MultiPolygon, 4326) NOT NULL,
            label_point     geometry(Point, 4326) NOT NULL,
            state_code      TEXT NOT NULL,
            district_code   TEXT NOT NULL,
            survey_num      TEXT,
            PRIMARY KEY (state_code, district_code, parcel_uuid)
        ) PARTITION BY LIST (state_code);
        """)
        
        logger.info("Creating partition functions...")
        cur.execute("""
        CREATE OR REPLACE FUNCTION create_master_partitions()
        RETURNS TRIGGER AS $$
        DECLARE
            state_part_name TEXT;
            district_part_name TEXT;
            state_exists BOOLEAN;
            district_exists BOOLEAN;
        BEGIN
            state_part_name := 'parcels_master_' || lower(NEW.state_code);
            district_part_name := state_part_name || '_' || NEW.district_code;

            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = state_part_name
            ) INTO state_exists;

            IF NOT state_exists THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF parcels_master
                     FOR VALUES IN (%L)
                     PARTITION BY LIST (district_code);',
                    state_part_name,
                    NEW.state_code
                );
            END IF;

            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = district_part_name
            ) INTO district_exists;

            IF NOT district_exists THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE %I PARTITION OF %I
                         FOR VALUES IN (%L);',
                        district_part_name,
                        state_part_name,
                        NEW.district_code
                    );

                    EXECUTE format(
                        'CREATE INDEX IF NOT EXISTS %I ON %I USING GIST (geom);',
                        district_part_name || '_geom_idx',
                        district_part_name
                    );

                    EXECUTE format(
                        'CREATE INDEX IF NOT EXISTS %I ON %I (state_code, district_code);',
                        district_part_name || '_state_district_idx',
                        district_part_name
                    );
                EXCEPTION
                    WHEN duplicate_table THEN
                        NULL;
                    WHEN OTHERS THEN
                        NULL;
                END;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
        
        cur.execute("""
        CREATE OR REPLACE FUNCTION create_simplified_partitions()
        RETURNS TRIGGER AS $$
        DECLARE
            state_part_name TEXT;
            district_part_name TEXT;
            state_exists BOOLEAN;
            district_exists BOOLEAN;
        BEGIN
            state_part_name := 'parcels_simplified_' || lower(NEW.state_code);
            district_part_name := state_part_name || '_' || NEW.district_code;

            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = state_part_name
            ) INTO state_exists;

            IF NOT state_exists THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF parcels_simplified
                     FOR VALUES IN (%L)
                     PARTITION BY LIST (district_code);',
                    state_part_name,
                    NEW.state_code
                );
            END IF;

            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = district_part_name
            ) INTO district_exists;

            IF NOT district_exists THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE %I PARTITION OF %I
                         FOR VALUES IN (%L);',
                        district_part_name,
                        state_part_name,
                        NEW.district_code
                    );

                    EXECUTE format(
                        'CREATE INDEX IF NOT EXISTS %I ON %I USING GIST (geom);',
                        district_part_name || '_geom_idx',
                        district_part_name
                    );

                    EXECUTE format(
                        'CREATE INDEX IF NOT EXISTS %I ON %I (state_code, district_code);',
                        district_part_name || '_state_district_idx',
                        district_part_name
                    );
                EXCEPTION
                    WHEN duplicate_table THEN
                        NULL;
                    WHEN OTHERS THEN
                        NULL;
                END;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
        
        logger.info("Creating triggers...")
        cur.execute("""
        DROP TRIGGER IF EXISTS trg_create_master_partitions ON parcels_master;
        CREATE TRIGGER trg_create_master_partitions
        BEFORE INSERT ON parcels_master
        FOR EACH ROW
        EXECUTE FUNCTION create_master_partitions();
        """)
        
        cur.execute("""
        DROP TRIGGER IF EXISTS trg_create_simplified_partitions ON parcels_simplified;
        CREATE TRIGGER trg_create_simplified_partitions
        BEFORE INSERT ON parcels_simplified
        FOR EACH ROW
        EXECUTE FUNCTION create_simplified_partitions();
        """)
        
        conn.commit()
        logger.info("=" * 60)
        logger.info("Local database schema setup completed successfully!")
        logger.info("=" * 60)
        logger.info(f"Database: {NEW_DB_NAME}")
        logger.info("Tables created:")
        logger.info("  - parcels_master (partitioned)")
        logger.info("  - parcels_simplified (partitioned)")
        logger.info("Partition functions and triggers are ready")
        logger.info("=" * 60)
        logger.info(f"\nTo use this database, update your .env file:")
        logger.info(f"  DB_NAME={NEW_DB_NAME}")
        logger.info("=" * 60)
        
        cur.close()
        conn.close()
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    setup_local_schema()
