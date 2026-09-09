# Workspace cutover operations

> Applies to the canonical Workspace at migration head `20260902_workspace_ai`. Phase 8 changes the application contract but does not drop legacy tables.

## Release gate

Before deploying the cutover build:

1. Back up the target PostgreSQL database using the organisation's normal encrypted, retained backup process. Record the backup identifier and restore-test result in the release ticket.
2. Upgrade to the single Alembic head and run the final idempotent backfill twice:

   ```powershell
   python backend/scripts/workspace_phase8_backfill.py --output output/workspace-redesign/phase8-backfill-idempotence.json
   ```

3. Generate the review template and final reconciliation:

   ```powershell
   python backend/scripts/workspace_phase8_reconciliation.py --write-review-template output/workspace-redesign/phase8-review-acceptance-template.json --output output/workspace-redesign/phase8-reconciliation.json
   ```

4. If review items exist, investigate each source record. An acceptance file may name a review key only with a non-empty reason. Rerun reconciliation with `--acceptance-file`; unknown keys or unaccepted items fail the gate.
5. Require `passed: true`, one migration head, zero unexpected differences, and no unexplained review item.
6. Run the backend, frontend, browser, and migration checks listed in `docs/workspace-redesign.md`.

## Deployment order

1. Take and identify the environment backup.
2. Deploy database expansions and run backfills/reconciliation.
3. Deploy the backend containing canonical Context, Entry, Dossier, Work, Overview, and AI routes.
4. Deploy the frontend cutover build. There is no Workspace feature flag or case allow-list after Phase 8.
5. Smoke-test owner, editor, and viewer access before widening traffic.
6. Retain generated JSON reports with the release evidence.

## Application rollback

Rollback is application-only and non-destructive:

- Deploy the last canonical-compatible Phase 7 frontend and backend together.
- Keep the database at the current expanded head. Do not downgrade or restore an older database over live canonical writes.
- Keep the redesign path enabled in the prior frontend so users continue writing canonical stores.
- Rerun reconciliation after rollback and after the forward fix.
- Never copy canonical rows back into independent legacy stores or resume legacy writes.

The isolated rehearsal is implemented by `backend/scripts/workspace_phase8_backup_restore.py`. It creates synthetic empty, small, and scale databases, upgrades and seeds the source, creates a custom backup, restores it, compares counts and reconciliation, boots the API, and drops both isolated databases. Its dump is fixture evidence only; it is not a production backup.

## Contract migration gate

Dropping legacy tables is deliberately outside this cutover. A future contract migration requires all of the following:

- the agreed retention period has elapsed;
- a current environment backup has been restored and verified;
- the final reconciliation passes against that environment;
- support confirms no historical link depends on an unmapped identifier;
- product and engineering sign off in the release record;
- the contract migration preserves mapping tables needed for historical support.

If any gate is absent, retain the tables. Retained legacy rows are inert migration sources and do not prevent the canonical application from operating.

## Health and incident checks

- Confirm `/api/workspace/{case_id}/overview`, `/entries`, `/work`, `/context`, `/ai-outputs`, `/api/dossiers`, and Dossier evidence-link routes respond for an authorised user.
- Confirm viewers receive read-only controls and mutation routes reject them.
- Check that a new or edited Entry creates an immutable revision and event.
- Check AI output citations resolve before acceptance and that rejection does not change casework.
- Rerun case-scoped reconciliation with `--case-id` when an incident concerns one case.
- Treat missing mappings, cross-case targets, absent Entry history, or unknown acceptance keys as release-blocking data-integrity failures.
