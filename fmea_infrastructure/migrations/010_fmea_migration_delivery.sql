-- Task 3 delivery persistence is additive after the immutable governance
-- sequence 005-009.  The tables below retain the typed application payloads
-- together with their canonical hashes so SQLite is a durable replay store,
-- not a second source of domain semantics.

CREATE TABLE fmea_template_drafts (
    workspace_id TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('xlsx', 'docx')),
    structure_json TEXT NOT NULL CHECK (length(structure_json) > 0),
    proposed_fields_json TEXT NOT NULL CHECK (length(proposed_fields_json) > 0),
    unknown_fields_json TEXT NOT NULL CHECK (length(unknown_fields_json) > 0),
    ambiguous_fields_json TEXT NOT NULL CHECK (length(ambiguous_fields_json) > 0),
    parser_warnings_json TEXT NOT NULL CHECK (length(parser_warnings_json) > 0),
    identified_fields_json TEXT NOT NULL CHECK (length(identified_fields_json) > 0),
    status TEXT NOT NULL CHECK (status = 'draft'),
    draft_json TEXT NOT NULL CHECK (length(draft_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, draft_id),
    UNIQUE (workspace_id, source_sha256, draft_id),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:')
);

CREATE TABLE fmea_template_patch_candidates (
    workspace_id TEXT NOT NULL,
    patch_id TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    input_template_version TEXT NOT NULL,
    target_template_id TEXT NOT NULL,
    target_template_version TEXT NOT NULL,
    target_template_hash TEXT NOT NULL,
    domain_pack_id TEXT NOT NULL,
    domain_pack_version TEXT NOT NULL,
    domain_pack_hash TEXT NOT NULL,
    evidence_pack_id TEXT NOT NULL,
    evidence_pack_hash TEXT NOT NULL,
    run_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    diff_json TEXT NOT NULL CHECK (length(diff_json) > 0),
    evidence_ids_json TEXT NOT NULL CHECK (length(evidence_ids_json) > 0),
    status TEXT NOT NULL CHECK (status = 'suggested'),
    applied INTEGER NOT NULL CHECK (applied = 0),
    candidate_json TEXT NOT NULL CHECK (length(candidate_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, patch_id),
    UNIQUE (workspace_id, draft_id, patch_id),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, draft_id)
        REFERENCES fmea_template_drafts(workspace_id, draft_id)
);

CREATE TABLE fmea_template_patch_decisions (
    workspace_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    suggestion_id TEXT NOT NULL,
    patch_id TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type = 'human'),
    action TEXT NOT NULL CHECK (action IN ('accepted', 'rejected')),
    reason TEXT NOT NULL,
    base_template_id TEXT NOT NULL,
    base_template_version TEXT NOT NULL,
    base_template_hash TEXT NOT NULL,
    new_template_version TEXT,
    candidate_json TEXT NOT NULL CHECK (length(candidate_json) > 0),
    decision_json TEXT NOT NULL CHECK (length(decision_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, decision_id),
    UNIQUE (workspace_id, patch_id),
    CHECK ((action = 'accepted') = (new_template_version IS NOT NULL)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, patch_id)
        REFERENCES fmea_template_patch_candidates(workspace_id, patch_id),
    FOREIGN KEY (workspace_id, draft_id)
        REFERENCES fmea_template_drafts(workspace_id, draft_id)
);

CREATE TABLE fmea_migration_runs (
    workspace_id TEXT NOT NULL,
    migration_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    source_revision_id TEXT NOT NULL,
    source_revision_hash TEXT NOT NULL,
    target_domain_pack_id TEXT NOT NULL,
    target_domain_pack_version TEXT NOT NULL,
    target_domain_pack_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('dry_run', 'confirmed', 'failed')),
    request_json TEXT NOT NULL CHECK (length(request_json) > 0),
    request_hash TEXT NOT NULL,
    report_id TEXT,
    report_hash TEXT,
    child_revision_id TEXT,
    idempotency_scope TEXT,
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    PRIMARY KEY (workspace_id, migration_id),
    UNIQUE (workspace_id, run_id),
    CHECK (length(request_hash) = 71 AND substr(request_hash, 1, 7) = 'sha256:'),
    CHECK (report_hash IS NULL OR length(report_hash) IN (64, 71)),
    CHECK (status <> 'confirmed' OR child_revision_id IS NOT NULL),
    CHECK (status = 'dry_run' OR finished_at IS NOT NULL)
);

CREATE TABLE fmea_migration_reports (
    workspace_id TEXT NOT NULL,
    report_id TEXT NOT NULL,
    migration_id TEXT NOT NULL,
    source_revision_id TEXT NOT NULL,
    source_revision_hash TEXT NOT NULL,
    target_domain_pack_id TEXT NOT NULL,
    target_domain_pack_version TEXT NOT NULL,
    target_domain_pack_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('dry_run', 'confirmed', 'failed')),
    plan_json TEXT NOT NULL CHECK (length(plan_json) > 0),
    report_json TEXT NOT NULL CHECK (length(report_json) > 0),
    report_hash TEXT NOT NULL,
    canonical_json_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, report_id),
    UNIQUE (workspace_id, migration_id),
    CHECK (length(report_hash) IN (64, 71)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, migration_id)
        REFERENCES fmea_migration_runs(workspace_id, migration_id)
);

CREATE TABLE fmea_migration_confirmations (
    workspace_id TEXT NOT NULL,
    confirmation_id TEXT NOT NULL,
    migration_id TEXT NOT NULL,
    report_id TEXT NOT NULL,
    report_hash TEXT NOT NULL,
    source_revision_id TEXT NOT NULL,
    source_revision_hash TEXT NOT NULL,
    target_domain_pack_id TEXT NOT NULL,
    target_domain_pack_version TEXT NOT NULL,
    target_domain_pack_hash TEXT NOT NULL,
    child_revision_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type = 'human'),
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    confirmation_json TEXT NOT NULL CHECK (length(confirmation_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    outbox_event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, confirmation_id),
    UNIQUE (workspace_id, migration_id),
    UNIQUE (workspace_id, idempotency_scope),
    UNIQUE (workspace_id, audit_event_id),
    UNIQUE (workspace_id, outbox_event_id),
    CHECK (length(report_hash) IN (64, 71)),
    CHECK (length(source_revision_hash) IN (64, 71)),
    CHECK (length(target_domain_pack_hash) IN (64, 71)),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, migration_id)
        REFERENCES fmea_migration_runs(workspace_id, migration_id),
    FOREIGN KEY (workspace_id, report_id)
        REFERENCES fmea_migration_reports(workspace_id, report_id),
    FOREIGN KEY (workspace_id, child_revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id),
    FOREIGN KEY (workspace_id, audit_event_id)
        REFERENCES fmea_audit_events(workspace_id, event_id),
    FOREIGN KEY (workspace_id, outbox_event_id)
        REFERENCES fmea_outbox_events(workspace_id, event_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (idempotency_scope)
        REFERENCES idempotency_records(scope_key)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE fmea_export_runs (
    workspace_id TEXT NOT NULL,
    export_run_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    snapshot_id TEXT,
    snapshot_hash TEXT NOT NULL,
    publication_id TEXT,
    format TEXT NOT NULL CHECK (format IN ('json', 'xlsx', 'docx')),
    draft_preview INTEGER NOT NULL CHECK (draft_preview IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'cancelling', 'cancelled', 'failed')),
    created_at TEXT NOT NULL,
    filename TEXT,
    artifact_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    run_json TEXT NOT NULL CHECK (length(run_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    PRIMARY KEY (workspace_id, export_run_id),
    CHECK ((draft_preview = 1) = (publication_id IS NULL)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id),
    FOREIGN KEY (workspace_id, snapshot_id)
        REFERENCES fmea_normalized_snapshots(workspace_id, snapshot_id),
    FOREIGN KEY (workspace_id, publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id)
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

CREATE INDEX idx_fmea_template_drafts_workspace_created
    ON fmea_template_drafts(workspace_id, created_at, draft_id);
CREATE INDEX idx_fmea_template_patch_candidates_workspace_draft
    ON fmea_template_patch_candidates(workspace_id, draft_id, created_at, patch_id);
CREATE INDEX idx_fmea_template_patch_decisions_workspace_patch
    ON fmea_template_patch_decisions(workspace_id, patch_id, created_at, decision_id);
CREATE INDEX idx_fmea_migration_runs_workspace_status
    ON fmea_migration_runs(workspace_id, status, created_at, migration_id);
CREATE INDEX idx_fmea_migration_reports_workspace_source
    ON fmea_migration_reports(workspace_id, source_revision_id, created_at, report_id);
CREATE INDEX idx_fmea_migration_confirmations_workspace_child
    ON fmea_migration_confirmations(workspace_id, child_revision_id, created_at, confirmation_id);
CREATE INDEX idx_fmea_export_runs_workspace_revision
    ON fmea_export_runs(workspace_id, revision_id, created_at, export_run_id);
CREATE INDEX idx_fmea_export_artifacts_workspace_revision
    ON fmea_export_artifacts(workspace_id, revision_id, created_at, artifact_id);

CREATE TRIGGER fmea_template_drafts_no_update
BEFORE UPDATE ON fmea_template_drafts
BEGIN SELECT RAISE(ABORT, 'immutable fmea_template_drafts'); END;
CREATE TRIGGER fmea_template_drafts_no_delete
BEFORE DELETE ON fmea_template_drafts
BEGIN SELECT RAISE(ABORT, 'immutable fmea_template_drafts'); END;
CREATE TRIGGER fmea_template_patch_candidates_no_update
BEFORE UPDATE ON fmea_template_patch_candidates
BEGIN SELECT RAISE(ABORT, 'immutable fmea_template_patch_candidates'); END;
CREATE TRIGGER fmea_template_patch_candidates_no_delete
BEFORE DELETE ON fmea_template_patch_candidates
BEGIN SELECT RAISE(ABORT, 'immutable fmea_template_patch_candidates'); END;
CREATE TRIGGER fmea_template_patch_decisions_no_update
BEFORE UPDATE ON fmea_template_patch_decisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_template_patch_decisions'); END;
CREATE TRIGGER fmea_template_patch_decisions_no_delete
BEFORE DELETE ON fmea_template_patch_decisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_template_patch_decisions'); END;
CREATE TRIGGER fmea_migration_reports_no_update
BEFORE UPDATE ON fmea_migration_reports
BEGIN SELECT RAISE(ABORT, 'immutable fmea_migration_reports'); END;
CREATE TRIGGER fmea_migration_reports_no_delete
BEFORE DELETE ON fmea_migration_reports
BEGIN SELECT RAISE(ABORT, 'immutable fmea_migration_reports'); END;
CREATE TRIGGER fmea_migration_confirmations_no_update
BEFORE UPDATE ON fmea_migration_confirmations
BEGIN SELECT RAISE(ABORT, 'immutable fmea_migration_confirmations'); END;
CREATE TRIGGER fmea_migration_confirmations_no_delete
BEFORE DELETE ON fmea_migration_confirmations
BEGIN SELECT RAISE(ABORT, 'immutable fmea_migration_confirmations'); END;
CREATE TRIGGER fmea_export_artifacts_no_update
BEFORE UPDATE ON fmea_export_artifacts
BEGIN SELECT RAISE(ABORT, 'immutable fmea_export_artifacts'); END;
CREATE TRIGGER fmea_export_artifacts_no_delete
BEFORE DELETE ON fmea_export_artifacts
BEGIN SELECT RAISE(ABORT, 'immutable fmea_export_artifacts'); END;
