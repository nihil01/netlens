# NetLens production-hardening implementation report

Date: 2026-08-01

## Outcome

The correctness and persistence foundations are implemented and verified locally. NetLens
is materially safer and more operable, but it is not yet approved for unattended 24/7
production use. The live FMC account cannot read aggregate health metrics (HTTP 403), and
the remaining limitations below require environment validation or further implementation.

## Aggregate-metrics root cause

The audit did not assume an FMC model limitation. A read-only diagnostic discovered 74
device records, selected a connected current Cisco Firepower 1120 record, and used that
device UUID. FMC returned HTTP 403 and `The user is not authorized` from the aggregate
metrics endpoint (128.5 ms, 111 bytes).

In this environment, the immediate root cause is missing read permission for FMC health
metrics. Two code defects amplified it: the old client collapsed 403 into an untyped
exception, and the API/frontend replaced absent interface counters with zero. Operators
therefore saw plausible but false zero metrics instead of a permission error.

The corrected path classifies permission failures, preserves null versus actual zero,
validates detail UUIDs, records bounded diagnostics, isolates failures by device, performs
category/operational fallback where valid, stores partial results, and uses an expiring
capability observation instead of permanently disabling an endpoint after one failure.

## Changes made

### Backend and data correctness

- Added reusable FMC HTTP/auth client with pagination safety, timeouts, bounded exponential
  retry with jitter, 401 refresh once, request pacing, typed error categories, and redacted
  diagnostics.
- Added discovery/detail UUID validation, duplicate/dummy/container/disconnected handling,
  per-device failure isolation, complete CPU/memory/disk/interface/fan normalization, and
  unambiguous interface matching.
- Added explicit metric states including `VALUE_ZERO`, `NO_DATA`, `PERMISSION_ERROR`,
  `STALE_DEVICE`, and `PARTIAL`; no missing metric is defaulted to zero.
- Removed live FMC collection from HTTP dashboard requests. APIs read local state only.
- Repaired FMC audit route families, distinct audit/record/snapshot identifiers, config
  changes, aliases, timestamp parsing, raw fact preservation/redaction, and deployment
  history normalization.
- Added strict JWT audience validation, role checks for audit export/manual refresh,
  Redis-backed rate limiting, structured secret-masking logs, and process telemetry.

### Database and retention

- Added durable collector runs, source freshness, FMC current devices, metric samples,
  bounded raw responses, correlation records, HA current state/transitions, VPN current
  state/transitions, and alert current state/observations.
- Added VPN availability, outage, MTBF, MTTR, transition, and flapping calculations.
- Added alert lifecycle state including resolution/reopen/flapping.
- Added configurable retention while protecting long-lived facts from collector-run
  cascade deletion.
- Kept current state permanent; no production migration was applied automatically.

### Scheduler and real time

- Split discovery, health, interfaces, HA, alerts, VPN, audit, inventory, scanner, and
  retention into independent jobs with jitter, coalescing, bounded execution, and
  PostgreSQL advisory locks across replicas.
- Added source freshness and persisted collector outcomes.
- Added authenticated SSE invalidation with heartbeat, event ID, bounded state, reconnect
  backoff, and React Query periodic fallback.

### Frontend

- Added nullable/error/stale metric presentation and persisted device history charts.
- Added HA and Health Alerts workspaces, VPN timeline/analytics, Audit dashboard/diff,
  data-freshness indicators, Operator mode, and a full-screen Wallboard mode.
- Added route-level lazy loading. The initial production chunk is approximately 440 KB;
  Monitoring and Audit load separately.
- Removed hardcoded API/Keycloak endpoints and enabled PKCE S256.

### Deployment and observability

- Added liveness, readiness, dependency, and Prometheus endpoints.
- Added backend/frontend healthchecks and restart policies; removed insecure Compose
  secret fallbacks and fixed frontend/backend auth-variable consistency.
- Documented environment variables, deployment, operations, and rollback.

## Database migrations

| Migration | Purpose |
| --- | --- |
| `V000` | Clean-install FMC audit baseline |
| `V001` | NOC current-state/history schema and indexes |
| `V002` | Audit raw identifiers and normalized diff facts |
| `V003` | Retention-safe history foreign keys |
| `V004` | Honest unknown audit timestamp semantics |

Migration SQL was exercised against PostgreSQL with `ON_ERROR_STOP` inside transactions
ending in `ROLLBACK`. No persistent database change was made during hardening.

## Verification results

- Backend tests: 71 passed.
- Backend Ruff: passed for `app` and `tests`.
- Frontend ESLint: passed.
- Frontend TypeScript/Vite production build: passed.
- Compose configuration: passed with validation-only credentials.
- PostgreSQL migration checks: passed with rollback, including V004.
- Live FMC read-only diagnostic: discovery passed (74 records); aggregate health failed
  with a confirmed permission 403. No token or password was logged.

## Known limitations / release blockers

1. FMC administrators must grant the service account read access to health endpoints;
   aggregate metrics cannot be accepted across all supported devices until then.
2. NetBox↔FMC correlation storage exists, but the reviewed-candidate/manual-override
   workflow and UI are not complete. No fuzzy auto-merge is performed.
3. HA current roles/transitions are persisted, but the HA workspace does not yet join all
   member CPU/memory/disk/interface history into one investigation view.
4. VPN core analytics and timeline work; outage histograms, distributions, and flap
   heatmap visualizations are not complete.
5. Alert history/filtering works; noisy-device/module and duration analytics remain.
6. Audit facts/diffs work; full change-session clustering, bulk-change detection, and
   deployment-correlation analysis remain.
7. High-resolution retention exists, but one-year downsampling is not implemented.
8. NetBox and OpenSearch have active dependency probes, but do not yet share the complete
   persisted collector/freshness pipeline used by FMC.
9. Browser E2E, load, long-soak, FMC failure-injection, backup/restore, and disaster-
   recovery exercises have not been run in the target NOC environment.
10. Frontend bearer-token storage remains a defense-in-depth concern; a BFF/httpOnly
    session design should be evaluated. Container least-privilege also needs a scanner-
    capability review before switching the backend to a non-root user.
11. The pre-existing tracked files `backend/test.json` and
    `backend/app/scanner/net_dataset.json` contain internal IP data. Their business need,
    classification, and repository retention must be reviewed before release; they were
    not deleted or rewritten during this non-destructive hardening pass.

## Future roadmap

1. Correct FMC permissions, replay live device matrix diagnostics, and sign off each
   metric/capability state.
2. Finish reviewed NetBox/FMC correlation and stale-device reconciliation.
3. Complete HA member investigations, alert analytics, VPN histograms/heatmaps, and audit
   session/deployment correlation.
4. Add downsampling/partition maintenance and capacity dashboards.
5. Add Playwright E2E, load/soak/failure-recovery suites, backup restore drills, and NOC
   wallboard acceptance tests.
6. Complete user-action audit, finer RBAC, BFF session assessment, and container
   least-privilege hardening.
