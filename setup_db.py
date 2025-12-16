#!/usr/bin/env python3
"""
Database Setup Script

Creates partitioned tables, functions, and triggers for the parcel database.
This script can be run independently to set up the database schema without running the full ETL.

Usage:
    python setup_db.py
    # Or with environment variables:
    DB_HOST=localhost DB_PORT=5432 DB_NAME=parcels_db DB_USER=postgres DB_PASSWORD=postgres python setup_db.py
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

import psycopg2
from psycopg2 import sql

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_db_config():
    """Get database configuration from environment variables."""
    config = {
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT'),
        'database': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }
    
    missing = [key for key, value in config.items() if value is None]
    if missing:
        logger.error(f"Missing required database configuration: {', '.join(missing)}")
        logger.error("Please set environment variables:")
        logger.error("  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
        logger.error("\nOr create a .env file with these variables.")
        sys.exit(1)
    
    try:
        config['port'] = int(config['port'])
    except (ValueError, TypeError):
        logger.error(f"Invalid DB_PORT value: {config['port']}")
        sys.exit(1)
    
    return config


def setup_database():
    """Create partitioned tables, functions, and triggers."""
    db_config = get_db_config()
    
    logger.info("Connecting to database...")
    logger.info(f"Host: {db_config['host']}, Database: {db_config['database']}")
    
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        
        logger.info("Enabling PostGIS extension...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        
        logger.info("Creating parcels_master table...")
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
            PRIMARY KEY (state_code, district_code, parcel_uuid)
        ) PARTITION BY LIST (state_code);
        """)
        
        logger.info("Creating parcels_simplified table...")
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
        logger.info("Database setup completed successfully!")
        logger.info("Tables created: parcels_master, parcels_simplified")
        logger.info("Partition functions and triggers are ready")
        
        cur.close()
        conn.close()
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    setup_database()

