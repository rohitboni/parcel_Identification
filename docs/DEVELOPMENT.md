# Development Guide

## Overview

This guide covers the development workflow, running the application, testing, debugging, and best practices for contributing to the Parcel MVP project.

## Development Environment Setup

### Prerequisites

1. Follow [SETUP.md](SETUP.md) for initial setup
2. Ensure virtual environment is activated
3. Database is set up and populated

### Activate Virtual Environment

```bash
# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

## Running the Application

### Start Backend Server

```bash
cd backend
uvicorn main:app --reload
```

**Options**:
- `--reload`: Auto-reload on code changes
- `--host 0.0.0.0`: Listen on all interfaces
- `--port 8001`: Use different port

**Access Points**:
- API: `http://127.0.0.1:8000`
- API Docs: `http://127.0.0.1:8000/docs`
- Alternative Docs: `http://127.0.0.1:8000/redoc`

### Run Frontend

**Option 1: Direct File**
- Open `frontend/map-app/index.html` in browser

**Option 2: Local Server**
```bash
cd frontend/map-app
python3 -m http.server 8080
# Access at http://127.0.0.1:8080
```

## Project Structure

```
parcel_mvp/
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── identify_api/             # Parcel identification
│   │   ├── identify_server.py    # API endpoint
│   │   └── utils/
│   │       ├── query_parcel.py   # Query logic
│   │       └── spatial_index.py  # Spatial index loader
│   ├── tile_server/               # Tile generation
│   │   ├── tile_server_raster.py  # Raster tile endpoint
│   │   ├── tile_server_vector.py # Vector tile endpoint (alternative)
│   │   └── utils/
│   │       ├── generate_tile.py   # Tile generation
│   │       ├── cache_manager.py   # Cache operations
│   │       └── tile_utils.py      # Coordinate utils
│   └── cache/                     # Tile cache directory
├── frontend/
│   └── map-app/
│       └── index.html             # Map interface
├── etl/
│   └── load_vellore.py            # Data loading pipeline
└── data/
    └── vellore/                   # Shapefile data
```

## Development Workflow

### 1. Make Code Changes

Edit files in your preferred editor. The server will auto-reload if using `--reload` flag.

### 2. Test Changes

**Backend Changes**:
- Check API docs at `http://127.0.0.1:8000/docs`
- Test endpoints manually or with curl/Postman
- Check server logs for errors

**Frontend Changes**:
- Refresh browser to see changes
- Check browser console for errors
- Test map interactions

### 3. Verify Functionality

- Map displays correctly
- Tiles load properly
- Click-to-identify works
- No console errors

## Code Organization

### Backend Modules

**Main App** (`backend/main.py`):
- FastAPI application setup
- CORS middleware configuration
- Router registration

**Identify API** (`backend/identify_api/`):
- Endpoint: `/api/identify`
- Spatial queries using in-memory index
- Returns GeoJSON

**Tile Server** (`backend/tile_server/`):
- Endpoint: `/tiles/{z}/{x}/{y}.png`
- Generates raster tiles on-demand
- Manages tile cache

### Adding New Endpoints

1. Create router in appropriate module:
```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/new-endpoint")
def new_endpoint():
    return {"message": "Hello"}
```

2. Register in `backend/main.py`:
```python
from new_module import router as new_router

app.include_router(new_router, prefix="/api")
```

## Debugging

### Backend Debugging

**Enable Debug Mode**:
```python
# In main.py
app = FastAPI(title="Parcel MVP Backend", version="1.0", debug=True)
```

**Print Statements**:
```python
print(f"Debug: {variable}")
```

**Logging**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug("Debug message")
```

**Check Server Logs**:
- Watch terminal output for errors
- Check for stack traces
- Verify database connections

### Frontend Debugging

**Browser Console**:
- Open Developer Tools (F12)
- Check Console tab for errors
- Use `console.log()` for debugging

**Network Tab**:
- Monitor API requests
- Check response status codes
- Verify tile requests

**Common Issues**:
- CORS errors: Check backend CORS configuration
- 404 errors: Verify API endpoint URLs
- Tile loading: Check cache directory permissions

### Database Debugging

**Connect to Database**:
```bash
psql -U postgres -d parcels_db
```

**Check Queries**:
```sql
-- Check table row counts
SELECT COUNT(*) FROM parcels_raw;
SELECT COUNT(*) FROM parcels;
SELECT COUNT(*) FROM parcels_simplified;

-- Test spatial query
SELECT parcel_uuid, ST_AsText(geom) 
FROM parcels_simplified 
LIMIT 1;

-- Check spatial index
EXPLAIN ANALYZE 
SELECT * FROM parcels_simplified 
WHERE geom && ST_MakeEnvelope(79.0, 13.0, 80.0, 14.0, 4326);
```

## Testing

### Manual Testing

**API Endpoints**:
```bash
# Health check
curl http://127.0.0.1:8000/health

# Identify endpoint
curl "http://127.0.0.1:8000/api/identify?lat=13.1&lon=79.28"

# Tile endpoint
curl http://127.0.0.1:8000/tiles/12/2945/1898.png -o test_tile.png
```

**Frontend**:
- Open map in browser
- Click on parcels
- Verify highlight appears
- Check alert shows parcel info

### Automated Testing (Future)

Consider adding:
- Unit tests for utility functions
- Integration tests for API endpoints
- End-to-end tests for frontend

## Code Style

### Python

Follow PEP 8:
- 4 spaces for indentation
- Maximum line length: 79 characters
- Use descriptive variable names
- Add docstrings to functions

**Example**:
```python
def generate_tile(z: int, x: int, y: int) -> bytes:
    """
    Generate a 256x256 PNG raster tile.
    
    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
    
    Returns:
        PNG image bytes
    """
    # Implementation
```

### JavaScript

Follow standard conventions:
- Use `const` and `let` (avoid `var`)
- Use meaningful variable names
- Add comments for complex logic

## Performance Optimization

### Tile Caching

- Tiles are cached automatically
- Clear cache if needed: `rm -rf backend/cache/*`
- Monitor cache size

### Database Queries

- Use spatial indexes (automatic with PostGIS)
- Use bounding box operator (`&&`) before `ST_Intersects`
- Consider connection pooling for high traffic

### Frontend Optimization

- Minimize API calls
- Cache tile layers
- Use appropriate zoom levels

## Common Development Tasks

### Add New Attribute to Parcels

1. Update ETL (`etl/load_vellore.py`):
   - Add column to insert statements
   - Map from shapefile field

2. Update Database Schema:
   - Add column to tables
   - Or recreate tables

3. Update API Response:
   - Include in identify endpoint response

### Change Tile Styling

Edit `backend/tile_server/utils/generate_tile.py`:
- Modify colors in rasterization
- Change text styling
- Adjust label positioning

### Modify Map Center/Zoom

Edit `frontend/map-app/index.html`:
```javascript
const map = L.map("map").setView([lat, lon], zoom);
```

## Troubleshooting

### Server Won't Start

- Check port is available: `lsof -i :8000`
- Verify virtual environment is activated
- Check for syntax errors in code
- Verify database is running

### Tiles Not Loading

- Check cache directory exists and is writable
- Verify database has data
- Check tile coordinates are valid
- Review server logs for errors

### Identify Not Working

- Verify spatial index loaded (check server startup logs)
- Check coordinates are in valid range
- Verify database has parcels
- Check browser console for API errors

### Import Errors

- Ensure virtual environment is activated
- Verify all dependencies installed: `pip install -r requirements.txt`
- Check Python path includes project directory

## Best Practices

1. **Version Control**: Commit frequently with descriptive messages
2. **Code Review**: Review changes before merging
3. **Documentation**: Update docs when adding features
4. **Testing**: Test changes thoroughly before committing
5. **Error Handling**: Add proper error handling
6. **Logging**: Use logging instead of print statements
7. **Configuration**: Use environment variables for sensitive data

## Related Documentation

- [SETUP.md](SETUP.md) - Initial setup
- [CONFIG.md](CONFIG.md) - Configuration details
- [API.md](API.md) - API documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture

