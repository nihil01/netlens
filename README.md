# NetLens

NetLens is a Network Intelligence Platform: FastAPI + React UI for IP investigation, NetBox context, OpenSearch activity summaries, and future scanner jobs.

## Current MVP

- FastAPI backend with `/api/health`.
- IP Intelligence endpoint: `GET /api/ip/{ip}/summary`.
- Mock NetBox/OpenSearch modes for safe early development.
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

Open: http://localhost:5173

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Open: http://localhost:8088

## Security rules

- Never commit NetBox tokens, device passwords, OpenSearch credentials, or Keycloak secrets.
- Keep `NETBOX_MODE=mock` and `OPENSEARCH_MODE=mock` until real mappings are confirmed.
- NetBox writes are intentionally not implemented in this MVP. First production mode must be read-only.
