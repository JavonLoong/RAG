-- Task 3 is additive.  Governance stores immutable revision/publication
-- lifecycle records beside the legacy row publication state and reuses the
-- shared fmea_outbox_events and idempotency_records tables.
CREATE TABLE IF NOT EXISTS fmea_revisions (
    workspace_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    analysis_record_version INTEGER NOT NULL CHECK (analysis_record_version > 0),
    parent_revision_id TEXT,
    parent_revision_hash TEXT,
    revision_hash TEXT NOT NULL,
    revision_json TEXT NOT NULL CHECK (length(revision_json) > 0),
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    canonical_json_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, revision_id),
    UNIQUE (workspace_id, revision_id, record_version),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (substr(revision_hash, 1, 7) = 'sha256:' OR length(revision_hash) = 64),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK ((parent_revision_id IS NULL) = (parent_revision_hash IS NULL)),
    FOREIGN KEY (workspace_id, parent_revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS fmea_revision_readiness_reports (
    workspace_id TEXT NOT NULL,
    readiness_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    target_record_version INTEGER NOT NULL CHECK (target_record_version > 0),
    ready INTEGER NOT NULL CHECK (ready IN (0, 1)),
    blocking_codes_json TEXT NOT NULL CHECK (length(blocking_codes_json) > 0),
    report_hash TEXT NOT NULL,
    report_json TEXT NOT NULL CHECK (length(report_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, readiness_id),
    UNIQUE (workspace_id, revision_id, target_record_version),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(report_hash) IN (64, 71))
    ,FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
);

CREATE TABLE IF NOT EXISTS fmea_approval_submissions (
    workspace_id TEXT NOT NULL,
    submission_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'pending'),
    submitter_actor_id TEXT NOT NULL,
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    submission_json TEXT NOT NULL CHECK (length(submission_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    outbox_event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, submission_id),
    UNIQUE (workspace_id, submission_id, record_version),
    UNIQUE (workspace_id, idempotency_scope),
    UNIQUE (workspace_id, audit_event_id),
    UNIQUE (workspace_id, outbox_event_id),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
);

CREATE TABLE IF NOT EXISTS fmea_approval_decisions (
    workspace_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    submission_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved', 'rejected')),
    approver_actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    decision_json TEXT NOT NULL CHECK (length(decision_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    outbox_event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, approval_id),
    UNIQUE (workspace_id, approval_id, record_version),
    UNIQUE (workspace_id, idempotency_scope),
    UNIQUE (workspace_id, audit_event_id),
    UNIQUE (workspace_id, outbox_event_id),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, submission_id)
        REFERENCES fmea_approval_submissions(workspace_id, submission_id),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
);

CREATE TABLE IF NOT EXISTS fmea_approval_withdrawals (
    workspace_id TEXT NOT NULL,
    withdrawal_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    withdrawal_json TEXT NOT NULL CHECK (length(withdrawal_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    outbox_event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, withdrawal_id),
    UNIQUE (workspace_id, idempotency_scope),
    UNIQUE (workspace_id, audit_event_id),
    UNIQUE (workspace_id, outbox_event_id),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, approval_id)
        REFERENCES fmea_approval_decisions(workspace_id, approval_id),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
);

CREATE TABLE IF NOT EXISTS fmea_publication_manifests (
    workspace_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    version_manifest_hash TEXT NOT NULL,
    previous_audit_chain_head TEXT,
    export_eligible INTEGER NOT NULL CHECK (export_eligible IN (0, 1)),
    manifest_hash TEXT NOT NULL,
    manifest_json TEXT NOT NULL CHECK (length(manifest_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, manifest_id),
    UNIQUE (workspace_id, revision_id, manifest_id),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(snapshot_hash) IN (64, 71)),
    CHECK (length(version_manifest_hash) IN (64, 71)),
    CHECK (length(manifest_hash) IN (64, 71)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id),
    FOREIGN KEY (workspace_id, approval_id)
        REFERENCES fmea_approval_decisions(workspace_id, approval_id)
);

CREATE TABLE IF NOT EXISTS fmea_normalized_snapshots (
    workspace_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    snapshot_json TEXT NOT NULL CHECK (length(snapshot_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, snapshot_id),
    UNIQUE (workspace_id, publication_id),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(snapshot_hash) IN (64, 71)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, manifest_id)
        REFERENCES fmea_publication_manifests(workspace_id, manifest_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS fmea_publications (
    workspace_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    audit_chain_head TEXT NOT NULL,
    publisher_actor_id TEXT NOT NULL,
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    publication_json TEXT NOT NULL CHECK (length(publication_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, publication_id),
    UNIQUE (workspace_id, publication_id, record_version),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(manifest_hash) IN (64, 71)),
    CHECK (length(snapshot_hash) IN (64, 71)),
    CHECK (length(audit_chain_head) IN (64, 71)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id),
    FOREIGN KEY (workspace_id, approval_id)
        REFERENCES fmea_approval_decisions(workspace_id, approval_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, manifest_id)
        REFERENCES fmea_publication_manifests(workspace_id, manifest_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, snapshot_id)
        REFERENCES fmea_normalized_snapshots(workspace_id, snapshot_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS fmea_publication_withdrawals (
    workspace_id TEXT NOT NULL,
    withdrawal_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    replacement_publication_id TEXT,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    withdrawal_json TEXT NOT NULL CHECK (length(withdrawal_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    outbox_event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, withdrawal_id),
    UNIQUE (workspace_id, idempotency_scope),
    UNIQUE (workspace_id, audit_event_id),
    UNIQUE (workspace_id, outbox_event_id),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id),
    FOREIGN KEY (workspace_id, replacement_publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id)
);

CREATE TABLE IF NOT EXISTS fmea_supersessions (
    workspace_id TEXT NOT NULL,
    supersession_id TEXT NOT NULL,
    old_publication_id TEXT NOT NULL,
    new_publication_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    supersession_json TEXT NOT NULL CHECK (length(supersession_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    outbox_event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, supersession_id),
    UNIQUE (workspace_id, idempotency_scope),
    UNIQUE (workspace_id, old_publication_id, new_publication_id),
    UNIQUE (workspace_id, audit_event_id),
    UNIQUE (workspace_id, outbox_event_id),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK (old_publication_id <> new_publication_id),
    FOREIGN KEY (workspace_id, old_publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id),
    FOREIGN KEY (workspace_id, new_publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id)
);

CREATE TABLE IF NOT EXISTS fmea_export_eligibility (
    workspace_id TEXT NOT NULL,
    eligibility_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    eligibility_hash TEXT NOT NULL,
    eligibility_json TEXT NOT NULL CHECK (length(eligibility_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, eligibility_id),
    UNIQUE (workspace_id, publication_id),
    CHECK (length(eligibility_hash) = 71 AND substr(eligibility_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id),
    FOREIGN KEY (workspace_id, manifest_id)
        REFERENCES fmea_publication_manifests(workspace_id, manifest_id)
);

-- The legacy audit_events table is row-bound.  Governance uses this shared
-- audit-chain shape for revision/publication aggregates without creating a
-- second per-feature audit authority.
CREATE TABLE IF NOT EXISTS fmea_audit_events (
    workspace_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('revision', 'approval', 'publication')),
    resource_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'model', 'system')),
    command TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    canonical_payload_hash TEXT NOT NULL,
    event_json TEXT NOT NULL CHECK (length(event_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, event_id),
    UNIQUE (workspace_id, idempotency_scope),
    CHECK (length(canonical_payload_hash) = 71 AND substr(canonical_payload_hash, 1, 7) = 'sha256:')
);

CREATE INDEX IF NOT EXISTS idx_fmea_revisions_workspace_analysis
    ON fmea_revisions(workspace_id, analysis_id, record_version, revision_id);
CREATE INDEX IF NOT EXISTS idx_fmea_revision_readiness_workspace_revision
    ON fmea_revision_readiness_reports(workspace_id, revision_id, target_record_version);
CREATE INDEX IF NOT EXISTS idx_fmea_approval_submissions_workspace_revision
    ON fmea_approval_submissions(workspace_id, revision_id, created_at, submission_id);
CREATE INDEX IF NOT EXISTS idx_fmea_approval_decisions_workspace_revision
    ON fmea_approval_decisions(workspace_id, revision_id, created_at, approval_id);
CREATE INDEX IF NOT EXISTS idx_fmea_approval_withdrawals_workspace_approval
    ON fmea_approval_withdrawals(workspace_id, approval_id, created_at, withdrawal_id);
CREATE INDEX IF NOT EXISTS idx_fmea_publication_manifests_workspace_revision
    ON fmea_publication_manifests(workspace_id, revision_id, created_at, manifest_id);
CREATE INDEX IF NOT EXISTS idx_fmea_publications_workspace_analysis
    ON fmea_publications(workspace_id, analysis_id, created_at, publication_id);
CREATE INDEX IF NOT EXISTS idx_fmea_publication_withdrawals_workspace_publication
    ON fmea_publication_withdrawals(workspace_id, publication_id, created_at, withdrawal_id);
CREATE INDEX IF NOT EXISTS idx_fmea_supersessions_workspace_old_publication
    ON fmea_supersessions(workspace_id, old_publication_id, created_at, supersession_id);
CREATE INDEX IF NOT EXISTS idx_fmea_audit_events_workspace_resource
    ON fmea_audit_events(workspace_id, resource_type, resource_id, created_at, event_id);

CREATE TRIGGER IF NOT EXISTS fmea_revisions_no_update
BEFORE UPDATE ON fmea_revisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_revisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_revisions_no_delete
BEFORE DELETE ON fmea_revisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_revisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_revision_readiness_reports_no_update
BEFORE UPDATE ON fmea_revision_readiness_reports
BEGIN SELECT RAISE(ABORT, 'immutable fmea_revision_readiness_reports'); END;
CREATE TRIGGER IF NOT EXISTS fmea_revision_readiness_reports_no_delete
BEFORE DELETE ON fmea_revision_readiness_reports
BEGIN SELECT RAISE(ABORT, 'immutable fmea_revision_readiness_reports'); END;
CREATE TRIGGER IF NOT EXISTS fmea_approval_submissions_no_update
BEFORE UPDATE ON fmea_approval_submissions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_approval_submissions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_approval_submissions_no_delete
BEFORE DELETE ON fmea_approval_submissions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_approval_submissions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_approval_decisions_no_update
BEFORE UPDATE ON fmea_approval_decisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_approval_decisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_approval_decisions_no_delete
BEFORE DELETE ON fmea_approval_decisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_approval_decisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_approval_withdrawals_no_update
BEFORE UPDATE ON fmea_approval_withdrawals
BEGIN SELECT RAISE(ABORT, 'immutable fmea_approval_withdrawals'); END;
CREATE TRIGGER IF NOT EXISTS fmea_approval_withdrawals_no_delete
BEFORE DELETE ON fmea_approval_withdrawals
BEGIN SELECT RAISE(ABORT, 'immutable fmea_approval_withdrawals'); END;
CREATE TRIGGER IF NOT EXISTS fmea_publication_manifests_no_update
BEFORE UPDATE ON fmea_publication_manifests
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publication_manifests'); END;
CREATE TRIGGER IF NOT EXISTS fmea_publication_manifests_no_delete
BEFORE DELETE ON fmea_publication_manifests
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publication_manifests'); END;
CREATE TRIGGER IF NOT EXISTS fmea_normalized_snapshots_no_update
BEFORE UPDATE ON fmea_normalized_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_normalized_snapshots'); END;
CREATE TRIGGER IF NOT EXISTS fmea_normalized_snapshots_no_delete
BEFORE DELETE ON fmea_normalized_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_normalized_snapshots'); END;
CREATE TRIGGER IF NOT EXISTS fmea_publications_no_update
BEFORE UPDATE ON fmea_publications
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publications'); END;
CREATE TRIGGER IF NOT EXISTS fmea_publications_no_delete
BEFORE DELETE ON fmea_publications
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publications'); END;
CREATE TRIGGER IF NOT EXISTS fmea_publication_withdrawals_no_update
BEFORE UPDATE ON fmea_publication_withdrawals
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publication_withdrawals'); END;
CREATE TRIGGER IF NOT EXISTS fmea_publication_withdrawals_no_delete
BEFORE DELETE ON fmea_publication_withdrawals
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publication_withdrawals'); END;
CREATE TRIGGER IF NOT EXISTS fmea_supersessions_no_update
BEFORE UPDATE ON fmea_supersessions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_supersessions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_supersessions_no_delete
BEFORE DELETE ON fmea_supersessions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_supersessions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_export_eligibility_no_update
BEFORE UPDATE ON fmea_export_eligibility
BEGIN SELECT RAISE(ABORT, 'immutable fmea_export_eligibility'); END;
CREATE TRIGGER IF NOT EXISTS fmea_export_eligibility_no_delete
BEFORE DELETE ON fmea_export_eligibility
BEGIN SELECT RAISE(ABORT, 'immutable fmea_export_eligibility'); END;
CREATE TRIGGER IF NOT EXISTS fmea_audit_events_no_update
BEFORE UPDATE ON fmea_audit_events
BEGIN SELECT RAISE(ABORT, 'immutable fmea_audit_events'); END;
CREATE TRIGGER IF NOT EXISTS fmea_audit_events_no_delete
BEFORE DELETE ON fmea_audit_events
BEGIN SELECT RAISE(ABORT, 'immutable fmea_audit_events'); END;
