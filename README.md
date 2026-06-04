# NetLens

NetLens is a Network Intelligence Platform: FastAPI + React UI for IP investigation, NetBox context, OpenSearch activity summaries, and scheduled scanner jobs.

## Current MVP

- FastAPI backend with `/api/health`.
- IP Intelligence endpoint: `GET /api/ip/{ip}/summary`.
- Real read-only NetBox REST API template for IP -> device/site/interface context.
- Real OpenSearch REST query template for source/destination IP activity summary.
- Daily scanner scheduling skeleton via APScheduler cron trigger.
- React + TypeScript UI with IP lookup page.
- Docker Compose for backend, frontend, PostgreSQL, Redis.
- Keycloak JWT validation skeleton. Disabled by default for local development.

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

Open: `localhost:5173`

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Open: `localhost:8088`

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
```

Timezone is `Asia/Baku`. The scheduled job currently calls `ScannerService.run_scheduled_scan()`, which is the boundary where the real discovery/port/nmap pipeline will be wired next.

## Security rules

- Never commit NetBox tokens, device passwords, OpenSearch credentials, or Keycloak secrets.
- NetBox is read-only until an explicit approve/dry-run workflow exists.
- Scanner schedule defaults to disabled. Enable only after scope/concurrency limits are confirmed.
