from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from identify_api.utils.query_parcel import find_parcel

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
