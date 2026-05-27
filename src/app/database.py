import os
import sqlite3
from pathlib import Path

DATABASE_PATH = Path(os.getenv("DEEPMEMO_DB_PATH", Path(__file__).parent.parent.parent / "data.db"))


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str):
    columns = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

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
    conn.close()
