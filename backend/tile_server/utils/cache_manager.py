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

# Initialize S3 client (only if credentials are provided)
# S3 is the ONLY storage location - no local cache
_s3_client = None
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    try:
        _s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_S3_REGION_NAME
        )
        logger.info(f"S3 client initialized for bucket: {AWS_STORAGE_BUCKET_NAME}")
    except Exception as e:
        logger.warning(f"Failed to initialize S3 client: {e}")
        _s3_client = None
else:
    logger.warning("S3 credentials not configured, S3 tile storage disabled")

def _s3_tile_key(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> str:
    """
    Generate S3 key in format: state_code/district_code/z/x/y.png
    
    Examples:
        - KA/630/15/23425/15134.png
        - TN/VELLORE/16/46850/30268.png
    
    Args:
        state_code: State code (e.g., 'KA', 'TN') - normalized to uppercase
        district_code: District code (e.g., '630', 'VELLORE') - kept as-is
        z: Zoom level (15-18)
        x: Tile X coordinate
        y: Tile Y coordinate
    
    Returns:
        S3 key string: state_code/district_code/z/x/y.png
    """
    # Normalize state code to uppercase, keep district code as-is
    state_part = (state_code or 'all').upper()
    district_part = (district_code or 'all')
    
    # S3 key structure: state_code/district_code/z/x/y.png
    return f"{state_part}/{district_part}/{z}/{x}/{y}.png"

def get_cloudfront_url(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> str:
    """
    Generate CloudFront URL for a tile.
    
    Format: https://{CLOUDFRONT_DOMAIN}/state_code/district_code/z/x/y.png
    
    Examples:
        - https://df77x5vpgut6a.cloudfront.net/KA/630/15/23425/15134.png
        - https://df77x5vpgut6a.cloudfront.net/TN/VELLORE/16/46850/30268.png
    
    Args:
        z: Zoom level (15-18)
        x: Tile X coordinate
        y: Tile Y coordinate
        state_code: State code (e.g., 'KA', 'TN')
        district_code: District code (e.g., '630', 'VELLORE')
    
    Returns:
        CloudFront URL string
    """
    s3_key = _s3_tile_key(z, x, y, state_code, district_code)
    protocol = "https" if USE_CLOUDFRONT else "http"
    return f"{protocol}://{CLOUDFRONT_DOMAIN}/{s3_key}"

def get_tile_from_s3(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> Optional[bytes]:
    """
    Get tile from S3 bucket. Returns tile data if found, None otherwise.
    This is the ONLY storage location - no local cache fallback.
    """
    if not _s3_client:
        logger.warning("S3 client not initialized - cannot retrieve tiles")
        return None
    
    try:
        s3_key = _s3_tile_key(z, x, y, state_code, district_code)
        
        # Try to get object from S3
        response = _s3_client.get_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=s3_key)
        tile_data = response['Body'].read()
        
        if ENABLE_CACHE_LOGGING:
            logger.info(f"[S3 HIT] Tile {z}/{x}/{y} retrieved from S3 (key: {s3_key})")
        
        return tile_data
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'NoSuchKey':
            # Tile doesn't exist in S3 - this is normal, will generate on-demand
            if ENABLE_CACHE_LOGGING:
                logger.debug(f"[S3 MISS] Tile {z}/{x}/{y} not found in S3 (key: {s3_key})")
            return None
        else:
            # Other S3 error (permissions, network, etc.)
            logger.error(f"[S3 ERROR] Failed to get tile {z}/{x}/{y} from S3: {e}")
            return None
    except Exception as e:
        logger.error(f"[S3 ERROR] Unexpected error getting tile {z}/{x}/{y} from S3: {e}")
        return None

def get_tile(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> Optional[bytes]:
    """
    Get tile from S3 only. No local cache fallback.
    This is the main function to use for checking if a tile exists.
    """
    return get_tile_from_s3(z, x, y, state_code, district_code)

def save_tile_to_s3(z: int, x: int, y: int, tile_data: bytes, state_code: str = None, district_code: str = None) -> bool:
    """
    Save tile to S3 bucket. Returns True if successful, False otherwise.
    This is the ONLY storage location - no local cache.
    """
    if not _s3_client:
        logger.error("S3 client not initialized - cannot save tiles")
        return False
    
    try:
        s3_key = _s3_tile_key(z, x, y, state_code, district_code)
        
        _s3_client.put_object(
            Bucket=AWS_STORAGE_BUCKET_NAME,
            Key=s3_key,
            Body=tile_data,
            ContentType='image/png',
            CacheControl='public, max-age=31536000'  # 1 year cache
        )
        
        if ENABLE_CACHE_LOGGING:
            logger.info(f"[S3 SAVED] Tile {z}/{x}/{y} saved to S3 (key: {s3_key})")
        else:
            logger.info(f"[S3 SAVED] Tile {z}/{x}/{y} saved to S3")
        
        return True
    except Exception as e:
        logger.error(f"[S3 ERROR] Failed to save tile {z}/{x}/{y} to S3: {e}")
        return False

def save_tile(z: int, x: int, y: int, tile_data: bytes, state_code: str = None, district_code: str = None):
    """
    Save tile to S3 only. No local cache.
    This is the main function to use for saving generated tiles.
    """
    save_tile_to_s3(z, x, y, tile_data, state_code, district_code)
