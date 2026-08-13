CREATE TABLE IF NOT EXISTS knowledge_scope (
    scope_id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('system', 'temporary')),
    owner_key TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('empty', 'processing', 'ready', 'error', 'deleting', 'deleted')
    ),
    current_version TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_version (
    scope_id TEXT NOT NULL,
    version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    documents_path TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    index_path TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('building', 'validating', 'ready', 'rejected')
    ),
    source_revision TEXT,
    built_at TEXT NOT NULL,
    published_at TEXT,
    PRIMARY KEY (scope_id, version),
    FOREIGN KEY (scope_id) REFERENCES knowledge_scope(scope_id)
);

CREATE TABLE IF NOT EXISTS upload_file (
    file_id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    parse_status TEXT NOT NULL CHECK (
        parse_status IN ('pending', 'parsing', 'ready', 'error', 'deleted')
    ),
    error_code TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scope_id) REFERENCES knowledge_scope(scope_id)
);

CREATE TABLE IF NOT EXISTS job (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL CHECK (
        job_type IN ('ingest_file', 'build_scope', 'publish_public', 'delete_scope')
    ),
    scope_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed')
    ),
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    locked_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (scope_id) REFERENCES knowledge_scope(scope_id)
);

INSERT OR IGNORE INTO knowledge_scope (
    scope_id,
    scope_type,
    owner_key,
    status,
    current_version,
    created_at
) VALUES (
    'legacy',
    'system',
    NULL,
    'ready',
    NULL,
    CURRENT_TIMESTAMP
);

ALTER TABLE session ADD COLUMN owner_key TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE session ADD COLUMN scope_id TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE session ADD COLUMN expires_at TEXT;

ALTER TABLE message ADD COLUMN answer_status TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE message ADD COLUMN knowledge_scope_id TEXT;
ALTER TABLE message ADD COLUMN knowledge_version TEXT;

CREATE INDEX IF NOT EXISTS idx_knowledge_scope_owner_status_expiry
    ON knowledge_scope(owner_key, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_version_scope_status_published
    ON knowledge_version(scope_id, status, published_at);
CREATE INDEX IF NOT EXISTS idx_session_owner_updated
    ON session(owner_key, updated_at);
CREATE INDEX IF NOT EXISTS idx_session_scope_expiry
    ON session(scope_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_message_session_created
    ON message(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_upload_file_scope_status
    ON upload_file(scope_id, parse_status);
CREATE INDEX IF NOT EXISTS idx_job_status_available
    ON job(status, available_at);
CREATE INDEX IF NOT EXISTS idx_job_scope_type_status
    ON job(scope_id, job_type, status);
