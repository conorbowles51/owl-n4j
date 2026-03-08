# Owl Deployment Guide

## Architecture

```
Browser
    |--- :5173  -->  Vite dev server (frontend)
    |--- :8000  -->  Uvicorn (backend API)
```

Same as the old screen session setup, but managed by systemd (auto-restart, auto-boot, proper logs).

---

## First-Time Server Setup

Run once on the GCP instance as root:

```bash
sudo bash deploy/setup-server.sh
```

This installs systemd services, kills old screen sessions, enables auto-start on boot.

---

## Deploying

After merging changes to `main`:

```bash
ssh your-server
sudo bash deploy/deploy.sh
```

The script will:
1. Check pre-flight conditions (disk space, Docker containers)
2. Stash any local changes on the server
3. Pull latest code from `main`
4. Install Python + frontend dependencies
5. Run database migrations (Alembic)
6. Restart backend + frontend services
7. Run a health check
8. **Auto-rollback** if the health check fails

---

## Rolling Back

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

# Live frontend logs
journalctl -u owl-frontend -f

# Deploy history
ls deploy/logs/
```

---

## Service Management

```bash
# Check status
sudo systemctl status owl-backend
sudo systemctl status owl-frontend

# Restart
sudo systemctl restart owl-backend
sudo systemctl restart owl-frontend
```

Services auto-restart on crash and auto-start on boot.

---

## Files

| File | Purpose |
|------|---------|
| `deploy/deploy.sh` | Main deploy script |
| `deploy/setup-server.sh` | One-time server setup |
| `deploy/rollback.sh` | Manual rollback |
| `deploy/logs/` | Deploy logs (git-ignored) |
