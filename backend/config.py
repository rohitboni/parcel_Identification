"""
Backend Configuration

Centralized configuration for database connections and table names.
Supports both local and Neon databases.
"""

import os
from dotenv import load_dotenv

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

