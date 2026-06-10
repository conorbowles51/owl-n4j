# Deploying the Testing Hub

Short answer: **you don't need a new deploy script.** The existing
`deploy/deploy.sh` handles everything. This note just explains what (if
anything) the server Claude needs to know.

## What the hub is
A login-gated QA page served by the **backend** that lists everything shipped
in the Cellebrite work; testers (neil / alex / conor / arturo, password `testing`)
record Pass/Fail/Blocked + notes per item. Feedback is saved to a JSON file on
disk and attributed per tester.

## Does it need anything special at deploy time?
No new moving parts:

| Concern | Status |
|---|---|
| New Python deps | **None** — uses `bcrypt`, `python-jose`, `fastapi` (all already in `requirements.txt`). |
| DB migration | **None** — feedback is a JSON file (`data/testing-feedback.json`), not Postgres/Neo4j. |
| Frontend build | **None** — the page is a static file served by the backend (`backend/static/testing-hub.html`). |
| New env vars | **None** — reuses the app's existing `AUTH_SECRET_KEY` to sign hub tokens. |
| File permissions | `deploy.sh` already `chown`s `data/` to the app user, so the feedback file is writable. |

So a normal deploy is all that's required:

```bash
ssh your-server
sudo bash deploy/deploy.sh
```

The script pulls `main`, installs deps, runs migrations (a no-op for this
feature), restarts `owl-backend` + `owl-frontend`, health-checks, and
auto-rolls-back on failure.

## How testers reach it
The page is a **backend route**. Two ways to open it:

1. **Through the app origin (recommended, no infra change):**
   `https://<your-app-domain>/api/testing/hub`
   The frontend already proxies `/api/*` to the backend in every environment
   (Vite dev proxy and the nginx `location /api/` rule), so this URL works with
   no new reverse-proxy config, and the page's `/api/testing/*` calls are
   same-origin.

2. **Directly off the backend:** `http://<server>:8000/testing`
   Only if port 8000 is reachable from the tester's network.

> If you'd rather expose a clean `/testing` path on the main domain, add one
> nginx rule (optional):
> ```nginx
> location /testing { proxy_pass http://127.0.0.1:8000/testing; }
> ```
> It's not required — option 1 already works everywhere.

## Logins
- `neil` / `alex` / `conor` / `arturo`, all with password `testing`.
- These are **hub-only** accounts (a separate, self-contained login). Signing in
  grants **no** access to the rest of the app — the token carries a
  `hub: "testing"` claim that the app's own auth rejects.
- To change them later: edit `_TESTERS` / `_PASSWORD` in
  `backend/services/testing_auth.py` (passwords are bcrypt-hashed at import).

## Where feedback lands
- `data/testing-feedback.json` (gitignored, persists across deploys).
- Devs can read everyone's input via `GET /api/testing/feedback` (with a hub
  token) or just open the file on the server.

## Smoke check after deploy
```bash
# page serves
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/testing/hub   # 200
# unauthenticated data is blocked
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/testing/checklist  # 401
# login works
curl -s -X POST http://127.0.0.1:8000/api/testing/login \
  -H 'Content-Type: application/json' -d '{"username":"neil","password":"testing"}'
```
