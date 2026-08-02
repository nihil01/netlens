# NetLens NOC runbook

## What healthy looks like

- `/api/health/live` returns `200` whenever the process event loop is alive.
- `/api/health/ready` returns `200` only when PostgreSQL, Redis, and the enabled scheduler
  are ready.
- `/api/health/dependencies` reports each integration and every persisted source freshness
  state separately.
- `/api/metrics` exposes collector, FMC HTTP, missing-metric, stale-source, scheduler-lag,
  database-write, and SSE-client telemetry.
- Operator views read PostgreSQL/Redis state; an FMC outage must not make API pages hang.

Alert on readiness failures, any `ERROR` source, sustained `STALE` sources, scheduler lag
greater than the source cadence, rising FMC HTTP errors, database write errors, and a
rapid increase in missing metrics.

## First response

1. Check `health/ready`, then `health/dependencies`.
2. Identify the failing source and compare `last_attempt`, `last_success`, duration,
   records received, partial-result flag, and error.
3. Inspect structured logs by `component`, `collection_run_id`, `device_id`, endpoint,
   HTTP status, and error category. Authorization headers and secret-shaped fields are
   masked.
4. Confirm the last successful local data remains visible with `Stale`/`Error`; do not
   interpret it as current.
5. Check the relevant collector run before restarting anything. Restarts do not repair
   permissions, stale UUIDs, invalid responses, or an overloaded FMC.

## Common incidents

### FMC aggregate metrics return 403

This deployment has already reproduced this condition with a valid current device UUID.
Device discovery may work while health endpoints are forbidden. Confirm the account can
read `/health/aggregatemetrics` and operational metrics. Request only the missing
read-only FMC permission. Do not broaden NetLens to configuration or deployment rights.

Expected UI/data state is `PERMISSION_ERROR`, never zero. After permissions are corrected,
wait for the next health cycle and confirm `last_success`, raw diagnostic metadata, and
capability state recover. One 5xx/403 does not permanently disable a capability.

### One device or metric category fails

Find the device-level `collection_run_id`. Aggregate collection first tries all metrics,
then category fallbacks for temporary/invalid responses, and operational CPU/memory where
applicable. Successful categories are persisted as `PARTIAL`; other devices continue.

### Dashboard is stale but dependencies are reachable

Check scheduler state/lag and PostgreSQL advisory-lock contention. Compare source cadence
with `last_attempt`. If a collector is repeatedly `skipped_locked`, locate another active
NetLens instance or a long-running job before restarting.

### Redis is down

Readiness becomes unhealthy and rate limiting fails open to avoid an application outage.
PostgreSQL history remains authoritative. Restore Redis, then confirm cache warming and
freshness; do not delete PostgreSQL state.

### PostgreSQL is down or full

Readiness fails. Restore connectivity/capacity, verify writes, then examine
`database_write_errors_total`. Do not run retention or schema changes until a backup is
confirmed.

### VPN flapping

Use the persisted tunnel timeline rather than the current snapshot. Confirm transition
timestamps and status quality. Default detection is three transitions in 15 minutes.
Transitions survive NetLens restarts.

### HA degraded/unknown

Treat configured primary/secondary and runtime active/standby as separate facts. Check
both member UUIDs and their individual collection results. A pair UUID must never be used
for member metrics.

## Maintenance

- Review retention execution daily and database growth weekly.
- Back up audit records and long-lived HA/VPN/alert history according to policy.
- Rotate integration credentials and verify no token appears in logs.
- Re-run read-only FMC diagnostics only during a controlled investigation.
- After upgrades, run backend unit tests, frontend lint/build, migration transaction
  checks, and an authenticated smoke test.

## Escalation evidence

Provide timestamps in UTC and Asia/Baku, collection run IDs, device/tunnel/pair IDs,
endpoint path without credentials, HTTP status, duration, response byte count, error
category, and freshness state. Raw payload access should be limited and audited.
