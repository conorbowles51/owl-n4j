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
