-- Composite parent keys make every child reference workspace-safe.  These are
-- additive indexes on the v1/v2 tables and are created before v3 children.
CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_rows_workspace_row
    ON fmea_rows(workspace_id, row_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_packs_workspace_pack
    ON evidence_packs(workspace_id, pack_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_events_workspace_event
    ON audit_events(workspace_id, event_id);

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

CREATE TABLE IF NOT EXISTS fmea_assistance_audit_events (
    event_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human','model','system')),
    command TEXT NOT NULL,
    suggestion_id TEXT NOT NULL,
    decision_id TEXT,
    idempotency_scope TEXT NOT NULL,
    resource_path TEXT NOT NULL,
    canonical_payload_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    event_json TEXT NOT NULL CHECK (length(event_json) > 0),
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, event_id),
    CHECK (length(canonical_payload_hash) = 71 AND substr(canonical_payload_hash, 1, 7) = 'sha256:'),
    CHECK (length(event_hash) = 71 AND substr(event_hash, 1, 7) = 'sha256:')
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
    payload_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, suggestion_id, suggestion_record_version),
    UNIQUE (workspace_id, suggestion_id),
    UNIQUE (workspace_id, suggestion_hash),
    CHECK (length(model_hash) = 71 AND substr(model_hash, 1, 7) = 'sha256:'),
    CHECK (length(prompt_hash) = 71 AND substr(prompt_hash, 1, 7) = 'sha256:'),
    CHECK (length(suggestion_hash) = 71 AND substr(suggestion_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK ((domain_pack_id IS NULL) = (domain_pack_version IS NULL)),
    CHECK ((template_id IS NULL) = (template_version IS NULL)),
    CHECK ((rule_pack_id IS NULL) = (rule_pack_version IS NULL)),
    FOREIGN KEY (workspace_id, audit_event_id)
        REFERENCES fmea_assistance_audit_events(workspace_id, event_id)
);

CREATE TABLE IF NOT EXISTS fmea_assistance_decisions (
    decision_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    suggestion_id TEXT NOT NULL,
    suggestion_hash TEXT NOT NULL,
    suggestion_record_version INTEGER NOT NULL CHECK (suggestion_record_version > 0),
    target_record_version INTEGER NOT NULL CHECK (target_record_version > 0),
    action TEXT NOT NULL CHECK (action IN ('adopt','partial_adopt','edit_and_adopt','reject','defer','request_evidence')),
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type = 'human'),
    edits_json TEXT NOT NULL CHECK (length(edits_json) > 0),
    decision_json TEXT NOT NULL CHECK (length(decision_json) > 0),
    reason TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL,
    audit_event_id TEXT NOT NULL UNIQUE,
    resulting_resource_type TEXT,
    resulting_resource_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, suggestion_id, suggestion_record_version),
    CHECK (length(suggestion_hash) = 71 AND substr(suggestion_hash, 1, 7) = 'sha256:'),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK ((resulting_resource_type IS NULL) = (resulting_resource_id IS NULL)),
    FOREIGN KEY (workspace_id, suggestion_id)
        REFERENCES fmea_assistance_suggestions(workspace_id, suggestion_id),
    FOREIGN KEY (workspace_id, audit_event_id)
        REFERENCES fmea_assistance_audit_events(workspace_id, event_id)
);

CREATE TABLE IF NOT EXISTS fmea_risk_proposals (
    proposal_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    row_id TEXT NOT NULL,
    source_record_version INTEGER NOT NULL CHECK (source_record_version > 0),
    evidence_pack_id TEXT NOT NULL,
    domain_pack_id TEXT NOT NULL,
    domain_pack_version TEXT NOT NULL,
    rule_pack_id TEXT NOT NULL,
    rule_pack_version TEXT NOT NULL,
    dimensions_json TEXT NOT NULL CHECK (length(dimensions_json) > 0),
    reason TEXT NOT NULL,
    assistance_suggestion_id TEXT,
    uncertainty TEXT,
    status TEXT NOT NULL CHECK (status = 'proposed'),
    proposal_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, row_id, proposal_id),
    UNIQUE (workspace_id, proposal_hash),
    CHECK (length(proposal_hash) = 71 AND substr(proposal_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, row_id) REFERENCES fmea_rows(workspace_id, row_id),
    FOREIGN KEY (workspace_id, evidence_pack_id) REFERENCES evidence_packs(workspace_id, pack_id),
    FOREIGN KEY (workspace_id, assistance_suggestion_id)
        REFERENCES fmea_assistance_suggestions(workspace_id, suggestion_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_risk_proposals_workspace_proposal
    ON fmea_risk_proposals(workspace_id, proposal_id);

CREATE TABLE IF NOT EXISTS fmea_risk_assessments (
    assessment_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    row_id TEXT NOT NULL,
    source_record_version INTEGER NOT NULL CHECK (source_record_version > 0),
    evidence_pack_id TEXT NOT NULL,
    domain_pack_id TEXT NOT NULL,
    domain_pack_version TEXT NOT NULL,
    rule_pack_id TEXT NOT NULL,
    rule_pack_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('unscored','proposed','reviewed','confirmed','invalidated')),
    dimensions_json TEXT NOT NULL CHECK (length(dimensions_json) > 0),
    derived_json TEXT,
    proposal_id TEXT,
    assistance_suggestion_id TEXT,
    confirmer_actor_id TEXT,
    invalidated_reason TEXT,
    record_version INTEGER NOT NULL CHECK (record_version > 0),
    assessment_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, row_id, record_version),
    CHECK (length(assessment_hash) = 71 AND substr(assessment_hash, 1, 7) = 'sha256:'),
    CHECK (
        status <> 'confirmed'
        OR (
            derived_json IS NOT NULL AND length(derived_json) > 0
            AND confirmer_actor_id IS NOT NULL AND length(confirmer_actor_id) > 0
            AND proposal_id IS NOT NULL AND length(proposal_id) > 0
        )
    ),
    CHECK (status <> 'invalidated' OR (invalidated_reason IS NOT NULL AND length(invalidated_reason) > 0)),
    FOREIGN KEY (workspace_id, row_id) REFERENCES fmea_rows(workspace_id, row_id),
    FOREIGN KEY (workspace_id, evidence_pack_id) REFERENCES evidence_packs(workspace_id, pack_id),
    FOREIGN KEY (workspace_id, proposal_id) REFERENCES fmea_risk_proposals(workspace_id, proposal_id),
    FOREIGN KEY (workspace_id, assistance_suggestion_id)
        REFERENCES fmea_assistance_suggestions(workspace_id, suggestion_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fmea_risk_assessments_workspace_assessment
    ON fmea_risk_assessments(workspace_id, assessment_id);

CREATE TABLE IF NOT EXISTS fmea_risk_decisions (
    decision_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    row_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    proposal_id TEXT,
    audit_event_id TEXT NOT NULL,
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
        (decision_type = 'confirm' AND from_status IN ('proposed','reviewed') AND to_status = 'confirmed' AND actor_type = 'human')
        OR (decision_type = 'reject' AND from_status = 'proposed' AND to_status = 'reviewed' AND actor_type = 'human')
        OR (decision_type = 'invalidate' AND from_status IN ('unscored','proposed','reviewed','confirmed')
            AND to_status = 'invalidated' AND actor_type IN ('human','system'))
    ),
    FOREIGN KEY (workspace_id, row_id) REFERENCES fmea_rows(workspace_id, row_id),
    FOREIGN KEY (workspace_id, assessment_id) REFERENCES fmea_risk_assessments(workspace_id, assessment_id),
    FOREIGN KEY (workspace_id, proposal_id) REFERENCES fmea_risk_proposals(workspace_id, proposal_id),
    FOREIGN KEY (workspace_id, audit_event_id) REFERENCES audit_events(workspace_id, event_id)
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
CREATE INDEX IF NOT EXISTS idx_fmea_assistance_audit_workspace_target
    ON fmea_assistance_audit_events(workspace_id, target_type, target_id, created_at, event_id);
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

CREATE TRIGGER IF NOT EXISTS fmea_assistance_audit_events_no_update
BEFORE UPDATE ON fmea_assistance_audit_events
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_assistance_audit_events');
END;

CREATE TRIGGER IF NOT EXISTS fmea_assistance_audit_events_no_delete
BEFORE DELETE ON fmea_assistance_audit_events
BEGIN
    SELECT RAISE(ABORT, 'immutable fmea_assistance_audit_events');
END;

CREATE TRIGGER IF NOT EXISTS fmea_assistance_suggestions_audit_binding
BEFORE INSERT ON fmea_assistance_suggestions
WHEN NOT EXISTS (
    SELECT 1
    FROM fmea_assistance_audit_events AS audit
    WHERE audit.workspace_id = NEW.workspace_id
      AND audit.event_id = NEW.audit_event_id
      AND audit.target_type = NEW.target_type
      AND audit.target_id = NEW.target_id
      AND audit.suggestion_id = NEW.suggestion_id
      AND audit.decision_id IS NULL
      AND audit.canonical_payload_hash = NEW.payload_hash
      AND EXISTS (
          SELECT 1
          FROM idempotency_records AS idem
          WHERE idem.scope_key = audit.idempotency_scope
            AND idem.payload_hash = NEW.payload_hash
            AND idem.state IN ('reserved','completed')
      )
)
BEGIN
    SELECT RAISE(ABORT, 'assistance suggestion audit mismatch');
END;

CREATE TRIGGER IF NOT EXISTS fmea_assistance_decisions_audit_binding
BEFORE INSERT ON fmea_assistance_decisions
WHEN NOT EXISTS (
    SELECT 1
    FROM fmea_assistance_audit_events AS audit
    JOIN fmea_assistance_suggestions AS suggestion
      ON suggestion.workspace_id = NEW.workspace_id
     AND suggestion.suggestion_id = NEW.suggestion_id
    WHERE audit.workspace_id = NEW.workspace_id
      AND audit.event_id = NEW.audit_event_id
      AND audit.target_type = suggestion.target_type
      AND audit.target_id = suggestion.target_id
      AND audit.suggestion_id = NEW.suggestion_id
      AND audit.decision_id = NEW.decision_id
      AND audit.actor_id = NEW.actor_id
      AND audit.actor_type = NEW.actor_type
      AND audit.canonical_payload_hash = NEW.payload_hash
      AND EXISTS (
          SELECT 1
          FROM idempotency_records AS idem
          WHERE idem.scope_key = audit.idempotency_scope
            AND idem.payload_hash = NEW.payload_hash
            AND idem.state IN ('reserved','completed')
      )
)
BEGIN
    SELECT RAISE(ABORT, 'assistance decision audit mismatch');
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

CREATE TRIGGER IF NOT EXISTS fmea_risk_assessments_transition_guard
BEFORE UPDATE ON fmea_risk_assessments
WHEN NOT (
    NEW.record_version = OLD.record_version + 1
    AND (
        (OLD.status = 'proposed' AND NEW.status IN ('reviewed', 'confirmed', 'invalidated'))
        OR (OLD.status = 'reviewed' AND NEW.status IN ('confirmed', 'invalidated'))
        OR (OLD.status = 'unscored' AND NEW.status = 'invalidated')
    )
)
BEGIN
    SELECT RAISE(ABORT, 'illegal fmea risk assessment transition');
END;

CREATE TRIGGER IF NOT EXISTS fmea_risk_assessments_requires_decision
BEFORE UPDATE ON fmea_risk_assessments
WHEN NOT EXISTS (
    SELECT 1
    FROM fmea_risk_decisions AS d
    WHERE d.workspace_id = OLD.workspace_id
      AND d.assessment_id = OLD.assessment_id
      AND d.row_id = OLD.row_id
      AND (d.proposal_id IS NEW.proposal_id)
      AND d.from_status = OLD.status
      AND d.to_status = NEW.status
      AND d.expected_assessment_version = OLD.record_version
      AND d.applied_assessment_version = NEW.record_version
      AND (
          (NEW.status = 'confirmed' AND d.decision_type = 'confirm')
          OR (NEW.status = 'reviewed' AND d.decision_type = 'reject')
          OR (NEW.status = 'invalidated' AND d.decision_type = 'invalidate')
      )
)
BEGIN
    SELECT RAISE(ABORT, 'risk assessment transition requires matching decision and audit');
END;

CREATE TRIGGER IF NOT EXISTS fmea_risk_decisions_audit_binding
BEFORE INSERT ON fmea_risk_decisions
WHEN NOT EXISTS (
    SELECT 1
    FROM audit_events AS a
    WHERE a.workspace_id = NEW.workspace_id
      AND a.event_id = NEW.audit_event_id
      AND a.row_id = NEW.row_id
      AND a.decision_id = NEW.decision_id
      AND a.actor_id = NEW.actor_id
      AND a.actor_type = NEW.actor_type
      AND a.canonical_payload_hash = NEW.payload_hash
)
BEGIN
    SELECT RAISE(ABORT, 'risk decision requires matching audit event');
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
