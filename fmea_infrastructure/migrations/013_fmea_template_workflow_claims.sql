-- Durable template workflow claims and the narrowly typed template audit chain.
-- Migrations 010-012 remain immutable; legacy rows may have NULL link columns,
-- while all rows written after this migration must carry the full chain.

ALTER TABLE fmea_template_patch_candidates
    ADD COLUMN suggestion_id TEXT;

ALTER TABLE fmea_template_patch_candidates
    ADD COLUMN audit_event_id TEXT;

ALTER TABLE fmea_template_patch_candidates
    ADD COLUMN outbox_event_id TEXT;

ALTER TABLE fmea_template_patch_decisions
    ADD COLUMN audit_event_id TEXT;

ALTER TABLE fmea_template_patch_decisions
    ADD COLUMN outbox_event_id TEXT;

CREATE TABLE fmea_template_audit_events (
    workspace_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    patch_id TEXT,
    draft_id TEXT NOT NULL,
    suggestion_id TEXT,
    decision_id TEXT,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'model', 'system')),
    command TEXT NOT NULL CHECK (
        command IN ('fmea.template.import', 'fmea.template.patch.suggest',
                    'fmea.template.patch.accept', 'fmea.template.patch.reject')
    ),
    action TEXT NOT NULL CHECK (action IN ('imported', 'suggested', 'accepted', 'rejected')),
    idempotency_scope TEXT NOT NULL,
    canonical_payload_hash TEXT NOT NULL,
    outbox_event_id TEXT NOT NULL,
    event_json TEXT NOT NULL CHECK (length(event_json) > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, event_id),
    UNIQUE (workspace_id, idempotency_scope),
    UNIQUE (workspace_id, outbox_event_id),
    CHECK ((action IN ('imported', 'suggested')) = (decision_id IS NULL)),
    CHECK ((action = 'imported') = (patch_id IS NULL AND suggestion_id IS NULL)),
    CHECK ((action <> 'imported') = (patch_id IS NOT NULL AND suggestion_id IS NOT NULL)),
    CHECK (length(canonical_payload_hash) = 71 AND substr(canonical_payload_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (workspace_id, draft_id)
        REFERENCES fmea_template_drafts(workspace_id, draft_id),
    FOREIGN KEY (outbox_event_id)
        REFERENCES fmea_outbox_events(event_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE fmea_template_patch_generation_claims (
    workspace_id TEXT NOT NULL,
    patch_id TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (workspace_id, patch_id),
    UNIQUE (idempotency_scope),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    FOREIGN KEY (idempotency_scope)
        REFERENCES idempotency_records(scope_key)
);

CREATE TABLE fmea_template_patch_decision_intents (
    workspace_id TEXT NOT NULL,
    patch_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    suggestion_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('accepted', 'rejected')),
    idempotency_scope TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    decision_json TEXT NOT NULL CHECK (length(decision_json) > 0),
    canonical_json_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('reserved', 'completed')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (workspace_id, patch_id),
    UNIQUE (workspace_id, decision_id),
    UNIQUE (idempotency_scope),
    CHECK (length(payload_hash) = 71 AND substr(payload_hash, 1, 7) = 'sha256:'),
    CHECK (length(canonical_json_hash) = 71 AND substr(canonical_json_hash, 1, 7) = 'sha256:'),
    CHECK ((state = 'reserved') = (completed_at IS NULL)),
    FOREIGN KEY (workspace_id, patch_id)
        REFERENCES fmea_template_patch_candidates(workspace_id, patch_id),
    FOREIGN KEY (idempotency_scope)
        REFERENCES idempotency_records(scope_key)
);

CREATE INDEX idx_fmea_template_audit_workspace_patch
    ON fmea_template_audit_events(workspace_id, patch_id, created_at, event_id);

CREATE INDEX idx_fmea_template_generation_claims_scope
    ON fmea_template_patch_generation_claims(idempotency_scope, completed_at);

CREATE INDEX idx_fmea_template_decision_intents_state
    ON fmea_template_patch_decision_intents(workspace_id, state, created_at, patch_id);

CREATE TRIGGER fmea_template_audit_events_no_update
BEFORE UPDATE ON fmea_template_audit_events
BEGIN SELECT RAISE(ABORT, 'immutable fmea_template_audit_events'); END;

CREATE TRIGGER fmea_template_audit_events_no_delete
BEFORE DELETE ON fmea_template_audit_events
BEGIN SELECT RAISE(ABORT, 'immutable fmea_template_audit_events'); END;

CREATE TRIGGER fmea_template_patch_candidates_audit_binding
BEFORE INSERT ON fmea_template_patch_candidates
WHEN NEW.suggestion_id IS NULL
    OR NEW.audit_event_id IS NULL
    OR NEW.outbox_event_id IS NULL
    OR json_extract(NEW.suggestion_json, '$.suggestion_id') IS NOT NEW.suggestion_id
    OR NOT EXISTS (
        SELECT 1
        FROM fmea_template_audit_events AS audit
        JOIN fmea_outbox_events AS outbox ON outbox.event_id = NEW.outbox_event_id
        WHERE audit.workspace_id = NEW.workspace_id
          AND audit.event_id = NEW.audit_event_id
          AND audit.patch_id = NEW.patch_id
          AND audit.draft_id = NEW.draft_id
          AND audit.suggestion_id = NEW.suggestion_id
          AND audit.decision_id IS NULL
          AND audit.action = 'suggested'
          AND audit.command = 'fmea.template.patch.suggest'
          AND audit.outbox_event_id = outbox.event_id
          AND outbox.workspace_id = NEW.workspace_id
          AND outbox.aggregate_type = 'template_patch'
          AND outbox.aggregate_id = NEW.patch_id
          AND outbox.event_type = 'template.suggested'
          AND outbox.status = 'pending'
          AND outbox.idempotency_scope = audit.idempotency_scope
    )
BEGIN SELECT RAISE(ABORT, 'template candidate requires matching audit and outbox'); END;

CREATE TRIGGER fmea_template_patch_decisions_audit_binding
BEFORE INSERT ON fmea_template_patch_decisions
WHEN NEW.audit_event_id IS NULL
    OR NEW.outbox_event_id IS NULL
    OR NOT EXISTS (
        SELECT 1
        FROM fmea_template_audit_events AS audit
        JOIN fmea_outbox_events AS outbox ON outbox.event_id = NEW.outbox_event_id
        JOIN fmea_template_patch_candidates AS candidate
          ON candidate.workspace_id = NEW.workspace_id
         AND candidate.patch_id = NEW.patch_id
        WHERE audit.workspace_id = NEW.workspace_id
          AND audit.event_id = NEW.audit_event_id
          AND audit.patch_id = NEW.patch_id
          AND audit.draft_id = NEW.draft_id
          AND audit.suggestion_id = NEW.suggestion_id
          AND audit.decision_id = NEW.decision_id
          AND audit.action = NEW.action
          AND audit.command = CASE NEW.action
                WHEN 'accepted' THEN 'fmea.template.patch.accept'
                WHEN 'rejected' THEN 'fmea.template.patch.reject'
              END
          AND audit.outbox_event_id = outbox.event_id
          AND outbox.workspace_id = NEW.workspace_id
          AND outbox.aggregate_type = 'template_patch'
          AND outbox.aggregate_id = NEW.patch_id
          AND outbox.event_type = CASE NEW.action
                WHEN 'accepted' THEN 'template.accepted'
                WHEN 'rejected' THEN 'template.rejected'
              END
          AND outbox.status = 'pending'
          AND outbox.idempotency_scope = audit.idempotency_scope
          AND (
              candidate.suggestion_id = NEW.suggestion_id
              OR (
                  candidate.suggestion_id IS NULL
                  AND candidate.suggestion_json IS NOT NULL
                  AND json_extract(candidate.suggestion_json, '$.suggestion_id') IS NEW.suggestion_id
              )
          )
    )
BEGIN SELECT RAISE(ABORT, 'template decision requires matching audit and outbox'); END;

CREATE TRIGGER fmea_template_outbox_binding
BEFORE INSERT ON fmea_outbox_events
WHEN NEW.event_type IN ('template.imported', 'template.suggested', 'template.accepted', 'template.rejected')
    AND NOT EXISTS (
        SELECT 1
        FROM fmea_template_audit_events AS audit
        WHERE audit.workspace_id = NEW.workspace_id
          AND audit.outbox_event_id = NEW.event_id
          AND audit.idempotency_scope = NEW.idempotency_scope
          AND audit.action = CASE NEW.event_type
                WHEN 'template.imported' THEN 'imported'
                WHEN 'template.suggested' THEN 'suggested'
                WHEN 'template.accepted' THEN 'accepted'
                WHEN 'template.rejected' THEN 'rejected'
              END
    )
BEGIN SELECT RAISE(ABORT, 'template outbox requires matching audit'); END;
