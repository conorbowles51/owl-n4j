# Owl V2 Deployment Guide

## Architecture

This checkout is now the v2 deployment path.

It is designed to run alongside the already-deployed old app by using distinct
service names, container names, and host ports:

| Component | Old app | This repo / v2 |
|---|---:|---:|
| Frontend | `5173` | `5174` |
| Backend API | `8000` | `8002` |
| Evidence Engine API | `8001` | `8003` |
| PostgreSQL | `5432` | `5434` |
| Neo4j HTTP | `7474` | `7475` |
| Neo4j Bolt | `7687` | `7688` |
| ChromaDB | `8100` | `8101` |
| Redis | `6379` | `6380` |

Systemd services:

- `owl-backend-v2`
- `owl-frontend-v2`
- `owl-self-update` (optional, for admin-triggered updates)

Docker containers:

- `owl-v2-n4j`
- `owl-v2-pg`
- `owl-v2-chromadb`
- `owl-v2-redis`
- `owl-v2-evidence-api`
- `owl-v2-evidence-worker`

## First-Time Server Setup

1. Copy `.env.example` to `.env` and fill in the real values.
2. Run:

```bash
sudo bash deploy/setup-server.sh
```

That will:

1. Install `owl-backend-v2` and `owl-frontend-v2`
2. Install backend and `frontend_v2` dependencies
3. Build the frontend production bundle and start the v2 Docker stack
4. Start the v2 backend and frontend services

## Deploying Updates

```bash
ssh your-server
sudo bash deploy/deploy.sh
```

The script will:

1. Pull latest `main`
2. Install backend and `frontend_v2` dependencies
3. Build the frontend and configure its service to serve compiled assets
4. Rebuild and refresh the v2 Docker stack
5. Run Alembic migrations
6. Restart `owl-backend-v2` and `owl-frontend-v2`
7. Health-check the v2 backend
8. Roll back automatically if the v2 health check fails

The deployed frontend serves `frontend_v2/dist`; it does not expose Vite's
development `/src` module graph. The production server retains the `/api`
and WebSocket proxy used by the application.

Deployment and rollback check for queued/running engine work, accepted financial
imports, active statement review leases, unfinished running recovery campaigns,
and unfinished uploads/registration. The check is read-only and exits with code
75 when work exists or its state cannot be verified. Explicitly paused uploads
and campaigns, finished work, and results awaiting investigator review do not
block deployment. An abandoned upload still marked active must be completed or
explicitly paused; the gate does not silently expire it.

When work blocks a release, the deployment log includes a read-only diagnostic
breakdown: `engine_jobs`, `pending_financial_imports`, `financial_batch_leases`,
`recovery_items`, `upload_groups` and `upload_sessions`. Each nonempty category
shows its full blocking count and at most 10 record references, ordered by the
oldest available update timestamp, with the number of omitted references.
References include case/record UUIDs, applicable batch/run/group UUIDs, recognized
statuses, creation/update timestamps and active lease deadlines. Filenames,
document contents, worker tokens and credentials are never included. Missing
legacy diagnostic fields appear as `null`; unrecognized identifiers, statuses
or timestamps are redacted as `unrecognized`. Redaction never removes their
records from the blocking count.

These are counts of blocking records, not unique investigations or tasks: one
operation can be represented in multiple categories. Grouped upload members
count only through their group when that schema is available. Counts and samples
can change while work runs, and an old timestamp alone does not establish that
work is abandoned. The diagnostic does not pause, expire, retry or change any
record. A diagnostic query failure still defers the release with code 75 and
prints only the exception type, without connection details or query parameters.

Docker images are built before a fresh idle check permits container replacement.
Another check runs before the backend restarts. The check is retained in memory
across checkout changes, including automatic and standalone rollback. Rollback
uses the same deployment lock as deployment.

These checks are snapshots, not an intake lock: new work can arrive after the
last check. Existing workers finish their current jobs during graceful shutdown
(14,430-second worker wait and 14,500-second Docker grace). The backend service
gets a 14,500-second systemd stop window; Uvicorn waits for requests and the
application awaits its shielded atomic statement/recovery units. The installer
reloads this service configuration without restarting a running job. This is a
bounded graceful transition, not a guarantee for work that exceeds that window
or for a host forced shutdown.

The shutdown drop-in is installed from a regular temporary file and atomically
renamed before `daemon-reload`. It does not depend on `/dev/stdin`, which may be
absent in a service runner. A failed installation stops the release before the
backend restart; it never downgrades the ingestion gates or continues without
the configured grace. `bash deploy/tests/test-ingestion-shutdown.sh` exercises
real `install`/`mv` commands in a temporary directory with closed stdin,
permissions, repeated installation and destination failure. The same test was
validated on Linux with GNU coreutils and no `/dev/stdin` symlink.

If a release fails after building the frontend, its recovery trap restarts the
frontend using the bundle currently on disk. That bundle may already be new;
the restart does not prove that the backend or the whole release was updated.

## Admin-Triggered Updates

To allow admins to update the platform from the OWL admin UI:

1. Copy `deploy/owl-self-update.service.example` to `/etc/systemd/system/owl-self-update.service`
   and update `WorkingDirectory` / `ExecStart` to match the server checkout path.
2. Copy the narrow sudoers rules from `deploy/owl-self-update.sudoers.example`
   with `visudo`, replacing `owl-backend` with the Linux user that runs
   `owl-backend-v2`.
3. Enable the backend feature in `.env`:

```bash
PLATFORM_UPDATE_ENABLED=true
PLATFORM_UPDATE_BRANCH=main
PLATFORM_UPDATE_POLL_SECONDS=60
```

Set `PLATFORM_UPDATE_POLL_SECONDS=3600` later if you want hourly checks.

## Rolling Back

```bash
bash deploy/rollback.sh
bash deploy/rollback.sh <commit-hash>
```

## Logs

```bash
journalctl -u owl-backend-v2 -f
journalctl -u owl-frontend-v2 -f
docker logs -f owl-v2-evidence-api
docker logs -f owl-v2-evidence-worker
```
