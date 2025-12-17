#!/usr/bin/env python3
"""
Migrate Data from Neon cadastrals table to Partitioned Tables

Interactive migration script that allows selective migration by state and district.

This script:
1. Queries database for available states
2. Prompts user to select a state
3. Queries districts in selected state
4. Prompts user to select district(s) or all
5. Transforms geometry: EPSG:32643 → EPSG:4326
6. Maps column names: PascalCase → snake_case
7. Computes label_points using ST_PointOnSurface
8. Inserts into partitioned tables in batches

Usage:
    # Interactive mode (recommended)
    python migrate_neon_data.py
    
    # With custom batch size
    python migrate_neon_data.py --batch-size=500
    
    # Non-interactive mode (for automation)
    python migrate_neon_data.py --state-code=ka --district-code=526 526 --batch-size=1000
"""

import argparse
import sys
import logging
import psycopg2
from psycopg2.extras import execute_batch
from psycopg2 import sql
import time

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


def pre_create_partitions(conn, state_code, district_code):
    """Pre-create partitions for a state/district combination."""
    cur = conn.cursor()
    
    try:
        state_code_str = str(state_code).lower()
        district_code_str = str(district_code)
        state_part_name = f'parcels_master_neon_{state_code_str}'
        district_part_name = f'{state_part_name}_{district_code_str}'
        
        # Check if state partition exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = %s
            );
        """, (state_part_name,))
        
        state_exists = cur.fetchone()[0]
        
        if not state_exists:
            cur.execute(sql.SQL("""
                CREATE TABLE {} PARTITION OF parcels_master_neon
                FOR VALUES IN ({})
                PARTITION BY LIST (district_code);
            """).format(
                sql.Identifier(state_part_name),
                sql.Literal(state_code_str.upper())
            ))
            conn.commit()
        
        # Check if district partition exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = %s
            );
        """, (district_part_name,))
        
        district_exists = cur.fetchone()[0]
        
        if not district_exists:
            cur.execute(sql.SQL("""
                CREATE TABLE {} PARTITION OF {}
                FOR VALUES IN ({});
            """).format(
                sql.Identifier(district_part_name),
                sql.Identifier(state_part_name),
                sql.Literal(district_code_str)
            ))
            
            # Create indexes
            cur.execute(sql.SQL("""
                CREATE INDEX IF NOT EXISTS {} ON {} USING GIST (geom);
            """).format(
                sql.Identifier(district_part_name + '_geom_idx'),
                sql.Identifier(district_part_name)
            ))
            
            cur.execute(sql.SQL("""
                CREATE INDEX IF NOT EXISTS {} ON {} (state_code, district_code);
            """).format(
                sql.Identifier(district_part_name + '_state_district_idx'),
                sql.Identifier(district_part_name)
            ))
            
            conn.commit()
        
        # Same for simplified table
        state_part_simplified = f'parcels_simplified_neon_{state_code_str}'
        district_part_simplified = f'{state_part_simplified}_{district_code_str}'
        
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = %s
            );
        """, (state_part_simplified,))
        
        if not cur.fetchone()[0]:
            cur.execute(sql.SQL("""
                CREATE TABLE {} PARTITION OF parcels_simplified_neon
                FOR VALUES IN ({})
                PARTITION BY LIST (district_code);
            """).format(
                sql.Identifier(state_part_simplified),
                sql.Literal(state_code_str.upper())
            ))
            conn.commit()
        
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = %s
            );
        """, (district_part_simplified,))
        
        if not cur.fetchone()[0]:
            cur.execute(sql.SQL("""
                CREATE TABLE {} PARTITION OF {}
                FOR VALUES IN ({});
            """).format(
                sql.Identifier(district_part_simplified),
                sql.Identifier(state_part_simplified),
                sql.Literal(district_code_str)
            ))
            
            cur.execute(sql.SQL("""
                CREATE INDEX IF NOT EXISTS {} ON {} USING GIST (geom);
            """).format(
                sql.Identifier(district_part_simplified + '_geom_idx'),
                sql.Identifier(district_part_simplified)
            ))
            
            cur.execute(sql.SQL("""
                CREATE INDEX IF NOT EXISTS {} ON {} (state_code, district_code);
            """).format(
                sql.Identifier(district_part_simplified + '_state_district_idx'),
                sql.Identifier(district_part_simplified)
            ))
            
            conn.commit()
        
    except Exception as e:
        logger.error(f"Error pre-creating partitions: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()


def get_available_states(conn):
    """Query and return available states with counts."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT 
            "State_Code",
            "State_Name",
            COUNT(*) as parcel_count
        FROM cadastrals
        WHERE "State_Code" IS NOT NULL AND "State_Name" IS NOT NULL
        GROUP BY "State_Code", "State_Name"
        ORDER BY parcel_count DESC;
    """)
    return cur.fetchall()


def get_districts_for_state(conn, state_code):
    """Query and return districts for a given state with counts."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT 
            "District_Code",
            "District_Name",
            COUNT(*) as parcel_count
        FROM cadastrals
        WHERE "State_Code" = %s
          AND "District_Code" IS NOT NULL
          AND "District_Name" IS NOT NULL
        GROUP BY "District_Code", "District_Name"
        ORDER BY parcel_count DESC;
    """, (state_code,))
    return cur.fetchall()


def interactive_selection(conn):
    """Interactive selection of state and districts."""
    print("\n" + "=" * 60)
    print("Neon Database Migration - Interactive Selection")
    print("=" * 60)
    
    # Get available states
    states = get_available_states(conn)
    
    if not states:
        print("No states found in database!")
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
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(states):
                selected_state_code, selected_state_name, _ = states[choice_idx]
                break
            else:
                print(f"Please enter a number between 1 and {len(states)}")
        except ValueError:
            print("Please enter a valid number or 'q' to quit")
        except KeyboardInterrupt:
            print("\n\nMigration cancelled by user")
            return None, None
    
    print(f"\nSelected State: {selected_state_name} ({selected_state_code})")
    
    # Get districts for selected state
    districts = get_districts_for_state(conn, selected_state_code)
    
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
            
            # Handle "all" or the highest number (ALL districts option)
            if choice.lower() == 'all' or choice == str(len(districts) + 1):
                selected_districts = districts
                break
            else:
                # Parse comma-separated choices (handle spaces)
                choice_parts = [c.strip() for c in choice.split(',')]
                
                # Check if any choice is "all" or the ALL option number
                if any(c.lower() == 'all' or c == str(len(districts) + 1) for c in choice_parts):
                    print(f"Error: '{len(districts) + 1}' (ALL districts) cannot be combined with other selections.")
                    print(f"Please either select '{len(districts) + 1}' alone, or select individual districts (1-{len(districts)})")
                    continue
                
                # Convert to integers and validate
                try:
                    choices = [int(c) - 1 for c in choice_parts if c]
                except ValueError:
                    print(f"Error: Invalid input. Please enter numbers between 1 and {len(districts)}, or '{len(districts) + 1}' for ALL")
                    continue
                
                # Validate range
                if all(0 <= c < len(districts) for c in choices):
                    # Remove duplicates while preserving order
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
                    print(f"Please enter numbers between 1 and {len(districts)}, or '{len(districts) + 1}' for ALL")
        except ValueError:
            print(f"Error: Invalid input. Please enter numbers between 1 and {len(districts)}, or '{len(districts) + 1}' for ALL")
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
    
    confirm = input("\nProceed with migration? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("Migration cancelled")
        return None, None
    
    return selected_state_code, selected_districts


def migrate_data(batch_size=1000, state_code=None, districts=None):
    """Migrate data from cadastrals to partitioned tables."""
    conn_str = get_neon_connection_string()
    
    logger.info("=" * 60)
    logger.info("Starting Neon Data Migration")
    logger.info("=" * 60)
    
    try:
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        
        # Interactive selection if not provided
        if state_code is None or districts is None:
            result = interactive_selection(conn)
            if result == (None, None):
                logger.info("Migration cancelled by user")
                return
            state_code, districts = result
        
        # Store original state_code (lowercase) for queries, uppercase version for inserts
        state_code_lower = state_code.lower() if state_code else None
        state_code_upper = state_code.upper() if state_code else None
        
        # Pre-create partitions for selected districts
        logger.info("\nPre-creating partitions...")
        for district_code, district_name, _ in districts:
            pre_create_partitions(conn, state_code, district_code)
        logger.info("Partitions pre-created")
        
        # Calculate total count for selected districts
        # Need to match by both district_code AND district_name since codes can be duplicated
        district_filters = []
        district_params = []
        for district_code, district_name, _ in districts:
            district_filters.append('("District_Code" = %s AND "District_Name" = %s)')
            district_params.extend([district_code, district_name])
        
        where_district_filter = ' OR '.join(district_filters)
        
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM cadastrals
            WHERE "State_Code" = %s
              AND ({where_district_filter})
              AND geom IS NOT NULL
              AND "Survey_Number" IS NOT NULL;
        """, [state_code_lower] + district_params)
        
        total_count = cur.fetchone()[0]
        logger.info(f"Total parcels to migrate: {total_count:,}")
        
        if total_count == 0:
            logger.warning("No parcels found matching criteria!")
            return
        
        # Check if data already exists (match by district_code and district_name)
        district_exists_filters = []
        district_exists_params = []
        for district_code, district_name, _ in districts:
            district_exists_filters.append('(district_code = %s AND district_name = %s)')
            district_exists_params.extend([district_code, district_name])
        
        where_exists_filter = ' OR '.join(district_exists_filters)
        
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM parcels_master_neon
            WHERE state_code = %s
              AND ({where_exists_filter});
        """, [state_code_upper] + district_exists_params)
        
        existing_count = cur.fetchone()[0]
        logger.info(f"Existing records check: {existing_count:,} records already exist")
        
        if existing_count > 0:
            logger.warning(f"WARNING: {existing_count:,} parcels already exist in parcels_master_neon for selected state/districts!")
            logger.info("Options:")
            logger.info("  1. Skip existing records (recommended) - only migrate new data")
            logger.info("  2. Create duplicates - migrate all data again (will create duplicates)")
            logger.info("  3. Cancel migration")
            response = input("Choose option (1/2/3): ").strip()
            
            if response == '3':
                logger.info("Migration cancelled")
                return
            elif response == '2':
                logger.warning("Proceeding with duplicate creation...")
                skip_existing = False
            else:
                logger.info("Skipping existing records - only migrating new data...")
                skip_existing = True
        else:
            skip_existing = False
        
        # Get list of already migrated source_gids if skipping
        already_migrated_gids = set()
        if skip_existing:
            cur.execute(f"""
                SELECT DISTINCT source_gid
                FROM parcels_master_neon
                WHERE state_code = %s
                  AND ({where_exists_filter})
                  AND source_gid IS NOT NULL;
            """, [state_code_upper] + district_exists_params)
            already_migrated_gids = {row[0] for row in cur.fetchall()}
            logger.info(f"Found {len(already_migrated_gids):,} already migrated records (will be skipped)")
        
        # Migrate data in batches
        offset = 0
        total_inserted_master = 0
        total_inserted_simplified = 0
        
        insert_master_sql = """
        INSERT INTO parcels_master_neon 
        (geom, label_point, state, state_code, district_code, district_name, 
         sub_district_name, village_name, survey_num, source_gid)
        VALUES (
            ST_GeomFromEWKB(%s),
            ST_PointOnSurface(ST_GeomFromEWKB(%s)),
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        """
        
        # Recalculate total count excluding already migrated if skipping
        if skip_existing and already_migrated_gids:
            gid_placeholders = ','.join(['%s'] * len(already_migrated_gids))
            cur.execute(f"""
                SELECT COUNT(*) 
                FROM cadastrals
                WHERE "State_Code" = %s
                  AND ({where_district_filter})
                  AND geom IS NOT NULL
                  AND "Survey_Number" IS NOT NULL
                  AND gid NOT IN ({gid_placeholders});
            """, [state_code] + district_params + list(already_migrated_gids))
            total_count = cur.fetchone()[0]
            logger.info(f"Total parcels to migrate (excluding existing): {total_count:,}")
        
        # Build WHERE clause for selected districts (match by code AND name)
        # Note: where_district_filter already has the placeholders, we just need to use it
        base_where_template = """
            WHERE "State_Code" = %s
              AND ({district_filter})
              AND geom IS NOT NULL
              AND "State_Code" IS NOT NULL
              AND "District_Code" IS NOT NULL
              AND "District_Name" IS NOT NULL
              AND "Survey_Number" IS NOT NULL
        """
        base_where = base_where_template.format(district_filter=where_district_filter)
        
        while offset < total_count:
            batch_end = min(offset + batch_size, total_count)
            logger.info(f"\nProcessing batch: {offset + 1} to {batch_end} of {total_count:,}...")
            
            # Build query parameters (state_code_lower for cadastrals table, state_code_upper for inserts)
            query_params = [state_code_lower] + district_params.copy()
            
            # Add filter to exclude already migrated records if skipping
            where_clause = base_where
            if skip_existing and already_migrated_gids:
                gid_placeholders = ','.join(['%s'] * len(already_migrated_gids))
                where_clause += f" AND gid NOT IN ({gid_placeholders})"
                query_params.extend(list(already_migrated_gids))
                if offset == 0:
                    logger.info(f"Excluding {len(already_migrated_gids):,} already-migrated gids from query")
            
            query_params.extend([batch_size, offset])
            
            # Debug logging for first batch
            if offset == 0:
                logger.debug(f"Query will use {len(query_params)} parameters")
                logger.debug(f"WHERE clause length: {len(where_clause)} chars")
            
            # Fetch batch from cadastrals with transformed geometry
            try:
                query_sql = f"""
                    SELECT 
                        gid,
                        "Survey_Number",
                        "Village_Name",
                        "Mandal_Name",
                        "District_Name",
                        "State_Name",
                        "State_Code",
                        "District_Code",
                        ST_AsEWKB(ST_Transform(geom, 4326)) as geom_4326
                    FROM cadastrals
                    {where_clause}
                    ORDER BY gid
                    LIMIT %s OFFSET %s;
                """
                
                # Verify parameter count matches placeholders
                expected_params = 1 + len(district_params)  # state_code + district pairs
                if skip_existing and already_migrated_gids:
                    expected_params += len(already_migrated_gids)
                expected_params += 2  # LIMIT and OFFSET
                
                if len(query_params) != expected_params:
                    logger.error(f"Parameter count mismatch! Expected {expected_params}, got {len(query_params)}")
                    logger.error(f"state_code: {state_code}, district_params length: {len(district_params)}, already_migrated: {len(already_migrated_gids) if skip_existing and already_migrated_gids else 0}")
                    raise Exception(f"Parameter count mismatch: expected {expected_params}, got {len(query_params)}")
                
                cur.execute(query_sql, query_params)
                
                rows = cur.fetchall()
                
                if not rows:
                    # Before breaking, verify there really are no more rows
                    # Build count query with same WHERE clause but no ORDER BY/LIMIT/OFFSET
                    # count_params should be everything except LIMIT and OFFSET (last 2 params)
                    count_params = query_params[:-2]
                    
                    # Build count WHERE clause - use the same where_clause (it doesn't contain ORDER BY/LIMIT/OFFSET)
                    # where_clause is just the WHERE part, ORDER BY/LIMIT/OFFSET are added in the query_sql
                    try:
                        # First, verify the count query works
                        count_query = f"""
                            SELECT COUNT(*) 
                            FROM cadastrals
                            {where_clause};
                        """
                        
                        # Debug: Log the actual query and params for first failure
                        if offset == 1000:  # First time we hit this
                            logger.error(f"DEBUG: Count query WHERE clause:\n{where_clause}")
                            logger.error(f"DEBUG: Count params: {count_params}")
                            logger.error(f"DEBUG: Count params count: {len(count_params)}")
                            # Count placeholders in WHERE clause
                            placeholder_count = where_clause.count('%s')
                            logger.error(f"DEBUG: Placeholders in WHERE clause: {placeholder_count}")
                            
                            # Try a direct test
                            logger.error(f"DEBUG: Testing count query directly...")
                            try:
                                test_count_params = [state_code_lower] + district_params
                                test_where = base_where_template.format(district_filter=where_district_filter)
                                cur.execute(f"SELECT COUNT(*) FROM cadastrals {test_where};", test_count_params)
                                test_count = cur.fetchone()[0]
                                logger.error(f"DEBUG: Direct test count: {test_count:,}")
                            except Exception as test_err:
                                logger.error(f"DEBUG: Direct test failed: {test_err}")
                        
                        cur.execute(count_query, count_params)
                        remaining_count = cur.fetchone()[0]
                        
                        if offset == 1000:
                            logger.error(f"DEBUG: Count query result: {remaining_count:,}")
                        
                        if remaining_count > offset:
                            logger.error(f"ERROR: Query returned no rows but {remaining_count:,} rows should remain!")
                            logger.error(f"Offset: {offset:,}, Remaining: {remaining_count:,}")
                            logger.error(f"Query params count: {len(query_params)}, Count params count: {len(count_params)}")
                            logger.error(f"Skip existing: {skip_existing}, Already migrated gids: {len(already_migrated_gids) if skip_existing and already_migrated_gids else 0}")
                            
                            # Debug: Try fetching with a small OFFSET to see if query works
                            test_params = count_params + [10, offset]  # LIMIT 10, same OFFSET
                            cur.execute(f"""
                                SELECT gid
                                FROM cadastrals
                                {where_clause}
                                ORDER BY gid
                                LIMIT %s OFFSET %s;
                            """, test_params)
                            test_rows = cur.fetchall()
                            logger.error(f"Test query (LIMIT 10, OFFSET {offset}) returned {len(test_rows)} rows")
                            
                            # Try with OFFSET 0 to see if it's an OFFSET issue
                            test_params_0 = count_params + [10, 0]
                            cur.execute(f"""
                                SELECT gid
                                FROM cadastrals
                                {where_clause}
                                ORDER BY gid
                                LIMIT %s OFFSET %s;
                            """, test_params_0)
                            test_rows_0 = cur.fetchall()
                            logger.error(f"Test query (LIMIT 10, OFFSET 0) returned {len(test_rows_0)} rows")
                            
                            if test_rows_0 and not test_rows:
                                logger.error(f"This suggests the issue is with OFFSET {offset} - query works at OFFSET 0 but not at OFFSET {offset}")
                            
                            # Don't break, raise an error instead
                            raise Exception(f"Query returned no rows but {remaining_count:,} rows should remain at offset {offset}")
                        else:
                            logger.info(f"No more rows to process. Completed at offset {offset:,} (total available: {remaining_count:,})")
                    except Exception as count_error:
                        logger.warning(f"Could not verify remaining count: {count_error}")
                        import traceback
                        logger.warning(traceback.format_exc())
                        logger.info(f"Stopping migration at offset {offset} (no rows returned)")
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching batch at offset {offset}: {e}")
                logger.error(f"Query params: {query_params}")
                logger.error(f"WHERE clause: {where_clause}")
                import traceback
                traceback.print_exc()
                raise
            
            # Prepare data for master table
            master_rows = []
            for row in rows:
                gid, survey_num, village_name, mandal_name, district_name, \
                state_name, state_code, district_code, geom_wkb = row
                
                # geom_wkb is already in 4326, use it for both geom and label_point computation
                master_rows.append((
                    psycopg2.Binary(geom_wkb.tobytes()),  # geom (already 4326)
                    psycopg2.Binary(geom_wkb.tobytes()),  # label_point source (same geom)
                    str(state_name) if state_name else '',
                    state_code_upper if state_code else '',
                    str(district_code) if district_code else '',
                    str(district_name) if district_name else '',
                    str(mandal_name) if mandal_name else None,
                    str(village_name) if village_name else None,
                    str(survey_num) if survey_num else '',
                    int(gid)
                ))
            
            # Batch insert into master
            try:
                execute_batch(cur, insert_master_sql, master_rows, page_size=batch_size)
                total_inserted_master += len(master_rows)
                logger.info(f"Inserted {len(master_rows)} rows into parcels_master_neon (total: {total_inserted_master:,})")
            except Exception as e:
                logger.error(f"Error inserting into parcels_master_neon: {e}")
                conn.rollback()
                raise
            
            # Fetch UUIDs for simplified table (only for records we just inserted)
            # Use DISTINCT ON to get only the most recent record per source_gid
            # This prevents duplicates from previous migrations
            try:
                # Get the source_gids we just inserted
                inserted_source_gids = tuple([r[9] for r in master_rows])
                
                # Fetch UUIDs - use DISTINCT ON to get only one record per source_gid (most recent)
                cur.execute("""
                    SELECT DISTINCT ON (source_gid) 
                           parcel_uuid, source_gid, state_code, district_code, survey_num
                    FROM parcels_master_neon
                    WHERE source_gid IN %s
                    ORDER BY source_gid, created_at DESC;
                """, (inserted_source_gids,))
                
                uuid_rows = cur.fetchall()
                
                if len(uuid_rows) != len(master_rows):
                    logger.warning(f"Warning: Expected {len(master_rows)} UUIDs but got {len(uuid_rows)}")
                    # This might happen if some source_gids already existed, which is okay
                
            except Exception as e:
                logger.error(f"Error fetching UUIDs: {e}")
                conn.rollback()
                raise
            
            # Prepare data for simplified table
            # OPTIMIZATION: Fetch all geometries in a single batch query instead of one-by-one
            simplified_rows = []
            if uuid_rows:
                try:
                    # Build a single query to fetch all geometries at once
                    parcel_uuids = [row[0] for row in uuid_rows]
                    uuid_placeholders = ','.join(['%s'] * len(parcel_uuids))
                    
                    cur.execute(f"""
                        SELECT parcel_uuid, ST_AsEWKB(geom), ST_AsEWKB(label_point)
                        FROM parcels_master_neon
                        WHERE parcel_uuid IN ({uuid_placeholders});
                    """, parcel_uuids)
                    
                    # Create a lookup dictionary for fast access
                    geom_lookup = {}
                    for uuid, geom_wkb, label_point_wkb in cur.fetchall():
                        geom_lookup[uuid] = (geom_wkb, label_point_wkb)
                    
                    # Build simplified_rows using the lookup
                    for parcel_uuid, source_gid, state_code, district_code, survey_num in uuid_rows:
                        if parcel_uuid in geom_lookup:
                            geom_wkb, label_point_wkb = geom_lookup[parcel_uuid]
                            simplified_rows.append((
                                parcel_uuid,
                                psycopg2.Binary(geom_wkb.tobytes()),
                                psycopg2.Binary(label_point_wkb.tobytes()),
                                str(state_code),
                                str(district_code),
                                str(survey_num) if survey_num else None
                            ))
                        else:
                            logger.warning(f"Geometry not found for parcel_uuid {parcel_uuid}")
                            
                except Exception as e:
                    logger.error(f"Error batch-fetching geometries: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fallback: skip simplified table insert for this batch
                    simplified_rows = []
            
            # Batch insert into simplified (with ON CONFLICT to skip duplicates)
            if simplified_rows:
                try:
                    # Check which UUIDs already exist to avoid duplicates
                    existing_uuids = set()
                    if simplified_rows:
                        parcel_uuids = tuple([row[0] for row in simplified_rows])
                        cur.execute("""
                            SELECT parcel_uuid
                            FROM parcels_simplified_neon
                            WHERE parcel_uuid IN %s;
                        """, (parcel_uuids,))
                        existing_uuids = {row[0] for row in cur.fetchall()}
                    
                    # Filter out rows that already exist
                    new_simplified_rows = [row for row in simplified_rows if row[0] not in existing_uuids]
                    
                    if existing_uuids:
                        logger.info(f"Skipping {len(existing_uuids)} already existing records in parcels_simplified_neon")
                    
                    if new_simplified_rows:
                        insert_simplified_sql = """
                        INSERT INTO parcels_simplified_neon
                        (parcel_uuid, geom, label_point, state_code, district_code, survey_num)
                        VALUES (%s, ST_GeomFromEWKB(%s), ST_GeomFromEWKB(%s), %s, %s, %s)
                        ON CONFLICT (state_code, district_code, parcel_uuid) DO NOTHING
                        """
                        execute_batch(cur, insert_simplified_sql, new_simplified_rows, page_size=batch_size)
                        total_inserted_simplified += len(new_simplified_rows)
                        logger.info(f"Inserted {len(new_simplified_rows)} rows into parcels_simplified_neon (total: {total_inserted_simplified:,})")
                    else:
                        logger.info("All records already exist in parcels_simplified_neon, skipping insert")
                        
                except Exception as e:
                    logger.error(f"Error inserting into parcels_simplified_neon: {e}")
                    conn.rollback()
                    raise
            
            conn.commit()
            offset += len(rows)  # Use actual rows processed, not batch_size
            
            # Progress update
            progress = (offset / total_count) * 100 if total_count > 0 else 0
            logger.info(f"Progress: {progress:.1f}% ({offset:,}/{total_count:,})")
            
            # Small delay to avoid overwhelming the database
            time.sleep(0.1)
        
        logger.info("\n" + "=" * 60)
        logger.info("Migration Complete!")
        logger.info("=" * 60)
        logger.info(f"State: {state_code}")
        logger.info(f"Districts: {', '.join([d[1] for d in districts])}")
        logger.info(f"Total rows inserted into parcels_master_neon: {total_inserted_master:,}")
        logger.info(f"Total rows inserted into parcels_simplified_neon: {total_inserted_simplified:,}")
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


def main():
    parser = argparse.ArgumentParser(
        description='Migrate Neon cadastrals data to partitioned tables',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (recommended)
  python migrate_neon_data.py
  
  # With custom batch size
  python migrate_neon_data.py --batch-size=500
  
  # Non-interactive (for automation)
  python migrate_neon_data.py --state-code=ka --district-code=526 --batch-size=1000
        """
    )
    parser.add_argument('--batch-size', type=int, default=2000, 
                       help='Batch size for inserts (default: 1000)')
    parser.add_argument('--state-code', type=str, default=None,
                       help='State code to migrate (e.g., "ka"). If not provided, interactive selection.')
    parser.add_argument('--district-code', type=str, nargs='+', default=None,
                       help='District code(s) to migrate (e.g., "526"). If not provided, interactive selection.')
    
    args = parser.parse_args()
    
    # If state/district provided, use them; otherwise interactive
    districts = None
    if args.state_code and args.district_code:
        # Non-interactive mode
        conn_str = get_neon_connection_string()
        conn = psycopg2.connect(conn_str)
        districts = []
        for dist_code in args.district_code:
            cur = conn.cursor()
            cur.execute("""
                SELECT "District_Code", "District_Name", COUNT(*) 
                FROM cadastrals
                WHERE "State_Code" = %s AND "District_Code" = %s
                GROUP BY "District_Code", "District_Name";
            """, (args.state_code, dist_code))
            result = cur.fetchone()
            if result:
                districts.append(result)
            cur.close()
        conn.close()
        
        if not districts:
            logger.error(f"No districts found for state_code={args.state_code}, district_code={args.district_code}")
            sys.exit(1)
    
    migrate_data(batch_size=args.batch_size, state_code=args.state_code, districts=districts)


if __name__ == '__main__':
    main()

