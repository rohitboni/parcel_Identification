import psycopg2
import geopandas as gpd
import logging
import sys
from pathlib import Path

# Add backend directory to path to import config
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from config import DB_CONFIG, TABLE_MASTER

logger = logging.getLogger(__name__)


def find_parcel(lat: float, lon: float):
    """
    Find parcel using database-side spatial query.
    This is more efficient for large datasets than loading all parcels into memory.
    
    Returns a GeoDataFrame row (Series) or None.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        # Use database-side spatial query with partition pruning optimization
        # For partitioned tables, we can optimize by filtering on partition keys first
        # But since we don't know state/district from coordinates, we use spatial index
        
        # Optimized query: Use spatial index with bounding box check first (faster)
        # Use ST_DWithin with small buffer (1 meter) to handle click precision issues
        # This allows finding parcels even if the click is slightly outside the boundary
        query = f"""
            SELECT 
                parcel_uuid,
                geom,
                survey_num,
                state_code,
                district_code,
                district_name,
                sub_district_name,
                village_name,
                state
            FROM {TABLE_MASTER}
            WHERE geom && ST_MakeEnvelope(%s - 0.01, %s - 0.01, %s + 0.01, %s + 0.01, 4326)
              AND (
                  ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                  OR ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 1.0)
              )
            ORDER BY ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)
            LIMIT 1;
        """
        
        # Use bounding box first (uses spatial index), then check containment or proximity
        # ST_DWithin with 1m buffer handles cases where click is slightly outside boundary
        # Order by distance to get the closest parcel if multiple are found
        
        # Execute query with bounding box optimization
        # Bounding box of 0.01 degrees (≈1.1km) to catch parcels near boundaries
        result = gpd.read_postgis(query, conn, geom_col='geom', crs='EPSG:4326', 
                                  params=(lon, lat, lon, lat, lon, lat, lon, lat, lon, lat))
        conn.close()
        
        if len(result) == 0:
            logger.debug(f"No parcel found at lat={lat}, lon={lon}")
            return None
        
        # Convert to Series (single row)
        row = result.iloc[0]
        
        # Rename geometry column if needed
        if 'geometry' not in row.index and 'geom' in row.index:
            row = row.rename({'geom': 'geometry'})
        
        logger.debug(f"Found parcel: {row.get('survey_num', 'N/A')} at [{lat}, {lon}]")
        return row
        
    except Exception as e:
        logger.error(f"Error querying parcel: {e}")
        import traceback
        traceback.print_exc()
        return None
