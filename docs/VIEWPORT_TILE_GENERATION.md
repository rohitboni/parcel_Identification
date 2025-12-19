# Viewport-Based Tile Generation Strategy

## Overview

The tile generation system uses a **viewport-priority strategy** to ensure users see tiles for their current viewport immediately, while surrounding tiles are pre-generated in the background for smooth panning.

## Priority Strategy

### 1. Viewport Tiles (Highest Priority)
- **When**: Generated immediately when viewport changes
- **What**: All tiles covering the current map viewport
- **Purpose**: Ensure users see tiles for what they're currently viewing

### 2. Surrounding Tiles (Background Priority)
- **When**: Generated after viewport tiles
- **What**: Tiles in a spiral pattern around the viewport (configurable radius)
- **Purpose**: Pre-generate tiles for smooth panning/zooming

## Implementation

### Backend: Viewport Tile Generation

**File**: `backend/tile_server/utils/viewport_tiles.py`

**Key Functions**:

1. **`get_viewport_tiles(min_lat, min_lon, max_lat, max_lon, zoom)`**
   - Calculates all tile coordinates covering the viewport bounding box
   - Returns list of `(z, x, y)` tuples

2. **`get_surrounding_tiles(center_x, center_y, zoom, radius)`**
   - Generates tiles in spiral pattern around center tile
   - Radius determines how many rings of tiles to generate
   - Returns tiles ordered by distance from center (closer first)

3. **`generate_tiles_for_viewport(...)`**
   - Main function that orchestrates tile generation
   - **Priority 1**: Generate viewport tiles first
   - **Priority 2**: Generate surrounding tiles after
   - Checks cache before generating (avoids duplicate work)
   - Returns statistics about generation

### API Endpoint

**Endpoint**: `GET /api/pregenerate-viewport`

**Parameters**:
- `min_lat`, `min_lon`, `max_lat`, `max_lon`: Viewport bounding box
- `zoom`: Zoom level (15-18)
- `state_code` (optional): Filter by state
- `district_code` (optional): Filter by district
- `surrounding_radius` (optional, default=2): Number of rings of surrounding tiles

**Response**:
```json
{
  "viewport_tiles": 25,
  "surrounding_tiles": 24,
  "generated": 10,
  "cached": 39,
  "errors": 0
}
```

### Frontend Integration

**File**: `frontend/map-app/index.html`

**Behavior**:
1. **On Map Move/Zoom**: Triggers viewport tile pre-generation
2. **Debouncing**: Waits 500ms after map stops moving before generating (avoids excessive requests)
3. **Non-blocking**: Pre-generation happens in background, doesn't block UI
4. **Zoom Level Check**: Only pre-generates for zoom levels 15-18

**Code Flow**:
```javascript
map.on('moveend', function() {
  scheduleViewportGeneration(); // Debounced, waits 500ms
});

function pregenerateViewportTiles() {
  const bounds = map.getBounds();
  // Call /api/pregenerate-viewport with viewport bounds
}
```

## Tile Serving Priority

### Current Tile Request Flow

1. **Check Cache First**: Always check cache before generating
   - Cache structure: `cache/state/district/z/x/y.png`
   - Fast lookup (< 10ms)

2. **Generate if Missing**: Generate tile on-demand
   - Viewport tiles: Generated immediately (user sees them)
   - Surrounding tiles: Pre-generated in background

3. **Save to Cache**: All generated tiles are cached
   - Organized by state/district for easy management
   - Future requests use cached tiles

## Spiral Pattern Algorithm

Surrounding tiles are generated in a spiral pattern expanding outward:

```
Radius 1 (8 tiles):
  [ ] [ ] [ ]
  [ ] [X] [ ]
  [ ] [ ] [ ]

Radius 2 (16 tiles):
  [ ] [ ] [ ] [ ] [ ]
  [ ] [ ] [ ] [ ] [ ]
  [ ] [ ] [X] [ ] [ ]
  [ ] [ ] [ ] [ ] [ ]
  [ ] [ ] [ ] [ ] [ ]
```

**Priority Order**:
1. Direct neighbors (radius=1) - 8 tiles
2. Next ring (radius=2) - 16 tiles
3. Outer rings (radius=3, 4, ...) - expanding outward

Tiles are sorted by distance from center, so closer tiles are generated first.

## Cache Structure

Tiles are cached in organized directory structure:

```
cache/
  ├── ALL/              # No state filter
  │   └── all/         # No district filter
  │       └── 15/
  │           └── 23456/
  │               └── 15181.png
  ├── KA/              # Karnataka state
  │   ├── all/         # All districts in Karnataka
  │   │   └── 15/
  │   └── 526/        # Bengaluru (Rural) district
  │       └── 15/
  │           └── 23456/
  │               └── 15181.png
```

## Performance Considerations

### Benefits

1. **Immediate Viewport Coverage**: Users see tiles for current viewport right away
2. **Smooth Panning**: Surrounding tiles pre-generated for seamless navigation
3. **Efficient Caching**: Tiles organized by state/district for easy management
4. **Background Generation**: Doesn't block UI while generating surrounding tiles

### Optimization Strategies

1. **Debouncing**: Frontend waits 500ms after map stops moving
2. **Cache First**: Always check cache before generating
3. **Priority Order**: Viewport tiles generated before surrounding tiles
4. **Configurable Radius**: Adjust `surrounding_radius` based on needs

### Performance Metrics

- **Viewport Tile Generation**: 100-500ms per tile (depends on parcel count)
- **Cache Hit**: < 10ms (file read)
- **Surrounding Tile Generation**: Background, doesn't block UI
- **Typical Viewport**: 20-50 tiles (depends on zoom level)

## Usage Example

### Frontend (Automatic)

The frontend automatically calls the pre-generation endpoint when:
- Map is moved (after 500ms debounce)
- Map is zoomed (after 500ms debounce)
- Initial page load

### Backend (Manual)

You can manually trigger viewport tile generation:

```python
from backend.tile_server.utils.viewport_tiles import generate_tiles_for_viewport

stats = generate_tiles_for_viewport(
    min_lat=13.0,
    min_lon=77.0,
    max_lat=13.5,
    max_lon=77.5,
    zoom=15,
    state_code='KA',
    district_code='526',
    surrounding_radius=2
)

print(f"Generated: {stats['generated']}, Cached: {stats['cached']}")
```

## Configuration

### Adjusting Surrounding Radius

**Frontend**: Change `surrounding_radius` parameter in `pregenerateViewportTiles()`:
```javascript
params.append('surrounding_radius', '3'); // Generate 3 rings instead of 2
```

**Backend**: Change default in API endpoint:
```python
surrounding_radius: int = Query(3, ge=0, le=5)  # Default 3 rings
```

### Adjusting Debounce Time

**Frontend**: Change timeout in `scheduleViewportGeneration()`:
```javascript
viewportGenerationTimeout = setTimeout(() => {
  pregenerateViewportTiles();
}, 1000); // Wait 1 second instead of 500ms
```

## Troubleshooting

### Tiles Not Pre-generating

1. **Check Zoom Level**: Only works for zoom 15-18
2. **Check Console**: Look for errors in browser console
3. **Check Backend Logs**: Verify API endpoint is being called
4. **Check Network Tab**: Verify requests are being made

### Too Many Requests

1. **Increase Debounce Time**: Wait longer after map stops moving
2. **Reduce Surrounding Radius**: Generate fewer surrounding tiles
3. **Check Cache**: Ensure tiles are being cached properly

### Performance Issues

1. **Reduce Surrounding Radius**: Generate fewer tiles
2. **Increase Debounce Time**: Generate less frequently
3. **Monitor Cache**: Ensure cache is working correctly

## Related Documentation

- [TILES.md](TILES.md) - General tile generation documentation
- [API.md](API.md) - API endpoint details
- [CACHE.md](CACHE.md) - Cache management documentation

