-- Task 4 export delivery is additive. Migration 010 is an accepted Task 3
-- artifact and must remain byte-for-byte stable.
--
-- Version 010 exposed placeholder export tables before authoritative export
-- writes existed. There is no sound way to invent actor/idempotency/audit
-- authority for legacy rows, so the upgrade explicitly rejects non-empty
-- placeholder tables and leaves version 010 intact.

CREATE TEMP TABLE fmea_export_011_guard (
    legacy_row_count INTEGER NOT NULL,
    CONSTRAINT fmea_export_011_requires_empty_legacy_tables CHECK (legacy_row_count = 0)
);

INSERT INTO fmea_export_011_guard(legacy_row_count)
SELECT
    (SELECT COUNT(*) FROM fmea_export_runs)
    + (SELECT COUNT(*) FROM fmea_export_artifacts);

DROP TABLE fmea_export_011_guard;

DROP TABLE fmea_export_artifacts;
DROP TABLE fmea_export_runs;

CREATE TABLE fmea_export_runs (
    workspace_id TEXT NOT NULL,
    export_run_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    snapshot_id TEXT,
    snapshot_hash TEXT NOT NULL,
    publication_id TEXT,
    format TEXT NOT NULL CHECK (format IN ('json', 'xlsx', 'docx')),
    draft_preview INTEGER NOT NULL CHECK (draft_preview IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    created_at TEXT NOT NULL,
    filename TEXT,
    artifact_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    actor_id TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    request_json TEXT NOT NULL CHECK (length(request_json) > 0),
    request_hash TEXT NOT NULL,
    audit_event_id TEXT,
    outbox_event_id TEXT,
    run_json TEXT NOT NULL CHECK (length(run_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    PRIMARY KEY (workspace_id, export_run_id),
    UNIQUE (workspace_id, idempotency_scope),
    CHECK ((draft_preview = 1) = (publication_id IS NULL)),
    CHECK (length(request_hash) = 71 AND substr(request_hash, 1, 7) = 'sha256:'),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK (
        (status = 'queued' AND started_at IS NULL AND finished_at IS NULL AND artifact_id IS NULL
            AND error IS NULL AND audit_event_id IS NULL AND outbox_event_id IS NULL)
        OR (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL AND artifact_id IS NULL
            AND error IS NULL AND audit_event_id IS NULL AND outbox_event_id IS NULL)
        OR (status = 'succeeded' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND artifact_id IS NOT NULL
            AND error IS NULL AND audit_event_id IS NOT NULL AND outbox_event_id IS NOT NULL)
        OR (status = 'failed' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND artifact_id IS NULL
            AND error IS NOT NULL AND audit_event_id IS NULL AND outbox_event_id IS NULL)
    ),
    CHECK (created_at <= started_at OR started_at IS NULL),
    CHECK (started_at <= finished_at OR finished_at IS NULL),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id),
    FOREIGN KEY (workspace_id, snapshot_id)
        REFERENCES fmea_normalized_snapshots(workspace_id, snapshot_id),
    FOREIGN KEY (workspace_id, publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id),
    FOREIGN KEY (workspace_id, audit_event_id)
        REFERENCES fmea_audit_events(workspace_id, event_id),
    FOREIGN KEY (outbox_event_id)
        REFERENCES fmea_outbox_events(event_id),
    FOREIGN KEY (idempotency_scope)
        REFERENCES idempotency_records(scope_key)
);

CREATE TABLE fmea_export_artifacts (
    workspace_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    export_run_id TEXT NOT NULL,
    publication_id TEXT,
    revision_id TEXT NOT NULL,
    snapshot_id TEXT,
    snapshot_hash TEXT NOT NULL,
    format TEXT NOT NULL CHECK (format IN ('json', 'xlsx', 'docx')),
    media_type TEXT NOT NULL,
    byte_length INTEGER NOT NULL CHECK (byte_length >= 0),
    sha256 TEXT NOT NULL,
    draft_preview INTEGER NOT NULL CHECK (draft_preview IN (0, 1)),
    created_at TEXT NOT NULL,
    filename TEXT,
    artifact_json TEXT NOT NULL CHECK (length(artifact_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    PRIMARY KEY (workspace_id, artifact_id),
    UNIQUE (workspace_id, export_run_id),
    CHECK ((draft_preview = 1) = (publication_id IS NULL)),
    CHECK (length(sha256) = 71 AND substr(sha256, 1, 7) = 'sha256:'),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, export_run_id)
        REFERENCES fmea_export_runs(workspace_id, export_run_id),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id),
    FOREIGN KEY (workspace_id, snapshot_id)
        REFERENCES fmea_normalized_snapshots(workspace_id, snapshot_id),
    FOREIGN KEY (workspace_id, publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id)
);

CREATE INDEX idx_fmea_export_runs_workspace_revision
    ON fmea_export_runs(workspace_id, revision_id, created_at, export_run_id);
CREATE INDEX idx_fmea_export_artifacts_workspace_revision
    ON fmea_export_artifacts(workspace_id, revision_id, created_at, artifact_id);

CREATE TRIGGER fmea_export_artifacts_no_update
BEFORE UPDATE ON fmea_export_artifacts
BEGIN SELECT RAISE(ABORT, 'immutable fmea_export_artifacts'); END;
CREATE TRIGGER fmea_export_artifacts_no_delete
BEFORE DELETE ON fmea_export_artifacts
BEGIN SELECT RAISE(ABORT, 'immutable fmea_export_artifacts'); END;

CREATE TRIGGER fmea_export_runs_immutable_fields
BEFORE UPDATE ON fmea_export_runs
WHEN NEW.workspace_id IS NOT OLD.workspace_id
    OR NEW.export_run_id IS NOT OLD.export_run_id
    OR NEW.revision_id IS NOT OLD.revision_id
    OR NEW.snapshot_id IS NOT OLD.snapshot_id
    OR NEW.snapshot_hash IS NOT OLD.snapshot_hash
    OR NEW.publication_id IS NOT OLD.publication_id
    OR NEW.format IS NOT OLD.format
    OR NEW.draft_preview IS NOT OLD.draft_preview
    OR NEW.created_at IS NOT OLD.created_at
    OR NEW.filename IS NOT OLD.filename
    OR NEW.actor_id IS NOT OLD.actor_id
    OR NEW.idempotency_scope IS NOT OLD.idempotency_scope
    OR NEW.request_json IS NOT OLD.request_json
    OR NEW.request_hash IS NOT OLD.request_hash
BEGIN SELECT RAISE(ABORT, 'immutable fmea_export_runs binding'); END;

CREATE TRIGGER fmea_export_runs_status_transition
BEFORE UPDATE ON fmea_export_runs
WHEN NEW.status IS NOT OLD.status AND NOT (
    (OLD.status = 'queued' AND NEW.status IN ('running', 'failed'))
    OR (OLD.status = 'running' AND NEW.status IN ('succeeded', 'failed'))
)
BEGIN SELECT RAISE(ABORT, 'invalid fmea_export_runs status transition'); END;

CREATE TRIGGER fmea_export_runs_completion_binding
BEFORE UPDATE ON fmea_export_runs
WHEN NEW.status = 'succeeded' AND NOT (
    EXISTS (
        SELECT 1 FROM fmea_export_artifacts AS artifact
        WHERE artifact.workspace_id = NEW.workspace_id
          AND artifact.artifact_id = NEW.artifact_id
          AND artifact.export_run_id = NEW.export_run_id
          AND artifact.revision_id = NEW.revision_id
          AND artifact.snapshot_id IS NEW.snapshot_id
          AND artifact.snapshot_hash = NEW.snapshot_hash
          AND artifact.publication_id IS NEW.publication_id
          AND artifact.format = NEW.format
          AND artifact.draft_preview = NEW.draft_preview
          AND artifact.filename IS NEW.filename
    )
    AND EXISTS (
        SELECT 1 FROM fmea_audit_events AS audit
        WHERE audit.workspace_id = NEW.workspace_id
          AND audit.event_id = NEW.audit_event_id
          AND audit.resource_type = 'revision'
          AND audit.resource_id = NEW.revision_id
          AND audit.actor_id = NEW.actor_id
          AND audit.actor_type = 'human'
          AND audit.command = 'fmea.export.start'
          AND audit.idempotency_scope = NEW.idempotency_scope
          AND audit.canonical_payload_hash = NEW.request_hash
          AND audit.created_at = NEW.finished_at
    )
    AND EXISTS (
        SELECT 1 FROM fmea_outbox_events AS outbox
        WHERE outbox.workspace_id = NEW.workspace_id
          AND outbox.event_id = NEW.outbox_event_id
          AND outbox.aggregate_type = 'fmea_governance'
          AND outbox.aggregate_id = NEW.revision_id
          AND outbox.event_type = 'export.completed'
          AND outbox.status = 'pending'
          AND outbox.idempotency_scope = NEW.idempotency_scope
          AND outbox.created_at = NEW.finished_at
    )
    AND EXISTS (
        SELECT 1 FROM idempotency_records AS idempotency
        WHERE idempotency.scope_key = NEW.idempotency_scope
          AND idempotency.payload_hash = NEW.request_hash
          AND idempotency.state IN ('reserved', 'completed')
    )
)
BEGIN SELECT RAISE(ABORT, 'export completion authority chain mismatch'); END;

CREATE TRIGGER fmea_export_runs_terminal_no_update
BEFORE UPDATE ON fmea_export_runs
WHEN OLD.status IN ('succeeded', 'failed')
BEGIN SELECT RAISE(ABORT, 'immutable terminal fmea_export_runs'); END;

CREATE TRIGGER fmea_export_runs_no_delete
BEFORE DELETE ON fmea_export_runs
BEGIN SELECT RAISE(ABORT, 'immutable fmea_export_runs'); END;
