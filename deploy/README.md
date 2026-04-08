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
3. Build and start the v2 Docker stack
4. Start the v2 backend and frontend services

## Deploying Updates

```bash
ssh your-server
sudo bash deploy/deploy.sh
```

The script will:

1. Pull latest `main`
2. Install backend and `frontend_v2` dependencies
3. Rebuild and refresh the v2 Docker stack
4. Run Alembic migrations
5. Restart `owl-backend-v2` and `owl-frontend-v2`
6. Health-check the v2 backend
7. Roll back automatically if the v2 health check fails

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
