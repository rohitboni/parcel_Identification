-- Create partitioned tables for parcel data
-- Run this script to set up the database schema

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Create parcels_master partitioned table
CREATE TABLE parcels_master (
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

-- Create parcels_simplified partitioned table
CREATE TABLE parcels_simplified (
    parcel_uuid     UUID NOT NULL,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    label_point     geometry(Point, 4326) NOT NULL,
    state_code      TEXT NOT NULL,
    district_code   TEXT NOT NULL,
    survey_num      TEXT,
    PRIMARY KEY (state_code, district_code, parcel_uuid)
) PARTITION BY LIST (state_code);

-- Function to auto-create partitions for parcels_master
CREATE OR REPLACE FUNCTION create_master_partitions()
RETURNS TRIGGER AS $$
DECLARE
    state_part_name    TEXT;
    district_part_name TEXT;
BEGIN
    state_part_name := 'parcels_master_' || lower(NEW.state_code);
    district_part_name := state_part_name || '_' || NEW.district_code;

    -- Create state partition if not exists
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF parcels_master
         FOR VALUES IN (%L)
         PARTITION BY LIST (district_code);',
        state_part_name,
        NEW.state_code
    );

    -- Create district sub-partition if not exists
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
         FOR VALUES IN (%L);',
        district_part_name,
        state_part_name,
        NEW.district_code
    );

    -- Create indexes on the district partition
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I_geom_idx ON %I USING GIST (geom);',
        district_part_name || '_geom_idx',
        district_part_name
    );

    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I_state_district_idx ON %I (state_code, district_code);',
        district_part_name || '_state_district_idx',
        district_part_name
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for parcels_master
CREATE TRIGGER trg_create_master_partitions
BEFORE INSERT ON parcels_master
FOR EACH ROW
EXECUTE FUNCTION create_master_partitions();

-- Function to auto-create partitions for parcels_simplified
CREATE OR REPLACE FUNCTION create_simplified_partitions()
RETURNS TRIGGER AS $$
DECLARE
    state_part_name    TEXT;
    district_part_name TEXT;
BEGIN
    state_part_name := 'parcels_simplified_' || lower(NEW.state_code);
    district_part_name := state_part_name || '_' || NEW.district_code;

    -- Create state partition if not exists
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF parcels_simplified
         FOR VALUES IN (%L)
         PARTITION BY LIST (district_code);',
        state_part_name,
        NEW.state_code
    );

    -- Create district sub-partition if not exists
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
         FOR VALUES IN (%L);',
        district_part_name,
        state_part_name,
        NEW.district_code
    );

    -- Create indexes on the district partition
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I_geom_idx ON %I USING GIST (geom);',
        district_part_name || '_geom_idx',
        district_part_name
    );

    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I_state_district_idx ON %I (state_code, district_code);',
        district_part_name || '_state_district_idx',
        district_part_name
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for parcels_simplified
CREATE TRIGGER trg_create_simplified_partitions
BEFORE INSERT ON parcels_simplified
FOR EACH ROW
EXECUTE FUNCTION create_simplified_partitions();
