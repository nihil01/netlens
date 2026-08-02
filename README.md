# NetLens

NetLens is an internal Network Operations Center platform built with FastAPI, React,
PostgreSQL, Redis, NetBox, Cisco FMC, and OpenSearch integrations.

Production-hardening documentation:

- [Technical audit](docs/TECHNICAL_AUDIT.md)
- [Implementation report](docs/IMPLEMENTATION_REPORT.md)
- [Environment variables](docs/ENVIRONMENT.md)
- [Deployment procedure](docs/DEPLOYMENT.md)
- [NOC runbook](docs/RUNBOOK.md)
- [Rollback plan](docs/ROLLBACK.md)

The current release is not yet approved for unattended production use. See the
implementation report for the confirmed FMC permission blocker and remaining validation
gaps.

## Current capabilities

- FastAPI backend with liveness, readiness, dependency, and Prometheus endpoints.
- IP Intelligence endpoint: `GET /api/ip/{ip}/summary`.
- Real read-only NetBox REST API template for IP -> device/site/interface context.
- Real OpenSearch REST query template for source/destination IP activity summary.
- Daily scanner scheduling skeleton via APScheduler cron trigger.
- React + TypeScript UI with IP lookup page.
- Persisted FMC device metrics, source freshness, HA/VPN transitions, alert lifecycle,
  audit facts, and bounded raw diagnostics.
- Independent collectors, local-state dashboards, SSE updates, Operator mode, and NOC
  Wallboard mode.
- Docker Compose for backend, frontend, PostgreSQL, and Redis.
- Strict Keycloak JWT validation and role-protected sensitive operations; authentication
  remains disabled by default only for local development.

## Local development

```bash
cp .env.example .env
cd backend
uv sync --dev
uv run pytest
uv run uvicorn app.main:app --reload
```

In another shell:

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Apply the versioned migrations first as described in `docs/DEPLOYMENT.md`, then open the
port configured by `FRONTEND_PORT` (default `http://localhost`).

## NetBox integration

Configure in `.env`:

```env
NETBOX_URL=<netbox-base-url>
NETBOX_TOKEN=<netbox-api-token>
NETBOX_VERIFY_SSL=1
```

The backend calls NetBox read-only:

- `/api/ipam/ip-addresses/?q=<ip>`
- fallback `/api/ipam/ip-addresses/?address=<ip>/32` or `/128`
- `/api/dcim/interfaces/?device_id=<id>` when an assigned device is found

No NetBox write path exists yet. That is intentional.

## OpenSearch integration

Configure in `.env`:

```env
OPENSEARCH_URL=<opensearch-base-url>
OPENSEARCH_USERNAME=<username>
OPENSEARCH_PASSWORD=<password>
OPENSEARCH_INDEX_PATTERN=checkpoint-*,fmc-*,estreamer-*
OPENSEARCH_TIMESTAMP_FIELD=@timestamp
OPENSEARCH_SOURCE_IP_FIELDS=["source.ip","src_ip","src","client.ip"]
OPENSEARCH_DESTINATION_IP_FIELDS=["destination.ip","dst_ip","dst","server.ip"]
OPENSEARCH_DESTINATION_PORT_FIELD=destination.port
OPENSEARCH_ACTION_FIELD=event.action
```

The query template uses:

- time range: `now-24h` to `now`
- source/destination IP term matching
- top destination aggregation
- top destination port aggregation
- blocked/deny/drop action aggregation for security event count
- `INTERNAL_CIDRS` to split internal vs external peers in backend code

## Daily scanner schedule

Configure in `.env`:

```env
SCANNER_SCHEDULE_ENABLED=1
SCANNER_SCHEDULE_CRON=0 2 * * *
SCANNER_DEFAULT_SCOPE=netbox-management
SCANNER_PROFILE=safe
SCANNER_CREDENTIALS=[{"username":"scanner","password":"change-me"}]
```

The scheduled job runs the discovery, port check, NetBox sync, and nmap fingerprinting pipeline.

Completed scan profiles are stored in Redis under `scanner:profiles:latest` and exposed by
`GET /api/scanner/profiles`. A failed run does not replace the last successful snapshot.

NetBox inventory is also refreshed proactively so `/api/netbox/inventory` normally reads from Redis:

```env
NETBOX_DEVICE_CACHE_TTL_SECONDS=3600
INVENTORY_REFRESH_ENABLED=true
INVENTORY_REFRESH_CRON=*/30 * * * *
```

The scheduler uses the `Asia/Baku` timezone and starts an inventory cache warm-up when the API starts.

## Security rules

- Never commit NetBox tokens, device passwords, OpenSearch credentials, or Keycloak secrets.
- NetBox is read-only until an explicit approve/dry-run workflow exists.
- Scanner schedule defaults to disabled. Enable only after scope/concurrency limits are confirmed.
