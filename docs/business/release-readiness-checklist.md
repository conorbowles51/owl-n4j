# Release Readiness Checklist

Prepared: 2026-06-04

## Reader And Use

This checklist is for the founders deciding whether Owl is ready to licence to external customers. After reading it, the team should be able to split work into release blockers, first-customer hardening, and later improvements.

The standard used here is not "perfect enterprise software". The standard is: can a real investigation firm safely put real client/case data into an isolated Owl instance, receive support, recover from failure, and understand the limits of the AI output?

## Release Assumption

The first external licensing window is expected around July 2026 through Alex's investigator contacts in the United States. The first customers are likely to be smaller investigation or legal/investigation-adjacent teams, not large government agencies or highly formal enterprise procurement departments.

That means Owl can launch without every future enterprise feature, but it cannot launch without trust basics: authentication, secrets, data isolation, backups, restore, auditability, and a clear support path.

## Priority Definitions

- **Release blocker:** Do before any external customer uses Owl with real case data.
- **First-customer hardening:** Do before expanding beyond a tightly supervised first customer or pilot.
- **Defer:** Useful, but not needed for the first external licences if risk is acknowledged.

## Recommended Definitely List

These should be treated as release blockers unless the team consciously accepts the risk in writing.

| Area | Item | Priority | Acceptance Criteria |
|---|---|---:|---|
| Security | Replace all default secrets and development credentials | Release blocker | Every customer instance has unique database passwords, JWT/session signing keys, API keys, admin credentials, and service secrets. No production secrets live in source control. |
| Security | Centralise production secret handling | Release blocker | Secrets are stored in a controlled secret manager or equivalent deployment mechanism. Rotation is documented and tested. |
| Security | Harden the Docker stack for production | Release blocker | Databases are not publicly exposed, containers run with minimum practical privileges, only required ports are open, TLS is enforced, and admin services are restricted. |
| Authentication | Multi-factor authentication | Release blocker | MFA is available for all users and mandatory for admins. Recovery codes or an admin recovery process exists. |
| Authentication | Password reset and account recovery | Release blocker | A user can recover access without a developer manually editing a database, while preserving auditability. |
| Access control | Role-based access control | Release blocker | At minimum: owner/admin, investigator/editor, reviewer/read-only. Permissions are enforced server-side. |
| Auditability | Audit logs for sensitive actions | Release blocker | Logins, failed logins, case access, file uploads, exports, deletes, admin actions, AI queries, and permission changes are recorded. |
| Evidence integrity | Preserve uploaded evidence and file hashes | Release blocker | Original files are retained, hashed, and traceable to uploader/time/case. Hashes survive backup/export/import. |
| AI reliability | Source citations for AI answers | Release blocker | Important AI claims link back to the document/page/chunk/entity evidence used. Users can inspect the basis for a graph edge or answer. |
| AI reliability | Clear AI limitation language | Release blocker | The UI/docs tell users that AI output is investigative assistance, not verified fact, legal advice, or a substitute for human review. |
| Backups | Automatic infrastructure backups | Release blocker | Postgres, Neo4j, Chroma/vector data, uploaded files, and deployment config are backed up on a schedule. |
| Backups | Tested restore process | Release blocker | A backup has been restored into a clean environment and verified with a representative case. Restore steps are documented. |
| Portability | Case export/import | Release blocker | A case can be exported and re-imported with evidence, entities, relationships, notes, snapshots, and relevant metadata intact. |
| Deployment | Multi-instance GCP deployment process | Release blocker | The team can create a new isolated customer instance from a repeatable process without hand-building each server. |
| Deployment | Update and rollback system for customer instances | Release blocker | The team can deploy an update to one or many customer instances, verify health, and roll back if needed. |
| Deployment | Database migration discipline | Release blocker | Schema/data migrations run safely across isolated instances and can be verified before/after deployment. |
| Monitoring | Health checks and basic alerting | Release blocker | Each instance exposes backend, worker, database, and storage health signals. Failures alert the team. |
| Logging | Sensitive-data-safe error logging | Release blocker | Logs are useful for support but do not dump evidence text, uploaded documents, API keys, passwords, or full AI prompts by default. |
| Documentation | Comprehensive documentation page | Release blocker | Admin setup, user workflow, evidence upload, graph/timeline/map/financial views, AI assistant, exports, backups, restore, and support procedures are documented. |
| Commercial | Customer licence terms and data-processing terms | Release blocker | A customer cannot be onboarded without signed commercial terms, acceptable use, confidentiality/data-processing terms, and liability boundaries. |
| Support | Incident response and support runbook | Release blocker | The team knows what to do for a data issue, failed deployment, unavailable instance, bad AI output, lost admin access, or failed restore. |

## First-Customer Hardening

These are very important, but a tightly supervised first paid pilot could proceed if the gap is disclosed, mitigated manually, and tracked.

| Area | Item | Priority | Acceptance Criteria |
|---|---|---:|---|
| Security | Session timeout and device/session management | First-customer hardening | Sessions expire after reasonable inactivity; admins can invalidate sessions. |
| Security | Admin access boundary | First-customer hardening | Developer/admin access to customer instances is logged, minimised, and ideally approved by the customer for support events. |
| Security | Vulnerability and dependency scan | First-customer hardening | Critical/high dependency issues are reviewed before launch. |
| Deployment | Customer instance inventory | First-customer hardening | The team has a single view of customer, region, version, health, backup state, and last deployment. |
| Deployment | Environment promotion path | First-customer hardening | A release can move from local/dev to staging to one customer instance before fleet rollout. |
| Data | Customer-level data deletion | First-customer hardening | The team can delete a case, user, and full customer instance according to contract and document what was deleted. |
| Product | Bates number support | First-customer hardening | Legal/investigation users can trace evidence references to stable production/document identifiers. |
| Product | Court/client-ready exports | First-customer hardening | PDF/CSV exports exist for timeline, entities, relationships, graph images, and report summaries. |
| Product | User corrections for AI extraction | First-customer hardening | Users can correct entities/relationships and those corrections persist through reloads/exports. |
| Cost | Per-customer and per-case AI cost controls | First-customer hardening | Usage is visible and can be capped or alerted before bills surprise either party. |
| Onboarding | First-case onboarding guide | First-customer hardening | A new investigator can create a case, upload evidence, review graph/timeline, ask questions, and export results without founder handholding. |
| Sales | Pilot success criteria | First-customer hardening | Each paid pilot has defined success metrics: time saved, case insight generated, reliability feedback, and renewal/expansion decision. |

## Defer For Later

These are valuable but probably not necessary before the first licences.

| Item | Why Defer |
|---|---|
| Full billing/subscription automation | Manual invoicing is fine for the first few customers. |
| SSO/SAML | Important for enterprise later, but not needed for small investigation firms unless requested. |
| SOC 2 or ISO 27001 certification | Too heavy before validation, but design controls so certification is possible later. |
| Marketplace integrations | Direct deployment is enough for early customers. |
| In-app support chat | Email and scheduled calls are enough at first. |
| Advanced customer analytics dashboard | Basic usage, cost, health, and backup visibility matter more. |
| Full mobile experience | Investigative graph work is likely desktop-first. |

## Security Checklist Detail

### Secrets And Credentials

Before any customer instance goes live:

- Generate unique credentials per customer instance.
- Rotate all development/default passwords.
- Separate production and development API keys.
- Restrict access to OpenAI/Gemini/other model provider keys.
- Ensure JWT/session signing keys are high entropy and customer-specific.
- Record who can access secrets and why.
- Document emergency rotation steps.

### Instance Isolation

The commercial promise is that each customer gets an isolated environment. That needs evidence, not just architecture intent:

- Separate cloud project or strong project-level separation per customer.
- Separate databases, storage volumes/buckets, secrets, backups, and logs.
- No shared admin password across customers.
- No shared evidence storage path across customers.
- Clear naming convention for instances and backups.
- Written deletion process for offboarding.

### Audit Logs

Audit logs should answer:

- Who accessed this case?
- Who uploaded or deleted evidence?
- Who exported data?
- Who asked the AI a sensitive question?
- Who changed permissions?
- Which admin accessed the instance for support?
- What changed before a customer reported a problem?

The logs do not need to be a full SIEM on day one. They do need to be trustworthy, queryable, and retained.

## Backup And Restore Requirements

Backups are not complete until restore works.

Minimum backup scope:

- Relational case/user/task/audit data.
- Graph entities and relationships.
- Vector/embedding store data or a documented rebuild path.
- Uploaded evidence files.
- Configuration needed to recreate the instance.
- Application version and migration state.

Minimum restore test:

1. Create a representative case with uploaded evidence, extracted graph, timeline events, map locations, financial transactions, notes, and AI chat history.
2. Run a scheduled backup or manual backup using the production process.
3. Restore into a clean environment.
4. Confirm login works.
5. Confirm the case opens.
6. Confirm evidence files are present and hashes match.
7. Confirm graph/timeline/map/financial views load.
8. Confirm exports still work.
9. Confirm audit logs show the restore or imported state.

## Deployment Requirements

The team should be able to deploy Owl like a product, not like a one-off server project.

Minimum release workflow:

- Build versioned application images or release artifacts.
- Provision a new customer instance from a repeatable script or infrastructure definition.
- Run migrations automatically with clear failure handling.
- Health-check the deployment.
- Smoke-test login, evidence upload, graph view, AI assistant, export, and backup.
- Roll back to the previous known-good version if health checks fail.
- Record which customer is on which version.

For the first few customers, the system can be semi-automated. But the exact steps should still be written and repeatable.

## Documentation Requirements

The comprehensive documentation page should include:

- Getting started.
- User roles and permissions.
- Creating and managing a case.
- Uploading and processing evidence.
- Understanding AI extraction quality.
- Reviewing graph entities and relationships.
- Timeline, map, table, and financial workflows.
- Asking the AI assistant questions.
- Interpreting source citations.
- Exporting case materials.
- Backup/restore expectations.
- Security model in plain language.
- Support and escalation process.
- Known limitations.

## Legal And Commercial Readiness

Even a small first licence needs basic paperwork:

- Customer licence agreement or SaaS/service agreement.
- Data processing agreement.
- Confidentiality language.
- Acceptable use policy.
- AI limitations and human-review disclaimer.
- Support hours and response expectations.
- Backup/restore responsibility.
- Data deletion and offboarding terms.
- Liability cap.
- Payment terms.
- Clarification of whether Alex/Owl Consultancy is reseller, customer, referral partner, or founder-led sales channel.

This is especially important because the platform may process criminal, legal, financial, and personally sensitive investigation data.

## First External Release Gate

Before saying "V1 is ready for external licensing", run one complete release drill:

1. Provision a fresh isolated instance.
2. Create users with MFA.
3. Upload a representative investigation dataset.
4. Process evidence end to end.
5. Inspect graph, timeline, map, financial, and AI assistant outputs.
6. Export a case/report.
7. Trigger a backup.
8. Restore the backup into a clean environment.
9. Deploy an update.
10. Roll back the update.
11. Review audit logs.
12. Confirm docs are enough for a new user to complete the workflow.

If any step fails, Owl can still be close, but it is not release-ready for real customer data.
