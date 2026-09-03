-- Add durable transport metadata without rewriting immutable migrations.
-- Drafts and candidates are immutable version 1 resources; a decision advances
-- the logical patch resource to version 2.  The full suggestion envelope is
-- retained so a later CLI process can reproduce the exact proposal provenance.

ALTER TABLE fmea_template_drafts
    ADD COLUMN record_version INTEGER NOT NULL DEFAULT 1 CHECK (record_version = 1);

ALTER TABLE fmea_template_patch_candidates
    ADD COLUMN suggestion_json TEXT CHECK (suggestion_json IS NULL OR length(suggestion_json) > 0);

ALTER TABLE fmea_template_patch_candidates
    ADD COLUMN record_version INTEGER NOT NULL DEFAULT 1 CHECK (record_version = 1);

ALTER TABLE fmea_template_patch_decisions
    ADD COLUMN record_version INTEGER NOT NULL DEFAULT 2 CHECK (record_version = 2);

CREATE INDEX idx_fmea_template_patch_state
    ON fmea_template_patch_candidates(workspace_id, patch_id, record_version);
