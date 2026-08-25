CREATE TABLE IF NOT EXISTS review_suggestion_runs (
    run_id TEXT PRIMARY KEY,
    row_id TEXT NOT NULL REFERENCES fmea_rows(row_id),
    workspace_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    source_record_version INTEGER NOT NULL CHECK (source_record_version > 0),
    status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
    request_hash TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL UNIQUE,
    suggestion_id TEXT,
    error_code TEXT,
    retryable INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0,1)),
    request_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS review_suggestions (
    suggestion_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES review_suggestion_runs(run_id),
    row_id TEXT NOT NULL REFERENCES fmea_rows(row_id),
    workspace_id TEXT NOT NULL,
    source_record_version INTEGER NOT NULL CHECK (source_record_version > 0),
    stale INTEGER NOT NULL CHECK (stale IN (0,1)),
    suggestion_json TEXT NOT NULL,
    suggestion_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id TEXT PRIMARY KEY,
    row_id TEXT NOT NULL REFERENCES fmea_rows(row_id),
    workspace_id TEXT NOT NULL,
    previous_record_version INTEGER NOT NULL CHECK (previous_record_version > 0),
    record_version INTEGER NOT NULL CHECK (record_version = previous_record_version + 1),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('accept','modify_and_accept','reject','request_evidence','defer')),
    reason_code TEXT NOT NULL CHECK (reason_code IN ('ACCEPT_AS_IS','FIELD_CORRECTION','UNSUPPORTED_CLAIM','CONFLICT_UNRESOLVED','EVIDENCE_REQUIRED','DEFERRED_FOR_EXPERT','HUMAN_OVERRIDE','OTHER')),
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (row_id, record_version)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    row_id TEXT NOT NULL REFERENCES fmea_rows(row_id),
    workspace_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human','model','system')),
    command TEXT NOT NULL,
    action TEXT,
    suggestion_id TEXT,
    decision_id TEXT,
    expected_record_version INTEGER,
    applied_record_version INTEGER,
    before_hash TEXT,
    after_hash TEXT,
    canonical_payload_hash TEXT NOT NULL,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_records (
    scope_key TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('reserved','completed')),
    status_code INTEGER,
    resource_id TEXT,
    response_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_review_runs_workspace_row
    ON review_suggestion_runs(workspace_id, row_id, created_at, run_id);
CREATE INDEX IF NOT EXISTS idx_review_suggestions_workspace_row
    ON review_suggestions(workspace_id, row_id, created_at, suggestion_id);
CREATE INDEX IF NOT EXISTS idx_review_decisions_workspace_row
    ON review_decisions(workspace_id, row_id, record_version, decision_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_workspace_row
    ON audit_events(workspace_id, row_id, created_at, event_id);

CREATE TRIGGER IF NOT EXISTS review_suggestions_no_update
BEFORE UPDATE ON review_suggestions
BEGIN
    SELECT RAISE(ABORT, 'immutable review_suggestions');
END;

CREATE TRIGGER IF NOT EXISTS review_suggestions_no_delete
BEFORE DELETE ON review_suggestions
BEGIN
    SELECT RAISE(ABORT, 'immutable review_suggestions');
END;

CREATE TRIGGER IF NOT EXISTS review_decisions_no_update
BEFORE UPDATE ON review_decisions
BEGIN
    SELECT RAISE(ABORT, 'immutable review_decisions');
END;

CREATE TRIGGER IF NOT EXISTS review_decisions_no_delete
BEFORE DELETE ON review_decisions
BEGIN
    SELECT RAISE(ABORT, 'immutable review_decisions');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'immutable audit_events');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'immutable audit_events');
END;
