# utils/cache_manager.py
import sys
import logging
from pathlib import Path
from typing import Optional
import boto3
from botocore.exceptions import ClientError

# Add backend directory to path for config import
_backend_dir = Path(__file__).parent.parent.parent  # Go up from utils/ -> tile_server/ -> backend/
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
from config import (
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_REGION_NAME,
    AWS_STORAGE_BUCKET_NAME, CLOUDFRONT_DOMAIN, USE_CLOUDFRONT
)

logger = logging.getLogger(__name__)
# Set to False to disable cache logging (faster performance)
ENABLE_CACHE_LOGGING = False

# Initialize S3 client
_s3_client = None

def _init_s3_client():
    """Initialize S3 client. Can be called multiple times safely."""
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    
    # Re-import config to ensure latest values (in case env vars were set after import)
    import importlib
    import config as config_module
    importlib.reload(config_module)
    
    from config import (
        AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_REGION_NAME,
        AWS_STORAGE_BUCKET_NAME
    )
    
    # Debug: Check what we got
    has_access_key = bool(AWS_ACCESS_KEY_ID)
    has_secret_key = bool(AWS_SECRET_ACCESS_KEY)
    access_key_preview = AWS_ACCESS_KEY_ID[:10] + "..." if AWS_ACCESS_KEY_ID and len(AWS_ACCESS_KEY_ID) > 10 else "None"
    
    print(f"[S3 INIT DEBUG] AWS_ACCESS_KEY_ID present: {has_access_key} ({access_key_preview})")
    print(f"[S3 INIT DEBUG] AWS_SECRET_ACCESS_KEY present: {has_secret_key}")
    print(f"[S3 INIT DEBUG] AWS_S3_REGION_NAME: {AWS_S3_REGION_NAME}")
    print(f"[S3 INIT DEBUG] AWS_STORAGE_BUCKET_NAME: {AWS_STORAGE_BUCKET_NAME}")
    
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        try:
            _s3_client = boto3.client(
                's3',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_S3_REGION_NAME
            )
            logger.info(f"S3 client initialized for bucket: {AWS_STORAGE_BUCKET_NAME}")
            print(f"[S3 INIT SUCCESS] S3 client initialized successfully for bucket: {AWS_STORAGE_BUCKET_NAME}")
        except Exception as e:
            logger.warning(f"Failed to initialize S3 client: {e}")
            print(f"[S3 INIT ERROR] Failed to initialize S3 client: {e}")
            import traceback
            traceback.print_exc()
            _s3_client = None
    else:
        logger.warning("S3 credentials not configured, S3 tile storage disabled")
        print(f"[S3 INIT WARNING] S3 credentials not configured - AWS_ACCESS_KEY_ID={has_access_key}, AWS_SECRET_ACCESS_KEY={has_secret_key}")
        _s3_client = None
    
    return _s3_client

# Initialize on module load
_init_s3_client()

def _s3_tile_key(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> str:
    """
    Generate S3 object key in format: state_code/district_code/z/x/y.png
    - state_code: State code (e.g., 'KA') or 'all' if no filter
    - district_code: District code (e.g., '630') or 'all' if no filter
    """
    state_part = (state_code or 'all').upper()
    district_part = (district_code or 'all')
    return f"{state_part}/{district_part}/{z}/{x}/{y}.png"

def get_cloudfront_url(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> str:
    """
    Generate CloudFront URL for a tile.
    Format: https://{CLOUDFRONT_DOMAIN}/state_code/district_code/z/x/y.png
    """
    s3_key = _s3_tile_key(z, x, y, state_code, district_code)
    protocol = "https" if USE_CLOUDFRONT else "http"
    return f"{protocol}://{CLOUDFRONT_DOMAIN}/{s3_key}"

def get_tile_from_s3(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> Optional[bytes]:
    """
    Get tile from S3. Returns tile data if found, None otherwise.
    """
    if not _s3_client:
        # Try to reinitialize
        _init_s3_client()
        if not _s3_client:
            logger.warning("S3 client not initialized - cannot retrieve tiles")
            print("S3 client not initialized - cannot retrieve tiles")
            return None
    
    try:
        s3_key = _s3_tile_key(z, x, y, state_code, district_code)
        response = _s3_client.get_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=s3_key)
        tile_data = response['Body'].read()
        if ENABLE_CACHE_LOGGING:
            logger.info(f"[S3 HIT] Tile {z}/{x}/{y} retrieved from S3 (key: {s3_key})")
        return tile_data
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'NoSuchKey':
            if ENABLE_CACHE_LOGGING:
                logger.debug(f"[S3 MISS] Tile {z}/{x}/{y} not found in S3 (key: {s3_key})")
            return None
        else:
            logger.error(f"[S3 ERROR] Failed to get tile {z}/{x}/{y} from S3: {e}")
            return None
    except Exception as e:
        logger.error(f"[S3 ERROR] Unexpected error getting tile {z}/{x}/{y} from S3: {e}")
        return None

def get_tile(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> Optional[bytes]:
    """
    Get tile from S3 (S3-only storage, no local cache).
    Returns tile data if found, None otherwise.
    """
    return get_tile_from_s3(z, x, y, state_code, district_code)

def save_tile_to_s3(z: int, x: int, y: int, tile_data: bytes, state_code: str = None, district_code: str = None) -> bool:
    """
    Save tile to S3.
    Returns True if successful, False otherwise.
    """
    if not _s3_client:
        # Try to reinitialize
        _init_s3_client()
        if not _s3_client:
            logger.error("S3 client not initialized - cannot save tiles")
            print("S3 client not initialized - cannot save tiles")
            return False
    
    try:
        s3_key = _s3_tile_key(z, x, y, state_code, district_code)
        _s3_client.put_object(
            Bucket=AWS_STORAGE_BUCKET_NAME,
            Key=s3_key,
            Body=tile_data,
            ContentType='image/png',
            CacheControl='public, max-age=31536000'
        )
        if ENABLE_CACHE_LOGGING:
            logger.info(f"[S3 SAVED] Tile {z}/{x}/{y} saved to S3 (key: {s3_key})")
        else:
            logger.info(f"[S3 SAVED] Tile {z}/{x}/{y} saved to S3")
        return True
    except Exception as e:
        logger.error(f"[S3 ERROR] Failed to save tile {z}/{x}/{y} to S3: {e}")
        return False

def save_tile(z: int, x: int, y: int, tile_data: bytes, state_code: str = None, district_code: str = None) -> bool:
    """
    Save tile to S3 (S3-only storage, no local cache).
    Returns True if successful, False otherwise.
    """
    return save_tile_to_s3(z, x, y, tile_data, state_code, district_code)

def check_tile_exists_in_s3(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> bool:
    """
    Check if a tile exists in S3.
    Returns True if tile exists, False otherwise.
    """
    if not _s3_client:
        return False
    
    try:
        s3_key = _s3_tile_key(z, x, y, state_code, district_code)
        _s3_client.head_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=s3_key)
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == '404' or error_code == 'NoSuchKey':
            return False
        else:
            logger.error(f"[S3 ERROR] Error checking tile {z}/{x}/{y} in S3: {e}")
            return False
    except Exception as e:
        logger.error(f"[S3 ERROR] Unexpected error checking tile {z}/{x}/{y} in S3: {e}")
        return False

# Backward compatibility aliases (for viewport_tiles.py)
get_tile_from_cache = get_tile
save_tile_to_cache = save_tile
