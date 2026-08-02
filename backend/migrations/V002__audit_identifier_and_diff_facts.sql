-- Preserve the distinct FMC audit identifiers and normalized config-change facts.
-- Additive/idempotent; safe to run while the old application is serving reads.

ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS audit_id varchar(128);
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS record_id varchar(128);
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS snapshot_id varchar(128);
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS source varchar(255);
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS subsystem varchar(255);
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS message text;
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS values_added jsonb;
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS values_deleted jsonb;
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS values_updated jsonb;
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS config_changes jsonb;
ALTER TABLE fmc_audit_records ADD COLUMN IF NOT EXISTS normalization_notes jsonb;

CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_audit_id ON fmc_audit_records (audit_id);
CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_record_id ON fmc_audit_records (record_id);
CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_snapshot_id ON fmc_audit_records (snapshot_id);
CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_subsystem ON fmc_audit_records (subsystem);
