-- Collector-run retention must not cascade-delete long-lived operational facts.
-- All changes are metadata-only and preserve existing rows.

ALTER TABLE metric_samples ALTER COLUMN collection_run_id DROP NOT NULL;
ALTER TABLE metric_samples DROP CONSTRAINT IF EXISTS metric_samples_collection_run_id_fkey;
ALTER TABLE metric_samples
    ADD CONSTRAINT metric_samples_collection_run_id_fkey
    FOREIGN KEY (collection_run_id) REFERENCES collector_runs(id) ON DELETE SET NULL;

ALTER TABLE ha_role_transitions
    DROP CONSTRAINT IF EXISTS ha_role_transitions_collection_run_id_fkey;
ALTER TABLE ha_role_transitions
    ADD CONSTRAINT ha_role_transitions_collection_run_id_fkey
    FOREIGN KEY (collection_run_id) REFERENCES collector_runs(id) ON DELETE SET NULL;

ALTER TABLE vpn_tunnel_transitions
    DROP CONSTRAINT IF EXISTS vpn_tunnel_transitions_collection_run_id_fkey;
ALTER TABLE vpn_tunnel_transitions
    ADD CONSTRAINT vpn_tunnel_transitions_collection_run_id_fkey
    FOREIGN KEY (collection_run_id) REFERENCES collector_runs(id) ON DELETE SET NULL;

ALTER TABLE health_alert_observations
    DROP CONSTRAINT IF EXISTS health_alert_observations_collection_run_id_fkey;
ALTER TABLE health_alert_observations
    ADD CONSTRAINT health_alert_observations_collection_run_id_fkey
    FOREIGN KEY (collection_run_id) REFERENCES collector_runs(id) ON DELETE SET NULL;
