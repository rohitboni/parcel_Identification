# backend/identify_api/identify_server.py

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from identify_api.utils.query_parcel import find_parcel

router = APIRouter()

@router.get("/identify")
def identify(lat: float = Query(...), lon: float = Query(...)):
    row = find_parcel(lat, lon)

    if row is None:
        return JSONResponse({"status": "not_found"})

    geom_json = row.geometry.__geo_interface__

    result = {
        "status": "ok",
        "attributes": row.drop(labels="geometry").to_dict(),
        "geometry": geom_json,
        "coordinates": geom_json.get("coordinates") # raw coordinate list
    }
    # print(result)
    return JSONResponse(result)
