"""
Dual-database support: Postgres (primary) + SQLite (fallback).
Auto-migrates SQLite → Postgres on startup.
Provides connection pooling for Postgres via psycopg2.
"""

import os
import json
import sqlite3
import logging
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Environment
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_PATH = os.environ.get("DB_PATH", "/data/sessions.db")

# Global state
_db_engine = None
_pg_pool = None


def init_db():
    """Initialize database: create schema, migrate data, set up pooling."""
    global _db_engine, _pg_pool
    
    if DATABASE_URL:
        try:
            import psycopg2
            from psycopg2 import pool
            
            _pg_pool = pool.SimpleConnectionPool(2, 10, DATABASE_URL)
            _db_engine = "postgres"
            logger.info("✓ Postgres connection pool initialized")
            
            with pg_connection() as conn:
                _init_postgres_schema(conn)
            logger.info("✓ Postgres schema initialized")
            
            migrate_sqlite_to_postgres()
            logger.info("✓ Migration complete (SQLite → Postgres)")
            
        except Exception as e:
            logger.error(f"✗ Postgres init failed: {e}")
            logger.warning("Falling back to SQLite")
            _db_engine = "sqlite"
            _init_sqlite_schema()
    else:
        _db_engine = "sqlite"
        _init_sqlite_schema()
        logger.info("✓ SQLite initialized (no Postgres URL)")


@contextmanager
def get_db():
    """Context manager: get database connection (Postgres or SQLite)."""
    if _db_engine == "postgres":
        with pg_connection() as conn:
            yield conn
    else:
        conn = sqlite_connection()
        try:
            yield conn
        finally:
            conn.close()


def get_db_sync():
    """Backwards-compatible sync connection getter (for gradual refactoring)."""
    if _db_engine == "postgres":
        from psycopg2.extras import DictCursor
        conn = _pg_pool.getconn() if _pg_pool else None
        if conn:
            # Set default cursor factory to DictCursor for row compatibility
            conn.cursor_factory = DictCursor
            # Wrap to convert ? to %s for parameter binding, mark as pool connection
            return _PostgresConnectionWrapper(conn, is_pool_conn=True)
        return None
    else:
        return sqlite_connection()


def put_db_sync(conn):
    """Return Postgres connection to pool (no-op for SQLite)."""
    if _db_engine == "postgres" and _pg_pool:
        # Unwrap if it's a wrapper
        if isinstance(conn, _PostgresConnectionWrapper):
            _pg_pool.putconn(conn._conn)
        else:
            _pg_pool.putconn(conn)


class _PostgresConnectionWrapper:
    """Wrapper to convert SQLite-style ? parameters to Postgres %s."""
    
    def __init__(self, conn, is_pool_conn=False):
        self._conn = conn
        self._is_pool_conn = is_pool_conn
    
    def execute(self, query, params=None):
        """Execute, converting ? to %s."""
        if params:
            query = query.replace("?", "%s")
        cur = self._conn.cursor()
        cur.execute(query, params or [])
        return cur
    
    def executescript(self, script):
        """Execute script (SQLite compat - not ideal but needed)."""
        cur = self._conn.cursor()
        cur.execute(script)
        return cur
    
    def commit(self):
        self._conn.commit()
    
    def rollback(self):
        self._conn.rollback()
    
    def close(self):
        """Close or return to pool."""
        if self._is_pool_conn and _pg_pool:
            _pg_pool.putconn(self._conn)
        else:
            self._conn.close()
    
    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def pg_connection():
    """Get Postgres connection from pool."""
    global _pg_pool
    if not _pg_pool:
        raise RuntimeError("Postgres pool not initialized")
    
    conn = _pg_pool.getconn()
    try:
        # Use DictCursor so rows behave like dicts (sqlite3.Row compatibility)
        from psycopg2.extras import DictCursor
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.close()
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pg_pool.putconn(conn)


def sqlite_connection():
    """Get fresh SQLite connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_sqlite_schema():
    """Initialize SQLite schema."""
    conn = sqlite_connection()
    try:
        # Create all tables (truncated for brevity - same as original)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT NOT NULL UNIQUE,
                hashed_pw  TEXT NOT NULL,
                role       TEXT NOT NULL DEFAULT 'guest',
                status     TEXT NOT NULL DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL DEFAULT 1,
                date          TEXT NOT NULL,
                bw            REAL NOT NULL,
                rd            REAL NOT NULL,
                total_density REAL NOT NULL,
                exercises     TEXT NOT NULL,
                notes         TEXT DEFAULT '',
                created_at    TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id      INTEGER PRIMARY KEY,
                ai_key_enc   TEXT,
                ai_model     TEXT DEFAULT 'gemini-2.5-flash',
                first_name   TEXT,
                last_name    TEXT,
                dob          TEXT,
                gender       TEXT,
                week_start   TEXT DEFAULT 'Saturday',
                height_in    REAL,
                target_bw    REAL,
                activity_level TEXT DEFAULT '1.55',
                onboarded TEXT DEFAULT '0',
                external_api_key TEXT,
                last_seen_version TEXT DEFAULT '0.0.0',
                totp_secret TEXT,
                totp_enabled TEXT DEFAULT '0',
                rep_trigger INTEGER DEFAULT 50,
                updated_at   TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                alias      TEXT,
                tool       TEXT NOT NULL DEFAULT 'Bar',
                mult       REAL NOT NULL DEFAULT 2.0,
                muscles    TEXT NOT NULL DEFAULT '[]',
                day        TEXT,
                load_hint  TEXT,
                is_bw      INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                created_by INTEGER DEFAULT NULL,
                rep_trigger_override INTEGER DEFAULT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS protocols (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                name       TEXT NOT NULL,
                dose       TEXT,
                frequency  TEXT,
                notes      TEXT,
                sort_order INTEGER DEFAULT 0,
                start_date TEXT,
                end_date   TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                username   TEXT,
                event_type TEXT NOT NULL,
                detail     TEXT,
                ip         TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phases (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                phase_type TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date   TEXT,
                notes      TEXT,
                label      TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS insights_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _init_postgres_schema(conn):
    """Initialize Postgres schema."""
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         SERIAL PRIMARY KEY,
                username   TEXT NOT NULL UNIQUE,
                hashed_pw  TEXT NOT NULL,
                role       TEXT NOT NULL DEFAULT 'guest',
                status     TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            SERIAL PRIMARY KEY,
                user_id       INTEGER NOT NULL,
                date          DATE NOT NULL,
                bw            REAL NOT NULL,
                rd            REAL NOT NULL,
                total_density REAL NOT NULL,
                exercises     JSONB NOT NULL,
                notes         TEXT DEFAULT '',
                created_at    TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id           INTEGER PRIMARY KEY REFERENCES users(id),
                ai_key_enc        TEXT,
                ai_model          TEXT DEFAULT 'gemini-2.5-flash',
                first_name        TEXT,
                last_name         TEXT,
                dob               DATE,
                gender            TEXT,
                week_start        TEXT DEFAULT 'Saturday',
                height_in         REAL,
                target_bw         REAL,
                activity_level    TEXT DEFAULT '1.55',
                onboarded         TEXT DEFAULT '0',
                external_api_key  TEXT,
                last_seen_version TEXT DEFAULT '0.0.0',
                totp_secret       TEXT,
                totp_enabled      TEXT DEFAULT '0',
                rep_trigger       INTEGER DEFAULT 50,
                updated_at        TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id                 SERIAL PRIMARY KEY,
                name               TEXT NOT NULL UNIQUE,
                alias              TEXT,
                tool               TEXT NOT NULL DEFAULT 'Bar',
                mult               REAL NOT NULL DEFAULT 2.0,
                muscles            JSONB NOT NULL DEFAULT '[]',
                day                TEXT,
                load_hint          TEXT,
                is_bw              BOOLEAN DEFAULT FALSE,
                sort_order         INTEGER DEFAULT 0,
                created_at         TIMESTAMP DEFAULT NOW(),
                created_by         INTEGER REFERENCES users(id),
                rep_trigger_override INTEGER
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS protocols (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                name       TEXT NOT NULL,
                dose       TEXT,
                frequency  TEXT,
                notes      TEXT,
                sort_order INTEGER DEFAULT 0,
                start_date DATE,
                end_date   DATE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER REFERENCES users(id),
                username   TEXT,
                event_type TEXT NOT NULL,
                detail     TEXT,
                ip         TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS phases (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                phase_type TEXT NOT NULL,
                start_date DATE NOT NULL,
                end_date   DATE,
                notes      TEXT,
                label      TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS insights_messages (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cur.close()
    except Exception as e:
        logger.error(f"Postgres schema creation error: {e}")
        raise


def migrate_sqlite_to_postgres():
    """Migrate data from SQLite to Postgres (idempotent)."""
    if _db_engine != "postgres":
        logger.info("Postgres not active, skipping migration")
        return
    
    # Check if already migrated
    try:
        with pg_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            cur.close()
            if count > 0:
                logger.info(f"Postgres already populated ({count} users), skipping migration")
                return
    except Exception as e:
        logger.error(f"Migration check failed: {e}")
        return
    
    logger.info("Starting SQLite → Postgres migration...")
    
    try:
        sqlite_conn = sqlite_connection()
        sqlite_cur = sqlite_conn.cursor()
    except Exception as e:
        logger.error(f"Could not open SQLite: {e}")
        return
    
    try:
        with pg_connection() as pg_conn:
            pg_cur = pg_conn.cursor()
            
            # Disable FK constraints during migration
            pg_cur.execute("SET CONSTRAINTS ALL DEFERRED")
            
            # Migrate users first
            sqlite_cur.execute("SELECT id, username, hashed_pw, role, status, created_at FROM users")
            user_ids = set()
            for row in sqlite_cur.fetchall():
                user_ids.add(row[0])
                try:
                    pg_cur.execute("""
                        INSERT INTO users (id, username, hashed_pw, role, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, row)
                except Exception as e:
                    logger.warning(f"User insert failed: {e}")
            pg_conn.commit()
            logger.info(f"✓ Users migrated ({len(user_ids)} users)")
            
            # Migrate sessions (only those with valid user_id)
            sqlite_cur.execute("""
                SELECT id, user_id, date, bw, rd, total_density, exercises, created_at, notes
                FROM sessions
            """)
            session_count = 0
            for row in sqlite_cur.fetchall():
                if row[1] not in user_ids:
                    logger.warning(f"Skipping session {row[0]}: user_id {row[1]} does not exist")
                    continue
                try:
                    pg_cur.execute("""
                        INSERT INTO sessions
                        (id, user_id, date, bw, rd, total_density, exercises, created_at, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, row)
                    session_count += 1
                except Exception as e:
                    logger.warning(f"Session insert failed: {e}")
            pg_conn.commit()
            logger.info(f"✓ Sessions migrated ({session_count} sessions)")
            
            # Migrate user_settings, exercises, protocols, events, phases, insights_messages
            for table in ["user_settings", "exercises", "protocols", "events", "phases", "insights_messages"]:
                try:
                    sqlite_cur.execute(f"SELECT * FROM {table}")
                    cols = [d[0] for d in sqlite_cur.description]
                    migrated = 0
                    for row in sqlite_cur.fetchall():
                        # For tables with user_id, check if user exists
                        if "user_id" in cols:
                            user_id_idx = cols.index("user_id")
                            if row[user_id_idx] not in user_ids:
                                logger.warning(f"Skipping {table} record: user_id {row[user_id_idx]} does not exist")
                                continue
                        placeholders = ", ".join(["%s"] * len(cols))
                        col_str = ", ".join(cols)
                        try:
                            pg_cur.execute(f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING", row)
                            migrated += 1
                        except Exception as e:
                            logger.warning(f"{table} insert failed: {e}")
                    pg_conn.commit()
                    logger.info(f"✓ {table} migrated ({migrated} records)")
                except Exception as e:
                    logger.warning(f"{table} migration: {e}")
            
            pg_cur.close()
            logger.info("✓ Migration complete")
            
    except Exception as e:
        logger.error(f"Postgres migration failed: {e}")
    finally:
        sqlite_conn.close()
