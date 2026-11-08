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

1. Copy `.env.example` to `.env` and fill in the real values. With `LOUPE_ENV=production` the backend refuses to start
   on a missing or shipped secret, naming it. `bash deploy/rotate-secrets.sh --check`, then `--apply`, generates them
   and moves the stored AI credentials to the new key. `LOUPE_HTTPS=true` only once the site is served over HTTPS.
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

An already-deferred release also samples PostgreSQL lock waits in the current
database. It shows at most 10 waiting backend PIDs, their state, wait event/type
and transaction age in seconds, with at most 10 blocking PIDs per waiter and
10 distinct blocker activity summaries. Omitted blocker references are counted;
reaching the waiter limit means the sample may be incomplete. A blocker whose
activity is unavailable remains identified only by PID and `activity_visible:
false`; PID 0 can refer to a prepared transaction. This is a transient sample,
not proof of why an ingestion stopped or permission to terminate a backend.
It never reads or logs SQL text, database usernames, client addresses, connection
strings or evidence. Local two-second statement and half-second lock timeouts
apply only to the diagnostic connection. SQLite skips this PostgreSQL-only
sample. Permission, timeout or diagnostic errors retain the original blocking
counts and exit code 75; they print only the exception type. The sample does not
alter the release predicates, pause work, cancel statements or release locks.

Docker images are built before a fresh idle check permits container replacement.
Another check runs before the backend restarts. The check is retained in memory
across checkout changes, including automatic and standalone rollback. Rollback
uses the same deployment lock as deployment.

These checks are snapshots, not an intake lock: new work can arrive after the
last check. Engine workers finish their current jobs during graceful shutdown
(14,430-second worker wait and 14,500-second Docker grace). The backend stop is
bounded instead: Uvicorn cancels request tasks still running 20 seconds after
SIGTERM, the lifespan abandons background financial units 10 seconds later,
and the application's watchdog ends the process 45 seconds after the first
stop signal. Abandoned units are durable (leased import batches, pending
recovery items, revisioned identity-graph sweeps): their open transactions roll
back and the next start resumes them. The service drop-in sets
`TimeoutStopSec=90` and `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20`; systemd's
SIGKILL at 90 seconds is the backstop. The installer reloads this service
configuration without restarting a running job.

Deploy and rollback never block on `systemctl restart`. The backend is stopped
without blocking; if it is still running after 60 seconds the deploy records
the last 80 lines of its journal (which name the requests and tasks still
pending), sends SIGINT to every process in the unit (Uvicorn's force-quit),
then SIGKILL after 20 more seconds. The deploy then always reaches its health
check, writes the last-good marker when healthy, and ends its log with a
summary block (outcome, commit, how the backend stop went, last-good) on every
exit, including an interrupted one. `bash deploy/tests/test-backend-stop.sh`
exercises the escalation with a simulated unit.

The shutdown drop-in is installed from a regular temporary file and atomically
renamed before `daemon-reload`. It does not depend on `/dev/stdin`, which may be
absent in a service runner. A failed installation stops the release before the
backend restart; it never downgrades the ingestion gates or continues without
the configured grace. `bash deploy/tests/test-ingestion-shutdown.sh` exercises
real `install`/`mv` commands in a temporary directory with closed stdin,
permissions, repeated installation and destination failure. The same test was
validated on Linux with GNU coreutils and no `/dev/stdin` symlink.

The backend's memory allocator is a host switch, off by default. Writing
`mimalloc` to `/etc/default/owl-backend-allocator` makes the next release or
rollback install the `backend-allocator.conf` drop-in
(`Environment=PYTHONMALLOC=mimalloc`); removing the file, or any other content,
removes the drop-in, and the backend runs Python's default allocator again from
its next restart. The switch is outside the checkout, so no release or rollback
changes it. Measured in a fresh process on one large account history: the
default allocator keeps 1.6 GB resident afterwards, mimalloc 0.5 GB, at about
30% more CPU. `bash deploy/tests/test-backend-allocator.sh` exercises off,
on, repeat, switching off and an unavailable unit directory.

If a release fails after building the frontend, its recovery trap restarts the
frontend using the bundle currently on disk. That bundle may already be new;
the restart does not prove that the backend or the whole release was updated.

## Promoting a release to a customer instance

One path, development box first, customer instances after, each step a script that
exists in this repo:

1. **Validate on the development box.** A commit reaches customers only after it has
   been live on the development box (`deploy-now.sh` there), its head suite has a
   green verdict (`suite-slot.sh heads <sha>` on the box), and the per-head scans
   (`deploy/ci/scan-head.sh`, automatic per live head) show no new high findings.
2. **Provision once per customer:** `deploy/provision` (Terraform; see its README),
   then on the new VM `sudo bash deploy/setup-server.sh`, fill `.env` from
   `.env.example` and run `sudo bash deploy/rotate-secrets.sh --check` then
   `--apply` so no shipped secret survives.
3. **Promote the validated commit:** on the customer VM,
   `sudo DEPLOY_TARGET_SHA=<sha> bash deploy/deploy.sh` — the same release path as
   the development box, pinned to exactly the validated commit (never whatever was
   pushed after it), with its health check and automatic rollback
   (`deploy/rollback.sh` by hand if needed).
4. **Verify:** `/health` reports the promoted commit; `deploy/backup-check.sh`
   stays green; the instance's entry in the inventory
   (`deploy/ci/inventory-update.sh` on the box, `deploy/provision/inventory/` for
   terraformed customers) shows the new version. `deploy/ci/inventory-check.sh`
   fails on a missing or stale entry.

No customer instance exists yet (8 Nov 2026); steps 2-4 are written against the
scripts above and first run for real when one does.

## Choosing the correct server checkout

Before running a deployment, identify the checkout used by the live services:

```bash
systemctl show owl-backend-v2 owl-frontend-v2 -p Id -p WorkingDirectory
```

On the current investigation-platform host, both services use the repository at
`/home/conorbowles51/app-v3/owl-n4j`, on `integration/evidence-main-reunion`.
The older `/home/conorbowles51/app_v2` checkout uses `main` and is not the current
Loupe deployment. Do not reset or merge that older checkout to deploy this release.

From the confirmed live repository root, run `bash deploy/deploy.sh`. Preserve
the ingestion checks. A reported ingestion deferral is different from a Git
conflict; inspect that checkout's `deploy/logs` for the actual release result.

The Git update fetches one explicit branch without writing shared `FETCH_HEAD`,
then fast-forwards to its resolved commit. This avoids ambiguous multi-head
`git pull` results and ignores extra pull merge targets in branch configuration.
It rejects a mismatched checked-out branch and preserves server-only commits
when the history is ahead or divergent. It never resets the checkout to make a
deployment pass. Run `bash deploy/tests/test-git-update.sh` for the isolated Git
regression checks, including ambiguous fetch metadata and divergent history.

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

## When a release pauses running work

Work is paused only for the part of a release that replaces services. Everything else happens beside them: staging the tree,
packages, the prepare, the frontend build, the image build.

- `deploy.sh` reads a host script's path from `deploy/logs/.release-work-hook` (outside the repository). `<hook> pause-imports`
  runs after the last build. `<hook> pause-uploads` runs before the gate that needs uploads stopped, after any additive migrations
  and their prepare (`deploy/migration_safety.py`: old code keeps working beside them); any other migration waits for uploads to
  stop. `<hook> resume` runs as soon as the release is healthy, before anything is tidied, and on every exit. Without that file
  every gate applies from the start of `deploy.sh`, and whoever runs it must pause first.
- On this host the hook lets the work in hand finish (20-minute cap each) with uploads still running. It resumes uploads first. A
  hold keeps pausing work that starts during the swap.
- With the hook, gates before the pause pass without looking; after it each gate tries 3 times, 5 s apart.
- A release takes a systemd scope of its own, so a release started by a job is not held by the jobs' memory limit.
- Every step in a deploy log carries its UTC time.

## Where the backend runs from

The backend does not run from the live checkout. A release moves that checkout first, because the gates, the migrations
and the image builds need the new commit, and it takes 12 to 20 minutes before the backend is replaced. Lazy imports, data
files and child processes of a backend running there would read the new commit in that time.

- `deploy/backend-tree.sh` keeps two git worktrees, `blue` and `green`, in `../loupe-backend`. `current` links to the one
  the unit starts from, through the drop-in `70-lx-releaseprep-tree.conf` (`WorkingDirectory=`).
- A release stages its commit in the tree no process of the unit has as its working directory, compiles it, and runs the
  prepare unit there. `current` switches right before the backend is replaced. A running backend keeps the tree it started
  in, so it reads one commit from its start to its end, and so do its children.
- The trees hold code only: `.env`, `data`, `evidence-data`, `backend/logs` and `deploy/logs` are links to the live checkout.
  A new folder of runtime data under the checkout goes in `BACKEND_TREE_SHARED`.
- Packages follow the tree. `<tree>/.venv` links to `venvs/<hash of backend/requirements.txt>`, built beside by a hard-link copy
  of the venv in use plus `pip install -r`: `pip` replaces files and never writes one in place, so the copies share only files
  that did not change. The unit starts `current/.venv/bin/uvicorn`; that script's first line names the venv's real folder, so a
  running backend never reads a package newer than its tree, whichever way the link moves. A process started as
  `current/.venv/bin/python` would follow the link: start scripts, not the bare interpreter. Rollback needs no pip. The
  checkout's `.venv` is the release tooling's and is brought up to date after a healthy release.
- A gate or build that stops a release changes nothing the backend reads. A failed health check points `current` back at the
  tree that ran, at the rollback commit. Commits from before the trees run from the checkout (`deploy/rollback.sh`).
- The evidence engine has no such window: its containers run images and mount data folders only.
- The virtual environment is shared. A release that changes `requirements.txt` installs into it while the old backend runs.
- Way back: set `deploy/backend-tree.conf` to `checkout`; the next restart removes the drop-in and runs from the checkout.
- `systemctl restart owl-backend-v2` starts what `current` names, which is what is live.
- `bash deploy/tests/test-backend-tree.sh`; a whole release: `test_the_old_backend_keeps_its_own_code_while_a_release_prepares`
  in `backend/tests/test_deployment_script_safety.py`.

## Replacing the backend without a wait

A release that changes the backend restarts it, and requests wait in the held API port's queue while the new workers
start. With `deploy/backend-restart.conf` (or `/etc/default/owl-backend-restart`, which overrides it on the host) set
to `handover`, the unit's main process is `deploy/backend_supervisor.py`, installed to `/usr/local/lib/loupe`. A release
then starts the new backend beside the old one on the same socket, from the other backend tree, so nginx and every client
keep the same address;
the old backend stops only after each new worker has answered `/health` as healthy and the ingestion gate has passed
again, and it finishes its requests within the usual stop bounds.

- A new backend that does not come up is stopped. The old one keeps serving, the checkout goes back and the release
  reports NOT RELEASED. `deploy/logs/.backend-handover-failed` says why; the next release uses a restart and clears it.
- Rule for migrations: a release hands over only when every pending migration is additive
  (`deploy/migration_safety.py`). Any other migration uses a restart.
- A changed `.env`, unit file or supervisor also uses a restart: the environment is read once, when the unit starts.
- Every background loop states its owner in `backend/services/backend_handover.py` (`BACKGROUND_LOOPS`).
- Way back: set the switch to `restart`; the next restart puts the plain unit back. A rollback always restarts into the plain unit.
- Rehearsal on a throwaway port under real systemd: `deploy/tests/rehearse-handover.sh <python with uvicorn>`.

## Signing in: two-step, and getting an account back

Two-step sign-in needs `MFA_ENCRYPTION_KEY` in the server's `.env` (`openssl rand -hex 32`). It has no default. While it
is unset nobody can enrol and the Security page says why. It is backed up with `.env` by the keys bundle: losing it means
authenticator codes stop working, and each enrolled person signs in with a recovery code and enrols again.

A person enrols in Settings, Security. An administrator sees who has enrolled in User Management.

There is no email in this app, so nothing is sent to anyone. Reset by email waits for a mail sender.

| Lost | What to do |
|---|---|
| Password | An administrator opens User Management and issues a reset code, then gives it to the person. It works once, for one hour. The person chooses "I have a reset code" on the sign-in page. Every sign-in of theirs ends |
| Authenticator, with recovery codes kept | The person signs in with a recovery code. In Settings, Security, their password and another recovery code turn two-step off, so they can enrol the new device |
| Authenticator and recovery codes | An administrator chooses Remove two-step. The person signs in with their password and enrols again |
| An administrator's account | A super admin does the same for them. Only a super admin can recover an administrator, and nobody can recover themselves in the app |
| The last administrator's account | On the box: `sudo bash deploy/account-recovery.sh reset <email>`, with `--remove-two-step` if the authenticator is lost too. The code prints once, to that terminal |

Every issue, use and removal is in the activity trail. A code or secret is never logged.

**Requiring two-step for administrators** is off until someone turns it on:

```bash
sudo bash deploy/account-recovery.sh require --check   # who is ready; nothing is written
sudo bash deploy/account-recovery.sh require --on      # refused until the check is clean
sudo bash deploy/account-recovery.sh require --off
```

`--on` is refused while the signing key is the shipped one (a forged sign-in would walk past any second step), while the
encryption key is unset, and until every active administrator is enrolled and holds at least one recovery code. Once on,
an administrator who has not enrolled is refused on the administrator screens, and on every other route that reads their
account, until they do; Settings, Security stays open. An enrolled administrator cannot turn two-step off: one with a new
device gets it removed by a super admin, or by the box command.
Accounts that are not administrators are untouched, and scripts that sign in with a password keep working unless the
account they use has enrolled; `--check` lists administrators' sign-ins from scripts in the last 30 days.

To change the key: set the old value as `MFA_ENCRYPTION_KEY_PREVIOUS` and the new one as `MFA_ENCRYPTION_KEY`, restart,
run `sudo bash deploy/account-recovery.sh rekey`, then remove the old value.

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

## Backups

`docs/backup-inventory.md` lists every store and its protection; `docs/backup-restore.md` holds the restore steps.
`docs/customer-data-procedures.md` holds customer export, offboarding, backup expiry and two-person deletion.
`bash deploy/tests/test-<name>.sh` exercises `db-backup`, `neo4j-backup`, `chroma-backup`, `keys-bundle`,
`evidence-copy`, `backup-check`, `backup-crypt`, `backup-now`, `backup-procedures` and `restore-drill`.
`deploy/restore-drill.sh run` restores the newest backups into scratch containers.

Before a release, `bash deploy/backup-now.sh` takes a full recovery set (keys, Postgres, Neo4j, Chroma), and refuses when the box
has too little memory or disk; `--check` says whether it would run. `bash deploy/backup-crypt.sh new-key` switches on encryption at rest.
