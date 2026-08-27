CREATE TABLE IF NOT EXISTS fmea_domain_packs (
    workspace_id TEXT NOT NULL,
    pack_id TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('registered','retired')),
    content_hash TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    manifest_json TEXT NOT NULL CHECK (length(manifest_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, pack_id, version),
    UNIQUE (workspace_id, content_hash),
    CHECK (length(content_hash) = 71 AND substr(content_hash, 1, 7) = 'sha256:'),
    CHECK (length(source_hash) = 71 AND substr(source_hash, 1, 7) = 'sha256:')
);

CREATE TABLE IF NOT EXISTS fmea_scoring_rule_packs (
    workspace_id TEXT NOT NULL,
    rule_pack_id TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('registered','retired')),
    rule_hash TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    rule_json TEXT NOT NULL CHECK (length(rule_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, rule_pack_id, version),
    UNIQUE (workspace_id, rule_hash),
    CHECK (length(rule_hash) = 71 AND substr(rule_hash, 1, 7) = 'sha256:'),
    CHECK (length(source_hash) = 71 AND substr(source_hash, 1, 7) = 'sha256:')
);

CREATE TABLE IF NOT EXISTS fmea_assistance_suggestions (
    suggestion_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_record_version INTEGER NOT NULL CHECK (target_record_version > 0),
    evidence_pack_ids_json TEXT NOT NULL CHECK (length(evidence_pack_ids_json) > 0),
    payload_json TEXT NOT NULL CHECK (length(payload_json) > 0),
    evidence_ids_json TEXT NOT NULL CHECK (length(evidence_ids_json) > 0),
    conflict_ids_json TEXT NOT NULL CHECK (length(conflict_ids_json) > 0),
    uncertainty TEXT,
    model_hash TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    run_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    domain_pack_id TEXT,
    domain_pack_version TEXT,
    template_id TEXT,
    template_version TEXT,
    rule_pack_id TEXT,
    rule_pack_version TEXT,
    suggestion_record_version INTEGER NOT NULL CHECK (suggestion_record_version > 0),
    status TEXT NOT NULL CHECK (status IN ('proposed','stale')),
    applied INTEGER NOT NULL DEFAULT 0 CHECK (applied = 0),
    suggestion_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, suggestion_id, suggestion_record_version),
    UNIQUE (workspace_id, suggestion_hash),
    CHECK (length(model_hash) = 71 AND substr(model_hash, 1, 7) = 'sha256:'),
    CHECK (length(prompt_hash) = 71 AND substr(prompt_hash, 1, 7) = 'sha256:'),
    CHECK (length(suggestion_hash) = 71 AND substr(suggestion_hash, 1, 7) = 'sha256:'),
    CHECK ((domain_pack_id IS NULL) = (domain_pack_version IS NULL)),
    CHECK ((template_id IS NULL) = (template_version IS NULL)),
    CHECK ((rule_pack_id IS NULL) = (rule_pack_version IS NULL))
);

CREATE TABLE IF NOT EXISTS fmea_assistance_decisions (
    decision_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    suggestion_id TEXT NOT NULL REFERENCES fmea_assistance_suggestions(suggestion_id),
    suggestion_hash TEXT NOT NULL,
    suggestion_record_version INTEGER NOT NULL CHECK (suggestion_record_version > 0),
    target_record_version INTEGER NOT NULL CHECK (target_record_version > 0),
    action TEXT NOT NULL CHECK (action IN ('adopt','partial_adopt','edit_and_adopt','reject','defer','request_evidence')),
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type = 'human'),
    edits_json TEXT NOT NULL CHECK (length(edits_json) > 0),
    reason TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL,
    resulting_resource_type TEXT,
    resulting_resource_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, suggestion_id, suggestion_record_version),
    CHECK (length(suggestion_hash) = 71 AND substr(suggestion_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK ((resulting_resource_type IS NULL) = (resulting_resource_id IS NULL))
);

CREATE TABLE IF NOT EXISTS fmea_risk_proposals (
    proposal_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    row_id TEXT NOT NULL REFERENCES fmea_rows(row_id),
    source_record_version INTEGER NOT NULL CHECK (source_record_version > 0),
    evidence_pack_id TEXT NOT NULL REFERENCES evidence_packs(pack_id),
    domain_pack_id TEXT NOT NULL,
    domain_pack_version TEXT NOT NULL,
    rule_pack_id TEXT NOT NULL,
    rule_pack_version TEXT NOT NULL,
    dimensions_json TEXT NOT NULL CHECK (length(dimensions_json) > 0),
    reason TEXT NOT NULL,
    assistance_suggestion_id TEXT REFERENCES fmea_assistance_suggestions(suggestion_id),
    uncertainty TEXT,
    status TEXT NOT NULL CHECK (status = 'proposed'),
    proposal_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, row_id, proposal_id),
    UNIQUE (workspace_id, proposal_hash),
    CHECK (length(proposal_hash) = 71 AND substr(proposal_hash, 1, 7) = 'sha256:')
);

CREATE TABLE IF NOT EXISTS fmea_risk_assessments (
    assessment_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    row_id TEXT NOT NULL REFERENCES fmea_rows(row_id),
    source_record_version INTEGER NOT NULL CHECK (source_record_version > 0),
    evidence_pack_id TEXT NOT NULL REFERENCES evidence_packs(pack_id),
    domain_pack_id TEXT NOT NULL,
    domain_pack_version TEXT NOT NULL,
    rule_pack_id TEXT NOT NULL,
    rule_pack_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('unscored','proposed','reviewed','confirmed','invalidated')),
    dimensions_json TEXT NOT NULL CHECK (length(dimensions_json) > 0),
    derived_json TEXT,
    proposal_id TEXT REFERENCES fmea_risk_proposals(proposal_id),
    assistance_suggestion_id TEXT REFERENCES fmea_assistance_suggestions(suggestion_id),
    confirmer_actor_id TEXT,
    invalidated_reason TEXT,
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    assessment_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, row_id, record_version),
    CHECK (length(assessment_hash) = 71 AND substr(assessment_hash, 1, 7) = 'sha256:'),
    CHECK (status <> 'confirmed' OR (derived_json IS NOT NULL AND confirmer_actor_id IS NOT NULL)),
    CHECK (status <> 'invalidated' OR (invalidated_reason IS NOT NULL AND length(invalidated_reason) > 0))
);

CREATE TABLE IF NOT EXISTS fmea_risk_decisions (
    decision_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    row_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL REFERENCES fmea_risk_assessments(assessment_id),
    proposal_id TEXT REFERENCES fmea_risk_proposals(proposal_id),
    decision_type TEXT NOT NULL CHECK (decision_type IN ('confirm','reject','invalidate')),
    from_status TEXT NOT NULL CHECK (from_status IN ('unscored','proposed','reviewed','confirmed','invalidated')),
    to_status TEXT NOT NULL CHECK (to_status IN ('unscored','proposed','reviewed','confirmed','invalidated')),
    expected_assessment_version INTEGER NOT NULL CHECK (expected_assessment_version > 0),
    applied_assessment_version INTEGER NOT NULL CHECK (applied_assessment_version > 0),
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human','system')),
    decision_json TEXT NOT NULL CHECK (length(decision_json) > 0),
    idempotency_scope TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, assessment_id, applied_assessment_version),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK (
        (decision_type IN ('confirm','reject') AND actor_type = 'human')
        OR (decision_type = 'invalidate' AND actor_type IN ('human','system'))
    )
);

CREATE TABLE IF NOT EXISTS fmea_outbox_events (
    event_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'pending'),
    payload_json TEXT NOT NULL CHECK (length(payload_json) > 0),
    payload_hash TEXT NOT NULL,
    idempotency_scope TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, aggregate_type, aggregate_id, event_type, payload_hash),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:')
);

CREATE INDEX IF NOT EXISTS idx_fmea_domain_packs_workspace_identity
    ON fmea_domain_packs(workspace_id, pack_id, version, status);
CREATE INDEX IF NOT EXISTS idx_fmea_scoring_rule_packs_workspace_identity
    ON fmea_scoring_rule_packs(workspace_id, rule_pack_id, version, status);
CREATE INDEX IF NOT EXISTS idx_fmea_assistance_suggestions_workspace_target
    ON fmea_assistance_suggestions(workspace_id, target_type, target_id, kind, status, suggestion_record_version);
CREATE INDEX IF NOT EXISTS idx_fmea_assistance_decisions_workspace_suggestion
    ON fmea_assistance_decisions(workspace_id, suggestion_id, created_at, decision_id);
CREATE INDEX IF NOT EXISTS idx_fmea_risk_proposals_workspace_row
    ON fmea_risk_proposals(workspace_id, row_id, status, source_record_version);
CREATE INDEX IF NOT EXISTS idx_fmea_risk_assessments_workspace_row
    ON fmea_risk_assessments(workspace_id, row_id, status, record_version);
CREATE INDEX IF NOT EXISTS idx_fmea_risk_decisions_workspace_row
    ON fmea_risk_decisions(workspace_id, row_id, created_at, decision_id);
CREATE INDEX IF NOT EXISTS idx_fmea_outbox_workspace_aggregate
    ON fmea_outbox_events(workspace_id, aggregate_type, aggregate_id, created_at, event_id);

CREATE TRIGGER IF NOT EXISTS fmea_domain_packs_no_update
BEFORE UPDATE ON fmea_domain_packs
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_domain_packs');
END;

CREATE TRIGGER IF NOT EXISTS fmea_domain_packs_no_delete
BEFORE DELETE ON fmea_domain_packs
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_domain_packs');
END;

CREATE TRIGGER IF NOT EXISTS fmea_scoring_rule_packs_no_update
BEFORE UPDATE ON fmea_scoring_rule_packs
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_scoring_rule_packs');
END;

CREATE TRIGGER IF NOT EXISTS fmea_scoring_rule_packs_no_delete
BEFORE DELETE ON fmea_scoring_rule_packs
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_scoring_rule_packs');
END;

CREATE TRIGGER IF NOT EXISTS fmea_assistance_suggestions_no_update
BEFORE UPDATE ON fmea_assistance_suggestions
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_assistance_suggestions');
END;

CREATE TRIGGER IF NOT EXISTS fmea_assistance_suggestions_no_delete
BEFORE DELETE ON fmea_assistance_suggestions
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_assistance_suggestions');
END;

CREATE TRIGGER IF NOT EXISTS fmea_assistance_decisions_no_update
BEFORE UPDATE ON fmea_assistance_decisions
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_assistance_decisions');
END;

CREATE TRIGGER IF NOT EXISTS fmea_assistance_decisions_no_delete
BEFORE DELETE ON fmea_assistance_decisions
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_assistance_decisions');
END;

CREATE TRIGGER IF NOT EXISTS fmea_risk_proposals_no_update
BEFORE UPDATE ON fmea_risk_proposals
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_risk_proposals');
END;

CREATE TRIGGER IF NOT EXISTS fmea_risk_proposals_no_delete
BEFORE DELETE ON fmea_risk_proposals
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_risk_proposals');
END;

CREATE TRIGGER IF NOT EXISTS fmea_risk_assessments_confirmed_no_update
BEFORE UPDATE ON fmea_risk_assessments
WHEN OLD.status = 'confirmed'
BEGIN
    SELECT RAISE(ABORT, 'immutable confirmed fmea_risk_assessments');
END;

CREATE TRIGGER IF NOT EXISTS fmea_risk_assessments_confirmed_no_delete
BEFORE DELETE ON fmea_risk_assessments
WHEN OLD.status = 'confirmed'
BEGIN
    SELECT RAISE(ABORT, 'immutable confirmed fmea_risk_assessments');
END;

CREATE TRIGGER IF NOT EXISTS fmea_risk_decisions_no_update
BEFORE UPDATE ON fmea_risk_decisions
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_risk_decisions');
END;

CREATE TRIGGER IF NOT EXISTS fmea_risk_decisions_no_delete
BEFORE DELETE ON fmea_risk_decisions
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_risk_decisions');
END;

CREATE TRIGGER IF NOT EXISTS fmea_outbox_events_no_update
BEFORE UPDATE ON fmea_outbox_events
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_outbox_events');
END;

CREATE TRIGGER IF NOT EXISTS fmea_outbox_events_no_delete
BEFORE DELETE ON fmea_outbox_events
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_outbox_events');
END;
