# backend/identify-api/utils/query_parcel.py

from shapely.geometry import Point
from .spatial_index import parcels, sindex

def find_parcel(lat: float, lon: float):
    """
    Returns a row (Series) of the matching parcel or None.
    """
    pt = Point(lon, lat)

    # Step 1: Fast spatial index query
    candidate_indices = list(sindex.intersection(pt.bounds))
    if not candidate_indices:
        return None

    candidates = parcels.iloc[candidate_indices]

    # Step 2: Precise geometric check
    inside = candidates[candidates.geometry.contains(pt)]

    if inside.empty:
        return None

    # Return the first matching polygon
    return inside.iloc[0]
