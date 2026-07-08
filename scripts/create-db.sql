-- Create NetLens database (run this on your existing PostgreSQL)
-- Usage: psql -U postgres -f scripts/create-db.sql

SELECT 'CREATE DATABASE netlens'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'netlens')\gexec

CREATE USER netlens WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE netlens TO netlens;
ALTER USER netlens CREATEDB;
