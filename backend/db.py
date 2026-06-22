"""
Postgres connection pooling and schema initialization.
"""

import os
import logging
import contextvars
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
_pg_pool = None

# Per-request registry of connections handed out via get_db_sync(). A middleware
# opens a scope at the start of each request and reaps any connection that wasn't
# released, so a stray exception between get_db() and conn.close() can never leak
# a pooled connection. This is what keeps the 10-slot pool from silently draining.
_request_conns = contextvars.ContextVar("agon_request_conns", default=None)


def begin_request_scope():
    """Start a per-request connection scope. Returns a token for end_request_scope()."""
    return _request_conns.set([])


def end_request_scope(token):
    """Reap any connection checked out during the request but not released."""
    bucket = _request_conns.get()
    if bucket:
        for w in bucket:
            try:
                if getattr(w, "_conn", None) is not None:
                    # Leaked due to an exception path — roll back any open/aborted
                    # transaction before returning the connection to the pool so the
                    # next borrower doesn't inherit a poisoned session.
                    try:
                        w._conn.rollback()
                    except Exception:
                        pass
                    w.close()
            except Exception:
                pass
    try:
        _request_conns.reset(token)
    except Exception:
        pass


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
    """Wrapper for psycopg2 connections from the pool that ensures proper cleanup."""
    def __init__(self, conn):
        self._conn = conn
        self._cursor = None
    
    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)
    
    @property
    def rowcount(self):
        if self._cursor:
            return self._cursor.rowcount
        return 0
    
    def execute(self, sql, params=None):
        """Execute SQL using native psycopg2 %s placeholders."""
        if not self._cursor:
            self._cursor = self._conn.cursor()
        self._cursor.execute(sql, params)
        return self
    
    def fetchone(self):
        if self._cursor:
            return self._cursor.fetchone()
        return None
    
    def fetchall(self):
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
    wrapper = _ConnectionWrapper(conn)
    # Track this connection for the current request so it gets reclaimed even if
    # the caller never reaches its conn.close() (e.g. an exception fires first).
    bucket = _request_conns.get()
    if bucket is not None:
        bucket.append(wrapper)
    return wrapper


def _init_schema(conn):
    """Create all required tables and columns."""
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            hashed_pw TEXT NOT NULL,
            role VARCHAR(20) DEFAULT 'guest',
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # User settings (one row per user; holds profile, MFA, AI, and external-key state)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            dob DATE,
            gender VARCHAR(10),
            week_start VARCHAR(12) DEFAULT 'Saturday',
            height_in NUMERIC(5,2),
            target_bw NUMERIC(6,2),
            activity_level VARCHAR(20),
            onboarded VARCHAR(4) DEFAULT '0',
            last_seen_version VARCHAR(20) DEFAULT '0.0.0',
            rep_trigger NUMERIC(5,1) DEFAULT 50,
            set_time NUMERIC(4,2) DEFAULT 1.5,
            ollama_base_url TEXT,
            totp_secret TEXT,
            totp_enabled VARCHAR(4) DEFAULT '0',
            ai_key_enc TEXT,
            ai_model VARCHAR(100),
            external_api_key TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            total_density NUMERIC(6,4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
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
            start_date DATE,
            end_date DATE,
            sort_order INTEGER DEFAULT 0,
            track BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: add track column if it doesn't exist yet
    cursor.execute("""
        ALTER TABLE protocols ADD COLUMN IF NOT EXISTS track BOOLEAN DEFAULT FALSE
    """)

    # Phases (training blocks: weight-loss, recomp, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS phases (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            phase_type VARCHAR(50) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE,
            notes TEXT,
            label VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # AI Insights conversation history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS insights_messages (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Event / audit log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            username VARCHAR(255),
            event_type VARCHAR(50),
            detail TEXT,
            ip VARCHAR(64),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_protocols_user_id ON protocols(user_id)")
    
    # Fix protocols sequence if out of sync
    cursor.execute("SELECT MAX(id) FROM protocols")
    max_id = cursor.fetchone()[0]
    if max_id:
        cursor.execute(f"SELECT setval('protocols_id_seq', {max_id + 1})")
    
    # Add missing columns to sessions if they don't exist
    cursor.execute("""
        ALTER TABLE sessions
        ADD COLUMN IF NOT EXISTS total_density NUMERIC(6,4),
        ADD COLUMN IF NOT EXISTS sleep_hours NUMERIC(4,2),
        ADD COLUMN IF NOT EXISTS deep_sleep_pct SMALLINT
    """)
    
    # Add unique constraint on (user_id, date) if it doesn't exist
    # Check if constraint already exists
    cursor.execute("""
        SELECT 1 FROM information_schema.constraint_column_usage 
        WHERE table_name='sessions' AND column_name='date' AND constraint_name LIKE '%user_id%date%'
    """)
    if not cursor.fetchone():
        try:
            cursor.execute("ALTER TABLE sessions ADD UNIQUE(user_id, date)")
        except Exception:
            pass  # Constraint might already exist, ignore
    
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

    # Add remaining user_settings columns the app relies on (MFA, external key,
    # profile fields) so a partially-migrated database is brought fully up to date.
    cursor.execute("""
        ALTER TABLE user_settings
        ADD COLUMN IF NOT EXISTS totp_secret TEXT,
        ADD COLUMN IF NOT EXISTS totp_enabled VARCHAR(4) DEFAULT '0',
        ADD COLUMN IF NOT EXISTS external_api_key TEXT,
        ADD COLUMN IF NOT EXISTS activity_level VARCHAR(20),
        ADD COLUMN IF NOT EXISTS height_in NUMERIC(5,2),
        ADD COLUMN IF NOT EXISTS target_bw NUMERIC(6,2),
        ADD COLUMN IF NOT EXISTS onboarded VARCHAR(4) DEFAULT '0',
        ADD COLUMN IF NOT EXISTS last_seen_version VARCHAR(20) DEFAULT '0.0.0',
        ADD COLUMN IF NOT EXISTS rep_trigger NUMERIC(5,1) DEFAULT 50,
        ADD COLUMN IF NOT EXISTS set_time NUMERIC(4,2) DEFAULT 1.5
    """)

    # Add protocol start/end date tracking if missing
    cursor.execute("""
        ALTER TABLE protocols
        ADD COLUMN IF NOT EXISTS start_date DATE,
        ADD COLUMN IF NOT EXISTS end_date DATE
    """)

    # Indexes for the tables added above
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_phases_user_id ON phases(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_user_id ON insights_messages(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_username ON events(username)")
    
    # Reset sequences to prevent duplicate key violations
    cursor.execute("SELECT setval('insights_messages_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM insights_messages))")
    cursor.execute("SELECT setval('events_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM events))")
    cursor.execute("SELECT setval('exercises_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM exercises))")
    cursor.execute("SELECT setval('sessions_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM sessions))")
    cursor.execute("SELECT setval('users_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM users))")

    # Normalize protocol notes: strip spaces after commas (e.g. "KLOW, 5-AMINO" → "KLOW,5-AMINO")
    cursor.execute("""
        UPDATE protocols SET notes = REGEXP_REPLACE(notes, ',\\s+', ',', 'g')
        WHERE notes ~ ',\\s+'
    """)

    # Rename "Low Bar Squat" → "Back Squat" everywhere
    # If "Back Squat" already exists, just delete the duplicate row; otherwise rename it.
    cursor.execute("""
        DELETE FROM exercises WHERE name = 'Low Bar Squat'
          AND EXISTS (SELECT 1 FROM exercises e2 WHERE e2.name = 'Back Squat')
    """)
    cursor.execute("""
        UPDATE exercises SET name = 'Back Squat' WHERE name = 'Low Bar Squat'
    """)
    cursor.execute("""
        UPDATE sessions
        SET exercises = (
            SELECT jsonb_agg(
                CASE
                    WHEN ex->>'name' = 'Low Bar Squat'
                    THEN jsonb_set(ex, '{name}', '"Back Squat"')
                    ELSE ex
                END
            )
            FROM jsonb_array_elements(exercises) AS ex
        )
        WHERE exercises::text LIKE '%Low Bar Squat%'
    """)

    conn.commit()
    cursor.close()
