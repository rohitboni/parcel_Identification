#!/usr/bin/env python3
"""
Fix Partition Script

This script fixes partition creation issues by dropping and recreating
partitions with the correct primary key constraints.

The issue: When creating multi-level partitions (state -> district),
PostgreSQL requires that the primary key constraint includes all partitioning
columns. This script ensures partitions are created correctly.

Usage:
    python fix_partitions.py
"""

import os
import sys
import logging
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_db_config():
    """Get database configuration from environment variables."""
    config = {
        'host': os.getenv('DB_HOST', '127.0.0.1'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'parcels_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres')
    }
    return config


def drop_problematic_partitions(conn, table_name):
    """
    Drop any existing partitions that might have constraint issues.
    
    Args:
        conn: Database connection
        table_name: Name of the partitioned table ('parcels_master' or 'parcels_simplified')
    """
    cur = conn.cursor()
    
    try:
        # Find all partitions of the table using pg_inherits
        # This is more reliable than pattern matching
        cur.execute("""
            SELECT c.relname
            FROM pg_inherits i
            JOIN pg_class c ON i.inhrelid = c.oid
            JOIN pg_class p ON i.inhparent = p.oid
            WHERE p.relname = %s
            ORDER BY c.relname;
        """, (table_name,))
        
        partitions = cur.fetchall()
        
        if not partitions:
            logger.info(f"No existing partitions found for {table_name}")
            return
        
        logger.info(f"Found {len(partitions)} partitions for {table_name}")
        
        # Drop all partitions (CASCADE will handle dependencies)
        # Note: Need to drop child partitions first, then parent partitions
        # So we'll drop in reverse order (children first)
        partition_names = [row[0] for row in partitions]
        
        # Sort to drop deepest partitions first
        partition_names.sort(key=lambda x: x.count('_'), reverse=True)
        
        for partition_name in partition_names:
            try:
                logger.info(f"Dropping partition: {partition_name}")
                cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(partition_name)
                ))
            except Exception as e:
                logger.warning(f"Error dropping partition {partition_name}: {e}")
                conn.rollback()
                continue
        
        conn.commit()
        logger.info(f"Successfully dropped all partitions for {table_name}")
        
    except Exception as e:
        logger.error(f"Error dropping partitions: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()


def create_partitions_manually(conn, table_name, state_code, district_code):
    """
    Manually create partitions with correct structure.
    
    This function creates partitions in a way that ensures the primary key
    constraint is properly inherited, including all partitioning columns.
    
    Args:
        conn: Database connection
        table_name: Name of the partitioned table
        state_code: State code value
        district_code: District code value
    """
    cur = conn.cursor()
    
    try:
        state_code_str = str(state_code)
        district_code_str = str(district_code)
        state_part_name = f'{table_name}_{state_code_str.lower()}'
        district_part_name = f'{state_part_name}_{district_code_str}'
        
        # Step 1: Create state partition if it doesn't exist
        # Check if state partition exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = %s
            );
        """, (state_part_name,))
        
        state_exists = cur.fetchone()[0]
        
        if not state_exists:
            logger.info(f"Creating state partition: {state_part_name}")
            # Create state partition (partitioned by district_code)
            # Note: Intermediate partitions that are themselves partitioned
            # don't have their own primary key - they inherit from parent
            # The primary key constraint will be enforced on leaf partitions only
            try:
                cur.execute(sql.SQL("""
                    CREATE TABLE {} PARTITION OF {}
                    FOR VALUES IN ({})
                    PARTITION BY LIST (district_code);
                """).format(
                    sql.Identifier(state_part_name),
                    sql.Identifier(table_name),
                    sql.Literal(state_code_str)
                ))
                conn.commit()
                logger.info(f"Created state partition: {state_part_name}")
            except psycopg2.ProgrammingError as e:
                error_msg = str(e).lower()
                if 'constraint' in error_msg and 'partition' in error_msg:
                    # There might be an existing partition with wrong structure
                    logger.warning(f"Constraint error creating state partition, attempting to fix...")
                    # Try dropping and recreating
                    try:
                        cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                            sql.Identifier(state_part_name)
                        ))
                        conn.commit()
                        # Now try creating again
                        cur.execute(sql.SQL("""
                            CREATE TABLE {} PARTITION OF {}
                            FOR VALUES IN ({})
                            PARTITION BY LIST (district_code);
                        """).format(
                            sql.Identifier(state_part_name),
                            sql.Identifier(table_name),
                            sql.Literal(state_code_str)
                        ))
                        conn.commit()
                        logger.info(f"Successfully recreated state partition: {state_part_name}")
                    except Exception as e2:
                        logger.error(f"Failed to recreate partition: {e2}")
                        conn.rollback()
                        raise
                else:
                    conn.rollback()
                    raise
        else:
            # Check if the existing partition is correctly structured
            cur.execute("""
                SELECT relkind FROM pg_class WHERE relname = %s;
            """, (state_part_name,))
            result = cur.fetchone()
            if result and result[0] != 'p':  # 'p' means partitioned table
                logger.warning(f"State partition {state_part_name} exists but isn't partitioned correctly, dropping...")
                cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(state_part_name)
                ))
                conn.commit()
                # Recreate it
                cur.execute(sql.SQL("""
                    CREATE TABLE {} PARTITION OF {}
                    FOR VALUES IN ({})
                    PARTITION BY LIST (district_code);
                """).format(
                    sql.Identifier(state_part_name),
                    sql.Identifier(table_name),
                    sql.Literal(state_code_str)
                ))
                conn.commit()
                logger.info(f"Recreated state partition: {state_part_name}")
            else:
                logger.debug(f"State partition {state_part_name} already exists and is correctly structured")
        
        # Step 2: Create district partition if it doesn't exist
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = %s
            );
        """, (district_part_name,))
        
        district_exists = cur.fetchone()[0]
        
        if not district_exists:
            logger.info(f"Creating district partition: {district_part_name}")
            # Create district sub-partition
            cur.execute(sql.SQL("""
                CREATE TABLE {} PARTITION OF {}
                FOR VALUES IN ({});
            """).format(
                sql.Identifier(district_part_name),
                sql.Identifier(state_part_name),
                sql.Literal(district_code_str)
            ))
            
            # Create indexes on district partition
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
            logger.info(f"Created district partition: {district_part_name}")
        else:
            logger.debug(f"District partition {district_part_name} already exists")
            # Ensure indexes exist even if partition exists
            try:
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
            except Exception as e:
                logger.warning(f"Error creating indexes on {district_part_name}: {e}")
                conn.rollback()
        
    except Exception as e:
        logger.error(f"Error creating partitions: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()


def get_state_district_combinations(conn):
    """
    Query the database to find unique state_code/district_code combinations.
    This helps identify what partitions need to be created.
    
    Args:
        conn: Database connection
        
    Returns:
        List of (state_code, district_code) tuples
    """
    cur = conn.cursor()
    
    try:
        # Try to get combinations from parcels_master if it exists and has data
        # If not, fall back to known values
        cur.execute("""
            SELECT DISTINCT state_code, district_code
            FROM parcels_master
            LIMIT 100;
        """)
        results = cur.fetchall()
        
        if results:
            logger.info(f"Found {len(results)} state/district combinations in parcels_master")
            return [(str(row[0]), str(row[1])) for row in results]
        else:
            # Fall back to known Vellore values
            logger.info("No data found in parcels_master, using default Vellore values")
            return [('TN', 'VELLORE')]
            
    except psycopg2.Error as e:
        # Table might not exist or be empty, use defaults
        logger.info("Could not query parcels_master, using default Vellore values")
        return [('TN', 'VELLORE')]
    finally:
        cur.close()


def fix_parent_table_structure(conn, table_name):
    """
    Fix the parent table structure if it has incorrect primary key or partition key.
    
    This function checks if the table has the correct primary key (state_code, district_code, parcel_uuid)
    and partition key (state_code). If not, it fixes them.
    
    Args:
        conn: Database connection
        table_name: Name of the partitioned table
        
    Returns:
        True if structure is correct or was fixed, False otherwise
    """
    cur = conn.cursor()
    
    try:
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = %s
            );
        """, (table_name,))
        
        if not cur.fetchone()[0]:
            logger.error(f"Table {table_name} does not exist!")
            return False
        
        # Check primary key constraint
        cur.execute("""
            SELECT a.attname
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
            WHERE t.relname = %s
            AND c.contype = 'p'
            ORDER BY a.attnum;
        """, (table_name,))
        
        pk_columns = [row[0] for row in cur.fetchall()]
        
        logger.info(f"Table {table_name} current primary key columns: {pk_columns}")
        
        # Check partition key
        cur.execute("""
            SELECT a.attname
            FROM pg_partitioned_table pt
            JOIN pg_class t ON pt.partrelid = t.oid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(pt.partattrs)
            WHERE t.relname = %s
            ORDER BY a.attnum;
        """, (table_name,))
        
        partition_columns = [row[0] for row in cur.fetchall()]
        logger.info(f"Table {table_name} partition key columns: {partition_columns}")
        
        # Verify structure
        required_pk_columns = ['state_code', 'district_code', 'parcel_uuid']
        required_partition_column = 'state_code'
        
        pk_correct = pk_columns == required_pk_columns
        partition_correct = partition_columns == [required_partition_column]
        
        if pk_correct and partition_correct:
            logger.info(f"Table {table_name} structure is correct")
            return True
        
        # Structure needs fixing
        # Check if table is empty - if so, we can safely drop and recreate
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
            sql.Identifier(table_name)
        ))
        row_count = cur.fetchone()[0]
        
        if row_count > 0:
            logger.warning(f"Table {table_name} has incorrect structure and contains {row_count} rows!")
            logger.warning(f"  Primary key should be: {required_pk_columns}, found: {pk_columns}")
            logger.warning(f"  Partition key should be: [{required_partition_column}], found: {partition_columns}")
            logger.warning("Cannot automatically fix without dropping table (would lose data)")
            logger.warning("Please manually fix the table structure or migrate data first")
            return False
        else:
            # Table is empty, we can safely drop and recreate
            logger.warning(f"Table {table_name} has incorrect structure but is empty - will recreate")
            logger.info(f"Dropping and recreating {table_name} with correct structure...")
            
            # Drop the table (CASCADE will handle dependencies)
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                sql.Identifier(table_name)
            ))
            conn.commit()
            
            # Recreate with correct structure
            if table_name == 'parcels_master':
                cur.execute("""
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
                """)
            elif table_name == 'parcels_simplified':
                cur.execute("""
                    CREATE TABLE parcels_simplified (
                        parcel_uuid     UUID NOT NULL,
                        geom            geometry(MultiPolygon, 4326) NOT NULL,
                        label_point     geometry(Point, 4326) NOT NULL,
                        state_code      TEXT NOT NULL,
                        district_code   TEXT NOT NULL,
                        survey_num      TEXT,
                        PRIMARY KEY (state_code, district_code, parcel_uuid)
                    ) PARTITION BY LIST (state_code);
                """)
            
            # Recreate triggers
            if table_name == 'parcels_master':
                cur.execute("""
                    DROP TRIGGER IF EXISTS trg_create_master_partitions ON parcels_master;
                    CREATE TRIGGER trg_create_master_partitions
                    BEFORE INSERT ON parcels_master
                    FOR EACH ROW
                    EXECUTE FUNCTION create_master_partitions();
                """)
            elif table_name == 'parcels_simplified':
                cur.execute("""
                    DROP TRIGGER IF EXISTS trg_create_simplified_partitions ON parcels_simplified;
                    CREATE TRIGGER trg_create_simplified_partitions
                    BEFORE INSERT ON parcels_simplified
                    FOR EACH ROW
                    EXECUTE FUNCTION create_simplified_partitions();
                """)
            
            conn.commit()
            logger.info(f"Successfully recreated {table_name} with correct structure")
            return True
        
    except Exception as e:
        logger.error(f"Error checking table structure: {e}")
        return False
    finally:
        cur.close()


def fix_all_partitions():
    """Main function to fix partitions for both tables."""
    db_config = get_db_config()
    
    logger.info("Connecting to database...")
    logger.info(f"Host: {db_config['host']}, Database: {db_config['database']}")
    
    try:
        conn = psycopg2.connect(**db_config)
        
        # Check parent table structures first
        logger.info("Checking parent table structures...")
        master_ok = fix_parent_table_structure(conn, 'parcels_master')
        simplified_ok = fix_parent_table_structure(conn, 'parcels_simplified')
        
        if not master_ok or not simplified_ok:
            logger.error("Cannot proceed with partition creation - table structures are incorrect")
            logger.error("Please fix the table structures first by running create_tables.sql")
            logger.error("Note: This will require dropping and recreating the tables")
            return
        
        # Get state/district combinations (either from data or defaults)
        combinations = get_state_district_combinations(conn)
        
        if not combinations:
            # If we still don't have combinations, use defaults
            combinations = [('TN', 'VELLORE')]
        
        logger.info(f"Will create partitions for {len(combinations)} state/district combinations")
        
        logger.info("=" * 60)
        logger.info("Fixing partitions for parcels_master...")
        logger.info("=" * 60)
        
        # Temporarily disable trigger to avoid conflicts
        cur = conn.cursor()
        cur.execute("ALTER TABLE parcels_master DISABLE TRIGGER trg_create_master_partitions;")
        conn.commit()
        cur.close()
        
        # Drop problematic partitions for parcels_master
        drop_problematic_partitions(conn, 'parcels_master')
        
        # Create partitions for each state/district combination
        for state_code, district_code in combinations:
            create_partitions_manually(conn, 'parcels_master', state_code, district_code)
        
        # Re-enable trigger
        cur = conn.cursor()
        cur.execute("ALTER TABLE parcels_master ENABLE TRIGGER trg_create_master_partitions;")
        conn.commit()
        cur.close()
        
        logger.info("=" * 60)
        logger.info("Fixing partitions for parcels_simplified...")
        logger.info("=" * 60)
        
        # Temporarily disable trigger to avoid conflicts
        cur = conn.cursor()
        cur.execute("ALTER TABLE parcels_simplified DISABLE TRIGGER trg_create_simplified_partitions;")
        conn.commit()
        cur.close()
        
        # Drop problematic partitions for parcels_simplified
        drop_problematic_partitions(conn, 'parcels_simplified')
        
        # Create partitions for each state/district combination
        for state_code, district_code in combinations:
            create_partitions_manually(conn, 'parcels_simplified', state_code, district_code)
        
        # Re-enable trigger
        cur = conn.cursor()
        cur.execute("ALTER TABLE parcels_simplified ENABLE TRIGGER trg_create_simplified_partitions;")
        conn.commit()
        cur.close()
        
        logger.info("=" * 60)
        logger.info("Partition fix completed successfully!")
        logger.info("=" * 60)
        
        # Verify partitions were created
        cur = conn.cursor()
        cur.execute("""
            SELECT tablename
            FROM pg_tables
            WHERE tablename LIKE 'parcels_%'
            AND schemaname = 'public'
            ORDER BY tablename;
        """)
        tables = cur.fetchall()
        logger.info(f"\nCurrent tables/partitions:")
        for table in tables:
            logger.info(f"  - {table[0]}")
        
        cur.close()
        conn.close()
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    fix_all_partitions()

