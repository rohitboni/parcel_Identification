"""
Load module for ETL pipeline.

Handles database loading with batch inserts and progress tracking.
"""

import psycopg2
from psycopg2.extras import execute_values
from psycopg2 import sql
import geopandas as gpd
import pandas as pd
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def connect_db(db_config):
    """
    Create database connection.

    Args:
        db_config: Dictionary with database connection parameters
            {
                'host': '127.0.0.1',
                'port': 5432,
                'database': 'parcels_db',
                'user': 'postgres',
                'password': 'postgres'
            }

    Returns:
        psycopg2 connection object
    """
    return psycopg2.connect(**db_config)


def setup_partitioned_tables(conn):
    """
    Create partitioned tables if they don't exist.

    Args:
        conn: Database connection
    """
    cur = conn.cursor()

    try:
        # Enable PostGIS
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

        # Create parcels_master table - two-level partitioning (state -> district)
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

        # Create parcels_simplified table - two-level partitioning (state -> district)
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

        # Auto-create partitions with two levels (state partition -> district sub-partition)
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

            -- Check if state partition exists
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = state_part_name
            ) INTO state_exists;

            -- Create state partition only if it doesn't exist
            IF NOT state_exists THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF parcels_master
                     FOR VALUES IN (%L)
                     PARTITION BY LIST (district_code);',
                    state_part_name,
                    NEW.state_code
                );
            END IF;

            -- Check if district partition exists
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = district_part_name
            ) INTO district_exists;

            -- Create district sub-partition only if it doesn't exist
            IF NOT district_exists THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE %I PARTITION OF %I
                         FOR VALUES IN (%L);',
                        district_part_name,
                        state_part_name,
                        NEW.district_code
                    );

                    -- Create indexes on district partition
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
                        -- Partition already exists (created by another process), that's fine
                        NULL;
                    WHEN OTHERS THEN
                        -- If it's a lock error ("being used by active queries") or other issue, 
                        -- the partition might already exist or be created by pre-creation
                        -- Just continue - the insert will work if partition exists
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

            -- Check if state partition exists
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = state_part_name
            ) INTO state_exists;

            -- Create state partition only if it doesn't exist
            IF NOT state_exists THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF parcels_simplified
                     FOR VALUES IN (%L)
                     PARTITION BY LIST (district_code);',
                    state_part_name,
                    NEW.state_code
                );
            END IF;

            -- Check if district partition exists
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = district_part_name
            ) INTO district_exists;

            -- Create district sub-partition only if it doesn't exist
            IF NOT district_exists THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE %I PARTITION OF %I
                         FOR VALUES IN (%L);',
                        district_part_name,
                        state_part_name,
                        NEW.district_code
                    );

                    -- Create indexes on district partition
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
                        -- Partition already exists (created by another process), that's fine
                        NULL;
                    WHEN OTHERS THEN
                        -- If it's a lock error ("being used by active queries") or other issue, 
                        -- the partition might already exist or be created by pre-creation
                        -- Just continue - the insert will work if partition exists
                        NULL;
                END;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)

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
        logger.info("Partitioned tables and triggers created successfully")

    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()


def ensure_partitions_exist(conn, gdf, table_name='parcels_master'):
    """
    Pre-create all partitions needed for the data.
    
    This ensures partitions exist before batch inserts, avoiding
    "no partition found" errors during executemany operations.
    
    Args:
        conn: Database connection
        gdf: GeoDataFrame with state_code and district_code columns
        table_name: Name of the partitioned table
    """
    cur = conn.cursor()
    
    try:
        # Get unique state_code/district_code combinations
        unique_combos = gdf[['state_code', 'district_code']].drop_duplicates()
        
        logger.info(f"Pre-creating partitions for {len(unique_combos)} unique state/district combinations...")
        
        # Group by state_code to create state partitions first, then district partitions
        # This reduces the number of transactions needed
        state_groups = unique_combos.groupby('state_code')
        created_states = set()
        
        batch_count = 0
        commit_interval = 100  # Commit every 100 district partitions
        
        for state_code, state_group in state_groups:
            state_code_str = str(state_code)
            state_part_name = f'{table_name}_{state_code_str.lower()}'
            
            # Create state partition if not exists (only once per state)
            if state_code_str not in created_states:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_class WHERE relname = %s
                    );
                """, (state_part_name,))
                
                partition_exists = cur.fetchone()[0]
                
                if not partition_exists:
                    # Create state partition (partitioned by district_code)
                    try:
                        cur.execute(f"""
                            CREATE TABLE {state_part_name} PARTITION OF {table_name}
                            FOR VALUES IN ('{state_code_str}')
                            PARTITION BY LIST (district_code);
                        """)
                        logger.debug(f"Created state partition: {state_part_name}")
                    except Exception as e:
                        # If partition was created by another process, that's fine
                        if 'already exists' in str(e).lower():
                            logger.debug(f"State partition {state_part_name} already exists, skipping")
                        else:
                            raise
                else:
                    # Partition already exists - just use it
                    # The trigger will handle creating district partitions if needed
                    logger.debug(f"State partition {state_part_name} already exists, using existing partition")
                
                # Commit state partition creation immediately (if we created one)
                if not partition_exists:
                    conn.commit()
                created_states.add(state_code_str)
            
            # Now create all district partitions for this state
            for idx, row in state_group.iterrows():
                district_code = str(row['district_code'])
                district_part_name = f'{state_part_name}_{district_code}'
                
                # Check if district partition exists, create if not (with exception handling)
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_class WHERE relname = %s
                    );
                """, (district_part_name,))
                
                district_exists = cur.fetchone()[0]
                
                if not district_exists:
                    # Create district sub-partition with exception handling
                    try:
                        # Create district partition directly
                        cur.execute(f"""
                            CREATE TABLE {district_part_name} PARTITION OF {state_part_name}
                            FOR VALUES IN ('{district_code}');
                        """)
                        
                        # Create indexes on district partition (these are idempotent)
                        cur.execute(f"""
                            CREATE INDEX IF NOT EXISTS {district_part_name}_geom_idx 
                            ON {district_part_name} USING GIST (geom);
                        """)
                        cur.execute(f"""
                            CREATE INDEX IF NOT EXISTS {district_part_name}_state_district_idx 
                            ON {district_part_name} (state_code, district_code);
                        """)
                        
                        batch_count += 1
                        
                        # Commit periodically to avoid lock exhaustion
                        if batch_count % commit_interval == 0:
                            conn.commit()
                            logger.info(f"Created {batch_count} district partitions...")
                    except Exception as e:
                        error_msg = str(e).lower()
                        # If partition already exists, was created by trigger, or has lock issues, that's fine
                        if any(phrase in error_msg for phrase in ['already exists', 'being used', 'does not exist', 'duplicate']):
                            logger.debug(f"District partition {district_part_name} already exists or in use, skipping")
                            # Partition might exist now, try to create indexes anyway
                            try:
                                cur.execute(f"""
                                    CREATE INDEX IF NOT EXISTS {district_part_name}_geom_idx 
                                    ON {district_part_name} USING GIST (geom);
                                """)
                                cur.execute(f"""
                                    CREATE INDEX IF NOT EXISTS {district_part_name}_state_district_idx 
                                    ON {district_part_name} (state_code, district_code);
                                """)
                            except Exception:
                                pass  # Indexes might already exist or partition not ready
                            batch_count += 1
                        else:
                            raise
                else:
                    # Partition already exists, just ensure indexes exist
                    try:
                        cur.execute(f"""
                            CREATE INDEX IF NOT EXISTS {district_part_name}_geom_idx 
                            ON {district_part_name} USING GIST (geom);
                        """)
                        cur.execute(f"""
                            CREATE INDEX IF NOT EXISTS {district_part_name}_state_district_idx 
                            ON {district_part_name} (state_code, district_code);
                        """)
                    except Exception:
                        pass  # Indexes might already exist
        
        conn.commit()
        logger.info(f"All partitions pre-created successfully ({batch_count} district partitions)")
        
    except Exception as e:
        logger.error(f"Error pre-creating partitions: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()


def load_master(conn, gdf, batch_size=1000):
    """
    Load data into parcels_master table.
    
    Note: parcel_uuid is auto-generated by database (DEFAULT gen_random_uuid())
    
    Args:
        conn: Database connection
        gdf: GeoDataFrame with columns matching parcels_master schema:
            - geom (MultiPolygon, 4326)
            - label_point (Point, 4326)
            - state (TEXT)
            - state_code (TEXT)
            - district_code (TEXT)
            - district_name (TEXT)
            - sub_district_name (TEXT, optional)
            - village_name (TEXT, optional)
            - survey_num (TEXT)
        batch_size: Number of rows to insert per batch
        
    Returns:
        Number of rows inserted
    """
    cur = conn.cursor()
    
    # Pre-create all partitions before inserting
    ensure_partitions_exist(conn, gdf, 'parcels_master')
    
    # Prepare data for insertion
    # Note: parcel_uuid is auto-generated, so we don't include it
    insert_sql = """
    INSERT INTO parcels_master 
    (geom, label_point, state, state_code, district_code, district_name, 
     sub_district_name, village_name, survey_num)
    VALUES (ST_GeomFromEWKB(%s), ST_GeomFromEWKB(%s), %s, %s, %s, %s, %s, %s, %s)
    """
    
    # Prepare rows
    rows = []
    for idx, row in gdf.iterrows():
        # Convert geometries to WKB
        geom_wkb = psycopg2.Binary(row['geom'].wkb) if row['geom'] is not None else None
        label_point_wkb = (
            psycopg2.Binary(row['label_point'].wkb) 
            if 'label_point' in row and row['label_point'] is not None 
            else None
        )
        
        # Prepare row data
        row_data = (
            geom_wkb,
            label_point_wkb,
            str(row.get('state', '')),
            str(row.get('state_code', '')),
            str(row.get('district_code', '')),
            str(row.get('district_name', '')),
            str(row.get('sub_district_name')) if pd.notna(row.get('sub_district_name')) else None,
            str(row.get('village_name')) if pd.notna(row.get('village_name')) else None,
            str(row.get('survey_num', ''))
        )
        rows.append(row_data)
    
    # Batch insert using executemany for better performance
    total_inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        cur.executemany(insert_sql, batch)
        total_inserted += len(batch)
        logger.info(f"Inserted {total_inserted}/{len(rows)} rows into parcels_master")
    
    conn.commit()
    cur.close()
    
    return total_inserted


def load_simplified(conn, gdf_master, gdf_simplified, batch_size=1000):
    """
    Load data into parcels_simplified table.
    
    Matches simplified rows to master rows by POSITION (insertion order).
    This is correct because:
    - gdf_simplified is derived from gdf_master row-by-row in the same order
    - Multiple parcels can have the same survey_num (different geometries, same survey number)
    - Matching by survey_num would cause duplicate parcel_uuid errors
    - parcel_uuid is the unique identifier (foreign key from parcels_master)
    
    Args:
        conn: Database connection
        gdf_master: GeoDataFrame used for master table (for reference, not used for matching)
        gdf_simplified: GeoDataFrame with simplified geometries (same order as gdf_master)
        batch_size: Number of rows to insert per batch
        
    Returns:
        Number of rows inserted
    """
    cur = conn.cursor()
    
    # Pre-create all partitions before inserting
    ensure_partitions_exist(conn, gdf_simplified, 'parcels_simplified')
    
    # Fetch parcel_uuid values from parcels_master in insertion order
    # This ensures we match gdf_simplified[i] to parcels_master[i] by position
    logger.info("Fetching parcel_uuid values from parcels_master in insertion order...")
    cur.execute("""
        SELECT parcel_uuid, state_code, district_code
        FROM parcels_master
        ORDER BY created_at, parcel_uuid
    """)
    master_rows = cur.fetchall()
    master_uuids = {i: row[0] for i, row in enumerate(master_rows)}
    
    if len(master_uuids) != len(gdf_simplified):
        logger.warning(
            f"Mismatch: parcels_master has {len(master_uuids)} rows, "
            f"but gdf_simplified has {len(gdf_simplified)} rows. "
            f"This might cause issues."
        )
    
    # Insert using position-based matching
    insert_sql = """
    INSERT INTO parcels_simplified
    (parcel_uuid, geom, label_point, state_code, district_code, survey_num)
    VALUES (%s, ST_GeomFromEWKB(%s), ST_GeomFromEWKB(%s), %s, %s, %s)
    """
    
    rows = []
    for position, (idx, row) in enumerate(gdf_simplified.iterrows()):
        # Access geometry using the geometry property (works regardless of column name)
        geom = gdf_simplified.geometry.loc[idx]
        geom_wkb = psycopg2.Binary(geom.wkb) if geom is not None and hasattr(geom, 'wkb') else None
        
        label_point_wkb = (
            psycopg2.Binary(row['label_point'].wkb) 
            if 'label_point' in row and row['label_point'] is not None 
            else None
        )
        
        state_code = str(row.get('state_code', ''))
        district_code = str(row.get('district_code', ''))
        survey_num = str(row.get('survey_num', ''))
        
        # Match by position: gdf_simplified[position] corresponds to master_uuids[position]
        # This works because gdf_simplified is derived from gdf_master in the same order
        parcel_uuid = master_uuids.get(position)
        
        if parcel_uuid is None:
            logger.warning(f"No parcel_uuid found for position {position}, skipping")
            continue

        row_data = (
            parcel_uuid,  # Use UUID from master table (matched by position - acts as foreign key)
            geom_wkb,
            label_point_wkb,
            state_code,
            district_code,
            survey_num
        )
        rows.append(row_data)
    
    # Batch insert using executemany for better performance
    total_inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        cur.executemany(insert_sql, batch)
        total_inserted += len(batch)
        logger.info(f"Inserted {total_inserted}/{len(rows)} rows into parcels_simplified")
    
    conn.commit()
    cur.close()
    
    return total_inserted

