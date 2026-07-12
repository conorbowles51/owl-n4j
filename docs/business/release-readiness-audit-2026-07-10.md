# First-Customer Release Readiness Audit

Prepared: 2026-07-10

## Reader And Decision

This audit is for the founders and engineers deciding whether the investigation platform can accept real customer data. After reading it, the team should be able to create a release backlog, decide what blocks the first supervised customer, and run an evidence-based go/no-go review.

The standard is deliberately practical: the first release does not need every enterprise feature, but a customer must be able to trust that only authorised people can reach a case, evidence will not be lost, an update will not corrupt it, a failure will be noticed, and AI output can be traced back to source material.

## Scope And Method

This is a static review of the current checkout plus the existing automated checks. It covered the deployment/Compose definitions, service entry points and configuration, authentication and permission helpers, API route families, data stores, migrations, frontend routes/features, tests, business documentation, and the outstanding backlog. The old checklist and attached notes were treated as hypotheses and checked against the current repository.

It did not include a penetration test, a running Google Cloud instance, a full browser walkthrough with production-sized customer data, provider-account settings, or legal review. The working tree also contains active timeline and ingestion changes; those were inspected but not altered, and the release candidate must be re-audited after they are final. Product items taken only from the backlog are described as unresolved until reproduced or formally closed.

## Executive Verdict

**Current decision: NO-GO for real external customer data.**

The application has substantial product depth and a meaningful automated-test base, but the current deployment and API boundaries contain release-blocking security and recoverability gaps. The most urgent are:

1. The production Compose definition publishes databases and internal services on host ports while using shared default credentials.
2. The evidence-engine API has no authentication layer and is published on a host port. Its API can upload, list, inspect, and delete case jobs/files.
3. Authentication and case authorisation are inconsistent in the main backend. Confirmed examples include public user-list/detail endpoints, graph and financial endpoints without authentication or membership checks, and case file browsing that authenticates a user but does not authorise the requested case.
4. There is no implemented backup system or tested whole-instance restore procedure.
5. Rollback is not migration-safe, and the standalone rollback script does not actually move Git `HEAD` to the requested release.
6. The server setup runs the Vite development server as the production frontend and exposes the backend on all interfaces without a TLS/reverse-proxy configuration.
7. The main frontend test and lint gates currently fail, high-severity runtime dependency advisories are present, and there is no CI workflow.
8. Monitoring is limited to health endpoints and local/database logs; there is no alert delivery, fleet inventory, or reliable degraded-state deployment gate.

This is not a recommendation to delay until the platform is perfect. It is a recommendation to complete the Phase 0 release gate below, then onboard one tightly supervised pilot and learn from it.

## What Is Already Strong

The audit found important foundations worth keeping:

- Separate Postgres, Neo4j, Chroma, Redis, backend, ingestion API, and worker services already exist.
- Uploaded evidence is hashed with SHA-256, and evidence records include original filename, size, creator, and hash metadata.
- Case membership models and owner/editor/viewer concepts exist, and several newer routers correctly call a central case-access service.
- User passwords are bcrypt-hashed; admin and super-admin roles exist.
- The product covers case management, evidence ingestion, graph, table, timeline, map, financial analysis, Cellebrite data, workspace/notebook, chat, and agent workflows.
- AI-cost records and an admin cost dashboard exist.
- Admin-triggered update status and a constrained systemd launcher exist.
- Backend tests pass (119 tests), ingestion tests pass (34 tests), and both web applications produce production builds.
- Health checks exist for the backend and ingestion service, providing a base for proper readiness and alerting.
- Manual graph edits, merge jobs, recycle-bin behaviour, timelines, notebooks, and exports have targeted tests.

## Priority Definitions

- **P0 — release blocker:** required before any external user is allowed to upload real case data.
- **P1 — supervised-pilot blocker:** may be completed during internal rehearsal, but must exist before the first customer is expected to operate without a founder beside them.
- **P2 — scale hardening:** complete before expanding beyond the first few closely managed customers.
- **Deferred:** valuable later; not a reason to hold the first supervised pilot.

## Confirmed Security Findings

These findings come from the current code, not from a generic checklist.

### CRITICAL-1: Internal data services are exposed with shared default credentials

**Location:** `docker-compose.yml:4-70`, `docker-compose.yml:100-114`

**Category:** Spoofing, information disclosure, tampering, denial of service, elevation of privilege.

**Exploit:** The Compose stack publishes Neo4j HTTP/Bolt, Postgres, Chroma, Redis, and the ingestion API on host ports. Neo4j and Postgres use credentials embedded in the Compose file, Redis has no password, and Chroma has no application authentication here. If the VM firewall permits those ports, a remote caller can bypass the application and read, alter, or delete customer data. Reusing this file across customers also reuses credentials.

**Reachability:** Remote unauthenticated when the host firewall exposes the mapped ports; otherwise adjacent/local network or compromised host process.

**Business impact:** Full case-data breach, tampering, or loss.

**P0 remediation:** Remove host port mappings for all internal services, use a private Compose network, bind any diagnostic port to loopback only, generate unique per-instance credentials from Secret Manager, rotate existing shared values, and make production configuration fail closed when a required secret is absent.

### CRITICAL-2: The evidence-engine API has no authentication or case authorisation

**Location:** `evidence-engine/app/main.py:35-41`, `evidence-engine/app/api/routes/upload.py:18-99`, `evidence-engine/app/api/routes/files.py:23-86`, `docker-compose.yml:55-63`

**Category:** Spoofing, tampering, information disclosure, denial of service, elevation of privilege.

**Exploit:** The ingestion service registers upload, file, job, merge, Cellebrite, and WebSocket routers without an authentication dependency. Compose publishes the service on host port 8003. A caller who can reach the port can submit files under an arbitrary `case_id`, enumerate or delete jobs/files, trigger expensive processing, and observe progress.

**Reachability:** Remote unauthenticated if port 8003 is reachable.

**Business impact:** Data breach, evidence destruction, cross-case contamination, and uncontrolled AI/cloud spend.

**P0 remediation:** Do not expose the service publicly. Place it on an internal network and require backend-to-engine authentication with a per-instance service identity or signed token. Enforce case ownership in the main backend before forwarding every request. Add request-size, file-count, job-concurrency, and cost limits.

### HIGH-1: Main API authentication and object-level authorisation are inconsistent

**Location:** `backend/routers/users.py:156-185`, `backend/routers/graph.py:248-288`, `backend/routers/graph.py:518-685`, `backend/routers/graph.py:2000-2102`, `backend/routers/financial.py:200-423`, `backend/routers/filesystem.py:39-74`, `backend/routers/filesystem.py:153-184`

**Category:** Broken access control / IDOR, information disclosure, tampering.

**Exploit:** User listing and detail endpoints have no authentication dependency. Multiple graph read/analysis endpoints and financial read/write endpoints accept a caller-provided `case_id` but do not call the case-access service. The filesystem router authenticates the caller and blocks path traversal, but never confirms that the caller belongs to the requested case. A user who knows or obtains another case UUID can read its evidence paths/contents or graph/financial data; unauthenticated callers can hit some surfaces directly.

**Reachability:** Remote unauthenticated for public endpoints; authenticated low-privilege user for other object-level access paths.

**Business impact:** Cross-case disclosure or alteration inside a customer instance and exposure of the user directory.

**P0 remediation:** Make authentication a default router/application dependency, explicitly opt out only for `/health`, login, and a locked-down bootstrap flow, and require central `check_case_access` calls for every case-scoped read or write. Add negative tests proving a viewer cannot edit and a non-member cannot read each route family.

### HIGH-2: Destructive and global administration operations are available to ordinary users

**Location:** `backend/routers/system_logs.py:46-153`, `backend/routers/maintenance.py:29-161`, `backend/routers/backfill.py:490-942`, `backend/routers/llm_config.py:92-207`, `backend/routers/query.py:32-117`

**Category:** Tampering, repudiation, information disclosure, denial of service, elevation of privilege.

**Exploit:** Any authenticated user can clear all system logs, run vector repair/purge operations, launch expensive backfills, change the global LLM model/confidence threshold, and issue arbitrary read Cypher across the graph. The Cypher blocklist is string-based and is not a case boundary.

**Reachability:** Any authenticated user, including a guest/viewer.

**Business impact:** Audit destruction, cross-case disclosure, data mutation, outages, and unexpected AI spend.

**P0 remediation:** Require admin/super-admin for instance-wide operations, remove direct Cypher from normal production builds or enforce a parser-backed read-only/case-scoped query layer, require confirmation and audit records for destructive actions, and make security audit records append-only to application users.

### HIGH-3: Authentication can fall back to a known signing secret and sessions are not production-hardened

**Location:** `backend/config.py:121-125`, `backend/routers/auth.py:23-30`, `backend/routers/auth.py:82-102`, `backend/routers/auth.py:133-155`, `frontend_v2/src/features/auth/hooks/use-auth.ts:12-23`

**Category:** Spoofing, session theft, elevation of privilege.

**Exploit:** If deployment omits `AUTH_SECRET_KEY`, the application uses a source-known default. An attacker can mint a JWT for an existing email. Tokens last 24 hours by default, have no revocation identifier, are returned to JavaScript and stored in `localStorage`, and the cookie lacks the `Secure` flag. Login has no rate limit or lockout, and changed/deactivated accounts can retain usable bearer tokens on routes that only decode the JWT rather than loading the database user.

**Reachability:** Remote unauthenticated for token forging when the default is active; XSS/browser compromise for token theft.

**Business impact:** Account takeover and persistent unauthorised access.

**P0 remediation:** Require a high-entropy instance-unique signing key at startup, use Secure/HttpOnly/SameSite cookies as the only browser token store, add CSRF protection for cookie-authenticated state changes, shorten sessions, add server-side session/revocation state, and rate-limit login. Verify active-user state on every protected request.

### HIGH-4: Rollback can leave code and schema in an incompatible state

**Location:** `deploy/deploy.sh:118-164`, `deploy/deploy.sh:190-207`, `deploy/rollback.sh:54-115`

**Category:** Tampering, availability, data integrity.

**Exploit:** Deploy runs forward Alembic migrations before health verification. Automatic rollback resets application files but does not reverse or restore the database migration. The standalone rollback uses `git checkout <commit> -- .`, which replaces tracked files while leaving `HEAD` and release identity unchanged, and it also does not address schema compatibility. A failed release can therefore report an old code tree against a new schema and cannot reliably identify what is running.

**Reachability:** Operational failure during a normal update.

**Business impact:** Outage, silent data corruption, and an unrecoverable customer instance without manual intervention.

**P0 remediation:** Deploy immutable versioned artifacts, use expand/contract backward-compatible migrations, take a verified pre-migration backup, record schema and application versions, test rollback for every release, and restore the database when rollback crosses an incompatible migration. Never use an untested downgrade in production as the only recovery plan.

### HIGH-5: Production traffic is served by development processes without a TLS boundary

**Location:** `deploy/setup-server.sh:60-103`, `deploy/setup-server.sh:169-175`

**Category:** Information disclosure, tampering, denial of service.

**Exploit:** The setup script starts Uvicorn directly on `0.0.0.0` and runs `npm run dev` (Vite's development server) on `0.0.0.0`. It documents plain HTTP URLs and does not install a reverse proxy, TLS certificate, security headers, request-size limits, or trusted-proxy configuration.

**Reachability:** Remote network clients when ports are open.

**Business impact:** Credential/evidence interception, unsupported production serving, and avoidable exposure of development behaviour.

**P0 remediation:** Build static frontend assets in CI, serve them through Caddy/Nginx or a managed load balancer, proxy only `/api` to a loopback-bound backend, enforce HTTPS/HSTS and security headers, and allow only ports 80/443 from the internet. Restrict SSH with IAP or a tightly controlled admin network.

### HIGH-6: There is no complete backup and restore implementation

**Location:** repository-wide search of `deploy/`, backend, evidence engine, and scripts; only entity/snapshot restore helpers and scripts that instruct an operator to take a backup were found.

**Category:** Availability and integrity.

**Failure scenario:** Disk corruption, accidental deletion, a bad migration, a compromised host, or a customer-requested recovery loses Postgres records, graph data, evidence files, Chroma data, and deployment state with no coordinated restore point.

**Business impact:** Permanent loss of investigation data and breach of contractual commitments.

**P0 remediation:** Implement scheduled, encrypted, off-instance backups covering Postgres, Neo4j, original evidence, Chroma or its deterministic rebuild inputs, secrets/config metadata, and release/schema versions. Define RPO/RTO and prove a clean-environment restore before onboarding.

### MEDIUM-1: The health gate can report success while dependencies are degraded

**Location:** `backend/main.py:175-205`, `evidence-engine/app/api/routes/health.py:10-26`, `deploy/deploy.sh:156-164`

**Failure scenario:** The backend always returns top-level `"status": "ok"`. The ingestion service correctly reports `degraded` when Postgres, Neo4j, Chroma, or Redis fails, but the deploy script only rejects evidence-engine values beginning with `error:` or `unavailable`. A deployment can be marked healthy while ingestion is unusable.

**Remediation:** Separate liveness and readiness endpoints, return a non-2xx readiness response for required dependency failure, check Postgres directly from the backend, and make deployment health require every critical dependency plus a real authenticated smoke test.

### MEDIUM-2: Stored report HTML is rendered without sanitisation

**Location:** `frontend_v2/src/features/reports/components/ReportViewer.tsx:40-44`

**Exploit:** Report content is inserted with `dangerouslySetInnerHTML`. If report HTML contains attacker-controlled or unsafe AI-generated markup, it can execute in the application origin and steal the JavaScript-readable bearer token. The reports backend is currently absent, so this is a dormant but serious hazard when that feature is completed.

**Remediation:** Store structured/Markdown content, render with an allowlisted renderer, sanitise HTML, deploy a strict Content Security Policy, and stop storing auth tokens in `localStorage`.

### MEDIUM-3: Upload and processing limits are incomplete

**Location:** `evidence-engine/app/api/routes/upload.py:18-62`

**Exploit:** The ingestion API reads each uploaded file fully into memory before writing it and has no visible maximum body/file size, per-case quota, job concurrency limit, or request rate limit. A reachable caller can exhaust memory, disk, worker capacity, or AI budget.

**Remediation:** Stream uploads, enforce limits at the reverse proxy and application, validate archives against decompression bombs, cap concurrent jobs per instance/case, add storage thresholds and cost budgets, and surface quota errors clearly.

### MEDIUM-4: Audit logs are mutable, incomplete, and capped by count

**Location:** `backend/services/system_log_service.py:68-116`, `backend/services/system_log_service.py:266-274`, `backend/routers/auth.py`, `backend/routers/users.py`

**Failure scenario:** Logs are trimmed after 10,000 records, can be deleted through the API, and login/user-management routes do not consistently record security events. An incident may have no trustworthy history of access, exports, deletes, permission changes, or administrator support access.

**Remediation:** Define event coverage and retention by time/contract, export security audit events to an access-controlled sink, prohibit deletion by ordinary application admins, and record actor, case, object, action, result, source IP, and correlation ID without recording evidence content or secrets.

## Product Review By Section

### Authentication, Users, And Administration — Partial; P0 work required

Present:

- bcrypt password hashing;
- JWT login and logout;
- user activation and global roles;
- admin/super-admin creation and update rules;
- initial-admin setup flow.

Required before release:

- close the public user endpoints and make server-side authorisation consistent;
- MFA for admins and preferably all users;
- password reset/account recovery without database editing;
- stronger password policy, login throttling, failed-login audit, session expiry/revocation, and forced logout after password/role changes;
- lock down the bootstrap endpoint to provisioning time and remove the concurrent-first-user race;
- add an admin-only frontend route guard (the current `AdminLayout` itself performs no role check);
- support recovery codes and a documented lost-admin procedure.

### Case Management And Collaboration — Strong foundation; authorisation gate is P0

Present:

- create/list/open/update/archive/delete cases;
- owner/editor/viewer membership concepts and custom permissions;
- case profiles and deadlines;
- active-user checks in newer case services.

Required:

- prove every downstream graph, evidence, financial, timeline, map, workspace, chat, export, and WebSocket route enforces the same case membership;
- add a route-by-route permission matrix and integration tests for owner, editor, viewer, guest, non-member, admin, and super-admin;
- define whether super-admin may see every case and make support access visible to the customer;
- log case access, membership changes, archive/delete/export, and support impersonation;
- prevent removal/deactivation of the last viable case owner.

### Evidence Upload, Files, And Processing — Substantial; security and resilience work is P0/P1

Present:

- SHA-256 hashing and original filename/size/uploader metadata;
- folders, duplicate detection, previews, processing profiles, status, and background jobs;
- document, image/OCR, audio, video, spreadsheet, and Cellebrite processing paths;
- chunked/streamed staging in parts of the main backend.

Required:

- internalise and authenticate the ingestion API;
- enforce file, request, case-storage, and concurrency quotas;
- preserve originals as immutable objects and define whether deletion is soft, hard, or retention-controlled;
- record a chain-of-handling history without making unsupported legal “chain of custody” claims;
- add malware scanning, MIME/signature validation, archive-bomb protection, filename normalisation, and rejected-file quarantine;
- make jobs idempotent and resumable after worker/VM restarts;
- test cancellation, concurrent uploads, low disk, provider timeout, partial parsing, duplicate names, huge files, corrupt files, and interrupted writes;
- expose actionable error messages while keeping evidence text and provider secrets out of logs.

### Graph And Entity Review — Feature-rich; access control and provenance are P0/P1

Present:

- graph loading/search/expansion, entity details, algorithms, manual creation/editing, merging, rejected merges, geocoding, insights, and recycle-bin operations;
- case IDs are passed into most Neo4j queries;
- targeted tests for merges, graph edits, and safety helpers.

Required:

- enforce case permissions on every endpoint rather than relying on `case_id` query filtering;
- require source document/page/quote provenance for extracted entities, relationships, facts, and insights and keep it visible after merges;
- distinguish extracted fact, model inference, investigator assertion, and verified fact in the data model and UI;
- stress test large graphs, merge concurrency, graph algorithms, export resolution, and browser memory;
- provide a clear explanation for capped/filtered graphs and faded relevance nodes;
- add deterministic audit records for manual edits, merges, restores, and deletes.

### Table View — Mostly product hardening; P1

Required:

- verify search/filter/export operate on the full case dataset rather than only loaded rows;
- preserve stable entity/transaction identifiers in exports;
- make bulk edits permission-aware and auditable;
- test sorting, pagination/virtualisation, empty data, large data, malformed properties, and merged/deleted entities;
- ensure columns make provenance and confidence visible, not just model output.

### Timeline And Saved Views — Active development; P1 regression gate

Present:

- timeline endpoints, saved timeline views, and current work on timeline exports/date handling;
- targeted service/router tests.

Required:

- finish and merge the active timeline changes before declaring a release candidate;
- verify date precision, unknown dates, timezone behaviour, source citations, manual corrections, saved-view ownership, and export fidelity;
- test thousands of events and confirm filtering/exporting does not silently omit data;
- clearly distinguish event date from evidence/file ingestion date.

### Map And Geocoding — Functional; P1

Required:

- show geocoding source, confidence/precision, and manual correction history;
- avoid representing approximate coordinates as exact locations;
- add provider quota/budget handling, retry/backoff, cache controls, and degraded behaviour;
- test invalid addresses, ambiguous places, duplicate locations, no-network mode, and large marker counts;
- confirm map tiles/geocoding providers are named in privacy and subprocessor documentation.

### Financial Analysis And Exports — Rich but blocked by access control; P0/P1

Present:

- transaction/intelligence modes, categories, from/to corrections, sub-transactions, summaries, charts, bulk correction, and PDF export.

Required:

- add authentication and case authorisation to every read and write route;
- trace every value to its source document/page/quote and clearly label inferred transactions;
- test currency, decimal precision, negative/refund values, missing dates, timezones, duplicate transactions, aggregation totals, and export parity;
- add stable human-reference transaction IDs;
- ensure PDF/CSV output includes filters, generation time, case identity, confidentiality label, and provenance;
- make search persistent on smaller screens and complete the known financial usability backlog.

### Cellebrite Workflows — Valuable differentiator; P1 stress and licensing review

Required:

- test representative and very large UFDR/XML exports, partial/corrupt reports, cancellation, re-ingestion, duplicate contacts, attachments, timezone conversion, and multi-report intersection;
- prove report/file deletion cannot leave cross-store orphans;
- validate search and export results against known fixtures;
- document which Cellebrite formats/versions are supported and any third-party licensing restrictions;
- ensure raw mobile-device data follows the strictest retention, access, and logging controls.

### Triage — Useful but high-risk filesystem surface; P1

Required:

- restrict source roots at deployment and authorise triage as an admin/import role rather than a general user action;
- prevent symlink/path escapes and network-share surprises;
- cap scan depth, file count, hashing work, concurrency, and LLM advisory cost;
- make dry-run the default and show exactly what will be imported into which case;
- test cancellation/restart and preserve a manifest of triaged source files and hashes.

### Workspace, Notes, Findings, Witnesses, And Notebook — Broad; P1 reliability gate

Present:

- notes, theories, witnesses, findings-related workspace models, deadlines, notebook entries, links to entities/evidence, and notebook export work.

Required:

- reproduce and close or explicitly retire the existing backlog reports about disappearing/failed notes, snapshot timeouts, and cross-case audit entries;
- prevent modal dismissal or navigation from discarding unsaved work; add drafts/autosave where appropriate;
- add optimistic-concurrency handling so one investigator cannot silently overwrite another;
- ensure every object is case-scoped, permission-checked, exportable, and auditable;
- define privilege/confidentiality labels as product metadata without implying legal status automatically.

### Reports And Court/Client-Ready Export — Incomplete; P1 blocker

The frontend Reports page calls `/api/reports`, but no reports router is registered in the backend. The viewer's Print and Export buttons also have no handlers in the reviewed component.

Required:

- decide whether V1 reports are a dedicated report builder or a curated bundle of existing graph/timeline/notebook/financial exports;
- implement server-side, case-authorised report persistence and generation;
- sanitise content and generate deterministic PDF/DOCX/CSV outputs;
- include case identity, report version, author, generation timestamp, section ordering, source citations, confidentiality marking, and an AI/human-review statement;
- test pagination, fonts, large tables, graph DPI, page breaks, missing assets, and re-export consistency.

### AI Chat — Good retrieval foundations; citation contract is P0/P1

Present:

- case/document-scoped retrieval, source objects, page metadata, document links, result graphs, and cost tracking.

Required:

- require a visible citation for every material factual claim or explicitly state that no supporting source was found;
- make every citation open the exact file/page/chunk/quote and test broken/deleted sources;
- distinguish retrieval evidence from model reasoning and never present absence of evidence as evidence of absence;
- add the permanent message: AI output can be incomplete or wrong and must be verified against original evidence;
- defend against prompt injection in uploaded documents and tool output;
- define retention and provider-training terms for prompts/files, and verify actual provider settings support landing-page claims;
- add per-case/per-user budgets, warnings, hard caps, and graceful provider outage handling.

### Investigation Agent — Supervised pilot only until hardened; P1

Present:

- stored threads/runs, tool traces, cancellation, graph/table/chart/report artifacts, exports, and cost records.

Required:

- keep tools read-only by default and require explicit confirmation for mutations/exports;
- enforce case permissions inside each tool, not only at the outer agent endpoint;
- cap tool iterations, query size, result size, runtime, and spend;
- test prompt injection, cross-case key guessing, malicious evidence text, cancellation races, retries, duplicated tool calls, and partial failures;
- show the investigation trail and citations by default for customer use;
- label agent-generated artifacts as drafts until a human approves them.

### Platform Administration — Useful start; P0/P1 hardening

Present:

- users, profiles, logs, tasks, AI costs, and platform update screens;
- update checking and constrained systemd service start.

Required:

- enforce the admin role in frontend navigation and every backend admin/maintenance route;
- replace in-place Git updates with a release-channel/fleet deployment system;
- add instance ID, customer, environment, version, schema version, region, health, storage, last backup, last restore test, and last deployment to an operations inventory;
- separate customer-visible audit history from internal technical logs;
- make support access time-bound and auditable.

### Branding And First-Run Experience — Decision required; P1

The recent history contains competing Owl/Deduce branding changes, while brand-research material is still active.

Required:

- freeze the product/company name before domain, contracts, certificate names, email, and customer documentation are issued;
- perform company-name, domain, social-handle, and trademark clearance with professional advice where needed;
- replace names/logos/favicons/email copy/export templates consistently across app, landing page, docs, systemd units, image names, and legal terms;
- create a first-login onboarding checklist and a small representative demo case;
- establish `support@`, `security@`, and operational sender addresses with SPF, DKIM, and DMARC.

## Recommended Per-Customer Google Cloud Architecture

### Isolation Boundary

For the first customers, use one Google Cloud project per customer plus a separate company operations project. A project boundary makes IAM, billing, quotas, logs, secrets, backups, deletion, and incident scope easier to reason about than several customer VMs in one project.

Each customer project should contain:

- one explicitly sized Compute Engine instance initially, or a later managed service design;
- a dedicated VPC/firewall policy and reserved static external IP;
- a unique service account with only the permissions that instance needs;
- unique Secret Manager secrets;
- dedicated persistent disks and evidence object-storage bucket;
- dedicated backup location/retention policy;
- budget alerts, log sinks, uptime checks, and labels identifying customer/environment/owner;
- no shared database, volume, model-provider key, admin password, backup, or log store unless the sharing is deliberately designed and contractually disclosed.

The central operations project should hold:

- Cloud DNS for the product domain;
- Artifact Registry for immutable signed/versioned images;
- infrastructure state and the deployment control plane;
- a minimal customer-instance inventory;
- central alert routing and security audit sinks, designed to avoid copying evidence content;
- break-glass identities protected by phishing-resistant MFA.

### Domain And TLS

Recommended first-release flow:

1. Buy the final domain through a registrar account owned by the company, protected by MFA, registry lock where available, and named recovery contacts.
2. Delegate DNS to a Cloud DNS public managed zone in the operations project.
3. Reserve a static external IP in each customer project.
4. Provision an explicit `customer.ourdomain.com` A/AAAA record pointing to that customer's IP. Cloud DNS supports creating these records through its API or Terraform. A wildcard DNS record is only useful when every name terminates at the same routing layer; it cannot select a different customer VM by hostname on its own.
5. Terminate TLS at a hardened reverse proxy on the customer instance for the first few customers, or at a managed external Application Load Balancer when central routing is justified. Automate certificate issuance and renewal and alert well before expiry.
6. Redirect HTTP to HTTPS and enable HSTS only after every intended subdomain is HTTPS-ready.

Relevant current Google documentation:

- [Cloud DNS record management](https://docs.cloud.google.com/dns/docs/records)
- [Compute Engine static external IP addresses](https://docs.cloud.google.com/compute/docs/ip-addresses/configure-static-external-ip-address)
- [Certificate Manager DNS authorisation and wildcard coverage](https://docs.cloud.google.com/certificate-manager/docs/domain-authorization)

### Network Boundary

- Expose only 80/443 publicly; redirect 80 to 443.
- Bind the backend to loopback or a private container network.
- Do not publish Postgres, Neo4j, Chroma, Redis, or ingestion ports.
- Use IAP/OS Login or a VPN for administration; avoid public SSH where possible.
- Use least-privilege firewall rules and service accounts.
- Turn on automatic OS security updates or run a documented patch schedule.
- Add host and disk-capacity monitoring before allowing uploads.

### Secrets

Each instance needs unique values for:

- database users/passwords;
- Neo4j credentials;
- Redis/service authentication where retained;
- JWT/session signing keys;
- initial admin recovery material;
- backend-to-ingestion service identity;
- model, maps/geocoding, email, monitoring, and backup credentials.

Provision secrets from Secret Manager at runtime or into a root-readable environment file with strict permissions. Do not bake them into images, Compose files, repositories, logs, support bundles, or backups without encryption. Document rotation and test it.

### Provisioning

Create a Terraform module or equivalent repeatable infrastructure definition that accepts at least:

- customer slug and display name;
- project/billing account;
- region/zone and data-residency choice;
- machine/disk/storage sizes;
- DNS name;
- backup retention and RPO/RTO tier;
- model-provider configuration and spend budget;
- initial administrators and support-access policy;
- release channel/version.

Provisioning should output an inventory record and run an automated smoke test. Hand-built VMs are acceptable only for an internal rehearsal, not as the customer deployment process.

## Release, Update, Migration, And Rollback System

### Release Artifact

- Build backend, ingestion, worker, and frontend artifacts once in CI.
- Tag with an immutable semantic version and commit SHA; pin production by image digest.
- Generate an SBOM and vulnerability scan; record the approved artifact set in a release manifest.
- Do not run `git pull`, `pip install`, `npm ci`, or a Vite dev server on customer production hosts.

### Promotion

Use this sequence:

1. Developer checks and code review.
2. CI unit/integration/security/build gates.
3. Restore a recent sanitised backup into staging.
4. Run migrations and full smoke/end-to-end tests in staging.
5. Deploy to the company demo/internal instance.
6. Deploy to one canary customer in an agreed maintenance window.
7. Observe health/error/latency/job metrics.
8. Roll out in small batches, recording outcome per instance.

### Database Migrations

- Treat Postgres, Neo4j, Chroma metadata, and file manifests as one compatibility contract.
- Prefer expand/contract migrations: add compatible schema, deploy code that understands old/new, backfill, then remove old schema in a later release.
- Make migrations idempotent where practical and record duration/progress.
- Test against realistic customer-sized data and old-version backups.
- Block deployment when preconditions, disk space, backup freshness, or migration state fail.
- Never assume application rollback automatically reverses a data migration.

### Rollback

A releasable version must have a written recovery choice:

- **Code rollback:** previous artifact remains compatible with the current schema.
- **Roll forward:** fix is safer than reversing a completed migration.
- **Full restore:** restore the coordinated pre-deploy backup when schema/data are incompatible.

The team must rehearse all three. The admin update button should only request an approved release; it should not decide release compatibility on its own.

## Backup, Restore, Retention, And Deletion

### Backup Set

Back up as one documented recovery set:

- Postgres application and audit data;
- Neo4j graph data and indexes/constraints;
- original evidence and generated derivatives;
- Chroma data, or the complete immutable inputs and tested procedure needed to rebuild it;
- deployment/release manifest and migration versions;
- non-secret configuration plus references to separately protected secrets;
- customer/instance identity needed to recreate DNS, IAM, and storage.

### Policy

- Agree an RPO and RTO with the customer; a reasonable pilot target might be stated in hours, but it must be chosen and tested, not assumed.
- Keep multiple generations, encrypt backups, and store them outside the failure boundary of the instance/project where practical.
- Use retention locks/immutability appropriate to the threat model.
- Monitor age, completion, size anomalies, and restore-test status.
- Ensure backup access and deletion are more restricted than ordinary application administration.

### Restore Test

Before release, restore a representative case into a clean project and verify:

1. application and schema versions are known;
2. users can authenticate;
3. membership/permissions remain correct;
4. original file hashes match;
5. folders/previews/processing status load;
6. graph, table, timeline, map, financial, Cellebrite, workspace, notebook, chats, and agent artifacts load;
7. citations open the correct source;
8. exports reproduce;
9. queued/running jobs recover safely;
10. audit history remains intact and the restore is itself recorded.

### Offboarding And Deletion

Create a two-person, ticketed process to:

- disable users and support access;
- export customer data in the agreed format;
- remove DNS and certificates;
- delete instance, disks, buckets, logs, secrets, backups, and central inventory entries according to contract;
- account for backup expiry rather than claiming immediate deletion where it is not true;
- provide a deletion certificate/record without retaining sensitive case content.

## Monitoring, Logging, And Support

### Minimum Signals Per Instance

- external HTTPS uptime and certificate expiry;
- backend and ingestion readiness;
- Postgres, Neo4j, Chroma, and Redis connectivity;
- worker heartbeat, queue depth, oldest job age, failures, and retries;
- disk/evidence storage use and forecast;
- CPU, memory, load, container restarts, and OOM events;
- HTTP 4xx/5xx rate, latency, WebSocket failures, and login failures;
- backup freshness/failure and last restore test;
- current application/schema version and deployment result;
- AI/provider errors, token/cost usage, and budget thresholds.

### Alerting

Route P0 alerts to a monitored on-call destination, not just a dashboard. Define ownership and response for unavailable instance, failed backup, disk nearing full, repeated auth failures, suspected breach, runaway cost, stuck ingestion, certificate expiry, and failed update.

OpenTelemetry packages are installed in the backend but no active telemetry export was found. Either wire OTel to a chosen backend or remove the false signal of unused dependencies. Error tracking may use Cloud Error Reporting, Sentry, or another approved tool, but customer evidence/prompt content must be scrubbed.

### Support Runbooks

Write and rehearse:

- unavailable instance;
- failed/stuck ingestion;
- low/full disk;
- failed backup or restore;
- failed update/rollback;
- lost admin/MFA device;
- suspected unauthorised access or data disclosure;
- incorrect or harmful AI output;
- model/geocoding provider outage;
- customer offboarding/deletion;
- legal hold or deletion request conflict.

Define support hours, contact channels, severity levels, response targets, maintenance windows, and who may access customer data. Support access should be time-bound, least-privilege, and audited.

## QA And Release Engineering

### Current Verification Baseline (2026-07-10)

| Check | Result |
|---|---|
| Backend Pytest | **Pass:** 119 tests; 8 deprecation warnings |
| Evidence-engine Pytest | **Pass:** 34 tests |
| Main frontend Vitest | **Fail:** 147 passed, 11 failed; 6 of 57 test files failed |
| Main frontend production build | **Pass with warnings:** 2.16 MB main JS chunk before gzip; chunk-size warning |
| Main frontend ESLint | **Fail:** 28 errors, 22 warnings; generated Storybook output is being linted |
| Landing production build | **Pass** |
| Landing ESLint | **Pass** |
| Main frontend runtime dependency audit | **Fail:** 3 high and 1 moderate advisories, including React Router and lodash-es dependency paths |
| Landing runtime dependency audit | **Pass:** no known vulnerabilities reported |
| Python environment consistency | **Pass:** `pip check` reports no broken requirements |
| End-to-end browser tests | **Missing:** no Playwright/Cypress test suite found |
| CI workflow | **Missing:** no `.github/workflows` files found |

The passing Python tests do not cover the full access-control matrix: the confirmed unauthorised routes demonstrate that route coverage and negative security tests are incomplete.

### Required CI Gate

On every pull request and release:

- Python formatting/lint/type checks selected by the team;
- backend and ingestion tests with coverage reporting;
- frontend typecheck, lint, unit tests, and production build;
- dependency and container-image vulnerability scans;
- secret scanning;
- migration-upgrade test from the oldest supported customer version;
- API contract/security tests for every role and non-member;
- end-to-end smoke tests for login, case creation, membership, upload/process, graph, timeline, financial, chat citation, report/export, admin boundary, and logout;
- artifact publishing only after all required gates pass.

### Manual Release Matrix

Test at least current Chrome and Edge on the supported desktop resolutions. Add Firefox/Safari only if promised. Include slow network, provider failure, refresh during a long job, concurrent users, session expiry, keyboard-only operation, high zoom, and screen-reader basics.

Run load tests using representative case sizes:

- many small files and a few very large files;
- 10k+ entities and relationships;
- large Cellebrite reports;
- thousands of timeline events and financial transactions;
- simultaneous ingestion and investigation;
- near-full disk and worker restart.

Define pass/fail thresholds for response latency, job completion, memory, error rate, queue delay, and maximum supported case size.

## Privacy, Legal, And Commercial Readiness

Obtain qualified legal/privacy advice before launch. At minimum prepare:

- customer licence/service agreement;
- data processing agreement defining controller/processor roles;
- privacy notice and acceptable-use policy;
- confidentiality and IP terms;
- subprocessor list covering Google Cloud, model providers, maps/geocoding, email, monitoring/error tracking, and support tools;
- data-location, international-transfer, retention, backup, deletion, legal-hold, and breach-notification terms;
- AI limitations, human-review requirement, prohibited/high-risk uses, and allocation of responsibility;
- support/maintenance terms, uptime wording, RPO/RTO, liability cap, payment, termination, and export/offboarding;
- security schedule describing instance isolation and support access accurately.

Investigation data can include criminal allegations, communications, location, financial, biometric-like media, legal privilege, and data about uninvolved third parties. Do not make marketing promises such as “strict no-training terms,” residency, deletion, encryption, or isolation until the deployed provider settings and contracts prove them.

Also complete company ownership of source code, prompts, domains, trademarks, cloud accounts, model-provider accounts, and customer contracts before founders personally hold production infrastructure.

## Documentation And Onboarding

Create two separate sets of documentation.

Customer documentation:

- first login and MFA;
- roles and case permissions;
- create a case and invite a collaborator;
- upload/process evidence and understand supported formats/limits;
- review/correct entities and relationships;
- use graph, table, timeline, map, financial, Cellebrite, workspace, notebook, chat, agent, and reports;
- understand citations, confidence, and AI limitations;
- export, request restore, request deletion, and contact support;
- known limitations and release notes.

Internal runbooks:

- provision/onboard a customer;
- rotate secrets and recover admin access;
- deploy/canary/rollback/restore;
- monitor and respond to incidents;
- handle provider outages/cost spikes;
- offboard/delete a customer;
- maintain the fleet inventory and supported-version policy.

The existing guide-generation scripts are useful, but generated PDFs should be a release artifact derived from versioned source documentation, not the only source of truth.

## Phased Delivery Plan

### Phase 0 — Before Any External Real Data

1. Freeze the production topology and brand/name decision.
2. Close every public/internal service exposure; rotate all secrets.
3. Apply default authentication and complete route-by-route case authorisation.
4. Restrict all destructive/global operations to admins and secure audit logs.
5. Harden sessions, add login throttling, and implement admin MFA and account recovery.
6. Build production static assets behind HTTPS and security headers.
7. Implement repeatable per-customer project/VM/DNS/secret provisioning.
8. Replace in-place source deployments with immutable versioned artifacts.
9. Implement coordinated backups and pass a clean restore drill.
10. Make update/migration/rollback strategy version-aware and rehearse it.
11. Fix required frontend tests/lint and high runtime dependency advisories; add CI.
12. Add real readiness checks, alerting, disk/queue/backup monitoring, and an instance inventory.
13. Complete source-citation/AI warning acceptance tests.
14. Complete customer contract, DPA, privacy/subprocessor, support, retention, and incident terms.

### Phase 1 — Before The First Customer Operates Independently

1. Close unresolved note/snapshot/concurrent-upload regressions.
2. Finish reports/export or explicitly narrow the promised V1 export scope.
3. Complete user/admin and first-case documentation.
4. Add browser end-to-end tests and run large-case/performance exercises.
5. Add storage and AI budget alerts/caps.
6. Harden Agent and Triage for bounded, authorised use.
7. Run a full internal “day in the life” investigation with a non-developer.
8. Define pilot success measures, support cadence, and feedback/bug triage.

### Phase 2 — Before Expanding Beyond A Few Customers

1. Fleet-wide staged rollout and version compliance automation.
2. Centralised support tooling that does not expose customer evidence by default.
3. Stronger SLOs, disaster-recovery cadence, capacity forecasts, and security testing.
4. Formal vulnerability-management and penetration-test programme.
5. Customer-controlled retention/deletion and portable versioned case export/import.
6. SSO/SAML/SCIM where customers require it.
7. Compliance roadmap driven by actual sales requirements, not badges first.
8. Automated billing only when manual invoicing becomes a real bottleneck.

## First-Customer Go/No-Go Drill

Release only when one named owner signs off each item and evidence is attached.

1. Provision a brand-new customer project from automation.
2. Confirm only 80/443 are internet-reachable and TLS/security headers pass.
3. Prove every customer secret and credential is unique.
4. Create admin, investigator/editor, viewer, guest, and non-member test users; verify the permission matrix including direct API calls.
5. Upload a representative mixed dataset and verify hashes, provenance, status, failure handling, and quotas.
6. Review/correct graph entities and relationships; verify citations survive edits/merges.
7. Exercise table, timeline, map, financial, Cellebrite, workspace, notebook, chat, agent, and the promised report/export scope.
8. Confirm material AI claims link to the exact source and unsupported claims are clearly identified.
9. Trigger and observe a scheduled backup.
10. Restore the whole instance into a clean project and complete the restore checklist.
11. Deploy a backward-compatible update to staging and canary.
12. Simulate a failed deployment and prove the documented rollback/restore path.
13. Simulate worker crash, provider outage, low disk, expired session, and unauthorised case access.
14. Confirm alerts reach the responsible person and the support runbook is usable.
15. Verify current tests, lint, builds, dependency scans, and end-to-end suite are green in CI.
16. Have a non-developer complete onboarding and a first investigation from customer docs.
17. Confirm signed commercial/DPA terms, subprocessors, retention, support contacts, and offboarding procedure.

If any P0 control fails, do not use real external case data. A synthetic-data demo or design-partner walkthrough can continue while the control is completed.

## Explicit Deferrals For The First Pilot

These can wait unless the first customer contract requires them:

- automated subscriptions and billing;
- SAML/SSO/SCIM;
- SOC 2 or ISO 27001 certification;
- a sophisticated customer-facing status page;
- mobile-first graph investigation;
- multi-region active-active architecture;
- support chat inside the product;
- multiple model providers purely for choice rather than resilience or contract need.

Manual invoicing, founder-led onboarding, scheduled maintenance windows, and a simple internal fleet inventory are reasonable for the first one to three customers. Manual security boundaries, untested restores, and ad hoc production edits are not.

## Questions The Founders Must Decide

1. Is a customer project (stronger isolation) or a shared company project with one VM per customer the contractual promise? This audit recommends a project per customer.
2. Which countries/regions may hold customer data, backups, logs, and model-provider requests?
3. What RPO, RTO, support hours, maintenance window, and incident-notification target will be promised?
4. Which user roles exist at launch, and may company support staff ever view customer evidence?
5. What is the maximum supported storage, file size, case size, concurrent jobs, and monthly AI spend for the pilot package?
6. Which report/export formats are actually promised in V1?
7. Is the Agent included in V1, beta-labelled, admin-enabled, or disabled for the first customer?
8. What is the final product/company name and who owns the domain, marks, and cloud/provider accounts?
9. Which provider terms support the statements made on the landing page about training, retention, and customer isolation?
10. Who is the named owner for security, deployments, backups, support, and incident response during the first pilot?
