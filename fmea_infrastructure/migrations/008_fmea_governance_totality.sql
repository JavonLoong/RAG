-- Review round 3 makes the migration-007 lineage relations mandatory from
-- both directions and repairs only replay-authority metadata that can be
-- reconstructed from the existing shared audit/outbox/idempotency chain.

UPDATE fmea_revisions AS revision
SET idempotency_scope = (
        SELECT audit.idempotency_scope
        FROM fmea_governance_event_bindings AS binding
        JOIN fmea_audit_events AS audit
          ON audit.workspace_id = binding.workspace_id
         AND audit.event_id = binding.audit_event_id
        JOIN fmea_outbox_events AS outbox
          ON outbox.workspace_id = binding.workspace_id
         AND outbox.event_id = binding.outbox_event_id
        JOIN idempotency_records AS idempotency
          ON idempotency.scope_key = audit.idempotency_scope
        WHERE binding.workspace_id = revision.workspace_id
          AND binding.resource_type = 'revision'
          AND binding.resource_id = revision.revision_id
          AND binding.audit_event_id = revision.audit_event_id
          AND binding.outbox_event_id = revision.outbox_event_id
          AND audit.resource_type = 'revision'
          AND audit.resource_id = revision.revision_id
          AND audit.command = 'fmea.revision.assemble'
          AND outbox.aggregate_type = 'fmea_governance'
          AND outbox.aggregate_id = revision.revision_id
          AND outbox.event_type = 'revision.assembled'
          AND outbox.idempotency_scope = audit.idempotency_scope
          AND outbox.payload_hash = audit.canonical_payload_hash
          AND idempotency.payload_hash = audit.canonical_payload_hash
          AND idempotency.state = 'completed'
          AND idempotency.resource_id = revision.revision_id
          AND json_extract(idempotency.response_json, '$.revision_id') = revision.revision_id
          AND json_extract(idempotency.response_json, '$.record_version') = revision.record_version
          AND json_extract(idempotency.response_json, '$.audit_event_id') = revision.audit_event_id
          AND json_extract(idempotency.response_json, '$.outbox_event_id') = revision.outbox_event_id
          AND json_extract(idempotency.response_json, '$.replayed') = 0
    ),
    payload_hash = (
        SELECT audit.canonical_payload_hash
        FROM fmea_governance_event_bindings AS binding
        JOIN fmea_audit_events AS audit
          ON audit.workspace_id = binding.workspace_id
         AND audit.event_id = binding.audit_event_id
        JOIN fmea_outbox_events AS outbox
          ON outbox.workspace_id = binding.workspace_id
         AND outbox.event_id = binding.outbox_event_id
        JOIN idempotency_records AS idempotency
          ON idempotency.scope_key = audit.idempotency_scope
        WHERE binding.workspace_id = revision.workspace_id
          AND binding.resource_type = 'revision'
          AND binding.resource_id = revision.revision_id
          AND binding.audit_event_id = revision.audit_event_id
          AND binding.outbox_event_id = revision.outbox_event_id
          AND audit.resource_type = 'revision'
          AND audit.resource_id = revision.revision_id
          AND audit.command = 'fmea.revision.assemble'
          AND outbox.aggregate_type = 'fmea_governance'
          AND outbox.aggregate_id = revision.revision_id
          AND outbox.event_type = 'revision.assembled'
          AND outbox.idempotency_scope = audit.idempotency_scope
          AND outbox.payload_hash = audit.canonical_payload_hash
          AND idempotency.payload_hash = audit.canonical_payload_hash
          AND idempotency.state = 'completed'
          AND idempotency.resource_id = revision.revision_id
          AND json_extract(idempotency.response_json, '$.revision_id') = revision.revision_id
          AND json_extract(idempotency.response_json, '$.record_version') = revision.record_version
          AND json_extract(idempotency.response_json, '$.audit_event_id') = revision.audit_event_id
          AND json_extract(idempotency.response_json, '$.outbox_event_id') = revision.outbox_event_id
          AND json_extract(idempotency.response_json, '$.replayed') = 0
    )
WHERE revision.idempotency_scope IS NULL OR revision.payload_hash IS NULL;

UPDATE fmea_publications AS publication
SET idempotency_scope = (
        SELECT audit.idempotency_scope
        FROM fmea_governance_event_bindings AS binding
        JOIN fmea_audit_events AS audit
          ON audit.workspace_id = binding.workspace_id
         AND audit.event_id = binding.audit_event_id
        JOIN fmea_outbox_events AS outbox
          ON outbox.workspace_id = binding.workspace_id
         AND outbox.event_id = binding.outbox_event_id
        JOIN idempotency_records AS idempotency
          ON idempotency.scope_key = audit.idempotency_scope
        WHERE binding.workspace_id = publication.workspace_id
          AND binding.resource_type = 'publication'
          AND binding.resource_id = publication.publication_id
          AND binding.audit_event_id = publication.audit_event_id
          AND binding.outbox_event_id = publication.outbox_event_id
          AND audit.resource_type = 'publication'
          AND audit.resource_id = publication.publication_id
          AND audit.command = 'fmea.publication.publish'
          AND outbox.aggregate_type = 'fmea_governance'
          AND outbox.aggregate_id = publication.publication_id
          AND outbox.event_type = 'publication.published'
          AND outbox.idempotency_scope = audit.idempotency_scope
          AND outbox.payload_hash = audit.canonical_payload_hash
          AND idempotency.payload_hash = audit.canonical_payload_hash
          AND idempotency.state = 'completed'
          AND idempotency.resource_id = publication.publication_id
          AND json_extract(idempotency.response_json, '$.publication_id') = publication.publication_id
          AND json_extract(idempotency.response_json, '$.manifest_id') = publication.manifest_id
          AND json_extract(idempotency.response_json, '$.snapshot_id') = publication.snapshot_id
          AND json_extract(idempotency.response_json, '$.record_version') = publication.record_version
          AND json_extract(idempotency.response_json, '$.audit_event_id') = publication.audit_event_id
          AND json_extract(idempotency.response_json, '$.outbox_event_id') = publication.outbox_event_id
          AND json_extract(idempotency.response_json, '$.replayed') = 0
    ),
    payload_hash = (
        SELECT audit.canonical_payload_hash
        FROM fmea_governance_event_bindings AS binding
        JOIN fmea_audit_events AS audit
          ON audit.workspace_id = binding.workspace_id
         AND audit.event_id = binding.audit_event_id
        JOIN fmea_outbox_events AS outbox
          ON outbox.workspace_id = binding.workspace_id
         AND outbox.event_id = binding.outbox_event_id
        JOIN idempotency_records AS idempotency
          ON idempotency.scope_key = audit.idempotency_scope
        WHERE binding.workspace_id = publication.workspace_id
          AND binding.resource_type = 'publication'
          AND binding.resource_id = publication.publication_id
          AND binding.audit_event_id = publication.audit_event_id
          AND binding.outbox_event_id = publication.outbox_event_id
          AND audit.resource_type = 'publication'
          AND audit.resource_id = publication.publication_id
          AND audit.command = 'fmea.publication.publish'
          AND outbox.aggregate_type = 'fmea_governance'
          AND outbox.aggregate_id = publication.publication_id
          AND outbox.event_type = 'publication.published'
          AND outbox.idempotency_scope = audit.idempotency_scope
          AND outbox.payload_hash = audit.canonical_payload_hash
          AND idempotency.payload_hash = audit.canonical_payload_hash
          AND idempotency.state = 'completed'
          AND idempotency.resource_id = publication.publication_id
          AND json_extract(idempotency.response_json, '$.publication_id') = publication.publication_id
          AND json_extract(idempotency.response_json, '$.manifest_id') = publication.manifest_id
          AND json_extract(idempotency.response_json, '$.snapshot_id') = publication.snapshot_id
          AND json_extract(idempotency.response_json, '$.record_version') = publication.record_version
          AND json_extract(idempotency.response_json, '$.audit_event_id') = publication.audit_event_id
          AND json_extract(idempotency.response_json, '$.outbox_event_id') = publication.outbox_event_id
          AND json_extract(idempotency.response_json, '$.replayed') = 0
    )
WHERE publication.idempotency_scope IS NULL OR publication.payload_hash IS NULL;

CREATE TABLE fmea_migration_008_authority_guard (
    valid INTEGER NOT NULL
        CONSTRAINT migration_008_requires_replayable_authority CHECK (valid = 1)
);

INSERT INTO fmea_migration_008_authority_guard(valid)
SELECT CASE WHEN
    EXISTS (
        SELECT 1
        FROM fmea_revisions AS revision
        LEFT JOIN fmea_revision_analysis_bindings AS lineage
          ON lineage.workspace_id = revision.workspace_id
         AND lineage.revision_id = revision.revision_id
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
        WHERE lineage.revision_id IS NULL
           OR revision.audit_event_id IS NULL
           OR revision.outbox_event_id IS NULL
           OR revision.idempotency_scope IS NULL
           OR revision.payload_hash IS NULL
           OR binding.resource_id IS NULL
           OR audit.event_id IS NULL
           OR outbox.event_id IS NULL
           OR idempotency.scope_key IS NULL
           OR binding.audit_event_id <> revision.audit_event_id
           OR binding.outbox_event_id <> revision.outbox_event_id
           OR audit.resource_type <> 'revision'
           OR audit.resource_id <> revision.revision_id
           OR audit.command <> 'fmea.revision.assemble'
           OR audit.idempotency_scope <> revision.idempotency_scope
           OR audit.canonical_payload_hash <> revision.payload_hash
           OR outbox.aggregate_type <> 'fmea_governance'
           OR outbox.aggregate_id <> revision.revision_id
           OR outbox.event_type <> 'revision.assembled'
           OR outbox.idempotency_scope <> revision.idempotency_scope
           OR outbox.payload_hash <> revision.payload_hash
           OR idempotency.payload_hash <> revision.payload_hash
           OR idempotency.state <> 'completed'
           OR idempotency.resource_id <> revision.revision_id
           OR json_extract(idempotency.response_json, '$.revision_id') <> revision.revision_id
           OR json_extract(idempotency.response_json, '$.record_version') <> revision.record_version
           OR json_extract(idempotency.response_json, '$.audit_event_id') <> revision.audit_event_id
           OR json_extract(idempotency.response_json, '$.outbox_event_id') <> revision.outbox_event_id
           OR json_extract(idempotency.response_json, '$.replayed') <> 0
    )
    OR EXISTS (
        SELECT 1
        FROM fmea_publications AS publication
        LEFT JOIN fmea_publication_lineage_bindings AS lineage
          ON lineage.workspace_id = publication.workspace_id
         AND lineage.publication_id = publication.publication_id
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
        WHERE lineage.publication_id IS NULL
           OR publication.audit_event_id IS NULL
           OR publication.outbox_event_id IS NULL
           OR publication.idempotency_scope IS NULL
           OR publication.payload_hash IS NULL
           OR binding.resource_id IS NULL
           OR audit.event_id IS NULL
           OR outbox.event_id IS NULL
           OR idempotency.scope_key IS NULL
           OR binding.audit_event_id <> publication.audit_event_id
           OR binding.outbox_event_id <> publication.outbox_event_id
           OR audit.resource_type <> 'publication'
           OR audit.resource_id <> publication.publication_id
           OR audit.command <> 'fmea.publication.publish'
           OR audit.idempotency_scope <> publication.idempotency_scope
           OR audit.canonical_payload_hash <> publication.payload_hash
           OR outbox.aggregate_type <> 'fmea_governance'
           OR outbox.aggregate_id <> publication.publication_id
           OR outbox.event_type <> 'publication.published'
           OR outbox.idempotency_scope <> publication.idempotency_scope
           OR outbox.payload_hash <> publication.payload_hash
           OR idempotency.payload_hash <> publication.payload_hash
           OR idempotency.state <> 'completed'
           OR idempotency.resource_id <> publication.publication_id
           OR json_extract(idempotency.response_json, '$.publication_id') <> publication.publication_id
           OR json_extract(idempotency.response_json, '$.manifest_id') <> publication.manifest_id
           OR json_extract(idempotency.response_json, '$.snapshot_id') <> publication.snapshot_id
           OR json_extract(idempotency.response_json, '$.record_version') <> publication.record_version
           OR json_extract(idempotency.response_json, '$.audit_event_id') <> publication.audit_event_id
           OR json_extract(idempotency.response_json, '$.outbox_event_id') <> publication.outbox_event_id
           OR json_extract(idempotency.response_json, '$.replayed') <> 0
    )
THEN 0 ELSE 1 END;

DROP TABLE fmea_migration_008_authority_guard;

PRAGMA defer_foreign_keys = ON;

-- These insertion guards refer to the parent tables being rebuilt below.
-- Remove them before the first DROP and restore them after both parents exist.
DROP TRIGGER fmea_revision_analysis_bindings_lineage;
DROP TRIGGER fmea_publication_lineage_bindings_lineage;

CREATE TABLE fmea_revisions_v8 (
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
    audit_event_id TEXT,
    outbox_event_id TEXT,
    idempotency_scope TEXT,
    payload_hash TEXT,
    PRIMARY KEY (workspace_id, revision_id),
    UNIQUE (workspace_id, revision_id, record_version),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (substr(revision_hash, 1, 7) = 'sha256:' OR length(revision_hash) = 64),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK ((parent_revision_id IS NULL) = (parent_revision_hash IS NULL)),
    FOREIGN KEY (workspace_id, parent_revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revision_analysis_bindings(workspace_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, audit_event_id)
        REFERENCES fmea_audit_events(workspace_id, event_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, outbox_event_id)
        REFERENCES fmea_outbox_events(workspace_id, event_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (idempotency_scope)
        REFERENCES idempotency_records(scope_key)
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO fmea_revisions_v8
    (workspace_id,revision_id,analysis_id,analysis_record_version,parent_revision_id,
     parent_revision_hash,revision_hash,revision_json,record_version,canonical_json_hash,
     created_at,audit_event_id,outbox_event_id,idempotency_scope,payload_hash)
SELECT workspace_id,revision_id,analysis_id,analysis_record_version,parent_revision_id,
       parent_revision_hash,revision_hash,revision_json,record_version,canonical_json_hash,
       created_at,audit_event_id,outbox_event_id,idempotency_scope,payload_hash
FROM fmea_revisions;

DROP TABLE fmea_revisions;
ALTER TABLE fmea_revisions_v8 RENAME TO fmea_revisions;

CREATE INDEX idx_fmea_revisions_workspace_analysis
    ON fmea_revisions(workspace_id, analysis_id, record_version, revision_id);
CREATE UNIQUE INDEX uq_fmea_revisions_audit_event
    ON fmea_revisions(workspace_id, audit_event_id);
CREATE UNIQUE INDEX uq_fmea_revisions_outbox_event
    ON fmea_revisions(workspace_id, outbox_event_id);
CREATE UNIQUE INDEX uq_fmea_revisions_idempotency_scope
    ON fmea_revisions(workspace_id, idempotency_scope);
CREATE TRIGGER fmea_revisions_no_update
BEFORE UPDATE ON fmea_revisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_revisions'); END;
CREATE TRIGGER fmea_revisions_no_delete
BEFORE DELETE ON fmea_revisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_revisions'); END;
CREATE TRIGGER fmea_revisions_authority_required
BEFORE INSERT ON fmea_revisions
WHEN NEW.audit_event_id IS NULL
  OR NEW.outbox_event_id IS NULL
  OR NEW.idempotency_scope IS NULL
  OR NEW.payload_hash IS NULL
BEGIN SELECT RAISE(ABORT, 'revision authority metadata required'); END;

CREATE TABLE fmea_publications_v8 (
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
    audit_event_id TEXT,
    outbox_event_id TEXT,
    idempotency_scope TEXT,
    payload_hash TEXT,
    PRIMARY KEY (workspace_id, publication_id),
    UNIQUE (workspace_id, publication_id, record_version),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(manifest_hash) IN (64, 71)),
    CHECK (length(snapshot_hash) IN (64, 71)),
    CHECK (length(audit_chain_head) IN (64, 71)),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
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
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, publication_id)
        REFERENCES fmea_publication_lineage_bindings(workspace_id, publication_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, audit_event_id)
        REFERENCES fmea_audit_events(workspace_id, event_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, outbox_event_id)
        REFERENCES fmea_outbox_events(workspace_id, event_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (idempotency_scope)
        REFERENCES idempotency_records(scope_key)
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO fmea_publications_v8
    (workspace_id,publication_id,analysis_id,revision_id,revision_hash,approval_id,
     manifest_id,manifest_hash,snapshot_id,snapshot_hash,audit_chain_head,publisher_actor_id,
     record_version,publication_json,canonical_json_hash,created_at,audit_event_id,
     outbox_event_id,idempotency_scope,payload_hash)
SELECT workspace_id,publication_id,analysis_id,revision_id,revision_hash,approval_id,
       manifest_id,manifest_hash,snapshot_id,snapshot_hash,audit_chain_head,publisher_actor_id,
       record_version,publication_json,canonical_json_hash,created_at,audit_event_id,
       outbox_event_id,idempotency_scope,payload_hash
FROM fmea_publications;

DROP TABLE fmea_publications;
ALTER TABLE fmea_publications_v8 RENAME TO fmea_publications;

CREATE INDEX idx_fmea_publications_workspace_analysis
    ON fmea_publications(workspace_id, analysis_id, created_at, publication_id);
CREATE UNIQUE INDEX uq_fmea_publications_audit_event
    ON fmea_publications(workspace_id, audit_event_id);
CREATE UNIQUE INDEX uq_fmea_publications_outbox_event
    ON fmea_publications(workspace_id, outbox_event_id);
CREATE UNIQUE INDEX uq_fmea_publications_idempotency_scope
    ON fmea_publications(workspace_id, idempotency_scope);
CREATE TRIGGER fmea_publications_no_update
BEFORE UPDATE ON fmea_publications
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publications'); END;
CREATE TRIGGER fmea_publications_no_delete
BEFORE DELETE ON fmea_publications
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publications'); END;
CREATE TRIGGER fmea_publications_authority_required
BEFORE INSERT ON fmea_publications
WHEN NEW.audit_event_id IS NULL
  OR NEW.outbox_event_id IS NULL
  OR NEW.idempotency_scope IS NULL
  OR NEW.payload_hash IS NULL
BEGIN SELECT RAISE(ABORT, 'publication authority metadata required'); END;

CREATE TRIGGER fmea_revision_analysis_bindings_lineage
BEFORE INSERT ON fmea_revision_analysis_bindings
WHEN NOT EXISTS (
    SELECT 1
    FROM fmea_revisions AS revision
    JOIN fmea_analyses AS analysis
      ON analysis.workspace_id = revision.workspace_id
     AND analysis.analysis_id = revision.analysis_id
    WHERE revision.workspace_id = NEW.workspace_id
      AND revision.revision_id = NEW.revision_id
      AND revision.analysis_id = NEW.analysis_id
      AND revision.analysis_record_version = NEW.analysis_record_version
      AND CASE WHEN length(analysis.analysis_hash) = 71
               THEN substr(analysis.analysis_hash, 8) ELSE analysis.analysis_hash END
          = CASE WHEN length(NEW.analysis_hash) = 71
                 THEN substr(NEW.analysis_hash, 8) ELSE NEW.analysis_hash END
      AND CASE WHEN length(json_extract(revision.revision_json, '$.analysis_hash')) = 71
               THEN substr(json_extract(revision.revision_json, '$.analysis_hash'), 8)
               ELSE json_extract(revision.revision_json, '$.analysis_hash') END
          = CASE WHEN length(NEW.analysis_hash) = 71
                 THEN substr(NEW.analysis_hash, 8) ELSE NEW.analysis_hash END
)
BEGIN
    SELECT RAISE(ABORT, 'revision analysis lineage mismatch');
END;

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

-- Parent-table rebuilds can leave SQLite's deferred-FK counter reflecting the
-- transient DROP even when the final graph is valid. Validate the completed
-- graph directly before clearing only that transient counter.
CREATE TABLE fmea_migration_008_foreign_key_guard (
    valid INTEGER NOT NULL
        CONSTRAINT migration_008_requires_valid_foreign_keys CHECK (valid = 1)
);
INSERT INTO fmea_migration_008_foreign_key_guard(valid)
SELECT CASE WHEN EXISTS (SELECT 1 FROM pragma_foreign_key_check) THEN 0 ELSE 1 END;
DROP TABLE fmea_migration_008_foreign_key_guard;
PRAGMA defer_foreign_keys = OFF;
