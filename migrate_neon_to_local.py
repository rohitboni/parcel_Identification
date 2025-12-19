#!/usr/bin/env python3
"""
Migrate Data from Neon cadastrals Table to Local Database

This script:
1. Reads data from Neon database (cadastrals table - source table)
2. Transforms geometry: EPSG:32643 → EPSG:4326
3. Maps column names: PascalCase → snake_case
4. Computes label_points using ST_PointOnSurface
5. Inserts into local database (parcels_master, parcels_simplified)
6. Creates partitions automatically via triggers

Usage:
    # Interactive mode (recommended)
    python migrate_neon_to_local.py
    
    # With custom batch size
    python migrate_neon_to_local.py --batch-size=2000
"""

import argparse
import sys
import logging
import psycopg2
from psycopg2.extras import execute_batch
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Neon Database Connection (source)
NEON_DB_CONFIG = {
    "host": "ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech",
    "port": 5432,
    "database": "india_cadastral_production",
    "user": "neondb_owner",
    "password": "npg_KwgtR7LI1qUA",
    "sslmode": "require"
}

# Local Database Connection (destination)
LOCAL_DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "parcels_db_new"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres")
}


def get_states(conn):
    """Get list of states from Neon cadastrals table."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT "State_Code", "State_Name", COUNT(*) as count
        FROM cadastrals
        WHERE geom IS NOT NULL
          AND "State_Code" IS NOT NULL
          AND "District_Code" IS NOT NULL
          AND "District_Name" IS NOT NULL
          AND "Survey_Number" IS NOT NULL
        GROUP BY "State_Code", "State_Name"
        ORDER BY count DESC;
    """)
    return cur.fetchall()


def get_districts_for_state(conn, state_code):
    """Get list of districts for a state from Neon cadastrals table."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT "District_Code", "District_Name", COUNT(*) as count
        FROM cadastrals
        WHERE "State_Code" = %s
          AND geom IS NOT NULL
          AND "State_Code" IS NOT NULL
          AND "District_Code" IS NOT NULL
          AND "District_Name" IS NOT NULL
          AND "Survey_Number" IS NOT NULL
        GROUP BY "District_Code", "District_Name"
        ORDER BY count DESC;
    """, (state_code.lower(),))
    return cur.fetchall()


def interactive_selection(neon_conn):
    """Interactive selection of state and districts."""
    print("\n" + "=" * 60)
    print("Neon cadastrals → Local Database Migration - Interactive Selection")
    print("=" * 60)
    
    # Get states
    states = get_states(neon_conn)
    if not states:
        print("No states found in Neon cadastrals table!")
        return None, None
    
    print(f"\nFound {len(states)} state(s):\n")
    for idx, (state_code, state_name, count) in enumerate(states, 1):
        print(f"  [{idx}] {state_name:30s} ({state_code:5s}) - {count:>10,} parcels")
    
    # Select state
    while True:
        try:
            choice = input(f"\nSelect state (1-{len(states)}): ").strip()
            if choice.lower() == 'q':
                return None, None
            
            idx = int(choice) - 1
            if 0 <= idx < len(states):
                selected_state_code, selected_state_name, _ = states[idx]
                break
            else:
                print(f"Please enter a number between 1 and {len(states)}")
        except ValueError:
            print("Please enter a valid number or 'q' to quit")
        except KeyboardInterrupt:
            print("\n\nMigration cancelled by user")
            return None, None
    
    print(f"\nSelected State: {selected_state_name} ({selected_state_code})")
    
    # Get districts
    districts = get_districts_for_state(neon_conn, selected_state_code)
    if not districts:
        print(f"No districts found for {selected_state_name}!")
        return None, None
    
    print(f"\nFound {len(districts)} district(s) in {selected_state_name}:\n")
    for idx, (district_code, district_name, count) in enumerate(districts, 1):
        print(f"  [{idx}] {district_name:30s} ({district_code:10s}) - {count:>10,} parcels")
    print(f"  [{len(districts) + 1}] ALL districts")
    
    # Select districts
    while True:
        try:
            choice = input(f"\nSelect district(s) (1-{len(districts)}, comma-separated for multiple, or '{len(districts) + 1}' for ALL): ").strip()
            if choice.lower() == 'q':
                return None, None
            
            if choice.lower() == 'all' or choice == str(len(districts) + 1):
                selected_districts = districts
                break
            else:
                choice_parts = [c.strip() for c in choice.split(',')]
                
                if any(c.lower() == 'all' or c == str(len(districts) + 1) for c in choice_parts):
                    print(f"Error: '{len(districts) + 1}' (ALL districts) cannot be combined with other selections.")
                    continue
                
                try:
                    choices = [int(c) - 1 for c in choice_parts if c]
                except ValueError:
                    print(f"Error: Invalid input. Please enter numbers between 1 and {len(districts)}, or '{len(districts) + 1}' for ALL")
                    continue
                
                if all(0 <= c < len(districts) for c in choices):
                    seen = set()
                    unique_choices = []
                    for c in choices:
                        if c not in seen:
                            seen.add(c)
                            unique_choices.append(c)
                    selected_districts = [districts[c] for c in unique_choices]
                    break
                else:
                    invalid = [c + 1 for c in choices if c < 0 or c >= len(districts)]
                    print(f"Error: Invalid district numbers: {invalid}")
        except KeyboardInterrupt:
            print("\n\nMigration cancelled by user")
            return None, None
    
    print(f"\n{'='*60}")
    print(f"Selected {len(selected_districts)} district(s):")
    print(f"{'='*60}")
    total_parcels = 0
    for district_code, district_name, count in selected_districts:
        print(f"  ✓ {district_name:30s} ({district_code:10s}): {count:>10,} parcels")
        total_parcels += count
    
    print(f"{'='*60}")
    print(f"Total parcels to migrate: {total_parcels:,}")
    print(f"{'='*60}")
    
    confirm = input("\nProceed with migration to LOCAL database? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("Migration cancelled")
        return None, None
    
    return selected_state_code, selected_districts


def migrate_data(batch_size=2000, state_code=None, districts=None):
    """Migrate data from Neon cadastrals table to local database."""
    logger.info("=" * 60)
    logger.info("Starting Neon cadastrals → Local Database Migration")
    logger.info("=" * 60)
    
    try:
        # Connect to both databases
        neon_conn = psycopg2.connect(**NEON_DB_CONFIG)
        local_conn = psycopg2.connect(**LOCAL_DB_CONFIG)
        
        neon_cur = neon_conn.cursor()
        local_cur = local_conn.cursor()
        
        # Interactive selection if not provided
        if state_code is None or districts is None:
            result = interactive_selection(neon_conn)
            if result == (None, None):
                logger.info("Migration cancelled by user")
                return
            state_code, districts = result
        
        # Store original state_code (lowercase) for queries, uppercase version for inserts
        state_code_lower = state_code.lower() if state_code else None
        state_code_upper = state_code.upper() if state_code else None
        
        # Build district filter - need to match by both district_code AND district_name
        district_filters = []
        district_params = []
        for district_code, district_name, _ in districts:
            district_filters.append('("District_Code" = %s AND "District_Name" = %s)')
            district_params.extend([district_code, district_name])
        
        where_district_filter = ' OR '.join(district_filters)
        
        # Get total count
        neon_cur.execute(f"""
            SELECT COUNT(*) 
            FROM cadastrals
            WHERE "State_Code" = %s
              AND ({where_district_filter})
              AND geom IS NOT NULL
              AND "State_Code" IS NOT NULL
              AND "District_Code" IS NOT NULL
              AND "District_Name" IS NOT NULL
              AND "Survey_Number" IS NOT NULL;
        """, [state_code_lower] + district_params)
        
        total_count = neon_cur.fetchone()[0]
        logger.info(f"Total parcels to migrate: {total_count:,}")
        
        if total_count == 0:
            logger.warning("No parcels found matching criteria!")
            return
        
        # Check if source_gid column exists in local database
        local_cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'parcels_master' 
              AND column_name = 'source_gid';
        """)
        has_source_gid = local_cur.fetchone() is not None
        
        # Add source_gid column if it doesn't exist
        if not has_source_gid:
            logger.info("Adding source_gid column to parcels_master...")
            local_cur.execute("ALTER TABLE parcels_master ADD COLUMN IF NOT EXISTS source_gid INTEGER;")
            local_conn.commit()
            logger.info("source_gid column added")
        
        # Step 1: Create temporary staging tables (non-partitioned) to import data first
        logger.info("=" * 60)
        logger.info("Step 1: Creating temporary staging tables...")
        logger.info("=" * 60)
        
        try:
            # Create temporary staging table for master (same structure but not partitioned)
            local_cur.execute("""
                CREATE TEMP TABLE parcels_master_staging (
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
                    source_gid            INTEGER
                );
            """)
            
            # Create temporary staging table for simplified
            local_cur.execute("""
                CREATE TEMP TABLE parcels_simplified_staging (
                    parcel_uuid     UUID NOT NULL,
                    geom            geometry(MultiPolygon, 4326) NOT NULL,
                    label_point     geometry(Point, 4326) NOT NULL,
                    state_code      TEXT NOT NULL,
                    district_code   TEXT NOT NULL,
                    survey_num      TEXT
                );
            """)
            
            local_conn.commit()
            logger.info("Temporary staging tables created successfully")
        except Exception as e:
            logger.error(f"Error creating staging tables: {e}")
            local_conn.rollback()
            raise
        
        # Check if data already exists in local database
        # Build local WHERE clause for checking existing records
        local_district_filters = []
        local_district_params = []
        for district_code, district_name, _ in districts:
            local_district_filters.append('(district_code = %s AND district_name = %s)')
            local_district_params.extend([district_code, district_name])
        
        local_where_district_filter = ' OR '.join(local_district_filters)
        
        local_cur.execute(f"""
            SELECT COUNT(*) 
            FROM parcels_master
            WHERE state_code = %s
              AND ({local_where_district_filter});
        """, [state_code_upper] + local_district_params)
        
        existing_count = local_cur.fetchone()[0]
        if existing_count > 0:
            logger.warning(f"WARNING: {existing_count:,} parcels already exist in local database!")
            logger.info("Options:")
            logger.info("  1. Skip existing records (recommended) - only migrate new data")
            logger.info("  2. Delete existing and re-import - delete all existing data and import fresh")
            logger.info("  3. Create duplicates - migrate all data again (will create duplicates)")
            logger.info("  4. Cancel migration")
            response = input("Choose option (1/2/3/4): ").strip()
            
            if response == '4':
                logger.info("Migration cancelled")
                return
            elif response == '2':
                # Delete existing data
                logger.info(f"Deleting {existing_count:,} existing parcels...")
                local_cur.execute(f"""
                    DELETE FROM parcels_simplified
                    WHERE state_code = %s
                      AND ({local_where_district_filter});
                """, [state_code_upper] + local_district_params)
                simplified_deleted = local_cur.rowcount
                
                local_cur.execute(f"""
                    DELETE FROM parcels_master
                    WHERE state_code = %s
                      AND ({local_where_district_filter});
                """, [state_code_upper] + local_district_params)
                master_deleted = local_cur.rowcount
                
                local_conn.commit()
                logger.info(f"Deleted {master_deleted:,} rows from parcels_master")
                logger.info(f"Deleted {simplified_deleted:,} rows from parcels_simplified")
                skip_existing = False
            elif response == '3':
                skip_existing = False
            else:
                skip_existing = True
        else:
            skip_existing = False
        
        # Get already migrated source_gids if skipping
        already_migrated_gids = set()
        if skip_existing:
            local_cur.execute(f"""
                SELECT DISTINCT source_gid
                FROM parcels_master
                WHERE state_code = %s
                  AND ({local_where_district_filter})
                  AND source_gid IS NOT NULL;
            """, [state_code_upper] + local_district_params)
            already_migrated_gids = {row[0] for row in local_cur.fetchall()}
            logger.info(f"Found {len(already_migrated_gids):,} already migrated records (will be skipped)")
        
        # Recalculate total if skipping
        if skip_existing and already_migrated_gids:
            gid_placeholders = ','.join(['%s'] * len(already_migrated_gids))
            neon_cur.execute(f"""
                SELECT COUNT(*) 
                FROM cadastrals
                WHERE "State_Code" = %s
                  AND ({where_district_filter})
                  AND gid NOT IN ({gid_placeholders})
                  AND geom IS NOT NULL
                  AND "State_Code" IS NOT NULL
                  AND "District_Code" IS NOT NULL
                  AND "District_Name" IS NOT NULL
                  AND "Survey_Number" IS NOT NULL;
            """, [state_code_lower] + district_params + list(already_migrated_gids))
            total_count = neon_cur.fetchone()[0]
            logger.info(f"Total parcels to migrate (excluding existing): {total_count:,}")
        
        # Migration loop
        offset = 0
        total_inserted_master = 0
        total_inserted_simplified = 0
        
        # Insert into staging table first (not partitioned)
        insert_master_sql = """
        INSERT INTO parcels_master_staging 
        (geom, label_point, state, state_code, district_code, district_name, 
         sub_district_name, village_name, survey_num, source_gid)
        VALUES (
            ST_Transform(ST_SetSRID(ST_GeomFromEWKB(%s), 32643), 4326),
            ST_PointOnSurface(ST_Transform(ST_SetSRID(ST_GeomFromEWKB(%s), 32643), 4326)),
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        """
        
        insert_simplified_sql = """
        INSERT INTO parcels_simplified
        (parcel_uuid, geom, label_point, state_code, district_code, survey_num)
        VALUES (%s, ST_GeomFromEWKB(%s), ST_GeomFromEWKB(%s), %s, %s, %s)
        ON CONFLICT (state_code, district_code, parcel_uuid) DO NOTHING
        """
        
        # Build WHERE clause for Neon cadastrals query
        where_clause = f"""
            WHERE "State_Code" = %s
              AND ({where_district_filter})
              AND geom IS NOT NULL
              AND "State_Code" IS NOT NULL
              AND "District_Code" IS NOT NULL
              AND "District_Name" IS NOT NULL
              AND "Survey_Number" IS NOT NULL
        """
        
        if skip_existing and already_migrated_gids:
            gid_placeholders = ','.join(['%s'] * len(already_migrated_gids))
            where_clause += f" AND gid NOT IN ({gid_placeholders})"
        
        while offset < total_count:
            batch_end = min(offset + batch_size, total_count)
            logger.info(f"\nProcessing batch: {offset + 1} to {batch_end} of {total_count:,}...")
            
            # Build query parameters
            query_params = [state_code_lower] + district_params.copy()
            if skip_existing and already_migrated_gids:
                query_params.extend(list(already_migrated_gids))
            query_params.extend([batch_size, offset])
            
            # Fetch batch from Neon cadastrals table
            neon_cur.execute(f"""
                SELECT 
                    ST_AsEWKB(geom) as geom_wkb,
                    "State_Name",
                    "State_Code",
                    "District_Code",
                    "District_Name",
                    "Mandal_Name",
                    "Village_Name",
                    "Survey_Number",
                    gid
                FROM cadastrals
                {where_clause}
                ORDER BY gid
                LIMIT %s OFFSET %s;
            """, query_params)
            
            rows = neon_cur.fetchall()
            
            if not rows:
                logger.info(f"No more rows to process. Completed at offset {offset}")
                break
            
            # Prepare data for master table
            master_rows = []
            source_gids_batch = []
            
            for row in rows:
                geom_wkb, state_name, state_code_val, district_code_val, \
                district_name_val, mandal_name, village_name, survey_num, source_gid = row
                
                # Transform geometry and compute label point in database
                # We'll pass the WKB and let PostgreSQL do the transformation
                geom_wkb_bytes = geom_wkb.tobytes() if geom_wkb else None
                
                if geom_wkb_bytes:
                    # Master table row
                    master_rows.append((
                        psycopg2.Binary(geom_wkb_bytes),
                        psycopg2.Binary(geom_wkb_bytes),  # Same geometry for label_point calculation
                        str(state_name) if state_name else '',
                        str(state_code_val).upper() if state_code_val else '',
                        str(district_code_val) if district_code_val else '',
                        str(district_name_val) if district_name_val else '',
                        str(mandal_name) if mandal_name else None,
                        str(village_name) if village_name else None,
                        str(survey_num) if survey_num else '',
                        int(source_gid) if source_gid else None
                    ))
                    source_gids_batch.append(int(source_gid) if source_gid else None)
            
            # Batch insert into staging table
            if master_rows:
                try:
                    execute_batch(local_cur, insert_master_sql, master_rows, page_size=batch_size)
                    total_inserted_master += len(master_rows)
                    logger.info(f"Inserted {len(master_rows)} rows into staging (total: {total_inserted_master:,})")
                except Exception as e:
                    logger.error(f"Error inserting into staging table: {e}")
                    local_conn.rollback()
                    raise
            
            # Also insert into simplified staging table
            if source_gids_batch:
                # Fetch UUIDs from staging table
                source_gids_tuple = tuple([gid for gid in source_gids_batch if gid is not None])
                
                if source_gids_tuple:
                    gid_placeholders = ','.join(['%s'] * len(source_gids_tuple))
                    local_cur.execute(f"""
                        SELECT DISTINCT ON (source_gid) 
                               parcel_uuid, source_gid, state_code, district_code, survey_num
                        FROM parcels_master_staging
                        WHERE source_gid IN ({gid_placeholders})
                        ORDER BY source_gid, created_at DESC;
                    """, list(source_gids_tuple))
                    
                    uuid_rows = local_cur.fetchall()
                    
                    # Fetch geometries from staging
                    parcel_uuids = [row[0] for row in uuid_rows]
                    if parcel_uuids:
                        uuid_placeholders = ','.join(['%s'] * len(parcel_uuids))
                        local_cur.execute(f"""
                            SELECT parcel_uuid, ST_AsEWKB(geom), ST_AsEWKB(label_point)
                            FROM parcels_master_staging
                            WHERE parcel_uuid IN ({uuid_placeholders});
                        """, parcel_uuids)
                        
                        geom_lookup = {}
                        for uuid, geom_wkb, label_point_wkb in local_cur.fetchall():
                            geom_lookup[uuid] = (geom_wkb, label_point_wkb)
                        
                        # Prepare simplified rows for staging
                        simplified_rows = []
                        for parcel_uuid, source_gid, state_code_val, district_code_val, survey_num in uuid_rows:
                            if parcel_uuid in geom_lookup:
                                geom_wkb, label_point_wkb = geom_lookup[parcel_uuid]
                                simplified_rows.append((
                                    parcel_uuid,
                                    psycopg2.Binary(geom_wkb.tobytes()),
                                    psycopg2.Binary(label_point_wkb.tobytes()),
                                    str(state_code_val),
                                    str(district_code_val),
                                    str(survey_num) if survey_num else None
                                ))
                        
                        # Insert into simplified staging
                        if simplified_rows:
                            insert_simplified_staging_sql = """
                            INSERT INTO parcels_simplified_staging
                            (parcel_uuid, geom, label_point, state_code, district_code, survey_num)
                            VALUES (%s, ST_GeomFromEWKB(%s), ST_GeomFromEWKB(%s), %s, %s, %s)
                            """
                            try:
                                execute_batch(local_cur, insert_simplified_staging_sql, simplified_rows, page_size=batch_size)
                                total_inserted_simplified += len(simplified_rows)
                                logger.info(f"Inserted {len(simplified_rows)} rows into simplified staging (total: {total_inserted_simplified:,})")
                            except Exception as e:
                                logger.error(f"Error inserting into simplified staging: {e}")
                                local_conn.rollback()
                                raise
            
            local_conn.commit()
            offset += len(rows)
            
            # Progress update
            progress = (offset / total_count) * 100 if total_count > 0 else 0
            logger.info(f"Progress: {progress:.1f}% ({offset:,}/{total_count:,})")
        
        logger.info("\n" + "=" * 60)
        logger.info("Step 2: Data Import Complete!")
        logger.info("=" * 60)
        logger.info(f"Total rows imported to staging: {total_inserted_master:,}")
        logger.info(f"Total simplified rows imported: {total_inserted_simplified:,}")
        
        # Step 3: Create partitions and move data
        logger.info("\n" + "=" * 60)
        logger.info("Step 3: Creating partitions and moving data...")
        logger.info("=" * 60)
        
        state_part_name = f"parcels_master_{state_code_upper.lower()}"
        simplified_state_part = f"parcels_simplified_{state_code_upper.lower()}"
        
        try:
            # Create state partition
            local_cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {state_part_name} 
                PARTITION OF parcels_master
                FOR VALUES IN (%s)
                PARTITION BY LIST (district_code);
            """, (state_code_upper,))
            logger.info(f"Created state partition: {state_part_name}")
            
            # Create district partitions and move data
            # Group districts by district_code to avoid creating duplicate partitions
            districts_by_code = {}
            for district_code, district_name, count in districts:
                if district_code not in districts_by_code:
                    districts_by_code[district_code] = []
                districts_by_code[district_code].append((district_code, district_name, count))
            
            for district_code, district_list in districts_by_code.items():
                district_part_name = f"{state_part_name}_{district_code}"
                
                # Create partition (only once per district_code)
                local_cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {district_part_name}
                    PARTITION OF {state_part_name}
                    FOR VALUES IN (%s);
                """, (district_code,))
                
                # Move data from staging to partition
                # Filter by both district_code AND district_name to get correct records
                # Use ON CONFLICT DO NOTHING to handle any duplicate UUIDs
                district_names = [d[1] for d in district_list]
                placeholders = ','.join(['%s'] * len(district_names))
                
                local_cur.execute(f"""
                    INSERT INTO {district_part_name}
                    SELECT * FROM parcels_master_staging
                    WHERE state_code = %s 
                      AND district_code = %s
                      AND district_name IN ({placeholders})
                    ON CONFLICT (state_code, district_code, parcel_uuid) DO NOTHING;
                """, [state_code_upper, district_code] + district_names)
                
                moved_count = local_cur.rowcount
                
                # Create indexes
                local_cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS {district_part_name}_geom_idx
                    ON {district_part_name} USING GIST (geom);
                """)
                
                local_cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS {district_part_name}_state_district_idx
                    ON {district_part_name} (state_code, district_code);
                """)
                
                logger.info(f"  Created partition {district_part_name} and moved {moved_count:,} rows")
            
            # Same for simplified table
            local_cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {simplified_state_part} 
                PARTITION OF parcels_simplified
                FOR VALUES IN (%s)
                PARTITION BY LIST (district_code);
            """, (state_code_upper,))
            logger.info(f"Created state partition: {simplified_state_part}")
            
            # Use the same grouping for simplified table
            for district_code, district_list in districts_by_code.items():
                simplified_district_part = f"{simplified_state_part}_{district_code}"
                
                # Create partition (only once per district_code)
                local_cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {simplified_district_part}
                    PARTITION OF {simplified_state_part}
                    FOR VALUES IN (%s);
                """, (district_code,))
                
                # Move data from staging to partition
                # Simplified table doesn't have district_name, so we need to join with master staging
                # or filter by parcel_uuid from master staging
                # Get parcel_uuids from master staging for these districts
                district_names = [d[1] for d in district_list]
                placeholders = ','.join(['%s'] * len(district_names))
                
                # First get UUIDs from master staging for these districts
                local_cur.execute(f"""
                    SELECT parcel_uuid FROM parcels_master_staging
                    WHERE state_code = %s 
                      AND district_code = %s
                      AND district_name IN ({placeholders});
                """, [state_code_upper, district_code] + district_names)
                
                uuid_rows = local_cur.fetchall()
                if uuid_rows:
                    uuid_list = [row[0] for row in uuid_rows]
                    uuid_placeholders = ','.join(['%s'] * len(uuid_list))
                    
                    local_cur.execute(f"""
                        INSERT INTO {simplified_district_part}
                        SELECT * FROM parcels_simplified_staging
                        WHERE state_code = %s 
                          AND district_code = %s
                          AND parcel_uuid IN ({uuid_placeholders})
                        ON CONFLICT (state_code, district_code, parcel_uuid) DO NOTHING;
                    """, [state_code_upper, district_code] + uuid_list)
                else:
                    moved_count = 0
                
                moved_count = local_cur.rowcount
                
                # Create indexes
                local_cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS {simplified_district_part}_geom_idx
                    ON {simplified_district_part} USING GIST (geom);
                """)
                
                local_cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS {simplified_district_part}_state_district_idx
                    ON {simplified_district_part} (state_code, district_code);
                """)
                
                moved_count = local_cur.rowcount
                logger.info(f"  Created partition {simplified_district_part} and moved {moved_count:,} rows")
            
            local_conn.commit()
            logger.info("\n" + "=" * 60)
            logger.info("Migration Complete!")
            logger.info("=" * 60)
            logger.info(f"State: {state_code_upper}")
            logger.info(f"Districts: {', '.join([d[1] for d in districts])}")
            logger.info(f"Total rows in parcels_master: {total_inserted_master:,}")
            logger.info(f"Total rows in parcels_simplified: {total_inserted_simplified:,}")
            logger.info("All partitions created and data moved successfully!")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error creating partitions or moving data: {e}")
            import traceback
            traceback.print_exc()
            local_conn.rollback()
            raise
        
        neon_cur.close()
        local_cur.close()
        neon_conn.close()
        local_conn.close()
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Migrate data from Neon cadastrals table to local database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (recommended)
  python migrate_neon_to_local.py
  
  # With custom batch size
  python migrate_neon_to_local.py --batch-size=5000
        """
    )
    parser.add_argument('--batch-size', type=int, default=2000,
                       help='Number of rows to process per batch (default: 2000)')
    
    args = parser.parse_args()
    
    migrate_data(batch_size=args.batch_size)


if __name__ == '__main__':
    main()
