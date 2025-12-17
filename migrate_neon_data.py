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
            choice = input(f"\nSelect district(s) (1-{len(districts) + 1}, comma-separated for multiple, or 'all'): ").strip().lower()
            if choice == 'q':
                return None, None
            
            if choice == 'all' or choice == str(len(districts) + 1):
                selected_districts = districts
                break
            else:
                # Parse comma-separated choices
                choices = [int(c.strip()) - 1 for c in choice.split(',')]
                if all(0 <= c < len(districts) for c in choices):
                    selected_districts = [districts[c] for c in choices]
                    break
                else:
                    print(f"Please enter numbers between 1 and {len(districts)}")
        except ValueError:
            print("Please enter valid numbers, 'all', or 'q' to quit")
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
        
        # Pre-create partitions for selected districts
        logger.info("\nPre-creating partitions...")
        for district_code, district_name, _ in districts:
            pre_create_partitions(conn, state_code, district_code)
        logger.info("Partitions pre-created")
        
        # Calculate total count for selected districts
        district_codes = [d[0] for d in districts]
        placeholders = ','.join(['%s'] * len(district_codes))
        
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM cadastrals
            WHERE "State_Code" = %s
              AND "District_Code" IN ({placeholders})
              AND geom IS NOT NULL
              AND "Survey_Number" IS NOT NULL;
        """, [state_code] + district_codes)
        
        total_count = cur.fetchone()[0]
        logger.info(f"Total parcels to migrate: {total_count:,}")
        
        if total_count == 0:
            logger.warning("No parcels found matching criteria!")
            return
        
        # Check if data already exists
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM parcels_master_neon
            WHERE state_code = %s
              AND district_code IN ({placeholders});
        """, [state_code] + district_codes)
        
        existing_count = cur.fetchone()[0]
        if existing_count > 0:
            logger.warning(f"WARNING: {existing_count:,} parcels already exist in parcels_master_neon for selected state/districts!")
            logger.warning("This migration will create duplicates. Continue anyway?")
            response = input("Continue? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                logger.info("Migration cancelled")
                return
        
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
        
        # Build WHERE clause for selected districts
        placeholders = ','.join(['%s'] * len(district_codes))
        where_clause = f"""
            WHERE "State_Code" = %s
              AND "District_Code" IN ({placeholders})
              AND geom IS NOT NULL
              AND "State_Code" IS NOT NULL
              AND "District_Code" IS NOT NULL
              AND "District_Name" IS NOT NULL
              AND "Survey_Number" IS NOT NULL
        """
        
        while offset < total_count:
            batch_end = min(offset + batch_size, total_count)
            logger.info(f"\nProcessing batch: {offset + 1} to {batch_end} of {total_count:,}...")
            
            # Fetch batch from cadastrals with transformed geometry
            cur.execute(f"""
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
            """, [state_code] + district_codes + [batch_size, offset])
            
            rows = cur.fetchall()
            
            if not rows:
                break
            
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
                    str(state_code).upper() if state_code else '',
                    str(district_code) if district_code else '',
                    str(district_name) if district_name else '',
                    str(mandal_name) if mandal_name else None,
                    str(village_name) if village_name else None,
                    str(survey_num) if survey_num else '',
                    int(gid)
                ))
            
            # Batch insert into master
            execute_batch(cur, insert_master_sql, master_rows, page_size=batch_size)
            total_inserted_master += len(master_rows)
            logger.info(f"Inserted {total_inserted_master} rows into parcels_master_neon")
            
            # Fetch UUIDs for simplified table (matching by source_gid)
            cur.execute("""
                SELECT parcel_uuid, source_gid, state_code, district_code, survey_num
                FROM parcels_master_neon
                WHERE source_gid IN %s
                ORDER BY source_gid;
            """, (tuple([r[9] for r in master_rows]),))
            
            uuid_rows = cur.fetchall()
            
            # Prepare data for simplified table
            simplified_rows = []
            for parcel_uuid, source_gid, state_code, district_code, survey_num in uuid_rows:
                # Find corresponding geometry from master
                cur.execute("""
                    SELECT ST_AsEWKB(geom), ST_AsEWKB(label_point)
                    FROM parcels_master_neon
                    WHERE parcel_uuid = %s;
                """, (parcel_uuid,))
                geom_row = cur.fetchone()
                
                if geom_row:
                    geom_wkb = geom_row[0]
                    label_point_wkb = geom_row[1]
                    
                    simplified_rows.append((
                        parcel_uuid,
                        psycopg2.Binary(geom_wkb.tobytes()),
                        psycopg2.Binary(label_point_wkb.tobytes()),
                        str(state_code),
                        str(district_code),
                        str(survey_num) if survey_num else None
                    ))
            
            # Batch insert into simplified
            insert_simplified_sql = """
            INSERT INTO parcels_simplified_neon
            (parcel_uuid, geom, label_point, state_code, district_code, survey_num)
            VALUES (%s, ST_GeomFromEWKB(%s), ST_GeomFromEWKB(%s), %s, %s, %s)
            """
            execute_batch(cur, insert_simplified_sql, simplified_rows, page_size=batch_size)
            total_inserted_simplified += len(simplified_rows)
            logger.info(f"Inserted {total_inserted_simplified} rows into parcels_simplified_neon")
            
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
    parser.add_argument('--batch-size', type=int, default=1000, 
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

