# NetLens Docker Deployment

## Prerequisites

- Docker and Docker Compose installed
- Existing PostgreSQL instance
- Existing Redis instance

## 1. Create Database

Connect to your PostgreSQL and run:

```bash
psql -U postgres -f scripts/create-db.sql
```

Or manually:

```sql
CREATE DATABASE netlens;
CREATE USER netlens WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE netlens TO netlens;
ALTER USER netlens CREATEDB;
```

## 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values
```

Key variables to set:
- `POSTGRES_HOST` - your PostgreSQL host
- `POSTGRES_PASSWORD` - your PostgreSQL password
- `REDIS_HOST` - your Redis host
- `REDIS_PASSWORD` - your Redis password
- `NETBOX_URL` - your NetBox URL
- `NETBOX_TOKEN` - your NetBox API token
- `OPENSEARCH_URL` - your OpenSearch URL
- `OPENSEARCH_PASSWORD` - your OpenSearch password

## 3. Start Services

```bash
docker compose up -d
```

## 4. Setup Keycloak (if using auth)

1. Open Keycloak: `http://localhost:8080`
2. Login with admin credentials from .env
3. Create Realm: `netlens`
4. Create Client:
   - Client ID: `netlens`
   - Client Protocol: `openid-connect`
   - Access Type: `public`
   - Valid Redirect URIs: `http://localhost/*`
   - Web Origins: `http://localhost`
5. Create Roles: `admin`, `user`
6. Create users and assign roles
7. Update `.env` with `KEYCLOAK_ISSUER_URL=http://localhost:8080/realms/netlens`
8. Restart backend: `docker compose restart backend`

## Services

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 80 | Web UI |
| Backend | 8000 | API |
| Keycloak | 8080 | Auth (optional) |

## Commands

```bash
# Start all
docker compose up -d

# View logs
docker compose logs -f backend

# Restart backend
docker compose restart backend

# Stop all
docker compose down
```
