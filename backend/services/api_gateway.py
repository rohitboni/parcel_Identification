"""
API Gateway Service
Port: 8000
Purpose: Single entry point that routes requests to appropriate backend services
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
import httpx
import os

app = FastAPI(title="Parcel MVP API Gateway", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Backend service URLs (can be overridden via environment variables)
TILE_SERVICE_URL = os.getenv("TILE_SERVICE_URL", "http://127.0.0.1:8001")  # On-demand tile generation
PREGEN_SERVICE_URL = os.getenv("PREGEN_SERVICE_URL", "http://127.0.0.1:8002")  # Pre-generation service
IDENTIFY_SERVICE_URL = os.getenv("IDENTIFY_SERVICE_URL", "http://127.0.0.1:8003")  # Identify API

# HTTP client for proxying requests
http_client = httpx.AsyncClient(timeout=30.0)


@app.get("/health")
async def health():
    """Health check for gateway and all services"""
    services_status = {}
    
    # Check each service
    for service_name, service_url in [
        ("tile-service", TILE_SERVICE_URL),
        ("pregenerate-service", PREGEN_SERVICE_URL),
        ("identify-service", IDENTIFY_SERVICE_URL)
    ]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{service_url}/health")
                services_status[service_name] = {
                    "status": "up" if response.status_code == 200 else "down",
                    "url": service_url
                }
        except Exception as e:
            services_status[service_name] = {
                "status": "down",
                "error": str(e),
                "url": service_url
            }
    
    return {
        "status": "ok",
        "gateway": "up",
        "services": services_status
    }


@app.get("/tiles/{z}/{x}/{y}.png")
async def get_tile(z: int, x: int, y: int, request: Request):
    """
    Proxy tile requests to tile service (Service 1)
    Route: /tiles/{z}/{x}/{y}.png -> http://127.0.0.1:8001/tiles/{z}/{x}/{y}.png
    """
    try:
        # Build query parameters
        query_params = dict(request.query_params)
        
        # Forward request to tile service
        url = f"{TILE_SERVICE_URL}/tiles/{z}/{x}/{y}.png"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=query_params)
            
            if response.status_code == 200:
                return Response(
                    content=response.content,
                    media_type="image/png",
                    headers={
                        "Cache-Control": "public, max-age=3600",
                        "ETag": response.headers.get("ETag", "")
                    }
                )
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Tile service timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Tile service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@app.get("/api/pregenerate-viewport")
async def pregenerate_viewport(request: Request):
    """
    Proxy pre-generation requests to pre-generation service (Service 2)
    Route: /api/pregenerate-viewport -> http://127.0.0.1:8002/api/pregenerate-viewport
    """
    try:
        query_params = dict(request.query_params)
        url = f"{PREGEN_SERVICE_URL}/api/pregenerate-viewport"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=query_params)
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Pre-generation service timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Pre-generation service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@app.get("/api/check-district-tiles")
async def check_district_tiles(request: Request):
    """
    Proxy district tile check requests to pre-generation service (Service 2)
    Route: /api/check-district-tiles -> http://127.0.0.1:8002/api/check-district-tiles
    """
    try:
        query_params = dict(request.query_params)
        url = f"{PREGEN_SERVICE_URL}/api/check-district-tiles"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=query_params)
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Pre-generation service timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Pre-generation service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@app.get("/api/generate-district-tiles")
async def generate_district_tiles(request: Request):
    """
    Proxy district tile generation requests to pre-generation service (Service 2)
    Route: /api/generate-district-tiles -> http://127.0.0.1:8002/api/generate-district-tiles
    """
    try:
        query_params = dict(request.query_params)
        url = f"{PREGEN_SERVICE_URL}/api/generate-district-tiles"
        
        async with httpx.AsyncClient(timeout=3600.0) as client:  # Long timeout for generation
            response = await client.get(url, params=query_params)
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Pre-generation service timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Pre-generation service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_api(request: Request, path: str):
    """
    Proxy all /api/* requests to identify service (Service 3)
    Routes:
    - /api/identify -> http://127.0.0.1:8003/api/identify
    - /api/states-districts -> http://127.0.0.1:8003/api/states-districts
    - /api/bounds -> http://127.0.0.1:8003/api/bounds
    - /api/place-labels -> http://127.0.0.1:8003/api/place-labels
    """
    try:
        query_params = dict(request.query_params)
        method = request.method
        url = f"{IDENTIFY_SERVICE_URL}/api/{path}"
        
        # Get request body if present
        body = None
        if method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                params=query_params,
                content=body,
                headers=dict(request.headers)
            )
            
            # Return appropriate response type
            if response.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse(
                    content=response.json(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            else:
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.headers.get("content-type", "text/plain")
                )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Identify service timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Identify service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    await http_client.aclose()


if __name__ == "__main__":
    import uvicorn
    print("🚪 API Gateway starting on port 8000")
    print(f"   Routing tiles -> {TILE_SERVICE_URL}")
    print(f"   Routing pre-generation -> {PREGEN_SERVICE_URL}")
    print(f"   Routing API -> {IDENTIFY_SERVICE_URL}")
    uvicorn.run(app, host="127.0.0.1", port=8000)

