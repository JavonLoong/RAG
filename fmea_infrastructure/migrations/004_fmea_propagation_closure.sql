-- Task 4 is additive.  Existing review, risk, audit, and outbox rows are not
-- rewritten; propagation owns immutable graph/review history beside them.
CREATE TABLE IF NOT EXISTS fmea_propagation_topology_snapshots (
    workspace_id TEXT NOT NULL,
    topology_snapshot_id TEXT NOT NULL,
    analysis_id TEXT,
    topology_hash TEXT NOT NULL,
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    snapshot_hash TEXT NOT NULL,
    snapshot_json TEXT NOT NULL CHECK (length(snapshot_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, topology_snapshot_id),
    UNIQUE (workspace_id, topology_snapshot_id, record_version),
    CHECK (length(snapshot_hash) = 71 AND substr(snapshot_hash, 1, 7) = 'sha256:')
);

CREATE TABLE IF NOT EXISTS fmea_propagation_runs (
    workspace_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    source_record_version INTEGER NOT NULL CHECK (source_record_version > 0),
    status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
    graph_revision_id TEXT,
    assistance_suggestion_ids_json TEXT NOT NULL CHECK (length(assistance_suggestion_ids_json) > 0),
    error_code TEXT,
    error_message TEXT,
    request_hash TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL UNIQUE,
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, run_id)
);

CREATE TABLE IF NOT EXISTS fmea_propagation_graph_revisions (
    workspace_id TEXT NOT NULL,
    graph_revision_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    analysis_record_version INTEGER NOT NULL CHECK (analysis_record_version > 0),
    topology_snapshot_id TEXT NOT NULL,
    topology_hash TEXT NOT NULL,
    evidence_pack_ids_json TEXT NOT NULL CHECK (length(evidence_pack_ids_json) > 0),
    domain_pack_id TEXT NOT NULL,
    domain_pack_version TEXT NOT NULL,
    rule_pack_id TEXT NOT NULL,
    rule_pack_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('not_analyzed','proposed','reviewed','confirmed','invalidated')),
    assistance_suggestion_ids_json TEXT NOT NULL CHECK (length(assistance_suggestion_ids_json) > 0),
    source_row_ids_json TEXT NOT NULL CHECK (length(source_row_ids_json) > 0),
    unresolved_issue_codes_json TEXT NOT NULL CHECK (length(unresolved_issue_codes_json) > 0),
    parent_graph_revision_id TEXT,
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    graph_hash TEXT NOT NULL,
    graph_json TEXT NOT NULL CHECK (length(graph_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, graph_revision_id),
    UNIQUE (workspace_id, analysis_id, record_version),
    CHECK (length(graph_hash) = 71 AND substr(graph_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, topology_snapshot_id)
        REFERENCES fmea_propagation_topology_snapshots(workspace_id, topology_snapshot_id),
    FOREIGN KEY (workspace_id, parent_graph_revision_id)
        REFERENCES fmea_propagation_graph_revisions(workspace_id, graph_revision_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS fmea_propagation_edges (
    workspace_id TEXT NOT NULL,
    graph_revision_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    edge_order INTEGER NOT NULL CHECK (edge_order >= 0),
    edge_hash TEXT NOT NULL,
    edge_json TEXT NOT NULL CHECK (length(edge_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, graph_revision_id, edge_id),
    UNIQUE (workspace_id, graph_revision_id, edge_order),
    CHECK (length(edge_hash) = 71 AND substr(edge_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, graph_revision_id)
        REFERENCES fmea_propagation_graph_revisions(workspace_id, graph_revision_id)
);

CREATE TABLE IF NOT EXISTS fmea_propagation_evidence_snapshots (
    workspace_id TEXT NOT NULL,
    pack_id TEXT NOT NULL,
    pack_hash TEXT NOT NULL,
    pack_json TEXT NOT NULL CHECK (length(pack_json) > 0),
    snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, pack_id),
    UNIQUE (workspace_id, pack_id, pack_hash),
    CHECK (length(snapshot_hash) = 71 AND substr(snapshot_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, pack_id) REFERENCES evidence_packs(workspace_id, pack_id)
);

CREATE TABLE IF NOT EXISTS fmea_propagation_rule_snapshots (
    workspace_id TEXT NOT NULL,
    rule_pack_id TEXT NOT NULL,
    rule_pack_version TEXT NOT NULL,
    rule_hash TEXT NOT NULL,
    rule_json TEXT NOT NULL CHECK (length(rule_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, rule_pack_id, rule_pack_version),
    UNIQUE (workspace_id, rule_pack_id, rule_pack_version, rule_hash),
    CHECK (length(rule_hash) = 71 AND substr(rule_hash, 1, 7) = 'sha256:')
);

CREATE TABLE IF NOT EXISTS fmea_propagation_paths (
    workspace_id TEXT NOT NULL,
    graph_revision_id TEXT NOT NULL,
    path_id TEXT NOT NULL,
    path_order INTEGER NOT NULL CHECK (path_order >= 0),
    path_hash TEXT NOT NULL,
    path_json TEXT NOT NULL CHECK (length(path_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, graph_revision_id, path_id),
    UNIQUE (workspace_id, graph_revision_id, path_order),
    CHECK (length(path_hash) = 71 AND substr(path_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, graph_revision_id)
        REFERENCES fmea_propagation_graph_revisions(workspace_id, graph_revision_id)
);

CREATE TABLE IF NOT EXISTS fmea_propagation_issues (
    workspace_id TEXT NOT NULL,
    graph_revision_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    issue_code TEXT NOT NULL,
    issue_json TEXT NOT NULL CHECK (length(issue_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, graph_revision_id, issue_id),
    FOREIGN KEY (workspace_id, graph_revision_id)
        REFERENCES fmea_propagation_graph_revisions(workspace_id, graph_revision_id)
);

CREATE TABLE IF NOT EXISTS fmea_propagation_edge_decisions (
    workspace_id TEXT NOT NULL,
    edge_decision_id TEXT NOT NULL,
    graph_revision_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('accept','reject')),
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type = 'human'),
    reason TEXT NOT NULL,
    decision_json TEXT NOT NULL CHECK (length(decision_json) > 0),
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, edge_decision_id),
    UNIQUE (workspace_id, decision_id, edge_id),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, graph_revision_id)
        REFERENCES fmea_propagation_graph_revisions(workspace_id, graph_revision_id),
    FOREIGN KEY (workspace_id, graph_revision_id, edge_id)
        REFERENCES fmea_propagation_edges(workspace_id, graph_revision_id, edge_id)
);

CREATE TABLE IF NOT EXISTS fmea_propagation_graph_decisions (
    workspace_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    previous_graph_revision_id TEXT NOT NULL,
    resulting_graph_revision_id TEXT NOT NULL,
    decision_type TEXT NOT NULL CHECK (decision_type IN ('confirm','invalidate')),
    from_status TEXT NOT NULL CHECK (from_status IN ('proposed','reviewed','confirmed')),
    to_status TEXT NOT NULL CHECK (to_status IN ('confirmed','invalidated')),
    expected_graph_version INTEGER NOT NULL CHECK (expected_graph_version > 0),
    applied_graph_version INTEGER NOT NULL CHECK (applied_graph_version = expected_graph_version + 1),
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human','system')),
    acknowledged_issue_codes_json TEXT NOT NULL CHECK (length(acknowledged_issue_codes_json) > 0),
    decision_json TEXT NOT NULL CHECK (length(decision_json) > 0),
    idempotency_scope TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL UNIQUE,
    outbox_event_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, decision_id),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK (
        (decision_type = 'confirm' AND from_status IN ('proposed','reviewed')
            AND to_status = 'confirmed' AND actor_type = 'human')
        OR (decision_type = 'invalidate' AND from_status IN ('proposed','reviewed','confirmed')
            AND to_status = 'invalidated' AND actor_type IN ('human','system'))
    ),
    FOREIGN KEY (workspace_id, previous_graph_revision_id)
        REFERENCES fmea_propagation_graph_revisions(workspace_id, graph_revision_id),
    FOREIGN KEY (workspace_id, resulting_graph_revision_id)
        REFERENCES fmea_propagation_graph_revisions(workspace_id, graph_revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, audit_event_id)
        REFERENCES audit_events(workspace_id, event_id),
    FOREIGN KEY (workspace_id, outbox_event_id)
        REFERENCES fmea_outbox_events(workspace_id, event_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_fmea_propagation_graph_workspace_analysis
    ON fmea_propagation_graph_revisions(workspace_id, analysis_id, record_version);
CREATE INDEX IF NOT EXISTS idx_fmea_propagation_runs_workspace_analysis
    ON fmea_propagation_runs(workspace_id, analysis_id, created_at, run_id);
CREATE INDEX IF NOT EXISTS idx_fmea_propagation_edges_workspace_graph
    ON fmea_propagation_edges(workspace_id, graph_revision_id, edge_order);
CREATE INDEX IF NOT EXISTS idx_fmea_propagation_paths_workspace_graph
    ON fmea_propagation_paths(workspace_id, graph_revision_id, path_order);
CREATE INDEX IF NOT EXISTS idx_fmea_propagation_decisions_workspace_graph
    ON fmea_propagation_graph_decisions(workspace_id, previous_graph_revision_id, created_at, decision_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_outbox_workspace_event
    ON fmea_outbox_events(workspace_id, event_id);

CREATE TRIGGER IF NOT EXISTS fmea_propagation_topology_snapshots_no_update
BEFORE UPDATE ON fmea_propagation_topology_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_topology_snapshots'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_topology_snapshots_no_delete
BEFORE DELETE ON fmea_propagation_topology_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_topology_snapshots'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_evidence_snapshots_no_update
BEFORE UPDATE ON fmea_propagation_evidence_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_evidence_snapshots'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_evidence_snapshots_no_delete
BEFORE DELETE ON fmea_propagation_evidence_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_evidence_snapshots'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_rule_snapshots_no_update
BEFORE UPDATE ON fmea_propagation_rule_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_rule_snapshots'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_rule_snapshots_no_delete
BEFORE DELETE ON fmea_propagation_rule_snapshots
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_rule_snapshots'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_runs_no_update
BEFORE UPDATE ON fmea_propagation_runs
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_runs'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_runs_no_delete
BEFORE DELETE ON fmea_propagation_runs
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_runs'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_graph_revisions_no_update
BEFORE UPDATE ON fmea_propagation_graph_revisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_graph_revisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_graph_revisions_no_delete
BEFORE DELETE ON fmea_propagation_graph_revisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_graph_revisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_edges_no_update
BEFORE UPDATE ON fmea_propagation_edges
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_edges'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_edges_no_delete
BEFORE DELETE ON fmea_propagation_edges
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_edges'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_paths_no_update
BEFORE UPDATE ON fmea_propagation_paths
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_paths'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_paths_no_delete
BEFORE DELETE ON fmea_propagation_paths
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_paths'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_issues_no_update
BEFORE UPDATE ON fmea_propagation_issues
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_issues'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_issues_no_delete
BEFORE DELETE ON fmea_propagation_issues
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_issues'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_edge_decisions_no_update
BEFORE UPDATE ON fmea_propagation_edge_decisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_edge_decisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_edge_decisions_no_delete
BEFORE DELETE ON fmea_propagation_edge_decisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_edge_decisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_graph_decisions_no_update
BEFORE UPDATE ON fmea_propagation_graph_decisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_graph_decisions'); END;
CREATE TRIGGER IF NOT EXISTS fmea_propagation_graph_decisions_no_delete
BEFORE DELETE ON fmea_propagation_graph_decisions
BEGIN SELECT RAISE(ABORT, 'immutable fmea_propagation_graph_decisions'); END;
