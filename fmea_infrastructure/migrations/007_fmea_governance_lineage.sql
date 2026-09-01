-- Review round 2 adds relational governance lineage without rewriting the
-- checksum-stable governance migrations 005 and 006.
CREATE TABLE fmea_migration_007_guard (
    valid INTEGER NOT NULL
        CONSTRAINT migration_007_rejects_ambiguous_workspace CHECK (valid = 1)
);

INSERT INTO fmea_migration_007_guard(valid)
SELECT CASE WHEN EXISTS (
    SELECT analysis_id
    FROM fmea_rows
    GROUP BY analysis_id
    HAVING COUNT(DISTINCT workspace_id) > 1
) THEN 0 ELSE 1 END;

DROP TABLE fmea_migration_007_guard;

ALTER TABLE fmea_revisions ADD COLUMN idempotency_scope TEXT;
ALTER TABLE fmea_revisions ADD COLUMN payload_hash TEXT;
ALTER TABLE fmea_publications ADD COLUMN idempotency_scope TEXT;
ALTER TABLE fmea_publications ADD COLUMN payload_hash TEXT;

-- A non-partial parent key is required for SQLite composite FK resolution.
CREATE UNIQUE INDEX uq_fmea_analyses_workspace_analysis_fk
    ON fmea_analyses(workspace_id, analysis_id);

CREATE UNIQUE INDEX uq_fmea_revisions_idempotency_scope
    ON fmea_revisions(workspace_id, idempotency_scope)
    WHERE idempotency_scope IS NOT NULL;
CREATE UNIQUE INDEX uq_fmea_publications_idempotency_scope
    ON fmea_publications(workspace_id, idempotency_scope)
    WHERE idempotency_scope IS NOT NULL;

CREATE TABLE fmea_revision_analysis_bindings (
    workspace_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    analysis_record_version INTEGER NOT NULL CHECK (analysis_record_version > 0),
    analysis_hash TEXT NOT NULL,
    PRIMARY KEY (workspace_id, revision_id),
    UNIQUE (workspace_id, revision_id, analysis_id),
    CHECK (length(analysis_hash) IN (64, 71)),
    CHECK (length(analysis_hash) = 64 OR substr(analysis_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, analysis_id)
        REFERENCES fmea_analyses(workspace_id, analysis_id)
        DEFERRABLE INITIALLY DEFERRED
);

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
)
BEGIN
    SELECT RAISE(ABORT, 'revision analysis lineage mismatch');
END;

CREATE TRIGGER fmea_revision_analysis_bindings_no_update
BEFORE UPDATE ON fmea_revision_analysis_bindings
BEGIN SELECT RAISE(ABORT, 'immutable fmea_revision_analysis_bindings'); END;
CREATE TRIGGER fmea_revision_analysis_bindings_no_delete
BEFORE DELETE ON fmea_revision_analysis_bindings
BEGIN SELECT RAISE(ABORT, 'immutable fmea_revision_analysis_bindings'); END;

CREATE TABLE fmea_publication_lineage_bindings (
    workspace_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    PRIMARY KEY (workspace_id, publication_id),
    UNIQUE (workspace_id, manifest_id),
    UNIQUE (workspace_id, snapshot_id),
    CHECK (length(revision_hash) IN (64, 71)),
    CHECK (length(manifest_hash) IN (64, 71)),
    CHECK (length(snapshot_hash) IN (64, 71)),
    FOREIGN KEY (workspace_id, publication_id)
        REFERENCES fmea_publications(workspace_id, publication_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, manifest_id)
        REFERENCES fmea_publication_manifests(workspace_id, manifest_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, snapshot_id)
        REFERENCES fmea_normalized_snapshots(workspace_id, snapshot_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, revision_id)
        REFERENCES fmea_revisions(workspace_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, revision_id, analysis_id)
        REFERENCES fmea_revision_analysis_bindings(workspace_id, revision_id, analysis_id)
        DEFERRABLE INITIALLY DEFERRED
);

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

CREATE TRIGGER fmea_publication_lineage_bindings_no_update
BEFORE UPDATE ON fmea_publication_lineage_bindings
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publication_lineage_bindings'); END;
CREATE TRIGGER fmea_publication_lineage_bindings_no_delete
BEFORE DELETE ON fmea_publication_lineage_bindings
BEGIN SELECT RAISE(ABORT, 'immutable fmea_publication_lineage_bindings'); END;

INSERT INTO fmea_revision_analysis_bindings
    (workspace_id,revision_id,analysis_id,analysis_record_version,analysis_hash)
SELECT revision.workspace_id, revision.revision_id, revision.analysis_id,
       revision.analysis_record_version,
       CASE WHEN length(analysis.analysis_hash) = 71
            THEN substr(analysis.analysis_hash, 8) ELSE analysis.analysis_hash END
FROM fmea_revisions AS revision
JOIN fmea_analyses AS analysis
  ON analysis.workspace_id = revision.workspace_id
 AND analysis.analysis_id = revision.analysis_id
WHERE CASE WHEN length(analysis.analysis_hash) = 71
           THEN substr(analysis.analysis_hash, 8) ELSE analysis.analysis_hash END
      = CASE WHEN length(json_extract(revision.revision_json, '$.analysis_hash')) = 71
             THEN substr(json_extract(revision.revision_json, '$.analysis_hash'), 8)
             ELSE json_extract(revision.revision_json, '$.analysis_hash') END;

INSERT INTO fmea_publication_lineage_bindings
    (workspace_id,publication_id,manifest_id,snapshot_id,revision_id,analysis_id,
     revision_hash,manifest_hash,snapshot_hash)
SELECT publication.workspace_id, publication.publication_id,
       publication.manifest_id, publication.snapshot_id,
       publication.revision_id, publication.analysis_id,
       publication.revision_hash, publication.manifest_hash,
       publication.snapshot_hash
FROM fmea_publications AS publication
JOIN fmea_publication_manifests AS manifest
  ON manifest.workspace_id = publication.workspace_id
 AND manifest.manifest_id = publication.manifest_id
JOIN fmea_normalized_snapshots AS snapshot
  ON snapshot.workspace_id = publication.workspace_id
 AND snapshot.snapshot_id = publication.snapshot_id
WHERE manifest.revision_id = publication.revision_id
  AND manifest.revision_hash = publication.revision_hash
  AND manifest.approval_id = publication.approval_id
  AND manifest.snapshot_id = publication.snapshot_id
  AND manifest.snapshot_hash = publication.snapshot_hash
  AND manifest.manifest_hash = publication.manifest_hash
  AND snapshot.publication_id = publication.publication_id
  AND snapshot.manifest_id = publication.manifest_id
  AND snapshot.revision_id = publication.revision_id
  AND snapshot.revision_hash = publication.revision_hash
  AND snapshot.analysis_id = publication.analysis_id
  AND snapshot.snapshot_hash = publication.snapshot_hash;

CREATE TABLE fmea_migration_007_lineage_guard (
    valid INTEGER NOT NULL
        CONSTRAINT migration_007_rejects_invalid_governance_lineage CHECK (valid = 1)
);

INSERT INTO fmea_migration_007_lineage_guard(valid)
SELECT CASE WHEN
    EXISTS (
        SELECT 1 FROM fmea_revisions AS revision
        LEFT JOIN fmea_revision_analysis_bindings AS binding
          ON binding.workspace_id = revision.workspace_id
         AND binding.revision_id = revision.revision_id
        WHERE binding.revision_id IS NULL
    )
    OR EXISTS (
        SELECT 1 FROM fmea_publications AS publication
        LEFT JOIN fmea_publication_lineage_bindings AS binding
          ON binding.workspace_id = publication.workspace_id
         AND binding.publication_id = publication.publication_id
        WHERE binding.publication_id IS NULL
    )
THEN 0 ELSE 1 END;

DROP TABLE fmea_migration_007_lineage_guard;
