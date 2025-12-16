# API Documentation

## Base URL

Development: `http://127.0.0.1:8000`

## Endpoints

### 1. Raster Tile Endpoint

**Endpoint**: `GET /tiles/{z}/{x}/{y}.png`

**Description**: Returns a 256x256 PNG raster tile showing parcel boundaries and survey numbers.

**Path Parameters**:
- `z` (integer): Zoom level (allowed: 15-18; backend rejects others)
- `x` (integer): Tile X coordinate
- `y` (integer): Tile Y coordinate

**Response**:
- **Content-Type**: `image/png`
- **Body**: PNG image bytes (256x256 pixels)

**Example Request**:
```
GET /tiles/12/2945/1898.png
```

**Example Response**:
- PNG image with black parcel boundaries and survey number labels

**Caching**:
- Tiles are cached in `backend/cache/{z}/{x}/{y}.png`
- Cache is checked before generation
- Generated tiles are saved to cache

**Error Responses**:
- `500`: Tile generation failed (database error, etc.)

**Implementation**: `backend/tile_server/tile_server_raster.py`

---

### 2. Identify Parcel Endpoint

**Endpoint**: `GET /api/identify`

**Description**: Returns parcel information for a given latitude/longitude point.

**Query Parameters**:
- `lat` (float, required): Latitude in decimal degrees (EPSG:4326)
- `lon` (float, required): Longitude in decimal degrees (EPSG:4326)

**Response**:
- **Content-Type**: `application/json`

**Success Response** (200):
```json
{
  "status": "ok",
  "attributes": {
    "parcel_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "survey_num": "123/45",
    "v_name": "Village Name",
    "district": "Vellore",
    "tehsil": "Tehsil Name",
    ...
  },
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": [[[[79.28, 13.1], ...]]]
  },
  "coordinates": [[[[79.28, 13.1], ...]]]
}
```

**Not Found Response** (200):
```json
{
  "status": "not_found"
}
```

**Example Request**:
```
GET /api/identify?lat=13.1&lon=79.28
```

**Example Response**:
```json
{
  "status": "ok",
  "attributes": {
    "parcel_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "survey_num": "123/45",
    "v_name": "Sample Village",
    "district": "Vellore",
    "tehsil": "Sample Tehsil"
  },
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": [[[[79.28, 13.1], [79.281, 13.1], [79.281, 13.101], [79.28, 13.101], [79.28, 13.1]]]]
  },
  "coordinates": [[[[79.28, 13.1], [79.281, 13.1], [79.281, 13.101], [79.28, 13.101], [79.28, 13.1]]]]
}
```

**Implementation**: `backend/identify_api/identify_server.py`

**Query Logic**: `backend/identify_api/utils/query_parcel.py`

**Spatial Index**: `backend/identify_api/utils/spatial_index.py`

---

### 3. Vector Tile Endpoint (Alternative)

**Endpoint**: `GET /tiles/{z}/{x}/{y}.pbf`

**Description**: Returns a Mapbox Vector Tile (MVT) in protobuf format. This is an alternative implementation not currently used by the frontend.

**Path Parameters**:
- `z` (integer): Zoom level (0-22)
- `x` (integer): Tile X coordinate
- `y` (integer): Tile Y coordinate

**Response**:
- **Content-Type**: `application/vnd.mapbox-vector-tile`
- **Body**: Protobuf bytes (MVT format)
- **Status 204**: Empty tile (no features)

**Example Request**:
```
GET /tiles/12/2945/1898.pbf
```

**Caching**:
- Cache-Control header: `public, max-age=60`

**Error Responses**:
- `400`: Invalid z/x/y parameters
- `500`: Database query error

**Implementation**: `backend/tile_server/tile_server_vector.py`

**Note**: This endpoint is defined but not integrated into the main router. It uses asyncpg for async database queries.

---

### 4. Parcel Info Endpoint (Vector Tile Server)

**Endpoint**: `GET /parcel-info?parcel_uuid={uuid}`

**Description**: Returns detailed parcel information by UUID. Part of the vector tile server implementation.

**Query Parameters**:
- `parcel_uuid` (string, required): Parcel UUID

**Response**:
```json
{
  "parcel_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "survey_num": "123/45",
  "gp_name": "Gram Panchayat Name",
  "v_name": "Village Name",
  "v_code": "12345",
  "district": "Vellore",
  "state": "Tamil Nadu",
  "tehsil": "Tehsil Name",
  "centroid_wkt": "POINT(79.28 13.1)"
}
```

**Error Responses**:
- `400`: Missing parcel_uuid
- `404`: Parcel not found

**Implementation**: `backend/tile_server/tile_server_vector.py`

---

### 5. Health Check Endpoint

**Endpoint**: `GET /health`

**Description**: Simple health check endpoint.

**Response**:
- **Content-Type**: `text/plain`
- **Body**: `"ok"`

**Example Request**:
```
GET /health
```

**Example Response**:
```
ok
```

**Implementation**: `backend/tile_server/tile_server_vector.py`

---

## CORS Configuration

The API includes CORS middleware configured in `backend/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This allows requests from any origin (suitable for development).

## API Router Structure

The main FastAPI app (`backend/main.py`) includes routers:

```python
app.include_router(identify_router, prefix="/api")
app.include_router(tile_router)
```

- Identify router: `/api/*` endpoints
- Tile router: `/tiles/*` endpoints

## Error Handling

### Standard HTTP Status Codes

- `200`: Success
- `204`: No Content (empty tile)
- `400`: Bad Request (invalid parameters)
- `404`: Not Found (parcel not found)
- `500`: Internal Server Error (generation/query failure)

### Error Response Format

Most endpoints return JSON with error details:

```json
{
  "detail": "Error message description"
}
```

## Rate Limiting

Currently no rate limiting is implemented (MVP stage).

## Authentication

Currently no authentication is implemented (MVP stage).

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [TILES.md](TILES.md) - Tile generation details
- [SPATIAL_QUERIES.md](SPATIAL_QUERIES.md) - Spatial query implementation

