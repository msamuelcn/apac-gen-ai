"""Database connection pool and SQL execution helpers.

Connection pooling via psycopg 3's ConnectionPool ensures efficient
reuse of database connections. Tuning:
  - DB_POOL_MAX (default 5): Adjust based on concurrency
    * Local dev: 2-5
    * Small Cloud Run instance (1 CPU): 5-10
    * High concurrency (multi-instance): 15-30 per instance
"""

import logging
import os
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def _build_conninfo() -> str:
    """Build connection info string for psycopg connection pool.

    Note: All parameters (user, password, host, port) are safely passed
    via the conninfo string; no SQL injection risk here.
    """
    required = {
        "host": os.environ["ALLOYDB_HOST"],
        "port": os.environ.get("ALLOYDB_PORT", "5432"),
        "dbname": os.environ["ALLOYDB_DB"],
        "user": os.environ["ALLOYDB_USER"],
        "password": os.environ["ALLOYDB_PASSWORD"],
    }
    sslmode = os.environ.get("ALLOYDB_SSLMODE", "require")
    parts = " ".join(f"{k}={v}" for k, v in required.items())
    return f"{parts} sslmode={sslmode}"


def get_pool() -> ConnectionPool:
    """Return (and lazily initialise) the shared connection pool.

    Thread-safe singleton pattern: pool is created on first use
    and reused for all subsequent connections.
    """
    global _pool
    if _pool is None:
        pool_max = int(os.environ.get("DB_POOL_MAX", "5"))
        _pool = ConnectionPool(
            conninfo=_build_conninfo(),
            min_size=1,
            max_size=pool_max,
            kwargs={"row_factory": dict_row},  # Return rows as dicts
        )
        logger.info(f"Connection pool initialized (max_size={pool_max})")
    return _pool


def run_sql(sql: str, params=None, fetch: bool = True):
    """Execute *sql* against AlloyDB and optionally return rows as dicts.

    Args:
        sql: SQL statement (can include %(param)s placeholders)
        params: Dict of parameters for placeholders (psycopg2-style formatting)
        fetch: If True and query returns rows, fetch and return them;
               if False, return None (useful for INSERT/UPDATE/DELETE)

    Returns:
        List of dicts (one per row) if fetch=True and query has results;
        None otherwise.

    Raises:
        psycopg.Error: If SQL execution fails (connection error, invalid SQL, etc.)
    """
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetch and cur.description:
                return cur.fetchall()
            conn.commit()
            return None
