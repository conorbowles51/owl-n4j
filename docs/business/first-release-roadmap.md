# First Release Roadmap

Prepared: 2026-07-10

Work through these stages in order. Tasks inside a stage can happen in parallel. Do not allow external real case data until Stages 1–10 are complete and the release drill passes.

The detailed reasoning is in the [First-Customer Release Readiness Audit](release-readiness-audit-2026-07-10.md).

## Stage 1 — Make The Release Decisions

- [ ] Freeze the product/company name and confirm company ownership of the IP, domain, cloud accounts, provider accounts, and contracts.
- [ ] Confirm the hosting model: one Google Cloud project per customer, plus a separate company operations project.
- [ ] Choose allowed data regions and where evidence, backups, and logs may be stored.
- [ ] Define launch roles and whether company support staff may access customer evidence.
- [ ] Decide whether the Investigation Agent is included, beta-only, admin-enabled, or disabled.
- [ ] Decide which exports and reports are promised in V1.
- [ ] Set limits for files, storage, case size, concurrent jobs, and monthly AI spend.
- [ ] Set backup RPO, restore RTO, support hours, maintenance windows, and incident-notification targets.
- [ ] Name the owner for security, deployments, backups, support, and incidents.

**Exit condition:** Every decision above has a written answer and owner.

## Stage 2 — Lock Down The Application

- [ ] Remove public access to Postgres, Neo4j, Chroma, Redis, and the evidence engine.
- [ ] Put internal services on a private network and add backend-to-engine authentication.
- [ ] Generate unique database, service, JWT, API, and admin secrets for every customer instance.
- [ ] Remove production default passwords and make startup fail when required secrets are missing.
- [ ] Require authentication by default on backend routes.
- [ ] Add case-membership checks to every case-scoped API, including graph, financial, filesystem, evidence, timeline, map, workspace, chat, export, and WebSocket routes.
- [ ] Make maintenance, backfill, logs, model configuration, direct Cypher, and other global actions admin-only.
- [ ] Disable direct Cypher in production or make it admin-only, read-only, and case-scoped.
- [ ] Add permission tests for owner, editor, viewer, guest, non-member, admin, and super-admin.

**Exit condition:** A non-member cannot read a case, a viewer cannot edit it, and no internal service is publicly reachable.

## Stage 3 — Finish Accounts, Sessions, And Audit Logs

- [ ] Move browser authentication from local storage to Secure, HttpOnly, SameSite cookies with CSRF protection.
- [ ] Add shorter sessions, server-side revocation, and forced logout after password, role, or account changes.
- [ ] Add login rate limiting, failed-login auditing, and stronger password rules.
- [ ] Add password reset and administrator account recovery.
- [ ] Add MFA and require it for administrators.
- [ ] Lock or remove the initial-user setup endpoint after provisioning.
- [ ] Audit login, case access, uploads, exports, deletes, permission changes, admin actions, and support access.
- [ ] Send security audit events to a protected destination that ordinary users cannot clear.
- [ ] Set time-based log retention and prevent evidence, prompts, passwords, and API keys from entering logs by default.

**Exit condition:** Accounts can be recovered safely, sessions can be revoked, admins use MFA, and sensitive actions leave a trustworthy record.

## Stage 4 — Build The Customer Hosting Template

- [ ] Buy the final domain in a company-owned registrar account protected by MFA.
- [ ] Create the central Google Cloud operations project and Cloud DNS zone.
- [ ] Build Terraform or equivalent automation that creates an isolated project, network, VM, storage, secrets, backups, monitoring, and budget for each customer.
- [ ] Reserve a static IP and automatically create `customer.ourdomain.com` for each customer.
- [ ] Expose only ports 80 and 443; restrict administration through IAP, OS Login, VPN, or an approved admin network.
- [ ] Build static frontend assets and serve them through a production reverse proxy or managed load balancer.
- [ ] Bind application services privately and enable HTTPS, certificate renewal, HSTS, security headers, and upload limits.
- [ ] Configure operating-system patching and least-privilege service accounts/firewalls.
- [ ] Create an inventory containing each customer's project, region, URL, version, schema, storage, backup state, and health.

**Exit condition:** A repeatable workflow creates a working isolated customer environment with HTTPS and no manual infrastructure setup.

## Stage 5 — Build Safe Updates And Rollbacks

- [ ] Create CI gates for tests, lint, typecheck, builds, dependency scanning, secret scanning, and container scanning.
- [ ] Build versioned immutable application artifacts once in CI and store them in Artifact Registry.
- [ ] Stop running Git pulls, dependency installation, source builds, or the Vite development server on production machines.
- [ ] Add development, staging, internal, canary, and customer release channels.
- [ ] Record the exact application and schema version on every instance.
- [ ] Add pre-deployment checks for disk space, backup freshness, secrets, health, and migration state.
- [ ] Use backward-compatible expand/contract migrations and test them against realistic old-version backups.
- [ ] Define whether each release supports code rollback, requires roll-forward, or requires full restore.
- [ ] Deploy to staging, internal, canary, then the remaining customers, with authenticated smoke tests at each step.
- [ ] Rehearse a failed deployment and rollback before the process reaches a customer.

**Exit condition:** The team can deploy a known version, see where it is running, detect failure, and recover without manual production edits.

## Stage 6 — Implement Backups, Restore, And Deletion

- [ ] Automatically back up Postgres, Neo4j, evidence files, generated files, and Chroma or its complete rebuild inputs.
- [ ] Include application version, schema version, and configuration references in each recovery set.
- [ ] Encrypt backups, retain multiple generations, and store them outside the customer VM's failure boundary.
- [ ] Restrict backup access/deletion and alert on failed, late, or abnormal backups.
- [ ] Add a manual pre-deployment backup action.
- [ ] Write and test the full restore process in a clean customer project.
- [ ] Verify users, permissions, file hashes, product views, citations, chats, and exports after restore.
- [ ] Schedule recurring restore drills.
- [ ] Create customer export, offboarding, backup-expiry, and two-person deletion procedures.

**Exit condition:** A clean environment can be restored within the promised RTO and original evidence hashes match.

## Stage 7 — Add Monitoring And Support

- [ ] Make readiness fail when a required database, service, or worker is unavailable.
- [ ] Monitor HTTPS, certificates, CPU, memory, disk, container restarts, workers, queue depth, job failures, API errors, and latency.
- [ ] Monitor backup freshness, restore-test date, deployed version, AI-provider errors, storage, and AI costs.
- [ ] Add per-customer storage and AI-budget alerts.
- [ ] Route urgent alerts to a named responder rather than only a dashboard.
- [ ] Add structured, privacy-safe error reporting.
- [ ] Write runbooks for outages, stuck jobs, full disk, failed backups, failed deployments, lost admin access, provider outages, cost spikes, and suspected breaches.
- [ ] Define support email, severity levels, response targets, escalation contacts, and maintenance windows.
- [ ] Make support access time-limited, least-privilege, and audited.

**Exit condition:** Important failures alert a responsible person and have a tested response procedure.

## Stage 8 — Finish Product Release Blockers

- [ ] Add an admin-only frontend guard and verify roles throughout every product section.
- [ ] Add file/storage/job/AI quotas, malware and file-signature checks, archive protection, and safe large-file streaming.
- [ ] Make ingestion jobs safe to cancel, restart, and resume after worker or VM failure.
- [ ] Show source provenance for entities, relationships, facts, insights, events, locations, and financial transactions.
- [ ] Distinguish AI extraction, AI inference, investigator assertion, and human-verified fact.
- [ ] Ensure provenance survives edits and entity merges.
- [ ] Finish the timeline work and verify dates, timezones, saved views, filtering, and exports.
- [ ] Verify map precision/corrections and financial currency, totals, stable IDs, sources, and exports.
- [ ] Reproduce and close the note, snapshot, concurrent-upload, and unsaved-work bugs.
- [ ] Ensure workspace objects are case-scoped, permission-checked, auditable, and exportable.
- [ ] Implement the missing reports backend and working exports, or remove Reports from the V1 promise.
- [ ] Sanitize report content and test PDF/DOCX/CSV output, graphs, tables, fonts, and page breaks.
- [ ] Require exact sources for material AI claims and clearly mark unsupported answers.
- [ ] Add permanent AI limitations/human-review language and prompt-injection defences.
- [ ] Add AI budgets and make agent tools bounded, case-authorised, read-only by default, and approval-based for mutations/exports.
- [ ] Restrict Triage to approved roots and authorised import/admin users.
- [ ] Stress test large evidence sets, graphs, timelines, maps, financial cases, and Cellebrite reports.

**Exit condition:** Every feature promised for V1 works end to end with correct permissions, durable data, provenance, and usable exports.

## Stage 9 — Make The Quality Gates Green

- [ ] Fix the failing frontend tests and meaningful lint errors.
- [ ] Resolve high-severity runtime dependency advisories.
- [ ] Keep both Python suites, frontend tests, builds, lint, typecheck, and scans green in CI.
- [ ] Reduce or deliberately split the oversized frontend bundle.
- [ ] Add browser tests for login, permissions, evidence processing, main investigation views, citations, exports, admin boundaries, and logout.
- [ ] Test supported browsers, desktop sizes, keyboard use, high zoom, loading, empty, and error states.
- [ ] Run load tests using large files, many files, 10,000+ entities, large Cellebrite reports, and thousands of events/transactions.
- [ ] Define measured limits and pass/fail thresholds for speed, memory, errors, queue delay, and case size.
- [ ] Block release creation whenever a required check fails.

**Exit condition:** CI is green, core journeys pass in a real browser, and supported limits come from measured tests.

## Stage 10 — Finish Legal, Documentation, And Onboarding

- [ ] Finalise the customer agreement, DPA, privacy notice, acceptable-use policy, confidentiality, and IP terms.
- [ ] Publish the subprocessor list and define data location, transfers, retention, backup, deletion, legal holds, and breach notification.
- [ ] Add AI limitations, prohibited uses, human-review responsibilities, support terms, RPO/RTO, liability, termination, and offboarding.
- [ ] Verify that contractual and marketing security claims match the deployed provider settings and architecture.
- [ ] Create `support@` and `security@` addresses with SPF, DKIM, and DMARC.
- [ ] Write customer documentation for onboarding, roles, cases, uploads, investigation views, AI, citations, exports, support, and known limits.
- [ ] Write internal provisioning, deployment, rollback, restore, secret-rotation, incident, support, and offboarding runbooks.
- [ ] Create a safe demonstration case and first-login checklist.
- [ ] Have a non-developer complete a first investigation using only the documentation.

**Exit condition:** A customer can sign the correct terms, complete onboarding, and use the promised workflows without undocumented founder knowledge.

## Stage 11 — Run The Full Release Drill

- [ ] Provision a fresh customer project using production automation.
- [ ] Verify network exposure, HTTPS, certificates, security headers, and unique secrets.
- [ ] Test every role and a non-member using direct API requests.
- [ ] Upload and process a representative mixed investigation dataset.
- [ ] Exercise every promised V1 section, citation, and export.
- [ ] Run a scheduled backup and restore it into a clean project.
- [ ] Deploy an update through staging and canary.
- [ ] Simulate a failed deployment and complete the rollback or restore.
- [ ] Simulate worker failure, provider failure, low disk, expired sessions, and unauthorised case access.
- [ ] Confirm expected alerts arrive and runbooks are usable.
- [ ] Confirm CI, scans, tests, lint, browser tests, and load tests are green.
- [ ] Record evidence and an owner sign-off for every item.

**Exit condition:** The drill passes without unexplained failures or manual production edits.

## Stage 12 — Onboard The First Pilot

- [ ] Agree the pilot price, duration, users, cases, storage, AI allowance, support, and success measures.
- [ ] Sign the customer agreement and data terms.
- [ ] Provision the customer from the approved template.
- [ ] Create users with MFA and complete onboarding.
- [ ] Import only the agreed initial data.
- [ ] Schedule regular feedback and support calls.
- [ ] Review security, backups, errors, performance, usage, and cost throughout the pilot.
- [ ] Separate pilot bugs from feature requests.
- [ ] Complete a formal pilot review before onboarding another customer.

**Exit condition:** The pilot is reviewed and the team deliberately decides to renew, revise, expand, or stop.

## Later, Not First-Pilot Blockers

- [ ] Fleet-wide version compliance and staged rollout automation.
- [ ] Portable, versioned case export/import.
- [ ] Formal vulnerability management and recurring penetration tests.
- [ ] Stronger SLOs, disaster-recovery exercises, and capacity forecasting.
- [ ] SSO/SAML/SCIM when a customer requires it.
- [ ] SOC 2 or ISO 27001 when sales strategy justifies it.
- [ ] Automated billing when manual invoicing becomes a real bottleneck.
- [ ] Multi-region infrastructure, mobile-first investigation, and in-product support chat when demand justifies them.

