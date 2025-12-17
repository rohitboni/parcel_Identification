#!/usr/bin/env python3
"""
Setup Neon Production Database Schema

Creates partitioned tables for the Neon production database (india_cadastral_production).
This creates a new schema structure similar to the local database but adapted for Neon DB.

Usage:
    python setup_neon_db.py
"""

import os
import sys
import logging
import psycopg2
from psycopg2 import sql

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Neon Database Connection
NEON_DB_CONFIG = {
    "host": "ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech",
    "port": 5432,
    "database": "india_cadastral_production",
    "user": "neondb_owner",
    "password": "npg_KwgtR7LI1qUA",
    "sslmode": "require"
}


def get_neon_connection_string():
    """Get Neon database connection string."""
    return (
        f"postgresql://{NEON_DB_CONFIG['user']}:{NEON_DB_CONFIG['password']}"
        f"@{NEON_DB_CONFIG['host']}/{NEON_DB_CONFIG['database']}"
        f"?sslmode={NEON_DB_CONFIG['sslmode']}"
    )


def setup_neon_schema():
    """Create partitioned tables in Neon database."""
    conn_str = get_neon_connection_string()
    
    logger.info("Connecting to Neon database...")
    logger.info(f"Host: {NEON_DB_CONFIG['host']}, Database: {NEON_DB_CONFIG['database']}")
    
    try:
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        
        logger.info("Enabling PostGIS extension...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        
        logger.info("Creating parcels_master_neon partitioned table...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS parcels_master_neon (
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
        
        logger.info("Creating parcels_simplified_neon partitioned table...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS parcels_simplified_neon (
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
        CREATE OR REPLACE FUNCTION create_master_neon_partitions()
        RETURNS TRIGGER AS $$
        DECLARE
            state_part_name TEXT;
            district_part_name TEXT;
            state_exists BOOLEAN;
            district_exists BOOLEAN;
        BEGIN
            state_part_name := 'parcels_master_neon_' || lower(NEW.state_code);
            district_part_name := state_part_name || '_' || NEW.district_code;

            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = state_part_name
            ) INTO state_exists;

            IF NOT state_exists THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF parcels_master_neon
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
        CREATE OR REPLACE FUNCTION create_simplified_neon_partitions()
        RETURNS TRIGGER AS $$
        DECLARE
            state_part_name TEXT;
            district_part_name TEXT;
            state_exists BOOLEAN;
            district_exists BOOLEAN;
        BEGIN
            state_part_name := 'parcels_simplified_neon_' || lower(NEW.state_code);
            district_part_name := state_part_name || '_' || NEW.district_code;

            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = state_part_name
            ) INTO state_exists;

            IF NOT state_exists THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF parcels_simplified_neon
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
        DROP TRIGGER IF EXISTS trg_create_master_neon_partitions ON parcels_master_neon;
        CREATE TRIGGER trg_create_master_neon_partitions
        BEFORE INSERT ON parcels_master_neon
        FOR EACH ROW
        EXECUTE FUNCTION create_master_neon_partitions();
        """)
        
        cur.execute("""
        DROP TRIGGER IF EXISTS trg_create_simplified_neon_partitions ON parcels_simplified_neon;
        CREATE TRIGGER trg_create_simplified_neon_partitions
        BEFORE INSERT ON parcels_simplified_neon
        FOR EACH ROW
        EXECUTE FUNCTION create_simplified_neon_partitions();
        """)
        
        conn.commit()
        logger.info("=" * 60)
        logger.info("Neon database schema setup completed successfully!")
        logger.info("=" * 60)
        logger.info("Tables created:")
        logger.info("  - parcels_master_neon (partitioned)")
        logger.info("  - parcels_simplified_neon (partitioned)")
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
    setup_neon_schema()

