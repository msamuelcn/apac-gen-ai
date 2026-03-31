"""Database connection pool and SQL execution helpers."""

import os
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def _build_conninfo() -> str:
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
    """Return (and lazily initialise) the shared connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_build_conninfo(),
            min_size=1,
            max_size=int(os.environ.get("DB_POOL_MAX", "5")),
            kwargs={"row_factory": dict_row},
        )
    return _pool


def run_sql(sql: str, params=None, fetch: bool = True):
    """Execute *sql* against AlloyDB and optionally return rows as dicts."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetch and cur.description:
                return cur.fetchall()
            conn.commit()
            return None
