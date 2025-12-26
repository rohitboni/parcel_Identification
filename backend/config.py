"""
Backend Configuration

Centralized configuration for database connections and table names.
Supports both local and Neon databases.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (backend/ is one level down from root)
# This ensures .env is found whether running from backend/ or scripts/
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Fallback to default load_dotenv() behavior (current directory)
    load_dotenv()

# Database Configuration
# Defaults to local database (parcels_db_new)
# To use Neon database, update .env with Neon credentials
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "parcels_db_new"),  # Updated default to parcels_db_new
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres")
}

# Table Names Configuration
# Default to local database tables, but can be overridden for Neon
TABLE_MASTER = os.getenv("TABLE_MASTER", "parcels_master")
TABLE_SIMPLIFIED = os.getenv("TABLE_SIMPLIFIED", "parcels_simplified")

# For Neon database, set these in .env:
# TABLE_MASTER=parcels_master_neon
# TABLE_SIMPLIFIED=parcels_simplified_neon

# S3 Configuration for Tile Storage
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "ap-south-1")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "cadastrals-data")
AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN", f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com")

# CloudFront Configuration - TILES ONLY
CLOUDFRONT_DOMAIN = os.getenv("CLOUDFRONT_DOMAIN", "df77x5vpgut6a.cloudfront.net")
USE_CLOUDFRONT = os.getenv("USE_CLOUDFRONT", "True").lower() == "true"

