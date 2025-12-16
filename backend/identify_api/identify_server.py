from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from identify_api.utils.query_parcel import find_parcel
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "parcels_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres")
}


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


@router.get("/place-labels")
def get_place_labels(zoom: int = Query(..., ge=10, le=18)):
    """
    Get place labels (villages, districts) for the current map view.
    Returns labels with their centroids for display on the map.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    try:
        # Adjust label density based on zoom level
        # At lower zoom, show districts; at higher zoom, show villages
        if zoom < 13:
            # Show districts only
            query = """
                SELECT 
                    district_name as name,
                    ST_X(ST_Centroid(ST_Union(geom))) as lon,
                    ST_Y(ST_Centroid(ST_Union(geom))) as lat,
                    'district' as type
                FROM parcels_master
                WHERE district_name IS NOT NULL
                GROUP BY district_name
            """
        elif zoom < 15:
            # Show villages (grouped)
            query = """
                SELECT 
                    COALESCE(village_name, district_name) as name,
                    ST_X(ST_Centroid(ST_Union(geom))) as lon,
                    ST_Y(ST_Centroid(ST_Union(geom))) as lat,
                    'village' as type
                FROM parcels_master
                WHERE village_name IS NOT NULL OR district_name IS NOT NULL
                GROUP BY COALESCE(village_name, district_name)
                HAVING COUNT(*) > 10
            """
        else:
            # Show villages (more detailed)
            query = """
                SELECT 
                    COALESCE(village_name, district_name) as name,
                    ST_X(ST_Centroid(ST_Union(geom))) as lon,
                    ST_Y(ST_Centroid(ST_Union(geom))) as lat,
                    'village' as type
                FROM parcels_master
                WHERE village_name IS NOT NULL OR district_name IS NOT NULL
                GROUP BY COALESCE(village_name, district_name)
                HAVING COUNT(*) > 5
            """
        
        cur.execute(query)
        results = cur.fetchall()
        
        labels = []
        for name, lon, lat, label_type in results:
            if name and lon and lat:
                labels.append({
                    "name": name,
                    "lat": float(lat),
                    "lon": float(lon),
                    "type": label_type
                })
        
        return JSONResponse({"labels": labels})
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        cur.close()
        conn.close()
