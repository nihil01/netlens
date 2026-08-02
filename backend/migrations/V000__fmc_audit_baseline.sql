-- Existing FMC audit module baseline for clean installations.
-- Additive/idempotent: existing deployments are left unchanged.

CREATE TABLE IF NOT EXISTS fmc_audit_records (
    id serial PRIMARY KEY,
    fmc_id varchar(128) NOT NULL UNIQUE,
    timestamp timestamptz NOT NULL,
    user_name varchar(255),
    user_id varchar(128),
    source_ip varchar(45),
    action varchar(32),
    object_type varchar(128),
    object_name varchar(512),
    object_id varchar(128),
    parent_type varchar(128),
    parent_name varchar(512),
    parent_id varchar(128),
    before_json jsonb,
    after_json jsonb,
    changed_fields jsonb,
    refs_added jsonb,
    refs_removed jsonb,
    raw_json jsonb,
    collected_at timestamptz DEFAULT now(),
    risk_score smallint DEFAULT 0,
    risk_factors jsonb,
    deployment_id varchar(128),
    deployed boolean DEFAULT false,
    deploy_success boolean
);
CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_timestamp ON fmc_audit_records (timestamp);
CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_user_name ON fmc_audit_records (user_name);
CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_action ON fmc_audit_records (action);
CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_object_type ON fmc_audit_records (object_type);
CREATE INDEX IF NOT EXISTS ix_fmc_audit_records_risk_score ON fmc_audit_records (risk_score);
CREATE INDEX IF NOT EXISTS idx_audit_obj ON fmc_audit_records (object_type, object_name);

CREATE TABLE IF NOT EXISTS fmc_deployments (
    id serial PRIMARY KEY,
    fmc_id varchar(128) NOT NULL UNIQUE,
    name varchar(512),
    status varchar(64),
    started_at timestamptz,
    completed_at timestamptz,
    triggered_by varchar(255),
    device_count integer DEFAULT 0,
    success_count integer DEFAULT 0,
    failed_count integer DEFAULT 0,
    devices jsonb,
    raw_json jsonb,
    collected_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fmc_user_stats (
    id serial PRIMARY KEY,
    user_name varchar(255) NOT NULL,
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    total_changes integer DEFAULT 0,
    adds integer DEFAULT 0,
    updates integer DEFAULT 0,
    deletes integer DEFAULT 0,
    avg_risk_score double precision DEFAULT 0,
    max_risk_score smallint DEFAULT 0,
    objects_touched jsonb,
    computed_at timestamptz DEFAULT now(),
    CONSTRAINT uq_user_stats_period UNIQUE (user_name, period_start, period_end)
);
