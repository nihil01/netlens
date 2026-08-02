# NetLens deployment

## Preconditions

- PostgreSQL 16 and Redis 7 are reachable and backed up.
- A Keycloak realm/client is configured for production and emits the configured audience.
- Read-only integration accounts and trusted CA certificates are available.
- The FMC service account has health, HA, alert, VPN, audit, and deployment-history read
  permissions. A device-only account is insufficient.
- The host has enough storage for metrics and raw-response retention.

## Release procedure

1. Back up PostgreSQL and record the currently deployed image digests.
2. Copy `.env.example` to a protected environment file and supply all production values.
   Set `AUTH_ENABLED=true`, `VITE_AUTH_ENABLED=true`, and all TLS verification flags to
   `true`.
3. Apply migrations in lexical order. They are additive; do not enable
   `DATABASE_AUTO_CREATE_SCHEMA` in production.

   ```bash
   for migration in backend/migrations/V*.sql; do
     psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 -f "$migration"
   done
   ```

   `DATABASE_URL_SYNC` is a temporary `postgresql://...` operator connection used only by
   `psql`; the application continues to use `postgresql+asyncpg://...`.

4. Validate the resolved Compose configuration without printing it:

   ```bash
   docker compose config --quiet
   ```

5. Build and start the services:

   ```bash
   docker compose up -d --build
   ```

6. Gate the release on local-state readiness, then inspect dependency freshness:

   ```bash
   curl --fail http://127.0.0.1:9090/api/health/ready
   curl --fail http://127.0.0.1:9090/api/health/dependencies
   curl --fail http://127.0.0.1:9090/api/metrics
   ```

7. Verify that independent FMC jobs complete, source freshness becomes `FRESH` or a
   justified `DEGRADED`, and the dashboard never initiates a live FMC collection.
8. Validate Operator and Wallboard modes, SSE reconnect, a device metric history chart,
   HA roles, one VPN timeline, Health Alerts, and the Audit diff view.

## Migration safety

- `V000` creates the audit baseline for clean installations.
- `V001` adds current-state/history tables and indexes.
- `V002` adds distinct audit identifiers and normalized change facts.
- `V003` changes history foreign keys to `ON DELETE SET NULL` so collector-run retention
  cannot cascade-delete operational history.
- `V004` permits an unknown source event timestamp instead of fabricating collection time.

All four hardening migrations were syntax-checked against PostgreSQL inside transactions
that ended with `ROLLBACK`. Apply them once per environment and retain the migration log.

## Production topology notes

Collectors use PostgreSQL advisory locks, so multiple API replicas do not duplicate the
same scheduled job. Keep Redis and PostgreSQL external or on durable volumes. Route users
through the frontend nginx proxy so `/api` remains same-origin. Do not expose PostgreSQL,
Redis, FMC, NetBox, or OpenSearch directly to operator networks.
