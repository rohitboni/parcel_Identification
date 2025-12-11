-- ============================================================
-- NEW PARTITIONED TABLES SCHEMA
-- ============================================================

-- PARCELS_MASTER (Partitioned by State and District)
CREATE TABLE IF NOT EXISTS parcels_master (
    parcel_uuid           UUID,
    geom                  geometry(MultiPolygon, 4326) NOT NULL,
    label_point           geometry(Point, 4326),
    state                 TEXT NOT NULL,
    state_code            TEXT,
    district_code         TEXT NOT NULL,
    district_name         TEXT NOT NULL,
    sub_district_code     TEXT,
    sub_district_name     TEXT,
    village_code          TEXT,
    village_name          TEXT,
    survey_num            TEXT NOT NULL,
    created_at            TIMESTAMP DEFAULT now(),
    PRIMARY KEY (parcel_uuid, state)
) PARTITION BY LIST (state);

-- Composite index for parcels_master
CREATE INDEX IF NOT EXISTS idx_parcels_master_state_district
ON parcels_master (state, district_code);

-- Spatial index for parcels_master
CREATE INDEX IF NOT EXISTS idx_parcels_master_geom
ON parcels_master
USING GIST (geom);

-- PARCELS_SIMPLIFIED (Partitioned by State and District)
CREATE TABLE IF NOT EXISTS parcels_simplified (
    parcel_uuid     UUID,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    label_point     geometry(Point, 4326) NOT NULL,
    state_code      TEXT NOT NULL,
    district_code   TEXT NOT NULL,
    survey_num      TEXT,
    PRIMARY KEY (parcel_uuid, state_code)
) PARTITION BY LIST (state_code);

-- Spatial index for parcels_simplified
CREATE INDEX IF NOT EXISTS idx_parcels_simplified_geom
ON parcels_simplified
USING GIST (geom);

-- Composite index for parcels_simplified
CREATE INDEX IF NOT EXISTS idx_parcels_simplified_state_district
ON parcels_simplified (state_code, district_code);

-- ============================================================
-- AUTO-PARTITIONING FUNCTIONS AND TRIGGERS
-- ============================================================

-- Function to Auto-Create State + District Partitions (MASTER)
CREATE OR REPLACE FUNCTION create_master_partitions()
RETURNS TRIGGER AS $$
DECLARE
    state_part_name    TEXT;
    district_part_name TEXT;
BEGIN
    state_part_name := 'parcels_master_' || replace(lower(NEW.state), ' ', '_');
    district_part_name := state_part_name || '_' || NEW.district_code;
    
    -- Create state partition if not exists
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF parcels_master
         FOR VALUES IN (%L)
         PARTITION BY LIST (district_code);',
        state_part_name,
        NEW.state
    );
    
    -- Create district sub-partition if not exists
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
         FOR VALUES IN (%L);',
        district_part_name,
        state_part_name,
        NEW.district_code
    );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for PARCELS_MASTER
DROP TRIGGER IF EXISTS trg_create_master_partitions ON parcels_master;
CREATE TRIGGER trg_create_master_partitions
BEFORE INSERT ON parcels_master
FOR EACH ROW
EXECUTE FUNCTION create_master_partitions();

-- Function to Auto-Create State + District Partitions (SIMPLIFIED)
CREATE OR REPLACE FUNCTION create_simplified_partitions()
RETURNS TRIGGER AS $$
DECLARE
    state_part_name    TEXT;
    district_part_name TEXT;
BEGIN
    state_part_name := 'parcels_simplified_' || replace(lower(NEW.state_code), ' ', '_');
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
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for PARCELS_SIMPLIFIED
DROP TRIGGER IF EXISTS trg_create_simplified_partitions ON parcels_simplified;
CREATE TRIGGER trg_create_simplified_partitions
BEFORE INSERT ON parcels_simplified
FOR EACH ROW
EXECUTE FUNCTION create_simplified_partitions();

-- ============================================================
-- LEGACY TABLES (Old Schema)
-- ============================================================

-- 1. parcels_raw table
CREATE TABLE IF NOT EXISTS parcels_raw (
    parcel_uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geom        geometry(MultiPolygon, 4326),
    kide        TEXT,
    kide_1      TEXT,
    kide_2      TEXT,
    survey_num  TEXT,
    gp_name     TEXT,
    v_name      TEXT,
    v_code      TEXT,
    district    TEXT,
    state       TEXT,
    tehsil      TEXT
);

-- Spatial Index for parcels_raw
CREATE INDEX IF NOT EXISTS idx_parcels_raw_geom
    ON parcels_raw
    USING GIST (geom);

-- 2. parcels table
CREATE TABLE IF NOT EXISTS parcels (
    parcel_uuid UUID PRIMARY KEY,
    geom        geometry(MultiPolygon, 4326),
    district    TEXT,
    tehsil      TEXT,
    v_name      TEXT,
    survey_num  TEXT
);

-- Spatial Index for parcels
CREATE INDEX IF NOT EXISTS idx_parcels_geom
    ON parcels
    USING GIST (geom);

-- 3. parcels_simplified_legacy table (renamed to avoid conflict with new partitioned table)
CREATE TABLE IF NOT EXISTS parcels_simplified_legacy (
    parcel_uuid UUID PRIMARY KEY,
    geom        geometry(MultiPolygon, 4326),
    survey_num  TEXT,
    v_code      TEXT
);

-- Spatial Index for parcels_simplified_legacy
CREATE INDEX IF NOT EXISTS idx_parcels_simplified_legacy_geom
    ON parcels_simplified_legacy
    USING GIST (geom);

