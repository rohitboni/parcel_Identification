from shapely.geometry import Point
from .spatial_index import parcels, sindex


def find_parcel(lat: float, lon: float):
    """Returns a row (Series) of the matching parcel or None."""
    pt = Point(lon, lat)

    candidate_indices = list(sindex.intersection(pt.bounds))
    if not candidate_indices:
        return None

    candidates = parcels.iloc[candidate_indices]
    geom_col = parcels.geometry.name
    inside = candidates[candidates[geom_col].contains(pt)]

    if inside.empty:
        return None

    return inside.iloc[0]
