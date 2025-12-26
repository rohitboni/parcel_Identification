from fastapi import APIRouter, Response, HTTPException, Query
from tile_server.utils.generate_tile import generate_raster_tile
from tile_server.utils.cache_manager import get_tile, save_tile, get_cloudfront_url
from config import USE_CLOUDFRONT, CLOUDFRONT_DOMAIN
import httpx

router = APIRouter()


@router.get("/tiles/{z}/{x}/{y}.png")
async def get_raster_tile(
    z: int, 
    x: int, 
    y: int,
    state_code: str = None,
    district_code: str = None
):
    """
    Returns a raster tile at the given z/x/y indices.
    Optional filters: state_code, district_code

    Flow (if USE_CLOUDFRONT=True):
    1. Check CloudFront: https://{CLOUDFRONT_DOMAIN}/state_code/district_code/z/x/y.png
    2. If CloudFront has it, redirect/proxy from CloudFront
    3. If not in CloudFront, check S3
    4. If not in S3, generate on-demand
    5. Save generated tile to S3
    6. Serve tile to frontend

    Flow (if USE_CLOUDFRONT=False):
    1. Check S3 bucket: cadastrals-data/state_code/district_code/z/x/y.png
    2. If not found, generate on-demand
    3. Save generated tile to S3
    4. Serve tile to frontend

    CloudFront URL Format: https://df77x5vpgut6a.cloudfront.net/state_code/district_code/z/x/y.png
    S3 Path Format: state_code/district_code/z/x/y.png

    Examples:
        - CloudFront: https://df77x5vpgut6a.cloudfront.net/KA/630/15/23425/15134.png
        - S3 Key: KA/630/15/23425/15134.png

    Storage: S3 only (no local cache)
    """
    if z < 15 or z > 18:
        raise HTTPException(status_code=400, detail="z out of allowed range")
    
    cache_headers = {
        "Cache-Control": "public, max-age=3600",
        "ETag": f"{state_code or 'all'}-{district_code or 'all'}-{z}-{x}-{y}"
    }
    
    # Try CloudFront first if enabled
    if USE_CLOUDFRONT:
        cloudfront_url = get_cloudfront_url(z, x, y, state_code, district_code)
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                cf_response = await client.get(cloudfront_url)
                if cf_response.status_code == 200:
                    print(f"[CLOUDFRONT HIT] Tile {z}/{x}/{y} served from CloudFront (state={state_code or 'all'}, district={district_code or 'all'})")
                    return Response(
                        content=cf_response.content,
                        media_type="image/png",
                        headers=cache_headers
                    )
                elif cf_response.status_code == 404:
                    print(f"[CLOUDFRONT MISS] Tile {z}/{x}/{y} not found in CloudFront, checking S3...")
                else:
                    print(f"[CLOUDFRONT ERROR] Status {cf_response.status_code} for tile {z}/{x}/{y}, falling back to S3")
        except httpx.TimeoutException:
            print(f"[CLOUDFRONT TIMEOUT] Timeout fetching tile {z}/{x}/{y} from CloudFront, falling back to S3")
        except Exception as e:
            print(f"[CLOUDFRONT ERROR] Error fetching tile {z}/{x}/{y} from CloudFront: {e}, falling back to S3")
    
    # Check S3
    existing_tile = get_tile(z, x, y, state_code=state_code, district_code=district_code)
    if existing_tile:
        print(f"[S3 HIT] Tile {z}/{x}/{y} served from S3 (state={state_code or 'all'}, district={district_code or 'all'})")
        return Response(content=existing_tile, media_type="image/png", headers=cache_headers)
    
    # Generate on-demand
    print(f"[GENERATING] Tile {z}/{x}/{y} generating on-demand (state={state_code or 'all'}, district={district_code or 'all'})")
    try:
        tile_img = generate_raster_tile(z, x, y, state_code=state_code, district_code=district_code)
        print(f"[GENERATED] Tile {z}/{x}/{y} generated successfully ({len(tile_img)} bytes)")
    except Exception as e:
        print(f"[ERROR] Tile {z}/{x}/{y} generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Tile generation failed: {e}")
    
    # Save to S3
    save_success = save_tile(z, x, y, tile_img, state_code=state_code, district_code=district_code)
    if save_success:
        print(f"[S3 SAVED] Tile {z}/{x}/{y} saved to S3")
    else:
        print(f"[S3 SAVE FAILED] Tile {z}/{x}/{y} could not be saved to S3")
    
    return Response(content=tile_img, media_type="image/png", headers=cache_headers)
