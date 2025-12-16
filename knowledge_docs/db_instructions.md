Parcels_master table:

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



Added DEFAULT gen_random_uuid() so DB safely handles UUIDs


Partitioning correctly kept on state_code


About Indexes on Partitioned Tables (Important)
Do you need to manually create indexes for every partition?
PostgreSQL behavior:
Indexes created on the parent table are NOT inherited by child partitions.


You must create indexes on partitions — but this can (and should) be automated.



✅ Best Practice: Automatic Index Creation via Trigger
You can modify your partition-creation trigger to auto-create indexes on each new partition. Add this inside your partition trigger function:

-- Spatial index
EXECUTE format(
    'CREATE INDEX IF NOT EXISTS %I_geom_idx ON %I USING GIST (geom);',
    district_part_name,
    district_part_name
);

-- Composite index
EXECUTE format(
    'CREATE INDEX IF NOT EXISTS %I_state_district_idx ON %I (state_code, district_code);',
    district_part_name,
    district_part_name
);






Parcels_simplified:


CREATE TABLE parcels_simplified (
    parcel_uuid     UUID NOT NULL,

    -- Lighter geometry for tile rendering
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    label_point     geometry(Point, 4326) NOT NULL,

    -- Partition/filter fields
    state_code      TEXT NOT NULL,
    district_code   TEXT NOT NULL,

    -- Label text
    survey_num      TEXT,
    PRIMARY KEY (state_code, district_code, parcel_uuid)
) PARTITION BY LIST (state_code);



-- Create spatial index on the new district partition
EXECUTE format(
    'CREATE INDEX IF NOT EXISTS %I_geom_idx ON %I USING GIST (geom);',
    district_part_name,
    district_part_name
);

-- Create composite index
EXECUTE format(
    'CREATE INDEX IF NOT EXISTS %I_state_dist_idx ON %I (state_code, district_code);',
    district_part_name,
    district_part_name
);




Function to Auto-Create State + District Partitions (MASTER):

CREATE OR REPLACE FUNCTION create_master_partitions()
RETURNS TRIGGER AS $$
DECLARE
    state_part_name    TEXT;
    district_part_name TEXT;
BEGIN
    -- Use state_code (not state)
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

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;



Trigger for PARCELS_MASTER:

CREATE TRIGGER trg_create_master_partitions
BEFORE INSERT ON parcels_master
FOR EACH ROW
EXECUTE FUNCTION create_master_partitions();


 Function to Auto-Create State + District Partitions (SIMPLIFIED)

CREATE OR REPLACE FUNCTION create_simplified_partitions()
RETURNS TRIGGER AS $$
DECLARE
    state_part_name    TEXT;
    district_part_name TEXT;
BEGIN
    state_part_name := 'parcels_simplified_' || lower(NEW.state_code);
    district_part_name := state_part_name || '_' || NEW.district_code;

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF parcels_simplified
         FOR VALUES IN (%L)
         PARTITION BY LIST (district_code);',
        state_part_name,
        NEW.state_code
    );

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




Trigger for PARCELS_SIMPLIFIED:

CREATE TRIGGER trg_create_simplified_partitions
BEFORE INSERT ON parcels_simplified
FOR EACH ROW
EXECUTE FUNCTION create_simplified_partitions();


