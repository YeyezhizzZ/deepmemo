import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

DATABASE_PATH = Path(os.getenv("DEEPMEMO_DB_PATH", Path(__file__).parent.parent.parent / "data.db"))
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def connection_scope() -> Iterator[sqlite3.Connection]:
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str):
    columns = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def run_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migration (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    applied = {
        row["version"]
        for row in conn.execute("SELECT version FROM schema_migration").fetchall()
    }

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        applied_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        version = path.name.replace("'", "''")
        timestamp = applied_at.replace("'", "''")
        script = "\n".join(
            [
                "BEGIN IMMEDIATE;",
                path.read_text(encoding="utf-8"),
                (
                    "INSERT INTO schema_migration (version, applied_at) "
                    f"VALUES ('{version}', '{timestamp}');"
                ),
                "COMMIT;",
            ]
        )
        try:
            conn.executescript(script)
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    conn.execute("PRAGMA journal_mode = WAL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session (
            session_id TEXT PRIMARY KEY,
            session_name TEXT NOT NULL,
            message_ids TEXT NOT NULL DEFAULT '[]',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    ensure_column(cursor, "session", "session_topic", "session_topic TEXT DEFAULT ''")
    ensure_column(cursor, "session", "session_summary", "session_summary TEXT DEFAULT ''")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'ai')),
            content TEXT NOT NULL,
            citations TEXT DEFAULT '[]',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES session(session_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_meta (
            id TEXT PRIMARY KEY,
            file_path TEXT UNIQUE,
            file_hash TEXT,
            sync_status TEXT NOT NULL CHECK (
                sync_status IN ('synced', 'dirty', 'draft', 'processing', 'error')
            ),
            last_modified DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    run_migrations(conn)
    conn.close()
