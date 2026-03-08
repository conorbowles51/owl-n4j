# Owl Deployment Guide

## Architecture

```
Browser (port 80 or 8000)
    |
    v
  Nginx
    |--- /api/*     -->  Backend (127.0.0.1:8001)
    |--- /health    -->  Backend (127.0.0.1:8001)
    |--- /*         -->  frontend/dist/ (static files, SPA fallback)
```

- **Backend:** FastAPI/Uvicorn managed by systemd (`owl-backend` service)
- **Frontend:** Production build (`npm run build`) served as static files by Nginx
- **Database:** Neo4j + PostgreSQL via Docker Compose (unchanged)

---

## First-Time Server Setup

Run once on the GCP instance as root:

```bash
ssh your-server
sudo bash /home/conor/owl-console/owl-n4j/deploy/setup-server.sh
```

This installs Nginx, configures the systemd service, enables auto-start on boot, and does the initial frontend build.

---

## Deploying

After merging changes to `main`:

```bash
ssh your-server
sudo su - conor
cd ~/owl-console/owl-n4j
bash deploy/deploy.sh
```

The script will:
1. Check pre-flight conditions (disk space, Docker containers)
2. Stash any local changes on the server
3. Pull latest code from `main`
4. Install Python dependencies
5. Install frontend dependencies and build for production
6. Run database migrations (Alembic)
7. Restart the backend service
8. Reload Nginx
9. Run a health check
10. **Auto-rollback** if the health check fails

---

## Rolling Back

If something goes wrong after a deploy:

```bash
# Rollback to the last known good deploy
bash deploy/rollback.sh

# Rollback to a specific commit
bash deploy/rollback.sh abc1234
```

---

## Checking Logs

```bash
# Live backend logs
journalctl -u owl-backend -f

# Nginx logs
journalctl -u nginx -f

# Deploy history
ls deploy/logs/
cat deploy/logs/deploy-YYYYMMDD-HHMMSS.log
```

---

## Service Management

```bash
# Check status
sudo systemctl status owl-backend
sudo systemctl status nginx

# Restart backend
sudo systemctl restart owl-backend

# Reload Nginx (after config changes)
sudo systemctl reload nginx
```

Services auto-restart on crash and auto-start on boot.

---

## Files

| File | Purpose |
|------|---------|
| `deploy/deploy.sh` | Main deploy script |
| `deploy/setup-server.sh` | One-time server setup |
| `deploy/rollback.sh` | Manual rollback |
| `deploy/owl-backend.service` | systemd service unit |
| `deploy/owl-nginx.conf` | Nginx site config |
| `deploy/logs/` | Deploy logs (git-ignored) |
