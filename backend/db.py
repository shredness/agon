"""
Postgres connection pooling and schema initialization.
"""

import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
_pg_pool = None


def init_db():
    """Initialize Postgres connection pool and schema."""
    global _pg_pool
    
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is required")
    
    try:
        import psycopg2
        from psycopg2 import pool
        
        _pg_pool = pool.SimpleConnectionPool(2, 10, DATABASE_URL)
        logger.info("✓ Postgres connection pool initialized")
        
        with get_db() as conn:
            _init_schema(conn)
        logger.info("✓ Postgres schema initialized")
        
    except Exception as e:
        logger.error(f"✗ Postgres init failed: {e}")
        raise


@contextmanager
def get_db():
    """Get a Postgres connection from the pool (context manager)."""
    if not _pg_pool:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    from psycopg2.extras import DictCursor
    
    conn = _pg_pool.getconn()
    conn.cursor_factory = DictCursor
    
    try:
        yield conn
    finally:
        _pg_pool.putconn(conn)


class _ConnectionWrapper:
    """Wrapper for psycopg2 connections from the pool that ensures proper cleanup.
    Mimics sqlite3 connection API (execute directly on connection, ? -> %s conversion)."""
    def __init__(self, conn):
        self._conn = conn
        self._cursor = None
    
    def cursor(self, *args, **kwargs):
        """Get a cursor from the connection."""
        return self._conn.cursor(*args, **kwargs)
    
    def execute(self, sql, params=None):
        """Execute SQL directly (like sqlite3). Converts ? to %s for psycopg2."""
        if not self._cursor:
            self._cursor = self._conn.cursor()
        # Convert SQLite ? placeholders to psycopg2 %s
        if params and '?' in sql:
            sql = sql.replace('?', '%s')
        self._cursor.execute(sql, params)
        return self  # Return self to support chaining: conn.execute().fetchone()
    
    def fetchone(self):
        """Fetch one row from the last execute."""
        if self._cursor:
            return self._cursor.fetchone()
        return None
    
    def fetchall(self):
        """Fetch all rows from the last execute."""
        if self._cursor:
            return self._cursor.fetchall()
        return []
    
    def commit(self):
        return self._conn.commit()
    
    def rollback(self):
        return self._conn.rollback()
    
    def close(self):
        """Return connection to pool instead of closing it."""
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._conn:
            _pg_pool.putconn(self._conn)
            self._conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


def get_db_sync():
    """Non-context-manager connection getter for legacy code.
    Returns a wrapped connection that auto-returns to pool on close()."""
    if not _pg_pool:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    from psycopg2.extras import DictCursor
    
    conn = _pg_pool.getconn()
    conn.cursor_factory = DictCursor
    return _ConnectionWrapper(conn)


def _init_schema(conn):
    """Create all required tables and columns."""
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # User settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            dob DATE,
            gender VARCHAR(10),
            week_start INTEGER DEFAULT 0,
            height_in NUMERIC(5,2),
            target_bw NUMERIC(6,2),
            activity_level VARCHAR(20),
            onboarded BOOLEAN DEFAULT FALSE,
            last_seen_version VARCHAR(20),
            rep_trigger NUMERIC(5,1) DEFAULT 50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date DATE NOT NULL,
            bw NUMERIC(6,2),
            rd NUMERIC(6,4),
            notes TEXT,
            exercises JSONB DEFAULT '[]'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Exercise bank
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            alias VARCHAR(100),
            tool VARCHAR(50),
            mult NUMERIC(3,1),
            muscles JSONB DEFAULT '[]'::jsonb,
            day VARCHAR(20),
            load_hint VARCHAR(100),
            is_bw BOOLEAN DEFAULT FALSE,
            sort_order INTEGER DEFAULT 0,
            rep_trigger_override INTEGER,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Protocols
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS protocols (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100),
            dose VARCHAR(50),
            frequency VARCHAR(50),
            notes TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_protocols_user_id ON protocols(user_id)")
    
    # Migrate existing exercises table - add missing columns if they don't exist
    cursor.execute("""
        ALTER TABLE exercises
        ADD COLUMN IF NOT EXISTS alias VARCHAR(100),
        ADD COLUMN IF NOT EXISTS tool VARCHAR(50),
        ADD COLUMN IF NOT EXISTS load_hint VARCHAR(100),
        ADD COLUMN IF NOT EXISTS is_bw BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0
    """)
    
    # Add missing AI columns to user_settings if they don't exist
    cursor.execute("""
        ALTER TABLE user_settings
        ADD COLUMN IF NOT EXISTS ai_key_enc TEXT,
        ADD COLUMN IF NOT EXISTS ai_model VARCHAR(100),
        ADD COLUMN IF NOT EXISTS ollama_base_url TEXT,
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    """)
    
    conn.commit()
    cursor.close()
