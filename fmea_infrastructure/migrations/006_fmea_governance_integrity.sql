-- Review round 1 adds only integrity metadata to the Task 3 tables.  The
-- existing migration 005 remains checksum-stable for already initialized DBs.
ALTER TABLE fmea_analyses ADD COLUMN workspace_id TEXT;

UPDATE fmea_analyses
SET workspace_id = (
    SELECT MIN(row.workspace_id)
    FROM fmea_rows AS row
    WHERE row.analysis_id = fmea_analyses.analysis_id
)
WHERE workspace_id IS NULL;

ALTER TABLE fmea_revisions ADD COLUMN audit_event_id TEXT;
ALTER TABLE fmea_revisions ADD COLUMN outbox_event_id TEXT;
ALTER TABLE fmea_publications ADD COLUMN audit_event_id TEXT;
ALTER TABLE fmea_publications ADD COLUMN outbox_event_id TEXT;

ALTER TABLE fmea_revision_readiness_reports ADD COLUMN source_hashes_json TEXT;
ALTER TABLE fmea_revision_readiness_reports ADD COLUMN canonical_json_hash TEXT;
ALTER TABLE fmea_revision_readiness_reports ADD COLUMN idempotency_scope TEXT;
ALTER TABLE fmea_revision_readiness_reports ADD COLUMN payload_hash TEXT;
ALTER TABLE fmea_revision_readiness_reports ADD COLUMN audit_event_id TEXT;
ALTER TABLE fmea_revision_readiness_reports ADD COLUMN outbox_event_id TEXT;

ALTER TABLE fmea_export_eligibility ADD COLUMN source_hashes_json TEXT;
ALTER TABLE fmea_export_eligibility ADD COLUMN canonical_json_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_analyses_workspace_analysis
    ON fmea_analyses(workspace_id, analysis_id)
    WHERE workspace_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_revisions_audit_event
    ON fmea_revisions(workspace_id, audit_event_id)
    WHERE audit_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_revisions_outbox_event
    ON fmea_revisions(workspace_id, outbox_event_id)
    WHERE outbox_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_publications_audit_event
    ON fmea_publications(workspace_id, audit_event_id)
    WHERE audit_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_publications_outbox_event
    ON fmea_publications(workspace_id, outbox_event_id)
    WHERE outbox_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_readiness_idempotency_scope
    ON fmea_revision_readiness_reports(workspace_id, idempotency_scope)
    WHERE idempotency_scope IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_readiness_audit_event
    ON fmea_revision_readiness_reports(workspace_id, audit_event_id)
    WHERE audit_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_readiness_outbox_event
    ON fmea_revision_readiness_reports(workspace_id, outbox_event_id)
    WHERE outbox_event_id IS NOT NULL;

-- SQLite cannot add foreign keys to an existing table with ALTER TABLE.  This
-- shared binding table supplies workspace-qualified, deferrable authority
-- links for the exact audit/outbox pair stored by each governance record.
CREATE TABLE IF NOT EXISTS fmea_governance_event_bindings (
    workspace_id TEXT NOT NULL,
    resource_type TEXT NOT NULL CHECK (
        resource_type IN ('revision', 'approval_submission', 'approval',
                          'readiness', 'approval_withdrawal', 'publication',
                          'publication_withdrawal', 'supersession')
    ),
    resource_id TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    outbox_event_id TEXT NOT NULL,
    PRIMARY KEY (workspace_id, resource_type, resource_id),
    UNIQUE (workspace_id, audit_event_id),
    UNIQUE (workspace_id, outbox_event_id),
    FOREIGN KEY (workspace_id, audit_event_id)
        REFERENCES fmea_audit_events(workspace_id, event_id),
    FOREIGN KEY (workspace_id, outbox_event_id)
        REFERENCES fmea_outbox_events(workspace_id, event_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_fmea_governance_bindings_resource
    ON fmea_governance_event_bindings(workspace_id, resource_type, resource_id);

CREATE TRIGGER IF NOT EXISTS fmea_governance_event_bindings_no_update
BEFORE UPDATE ON fmea_governance_event_bindings
BEGIN SELECT RAISE(ABORT, 'immutable fmea_governance_event_bindings'); END;
CREATE TRIGGER IF NOT EXISTS fmea_governance_event_bindings_no_delete
BEFORE DELETE ON fmea_governance_event_bindings
BEGIN SELECT RAISE(ABORT, 'immutable fmea_governance_event_bindings'); END;
