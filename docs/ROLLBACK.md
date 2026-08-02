# NetLens rollback plan

## Application rollback

1. Stop rollout traffic and preserve logs plus current collector-run IDs.
2. Deploy the previously recorded backend/frontend image digests.
3. Keep the database at the migrated schema. V000–V004 are additive or loosen a nullability
   constraint, so the previous application can ignore new tables/columns.
4. Verify `/api/health/ready`, dependency freshness, and a read-only dashboard response.

Do not drop new tables or columns during an incident. Database rollback is a separate,
reviewed maintenance operation and is not required for application rollback.

## Configuration rollback

Restore the previous protected environment version, never a checked-in secret. If the
release involved credential rotation, retain the new credential and correct the config;
do not reactivate a known-exposed credential.

## Data recovery

- PostgreSQL is authoritative for history; restore from the pre-release backup only when
  corruption is proven.
- Redis can be rebuilt from collectors/local state, but flushing it is destructive and
  requires explicit incident approval.
- Raw FMC diagnostics are disposable after their retention period; audit, VPN, HA, and
  alert history are not.

## Rollback validation

Confirm there are no duplicate scheduled collectors, local data is marked with accurate
freshness, missing metrics remain null rather than zero, and no FMC write operation was
issued. Record the rollback reason and the last known good image/migration versions.
