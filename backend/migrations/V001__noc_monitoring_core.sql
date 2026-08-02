-- NetLens NOC current-state and history schema.
-- Additive only: no existing table or column is dropped or rewritten.

CREATE TABLE IF NOT EXISTS collector_runs (
    id uuid PRIMARY KEY,
    collector varchar(128) NOT NULL,
    source varchar(128) NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status varchar(32) NOT NULL,
    partial_result boolean NOT NULL DEFAULT false,
    records_received integer,
    duration_seconds double precision,
    error_category varchar(64),
    error text,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_collector_runs_collector ON collector_runs (collector);
CREATE INDEX IF NOT EXISTS idx_collector_runs_source ON collector_runs (source);
CREATE INDEX IF NOT EXISTS idx_collector_runs_started_at ON collector_runs (started_at);
CREATE INDEX IF NOT EXISTS idx_collector_runs_status ON collector_runs (status);

CREATE TABLE IF NOT EXISTS source_freshness (
    source varchar(128) PRIMARY KEY,
    state varchar(32) NOT NULL,
    last_attempt timestamptz,
    last_success timestamptz,
    collection_duration_seconds double precision,
    records_received integer,
    partial_result boolean NOT NULL DEFAULT false,
    error text,
    stale_threshold_seconds integer NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_source_freshness_state ON source_freshness (state);

CREATE TABLE IF NOT EXISTS fmc_devices_current (
    id bigserial PRIMARY KEY,
    domain_id uuid NOT NULL,
    device_id uuid NOT NULL,
    name varchar(512),
    host_name varchar(512),
    management_ip varchar(64),
    model varchar(255),
    model_number varchar(255),
    software_version varchar(128),
    serial_number varchar(255),
    is_connected boolean,
    health_status varchar(64),
    health_message text,
    deployment_status varchar(64),
    role varchar(64),
    status varchar(64),
    health_policy varchar(512),
    access_policy varchar(512),
    is_dummy_device boolean NOT NULL DEFAULT false,
    is_part_of_container boolean NOT NULL DEFAULT false,
    container_details jsonb NOT NULL DEFAULT '{}'::jsonb,
    capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
    aggregate_status varchar(32) NOT NULL,
    raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_collection_run_id uuid REFERENCES collector_runs(id) ON DELETE SET NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL,
    CONSTRAINT uq_fmc_device_domain_device UNIQUE (domain_id, device_id)
);
CREATE INDEX IF NOT EXISTS idx_fmc_devices_serial ON fmc_devices_current (serial_number);
CREATE INDEX IF NOT EXISTS idx_fmc_devices_health ON fmc_devices_current (health_status);
CREATE INDEX IF NOT EXISTS idx_fmc_devices_last_seen ON fmc_devices_current (last_seen_at);
CREATE INDEX IF NOT EXISTS idx_fmc_device_name ON fmc_devices_current (domain_id, name);

CREATE TABLE IF NOT EXISTS metric_samples (
    id bigserial PRIMARY KEY,
    timestamp timestamptz NOT NULL,
    domain_id uuid NOT NULL,
    device_id uuid,
    interface_id varchar(128),
    ha_pair_id uuid,
    vpn_tunnel_id varchar(256),
    metric_name varchar(128) NOT NULL,
    metric_value double precision,
    metric_status varchar(32) NOT NULL,
    source varchar(128) NOT NULL,
    metric_window varchar(32),
    collection_run_id uuid NOT NULL REFERENCES collector_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_metric_timestamp ON metric_samples (timestamp);
CREATE INDEX IF NOT EXISTS idx_metric_device ON metric_samples (device_id);
CREATE INDEX IF NOT EXISTS idx_metric_interface ON metric_samples (interface_id);
CREATE INDEX IF NOT EXISTS idx_metric_ha_pair ON metric_samples (ha_pair_id);
CREATE INDEX IF NOT EXISTS idx_metric_vpn_tunnel ON metric_samples (vpn_tunnel_id);
CREATE INDEX IF NOT EXISTS idx_metric_name ON metric_samples (metric_name);
CREATE INDEX IF NOT EXISTS idx_metric_status ON metric_samples (metric_status);
CREATE INDEX IF NOT EXISTS idx_metric_collection_run ON metric_samples (collection_run_id);
CREATE INDEX IF NOT EXISTS idx_metric_device_name_time
    ON metric_samples (device_id, metric_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_metric_interface_name_time
    ON metric_samples (interface_id, metric_name, timestamp DESC);

CREATE TABLE IF NOT EXISTS raw_fmc_responses (
    id bigserial PRIMARY KEY,
    collection_run_id uuid NOT NULL REFERENCES collector_runs(id) ON DELETE CASCADE,
    collected_at timestamptz NOT NULL,
    device_id uuid,
    endpoint text NOT NULL,
    http_status integer,
    duration_ms double precision,
    response_bytes integer NOT NULL DEFAULT 0,
    items_count integer,
    error_category varchar(64),
    payload jsonb,
    payload_omitted boolean NOT NULL DEFAULT false,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_fmc_run ON raw_fmc_responses (collection_run_id);
CREATE INDEX IF NOT EXISTS idx_raw_fmc_collected ON raw_fmc_responses (collected_at);
CREATE INDEX IF NOT EXISTS idx_raw_fmc_device ON raw_fmc_responses (device_id);
CREATE INDEX IF NOT EXISTS idx_raw_fmc_error ON raw_fmc_responses (error_category);
CREATE INDEX IF NOT EXISTS idx_raw_fmc_expires ON raw_fmc_responses (expires_at);

CREATE TABLE IF NOT EXISTS netbox_fmc_correlations (
    id bigserial PRIMARY KEY,
    netbox_device_id bigint NOT NULL,
    fmc_domain_id uuid NOT NULL,
    fmc_device_id uuid NOT NULL,
    method varchar(64) NOT NULL,
    confidence double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    matched_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    manual_override boolean NOT NULL DEFAULT false,
    last_verified_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_netbox_fmc_correlation
        UNIQUE (netbox_device_id, fmc_domain_id, fmc_device_id)
);
CREATE INDEX IF NOT EXISTS idx_correlation_netbox ON netbox_fmc_correlations (netbox_device_id);
CREATE INDEX IF NOT EXISTS idx_correlation_fmc ON netbox_fmc_correlations (fmc_device_id);

CREATE TABLE IF NOT EXISTS ha_pairs_current (
    pair_id uuid PRIMARY KEY,
    domain_id uuid NOT NULL,
    name varchar(512),
    pair_state varchar(32) NOT NULL,
    health_status varchar(64),
    health_message text,
    primary_device_id uuid NOT NULL,
    secondary_device_id uuid NOT NULL,
    active_member_id uuid,
    standby_member_id uuid,
    failover_link jsonb NOT NULL DEFAULT '{}'::jsonb,
    stateful_link jsonb NOT NULL DEFAULT '{}'::jsonb,
    monitored_interfaces jsonb NOT NULL DEFAULT '[]'::jsonb,
    last_role_transition_at timestamptz,
    last_health_transition_at timestamptz,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_ha_pair_domain ON ha_pairs_current (domain_id);
CREATE INDEX IF NOT EXISTS idx_ha_pair_state ON ha_pairs_current (pair_state);
CREATE INDEX IF NOT EXISTS idx_ha_pair_primary ON ha_pairs_current (primary_device_id);
CREATE INDEX IF NOT EXISTS idx_ha_pair_secondary ON ha_pairs_current (secondary_device_id);
CREATE INDEX IF NOT EXISTS idx_ha_pair_active ON ha_pairs_current (active_member_id);
CREATE INDEX IF NOT EXISTS idx_ha_pair_standby ON ha_pairs_current (standby_member_id);
CREATE INDEX IF NOT EXISTS idx_ha_pair_last_seen ON ha_pairs_current (last_seen_at);

CREATE TABLE IF NOT EXISTS ha_role_transitions (
    id bigserial PRIMARY KEY,
    domain_id uuid NOT NULL,
    pair_id uuid NOT NULL,
    device_id uuid NOT NULL,
    previous_role varchar(64),
    new_role varchar(64) NOT NULL,
    changed_at timestamptz NOT NULL,
    collection_run_id uuid REFERENCES collector_runs(id) ON DELETE CASCADE,
    raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_ha_transition_pair ON ha_role_transitions (pair_id);
CREATE INDEX IF NOT EXISTS idx_ha_transition_device ON ha_role_transitions (device_id);
CREATE INDEX IF NOT EXISTS idx_ha_transition_time ON ha_role_transitions (changed_at);

CREATE TABLE IF NOT EXISTS vpn_tunnels_current (
    tunnel_id varchar(256) PRIMARY KEY,
    domain_id uuid NOT NULL,
    name varchar(512),
    peer varchar(512),
    device_id uuid,
    policy varchar(512),
    current_status varchar(32) NOT NULL,
    is_flapping boolean NOT NULL DEFAULT false,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    state_changed_at timestamptz NOT NULL,
    last_up_at timestamptz,
    last_down_at timestamptz,
    transition_count integer NOT NULL DEFAULT 0,
    flap_count integer NOT NULL DEFAULT 0,
    raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_vpn_current_domain ON vpn_tunnels_current (domain_id);
CREATE INDEX IF NOT EXISTS idx_vpn_current_device ON vpn_tunnels_current (device_id);
CREATE INDEX IF NOT EXISTS idx_vpn_current_status ON vpn_tunnels_current (current_status);
CREATE INDEX IF NOT EXISTS idx_vpn_current_flapping ON vpn_tunnels_current (is_flapping);
CREATE INDEX IF NOT EXISTS idx_vpn_current_last_seen ON vpn_tunnels_current (last_seen_at);

CREATE TABLE IF NOT EXISTS vpn_tunnel_transitions (
    id bigserial PRIMARY KEY,
    tunnel_id varchar(256) NOT NULL REFERENCES vpn_tunnels_current(tunnel_id) ON DELETE CASCADE,
    previous_status varchar(32),
    new_status varchar(32) NOT NULL,
    changed_at timestamptz NOT NULL,
    duration_in_previous_state_seconds integer,
    collection_run_id uuid REFERENCES collector_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_vpn_transition_tunnel ON vpn_tunnel_transitions (tunnel_id);
CREATE INDEX IF NOT EXISTS idx_vpn_transition_time ON vpn_tunnel_transitions (changed_at);
CREATE INDEX IF NOT EXISTS idx_vpn_transition_tunnel_time
    ON vpn_tunnel_transitions (tunnel_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS health_alerts_current (
    alert_id varchar(256) PRIMARY KEY,
    domain_id uuid NOT NULL,
    device_id uuid,
    module_id varchar(256),
    severity varchar(32),
    source_status varchar(64),
    lifecycle_state varchar(32) NOT NULL,
    description text,
    details text,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    resolved_at timestamptz,
    reopen_count integer NOT NULL DEFAULT 0,
    repeat_count integer NOT NULL DEFAULT 0,
    raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_alert_domain ON health_alerts_current (domain_id);
CREATE INDEX IF NOT EXISTS idx_alert_device ON health_alerts_current (device_id);
CREATE INDEX IF NOT EXISTS idx_alert_module ON health_alerts_current (module_id);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON health_alerts_current (severity);
CREATE INDEX IF NOT EXISTS idx_alert_lifecycle ON health_alerts_current (lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_alert_last_seen ON health_alerts_current (last_seen_at);

CREATE TABLE IF NOT EXISTS health_alert_observations (
    id bigserial PRIMARY KEY,
    alert_id varchar(256) NOT NULL REFERENCES health_alerts_current(alert_id) ON DELETE CASCADE,
    observed_at timestamptz NOT NULL,
    lifecycle_state varchar(32) NOT NULL,
    severity varchar(32),
    source_status varchar(64),
    collection_run_id uuid REFERENCES collector_runs(id) ON DELETE CASCADE,
    raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_alert_observation_alert ON health_alert_observations (alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_observation_time ON health_alert_observations (observed_at);
