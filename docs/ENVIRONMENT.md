# NetLens environment variables

Start from `.env.example`. Never commit the resulting `.env` file. Production secrets
must come from the deployment secret store, and credentials previously exposed in source
or documentation must be rotated before deployment.

## Required production values

| Variable | Purpose |
| --- | --- |
| `POSTGRES_*` / `DATABASE_URL` | PostgreSQL connection used for current state and history |
| `REDIS_*` / `REDIS_URL` | Cache, rate limiting, and scheduler advisory coordination |
| `AUTH_ENABLED=true` | Enables JWT authentication; required for production |
| `KEYCLOAK_ISSUER_URL` | Exact realm issuer URL |
| `KEYCLOAK_CLIENT_ID` | OIDC client ID |
| `KEYCLOAK_AUDIENCE` | Audience that must be present in backend JWTs |
| `NETBOX_URL`, `NETBOX_TOKEN` | Read-only NetBox API access |
| `OPENSEARCH_URL`, credentials | Read-only OpenSearch API access |
| `FMC_URL`, `FMC_USERNAME`, `FMC_PASSWORD` | Read-only FMC API account |

The FMC account must be able to read device records, aggregate and operational health
metrics, interfaces, HA pairs, health alerts, VPN tunnel status, audit records, config
changes, and deployment history. NetLens does not execute FMC writes.

## FMC collection controls

| Variable | Default | Meaning |
| --- | ---: | --- |
| `FMC_TIMEOUT_SECONDS` | 30 | Per-request timeout |
| `FMC_MAX_ATTEMPTS` | 5 | Initial request plus bounded retries |
| `FMC_MIN_REQUEST_INTERVAL_SECONDS` | 1.0 | Minimum quiet interval after every FMC request; shared across collectors in one process |
| `FMC_RATE_LIMIT_COOLDOWN_SECONDS` | 10.0 | Fallback pause after HTTP 429 when FMC omits `Retry-After` |
| `FMC_HEALTH_HISTORY_LOOKBACK_SECONDS` | 3600 | Historical Snort CPU fallback window |
| `FMC_HEALTH_HISTORY_STEP_SECONDS` | 60 | Historical health-metric sampling step |
| `FMC_POLICY_ANALYSIS_REFRESH_HOURS` | 24 | Read-only access-policy analysis interval |
| `FMC_DEVICE_HEALTH_REFRESH_SECONDS` | 60 | Health cadence |
| `FMC_DISCOVERY_REFRESH_MINUTES` | 10 | Discovery cadence |
| `FMC_INTERFACE_REFRESH_MINUTES` | 20 | Interface configuration cadence |
| `FMC_HA_REFRESH_SECONDS` | 60 | HA cadence |
| `FMC_ALERT_REFRESH_SECONDS` | 60 | Alert cadence |
| `FMC_VPN_REFRESH_MINUTES` | 1 | VPN cadence |
| `FMC_AUDIT_INTERVAL_MINUTES` | 2 | Audit cadence |
| `FMC_RAW_RESPONSE_MAX_BYTES` | 262144 | Maximum persisted payload size |
| `FMC_RAW_RESPONSE_RETENTION_DAYS` | 14 | Raw diagnostic retention |
| `FMC_DEVICE_HEALTH_STALE_SECONDS` | 900 | Health stale threshold |
| `FMC_VPN_FLAP_TRANSITION_THRESHOLD` | 3 | Transitions needed for flapping |
| `FMC_VPN_FLAP_WINDOW_SECONDS` | 900 | Flapping window |

`FMC_FULL_SCAN_ENABLED` is disabled by default because independent collectors are the
production path. Enable the legacy full scan only for controlled diagnostics.

## Retention

High-resolution metric samples default to 90 days, VPN transitions and alert history to
1095 days, collector runs to 30 days, and raw FMC responses to their row-specific expiry
(14 days by default). Configure `RETENTION_CRON` in Asia/Baku time.

## TLS and frontend

Set all `*_VERIFY_SSL=true` values in production and install the internal CA chain in the
container trust store. The `false` examples exist only for isolated development.

The frontend variables are build-time values. `VITE_AUTH_ENABLED` must match backend
`AUTH_ENABLED`; use the same Keycloak URL, realm, and client. `VITE_API_BASE_URL=/api`
uses the included nginx reverse proxy and avoids embedding an environment-specific host.

## Secret-handling rules

- Use separate, least-privilege read-only accounts for FMC, NetBox, and OpenSearch.
- Never place tokens in URLs, logs, screenshots, compose files, or audit exports.
- Rotate passwords/tokens immediately after suspected exposure.
- Keep `SCANNER_CREDENTIALS` in a secret store; leave it empty when the scanner is unused.
- Restrict the `admin` role to scheduler/manual refresh operations and grant `export`
  only to users allowed to extract audit data.
