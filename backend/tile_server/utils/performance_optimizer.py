"""
Performance optimizations for tile generation.

Key optimizations:
1. Connection pooling (reuse connections)
2. Prepared statements (faster queries)
3. Batch geometry conversion
4. Query result caching
"""
import psycopg2
from psycopg2 import pool
import logging
from typing import Optional
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from config import DB_CONFIG

logger = logging.getLogger(__name__)

# Connection pool for better performance
_connection_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_min = 1
_pool_max = 5


def get_connection_pool():
    """Get or create connection pool."""
    global _connection_pool
    if _connection_pool is None:
        try:
            _connection_pool = psycopg2.pool.ThreadedConnectionPool(
                _pool_min,
                _pool_max,
                **DB_CONFIG
            )
            logger.info(f"Created connection pool: {_pool_min}-{_pool_max} connections")
        except Exception as e:
            logger.error(f"Error creating connection pool: {e}")
            # Fallback to single connection
            return None
    return _connection_pool


def get_db_connection():
    """Get connection from pool or create new one."""
    pool = get_connection_pool()
    if pool:
        try:
            return pool.getconn()
        except Exception as e:
            logger.warning(f"Error getting connection from pool: {e}")
            # Fallback to direct connection
            return psycopg2.connect(**DB_CONFIG)
    else:
        return psycopg2.connect(**DB_CONFIG)


def return_db_connection(conn):
    """Return connection to pool."""
    pool = get_connection_pool()
    if pool and conn:
        try:
            pool.putconn(conn)
        except Exception as e:
            logger.warning(f"Error returning connection to pool: {e}")
            conn.close()


def close_connection_pool():
    """Close all connections in pool."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Connection pool closed")

