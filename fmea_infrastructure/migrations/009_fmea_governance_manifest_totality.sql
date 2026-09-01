-- Review round 4 closes the remaining parent-side publication lineage gap.
-- The replay guard runs after migration 008 in the same outer transaction.  It
-- uses the application-defined function registered by the migration runner
-- because SQLite SQL cannot recompute the repository's canonical JSON/SHA
-- payloads or decode the typed audit/authority DTOs by itself.

CREATE TABLE fmea_migration_009_replay_guard (
    valid INTEGER NOT NULL
        CONSTRAINT migration_009_requires_safe_replay_authority CHECK (valid = 1)
);

INSERT INTO fmea_migration_009_replay_guard(valid)
SELECT CASE WHEN
    EXISTS (
        SELECT 1
        FROM fmea_revisions AS revision
        LEFT JOIN fmea_governance_event_bindings AS binding
          ON binding.workspace_id = revision.workspace_id
         AND binding.resource_type = 'revision'
         AND binding.resource_id = revision.revision_id
        LEFT JOIN fmea_audit_events AS audit
          ON audit.workspace_id = binding.workspace_id
         AND audit.event_id = binding.audit_event_id
        LEFT JOIN fmea_outbox_events AS outbox
          ON outbox.workspace_id = binding.workspace_id
         AND outbox.event_id = binding.outbox_event_id
        LEFT JOIN idempotency_records AS idempotency
          ON idempotency.scope_key = revision.idempotency_scope
        WHERE fmea_validate_governance_replay(
            json_object(
                'kind', 'revision',
                'workspace_id', revision.workspace_id,
                'resource_id', revision.revision_id,
                'authority_json', revision.revision_json,
                'authority_canonical_json_hash', revision.canonical_json_hash,
                'authority_scope', revision.idempotency_scope,
                'authority_payload_hash', revision.payload_hash,
                'authority_audit_event_id', revision.audit_event_id,
                'authority_outbox_event_id', revision.outbox_event_id,
                'authority_record_version', revision.record_version,
                'authority_analysis_id', revision.analysis_id,
                'authority_revision_hash', revision.revision_hash,
                'authority_analysis_record_version', revision.analysis_record_version,
                'authority_parent_revision_id', revision.parent_revision_id,
                'authority_parent_revision_hash', revision.parent_revision_hash,
                'audit_json', audit.event_json,
                'audit_event_id', audit.event_id,
                'audit_resource_type', audit.resource_type,
                'audit_resource_id', audit.resource_id,
                'audit_actor_id', audit.actor_id,
                'audit_command', audit.command,
                'audit_scope', audit.idempotency_scope,
                'audit_payload_hash', audit.canonical_payload_hash,
                'outbox_json', outbox.payload_json,
                'outbox_event_id', outbox.event_id,
                'outbox_row_event_id', outbox.event_id,
                'outbox_workspace_id', outbox.workspace_id,
                'outbox_aggregate_type', outbox.aggregate_type,
                'outbox_aggregate_id', outbox.aggregate_id,
                'outbox_event_type', outbox.event_type,
                'outbox_scope', outbox.idempotency_scope,
                'outbox_payload_hash', outbox.payload_hash,
                'idempotency_payload_hash', idempotency.payload_hash,
                'idempotency_state', idempotency.state,
                'idempotency_resource_id', idempotency.resource_id,
                'idempotency_response_json', idempotency.response_json
            )
        ) <> 1
    )
    OR EXISTS (
        SELECT 1
        FROM fmea_publications AS publication
        LEFT JOIN fmea_governance_event_bindings AS binding
          ON binding.workspace_id = publication.workspace_id
         AND binding.resource_type = 'publication'
         AND binding.resource_id = publication.publication_id
        LEFT JOIN fmea_audit_events AS audit
          ON audit.workspace_id = binding.workspace_id
         AND audit.event_id = binding.audit_event_id
        LEFT JOIN fmea_outbox_events AS outbox
          ON outbox.workspace_id = binding.workspace_id
         AND outbox.event_id = binding.outbox_event_id
        LEFT JOIN idempotency_records AS idempotency
          ON idempotency.scope_key = publication.idempotency_scope
        LEFT JOIN fmea_revisions AS dependency_revision
          ON dependency_revision.workspace_id = publication.workspace_id
         AND dependency_revision.revision_id = publication.revision_id
        LEFT JOIN fmea_approval_decisions AS dependency_approval
          ON dependency_approval.workspace_id = publication.workspace_id
         AND dependency_approval.approval_id = publication.approval_id
        LEFT JOIN fmea_approval_submissions AS dependency_submission
          ON dependency_submission.workspace_id = publication.workspace_id
         AND dependency_submission.submission_id = dependency_approval.submission_id
        LEFT JOIN fmea_publication_manifests AS dependency_manifest
          ON dependency_manifest.workspace_id = publication.workspace_id
         AND dependency_manifest.manifest_id = publication.manifest_id
        LEFT JOIN fmea_normalized_snapshots AS dependency_snapshot
          ON dependency_snapshot.workspace_id = publication.workspace_id
         AND dependency_snapshot.snapshot_id = publication.snapshot_id
        LEFT JOIN fmea_export_eligibility AS dependency_eligibility
          ON dependency_eligibility.workspace_id = publication.workspace_id
         AND dependency_eligibility.publication_id = publication.publication_id
        WHERE fmea_validate_governance_replay(
            json_object(
                'kind', 'publication',
                'workspace_id', publication.workspace_id,
                'resource_id', publication.publication_id,
                'authority_json', publication.publication_json,
                'authority_canonical_json_hash', publication.canonical_json_hash,
                'authority_scope', publication.idempotency_scope,
                'authority_payload_hash', publication.payload_hash,
                'authority_audit_event_id', publication.audit_event_id,
                'authority_outbox_event_id', publication.outbox_event_id,
                'authority_record_version', publication.record_version,
                'authority_analysis_id', publication.analysis_id,
                'authority_revision_id', publication.revision_id,
                'authority_revision_hash', publication.revision_hash,
                'authority_approval_id', publication.approval_id,
                'authority_manifest_id', publication.manifest_id,
                'authority_manifest_hash', publication.manifest_hash,
                'authority_snapshot_id', publication.snapshot_id,
                'authority_snapshot_hash', publication.snapshot_hash,
                'authority_audit_chain_head', publication.audit_chain_head,
                'authority_publisher_actor_id', publication.publisher_actor_id,
                'audit_json', audit.event_json,
                'audit_event_id', audit.event_id,
                'audit_resource_type', audit.resource_type,
                'audit_resource_id', audit.resource_id,
                'audit_actor_id', audit.actor_id,
                'audit_command', audit.command,
                'audit_scope', audit.idempotency_scope,
                'audit_payload_hash', audit.canonical_payload_hash,
                'outbox_json', outbox.payload_json,
                'outbox_event_id', outbox.event_id,
                'outbox_row_event_id', outbox.event_id,
                'outbox_workspace_id', outbox.workspace_id,
                'outbox_aggregate_type', outbox.aggregate_type,
                'outbox_aggregate_id', outbox.aggregate_id,
                'outbox_event_type', outbox.event_type,
                'outbox_scope', outbox.idempotency_scope,
                'outbox_payload_hash', outbox.payload_hash,
                'idempotency_payload_hash', idempotency.payload_hash,
                'idempotency_state', idempotency.state,
                'idempotency_resource_id', idempotency.resource_id,
                'idempotency_response_json', idempotency.response_json,
                'dependency_revision_json', dependency_revision.revision_json,
                'dependency_revision_canonical_json_hash', dependency_revision.canonical_json_hash,
                'dependency_revision_record_version', dependency_revision.record_version,
                'dependency_submission_json', dependency_submission.submission_json,
                'dependency_submission_canonical_json_hash', dependency_submission.canonical_json_hash,
                'dependency_submission_id', dependency_submission.submission_id,
                'dependency_submission_status', dependency_submission.status,
                'dependency_submission_submitter_actor_id', dependency_submission.submitter_actor_id,
                'dependency_submission_record_version', dependency_submission.record_version,
                'dependency_approval_json', dependency_approval.decision_json,
                'dependency_approval_canonical_json_hash', dependency_approval.canonical_json_hash,
                'dependency_approval_id', dependency_approval.approval_id,
                'dependency_approval_status', dependency_approval.status,
                'dependency_approval_approver_actor_id', dependency_approval.approver_actor_id,
                'dependency_approval_reason', dependency_approval.reason,
                'dependency_approval_record_version', dependency_approval.record_version,
                'dependency_manifest_json', dependency_manifest.manifest_json,
                'dependency_manifest_canonical_json_hash', dependency_manifest.canonical_json_hash,
                'dependency_snapshot_json', dependency_snapshot.snapshot_json,
                'dependency_snapshot_canonical_json_hash', dependency_snapshot.canonical_json_hash,
                'dependency_eligibility_json', dependency_eligibility.eligibility_json,
                'dependency_eligibility_canonical_json_hash', dependency_eligibility.canonical_json_hash,
                'dependency_eligibility_id', dependency_eligibility.eligibility_id,
                'dependency_eligibility_hash', dependency_eligibility.eligibility_hash,
                'dependency_manifest_id', dependency_manifest.manifest_id,
                'dependency_manifest_revision_id', dependency_manifest.revision_id,
                'dependency_manifest_revision_hash', dependency_manifest.revision_hash,
                'dependency_manifest_approval_id', dependency_manifest.approval_id,
                'dependency_manifest_snapshot_id', dependency_manifest.snapshot_id,
                'dependency_manifest_snapshot_hash', dependency_manifest.snapshot_hash,
                'dependency_manifest_hash', dependency_manifest.manifest_hash,
                'dependency_snapshot_id', dependency_snapshot.snapshot_id,
                'dependency_snapshot_publication_id', dependency_snapshot.publication_id,
                'dependency_snapshot_manifest_id', dependency_snapshot.manifest_id,
                'dependency_snapshot_revision_id', dependency_snapshot.revision_id,
                'dependency_snapshot_revision_hash', dependency_snapshot.revision_hash,
                'dependency_snapshot_analysis_id', dependency_snapshot.analysis_id,
                'dependency_snapshot_hash', dependency_snapshot.snapshot_hash,
                'dependency_eligibility_publication_id', dependency_eligibility.publication_id,
                'dependency_eligibility_manifest_id', dependency_eligibility.manifest_id,
                'dependency_eligibility', dependency_eligibility.eligible
            )
        ) <> 1
    )
THEN 0 ELSE 1 END;

DROP TABLE fmea_migration_009_replay_guard;

PRAGMA defer_foreign_keys = ON;

-- The insert trigger reads both parent tables being rebuilt.  Remove it while
-- those table names are transiently absent and restore the exact lineage
-- predicate after both replacements are complete.
DROP TRIGGER fmea_publication_lineage_bindings_lineage;

CREATE TABLE fmea_publication_manifests_v9 (
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
        REFERENCES fmea_approval_decisions(workspace_id, approval_id),
    FOREIGN KEY (workspace_id, manifest_id)
        REFERENCES fmea_publication_lineage_bindings(workspace_id, manifest_id)
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO fmea_publication_manifests_v9
    (workspace_id,manifest_id,revision_id,revision_hash,approval_id,snapshot_id,snapshot_hash,
     version_manifest_hash,previous_audit_chain_head,export_eligible,manifest_hash,manifest_json,
     canonical_json_hash,created_at)
SELECT workspace_id,manifest_id,revision_id,revision_hash,approval_id,snapshot_id,snapshot_hash,
       version_manifest_hash,previous_audit_chain_head,export_eligible,manifest_hash,manifest_json,
       canonical_json_hash,created_at
FROM fmea_publication_manifests;

DROP TABLE fmea_publication_manifests;
ALTER TABLE fmea_publication_manifests_v9 RENAME TO fmea_publication_manifests;

CREATE INDEX idx_fmea_publication_manifests_workspace_revision
    ON fmea_publication_manifests(workspace_id, revision_id, created_at, manifest_id);
CREATE TRIGGER fmea_publication_manifests_no_update
BEFORE UPDATE ON fmea_publication_manifests
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publication_manifests'); END;
CREATE TRIGGER fmea_publication_manifests_no_delete
BEFORE DELETE ON fmea_publication_manifests
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publication_manifests'); END;

CREATE TABLE fmea_normalized_snapshots_v9 (
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
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, snapshot_id)
        REFERENCES fmea_publication_lineage_bindings(workspace_id, snapshot_id)
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO fmea_normalized_snapshots_v9
    (workspace_id,snapshot_id,publication_id,manifest_id,revision_id,revision_hash,analysis_id,
     snapshot_hash,snapshot_json,canonical_json_hash,created_at)
SELECT workspace_id,snapshot_id,publication_id,manifest_id,revision_id,revision_hash,analysis_id,
       snapshot_hash,snapshot_json,canonical_json_hash,created_at
FROM fmea_normalized_snapshots;

DROP TABLE fmea_normalized_snapshots;
ALTER TABLE fmea_normalized_snapshots_v9 RENAME TO fmea_normalized_snapshots;

CREATE TRIGGER fmea_normalized_snapshots_no_update
BEFORE UPDATE ON fmea_normalized_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_normalized_snapshots'); END;
CREATE TRIGGER fmea_normalized_snapshots_no_delete
BEFORE DELETE ON fmea_normalized_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_normalized_snapshots'); END;

CREATE TRIGGER fmea_publication_lineage_bindings_lineage
BEFORE INSERT ON fmea_publication_lineage_bindings
WHEN NOT EXISTS (
    SELECT 1
    FROM fmea_publications AS publication
    JOIN fmea_publication_manifests AS manifest
      ON manifest.workspace_id = publication.workspace_id
     AND manifest.manifest_id = publication.manifest_id
    JOIN fmea_normalized_snapshots AS snapshot
      ON snapshot.workspace_id = publication.workspace_id
     AND snapshot.snapshot_id = publication.snapshot_id
    WHERE publication.workspace_id = NEW.workspace_id
      AND publication.publication_id = NEW.publication_id
      AND publication.manifest_id = NEW.manifest_id
      AND publication.snapshot_id = NEW.snapshot_id
      AND publication.revision_id = NEW.revision_id
      AND publication.analysis_id = NEW.analysis_id
      AND publication.revision_hash = NEW.revision_hash
      AND publication.manifest_hash = NEW.manifest_hash
      AND publication.snapshot_hash = NEW.snapshot_hash
      AND manifest.revision_id = NEW.revision_id
      AND manifest.revision_hash = NEW.revision_hash
      AND manifest.approval_id = publication.approval_id
      AND manifest.snapshot_id = NEW.snapshot_id
      AND manifest.snapshot_hash = NEW.snapshot_hash
      AND manifest.manifest_hash = NEW.manifest_hash
      AND snapshot.publication_id = NEW.publication_id
      AND snapshot.manifest_id = NEW.manifest_id
      AND snapshot.revision_id = NEW.revision_id
      AND snapshot.revision_hash = NEW.revision_hash
      AND snapshot.analysis_id = NEW.analysis_id
      AND snapshot.snapshot_hash = NEW.snapshot_hash
)
BEGIN
    SELECT RAISE(ABORT, 'publication manifest snapshot lineage mismatch');
END;

CREATE TABLE fmea_migration_009_foreign_key_guard (
    valid INTEGER NOT NULL
        CONSTRAINT migration_009_requires_valid_foreign_keys CHECK (valid = 1)
);
INSERT INTO fmea_migration_009_foreign_key_guard(valid)
SELECT CASE WHEN EXISTS (SELECT 1 FROM pragma_foreign_key_check) THEN 0 ELSE 1 END;
DROP TABLE fmea_migration_009_foreign_key_guard;
PRAGMA defer_foreign_keys = OFF;
