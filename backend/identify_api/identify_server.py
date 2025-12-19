from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from identify_api.utils.query_parcel import find_parcel
import psycopg2
import sys
from pathlib import Path

# Add backend directory to path to import config
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from config import DB_CONFIG, TABLE_MASTER

router = APIRouter()


@router.get("/identify")
def identify(lat: float = Query(...), lon: float = Query(...)):
    row = find_parcel(lat, lon)

    if row is None:
        return JSONResponse({"status": "not_found"})

    geom = row.get('geometry') or row.get('geom')
    
    if geom is None:
        return JSONResponse({"status": "error", "message": "Geometry not found in parcel data"})
    
    geom_json = geom.__geo_interface__
    attributes = row.to_dict()
    
    for key in ['geometry', 'geom']:
        attributes.pop(key, None)

    result = {
        "status": "ok",
        "attributes": attributes,
        "geometry": geom_json,
        "coordinates": geom_json.get("coordinates")
    }
    return JSONResponse(result)


@router.get("/states-districts")
def get_states_districts():
    """
    Get available states and districts for filtering.
    Returns list of states with their districts.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    try:
        # Get all states
        cur.execute(f"""
            SELECT DISTINCT state_code, state, COUNT(*) as count
            FROM {TABLE_MASTER}
            GROUP BY state_code, state
            ORDER BY state;
        """)
        states_data = cur.fetchall()
        
        states = []
        for state_code, state_name, count in states_data:
            # Get districts for this state
            cur.execute(f"""
                SELECT DISTINCT district_code, district_name, COUNT(*) as count
                FROM {TABLE_MASTER}
                WHERE state_code = %s
                GROUP BY district_code, district_name
                ORDER BY district_name;
            """, (state_code,))
            
            districts_data = cur.fetchall()
            districts = [
                {
                    "code": dist_code,
                    "name": dist_name,
                    "count": dist_count
                }
                for dist_code, dist_name, dist_count in districts_data
            ]
            
            states.append({
                "code": state_code,
                "name": state_name,
                "count": count,
                "districts": districts
            })
        
        return JSONResponse({"states": states})
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.get("/bounds")
def get_bounds(
    state_code: str = Query(None),
    district_code: str = Query(None)
):
    """
    Get bounding box for a state/district.
    Returns bounds as [min_lon, min_lat, max_lon, max_lat].
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    try:
        # Build WHERE clause with optional filters
        where_clauses = []
        params = []
        
        if state_code:
            where_clauses.append("state_code = %s")
            params.append(state_code.upper())
        
        if district_code:
            where_clauses.append("district_code = %s")
            params.append(district_code)
        
        where_clause = ""
        if where_clauses:
            where_clause = " WHERE " + " AND ".join(where_clauses)
        
        # Get bounding box
        query = f"""
            SELECT 
                ST_XMin(ST_Extent(geom)) as min_lon,
                ST_YMin(ST_Extent(geom)) as min_lat,
                ST_XMax(ST_Extent(geom)) as max_lon,
                ST_YMax(ST_Extent(geom)) as max_lat
            FROM {TABLE_MASTER}
            {where_clause}
        """
        
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        
        result = cur.fetchone()
        
        if result and result[0] is not None:
            min_lon, min_lat, max_lon, max_lat = result
            return JSONResponse({
                "bounds": [float(min_lon), float(min_lat), float(max_lon), float(max_lat)],
                "center": [
                    float((min_lat + max_lat) / 2),
                    float((min_lon + max_lon) / 2)
                ]
            })
        else:
            return JSONResponse({"status": "error", "message": "No data found"}, status_code=404)
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.get("/place-labels")
def get_place_labels(
    state_code: str = Query(None),
    district_code: str = Query(None)
):
    """
    Get all place labels (villages, districts) at once.
    Returns all labels with their centroids - frontend will filter by zoom level.
    Cached on frontend to avoid repeated calls.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    try:
        # Build WHERE clause with optional filters
        where_clauses = []
        params = []
        
        if state_code:
            where_clauses.append("state_code = %s")
            params.append(state_code.upper())
        
        if district_code:
            where_clauses.append("district_code = %s")
            params.append(district_code)
        
        # Build WHERE clause string
        where_clause = ""
        if where_clauses:
            where_clause = " AND " + " AND ".join(where_clauses)
        
        # Get ALL districts
        district_query = f"""
            SELECT 
                district_name as name,
                ST_X(ST_Centroid(ST_Union(geom))) as lon,
                ST_Y(ST_Centroid(ST_Union(geom))) as lat,
                'district' as type,
                COUNT(*) as parcel_count
            FROM {TABLE_MASTER}
            WHERE district_name IS NOT NULL{where_clause}
            GROUP BY district_name
        """
        
        # Get ALL villages
        village_query = f"""
            SELECT 
                COALESCE(village_name, district_name) as name,
                ST_X(ST_Centroid(ST_Union(geom))) as lon,
                ST_Y(ST_Centroid(ST_Union(geom))) as lat,
                'village' as type,
                COUNT(*) as parcel_count
            FROM {TABLE_MASTER}
            WHERE (village_name IS NOT NULL OR district_name IS NOT NULL){where_clause}
            GROUP BY COALESCE(village_name, district_name)
        """
        
        # Execute queries
        if params:
            cur.execute(district_query, params)
        else:
            cur.execute(district_query)
        district_results = cur.fetchall()
        
        if params:
            cur.execute(village_query, params)
        else:
            cur.execute(village_query)
        village_results = cur.fetchall()
        
        labels = []
        # Add districts
        for name, lon, lat, label_type, parcel_count in district_results:
            if name and lon and lat:
                labels.append({
                    "name": name,
                    "lat": float(lat),
                    "lon": float(lon),
                    "type": label_type,
                    "parcel_count": parcel_count
                })
        
        # Add villages
        for name, lon, lat, label_type, parcel_count in village_results:
            if name and lon and lat:
                labels.append({
                    "name": name,
                    "lat": float(lat),
                    "lon": float(lon),
                    "type": label_type,
                    "parcel_count": parcel_count
                })
        
        print(f"[PLACE-LABELS] Returning {len(labels)} labels (state={state_code or 'all'}, district={district_code or 'all'})")
        return JSONResponse({"labels": labels})
        
    except Exception as e:
        print(f"[PLACE-LABELS ERROR] {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        cur.close()
        conn.close()
