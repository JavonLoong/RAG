CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    filename TEXT NOT NULL UNIQUE,
    migration_hash TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fmea_analyses (
    analysis_id TEXT PRIMARY KEY,
    analysis_hash TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_packs (
    pack_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    pack_hash TEXT NOT NULL UNIQUE,
    pack_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS fmea_rows (
    row_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL REFERENCES fmea_analyses(analysis_id),
    evidence_pack_id TEXT NOT NULL REFERENCES evidence_packs(pack_id),
    review_status TEXT NOT NULL CHECK (review_status IN ('draft','suggested','in_review','accepted','rejected','superseded')),
    publication_status TEXT NOT NULL CHECK (publication_status IN ('unpublished','published','withdrawn')),
    record_version INTEGER NOT NULL CHECK (record_version >= 1),
    row_hash TEXT NOT NULL,
    row_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_source_snapshots (
    row_id TEXT PRIMARY KEY REFERENCES fmea_rows(row_id),
    workspace_id TEXT NOT NULL,
    source_record_version INTEGER NOT NULL,
    source_hash TEXT NOT NULL UNIQUE,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fmea_rows_workspace_analysis
    ON fmea_rows(workspace_id, analysis_id);
CREATE INDEX IF NOT EXISTS idx_fmea_rows_workspace_status
    ON fmea_rows(workspace_id, review_status, publication_status);
CREATE INDEX IF NOT EXISTS idx_evidence_packs_workspace
    ON evidence_packs(workspace_id, pack_id);

CREATE TRIGGER IF NOT EXISTS evidence_packs_no_update
BEFORE UPDATE ON evidence_packs
BEGIN
    SELECT RAISE(ABORT, 'immutable evidence_packs');
END;

CREATE TRIGGER IF NOT EXISTS evidence_packs_no_delete
BEFORE DELETE ON evidence_packs
BEGIN
    SELECT RAISE(ABORT, 'immutable evidence_packs');
END;

CREATE TRIGGER IF NOT EXISTS review_source_snapshots_no_update
BEFORE UPDATE ON review_source_snapshots
BEGIN
    SELECT RAISE(ABORT, 'immutable review_source_snapshots');
END;

CREATE TRIGGER IF NOT EXISTS review_source_snapshots_no_delete
BEFORE DELETE ON review_source_snapshots
BEGIN
    SELECT RAISE(ABORT, 'immutable review_source_snapshots');
END;
