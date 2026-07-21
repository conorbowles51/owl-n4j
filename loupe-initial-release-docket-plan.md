# Loupe Initial Release Plan
Source: `RELEASE_BACKLOG.html` (16 July 2026) and `v2-alpha-bridging-plan.md`, derived from the V2 Gap Assessment and V2 Bridging Roadmap (13 July 2026). This file de-duplicates both backlogs into one build-ordered Docket import.
Conscious exclusions retained from the bridging roadmap: `/nodes-by-type`, fcntl JSON locking, the abandoned V1 financial-pagination experiment, DKT-40’s alternate timezone-filter variant, and V1 client-side jsPDF. The broken end-user Cypher panel is deliberately retired; direct-query APIs are removed or strictly case-scoped and read-limited.

## Epic: Release Scope, Security & Identity
Color: #d95d47
Freeze the first-release contract, close every authentication and case-boundary gap, and make case and user administration safe before real external evidence enters the platform.

### Story: Publish the V1 feature and navigation contract
Priority: P0
Source: Release backlog REL-001 (repository and product audit, 16 July 2026). Resolve every ambiguous ‘keep, merge, port or remove’ item so engineering, QA, documentation and sales test the same product.
Release gate: Before implementation freeze. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- One versioned scope matrix drives backlog, test plan, documentation and release notes; no visible placeholder or non-working action remains.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Classify Graph analysis, Spotlight analysis, Map Proximity, movement trails, route analysis, AI Chat, Investigation Agent, Reports, Triage, AI…
Priority: P0
Estimate: 8h
Source: Release backlog REL-001, task 1. Classify Graph analysis, Spotlight analysis, Map Proximity, movement trails, route analysis, AI Chat, Investigation Agent, Reports, Triage, AI Costs and multiple model providers as V1, beta, admin-only or excluded.
Implement this bounded change under “Publish the V1 feature and navigation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before implementation freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Classify Graph analysis, Spotlight analysis, Map Proximity, movement trails, route analysis, AI Chat, Investigation Agent, Reports, Triage, AI Costs and multiple model providers as V1, beta, admin-only or excluded
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- One versioned scope matrix drives backlog, test plan, documentation and release notes; no visible placeholder or non-working action remains.

#### Task: For every excluded feature, remove its navigation, entry points, APIs where unsafe, documentation and marketing references
Priority: P0
Estimate: 4h
Source: Release backlog REL-001, task 2. For every excluded feature, remove its navigation, entry points, APIs where unsafe, documentation and marketing references.
Implement this bounded change under “Publish the V1 feature and navigation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before implementation freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: For every excluded feature, remove its navigation, entry points, APIs where unsafe, documentation and marketing references
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- One versioned scope matrix drives backlog, test plan, documentation and release notes; no visible placeholder or non-working action remains.

#### Task: Write one primary user journey for each included feature, with role, starting state, success outcome and supported limits
Priority: P0
Estimate: 8h
Source: Release backlog REL-001, task 3. Write one primary user journey for each included feature, with role, starting state, success outcome and supported limits.
Implement this bounded change under “Publish the V1 feature and navigation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before implementation freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Write one primary user journey for each included feature, with role, starting state, success outcome and supported limits
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- One versioned scope matrix drives backlog, test plan, documentation and release notes; no visible placeholder or non-working action remains.

#### Task: Record a named product owner and acceptance reviewer for every included surface
Priority: P0
Estimate: 6h
Source: Release backlog REL-001, task 4. Record a named product owner and acceptance reviewer for every included surface.
Implement this bounded change under “Publish the V1 feature and navigation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before implementation freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Record a named product owner and acceptance reviewer for every included surface
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- One versioned scope matrix drives backlog, test plan, documentation and release notes; no visible placeholder or non-working action remains.

### Story: Set the operating promises and hard limits
Priority: P0
Source: Release backlog REL-002 (repository and product audit, 16 July 2026). Convert undefined operational expectations into measurable release constraints.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Limits and responsibilities are documented, implemented as controls where applicable, and reflected in contract/support language.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Choose customer isolation model, permitted data regions and model/map/geocoding providers
Priority: P0
Estimate: 4h
Source: Release backlog REL-002, task 1. Choose customer isolation model, permitted data regions and model/map/geocoding providers.
Implement this bounded change under “Set the operating promises and hard limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Choose customer isolation model, permitted data regions and model/map/geocoding providers
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Limits and responsibilities are documented, implemented as controls where applicable, and reflected in contract/support language.

#### Task: Set maximum file size, files per upload, case storage, concurrent jobs, graph/event/transaction scale and monthly AI spend
Priority: P0
Estimate: 4h
Source: Release backlog REL-002, task 2. Set maximum file size, files per upload, case storage, concurrent jobs, graph/event/transaction scale and monthly AI spend.
Implement this bounded change under “Set the operating promises and hard limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Set maximum file size, files per upload, case storage, concurrent jobs, graph/event/transaction scale and monthly AI spend
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Limits and responsibilities are documented, implemented as controls where applicable, and reflected in contract/support language.

#### Task: Set backup RPO, restore RTO, support hours, maintenance windows and incident notification targets
Priority: P0
Estimate: 12h
Source: Release backlog REL-002, task 3. Set backup RPO, restore RTO, support hours, maintenance windows and incident notification targets.
Implement this bounded change under “Set the operating promises and hard limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Set backup RPO, restore RTO, support hours, maintenance windows and incident notification targets
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Limits and responsibilities are documented, implemented as controls where applicable, and reflected in contract/support language.

#### Task: Define company support access to customer evidence, approval rules and audit visibility
Priority: P0
Estimate: 8h
Source: Release backlog REL-002, task 4. Define company support access to customer evidence, approval rules and audit visibility.
Implement this bounded change under “Set the operating promises and hard limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define company support access to customer evidence, approval rules and audit visibility
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Limits and responsibilities are documented, implemented as controls where applicable, and reflected in contract/support language.

#### Task: Name accountable owners for security, releases, backups, support, incidents and privacy
Priority: P0
Estimate: 12h
Source: Release backlog REL-002, task 5. Name accountable owners for security, releases, backups, support, incidents and privacy.
Implement this bounded change under “Set the operating promises and hard limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Name accountable owners for security, releases, backups, support, incidents and privacy
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Limits and responsibilities are documented, implemented as controls where applicable, and reflected in contract/support language.

### Story: Run and sign the full first-customer release drill
Priority: P0
Source: Release backlog REL-003 (repository and product audit, 16 July 2026). Prove the complete system in a fresh production-like customer environment rather than inferring readiness from component tests.
Release gate: Final go/no-go. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Every P0/P1 criterion has recorded evidence and an owner; any failed P0 keeps the decision at no-go.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Provision a fresh isolated instance with unique secrets, HTTPS and only approved public ports
Priority: P0
Estimate: 4h
Source: Release backlog REL-003, task 1. Provision a fresh isolated instance with unique secrets, HTTPS and only approved public ports.
Implement this bounded change under “Run and sign the full first-customer release drill”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete by final go/no-go so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Provision a fresh isolated instance with unique secrets, HTTPS and only approved public ports
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every P0/P1 criterion has recorded evidence and an owner; any failed P0 keeps the decision at no-go.

#### Task: Exercise every role plus a non-member through the UI and direct API requests
Priority: P0
Estimate: 6h
Source: Release backlog REL-003, task 2. Exercise every role plus a non-member through the UI and direct API requests.
Implement this bounded change under “Run and sign the full first-customer release drill”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete by final go/no-go so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Exercise every role plus a non-member through the UI and direct API requests
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Every P0/P1 criterion has recorded evidence and an owner; any failed P0 keeps the decision at no-go.

#### Task: Upload/process a representative mixed dataset and verify graph, timeline, map, table, financial, Cellebrite, workspace, AI and promised exports
Priority: P0
Estimate: 6h
Source: Release backlog REL-003, task 3. Upload/process a representative mixed dataset and verify graph, timeline, map, table, financial, Cellebrite, workspace, AI and promised exports.
Implement this bounded change under “Run and sign the full first-customer release drill”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete by final go/no-go so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Upload/process a representative mixed dataset and verify graph, timeline, map, table, financial, Cellebrite, workspace, AI and promised exports
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every P0/P1 criterion has recorded evidence and an owner; any failed P0 keeps the decision at no-go.

#### Task: Run backup/clean restore, a normal update and a simulated failed update with rollback or restore
Priority: P0
Estimate: 12h
Source: Release backlog REL-003, task 4. Run backup/clean restore, a normal update and a simulated failed update with rollback or restore.
Implement this bounded change under “Run and sign the full first-customer release drill”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete by final go/no-go so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Run backup/clean restore, a normal update and a simulated failed update with rollback or restore
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Every P0/P1 criterion has recorded evidence and an owner; any failed P0 keeps the decision at no-go.

#### Task: Simulate worker/provider failure, low disk, expired session and unauthorised case access; confirm alerts and runbooks
Priority: P0
Estimate: 8h
Source: Release backlog REL-003, task 5. Simulate worker/provider failure, low disk, expired session and unauthorised case access; confirm alerts and runbooks.
Implement this bounded change under “Run and sign the full first-customer release drill”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete by final go/no-go so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Simulate worker/provider failure, low disk, expired session and unauthorised case access; confirm alerts and runbooks
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every P0/P1 criterion has recorded evidence and an owner; any failed P0 keeps the decision at no-go.

#### Task: Attach evidence and obtain named product, security and operations sign-off
Priority: P0
Estimate: 6h
Source: Release backlog REL-003, task 6. Attach evidence and obtain named product, security and operations sign-off.
Implement this bounded change under “Run and sign the full first-customer release drill”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete by final go/no-go so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Attach evidence and obtain named product, security and operations sign-off
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every P0/P1 criterion has recorded evidence and an owner; any failed P0 keeps the decision at no-go.

### Story: Authenticate and internalise the Evidence Engine
Priority: P0
Source: Release backlog SEC-001 (repository and product audit, 16 July 2026). The ingestion API currently registers upload, file, job, merge, Cellebrite and WebSocket routes without authentication and is host-published.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- No external caller can reach the engine directly; an authenticated non-member cannot operate on another case through the backend.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Remove public host exposure and place the API/worker/datastores on a private network
Priority: P0
Estimate: 8h
Source: Release backlog SEC-001, task 1. Remove public host exposure and place the API/worker/datastores on a private network.
Implement this bounded change under “Authenticate and internalise the Evidence Engine”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove public host exposure and place the API/worker/datastores on a private network
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- No external caller can reach the engine directly; an authenticated non-member cannot operate on another case through the backend.

#### Task: Add a per-instance backend-to-engine service identity using signed short-lived credentials or equivalent mutual authentication
Priority: P0
Estimate: 8h
Source: Release backlog SEC-001, task 2. Add a per-instance backend-to-engine service identity using signed short-lived credentials or equivalent mutual authentication.
Implement this bounded change under “Authenticate and internalise the Evidence Engine”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add a per-instance backend-to-engine service identity using signed short-lived credentials or equivalent mutual authentication
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- No external caller can reach the engine directly; an authenticated non-member cannot operate on another case through the backend.

#### Task: Reject missing, expired, replayed and wrong-instance credentials on HTTP and WebSocket routes
Priority: P0
Estimate: 8h
Source: Release backlog SEC-001, task 3. Reject missing, expired, replayed and wrong-instance credentials on HTTP and WebSocket routes.
Implement this bounded change under “Authenticate and internalise the Evidence Engine”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Reject missing, expired, replayed and wrong-instance credentials on HTTP and WebSocket routes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- No external caller can reach the engine directly; an authenticated non-member cannot operate on another case through the backend.

#### Task: Authorise the user and case in the main backend before forwarding every upload, job, file, merge or delete action
Priority: P0
Estimate: 8h
Source: Release backlog SEC-001, task 4. Authorise the user and case in the main backend before forwarding every upload, job, file, merge or delete action.
Implement this bounded change under “Authenticate and internalise the Evidence Engine”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Authorise the user and case in the main backend before forwarding every upload, job, file, merge or delete action
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- No external caller can reach the engine directly; an authenticated non-member cannot operate on another case through the backend.

#### Task: Add request, file, concurrency and cost limits plus negative integration tests
Priority: P0
Estimate: 8h
Source: Release backlog SEC-001, task 5. Add request, file, concurrency and cost limits plus negative integration tests.
Implement this bounded change under “Authenticate and internalise the Evidence Engine”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add request, file, concurrency and cost limits plus negative integration tests
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- No external caller can reach the engine directly; an authenticated non-member cannot operate on another case through the backend.

### Story: Enforce authentication and object-level authorisation across every API
Priority: P0
Source: Release backlog SEC-002 (repository and product audit, 16 July 2026). Apply one auditable permission contract to all route families and remove unauthenticated or caller-trusted case access.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The permission matrix and automated tests prove that non-members cannot read, viewers cannot mutate, and ordinary users cannot run instance-wide operations.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Make authentication the application/router default and explicitly exempt only health, login and a locked provisioning flow
Priority: P0
Estimate: 8h
Source: Release backlog SEC-002, task 1. Make authentication the application/router default and explicitly exempt only health, login and a locked provisioning flow.
Implement this bounded change under “Enforce authentication and object-level authorisation across every API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make authentication the application/router default and explicitly exempt only health, login and a locked provisioning flow
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The permission matrix and automated tests prove that non-members cannot read, viewers cannot mutate, and ordinary users cannot run instance-wide operations.

#### Task: Inventory every route and WebSocket by resource, action and required case/global permission
Priority: P0
Estimate: 16h
Source: Release backlog SEC-002, task 2. Inventory every route and WebSocket by resource, action and required case/global permission.
Implement this bounded change under “Enforce authentication and object-level authorisation across every API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Inventory every route and WebSocket by resource, action and required case/global permission
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The permission matrix and automated tests prove that non-members cannot read, viewers cannot mutate, and ordinary users cannot run instance-wide operations.

#### Task: Close public user list/detail and profile-management reads; add membership checks to Graph, Financial, Filesystem, Evidence, Timeline, Map,…
Priority: P0
Estimate: 8h
Source: Release backlog SEC-002, task 3. Close public user list/detail and profile-management reads; add membership checks to Graph, Financial, Filesystem, Evidence, Timeline, Map, Workspace, Chat, Agent, exports and snapshots.
Implement this bounded change under “Enforce authentication and object-level authorisation across every API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Close public user list/detail and profile-management reads; add membership checks to Graph, Financial, Filesystem, Evidence, Timeline, Map, Workspace, Chat, Agent, exports and snapshots
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The permission matrix and automated tests prove that non-members cannot read, viewers cannot mutate, and ordinary users cannot run instance-wide operations.

#### Task: Restrict maintenance, backfill, logs, model config, direct query and platform operations to the least privileged admin role
Priority: P0
Estimate: 8h
Source: Release backlog SEC-002, task 4. Restrict maintenance, backfill, logs, model config, direct query and platform operations to the least privileged admin role.
Implement this bounded change under “Enforce authentication and object-level authorisation across every API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Restrict maintenance, backfill, logs, model config, direct query and platform operations to the least privileged admin role
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The permission matrix and automated tests prove that non-members cannot read, viewers cannot mutate, and ordinary users cannot run instance-wide operations.

#### Task: Add owner/editor/viewer/guest/non-member/admin/super-admin negative tests for every route family
Priority: P0
Estimate: 16h
Source: Release backlog SEC-002, task 5. Add owner/editor/viewer/guest/non-member/admin/super-admin negative tests for every route family.
Implement this bounded change under “Enforce authentication and object-level authorisation across every API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add owner/editor/viewer/guest/non-member/admin/super-admin negative tests for every route family
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The permission matrix and automated tests prove that non-members cannot read, viewers cannot mutate, and ordinary users cannot run instance-wide operations.

### Story: Eliminate shared defaults and public datastore ports
Priority: P0
Source: Release backlog SEC-003 (repository and product audit, 16 July 2026). Neo4j, Postgres, Redis, Chroma and ingestion are host-published with development/default credentials.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A network scan exposes only approved services and secret validation prevents an instance starting with repository-known credentials.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Remove production host mappings for internal services; bind diagnostics to loopback only
Priority: P0
Estimate: 4h
Source: Release backlog SEC-003, task 1. Remove production host mappings for internal services; bind diagnostics to loopback only.
Implement this bounded change under “Eliminate shared defaults and public datastore ports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove production host mappings for internal services; bind diagnostics to loopback only
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- A network scan exposes only approved services and secret validation prevents an instance starting with repository-known credentials.

#### Task: Generate unique database, Redis/Chroma, service, JWT and bootstrap credentials per instance
Priority: P0
Estimate: 8h
Source: Release backlog SEC-003, task 2. Generate unique database, Redis/Chroma, service, JWT and bootstrap credentials per instance.
Implement this bounded change under “Eliminate shared defaults and public datastore ports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Generate unique database, Redis/Chroma, service, JWT and bootstrap credentials per instance
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A network scan exposes only approved services and secret validation prevents an instance starting with repository-known credentials.

#### Task: Make production startup fail closed when a required secret is absent, weak or equal to a known development value
Priority: P0
Estimate: 8h
Source: Release backlog SEC-003, task 3. Make production startup fail closed when a required secret is absent, weak or equal to a known development value.
Implement this bounded change under “Eliminate shared defaults and public datastore ports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make production startup fail closed when a required secret is absent, weak or equal to a known development value
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A network scan exposes only approved services and secret validation prevents an instance starting with repository-known credentials.

#### Task: Move secrets to an approved secret store and document rotation/emergency revocation
Priority: P0
Estimate: 8h
Source: Release backlog SEC-003, task 4. Move secrets to an approved secret store and document rotation/emergency revocation.
Implement this bounded change under “Eliminate shared defaults and public datastore ports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Move secrets to an approved secret store and document rotation/emergency revocation
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A network scan exposes only approved services and secret validation prevents an instance starting with repository-known credentials.

#### Task: Rotate any credential or signing key that has existed in repository/development configuration
Priority: P0
Estimate: 8h
Source: Release backlog SEC-003, task 5. Rotate any credential or signing key that has existed in repository/development configuration.
Implement this bounded change under “Eliminate shared defaults and public datastore ports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Rotate any credential or signing key that has existed in repository/development configuration
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A network scan exposes only approved services and secret validation prevents an instance starting with repository-known credentials.

### Story: Harden sessions, cookies and login
Priority: P0
Source: Release backlog SEC-004 (repository and product audit, 16 July 2026). Remove token theft and long-lived session paths and make account changes take effect immediately.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Stolen frontend JavaScript cannot read the session token; revoked/deactivated users lose access immediately; brute-force controls are tested.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Use Secure, HttpOnly, SameSite cookies as the browser credential and remove localStorage bearer tokens
Priority: P0
Estimate: 4h
Source: Release backlog SEC-004, task 1. Use Secure, HttpOnly, SameSite cookies as the browser credential and remove localStorage bearer tokens.
Implement this bounded change under “Harden sessions, cookies and login”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Use Secure, HttpOnly, SameSite cookies as the browser credential and remove localStorage bearer tokens
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stolen frontend JavaScript cannot read the session token; revoked/deactivated users lose access immediately; brute-force controls are tested.

#### Task: Add CSRF protection for cookie-authenticated state changes and a strict origin/CORS policy
Priority: P0
Estimate: 8h
Source: Release backlog SEC-004, task 2. Add CSRF protection for cookie-authenticated state changes and a strict origin/CORS policy.
Implement this bounded change under “Harden sessions, cookies and login”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add CSRF protection for cookie-authenticated state changes and a strict origin/CORS policy
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stolen frontend JavaScript cannot read the session token; revoked/deactivated users lose access immediately; brute-force controls are tested.

#### Task: Shorten idle/absolute session life; add server-side session IDs, revocation and device/session listing
Priority: P0
Estimate: 12h
Source: Release backlog SEC-004, task 3. Shorten idle/absolute session life; add server-side session IDs, revocation and device/session listing.
Implement this bounded change under “Harden sessions, cookies and login”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Shorten idle/absolute session life; add server-side session IDs, revocation and device/session listing
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stolen frontend JavaScript cannot read the session token; revoked/deactivated users lose access immediately; brute-force controls are tested.

#### Task: Revalidate active user and current role on protected requests; revoke sessions after password, role or account-state changes
Priority: P0
Estimate: 8h
Source: Release backlog SEC-004, task 4. Revalidate active user and current role on protected requests; revoke sessions after password, role or account-state changes.
Implement this bounded change under “Harden sessions, cookies and login”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Revalidate active user and current role on protected requests; revoke sessions after password, role or account-state changes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stolen frontend JavaScript cannot read the session token; revoked/deactivated users lose access immediately; brute-force controls are tested.

#### Task: Rate-limit login and recovery, audit failures, prevent user enumeration and add safe lockout/backoff
Priority: P0
Estimate: 8h
Source: Release backlog SEC-004, task 5. Rate-limit login and recovery, audit failures, prevent user enumeration and add safe lockout/backoff.
Implement this bounded change under “Harden sessions, cookies and login”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Rate-limit login and recovery, audit failures, prevent user enumeration and add safe lockout/backoff
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stolen frontend JavaScript cannot read the session token; revoked/deactivated users lose access immediately; brute-force controls are tested.

### Story: Deliver MFA and safe account recovery
Priority: P1
Source: Release backlog SEC-005 (repository and product audit, 16 July 2026). Admins need recoverable accounts without weak manual database edits or an unsafe ‘reset password’ shortcut.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Admin recovery does not reveal or set a reusable password, MFA cannot be bypassed, and all resets/recovery actions are auditable.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Require TOTP/WebAuthn MFA for admin and super-admin roles; decide policy for investigators
Priority: P1
Estimate: 4h
Source: Release backlog SEC-005, task 1. Require TOTP/WebAuthn MFA for admin and super-admin roles; decide policy for investigators.
Implement this bounded change under “Deliver MFA and safe account recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Require TOTP/WebAuthn MFA for admin and super-admin roles; decide policy for investigators
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admin recovery does not reveal or set a reusable password, MFA cannot be bypassed, and all resets/recovery actions are auditable.

#### Task: Implement self-service recovery with short-lived single-use tokens, generic responses and full audit events
Priority: P1
Estimate: 12h
Source: Release backlog SEC-005, task 2. Implement self-service recovery with short-lived single-use tokens, generic responses and full audit events.
Implement this bounded change under “Deliver MFA and safe account recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Implement self-service recovery with short-lived single-use tokens, generic responses and full audit events
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admin recovery does not reveal or set a reusable password, MFA cannot be bypassed, and all resets/recovery actions are auditable.

#### Task: Add an admin reset flow that creates a temporary credential or reset invitation, forces password change and revokes existing sessions
Priority: P1
Estimate: 8h
Source: Release backlog SEC-005, task 3. Add an admin reset flow that creates a temporary credential or reset invitation, forces password change and revokes existing sessions.
Implement this bounded change under “Deliver MFA and safe account recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add an admin reset flow that creates a temporary credential or reset invitation, forces password change and revokes existing sessions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admin recovery does not reveal or set a reusable password, MFA cannot be bypassed, and all resets/recovery actions are auditable.

#### Task: Enforce a stronger password policy and breached/common-password checks appropriate to the deployment
Priority: P1
Estimate: 8h
Source: Release backlog SEC-005, task 4. Enforce a stronger password policy and breached/common-password checks appropriate to the deployment.
Implement this bounded change under “Deliver MFA and safe account recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Enforce a stronger password policy and breached/common-password checks appropriate to the deployment
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admin recovery does not reveal or set a reusable password, MFA cannot be bypassed, and all resets/recovery actions are auditable.

#### Task: Issue recovery codes and document a two-person lost-admin procedure
Priority: P1
Estimate: 4h
Source: Release backlog SEC-005, task 5. Issue recovery codes and document a two-person lost-admin procedure.
Implement this bounded change under “Deliver MFA and safe account recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Issue recovery codes and document a two-person lost-admin procedure
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admin recovery does not reveal or set a reusable password, MFA cannot be bypassed, and all resets/recovery actions are auditable.

### Story: Guard administration in both UI and API
Priority: P0
Source: Release backlog SEC-006 (repository and product audit, 16 July 2026). Hidden navigation is not authorisation; direct admin URLs must fail safely for non-admins.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Non-admin users receive a consistent 403/redirect and cannot cause admin-side effects through direct requests.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add an admin route guard with explicit loading, forbidden and session-expired states
Priority: P0
Estimate: 8h
Source: Release backlog SEC-006, task 1. Add an admin route guard with explicit loading, forbidden and session-expired states.
Implement this bounded change under “Guard administration in both UI and API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add an admin route guard with explicit loading, forbidden and session-expired states
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Non-admin users receive a consistent 403/redirect and cannot cause admin-side effects through direct requests.

#### Task: Keep admin navigation role-aware but never rely on visibility for protection
Priority: P0
Estimate: 8h
Source: Release backlog SEC-006, task 2. Keep admin navigation role-aware but never rely on visibility for protection.
Implement this bounded change under “Guard administration in both UI and API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep admin navigation role-aware but never rely on visibility for protection
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Non-admin users receive a consistent 403/redirect and cannot cause admin-side effects through direct requests.

#### Task: Use one backend admin dependency for user, logs, costs, profiles, tasks, updates and maintenance operations
Priority: P0
Estimate: 6h
Source: Release backlog SEC-006, task 3. Use one backend admin dependency for user, logs, costs, profiles, tasks, updates and maintenance operations.
Implement this bounded change under “Guard administration in both UI and API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Use one backend admin dependency for user, logs, costs, profiles, tasks, updates and maintenance operations
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Non-admin users receive a consistent 403/redirect and cannot cause admin-side effects through direct requests.

#### Task: Prevent admins changing super-admins and protect the last active super-admin and last viable case owner
Priority: P0
Estimate: 8h
Source: Release backlog SEC-006, task 4. Prevent admins changing super-admins and protect the last active super-admin and last viable case owner.
Implement this bounded change under “Guard administration in both UI and API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prevent admins changing super-admins and protect the last active super-admin and last viable case owner
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Non-admin users receive a consistent 403/redirect and cannot cause admin-side effects through direct requests.

#### Task: Add browser tests for direct URL entry and direct API calls by every role
Priority: P0
Estimate: 8h
Source: Release backlog SEC-006, task 5. Add browser tests for direct URL entry and direct API calls by every role.
Implement this bounded change under “Guard administration in both UI and API”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add browser tests for direct URL entry and direct API calls by every role
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Non-admin users receive a consistent 403/redirect and cannot cause admin-side effects through direct requests.

### Story: Archive/deactivate users safely
Priority: P1
Source: Release backlog ADM-001 (repository and product audit, 16 July 2026). Provide a reversible account lifecycle that preserves attribution and does not silently orphan cases.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Admins can safely remove access and later restore it without losing attribution or weakening owner/admin guarantees.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add active/archived filtering and a clearly named Deactivate/Reactivate action to User Management
Priority: P1
Estimate: 8h
Source: Release backlog ADM-001, task 1. Add active/archived filtering and a clearly named Deactivate/Reactivate action to User Management.
Implement this bounded change under “Archive/deactivate users safely”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add active/archived filtering and a clearly named Deactivate/Reactivate action to User Management
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admins can safely remove access and later restore it without losing attribution or weakening owner/admin guarantees.

#### Task: Show affected case ownership/memberships before deactivation and block orphaning the last owner or administrator
Priority: P1
Estimate: 8h
Source: Release backlog ADM-001, task 2. Show affected case ownership/memberships before deactivation and block orphaning the last owner or administrator.
Implement this bounded change under “Archive/deactivate users safely”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show affected case ownership/memberships before deactivation and block orphaning the last owner or administrator
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admins can safely remove access and later restore it without losing attribution or weakening owner/admin guarantees.

#### Task: Revoke all sessions and prevent login immediately when deactivated
Priority: P1
Estimate: 8h
Source: Release backlog ADM-001, task 3. Revoke all sessions and prevent login immediately when deactivated.
Implement this bounded change under “Archive/deactivate users safely”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Revoke all sessions and prevent login immediately when deactivated
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admins can safely remove access and later restore it without losing attribution or weakening owner/admin guarantees.

#### Task: Preserve historical authorship and audit records; never hard-delete referenced users
Priority: P1
Estimate: 6h
Source: Release backlog ADM-001, task 4. Preserve historical authorship and audit records; never hard-delete referenced users.
Implement this bounded change under “Archive/deactivate users safely”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Preserve historical authorship and audit records; never hard-delete referenced users
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Admins can safely remove access and later restore it without losing attribution or weakening owner/admin guarantees.

#### Task: Audit actor, target, reason and result; test self/last-admin protections
Priority: P1
Estimate: 8h
Source: Release backlog ADM-001, task 5. Audit actor, target, reason and result; test self/last-admin protections.
Implement this bounded change under “Archive/deactivate users safely”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Audit actor, target, reason and result; test self/last-admin protections
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Admins can safely remove access and later restore it without losing attribution or weakening owner/admin guarantees.

### Story: Add an administrator-initiated password recovery flow
Priority: P1
Source: Release backlog ADM-002 (repository and product audit, 16 July 2026). Replace direct password setting with a secure reset workflow integrated with session revocation and audit.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The admin never learns the user’s final password, old sessions stop working, and every reset is traceable.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add Reset access in User Management with confirmation and reason
Priority: P1
Estimate: 8h
Source: Release backlog ADM-002, task 1. Add Reset access in User Management with confirmation and reason.
Implement this bounded change under “Add an administrator-initiated password recovery flow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add Reset access in User Management with confirmation and reason
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The admin never learns the user’s final password, old sessions stop working, and every reset is traceable.

#### Task: Issue a short-lived one-time reset invitation or temporary credential and force change at next sign-in
Priority: P1
Estimate: 4h
Source: Release backlog ADM-002, task 2. Issue a short-lived one-time reset invitation or temporary credential and force change at next sign-in.
Implement this bounded change under “Add an administrator-initiated password recovery flow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Issue a short-lived one-time reset invitation or temporary credential and force change at next sign-in
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The admin never learns the user’s final password, old sessions stop working, and every reset is traceable.

#### Task: Revoke the target’s current sessions and notify them through the approved channel
Priority: P1
Estimate: 4h
Source: Release backlog ADM-002, task 3. Revoke the target’s current sessions and notify them through the approved channel.
Implement this bounded change under “Add an administrator-initiated password recovery flow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Revoke the target’s current sessions and notify them through the approved channel
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The admin never learns the user’s final password, old sessions stop working, and every reset is traceable.

#### Task: Prevent lower admins resetting super-admins; rate-limit and audit every attempt
Priority: P1
Estimate: 8h
Source: Release backlog ADM-002, task 4. Prevent lower admins resetting super-admins; rate-limit and audit every attempt.
Implement this bounded change under “Add an administrator-initiated password recovery flow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prevent lower admins resetting super-admins; rate-limit and audit every attempt
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The admin never learns the user’s final password, old sessions stop working, and every reset is traceable.

#### Task: Test expired, reused, cancelled and wrong-user reset tokens
Priority: P1
Estimate: 6h
Source: Release backlog ADM-002, task 5. Test expired, reused, cancelled and wrong-user reset tokens.
Implement this bounded change under “Add an administrator-initiated password recovery flow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test expired, reused, cancelled and wrong-user reset tokens
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The admin never learns the user’s final password, old sessions stop working, and every reset is traceable.

### Story: Finish and regression-test the case archive lifecycle
Priority: P1
Source: Release backlog CASE-001 (repository and product audit, 16 July 2026). Archiving should declutter active work without looking like deletion or breaking deep links and permissions.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A completed case can be archived and restored without data loss, permission drift or confusion with permanent deletion.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Default lists/search to active cases and provide an explicit archived view with clear status treatment
Priority: P1
Estimate: 4h
Source: Release backlog CASE-001, task 1. Default lists/search to active cases and provide an explicit archived view with clear status treatment.
Implement this bounded change under “Finish and regression-test the case archive lifecycle”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Default lists/search to active cases and provide an explicit archived view with clear status treatment
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A completed case can be archived and restored without data loss, permission drift or confusion with permanent deletion.

#### Task: Confirm archive/unarchive is permission-checked, audited and preserves evidence, jobs, chats, exports and links
Priority: P1
Estimate: 6h
Source: Release backlog CASE-001, task 2. Confirm archive/unarchive is permission-checked, audited and preserves evidence, jobs, chats, exports and links.
Implement this bounded change under “Finish and regression-test the case archive lifecycle”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Confirm archive/unarchive is permission-checked, audited and preserves evidence, jobs, chats, exports and links
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A completed case can be archived and restored without data loss, permission drift or confusion with permanent deletion.

#### Task: Block or clearly handle new mutations and background jobs on archived cases
Priority: P1
Estimate: 8h
Source: Release backlog CASE-001, task 3. Block or clearly handle new mutations and background jobs on archived cases.
Implement this bounded change under “Finish and regression-test the case archive lifecycle”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Block or clearly handle new mutations and background jobs on archived cases
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A completed case can be archived and restored without data loss, permission drift or confusion with permanent deletion.

#### Task: Test direct links, super-admin all-cases view, restore and concurrent users
Priority: P1
Estimate: 12h
Source: Release backlog CASE-001, task 4. Test direct links, super-admin all-cases view, restore and concurrent users.
Implement this bounded change under “Finish and regression-test the case archive lifecycle”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test direct links, super-admin all-cases view, restore and concurrent users
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A completed case can be archived and restored without data loss, permission drift or confusion with permanent deletion.

### Story: Implement Case Settings or remove the route
Priority: P1
Source: Release backlog CASE-002 (repository and product audit, 16 July 2026). The visible settings route promises member, metadata, version and danger-zone management but currently contains no functionality.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Every visible Case Settings control is persisted, authorised, audited and covered by browser tests—or the route is absent.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Implement case title/description/status metadata editing with validation and audit
Priority: P1
Estimate: 12h
Source: Release backlog CASE-002, task 1. Implement case title/description/status metadata editing with validation and audit.
Implement this bounded change under “Implement Case Settings or remove the route”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Implement case title/description/status metadata editing with validation and audit
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible Case Settings control is persisted, authorised, audited and covered by browser tests—or the route is absent.

#### Task: Integrate collaborator roles/permissions and explicit owner transfer
Priority: P1
Estimate: 8h
Source: Release backlog CASE-002, task 2. Integrate collaborator roles/permissions and explicit owner transfer.
Implement this bounded change under “Implement Case Settings or remove the route”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Integrate collaborator roles/permissions and explicit owner transfer
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible Case Settings control is persisted, authorised, audited and covered by browser tests—or the route is absent.

#### Task: Show processing profile/version state and safe reprocessing implications
Priority: P1
Estimate: 6h
Source: Release backlog CASE-002, task 3. Show processing profile/version state and safe reprocessing implications.
Implement this bounded change under “Implement Case Settings or remove the route”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show processing profile/version state and safe reprocessing implications
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible Case Settings control is persisted, authorised, audited and covered by browser tests—or the route is absent.

#### Task: Create a danger zone for archive, export and delete with typed confirmation and permission checks
Priority: P1
Estimate: 8h
Source: Release backlog CASE-002, task 4. Create a danger zone for archive, export and delete with typed confirmation and permission checks.
Implement this bounded change under “Implement Case Settings or remove the route”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create a danger zone for archive, export and delete with typed confirmation and permission checks
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible Case Settings control is persisted, authorised, audited and covered by browser tests—or the route is absent.

#### Task: If scope excludes these controls, remove the route and relocate essential actions
Priority: P1
Estimate: 8h
Source: Release backlog CASE-002, task 5. If scope excludes these controls, remove the route and relocate essential actions.
Implement this bounded change under “Implement Case Settings or remove the route”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: If scope excludes these controls, remove the route and relocate essential actions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible Case Settings control is persisted, authorised, audited and covered by browser tests—or the route is absent.

### Story: Harden collaboration and ownership invariants
Priority: P0
Source: Release backlog CASE-003 (repository and product audit, 16 July 2026). Make invitations, permission changes and owner transitions safe across the whole case.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Membership changes cannot orphan a case, silently broaden access or remain effective after revocation.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Document owner/editor/viewer/guest capability presets and custom-permission semantics
Priority: P0
Estimate: 4h
Source: Release backlog CASE-003, task 1. Document owner/editor/viewer/guest capability presets and custom-permission semantics.
Implement this bounded change under “Harden collaboration and ownership invariants”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Document owner/editor/viewer/guest capability presets and custom-permission semantics
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Membership changes cannot orphan a case, silently broaden access or remain effective after revocation.

#### Task: Prevent removal, deactivation or transfer that leaves no viable owner; require explicit owner handover
Priority: P0
Estimate: 8h
Source: Release backlog CASE-003, task 2. Prevent removal, deactivation or transfer that leaves no viable owner; require explicit owner handover.
Implement this bounded change under “Harden collaboration and ownership invariants”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prevent removal, deactivation or transfer that leaves no viable owner; require explicit owner handover
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Membership changes cannot orphan a case, silently broaden access or remain effective after revocation.

#### Task: Make super-admin support access policy explicit and visible/audited to the customer
Priority: P0
Estimate: 8h
Source: Release backlog CASE-003, task 3. Make super-admin support access policy explicit and visible/audited to the customer.
Implement this bounded change under “Harden collaboration and ownership invariants”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make super-admin support access policy explicit and visible/audited to the customer
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Membership changes cannot orphan a case, silently broaden access or remain effective after revocation.

#### Task: Audit invitation, acceptance, role change, removal and support access
Priority: P0
Estimate: 8h
Source: Release backlog CASE-003, task 4. Audit invitation, acceptance, role change, removal and support access.
Implement this bounded change under “Harden collaboration and ownership invariants”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Audit invitation, acceptance, role change, removal and support access
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Membership changes cannot orphan a case, silently broaden access or remain effective after revocation.

#### Task: Test simultaneous permission edits and stale UI permissions
Priority: P0
Estimate: 6h
Source: Release backlog CASE-003, task 5. Test simultaneous permission edits and stale UI permissions.
Implement this bounded change under “Harden collaboration and ownership invariants”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test simultaneous permission edits and stale UI permissions
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Membership changes cannot orphan a case, silently broaden access or remain effective after revocation.

### Story: Stabilise deadlines and investigation snapshots
Priority: P1
Source: Release backlog CASE-004 (repository and product audit, 16 July 2026). Saved snapshots are part of the investigation workflow and must not freeze, disappear or cross cases.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Representative large snapshots and deadlines persist, reload and remain case-scoped without UI freezes or timeouts.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Reproduce snapshot save timeout/crash and missing-list reports against current Postgres-backed storage
Priority: P1
Estimate: 6h
Source: Release backlog CASE-004, task 1. Reproduce snapshot save timeout/crash and missing-list reports against current Postgres-backed storage.
Implement this bounded change under “Stabilise deadlines and investigation snapshots”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Reproduce snapshot save timeout/crash and missing-list reports against current Postgres-backed storage
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Representative large snapshots and deadlines persist, reload and remain case-scoped without UI freezes or timeouts.

#### Task: Add bounded payloads, progress, cancellation and clear failure recovery for large snapshots
Priority: P1
Estimate: 8h
Source: Release backlog CASE-004, task 2. Add bounded payloads, progress, cancellation and clear failure recovery for large snapshots.
Implement this bounded change under “Stabilise deadlines and investigation snapshots”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add bounded payloads, progress, cancellation and clear failure recovery for large snapshots
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Representative large snapshots and deadlines persist, reload and remain case-scoped without UI freezes or timeouts.

#### Task: Verify case scoping, membership, restore semantics and concurrent saves
Priority: P1
Estimate: 12h
Source: Release backlog CASE-004, task 3. Verify case scoping, membership, restore semantics and concurrent saves.
Implement this bounded change under “Stabilise deadlines and investigation snapshots”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify case scoping, membership, restore semantics and concurrent saves
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Representative large snapshots and deadlines persist, reload and remain case-scoped without UI freezes or timeouts.

#### Task: Test deadlines for timezone/date edges, permissions, reminders and archived cases
Priority: P1
Estimate: 6h
Source: Release backlog CASE-004, task 4. Test deadlines for timezone/date edges, permissions, reminders and archived cases.
Implement this bounded change under “Stabilise deadlines and investigation snapshots”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test deadlines for timezone/date edges, permissions, reminders and archived cases
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Representative large snapshots and deadlines persist, reload and remain case-scoped without UI freezes or timeouts.

#### Task: Add end-to-end save, list, open, export, delete and restore coverage
Priority: P1
Estimate: 12h
Source: Release backlog CASE-004, task 5. Add end-to-end save, list, open, export, delete and restore coverage.
Implement this bounded change under “Stabilise deadlines and investigation snapshots”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add end-to-end save, list, open, export, delete and restore coverage
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Representative large snapshots and deadlines persist, reload and remain case-scoped without UI freezes or timeouts.

### Bug: Remove unauthenticated write-Cypher execute endpoints
Priority: P0
Estimate: 4h
`POST /api/graph/execute-single-query` and `/execute-batch-queries` accept arbitrary write Cypher without authentication (V2 Gap Assessment §5, BRG-001). Delete these dead endpoints or, only if a verified internal caller remains, require authentication and reject every write clause. This is alpha-blocking because the current behavior permits direct evidence tampering.

Acceptance criteria:
- Both endpoints are absent from the router and OpenAPI schema, or return 401 without a token and reject every write attempt.
- Case-version loading completes end to end after the endpoints are retired or constrained.
- Direct integration tests prove an authenticated non-member cannot query or mutate another case.

### Bug: Require authentication and case membership on `/api/graph/locations`
Priority: P0
Estimate: 3h
The locations endpoint currently returns an arbitrary case’s points without a token (V2 Gap Assessment §5, BRG-002). Apply the standard authentication dependency and an object-level case-membership check without changing the authorised payload. This is alpha-blocking because location evidence is case-confidential.

Acceptance criteria:
- A request without a token returns 401.
- An authenticated non-member request returns 403 without location data.
- A permitted case member receives the same complete location payload as before.

### Bug: Require admin authentication on processing-profile CRUD
Priority: P0
Estimate: 3h
Processing-profile create, update and delete operations lack the required authentication dependency (V2 Gap Assessment §7 item 42, BRG-009). Apply the shared backend admin guard and keep read visibility aligned with the approved role matrix. This is alpha-blocking because processing profiles control how customer evidence is transformed.

Acceptance criteria:
- Unauthenticated create, update and delete requests return 401.
- Authenticated non-admin mutation requests return 403.
- An authorised admin can create, update and delete a profile, and each mutation produces an audit event.

## Epic: Evidence Intake & Ingestion Integrity
Color: #d18a18
Make uploads resumable and bounded, preserve immutable source provenance, and ensure every supported format either ingests completely or fails with an actionable and recoverable state.

### Story: Spike an ingestion agent against the deterministic pipeline
Priority: P1
Source: Release backlog ING-001 (repository and product audit, 16 July 2026). Evaluate whether a bounded agent materially improves entity deduplication and contextual linking without weakening reproducibility, cost or security.
Release gate: Before architecture freeze. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The decision is based on measured quality and safety, not intuition; any implementation remains replayable, idempotent and human-reviewable.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Define a benchmark corpus with aliases, ambiguous entities, conflicting facts, repeat uploads and cross-document relationships
Priority: P1
Estimate: 6h
Source: Release backlog ING-001, task 1. Define a benchmark corpus with aliases, ambiguous entities, conflicting facts, repeat uploads and cross-document relationships.
Implement this bounded change under “Spike an ingestion agent against the deterministic pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before architecture freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define a benchmark corpus with aliases, ambiguous entities, conflicting facts, repeat uploads and cross-document relationships
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The decision is based on measured quality and safety, not intuition; any implementation remains replayable, idempotent and human-reviewable.

#### Task: Specify an allowlisted read-only tool set, maximum steps/runtime/spend, case isolation and immutable execution trace
Priority: P1
Estimate: 8h
Source: Release backlog ING-001, task 2. Specify an allowlisted read-only tool set, maximum steps/runtime/spend, case isolation and immutable execution trace.
Implement this bounded change under “Spike an ingestion agent against the deterministic pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before architecture freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Specify an allowlisted read-only tool set, maximum steps/runtime/spend, case isolation and immutable execution trace
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The decision is based on measured quality and safety, not intuition; any implementation remains replayable, idempotent and human-reviewable.

#### Task: Compare precision, recall, duplicate rate, relationship quality, cost and latency against the current blocking/embedding/LLM pipeline
Priority: P1
Estimate: 8h
Source: Release backlog ING-001, task 3. Compare precision, recall, duplicate rate, relationship quality, cost and latency against the current blocking/embedding/LLM pipeline.
Implement this bounded change under “Spike an ingestion agent against the deterministic pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before architecture freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Compare precision, recall, duplicate rate, relationship quality, cost and latency against the current blocking/embedding/LLM pipeline
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The decision is based on measured quality and safety, not intuition; any implementation remains replayable, idempotent and human-reviewable.

#### Task: Threat-test prompt injection, cross-case key guessing, tool loops and malicious document text
Priority: P1
Estimate: 12h
Source: Release backlog ING-001, task 4. Threat-test prompt injection, cross-case key guessing, tool loops and malicious document text.
Implement this bounded change under “Spike an ingestion agent against the deterministic pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before architecture freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Threat-test prompt injection, cross-case key guessing, tool loops and malicious document text
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The decision is based on measured quality and safety, not intuition; any implementation remains replayable, idempotent and human-reviewable.

#### Task: Write an architecture decision: implement, restrict to analyst review, or reject; include migration and rollback implications
Priority: P1
Estimate: 12h
Source: Release backlog ING-001, task 5. Write an architecture decision: implement, restrict to analyst review, or reject; include migration and rollback implications.
Implement this bounded change under “Spike an ingestion agent against the deterministic pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before architecture freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Write an architecture decision: implement, restrict to analyst review, or reject; include migration and rollback implications
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The decision is based on measured quality and safety, not intuition; any implementation remains replayable, idempotent and human-reviewable.

### Story: Make provenance and human review first-class
Priority: P0
Source: Release backlog ING-002 (repository and product audit, 16 July 2026). Every extracted or inferred item must retain an exact path back to original material through edits and merges.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- An investigator can open the exact original support for every material graph fact and see who/what last changed it.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Store source file ID/hash, page/chunk/timecode, exact supporting excerpt and extraction run/model for entities, relationships, events, locations…
Priority: P0
Estimate: 8h
Source: Release backlog ING-002, task 1. Store source file ID/hash, page/chunk/timecode, exact supporting excerpt and extraction run/model for entities, relationships, events, locations and transactions.
Implement this bounded change under “Make provenance and human review first-class”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Store source file ID/hash, page/chunk/timecode, exact supporting excerpt and extraction run/model for entities, relationships, events, locations and transactions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can open the exact original support for every material graph fact and see who/what last changed it.

#### Task: Distinguish AI extraction, AI inference, investigator assertion and human-verified fact in data and UI
Priority: P0
Estimate: 8h
Source: Release backlog ING-002, task 2. Distinguish AI extraction, AI inference, investigator assertion and human-verified fact in data and UI.
Implement this bounded change under “Make provenance and human review first-class”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Distinguish AI extraction, AI inference, investigator assertion and human-verified fact in data and UI
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can open the exact original support for every material graph fact and see who/what last changed it.

#### Task: Preserve provenance sets through entity/relationship merge, edit, recycle and restore
Priority: P0
Estimate: 12h
Source: Release backlog ING-002, task 3. Preserve provenance sets through entity/relationship merge, edit, recycle and restore.
Implement this bounded change under “Make provenance and human review first-class”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Preserve provenance sets through entity/relationship merge, edit, recycle and restore
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can open the exact original support for every material graph fact and see who/what last changed it.

#### Task: Expose conflicts and unsupported assertions instead of overwriting or presenting a single false certainty
Priority: P0
Estimate: 8h
Source: Release backlog ING-002, task 4. Expose conflicts and unsupported assertions instead of overwriting or presenting a single false certainty.
Implement this bounded change under “Make provenance and human review first-class”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Expose conflicts and unsupported assertions instead of overwriting or presenting a single false certainty
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can open the exact original support for every material graph fact and see who/what last changed it.

#### Task: Add source-integrity tests across reprocessing and provider/model changes
Priority: P0
Estimate: 8h
Source: Release backlog ING-002, task 5. Add source-integrity tests across reprocessing and provider/model changes.
Implement this bounded change under “Make provenance and human review first-class”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add source-integrity tests across reprocessing and provider/model changes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can open the exact original support for every material graph fact and see who/what last changed it.

### Story: Reject or qualify vague and bad locations during ingestion
Priority: P1
Source: Release backlog ING-003 (repository and product audit, 16 July 2026). Prevent countries, generic regions, organisations and low-confidence geocodes from appearing as exact map points.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Low-quality locations are excluded or visibly approximate; exact pins have a defensible source and precision.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Define accepted location granularity and a reject/needs-review taxonomy
Priority: P1
Estimate: 6h
Source: Release backlog ING-003, task 1. Define accepted location granularity and a reject/needs-review taxonomy.
Implement this bounded change under “Reject or qualify vague and bad locations during ingestion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define accepted location granularity and a reject/needs-review taxonomy
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Low-quality locations are excluded or visibly approximate; exact pins have a defensible source and precision.

#### Task: Validate coordinates, impossible values, zero-island results and entity types before graph write
Priority: P1
Estimate: 6h
Source: Release backlog ING-003, task 2. Validate coordinates, impossible values, zero-island results and entity types before graph write.
Implement this bounded change under “Reject or qualify vague and bad locations during ingestion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Validate coordinates, impossible values, zero-island results and entity types before graph write
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Low-quality locations are excluded or visibly approximate; exact pins have a defensible source and precision.

#### Task: Store geocoder, query, formatted address, precision, confidence and ambiguity candidates
Priority: P1
Estimate: 8h
Source: Release backlog ING-003, task 3. Store geocoder, query, formatted address, precision, confidence and ambiguity candidates.
Implement this bounded change under “Reject or qualify vague and bad locations during ingestion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Store geocoder, query, formatted address, precision, confidence and ambiguity candidates
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Low-quality locations are excluded or visibly approximate; exact pins have a defensible source and precision.

#### Task: Route vague/ambiguous locations to review and allow investigator correction without AI overwrite
Priority: P1
Estimate: 8h
Source: Release backlog ING-003, task 4. Route vague/ambiguous locations to review and allow investigator correction without AI overwrite.
Implement this bounded change under “Reject or qualify vague and bad locations during ingestion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Route vague/ambiguous locations to review and allow investigator correction without AI overwrite
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Low-quality locations are excluded or visibly approximate; exact pins have a defensible source and precision.

#### Task: Build fixtures for invalid addresses, duplicate names, country-only values and no-network/provider failures
Priority: P1
Estimate: 12h
Source: Release backlog ING-003, task 5. Build fixtures for invalid addresses, duplicate names, country-only values and no-network/provider failures.
Implement this bounded change under “Reject or qualify vague and bad locations during ingestion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Build fixtures for invalid addresses, duplicate names, country-only values and no-network/provider failures
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Low-quality locations are excluded or visibly approximate; exact pins have a defensible source and precision.

### Story: Raise extraction and summary quality across supported formats
Priority: P1
Source: Release backlog ING-004 (repository and product audit, 16 July 2026). Define useful outputs for documents, messages, spreadsheets, audio, video and mobile exports instead of relying on generic prompts.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A signed fixture suite meets agreed extraction-quality thresholds and summaries are useful without hiding source uncertainty.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Expand document summaries to cover key facts, entities, dates, amounts, relationships, uncertainties and citations
Priority: P1
Estimate: 4h
Source: Release backlog ING-004, task 1. Expand document summaries to cover key facts, entities, dates, amounts, relationships, uncertainties and citations.
Implement this bounded change under “Raise extraction and summary quality across supported formats”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Expand document summaries to cover key facts, entities, dates, amounts, relationships, uncertainties and citations
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A signed fixture suite meets agreed extraction-quality thresholds and summaries are useful without hiding source uncertainty.

#### Task: Add structured text-message parsing for threads, participants, timestamps, attachments and timezones
Priority: P1
Estimate: 8h
Source: Release backlog ING-004, task 2. Add structured text-message parsing for threads, participants, timestamps, attachments and timezones.
Implement this bounded change under “Raise extraction and summary quality across supported formats”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add structured text-message parsing for threads, participants, timestamps, attachments and timezones
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A signed fixture suite meets agreed extraction-quality thresholds and summaries are useful without hiding source uncertainty.

#### Task: Validate OCR, transcription, spreadsheet tables and video frames on representative fixtures
Priority: P1
Estimate: 6h
Source: Release backlog ING-004, task 3. Validate OCR, transcription, spreadsheet tables and video frames on representative fixtures.
Implement this bounded change under “Raise extraction and summary quality across supported formats”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Validate OCR, transcription, spreadsheet tables and video frames on representative fixtures
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A signed fixture suite meets agreed extraction-quality thresholds and summaries are useful without hiding source uncertainty.

#### Task: Consolidate repetitive facts/insights into readable entity/document views while preserving atomic provenance
Priority: P1
Estimate: 4h
Source: Release backlog ING-004, task 4. Consolidate repetitive facts/insights into readable entity/document views while preserving atomic provenance.
Implement this bounded change under “Raise extraction and summary quality across supported formats”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Consolidate repetitive facts/insights into readable entity/document views while preserving atomic provenance
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A signed fixture suite meets agreed extraction-quality thresholds and summaries are useful without hiding source uncertainty.

#### Task: Version prompts/ontologies and run regression benchmarks before changing models or instructions
Priority: P1
Estimate: 6h
Source: Release backlog ING-004, task 5. Version prompts/ontologies and run regression benchmarks before changing models or instructions.
Implement this bounded change under “Raise extraction and summary quality across supported formats”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Version prompts/ontologies and run regression benchmarks before changing models or instructions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A signed fixture suite meets agreed extraction-quality thresholds and summaries are useful without hiding source uncertainty.

### Story: Make ingestion jobs idempotent, resumable and recoverable
Priority: P0
Source: Release backlog ING-005 (repository and product audit, 16 July 2026). Worker or VM failure must not duplicate, orphan or permanently wedge evidence processing.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- After interruption, a job can resume or cleanly fail without duplicate graph data, orphan files, stuck status or server restart.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Define durable stage checkpoints and idempotency keys for upload, batch, reprocess, merge and Cellebrite jobs
Priority: P0
Estimate: 4h
Source: Release backlog ING-005, task 1. Define durable stage checkpoints and idempotency keys for upload, batch, reprocess, merge and Cellebrite jobs.
Implement this bounded change under “Make ingestion jobs idempotent, resumable and recoverable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define durable stage checkpoints and idempotency keys for upload, batch, reprocess, merge and Cellebrite jobs
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- After interruption, a job can resume or cleanly fail without duplicate graph data, orphan files, stuck status or server restart.

#### Task: Resume safely after worker restart; make retry policy explicit for provider, database and network failures
Priority: P0
Estimate: 8h
Source: Release backlog ING-005, task 2. Resume safely after worker restart; make retry policy explicit for provider, database and network failures.
Implement this bounded change under “Make ingestion jobs idempotent, resumable and recoverable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Resume safely after worker restart; make retry policy explicit for provider, database and network failures
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- After interruption, a job can resume or cleanly fail without duplicate graph data, orphan files, stuck status or server restart.

#### Task: Implement cancellation with terminal-state convergence and cleanup of partial Chroma/Neo4j/Postgres/file writes
Priority: P0
Estimate: 12h
Source: Release backlog ING-005, task 3. Implement cancellation with terminal-state convergence and cleanup of partial Chroma/Neo4j/Postgres/file writes.
Implement this bounded change under “Make ingestion jobs idempotent, resumable and recoverable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Implement cancellation with terminal-state convergence and cleanup of partial Chroma/Neo4j/Postgres/file writes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- After interruption, a job can resume or cleanly fail without duplicate graph data, orphan files, stuck status or server restart.

#### Task: Prevent concurrent upload/processing deadlocks and reproduce project backlog BUG-011
Priority: P0
Estimate: 8h
Source: Release backlog ING-005, task 4. Prevent concurrent upload/processing deadlocks and reproduce project backlog BUG-011.
Implement this bounded change under “Make ingestion jobs idempotent, resumable and recoverable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prevent concurrent upload/processing deadlocks and reproduce project backlog BUG-011
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- After interruption, a job can resume or cleanly fail without duplicate graph data, orphan files, stuck status or server restart.

#### Task: Test crash at every stage, duplicate delivery, low disk, timeout and partial write
Priority: P0
Estimate: 6h
Source: Release backlog ING-005, task 5. Test crash at every stage, duplicate delivery, low disk, timeout and partial write.
Implement this bounded change under “Make ingestion jobs idempotent, resumable and recoverable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test crash at every stage, duplicate delivery, low disk, timeout and partial write
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- After interruption, a job can resume or cleanly fail without duplicate graph data, orphan files, stuck status or server restart.

### Story: Secure and bound the upload pipeline
Priority: P0
Source: Release backlog ING-006 (repository and product audit, 16 July 2026). Protect memory, disk, workers and AI budget from accidental or hostile uploads.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Oversized, malformed, disguised, malicious and quota-exceeding uploads fail predictably before expensive processing or durable contamination.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Stream uploads to quarantine storage while hashing; avoid reading entire files into memory
Priority: P0
Estimate: 8h
Source: Release backlog ING-006, task 1. Stream uploads to quarantine storage while hashing; avoid reading entire files into memory.
Implement this bounded change under “Secure and bound the upload pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Stream uploads to quarantine storage while hashing; avoid reading entire files into memory
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Oversized, malformed, disguised, malicious and quota-exceeding uploads fail predictably before expensive processing or durable contamination.

#### Task: Enforce reverse-proxy and application limits for body size, file count, archive expansion, case quota and concurrent jobs
Priority: P0
Estimate: 8h
Source: Release backlog ING-006, task 2. Enforce reverse-proxy and application limits for body size, file count, archive expansion, case quota and concurrent jobs.
Implement this bounded change under “Secure and bound the upload pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Enforce reverse-proxy and application limits for body size, file count, archive expansion, case quota and concurrent jobs
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Oversized, malformed, disguised, malicious and quota-exceeding uploads fail predictably before expensive processing or durable contamination.

#### Task: Validate file signatures against extension/MIME, normalise filenames, block traversal/symlinks and quarantine rejects
Priority: P0
Estimate: 8h
Source: Release backlog ING-006, task 3. Validate file signatures against extension/MIME, normalise filenames, block traversal/symlinks and quarantine rejects.
Implement this bounded change under “Secure and bound the upload pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Validate file signatures against extension/MIME, normalise filenames, block traversal/symlinks and quarantine rejects
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Oversized, malformed, disguised, malicious and quota-exceeding uploads fail predictably before expensive processing or durable contamination.

#### Task: Add malware scanning and decompression-bomb/archive recursion protection
Priority: P0
Estimate: 16h
Source: Release backlog ING-006, task 4. Add malware scanning and decompression-bomb/archive recursion protection.
Implement this bounded change under “Secure and bound the upload pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add malware scanning and decompression-bomb/archive recursion protection
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Oversized, malformed, disguised, malicious and quota-exceeding uploads fail predictably before expensive processing or durable contamination.

#### Task: Surface safe, actionable rejection messages without logging evidence content or secrets
Priority: P0
Estimate: 8h
Source: Release backlog ING-006, task 5. Surface safe, actionable rejection messages without logging evidence content or secrets.
Implement this bounded change under “Secure and bound the upload pipeline”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Surface safe, actionable rejection messages without logging evidence content or secrets
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Oversized, malformed, disguised, malicious and quota-exceeding uploads fail predictably before expensive processing or durable contamination.

### Story: Constrain Triage to approved sources and import roles
Priority: P0
Source: Release backlog TRI-001 (repository and product audit, 16 July 2026). Triage is a powerful local-filesystem surface and must not be a general-user file browser.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- An unauthorised user or out-of-root path cannot be scanned/imported, and every import has a durable manifest.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Require a dedicated import/admin permission and target-case upload permission
Priority: P0
Estimate: 8h
Source: Release backlog TRI-001, task 1. Require a dedicated import/admin permission and target-case upload permission.
Implement this bounded change under “Constrain Triage to approved sources and import roles”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Require a dedicated import/admin permission and target-case upload permission
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An unauthorised user or out-of-root path cannot be scanned/imported, and every import has a durable manifest.

#### Task: Fail closed when TRIAGE_ALLOWED_ROOTS is empty in production; canonicalise paths and block symlink/network-share escapes
Priority: P0
Estimate: 8h
Source: Release backlog TRI-001, task 2. Fail closed when TRIAGE_ALLOWED_ROOTS is empty in production; canonicalise paths and block symlink/network-share escapes.
Implement this bounded change under “Constrain Triage to approved sources and import roles”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Fail closed when TRIAGE_ALLOWED_ROOTS is empty in production; canonicalise paths and block symlink/network-share escapes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An unauthorised user or out-of-root path cannot be scanned/imported, and every import has a durable manifest.

#### Task: Cap scan depth, files, bytes, hashing concurrency and LLM advisory spend
Priority: P0
Estimate: 6h
Source: Release backlog TRI-001, task 3. Cap scan depth, files, bytes, hashing concurrency and LLM advisory spend.
Implement this bounded change under “Constrain Triage to approved sources and import roles”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Cap scan depth, files, bytes, hashing concurrency and LLM advisory spend
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An unauthorised user or out-of-root path cannot be scanned/imported, and every import has a durable manifest.

#### Task: Make dry run the default, showing exact source manifest, hashes, destination case/folder and exclusions
Priority: P0
Estimate: 6h
Source: Release backlog TRI-001, task 4. Make dry run the default, showing exact source manifest, hashes, destination case/folder and exclusions.
Implement this bounded change under “Constrain Triage to approved sources and import roles”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make dry run the default, showing exact source manifest, hashes, destination case/folder and exclusions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An unauthorised user or out-of-root path cannot be scanned/imported, and every import has a durable manifest.

#### Task: Test cancel/restart, permission loss, path races and duplicate import
Priority: P0
Estimate: 6h
Source: Release backlog TRI-001, task 5. Test cancel/restart, permission loss, path races and duplicate import.
Implement this bounded change under “Constrain Triage to approved sources and import roles”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test cancel/restart, permission loss, path races and duplicate import
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- An unauthorised user or out-of-root path cannot be scanned/imported, and every import has a durable manifest.

### Story: Remove ‘Stale’ as a user-facing document status
Priority: P1
Source: Release backlog EVID-001 (repository and product audit, 16 July 2026). Keep the internal reprocessing signal but present it as a clear action rather than an unexplained status category.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Users never see an unexplained Stale status; affected files have a clear reason and reprocess action.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Remove Stale from the status filter and document-status vocabulary
Priority: P1
Estimate: 4h
Source: Release backlog EVID-001, task 1. Remove Stale from the status filter and document-status vocabulary.
Implement this bounded change under “Remove ‘Stale’ as a user-facing document status”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove Stale from the status filter and document-status vocabulary
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- Users never see an unexplained Stale status; affected files have a clear reason and reprocess action.

#### Task: Rename internal processing_stale UI treatment to ‘Reprocessing recommended’ or approved copy with an explanation
Priority: P1
Estimate: 4h
Source: Release backlog EVID-001, task 2. Rename internal processing_stale UI treatment to ‘Reprocessing recommended’ or approved copy with an explanation.
Implement this bounded change under “Remove ‘Stale’ as a user-facing document status”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Rename internal processing_stale UI treatment to ‘Reprocessing recommended’ or approved copy with an explanation
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users never see an unexplained Stale status; affected files have a clear reason and reprocess action.

#### Task: Keep primary state as unprocessed/processing/processed/failed and show why configuration changes require reprocess
Priority: P1
Estimate: 8h
Source: Release backlog EVID-001, task 3. Keep primary state as unprocessed/processing/processed/failed and show why configuration changes require reprocess.
Implement this bounded change under “Remove ‘Stale’ as a user-facing document status”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep primary state as unprocessed/processing/processed/failed and show why configuration changes require reprocess
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users never see an unexplained Stale status; affected files have a clear reason and reprocess action.

#### Task: Update API/docs/tests without losing the internal invalidation mechanism
Priority: P1
Estimate: 6h
Source: Release backlog EVID-001, task 4. Update API/docs/tests without losing the internal invalidation mechanism.
Implement this bounded change under “Remove ‘Stale’ as a user-facing document status”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Update API/docs/tests without losing the internal invalidation mechanism
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users never see an unexplained Stale status; affected files have a clear reason and reprocess action.

### Story: Implement reliable folder reorganisation
Priority: P1
Source: Release backlog EVID-002 (repository and product audit, 16 July 2026). Dragging folders currently cannot reposition them even though the backend supports moves.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Folders and files move reliably by drag or keyboard/menu and remain correct after refresh without cycles or cross-case leakage.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add pointer drag/drop with valid drop targets, insertion feedback and auto-expand
Priority: P1
Estimate: 8h
Source: Release backlog EVID-002, task 1. Add pointer drag/drop with valid drop targets, insertion feedback and auto-expand.
Implement this bounded change under “Implement reliable folder reorganisation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add pointer drag/drop with valid drop targets, insertion feedback and auto-expand
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Folders and files move reliably by drag or keyboard/menu and remain correct after refresh without cycles or cross-case leakage.

#### Task: Provide keyboard/menu Move to… as an accessible alternative
Priority: P1
Estimate: 8h
Source: Release backlog EVID-002, task 2. Provide keyboard/menu Move to… as an accessible alternative.
Implement this bounded change under “Implement reliable folder reorganisation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Provide keyboard/menu Move to… as an accessible alternative
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Folders and files move reliably by drag or keyboard/menu and remain correct after refresh without cycles or cross-case leakage.

#### Task: Prevent self/descendant moves, cross-case moves and stale-tree races; surface backend errors
Priority: P1
Estimate: 8h
Source: Release backlog EVID-002, task 3. Prevent self/descendant moves, cross-case moves and stale-tree races; surface backend errors.
Implement this bounded change under “Implement reliable folder reorganisation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prevent self/descendant moves, cross-case moves and stale-tree races; surface backend errors
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Folders and files move reliably by drag or keyboard/menu and remain correct after refresh without cycles or cross-case leakage.

#### Task: Support moving selected files and folders with optimistic rollback and audit
Priority: P1
Estimate: 8h
Source: Release backlog EVID-002, task 4. Support moving selected files and folders with optimistic rollback and audit.
Implement this bounded change under “Implement reliable folder reorganisation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Support moving selected files and folders with optimistic rollback and audit
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Folders and files move reliably by drag or keyboard/menu and remain correct after refresh without cycles or cross-case leakage.

#### Task: Test deep trees, empty/root moves, concurrent rename/move and refresh persistence
Priority: P1
Estimate: 8h
Source: Release backlog EVID-002, task 5. Test deep trees, empty/root moves, concurrent rename/move and refresh persistence.
Implement this bounded change under “Implement reliable folder reorganisation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test deep trees, empty/root moves, concurrent rename/move and refresh persistence
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Folders and files move reliably by drag or keyboard/menu and remain correct after refresh without cycles or cross-case leakage.

### Story: Allow reviewed document-summary edits
Priority: P1
Source: Release backlog EVID-003 (repository and product audit, 16 July 2026). Investigators need to correct summaries without erasing the AI original or its provenance.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A permitted user can edit and recover a summary; its AI original and full edit history remain available.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add edit/cancel/save with unsaved-change protection and permissions
Priority: P1
Estimate: 8h
Source: Release backlog EVID-003, task 1. Add edit/cancel/save with unsaved-change protection and permissions.
Implement this bounded change under “Allow reviewed document-summary edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add edit/cancel/save with unsaved-change protection and permissions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A permitted user can edit and recover a summary; its AI original and full edit history remain available.

#### Task: Store original AI summary, current reviewed summary, editor, timestamp and version history
Priority: P1
Estimate: 8h
Source: Release backlog EVID-003, task 2. Store original AI summary, current reviewed summary, editor, timestamp and version history.
Implement this bounded change under “Allow reviewed document-summary edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Store original AI summary, current reviewed summary, editor, timestamp and version history
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A permitted user can edit and recover a summary; its AI original and full edit history remain available.

#### Task: Label AI-generated versus human-edited content and prevent reprocessing overwrite without review
Priority: P1
Estimate: 8h
Source: Release backlog EVID-003, task 3. Label AI-generated versus human-edited content and prevent reprocessing overwrite without review.
Implement this bounded change under “Allow reviewed document-summary edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Label AI-generated versus human-edited content and prevent reprocessing overwrite without review
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A permitted user can edit and recover a summary; its AI original and full edit history remain available.

#### Task: Add concurrency conflict handling and audit events
Priority: P1
Estimate: 8h
Source: Release backlog EVID-003, task 4. Add concurrency conflict handling and audit events.
Implement this bounded change under “Allow reviewed document-summary edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add concurrency conflict handling and audit events
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A permitted user can edit and recover a summary; its AI original and full edit history remain available.

#### Task: Ensure workspace/report/chat references use the approved current version while retaining history
Priority: P1
Estimate: 4h
Source: Release backlog EVID-003, task 5. Ensure workspace/report/chat references use the approved current version while retaining history.
Implement this bounded change under “Allow reviewed document-summary edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Ensure workspace/report/chat references use the approved current version while retaining history
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A permitted user can edit and recover a summary; its AI original and full edit history remain available.

### Story: Remove ‘Replace duplicate report’ from the upload menu
Priority: P1
Source: Release backlog EVID-004 (repository and product audit, 16 July 2026). Duplicate handling should be automatic, reviewable and format-aware—not a persistent destructive checkbox.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- General upload has no replace toggle; duplicate behavior is deterministic, non-destructive and explained at the point of detection.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Remove the checkbox/state from the general upload dropdown
Priority: P1
Estimate: 4h
Source: Release backlog EVID-004, task 1. Remove the checkbox/state from the general upload dropdown.
Implement this bounded change under “Remove ‘Replace duplicate report’ from the upload menu”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove the checkbox/state from the general upload dropdown
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- General upload has no replace toggle; duplicate behavior is deterministic, non-destructive and explained at the point of detection.

#### Task: Detect duplicate files/reports by stable hash/report identity and present a post-detection choice if genuinely needed
Priority: P1
Estimate: 8h
Source: Release backlog EVID-004, task 2. Detect duplicate files/reports by stable hash/report identity and present a post-detection choice if genuinely needed.
Implement this bounded change under “Remove ‘Replace duplicate report’ from the upload menu”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Detect duplicate files/reports by stable hash/report identity and present a post-detection choice if genuinely needed
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- General upload has no replace toggle; duplicate behavior is deterministic, non-destructive and explained at the point of detection.

#### Task: Define skip, link existing, reprocess and supersede semantics with non-destructive defaults
Priority: P1
Estimate: 4h
Source: Release backlog EVID-004, task 3. Define skip, link existing, reprocess and supersede semantics with non-destructive defaults.
Implement this bounded change under “Remove ‘Replace duplicate report’ from the upload menu”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define skip, link existing, reprocess and supersede semantics with non-destructive defaults
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- General upload has no replace toggle; duplicate behavior is deterministic, non-destructive and explained at the point of detection.

#### Task: Protect existing report data/links during any approved supersede flow and add audit
Priority: P1
Estimate: 8h
Source: Release backlog EVID-004, task 4. Protect existing report data/links during any approved supersede flow and add audit.
Implement this bounded change under “Remove ‘Replace duplicate report’ from the upload menu”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Protect existing report data/links during any approved supersede flow and add audit
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- General upload has no replace toggle; duplicate behavior is deterministic, non-destructive and explained at the point of detection.

#### Task: Add duplicate-name, same-content, changed-content and concurrent-upload tests
Priority: P1
Estimate: 8h
Source: Release backlog EVID-004, task 5. Add duplicate-name, same-content, changed-content and concurrent-upload tests.
Implement this bounded change under “Remove ‘Replace duplicate report’ from the upload menu”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add duplicate-name, same-content, changed-content and concurrent-upload tests
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- General upload has no replace toggle; duplicate behavior is deterministic, non-destructive and explained at the point of detection.

### Story: Define immutable originals, recycle, retention and chain-of-handling
Priority: P0
Source: Release backlog EVID-005 (repository and product audit, 16 July 2026). Evidence deletion and movement need defensible history without making unsupported legal chain-of-custody claims.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Original evidence hashes and handling history survive normal operations; irreversible deletion follows documented authority and retention rules.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Store originals immutably with SHA-256, uploader, received time, original name/size and storage version
Priority: P0
Estimate: 8h
Source: Release backlog EVID-005, task 1. Store originals immutably with SHA-256, uploader, received time, original name/size and storage version.
Implement this bounded change under “Define immutable originals, recycle, retention and chain-of-handling”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Store originals immutably with SHA-256, uploader, received time, original name/size and storage version
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Original evidence hashes and handling history survive normal operations; irreversible deletion follows documented authority and retention rules.

#### Task: Define soft delete/recycle, authorised hard delete, legal hold and retention/offboarding behavior
Priority: P0
Estimate: 4h
Source: Release backlog EVID-005, task 2. Define soft delete/recycle, authorised hard delete, legal hold and retention/offboarding behavior.
Implement this bounded change under “Define immutable originals, recycle, retention and chain-of-handling”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define soft delete/recycle, authorised hard delete, legal hold and retention/offboarding behavior
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Original evidence hashes and handling history survive normal operations; irreversible deletion follows documented authority and retention rules.

#### Task: Record upload, view, download, move, process, export, recycle, restore and delete events in tamper-resistant audit history
Priority: P0
Estimate: 12h
Source: Release backlog EVID-005, task 3. Record upload, view, download, move, process, export, recycle, restore and delete events in tamper-resistant audit history.
Implement this bounded change under “Define immutable originals, recycle, retention and chain-of-handling”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Record upload, view, download, move, process, export, recycle, restore and delete events in tamper-resistant audit history
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Original evidence hashes and handling history survive normal operations; irreversible deletion follows documented authority and retention rules.

#### Task: Verify cross-store cleanup/rebuild rules for derived text, frames, embeddings and graph data
Priority: P0
Estimate: 16h
Source: Release backlog EVID-005, task 4. Verify cross-store cleanup/rebuild rules for derived text, frames, embeddings and graph data.
Implement this bounded change under “Define immutable originals, recycle, retention and chain-of-handling”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify cross-store cleanup/rebuild rules for derived text, frames, embeddings and graph data
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Original evidence hashes and handling history survive normal operations; irreversible deletion follows documented authority and retention rules.

#### Task: Use ‘handling history’ language until legal review approves stronger claims
Priority: P0
Estimate: 6h
Source: Release backlog EVID-005, task 5. Use ‘handling history’ language until legal review approves stronger claims.
Implement this bounded change under “Define immutable originals, recycle, retention and chain-of-handling”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Use ‘handling history’ language until legal review approves stronger claims
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Original evidence hashes and handling history survive normal operations; irreversible deletion follows documented authority and retention rules.

### Story: Polish processing, preview and failure recovery
Priority: P1
Source: Release backlog EVID-006 (repository and product audit, 16 July 2026). Users must understand active jobs and recover without a server restart.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A user can diagnose and recover every fixture failure from the UI; reconnect/retry never creates duplicate jobs or data.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Fix the WebSocket reconnect implementation flagged by lint and test disconnect/retry/cancel races
Priority: P1
Estimate: 12h
Source: Release backlog EVID-006, task 1. Fix the WebSocket reconnect implementation flagged by lint and test disconnect/retry/cancel races.
Implement this bounded change under “Polish processing, preview and failure recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Fix the WebSocket reconnect implementation flagged by lint and test disconnect/retry/cancel races
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A user can diagnose and recover every fixture failure from the UI; reconnect/retry never creates duplicate jobs or data.

#### Task: Show per-file/batch progress, queue position, elapsed time, safe error detail and next action
Priority: P1
Estimate: 8h
Source: Release backlog EVID-006, task 2. Show per-file/batch progress, queue position, elapsed time, safe error detail and next action.
Implement this bounded change under “Polish processing, preview and failure recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show per-file/batch progress, queue position, elapsed time, safe error detail and next action
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A user can diagnose and recover every fixture failure from the UI; reconnect/retry never creates duplicate jobs or data.

#### Task: Support retry/reprocess from failure without duplicate upload or stale job cards
Priority: P1
Estimate: 8h
Source: Release backlog EVID-006, task 3. Support retry/reprocess from failure without duplicate upload or stale job cards.
Implement this bounded change under “Polish processing, preview and failure recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Support retry/reprocess from failure without duplicate upload or stale job cards
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A user can diagnose and recover every fixture failure from the UI; reconnect/retry never creates duplicate jobs or data.

#### Task: Verify protected previews/downloads for PDF, text, image, audio, video and unsupported formats
Priority: P1
Estimate: 8h
Source: Release backlog EVID-006, task 4. Verify protected previews/downloads for PDF, text, image, audio, video and unsupported formats.
Implement this bounded change under “Polish processing, preview and failure recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify protected previews/downloads for PDF, text, image, audio, video and unsupported formats
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A user can diagnose and recover every fixture failure from the UI; reconnect/retry never creates duplicate jobs or data.

#### Task: Test concurrent uploads, refresh/navigation during processing and long filenames/non-Latin text
Priority: P1
Estimate: 6h
Source: Release backlog EVID-006, task 5. Test concurrent uploads, refresh/navigation during processing and long filenames/non-Latin text.
Implement this bounded change under “Polish processing, preview and failure recovery”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test concurrent uploads, refresh/navigation during processing and long filenames/non-Latin text
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A user can diagnose and recover every fixture failure from the UI; reconnect/retry never creates duplicate jobs or data.

### Story: Investigator can upload huge evidence sets reliably
v1's tus/Uppy resumable-upload stack (proven on 31.8GB and 35GB uploads) has no v2 counterpart; v2 uploads run synchronously in-request with a 1-hour client timeout, so an interrupted large upload starts over (gap assessment §3.3, BRG-031; v1 refs `6558672`…`1f63e3d`, `deploy/owl-tusd.service`, tus hooks, Uppy component).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-031, gap assessment §3.3). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A multi-GB upload survives an interruption and resumes; ingest triggers on completion
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Stand up tusd service + server-side hooks
Estimate: 14h
Port v1's tusd deployment (`deploy/owl-tusd.service`) and the tus hooks that register uploads and hand completed files to the evidence-engine pipeline.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-031, gap assessment §3.3). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- tusd runs alongside the v2 stack with hooks wired to evidence registration
- Killing and restarting the backend mid-upload preserves offsets

#### Task: Uppy resumable-upload frontend
Estimate: 10h
Port the Uppy component and resume UX into v2's evidence upload surface, replacing the synchronous in-request path for large files.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-031, gap assessment §3.3). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- After a network blip, the progress bar resumes from the true server offset and never moves backwards
- The 1-hour client timeout path no longer applies to large uploads

#### Task: Completion-to-ingest trigger + large-upload verification
Estimate: 6h
Wire upload completion to evidence-engine ingestion and verify the stack end-to-end at multi-GB scale, matching v1's proven benchmark.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-031, gap assessment §3.3). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A completed multi-GB upload automatically enters the ingest pipeline
- A deliberately interrupted 10GB+ test upload resumes and completes

### Task: Upload robustness + failure surfacing
Estimate: 14h
Port background registration, per-file failure counts, whole-batch-failure detection (a 100%-failed batch must never read COMPLETED), ENOSPC→507 handling, and the amber "Action needed" task for silently-skipped no-phone reports (gap assessment §3.3, BRG-032; v1 refs `3040228`, `7e451cb`, `9fdb8d1`, `1f63e3d`/`2c0428e`).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-032, gap assessment §3.3). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each listed failure mode has a test and a visible user signal
- A fully-failed batch shows failed status, never COMPLETED
- Disk-full returns 507 with a user-readable message

### Task: Wiretap pipeline — decide, then port or retire properly
Priority: P1
Estimate: 6h
v2's `/wiretap/process` is a stub returning "retired" while the route stays live — a live endpoint that silently does nothing is the worst of both (gap assessment §2/§3.3, BRG-033 DECIDE). Decide with Neil: port v1's triad pipeline (`wiretap_service.py` + `ingest_audio.py`: .wav transcribe/translate, .sri parse, .rtf interpretation) or retire it deliberately (remove route + profile rules, document). This estimate covers the decision plus the retirement path; a port decision spawns a scoped M–L follow-up ticket.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-033, gap assessment §2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded; no dead route remains either way
- If retired: route and triad profile rules removed and the retirement documented; if ported: follow-up ticket created with v1 refs

### Task: Decide on-demand media AI analysis
Priority: P3
Estimate: 4h
v1 offers per-file on-demand transcribe/image-recognition, cached, using local Whisper (offline-capable); v2 is at-ingest only via OpenAI (cloud dependency, no re-run) — gap assessment §3.6, BRG-034 DECIDE, v1 ref `ed6146e`. Decide whether on-demand + offline capability matters for enterprise deployments (air-gapped clients).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-034, gap assessment §3.6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded; if yes, a scoped port ticket is created; if no, the drop is documented
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Task: Restore background-task stall recovery + cap task file lists
Estimate: 6h
Gap assessment §3.6 (yardstick item 44): stalled background tasks can't be marked failed on v2 (the recovery endpoint is gone), and task file lists rewrite unbounded per file where v1 caps at 100. Not covered by any roadmap ticket — added here so the gap isn't dropped silently. Port the mark-failed/stall-recovery endpoint and the file-list cap.
Source: V2 Alpha Bridging Plan (13 July 2026; Gap assessment §3.6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A stalled task can be marked failed from the tasks UI
- Task file lists are capped at 100 entries with a count of the remainder

## Epic: Core Investigation Surfaces
Color: #087f83
Deliver accurate, usable and full-dataset Graph, Timeline, Map and Table workflows so investigators can explore evidence without hidden caps, broken controls or misleading chronology.

### Story: Tune default graph spacing for readable layouts
Priority: P1
Source: Release backlog GRAPH-001 (repository and product audit, 16 July 2026). Current force defaults can overlap labels/nodes even though manual controls exist.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Default graphs settle quickly with no material node/label overlap on the supported fixture set.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Create representative small, medium, dense and 10k-node graph fixtures
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-001, task 1. Create representative small, medium, dense and 10k-node graph fixtures.
Implement this bounded change under “Tune default graph spacing for readable layouts”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create representative small, medium, dense and 10k-node graph fixtures
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Default graphs settle quickly with no material node/label overlap on the supported fixture set.

#### Task: Add collision/label-aware spacing and adaptive force parameters by graph size/degree
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-001, task 2. Add collision/label-aware spacing and adaptive force parameters by graph size/degree.
Implement this bounded change under “Tune default graph spacing for readable layouts”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add collision/label-aware spacing and adaptive force parameters by graph size/degree
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Default graphs settle quickly with no material node/label overlap on the supported fixture set.

#### Task: Choose defaults using measured settling time, overlap rate and browser memory—not one demo case
Priority: P1
Estimate: 6h
Source: Release backlog GRAPH-001, task 3. Choose defaults using measured settling time, overlap rate and browser memory—not one demo case.
Implement this bounded change under “Tune default graph spacing for readable layouts”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Choose defaults using measured settling time, overlap rate and browser memory—not one demo case
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Default graphs settle quickly with no material node/label overlap on the supported fixture set.

#### Task: Persist optional user adjustments per user/case and provide an obvious reset
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-001, task 4. Persist optional user adjustments per user/case and provide an obvious reset.
Implement this bounded change under “Tune default graph spacing for readable layouts”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Persist optional user adjustments per user/case and provide an obvious reset
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Default graphs settle quickly with no material node/label overlap on the supported fixture set.

#### Task: Regression-test resizing, filtered graphs, Spotlight and pinned nodes
Priority: P1
Estimate: 6h
Source: Release backlog GRAPH-001, task 5. Regression-test resizing, filtered graphs, Spotlight and pinned nodes.
Implement this bounded change under “Tune default graph spacing for readable layouts”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Regression-test resizing, filtered graphs, Spotlight and pinned nodes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Default graphs settle quickly with no material node/label overlap on the supported fixture set.

### Story: Reduce the Graph toolbar and context menu to safe investigator actions
Priority: P1
Source: Release backlog GRAPH-002 (repository and product audit, 16 July 2026). Remove technical, duplicated or non-working actions and use unambiguous recycle terminology.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The production toolbar/context menu exactly matches the approved action set and contains no expert-only or inert command.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Retire the broken end-user Cypher panel, remove Run Cypher from the production Graph toolbar, and remove or strictly case-scope and read-limit…
Priority: P1
Estimate: 6h
Source: Release backlog GRAPH-002, task 1. Also sourced from V2 Alpha Bridging Plan BRG-006 / Gap Assessment §5. Retire the broken end-user Cypher panel, remove Run Cypher from the production Graph toolbar, and remove or strictly case-scope and read-limit every underlying direct-query endpoint. The older instruction to repair `CypherPanel.tsx` is superseded by the approved release decision to retire the investigator-facing panel; its case-isolation and write-rejection requirements remain mandatory for any retained `/api/query` route.
Implement this bounded change under “Reduce the Graph toolbar and context menu to safe investigator actions”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Retire the broken end-user Cypher panel, remove Run Cypher from the production Graph toolbar, and remove or strictly case-scope and read-limit every underlying direct-query endpoint
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The production toolbar/context menu exactly matches the approved action set and contains no expert-only or inert command.

#### Task: Remove Expand Connections, Relationship Analysis, Pin/Unpin, Copy Key and Hide Node from the main-graph context menu
Priority: P1
Estimate: 4h
Source: Release backlog GRAPH-002, task 2. Remove Expand Connections, Relationship Analysis, Pin/Unpin, Copy Key and Hide Node from the main-graph context menu.
Implement this bounded change under “Reduce the Graph toolbar and context menu to safe investigator actions”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove Expand Connections, Relationship Analysis, Pin/Unpin, Copy Key and Hide Node from the main-graph context menu
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- The production toolbar/context menu exactly matches the approved action set and contains no expert-only or inert command.

#### Task: Retain Show Details, Add to Spotlight, Edit Entity and Recycle Entity; show Merge Selected only for 2+ selected nodes
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-002, task 3. Retain Show Details, Add to Spotlight, Edit Entity and Recycle Entity; show Merge Selected only for 2+ selected nodes.
Implement this bounded change under “Reduce the Graph toolbar and context menu to safe investigator actions”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Retain Show Details, Add to Spotlight, Edit Entity and Recycle Entity; show Merge Selected only for 2+ selected nodes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The production toolbar/context menu exactly matches the approved action set and contains no expert-only or inert command.

#### Task: Rename every destructive node action from Delete to Recycle and explain recoverability
Priority: P1
Estimate: 4h
Source: Release backlog GRAPH-002, task 4. Rename every destructive node action from Delete to Recycle and explain recoverability.
Implement this bounded change under “Reduce the Graph toolbar and context menu to safe investigator actions”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Rename every destructive node action from Delete to Recycle and explain recoverability
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The production toolbar/context menu exactly matches the approved action set and contains no expert-only or inert command.

#### Task: Move Force Controls into a clearly labelled view/layout settings affordance and test toolbar overflow at supported widths
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-002, task 5. Move Force Controls into a clearly labelled view/layout settings affordance and test toolbar overflow at supported widths.
Implement this bounded change under “Reduce the Graph toolbar and context menu to safe investigator actions”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Move Force Controls into a clearly labelled view/layout settings affordance and test toolbar overflow at supported widths
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The production toolbar/context menu exactly matches the approved action set and contains no expert-only or inert command.

### Story: Rebuild the create-relationship workflow
Priority: P0
Source: Release backlog GRAPH-003 (repository and product audit, 16 July 2026). Use a selected source entity, search for a target, name the relationship, and persist investigator provenance.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- An investigator can create the intended directed relationship without preselecting two nodes, and the resulting edge is auditable and recoverable.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Require exactly one source entity or make multi-source behavior explicit; never default a one-node selection to a self-relationship
Priority: P0
Estimate: 8h
Source: Release backlog GRAPH-003, task 1. Require exactly one source entity or make multi-source behavior explicit; never default a one-node selection to a self-relationship.
Implement this bounded change under “Rebuild the create-relationship workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Require exactly one source entity or make multi-source behavior explicit; never default a one-node selection to a self-relationship
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can create the intended directed relationship without preselecting two nodes, and the resulting edge is auditable and recoverable.

#### Task: Add full-case target search with type/identifier disambiguation and prevent invalid same-node links unless explicitly supported
Priority: P0
Estimate: 12h
Source: Release backlog GRAPH-003, task 2. Add full-case target search with type/identifier disambiguation and prevent invalid same-node links unless explicitly supported.
Implement this bounded change under “Rebuild the create-relationship workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add full-case target search with type/identifier disambiguation and prevent invalid same-node links unless explicitly supported
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can create the intended directed relationship without preselecting two nodes, and the resulting edge is auditable and recoverable.

#### Task: Validate/canonicalise relationship type while showing the human-readable label
Priority: P0
Estimate: 6h
Source: Release backlog GRAPH-003, task 3. Validate/canonicalise relationship type while showing the human-readable label.
Implement this bounded change under “Rebuild the create-relationship workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Validate/canonicalise relationship type while showing the human-readable label
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- An investigator can create the intended directed relationship without preselecting two nodes, and the resulting edge is auditable and recoverable.

#### Task: Persist notes, actor, timestamp, source type and optional supporting evidence—the current notes field is collected but unused
Priority: P0
Estimate: 8h
Source: Release backlog GRAPH-003, task 4. Persist notes, actor, timestamp, source type and optional supporting evidence—the current notes field is collected but unused.
Implement this bounded change under “Rebuild the create-relationship workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Persist notes, actor, timestamp, source type and optional supporting evidence—the current notes field is collected but unused
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can create the intended directed relationship without preselecting two nodes, and the resulting edge is auditable and recoverable.

#### Task: Add permission, duplicate, direction, case-boundary and undo/recycle tests
Priority: P0
Estimate: 8h
Source: Release backlog GRAPH-003, task 5. Add permission, duplicate, direction, case-boundary and undo/recycle tests.
Implement this bounded change under “Rebuild the create-relationship workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add permission, duplicate, direction, case-boundary and undo/recycle tests
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An investigator can create the intended directed relationship without preselecting two nodes, and the resulting edge is auditable and recoverable.

### Story: Make Spotlight a predictable toggle and selection workflow
Priority: P1
Source: Release backlog GRAPH-004 (repository and product audit, 16 July 2026). Spotlight should open even when empty, accept selected nodes from a logical action, and remain independently closable.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Users can open an empty Spotlight, add/remove selected nodes and close/reopen it without losing state or hunting in the legend.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Render the Spotlight panel whenever toggled on, including a useful empty state
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-004, task 1. Render the Spotlight panel whenever toggled on, including a useful empty state.
Implement this bounded change under “Make Spotlight a predictable toggle and selection workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Render the Spotlight panel whenever toggled on, including a useful empty state
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can open an empty Spotlight, add/remove selected nodes and close/reopen it without losing state or hunting in the legend.

#### Task: Add Add selected to Spotlight near selection actions/context—not in the legend—and support remove/clear
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-004, task 2. Add Add selected to Spotlight near selection actions/context—not in the legend—and support remove/clear.
Implement this bounded change under “Make Spotlight a predictable toggle and selection workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add Add selected to Spotlight near selection actions/context—not in the legend—and support remove/clear
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can open an empty Spotlight, add/remove selected nodes and close/reopen it without losing state or hunting in the legend.

#### Task: Keep the toolbar button state accurate and make the same control always open/close Spotlight
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-004, task 3. Keep the toolbar button state accurate and make the same control always open/close Spotlight.
Implement this bounded change under “Make Spotlight a predictable toggle and selection workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep the toolbar button state accurate and make the same control always open/close Spotlight
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can open an empty Spotlight, add/remove selected nodes and close/reopen it without losing state or hunting in the legend.

#### Task: Preserve Spotlight contents while hidden and define case/navigation reset behavior
Priority: P1
Estimate: 4h
Source: Release backlog GRAPH-004, task 4. Preserve Spotlight contents while hidden and define case/navigation reset behavior.
Implement this bounded change under “Make Spotlight a predictable toggle and selection workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Preserve Spotlight contents while hidden and define case/navigation reset behavior
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can open an empty Spotlight, add/remove selected nodes and close/reopen it without losing state or hunting in the legend.

#### Task: Remove the current analysis expander or redesign it around approved, understandable Spotlight-only outcomes
Priority: P1
Estimate: 4h
Source: Release backlog GRAPH-004, task 5. Remove the current analysis expander or redesign it around approved, understandable Spotlight-only outcomes.
Implement this bounded change under “Make Spotlight a predictable toggle and selection workflow”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove the current analysis expander or redesign it around approved, understandable Spotlight-only outcomes
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- Users can open an empty Spotlight, add/remove selected nodes and close/reopen it without losing state or hunting in the legend.

### Story: Complete manual entity creation and location linking
Priority: P1
Source: Release backlog GRAPH-005 (repository and product audit, 16 July 2026). Manual creation must support the same meaningful fields and provenance as entity editing.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Selecting a place fills the address fields and editing the address updates the pin; saved entities retain clear investigator provenance.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Use a schema-driven form by entity type rather than a three-field generic dialog
Priority: P1
Estimate: 12h
Source: Release backlog GRAPH-005, task 1. Use a schema-driven form by entity type rather than a three-field generic dialog.
Implement this bounded change under “Complete manual entity creation and location linking”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Use a schema-driven form by entity type rather than a three-field generic dialog
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Selecting a place fills the address fields and editing the address updates the pin; saved entities retain clear investigator provenance.

#### Task: For locations, keep map selection, address search, formatted address and coordinates bidirectionally linked
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-005, task 2. For locations, keep map selection, address search, formatted address and coordinates bidirectionally linked.
Implement this bounded change under “Complete manual entity creation and location linking”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: For locations, keep map selection, address search, formatted address and coordinates bidirectionally linked
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Selecting a place fills the address fields and editing the address updates the pin; saved entities retain clear investigator provenance.

#### Task: Show geocoding precision/confidence and allow pin correction/clear before save
Priority: P1
Estimate: 4h
Source: Release backlog GRAPH-005, task 3. Show geocoding precision/confidence and allow pin correction/clear before save.
Implement this bounded change under “Complete manual entity creation and location linking”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show geocoding precision/confidence and allow pin correction/clear before save
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Selecting a place fills the address fields and editing the address updates the pin; saved entities retain clear investigator provenance.

#### Task: Capture investigator assertion, actor and optional supporting evidence; protect verified fields from later AI overwrite
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-005, task 4. Capture investigator assertion, actor and optional supporting evidence; protect verified fields from later AI overwrite.
Implement this bounded change under “Complete manual entity creation and location linking”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Capture investigator assertion, actor and optional supporting evidence; protect verified fields from later AI overwrite
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Selecting a place fills the address fields and editing the address updates the pin; saved entities retain clear investigator provenance.

#### Task: Validate duplicates and offer compare/merge before creating a likely duplicate
Priority: P1
Estimate: 6h
Source: Release backlog GRAPH-005, task 5. Validate duplicates and offer compare/merge before creating a likely duplicate.
Implement this bounded change under “Complete manual entity creation and location linking”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Validate duplicates and offer compare/merge before creating a likely duplicate
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Selecting a place fills the address fields and editing the address updates the pin; saved entities retain clear investigator provenance.

### Story: Validate Graph algorithms and make results usable
Priority: P1
Source: Release backlog GRAPH-006 (repository and product audit, 16 July 2026). Algorithm output needs domain sign-off, explanations, scroll containment and deterministic result interaction.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Known fixtures return expected results, the panel is fully scrollable, and a domain reviewer signs the displayed interpretation.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Fix the Graph Analysis overlay so its full content and result lists scroll inside the right rail at all supported heights
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-006, task 1. Fix the Graph Analysis overlay so its full content and result lists scroll inside the right rail at all supported heights.
Implement this bounded change under “Validate Graph algorithms and make results usable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Fix the Graph Analysis overlay so its full content and result lists scroll inside the right rail at all supported heights
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known fixtures return expected results, the panel is fully scrollable, and a domain reviewer signs the displayed interpretation.

#### Task: Verify PageRank, Louvain, betweenness and shortest paths against known fixture graphs
Priority: P1
Estimate: 6h
Source: Release backlog GRAPH-006, task 2. Verify PageRank, Louvain, betweenness and shortest paths against known fixture graphs.
Implement this bounded change under “Validate Graph algorithms and make results usable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify PageRank, Louvain, betweenness and shortest paths against known fixture graphs
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Known fixtures return expected results, the panel is fully scrollable, and a domain reviewer signs the displayed interpretation.

#### Task: Add plain-language purpose, inputs, limits and interpretation for each algorithm
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-006, task 3. Add plain-language purpose, inputs, limits and interpretation for each algorithm.
Implement this bounded change under “Validate Graph algorithms and make results usable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add plain-language purpose, inputs, limits and interpretation for each algorithm
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known fixtures return expected results, the panel is fully scrollable, and a domain reviewer signs the displayed interpretation.

#### Task: Obtain domain-owner sign-off (the original note names Neil) on labels, ranking and presentation
Priority: P1
Estimate: 6h
Source: Release backlog GRAPH-006, task 4. Obtain domain-owner sign-off (the original note names Neil) on labels, ranking and presentation.
Implement this bounded change under “Validate Graph algorithms and make results usable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Obtain domain-owner sign-off (the original note names Neil) on labels, ranking and presentation
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known fixtures return expected results, the panel is fully scrollable, and a domain reviewer signs the displayed interpretation.

#### Task: Handle unavailable plugins, large-graph limits, empty results and cancellation without stale Spotlight data
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-006, task 5. Handle unavailable plugins, large-graph limits, empty results and cancellation without stale Spotlight data.
Implement this bounded change under “Validate Graph algorithms and make results usable”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Handle unavailable plugins, large-graph limits, empty results and cancellation without stale Spotlight data
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known fixtures return expected results, the panel is fully scrollable, and a domain reviewer signs the displayed interpretation.

### Story: Prove merge, similar-entity and recycle-bin data integrity
Priority: P0
Source: Release backlog GRAPH-007 (repository and product audit, 16 July 2026). No entity facts, sources, relationships or downstream references may disappear during the highest-risk Graph workflow.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Automated cross-store assertions prove no essential data or references are lost and recycle/restore returns a consistent entity.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Build end-to-end fixtures covering Find Similar → compare/reject/merge → recycle → restore
Priority: P0
Estimate: 16h
Source: Release backlog GRAPH-007, task 1. Build end-to-end fixtures covering Find Similar → compare/reject/merge → recycle → restore.
Implement this bounded change under “Prove merge, similar-entity and recycle-bin data integrity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Build end-to-end fixtures covering Find Similar → compare/reject/merge → recycle → restore
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Automated cross-store assertions prove no essential data or references are lost and recycle/restore returns a consistent entity.

#### Task: Verify properties, facts, insights, aliases, provenance, relationships, embeddings, timeline/map/financial links and workspace attachments survive…
Priority: P0
Estimate: 6h
Source: Release backlog GRAPH-007, task 2. Verify properties, facts, insights, aliases, provenance, relationships, embeddings, timeline/map/financial links and workspace attachments survive merge.
Implement this bounded change under “Prove merge, similar-entity and recycle-bin data integrity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify properties, facts, insights, aliases, provenance, relationships, embeddings, timeline/map/financial links and workspace attachments survive merge
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Automated cross-store assertions prove no essential data or references are lost and recycle/restore returns a consistent entity.

#### Task: Define deterministic conflict handling, merge idempotency and concurrent-merge locking
Priority: P0
Estimate: 4h
Source: Release backlog GRAPH-007, task 3. Define deterministic conflict handling, merge idempotency and concurrent-merge locking.
Implement this bounded change under “Prove merge, similar-entity and recycle-bin data integrity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define deterministic conflict handling, merge idempotency and concurrent-merge locking
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Automated cross-store assertions prove no essential data or references are lost and recycle/restore returns a consistent entity.

#### Task: Verify restore after manual recycle, merge and evidence deletion; prevent restoring into another case
Priority: P0
Estimate: 12h
Source: Release backlog GRAPH-007, task 4. Verify restore after manual recycle, merge and evidence deletion; prevent restoring into another case.
Implement this bounded change under “Prove merge, similar-entity and recycle-bin data integrity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify restore after manual recycle, merge and evidence deletion; prevent restoring into another case
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Automated cross-store assertions prove no essential data or references are lost and recycle/restore returns a consistent entity.

#### Task: Record immutable audit events and add a pre-merge preview/summary
Priority: P0
Estimate: 8h
Source: Release backlog GRAPH-007, task 5. Record immutable audit events and add a pre-merge preview/summary.
Implement this bounded change under “Prove merge, similar-entity and recycle-bin data integrity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Record immutable audit events and add a pre-merge preview/summary
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Automated cross-store assertions prove no essential data or references are lost and recycle/restore returns a consistent entity.

### Story: Meet Graph scale, restore and full-dataset semantics
Priority: P1
Source: Release backlog GRAPH-008 (repository and product audit, 16 July 2026). The UI must say when it shows a subset and never imply loaded rows are the complete case.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Restore meets its target; capped graphs are unmistakable; search/type actions and exports operate on the intended full dataset.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Profile and improve recycle-bin restore latency with a user-visible progress state and a measured target
Priority: P1
Estimate: 12h
Source: Release backlog GRAPH-008, task 1. Profile and improve recycle-bin restore latency with a user-visible progress state and a measured target.
Implement this bounded change under “Meet Graph scale, restore and full-dataset semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Profile and improve recycle-bin restore latency with a user-visible progress state and a measured target
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Restore meets its target; capped graphs are unmistakable; search/type actions and exports operate on the intended full dataset.

#### Task: Define supported graph sizes and stress-test load, search, selection, algorithms, merge and export
Priority: P1
Estimate: 12h
Source: Release backlog GRAPH-008, task 2. Define supported graph sizes and stress-test load, search, selection, algorithms, merge and export.
Implement this bounded change under “Meet Graph scale, restore and full-dataset semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define supported graph sizes and stress-test load, search, selection, algorithms, merge and export
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Restore meets its target; capped graphs are unmistakable; search/type actions and exports operate on the intended full dataset.

#### Task: Explain graph caps/filtering and faded relevance nodes; provide an explicit full-dataset search path
Priority: P1
Estimate: 4h
Source: Release backlog GRAPH-008, task 3. Explain graph caps/filtering and faded relevance nodes; provide an explicit full-dataset search path.
Implement this bounded change under “Meet Graph scale, restore and full-dataset semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Explain graph caps/filtering and faded relevance nodes; provide an explicit full-dataset search path
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Restore meets its target; capped graphs are unmistakable; search/type actions and exports operate on the intended full dataset.

#### Task: Make legend type selection query the full case rather than only the loaded cap (backlog BUG-015)
Priority: P1
Estimate: 8h
Source: Release backlog GRAPH-008, task 4. Make legend type selection query the full case rather than only the loaded cap (backlog BUG-015).
Implement this bounded change under “Meet Graph scale, restore and full-dataset semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make legend type selection query the full case rather than only the loaded cap (backlog BUG-015)
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Restore meets its target; capped graphs are unmistakable; search/type actions and exports operate on the intended full dataset.

#### Task: Split or worker-offload expensive layout/render tasks and set browser memory thresholds
Priority: P1
Estimate: 12h
Source: Release backlog GRAPH-008, task 5. Split or worker-offload expensive layout/render tasks and set browser memory thresholds.
Implement this bounded change under “Meet Graph scale, restore and full-dataset semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Split or worker-offload expensive layout/render tasks and set browser memory thresholds
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Restore meets its target; capped graphs are unmistakable; search/type actions and exports operate on the intended full dataset.

### Story: Streamline Timeline search and filters
Priority: P1
Source: Release backlog TIME-001 (repository and product audit, 16 July 2026). Keep the custom date range and add fast entity discovery while removing low-value preset clutter.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Users can find an entity and apply a custom date range without hidden state or toolbar overflow; preset buttons are gone.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add search within the Entities filter, including type/name/alias and result counts
Priority: P1
Estimate: 8h
Source: Release backlog TIME-001, task 1. Add search within the Entities filter, including type/name/alias and result counts.
Implement this bounded change under “Streamline Timeline search and filters”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add search within the Entities filter, including type/name/alias and result counts
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can find an entity and apply a custom date range without hidden state or toolbar overflow; preset buttons are gone.

#### Task: Remove 30d/90d/1yr presets; retain All and one accessible custom date-range control
Priority: P1
Estimate: 4h
Source: Release backlog TIME-001, task 2. Remove 30d/90d/1yr presets; retain All and one accessible custom date-range control.
Implement this bounded change under “Streamline Timeline search and filters”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove 30d/90d/1yr presets; retain All and one accessible custom date-range control
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- Users can find an entity and apply a custom date range without hidden state or toolbar overflow; preset buttons are gone.

#### Task: Keep search, type, entity and date filters visible/understandable at supported widths
Priority: P1
Estimate: 8h
Source: Release backlog TIME-001, task 3. Keep search, type, entity and date filters visible/understandable at supported widths.
Implement this bounded change under “Streamline Timeline search and filters”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep search, type, entity and date filters visible/understandable at supported widths
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can find an entity and apply a custom date range without hidden state or toolbar overflow; preset buttons are gone.

#### Task: Define whether filters apply to loaded or full data and show active-filter chips/counts
Priority: P1
Estimate: 8h
Source: Release backlog TIME-001, task 4. Define whether filters apply to loaded or full data and show active-filter chips/counts.
Implement this bounded change under “Streamline Timeline search and filters”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define whether filters apply to loaded or full data and show active-filter chips/counts
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Users can find an entity and apply a custom date range without hidden state or toolbar overflow; preset buttons are gone.

#### Task: Test keyboard search, clear/reset, zero results and thousands of entities
Priority: P1
Estimate: 6h
Source: Release backlog TIME-001, task 5. Test keyboard search, clear/reset, zero results and thousands of entities.
Implement this bounded change under “Streamline Timeline search and filters”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test keyboard search, clear/reset, zero results and thousands of entities
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Users can find an entity and apply a custom date range without hidden state or toolbar overflow; preset buttons are gone.

### Story: Redesign focused timelines and curation
Priority: P1
Source: Release backlog TIME-002 (repository and product audit, 16 July 2026). Replace ‘curate/focus/view’ ambiguity with one saved-timeline mental model and explicit selection actions.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A first-time user can create, edit, switch and delete a saved timeline without explanation from a developer.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Choose one user-facing term (for example Saved timeline) and update labels, help and empty states
Priority: P1
Estimate: 4h
Source: Release backlog TIME-002, task 1. Choose one user-facing term (for example Saved timeline) and update labels, help and empty states.
Implement this bounded change under “Redesign focused timelines and curation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Choose one user-facing term (for example Saved timeline) and update labels, help and empty states
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A first-time user can create, edit, switch and delete a saved timeline without explanation from a developer.

#### Task: Add Select all filtered, Clear selection and accurate selected/total counts
Priority: P1
Estimate: 8h
Source: Release backlog TIME-002, task 2. Add Select all filtered, Clear selection and accurate selected/total counts.
Implement this bounded change under “Redesign focused timelines and curation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add Select all filtered, Clear selection and accurate selected/total counts
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A first-time user can create, edit, switch and delete a saved timeline without explanation from a developer.

#### Task: Support create from selection, add/remove events, rename and delete with confirmation
Priority: P1
Estimate: 8h
Source: Release backlog TIME-002, task 3. Support create from selection, add/remove events, rename and delete with confirmation.
Implement this bounded change under “Redesign focused timelines and curation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Support create from selection, add/remove events, rename and delete with confirmation
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A first-time user can create, edit, switch and delete a saved timeline without explanation from a developer.

#### Task: Expose delete in the saved-timeline selector/management surface and handle deleting the active view
Priority: P1
Estimate: 8h
Source: Release backlog TIME-002, task 4. Expose delete in the saved-timeline selector/management surface and handle deleting the active view.
Implement this bounded change under “Redesign focused timelines and curation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Expose delete in the saved-timeline selector/management surface and handle deleting the active view
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A first-time user can create, edit, switch and delete a saved timeline without explanation from a developer.

#### Task: Protect unsaved curation on navigation/filter change and enforce owner/editor permissions
Priority: P1
Estimate: 8h
Source: Release backlog TIME-002, task 5. Protect unsaved curation on navigation/filter change and enforce owner/editor permissions.
Implement this bounded change under “Redesign focused timelines and curation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Protect unsaved curation on navigation/filter change and enforce owner/editor permissions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A first-time user can create, edit, switch and delete a saved timeline without explanation from a developer.

### Story: Prove date, time and provenance correctness
Priority: P0
Source: Release backlog TIME-003 (repository and product audit, 16 July 2026). Chronology must not silently invent precision or conflate event time with ingestion time.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Timeline order and displayed precision match the source fixtures, and every event opens its exact evidence support.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Model date precision, unknown/partial dates, event timezone and original textual value
Priority: P0
Estimate: 8h
Source: Release backlog TIME-003, task 1. Model date precision, unknown/partial dates, event timezone and original textual value.
Implement this bounded change under “Prove date, time and provenance correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Model date precision, unknown/partial dates, event timezone and original textual value
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Timeline order and displayed precision match the source fixtures, and every event opens its exact evidence support.

#### Task: Distinguish event date from file creation, extraction and ingestion dates in UI/export
Priority: P0
Estimate: 8h
Source: Release backlog TIME-003, task 2. Distinguish event date from file creation, extraction and ingestion dates in UI/export.
Implement this bounded change under “Prove date, time and provenance correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Distinguish event date from file creation, extraction and ingestion dates in UI/export
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Timeline order and displayed precision match the source fixtures, and every event opens its exact evidence support.

#### Task: Verify ordering around DST, midnight, mixed timezones and missing times
Priority: P0
Estimate: 6h
Source: Release backlog TIME-003, task 3. Verify ordering around DST, midnight, mixed timezones and missing times.
Implement this bounded change under “Prove date, time and provenance correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify ordering around DST, midnight, mixed timezones and missing times
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Timeline order and displayed precision match the source fixtures, and every event opens its exact evidence support.

#### Task: Show exact source citation and manual correction history for each event
Priority: P0
Estimate: 8h
Source: Release backlog TIME-003, task 4. Show exact source citation and manual correction history for each event.
Implement this bounded change under “Prove date, time and provenance correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show exact source citation and manual correction history for each event
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Timeline order and displayed precision match the source fixtures, and every event opens its exact evidence support.

#### Task: Add fixture-based backend/frontend regression tests and human review of representative cases
Priority: P0
Estimate: 8h
Source: Release backlog TIME-003, task 5. Add fixture-based backend/frontend regression tests and human review of representative cases.
Implement this bounded change under “Prove date, time and provenance correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add fixture-based backend/frontend regression tests and human review of representative cases
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Timeline order and displayed precision match the source fixtures, and every event opens its exact evidence support.

### Story: Finish court/client-ready Timeline exports
Priority: P1
Source: Release backlog TIME-004 (repository and product audit, 16 July 2026). Make PDF and CSV match filtered/selected/saved scope and the release export standard.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Exported event count and content exactly match the chosen source and render legibly across the fixture matrix.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Verify export source selection never silently includes events outside the chosen scope
Priority: P1
Estimate: 6h
Source: Release backlog TIME-004, task 1. Verify export source selection never silently includes events outside the chosen scope.
Implement this bounded change under “Finish court/client-ready Timeline exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify export source selection never silently includes events outside the chosen scope
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Exported event count and content exactly match the chosen source and render legibly across the fixture matrix.

#### Task: Apply the shared brand header/footer, case identity, generation time, author, confidentiality label and AI review statement
Priority: P1
Estimate: 8h
Source: Release backlog TIME-004, task 2. Apply the shared brand header/footer, case identity, generation time, author, confidentiality label and AI review statement.
Implement this bounded change under “Finish court/client-ready Timeline exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Apply the shared brand header/footer, case identity, generation time, author, confidentiality label and AI review statement
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Exported event count and content exactly match the chosen source and render legibly across the fixture matrix.

#### Task: Include exact source appendix and stable event identifiers
Priority: P1
Estimate: 8h
Source: Release backlog TIME-004, task 3. Include exact source appendix and stable event identifiers.
Implement this bounded change under “Finish court/client-ready Timeline exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Include exact source appendix and stable event identifiers
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Exported event count and content exactly match the chosen source and render legibly across the fixture matrix.

#### Task: Test page breaks, long summaries, fonts, non-Latin text, empty dates, 5k-event PDF limit and deterministic re-export
Priority: P1
Estimate: 6h
Source: Release backlog TIME-004, task 4. Test page breaks, long summaries, fonts, non-Latin text, empty dates, 5k-event PDF limit and deterministic re-export.
Implement this bounded change under “Finish court/client-ready Timeline exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test page breaks, long summaries, fonts, non-Latin text, empty dates, 5k-event PDF limit and deterministic re-export
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Exported event count and content exactly match the chosen source and render legibly across the fixture matrix.

#### Task: Add visual golden tests for compact/standard/detailed PDF modes
Priority: P1
Estimate: 8h
Source: Release backlog TIME-004, task 5. Add visual golden tests for compact/standard/detailed PDF modes.
Implement this bounded change under “Finish court/client-ready Timeline exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add visual golden tests for compact/standard/detailed PDF modes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Exported event count and content exactly match the chosen source and render legibly across the fixture matrix.

### Story: Scale Timeline interaction to supported case sizes
Priority: P1
Source: Release backlog TIME-005 (repository and product audit, 16 July 2026). Virtualisation, filtering and export must remain responsive with thousands of events.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The supported large-case fixture meets defined interaction and export thresholds without omissions or browser freezes.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Set supported event count and latency/memory thresholds
Priority: P1
Estimate: 8h
Source: Release backlog TIME-005, task 1. Set supported event count and latency/memory thresholds.
Implement this bounded change under “Scale Timeline interaction to supported case sizes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Set supported event count and latency/memory thresholds
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The supported large-case fixture meets defined interaction and export thresholds without omissions or browser freezes.

#### Task: Profile clustering, filtering, selection and scroll restoration with representative data
Priority: P1
Estimate: 6h
Source: Release backlog TIME-005, task 2. Profile clustering, filtering, selection and scroll restoration with representative data.
Implement this bounded change under “Scale Timeline interaction to supported case sizes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Profile clustering, filtering, selection and scroll restoration with representative data
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The supported large-case fixture meets defined interaction and export thresholds without omissions or browser freezes.

#### Task: Ensure client and server pagination/virtualisation do not omit filter/export results
Priority: P1
Estimate: 8h
Source: Release backlog TIME-005, task 3. Ensure client and server pagination/virtualisation do not omit filter/export results.
Implement this bounded change under “Scale Timeline interaction to supported case sizes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Ensure client and server pagination/virtualisation do not omit filter/export results
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The supported large-case fixture meets defined interaction and export thresholds without omissions or browser freezes.

#### Task: Test concurrent event corrections and saved-view edits
Priority: P1
Estimate: 6h
Source: Release backlog TIME-005, task 4. Test concurrent event corrections and saved-view edits.
Implement this bounded change under “Scale Timeline interaction to supported case sizes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test concurrent event corrections and saved-view edits
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The supported large-case fixture meets defined interaction and export thresholds without omissions or browser freezes.

#### Task: Provide loading, partial, retry and provider-degraded states
Priority: P1
Estimate: 8h
Source: Release backlog TIME-005, task 5. Provide loading, partial, retry and provider-degraded states.
Implement this bounded change under “Scale Timeline interaction to supported case sizes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Provide loading, partial, retry and provider-degraded states
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The supported large-case fixture meets defined interaction and export thresholds without omissions or browser freezes.

### Story: Expose and filter geocoding confidence and precision
Priority: P1
Source: Release backlog MAP-001 (repository and product audit, 16 July 2026). The data already carries confidence but the main Map does not let users interpret or filter it.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Users can identify and filter uncertain locations; approximate results never look exact.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Define confidence/precision levels and display them in marker popups/details/legend
Priority: P1
Estimate: 4h
Source: Release backlog MAP-001, task 1. Define confidence/precision levels and display them in marker popups/details/legend.
Implement this bounded change under “Expose and filter geocoding confidence and precision”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define confidence/precision levels and display them in marker popups/details/legend
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Users can identify and filter uncertain locations; approximate results never look exact.

#### Task: Add filter or review queue for exact, approximate, ambiguous and unverified locations
Priority: P1
Estimate: 8h
Source: Release backlog MAP-001, task 2. Add filter or review queue for exact, approximate, ambiguous and unverified locations.
Implement this bounded change under “Expose and filter geocoding confidence and precision”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add filter or review queue for exact, approximate, ambiguous and unverified locations
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can identify and filter uncertain locations; approximate results never look exact.

#### Task: Render approximate areas differently from exact pins and avoid false precision in coordinates
Priority: P1
Estimate: 8h
Source: Release backlog MAP-001, task 3. Render approximate areas differently from exact pins and avoid false precision in coordinates.
Implement this bounded change under “Expose and filter geocoding confidence and precision”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Render approximate areas differently from exact pins and avoid false precision in coordinates
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can identify and filter uncertain locations; approximate results never look exact.

#### Task: Show geocoding provider/query and manual correction history
Priority: P1
Estimate: 8h
Source: Release backlog MAP-001, task 4. Show geocoding provider/query and manual correction history.
Implement this bounded change under “Expose and filter geocoding confidence and precision”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show geocoding provider/query and manual correction history
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Users can identify and filter uncertain locations; approximate results never look exact.

#### Task: Test mixed confidence, duplicates, invalid coordinates and corrected locations
Priority: P1
Estimate: 6h
Source: Release backlog MAP-001, task 5. Test mixed confidence, duplicates, invalid coordinates and corrected locations.
Implement this bounded change under “Expose and filter geocoding confidence and precision”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test mixed confidence, duplicates, invalid coordinates and corrected locations
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Users can identify and filter uncertain locations; approximate results never look exact.

### Story: Remove non-V1 Map analysis surfaces
Priority: P1
Source: Release backlog MAP-002 (repository and product audit, 16 July 2026). Simplify the Map by removing Proximity and any unfinished routes/trails unless the scope decision gives them a tested user outcome.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The V1 Map contains only supported, working layers and actions; no placeholder or low-value analysis control is visible.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Remove Proximity toolbar, anchor state, radius panel and related dead code from the V1 build
Priority: P1
Estimate: 12h
Source: Release backlog MAP-002, task 1. Remove Proximity toolbar, anchor state, radius panel and related dead code from the V1 build.
Implement this bounded change under “Remove non-V1 Map analysis surfaces”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove Proximity toolbar, anchor state, radius panel and related dead code from the V1 build
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- The V1 Map contains only supported, working layers and actions; no placeholder or low-value analysis control is visible.

#### Task: Remove or feature-flag unused Route Analysis and the explicitly deferred Movement Trails placeholder
Priority: P1
Estimate: 8h
Source: Release backlog MAP-002, task 2. Remove or feature-flag unused Route Analysis and the explicitly deferred Movement Trails placeholder.
Implement this bounded change under “Remove non-V1 Map analysis surfaces”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove or feature-flag unused Route Analysis and the explicitly deferred Movement Trails placeholder
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- The V1 Map contains only supported, working layers and actions; no placeholder or low-value analysis control is visible.

#### Task: Clear persisted state/migrations and update help, tests and screenshots
Priority: P1
Estimate: 12h
Source: Release backlog MAP-002, task 3. Clear persisted state/migrations and update help, tests and screenshots.
Implement this bounded change under “Remove non-V1 Map analysis surfaces”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Clear persisted state/migrations and update help, tests and screenshots
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The V1 Map contains only supported, working layers and actions; no placeholder or low-value analysis control is visible.

#### Task: If any surface is retained, write its investigator outcome and full acceptance fixture before release
Priority: P1
Estimate: 4h
Source: Release backlog MAP-002, task 4. If any surface is retained, write its investigator outcome and full acceptance fixture before release.
Implement this bounded change under “Remove non-V1 Map analysis surfaces”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: If any surface is retained, write its investigator outcome and full acceptance fixture before release
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The V1 Map contains only supported, working layers and actions; no placeholder or low-value analysis control is visible.

### Story: Complete manual correction and provider-degraded behavior
Priority: P1
Source: Release backlog MAP-003 (repository and product audit, 16 July 2026). Investigators must be able to correct locations while the system remains useful when geocoding is unavailable.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Manual corrections survive reprocessing and provider outage produces an actionable degraded state, not silent disappearance.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Unify map pin, address search and entity location editing with undo/audit
Priority: P1
Estimate: 8h
Source: Release backlog MAP-003, task 1. Unify map pin, address search and entity location editing with undo/audit.
Implement this bounded change under “Complete manual correction and provider-degraded behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Unify map pin, address search and entity location editing with undo/audit
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Manual corrections survive reprocessing and provider outage produces an actionable degraded state, not silent disappearance.

#### Task: Add geocoder timeout/retry/backoff, cache policy, quota and cost controls
Priority: P1
Estimate: 8h
Source: Release backlog MAP-003, task 2. Add geocoder timeout/retry/backoff, cache policy, quota and cost controls.
Implement this bounded change under “Complete manual correction and provider-degraded behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add geocoder timeout/retry/backoff, cache policy, quota and cost controls
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Manual corrections survive reprocessing and provider outage produces an actionable degraded state, not silent disappearance.

#### Task: Show a clear degraded mode when tiles/geocoder are unavailable and retain known coordinates
Priority: P1
Estimate: 4h
Source: Release backlog MAP-003, task 3. Show a clear degraded mode when tiles/geocoder are unavailable and retain known coordinates.
Implement this bounded change under “Complete manual correction and provider-degraded behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show a clear degraded mode when tiles/geocoder are unavailable and retain known coordinates
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Manual corrections survive reprocessing and provider outage produces an actionable degraded state, not silent disappearance.

#### Task: Prevent AI reprocessing from overwriting investigator-verified coordinates
Priority: P1
Estimate: 8h
Source: Release backlog MAP-003, task 4. Prevent AI reprocessing from overwriting investigator-verified coordinates.
Implement this bounded change under “Complete manual correction and provider-degraded behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prevent AI reprocessing from overwriting investigator-verified coordinates
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Manual corrections survive reprocessing and provider outage produces an actionable degraded state, not silent disappearance.

#### Task: Name map/geocoding providers in privacy/subprocessor documentation
Priority: P1
Estimate: 4h
Source: Release backlog MAP-003, task 5. Name map/geocoding providers in privacy/subprocessor documentation.
Implement this bounded change under “Complete manual correction and provider-degraded behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Name map/geocoding providers in privacy/subprocessor documentation
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Manual corrections survive reprocessing and provider outage produces an actionable degraded state, not silent disappearance.

### Story: Validate Map scale, privacy and export behavior
Priority: P1
Source: Release backlog MAP-004 (repository and product audit, 16 July 2026). Large cases and sensitive location data need explicit performance and handling rules.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The large-location fixture remains usable and sensitive coordinates cannot leak through unauthorised export, logs or telemetry.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Cluster/virtualise markers and set supported marker-count thresholds
Priority: P1
Estimate: 12h
Source: Release backlog MAP-004, task 1. Cluster/virtualise markers and set supported marker-count thresholds.
Implement this bounded change under “Validate Map scale, privacy and export behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Cluster/virtualise markers and set supported marker-count thresholds
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The large-location fixture remains usable and sensitive coordinates cannot leak through unauthorised export, logs or telemetry.

#### Task: Test hidden types, heatmap, selection, side rail and fit bounds with large/duplicate datasets
Priority: P1
Estimate: 6h
Source: Release backlog MAP-004, task 2. Test hidden types, heatmap, selection, side rail and fit bounds with large/duplicate datasets.
Implement this bounded change under “Validate Map scale, privacy and export behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test hidden types, heatmap, selection, side rail and fit bounds with large/duplicate datasets
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The large-location fixture remains usable and sensitive coordinates cannot leak through unauthorised export, logs or telemetry.

#### Task: Define whether map screenshots/exports are V1 and apply access/audit/confidentiality controls
Priority: P1
Estimate: 8h
Source: Release backlog MAP-004, task 3. Define whether map screenshots/exports are V1 and apply access/audit/confidentiality controls.
Implement this bounded change under “Validate Map scale, privacy and export behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define whether map screenshots/exports are V1 and apply access/audit/confidentiality controls
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The large-location fixture remains usable and sensitive coordinates cannot leak through unauthorised export, logs or telemetry.

#### Task: Verify location data is excluded from logs/telemetry and follows case retention/export/delete
Priority: P1
Estimate: 6h
Source: Release backlog MAP-004, task 4. Verify location data is excluded from logs/telemetry and follows case retention/export/delete.
Implement this bounded change under “Validate Map scale, privacy and export behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify location data is excluded from logs/telemetry and follows case retention/export/delete
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The large-location fixture remains usable and sensitive coordinates cannot leak through unauthorised export, logs or telemetry.

#### Task: Test keyboard and non-pointer alternatives for marker selection/details
Priority: P1
Estimate: 6h
Source: Release backlog MAP-004, task 5. Test keyboard and non-pointer alternatives for marker selection/details.
Implement this bounded change under “Validate Map scale, privacy and export behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test keyboard and non-pointer alternatives for marker selection/details
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The large-location fixture remains usable and sensitive coordinates cannot leak through unauthorised export, logs or telemetry.

### Story: Regression-test Table as a full-case review surface
Priority: P1
Source: Release backlog TABLE-001 (repository and product audit, 16 July 2026). A polished appearance is not proof that search, sorting and export cover all case entities.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Table counts and exports match backend fixtures exactly across pagination and entity lifecycle changes.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Verify search, type filters, sorting and CSV export against the full dataset, not only loaded/capped rows
Priority: P1
Estimate: 6h
Source: Release backlog TABLE-001, task 1. Verify search, type filters, sorting and CSV export against the full dataset, not only loaded/capped rows.
Implement this bounded change under “Regression-test Table as a full-case review surface”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify search, type filters, sorting and CSV export against the full dataset, not only loaded/capped rows
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Table counts and exports match backend fixtures exactly across pagination and entity lifecycle changes.

#### Task: Test pagination/virtualisation, empty data, malformed properties, merged/recycled entities and relationship breadcrumbs
Priority: P1
Estimate: 6h
Source: Release backlog TABLE-001, task 2. Test pagination/virtualisation, empty data, malformed properties, merged/recycled entities and relationship breadcrumbs.
Implement this bounded change under “Regression-test Table as a full-case review surface”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test pagination/virtualisation, empty data, malformed properties, merged/recycled entities and relationship breadcrumbs
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Table counts and exports match backend fixtures exactly across pagination and entity lifecycle changes.

#### Task: Show stable entity IDs, confidence, verification state and provenance columns
Priority: P1
Estimate: 8h
Source: Release backlog TABLE-001, task 3. Show stable entity IDs, confidence, verification state and provenance columns.
Implement this bounded change under “Regression-test Table as a full-case review surface”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show stable entity IDs, confidence, verification state and provenance columns
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Table counts and exports match backend fixtures exactly across pagination and entity lifecycle changes.

#### Task: Preserve selection across pages only when behavior is explicit and safe
Priority: P1
Estimate: 8h
Source: Release backlog TABLE-001, task 4. Preserve selection across pages only when behavior is explicit and safe.
Implement this bounded change under “Regression-test Table as a full-case review surface”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Preserve selection across pages only when behavior is explicit and safe
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Table counts and exports match backend fixtures exactly across pagination and entity lifecycle changes.

#### Task: Add owner/editor/viewer/non-member permission coverage
Priority: P1
Estimate: 8h
Source: Release backlog TABLE-001, task 5. Add owner/editor/viewer/non-member permission coverage.
Implement this bounded change under “Regression-test Table as a full-case review surface”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add owner/editor/viewer/non-member permission coverage
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Table counts and exports match backend fixtures exactly across pagination and entity lifecycle changes.

### Story: Add auditable bulk edit and multi-entity merge
Priority: P1
Source: Release backlog TABLE-002 (repository and product audit, 16 July 2026). Speed up duplicate cleanup without turning bulk actions into a data-loss mechanism.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A multi-entity merge produces the same lossless audited result as the verified Graph flow and clearly states its scope.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Allow 2+ selected duplicates to open one merge preview with final name/type selection
Priority: P1
Estimate: 6h
Source: Release backlog TABLE-002, task 1. Allow 2+ selected duplicates to open one merge preview with final name/type selection.
Implement this bounded change under “Add auditable bulk edit and multi-entity merge”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Allow 2+ selected duplicates to open one merge preview with final name/type selection
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A multi-entity merge produces the same lossless audited result as the verified Graph flow and clearly states its scope.

#### Task: Preserve all facts, summaries, insights, aliases, sources and relationships with conflict review
Priority: P1
Estimate: 6h
Source: Release backlog TABLE-002, task 2. Preserve all facts, summaries, insights, aliases, sources and relationships with conflict review.
Implement this bounded change under “Add auditable bulk edit and multi-entity merge”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Preserve all facts, summaries, insights, aliases, sources and relationships with conflict review
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A multi-entity merge produces the same lossless audited result as the verified Graph flow and clearly states its scope.

#### Task: Make bulk property edits schema-aware, permission-checked and reversible/audited
Priority: P1
Estimate: 6h
Source: Release backlog TABLE-002, task 3. Make bulk property edits schema-aware, permission-checked and reversible/audited.
Implement this bounded change under “Add auditable bulk edit and multi-entity merge”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make bulk property edits schema-aware, permission-checked and reversible/audited
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A multi-entity merge produces the same lossless audited result as the verified Graph flow and clearly states its scope.

#### Task: Show full-case selection scope and prevent accidental operation on hidden rows
Priority: P1
Estimate: 12h
Source: Release backlog TABLE-002, task 4. Show full-case selection scope and prevent accidental operation on hidden rows.
Implement this bounded change under “Add auditable bulk edit and multi-entity merge”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show full-case selection scope and prevent accidental operation on hidden rows
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A multi-entity merge produces the same lossless audited result as the verified Graph flow and clearly states its scope.

#### Task: Reuse Graph merge integrity tests and refresh every dependent view after completion
Priority: P1
Estimate: 6h
Source: Release backlog TABLE-002, task 5. Reuse Graph merge integrity tests and refresh every dependent view after completion.
Implement this bounded change under “Add auditable bulk edit and multi-entity merge”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Reuse Graph merge integrity tests and refresh every dependent view after completion
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A multi-entity merge produces the same lossless audited result as the verified Graph flow and clearly states its scope.

### Bug: Bound betweenness centrality on production-size graphs
Priority: P0
Estimate: 12h
Betweenness centrality currently returns no result within 120 seconds on the 7.6k-node reference case and blocks the request synchronously (V2 Gap Assessment §5, BRG-007). Use a bounded approximate/sampled computation or an asynchronous job with progress and cancellation. This is alpha-blocking because one analysis request must not make the investigation service unavailable.

Acceptance criteria:
- The 7.6k-node fixture returns bounded results or starts an asynchronous job with visible progress and cancellation.
- No inline HTTP request remains blocked for longer than 10 seconds by betweenness calculation.
- Concurrent health and ordinary case requests remain responsive while the calculation runs.

## Epic: Cellebrite & Financial Investigation
Color: #7367a8
Restore the proven V1 mobile-forensics and financial capabilities on V2, migrate the real curated data, and reconcile every result against signed fixtures before alpha use.

### Story: Complete a V1-to-V2 Financial parity and scope matrix
Priority: P0
Source: Release backlog FIN-001 (repository and product audit, 16 July 2026). Replace an unbounded port request with a signed inventory of existing, missing, changed and intentionally dropped workflows.
Release gate: Before feature freeze. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A signed parity matrix defines exactly what ‘Financial V1 complete’ means and every retained gap has testable acceptance criteria.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Inventory V1 screenshots/routes/workflows against V2 transaction/intelligence modes, filters, corrections, categories, sub-transactions, charts…
Priority: P0
Estimate: 8h
Source: Release backlog FIN-001, task 1. Inventory V1 screenshots/routes/workflows against V2 transaction/intelligence modes, filters, corrections, categories, sub-transactions, charts and export.
Implement this bounded change under “Complete a V1-to-V2 Financial parity and scope matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Inventory V1 screenshots/routes/workflows against V2 transaction/intelligence modes, filters, corrections, categories, sub-transactions, charts and export
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A signed parity matrix defines exactly what ‘Financial V1 complete’ means and every retained gap has testable acceptance criteria.

#### Task: Interview the domain owner to rank missing workflows by release outcome
Priority: P0
Estimate: 4h
Source: Release backlog FIN-001, task 2. Interview the domain owner to rank missing workflows by release outcome.
Implement this bounded change under “Complete a V1-to-V2 Financial parity and scope matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Interview the domain owner to rank missing workflows by release outcome
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A signed parity matrix defines exactly what ‘Financial V1 complete’ means and every retained gap has testable acceptance criteria.

#### Task: Create a fixture and acceptance journey for every retained financial capability
Priority: P0
Estimate: 4h
Source: Release backlog FIN-001, task 3. Create a fixture and acceptance journey for every retained financial capability.
Implement this bounded change under “Complete a V1-to-V2 Financial parity and scope matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create a fixture and acceptance journey for every retained financial capability
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A signed parity matrix defines exactly what ‘Financial V1 complete’ means and every retained gap has testable acceptance criteria.

#### Task: Remove navigation/help for explicitly deferred functions
Priority: P0
Estimate: 4h
Source: Release backlog FIN-001, task 4. Remove navigation/help for explicitly deferred functions.
Implement this bounded change under “Complete a V1-to-V2 Financial parity and scope matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove navigation/help for explicitly deferred functions
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- A signed parity matrix defines exactly what ‘Financial V1 complete’ means and every retained gap has testable acceptance criteria.

#### Task: Convert each accepted gap into a linked implementation story before closing this decision
Priority: P0
Estimate: 12h
Source: Release backlog FIN-001, task 5. Convert each accepted gap into a linked implementation story before closing this decision.
Implement this bounded change under “Complete a V1-to-V2 Financial parity and scope matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Convert each accepted gap into a linked implementation story before closing this decision
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A signed parity matrix defines exactly what ‘Financial V1 complete’ means and every retained gap has testable acceptance criteria.

### Story: Secure and prove Financial data correctness
Priority: P0
Source: Release backlog FIN-002 (repository and product audit, 16 July 2026). Financial reads/writes require case authorisation and accounting-grade arithmetic/source traceability.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Unauthorised requests fail and every tested total/transaction ID/source matches the signed fixture ledger.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add authentication and case permission checks to every financial endpoint and mutation
Priority: P0
Estimate: 8h
Source: Release backlog FIN-002, task 1. Add authentication and case permission checks to every financial endpoint and mutation.
Implement this bounded change under “Secure and prove Financial data correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add authentication and case permission checks to every financial endpoint and mutation
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Unauthorised requests fail and every tested total/transaction ID/source matches the signed fixture ledger.

#### Task: Use decimal/currency-aware calculations; test negative/refund values, FX, missing dates, duplicates and rounding
Priority: P0
Estimate: 6h
Source: Release backlog FIN-002, task 2. Use decimal/currency-aware calculations; test negative/refund values, FX, missing dates, duplicates and rounding.
Implement this bounded change under “Secure and prove Financial data correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Use decimal/currency-aware calculations; test negative/refund values, FX, missing dates, duplicates and rounding
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Unauthorised requests fail and every tested total/transaction ID/source matches the signed fixture ledger.

#### Task: Add a stable human-reference transaction ID that persists in UI, notes and exports
Priority: P0
Estimate: 8h
Source: Release backlog FIN-002, task 3. Add a stable human-reference transaction ID that persists in UI, notes and exports.
Implement this bounded change under “Secure and prove Financial data correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add a stable human-reference transaction ID that persists in UI, notes and exports
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Unauthorised requests fail and every tested total/transaction ID/source matches the signed fixture ledger.

#### Task: Trace every value to file/page/quote and label inferred or manually corrected values
Priority: P0
Estimate: 8h
Source: Release backlog FIN-002, task 4. Trace every value to file/page/quote and label inferred or manually corrected values.
Implement this bounded change under “Secure and prove Financial data correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Trace every value to file/page/quote and label inferred or manually corrected values
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Unauthorised requests fail and every tested total/transaction ID/source matches the signed fixture ledger.

#### Task: Reconcile summary cards, charts, filtered totals and exports against known ledgers
Priority: P0
Estimate: 12h
Source: Release backlog FIN-002, task 5. Reconcile summary cards, charts, filtered totals and exports against known ledgers.
Implement this bounded change under “Secure and prove Financial data correctness”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Reconcile summary cards, charts, filtered totals and exports against known ledgers
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Unauthorised requests fail and every tested total/transaction ID/source matches the signed fixture ledger.

### Story: Improve Financial review ergonomics
Priority: P1
Source: Release backlog FIN-003 (repository and product audit, 16 July 2026). Keep search available on constrained screens and make client conversations referenceable.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Investigators can search and reference a transaction while the filter panel is closed, including on the minimum supported width.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Move the primary search field outside the collapsible filter panel and retain it at supported widths
Priority: P1
Estimate: 8h
Source: Release backlog FIN-003, task 1. Move the primary search field outside the collapsible filter panel and retain it at supported widths.
Implement this bounded change under “Improve Financial review ergonomics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Move the primary search field outside the collapsible filter panel and retain it at supported widths
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Investigators can search and reference a transaction while the filter panel is closed, including on the minimum supported width.

#### Task: Add visible stable transaction IDs and direct lookup by ID
Priority: P1
Estimate: 8h
Source: Release backlog FIN-003, task 2. Add visible stable transaction IDs and direct lookup by ID.
Implement this bounded change under “Improve Financial review ergonomics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add visible stable transaction IDs and direct lookup by ID
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Investigators can search and reference a transaction while the filter panel is closed, including on the minimum supported width.

#### Task: Preserve filters/search when opening details and make reset scope obvious
Priority: P1
Estimate: 4h
Source: Release backlog FIN-003, task 3. Preserve filters/search when opening details and make reset scope obvious.
Implement this bounded change under “Improve Financial review ergonomics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Preserve filters/search when opening details and make reset scope obvious
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Investigators can search and reference a transaction while the filter panel is closed, including on the minimum supported width.

#### Task: Review editable purpose/counterparty/notes flows for unsaved changes, concurrency and audit
Priority: P1
Estimate: 6h
Source: Release backlog FIN-003, task 4. Review editable purpose/counterparty/notes flows for unsaved changes, concurrency and audit.
Implement this bounded change under “Improve Financial review ergonomics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Review editable purpose/counterparty/notes flows for unsaved changes, concurrency and audit
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Investigators can search and reference a transaction while the filter panel is closed, including on the minimum supported width.

#### Task: Test keyboard navigation, dense tables and 200% zoom
Priority: P1
Estimate: 6h
Source: Release backlog FIN-003, task 5. Test keyboard navigation, dense tables and 200% zoom.
Implement this bounded change under “Improve Financial review ergonomics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test keyboard navigation, dense tables and 200% zoom
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Investigators can search and reference a transaction while the filter panel is closed, including on the minimum supported width.

### Story: Standardise Financial and cost-ledger exports
Priority: P1
Source: Release backlog FIN-004 (repository and product audit, 16 July 2026). Exports must be explainable, billable and consistent with visible filters.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Financial and cost-ledger exports reconcile to on-screen scope and are usable as stable client/court references.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add case identity/reference, applied filters, generation time, author, confidentiality and source provenance to PDF/CSV
Priority: P1
Estimate: 8h
Source: Release backlog FIN-004, task 1. Add case identity/reference, applied filters, generation time, author, confidentiality and source provenance to PDF/CSV.
Implement this bounded change under “Standardise Financial and cost-ledger exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add case identity/reference, applied filters, generation time, author, confidentiality and source provenance to PDF/CSV
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Financial and cost-ledger exports reconcile to on-screen scope and are usable as stable client/court references.

#### Task: Consolidate repeated cost-ledger ingestion line items by evidence/job while preserving an auditable detail appendix
Priority: P1
Estimate: 6h
Source: Release backlog FIN-004, task 2. Consolidate repeated cost-ledger ingestion line items by evidence/job while preserving an auditable detail appendix.
Implement this bounded change under “Standardise Financial and cost-ledger exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Consolidate repeated cost-ledger ingestion line items by evidence/job while preserving an auditable detail appendix
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Financial and cost-ledger exports reconcile to on-screen scope and are usable as stable client/court references.

#### Task: Add case filter/grouping and PDF export to Cost Ledger
Priority: P1
Estimate: 8h
Source: Release backlog FIN-004, task 3. Add case filter/grouping and PDF export to Cost Ledger.
Implement this bounded change under “Standardise Financial and cost-ledger exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add case filter/grouping and PDF export to Cost Ledger
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Financial and cost-ledger exports reconcile to on-screen scope and are usable as stable client/court references.

#### Task: Test wide tables, long values, currencies, totals, page breaks and deterministic regeneration
Priority: P1
Estimate: 6h
Source: Release backlog FIN-004, task 4. Test wide tables, long values, currencies, totals, page breaks and deterministic regeneration.
Implement this bounded change under “Standardise Financial and cost-ledger exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test wide tables, long values, currencies, totals, page breaks and deterministic regeneration
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Financial and cost-ledger exports reconcile to on-screen scope and are usable as stable client/court references.

#### Task: Audit every export and restrict it to authorised roles
Priority: P1
Estimate: 6h
Source: Release backlog FIN-004, task 5. Audit every export and restrict it to authorised roles.
Implement this bounded change under “Standardise Financial and cost-ledger exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Audit every export and restrict it to authorised roles
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Financial and cost-ledger exports reconcile to on-screen scope and are usable as stable client/court references.

### Story: Stress-test large financial cases
Priority: P1
Source: Release backlog FIN-005 (repository and product audit, 16 July 2026). Prove pagination, filtering, correction and export with thousands of transactions.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The signed large-ledger fixture meets thresholds with correct totals and no omitted/duplicated rows.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Set supported transaction counts and latency/memory/export thresholds
Priority: P1
Estimate: 8h
Source: Release backlog FIN-005, task 1. Set supported transaction counts and latency/memory/export thresholds.
Implement this bounded change under “Stress-test large financial cases”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Set supported transaction counts and latency/memory/export thresholds
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The signed large-ledger fixture meets thresholds with correct totals and no omitted/duplicated rows.

#### Task: Test server pagination and full-dataset filters/totals under concurrent ingestion
Priority: P1
Estimate: 6h
Source: Release backlog FIN-005, task 2. Test server pagination and full-dataset filters/totals under concurrent ingestion.
Implement this bounded change under “Stress-test large financial cases”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test server pagination and full-dataset filters/totals under concurrent ingestion
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The signed large-ledger fixture meets thresholds with correct totals and no omitted/duplicated rows.

#### Task: Profile charts and entity-flow tables for unnecessary full-data rendering
Priority: P1
Estimate: 8h
Source: Release backlog FIN-005, task 3. Profile charts and entity-flow tables for unnecessary full-data rendering.
Implement this bounded change under “Stress-test large financial cases”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Profile charts and entity-flow tables for unnecessary full-data rendering
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The signed large-ledger fixture meets thresholds with correct totals and no omitted/duplicated rows.

#### Task: Verify corrections and bulk categorisation under concurrent users
Priority: P1
Estimate: 6h
Source: Release backlog FIN-005, task 4. Verify corrections and bulk categorisation under concurrent users.
Implement this bounded change under “Stress-test large financial cases”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify corrections and bulk categorisation under concurrent users
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The signed large-ledger fixture meets thresholds with correct totals and no omitted/duplicated rows.

#### Task: Add interruption/retry behavior for long exports
Priority: P1
Estimate: 8h
Source: Release backlog FIN-005, task 5. Add interruption/retry behavior for long exports.
Implement this bounded change under “Stress-test large financial cases”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add interruption/retry behavior for long exports
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The signed large-ledger fixture meets thresholds with correct totals and no omitted/duplicated rows.

### Story: Create a Cellebrite V1-to-V2 parity matrix
Priority: P0
Source: Release backlog CELL-001 (repository and product audit, 16 July 2026). Define which Overview, contacts, communications, events, locations, files, graph and intersection workflows constitute release parity.
Release gate: Before feature freeze. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The signed matrix replaces the vague port request and all retained gaps are represented by testable stories/tasks.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Inventory V1 behavior against the current V2 tabs and APIs with screenshots and sample reports
Priority: P0
Estimate: 4h
Source: Release backlog CELL-001, task 1. Inventory V1 behavior against the current V2 tabs and APIs with screenshots and sample reports.
Implement this bounded change under “Create a Cellebrite V1-to-V2 parity matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Inventory V1 behavior against the current V2 tabs and APIs with screenshots and sample reports
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The signed matrix replaces the vague port request and all retained gaps are represented by testable stories/tasks.

#### Task: List supported UFDR/XML/ZIP formats and Cellebrite versions plus intentional exclusions
Priority: P0
Estimate: 8h
Source: Release backlog CELL-001, task 2. List supported UFDR/XML/ZIP formats and Cellebrite versions plus intentional exclusions.
Implement this bounded change under “Create a Cellebrite V1-to-V2 parity matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: List supported UFDR/XML/ZIP formats and Cellebrite versions plus intentional exclusions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The signed matrix replaces the vague port request and all retained gaps are represented by testable stories/tasks.

#### Task: Prioritise gaps with a domain owner and create one acceptance fixture per retained workflow
Priority: P0
Estimate: 8h
Source: Release backlog CELL-001, task 3. Prioritise gaps with a domain owner and create one acceptance fixture per retained workflow.
Implement this bounded change under “Create a Cellebrite V1-to-V2 parity matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prioritise gaps with a domain owner and create one acceptance fixture per retained workflow
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The signed matrix replaces the vague port request and all retained gaps are represented by testable stories/tasks.

#### Task: Review third-party format/library/licensing constraints
Priority: P0
Estimate: 6h
Source: Release backlog CELL-001, task 4. Review third-party format/library/licensing constraints.
Implement this bounded change under “Create a Cellebrite V1-to-V2 parity matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Review third-party format/library/licensing constraints
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The signed matrix replaces the vague port request and all retained gaps are represented by testable stories/tasks.

#### Task: Remove or label deferred features rather than shipping partial controls
Priority: P0
Estimate: 4h
Source: Release backlog CELL-001, task 5. Remove or label deferred features rather than shipping partial controls.
Implement this bounded change under “Create a Cellebrite V1-to-V2 parity matrix”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove or label deferred features rather than shipping partial controls
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- The signed matrix replaces the vague port request and all retained gaps are represented by testable stories/tasks.

### Story: Harden Cellebrite ingestion and deletion
Priority: P1
Source: Release backlog CELL-002 (repository and product audit, 16 July 2026). Mobile reports are large, nested and sensitive; partial processing must not leave cross-store orphans.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Every fixture either imports deterministically or fails cleanly; deleting/re-ingesting a report leaves no orphans or duplicate intelligence.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Test representative, very large, partial, corrupt and duplicate reports plus cancellation/re-ingestion
Priority: P1
Estimate: 6h
Source: Release backlog CELL-002, task 1. Test representative, very large, partial, corrupt and duplicate reports plus cancellation/re-ingestion.
Implement this bounded change under “Harden Cellebrite ingestion and deletion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test representative, very large, partial, corrupt and duplicate reports plus cancellation/re-ingestion
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Every fixture either imports deterministically or fails cleanly; deleting/re-ingesting a report leaves no orphans or duplicate intelligence.

#### Task: Make report identity/idempotency explicit and remove the unsafe ‘Replace duplicate report’ shortcut from general upload
Priority: P1
Estimate: 8h
Source: Release backlog CELL-002, task 2. Make report identity/idempotency explicit and remove the unsafe ‘Replace duplicate report’ shortcut from general upload.
Implement this bounded change under “Harden Cellebrite ingestion and deletion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make report identity/idempotency explicit and remove the unsafe ‘Replace duplicate report’ shortcut from general upload
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every fixture either imports deterministically or fails cleanly; deleting/re-ingesting a report leaves no orphans or duplicate intelligence.

#### Task: Verify attachments, thumbnails and raw files remain linked and authorised
Priority: P1
Estimate: 6h
Source: Release backlog CELL-002, task 3. Verify attachments, thumbnails and raw files remain linked and authorised.
Implement this bounded change under “Harden Cellebrite ingestion and deletion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify attachments, thumbnails and raw files remain linked and authorised
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Every fixture either imports deterministically or fails cleanly; deleting/re-ingesting a report leaves no orphans or duplicate intelligence.

#### Task: Implement coordinated delete/recycle across Postgres, Neo4j, Chroma and file storage
Priority: P1
Estimate: 16h
Source: Release backlog CELL-002, task 4. Implement coordinated delete/recycle across Postgres, Neo4j, Chroma and file storage.
Implement this bounded change under “Harden Cellebrite ingestion and deletion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Implement coordinated delete/recycle across Postgres, Neo4j, Chroma and file storage
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every fixture either imports deterministically or fails cleanly; deleting/re-ingesting a report leaves no orphans or duplicate intelligence.

#### Task: Retain source hashes, parser version, timezone assumptions and ingest manifest
Priority: P1
Estimate: 8h
Source: Release backlog CELL-002, task 5. Retain source hashes, parser version, timezone assumptions and ingest manifest.
Implement this bounded change under “Harden Cellebrite ingestion and deletion”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Retain source hashes, parser version, timezone assumptions and ingest manifest
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every fixture either imports deterministically or fails cleanly; deleting/re-ingesting a report leaves no orphans or duplicate intelligence.

### Story: Validate Cellebrite search, identity and timezone semantics
Priority: P1
Source: Release backlog CELL-003 (repository and product audit, 16 July 2026). Phone identity, aliases and timestamps must stay consistent across tabs and reports.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Known fixture queries return the expected people, messages, events and intersections with unambiguous source/time semantics.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Verify phone/email/app identity normalisation, alias merge and duplicate-contact handling
Priority: P1
Estimate: 6h
Source: Release backlog CELL-003, task 1. Verify phone/email/app identity normalisation, alias merge and duplicate-contact handling.
Implement this bounded change under “Validate Cellebrite search, identity and timezone semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify phone/email/app identity normalisation, alias merge and duplicate-contact handling
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Known fixture queries return the expected people, messages, events and intersections with unambiguous source/time semantics.

#### Task: Test message/call/event timezone conversion and preserve original timestamp/zone
Priority: P1
Estimate: 6h
Source: Release backlog CELL-003, task 2. Test message/call/event timezone conversion and preserve original timestamp/zone.
Implement this bounded change under “Validate Cellebrite search, identity and timezone semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test message/call/event timezone conversion and preserve original timestamp/zone
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Known fixture queries return the expected people, messages, events and intersections with unambiguous source/time semantics.

#### Task: Make global versus tab/thread search scope visible and fixture-tested
Priority: P1
Estimate: 6h
Source: Release backlog CELL-003, task 3. Make global versus tab/thread search scope visible and fixture-tested.
Implement this bounded change under “Validate Cellebrite search, identity and timezone semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make global versus tab/thread search scope visible and fixture-tested
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known fixture queries return the expected people, messages, events and intersections with unambiguous source/time semantics.

#### Task: Validate multi-report intersections against known contacts/events/locations
Priority: P1
Estimate: 6h
Source: Release backlog CELL-003, task 4. Validate multi-report intersections against known contacts/events/locations.
Implement this bounded change under “Validate Cellebrite search, identity and timezone semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Validate multi-report intersections against known contacts/events/locations
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Known fixture queries return the expected people, messages, events and intersections with unambiguous source/time semantics.

#### Task: Ensure every result links to its source report/item/attachment
Priority: P1
Estimate: 8h
Source: Release backlog CELL-003, task 5. Ensure every result links to its source report/item/attachment.
Implement this bounded change under “Validate Cellebrite search, identity and timezone semantics”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Ensure every result links to its source report/item/attachment
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known fixture queries return the expected people, messages, events and intersections with unambiguous source/time semantics.

### Story: Meet Cellebrite performance and export targets
Priority: P1
Source: Release backlog CELL-004 (repository and product audit, 16 July 2026). Large reports must not freeze the browser or silently truncate results.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The large mobile-report fixture processes and remains navigable within measured thresholds with no silent truncation.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Set supported report size/event/message/file counts and processing targets
Priority: P1
Estimate: 8h
Source: Release backlog CELL-004, task 1. Set supported report size/event/message/file counts and processing targets.
Implement this bounded change under “Meet Cellebrite performance and export targets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Set supported report size/event/message/file counts and processing targets
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The large mobile-report fixture processes and remains navigable within measured thresholds with no silent truncation.

#### Task: Virtualise/paginate heavy lists and profile Overview, Contact feed, communications, timeline, locations and graph
Priority: P1
Estimate: 12h
Source: Release backlog CELL-004, task 2. Virtualise/paginate heavy lists and profile Overview, Contact feed, communications, timeline, locations and graph.
Implement this bounded change under “Meet Cellebrite performance and export targets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Virtualise/paginate heavy lists and profile Overview, Contact feed, communications, timeline, locations and graph
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The large mobile-report fixture processes and remains navigable within measured thresholds with no silent truncation.

#### Task: Test cancellation, refresh during processing and provider/worker restart
Priority: P1
Estimate: 6h
Source: Release backlog CELL-004, task 3. Test cancellation, refresh during processing and provider/worker restart.
Implement this bounded change under “Meet Cellebrite performance and export targets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test cancellation, refresh during processing and provider/worker restart
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The large mobile-report fixture processes and remains navigable within measured thresholds with no silent truncation.

#### Task: Define and test authorised exports with filters, stable IDs, provenance and confidentiality
Priority: P1
Estimate: 6h
Source: Release backlog CELL-004, task 4. Define and test authorised exports with filters, stable IDs, provenance and confidentiality.
Implement this bounded change under “Meet Cellebrite performance and export targets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define and test authorised exports with filters, stable IDs, provenance and confidentiality
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The large mobile-report fixture processes and remains navigable within measured thresholds with no silent truncation.

#### Task: Add visible cap/partial-result indicators wherever limits apply
Priority: P1
Estimate: 8h
Source: Release backlog CELL-004, task 5. Add visible cap/partial-result indicators wherever limits apply.
Implement this bounded change under “Meet Cellebrite performance and export targets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add visible cap/partial-result indicators wherever limits apply
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The large mobile-report fixture processes and remains navigable within measured thresholds with no silent truncation.

### Bug: NaN-safe financial aggregates with visible exclusion counts
Priority: P0
Estimate: 6h
A single stored NaN amount turns `sum()`/`max()` into NaN, which `safe_float` flattens to $0 — v1's flagship case shows $0 volume across 43,805 transactions and v2 has the identical code path; 144 unparseable amounts also silently vanish from every aggregate (gap assessment §5, BRG-003). Filter non-finite amounts inside the Cypher aggregates for summary, volume, and entities, and return the excluded count — no silent truncation.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-003, gap assessment §5). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Financial summary on a case containing one NaN amount returns correct nonzero totals
- Response carries `excluded_count` for non-finite/unparseable amounts
- UI shows "N amounts could not be parsed" whenever the count is nonzero

### Story: Ingester writes every artifact type v1 does
Priority: P1
v2's ingester writes ~38% of v1's artifact coverage (gap assessment §3.2, BRG-010). Missing writers: Notification, Voicemail, NetworkUsage, Autofill, InstalledApplication, SIMData, Journey, DictionaryWord, SocialMediaActivity, ChatActivity, FileDownload, FileUpload, Note, DeviceConnectivity, Cookie, LogEntry, MotionActivity/ActivitySensorData, AppsUsageLog, User. v1 reference: `ingestion/scripts/cellebrite/neo4j_writer.py:1175-1224` dispatch.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-010, gap assessment §3.2, gap assessment §3.2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Writer dispatch parity with v1's dispatch table
- Reconciliation report shows no parsed-but-unwritten model types on a fixture ingest

#### Task: Port comms and personal-artifact writers
Priority: P1
Estimate: 14h
Port the writers closest to investigative value first: Notification, Voicemail, ChatActivity, SocialMediaActivity, Note, DictionaryWord, FileDownload, FileUpload (BRG-010). Match v1's node labels, properties, and relationship shapes exactly so downstream surfaces port cleanly.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-010, gap assessment §3.2, gap assessment §3.2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each listed artifact type in the fixture UFED report produces nodes matching v1's schema
- Counts per type match v1's ingest of the same fixture

#### Task: Port device and system-artifact writers
Priority: P1
Estimate: 12h
Port the remaining writers: Autofill, InstalledApplication, SIMData, Journey, DeviceConnectivity, Cookie, LogEntry, MotionActivity/ActivitySensorData, AppsUsageLog, User (BRG-010).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-010, gap assessment §3.2, gap assessment §3.2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each listed artifact type in the fixture produces nodes matching v1's schema
- Reconciliation shows zero parsed-but-unwritten types across the full dispatch table

#### Bug: NetworkUsage parsed then silently dropped
Priority: P1
Estimate: 4h
v2 parses NetworkUsage models and then never writes them — the worst kind of silent data loss because the parse succeeds (gap assessment §3.2/§6, BRG-010). Wire the parsed models into the writer dispatch.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-010, gap assessment §3.2, gap assessment §3.2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- NetworkUsage fixture rows appear in Neo4j after ingest
- Reconciliation counts parsed = written for NetworkUsage

### Story: Ingest fails loudly instead of writing bad data
Priority: P1
Four gates v1 added after real production failures are missing from v2's ingester (gap assessment §3.2, BRG-011; v1 refs `35fe75a`, `3040228`, `9f0f397`, `1b8a32c`). Without them, malformed or unusual inputs produce quietly wrong data rather than actionable errors.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-011, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each gate has a fixture test reproducing the original real-world failure
- All four gates fire visibly (hard error or warning) rather than writing silently wrong data

#### Task: Hard-fail on empty phone_numbers + under-count coverage warnings
Priority: P1
Estimate: 5h
Port the empty-`phone_numbers` hard-fail (broken investigative views otherwise) and the under-count coverage warnings that flag when written counts fall short of parsed counts (BRG-011 gates a and d).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-011, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Ingesting a report with an empty phone_numbers set fails with an actionable error, writing nothing
- A fixture with deliberately dropped rows produces a visible under-count warning

#### Task: IMEI/MSISDN-fallback report dedup keys
Priority: P1
Estimate: 4h
Today two numberless devices collide as "duplicates" — a wrong dedupe verdict can overwrite a distinct device (BRG-011 gate b). Port v1's IMEI/MSISDN-fallback key scheme.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-011, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Two numberless-device fixtures ingest as two distinct reports
- A genuine duplicate report is still detected as a duplicate

#### Task: Nested-XML BFS detection to depth 6 (DKT-34)
Priority: P1
Estimate: 4h
Real customer zips arrive as `Report/Report/*.xml` and are undetectable by v2 today (BRG-011 gate c, DKT-34). Port v1's breadth-first XML detection to depth 6.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-011, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- The DKT-34 nested-zip fixture is detected and ingested
- Flat-layout reports still ingest unchanged

### Story: Contacts resolve to the correct identities across sources
Priority: P1
v2's identity keying is a US-centric regex and it lacks v1's owner inference and alias preservation, so people conflate, split, or show as "Unknown" (gap assessment §3.2, BRG-012/013/014). These encode explicit product decisions already made — port as specified.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-012, BRG-013, BRG-014, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Identity-key regression fixtures pass (no conflation, no splits)
- FFS-extracted phones get a correct owner identity

#### Task: Port owner-number/name inference for FFS extractions
Priority: P1
Estimate: 12h
Full-file-system extractions omit the header MSISDN and have an empty IsPhoneOwner party; v1 infers the owner from comms Account fields behind a 3-tier gate (BRG-012, v1 ref `f4cae84`). Must never overwrite a manually-set owner.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-012, BRG-013, BRG-014, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- FFS fixture ingests with the correct inferred owner
- A case with a manually-set owner is left untouched by inference

#### Task: International phone normalization via libphonenumber E.164
Priority: P1
Estimate: 6h
v2 keys identities with a US-centric regex, so international numbers conflate or split contacts — an identity-conflation risk in evidence (BRG-013, v1 refs `8e730a4`, `backend/services/phone_normalise.py`). Replace the regex with libphonenumber E.164 keys everywhere it was used.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-012, BRG-013, BRG-014, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- E.164 keys used at every former regex site
- International-number regression fixtures produce stable, non-conflated identity keys

#### Task: Contact-alias preservation + WhatsApp identity unification
Priority: P1
Estimate: 10h
Port `_merge_contact_entry` alias preservation (all saved names per contact retained) and WhatsApp account-number unification to the person (BRG-014, v1 refs `8510947`, `92d9cc6`).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-012, BRG-013, BRG-014, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Multi-alias fixture retains every saved name after ingest
- WhatsApp fixture resolves the account number to one person identity

### Task: Geo ingestion — geotag harvest, coordinate coverage, fast reverse-geocoder
Priority: P1
Estimate: 12h
Photo-EXIF geotag harvest and all-coordinates capture are missing; v2's reverse geocoder runs in the fork-per-call mode that collapsed v1 ingest to under 1 model/s, and the live geocoder isn't running at all (gap assessment §3.6, BRG-015; v1 refs `b47e60f`, `09bd9a8`, `e072fb2`). Port RGeocoder mode=1 with the coordinate cache and stand up the live geocoder service.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-015, gap assessment §3.6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Geotagged-photo fixture produces map points after ingest
- RGeocoder mode=1 with coordinate cache is in place; ingest of a location-dense fixture completes at v1-comparable speed
- `geocoder/status` reports ready

### Task: Media linkage — trust Cellebrite metadata type over file extension
Priority: P1
Estimate: 3h
Port v1's fix (ref `fc20c20`) so media with odd extensions still links to its message (BRG-016).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-016). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Odd-extension audio/media fixture links to its parent message
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Task: Re-ingest the UFED corpus into v2 and reconcile against v1
Priority: P1
Estimate: 12h
Blocked by every other ticket in this epic. Re-ingest the corpus through v2's pipeline and validate per-report counts against v1 using the reconciliation framework that exists on both sides (BRG-017). Run sequentially with memory monitoring per the C2-zombie lesson. This unblocks all cellebrite QA — v2 currently has zero PhoneReports.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-017). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Per-report reconciliation matches v1's counts per artifact type, or every difference is explained and logged
- Ingest runs sequentially with memory monitoring and no host instability

### Story: Investigator sees a correct, complete phone timeline
The cellebrite timeline "second wave" (BRG-018, split per the roadmap's instruction). Today owner-sent messages show "Unknown", timestamps stored in UTC render wrong day boundaries without the TZ work, and multi-source rows duplicate. v1 refs: `0da927e`, `fd82ea7`, `55d82be`/`71c1a1b`/`81520e0`, `3cf58bf`, `504bcde`/`debb7cf`, `8c45053`, `8d3aeb3`/`4a74c1c`/`db56c5e`.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-018, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- The DKT-23 duplicate repro and the owner-attribution repro both pass on v2 with re-ingested data
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Owner + recipient attribution on timeline events
Estimate: 10h
Owner-sent messages currently show "Unknown" on v2's cellebrite timeline, and workspace-timeline communication rows lost v1's synthesized "sender → recipient" party attribution, showing a raw summary instead (gap assessment §3.2 and §3.5). Port v1's attribution so both surfaces name the parties.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-018, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Owner-sent messages show the owner as sender on the cellebrite timeline
- Workspace timeline communication rows show "sender → recipient" party attribution

#### Task: Timezone-correct timeline display
Estimate: 10h
Timestamps are stored UTC; without v1's `cellebriteTime` util and TZ selector, day boundaries and date filters are wrong (gap assessment §3.2). Port the util and selector across timeline surfaces.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-018, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Events near midnight fall on the correct local day for the selected timezone
- Date-range filters return the same event sets as v1 for the same fixture and TZ

#### Bug: Multi-source duplicate rows in evidence views
Estimate: 8h
The same message ingested from multiple sources renders as duplicate rows (gap assessment §3.2, part of BRG-018; DKT-23 family). Port v1's multi-source duplicate collapse.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-018, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- The DKT-23 duplicate repro shows one collapsed row with source provenance
- Distinct-but-similar messages are never merged

#### Task: Inline media on timeline rows
Estimate: 12h
Port thumbnails, voice-note player, and full message bodies inline on timeline rows (BRG-018).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-018, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Image rows show thumbnails that open full-size
- Voice notes play inline; full bodies render without truncation

#### Task: Virtualized rows + keyset /events pagination + envelope endpoint
Estimate: 12h
Port v1's virtualized row rendering and keyset pagination with the envelope endpoint so large timelines scroll smoothly and completely (BRG-018). Pairs with the honest-totals work in the Provenance epic — the v2 timeline client currently stops after 100 pages × 2,000 rows silently.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-018, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A 100k+-event timeline scrolls without jank and loads to the true end
- Envelope endpoint returns honest totals used by the client

#### Task: Event-type coverage — Calendar, media-as-events, Autofill, Notification, Voicemail
Estimate: 8h
Surface the newly-written artifact types (from the ingestion epic) as timeline events, matching v1's event-type coverage (BRG-018; pairs with the artifact-writer story).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-018, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each listed type appears on the timeline with v1-equivalent rendering for the fixture corpus
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Story: Cross-phone graph shows direction, flow, and scale
v2 has the 331-line pre-rebuild snapshot of a view v1 rebuilt across ~30 commits (gap assessment §3.2, BRG-019, split per the roadmap). v1 refs: `49105bc`, `1b13d71`, `3828e41`, `546e1ab`, `2395fb4`, `9942414` era; cap-lift `5bca0a8`.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-019, gap assessment §3.2, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Direction/flow view works on a re-ingested multi-phone case with no silent caps
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Directional edges + flow view
Estimate: 12h
Port directional edges and the flow view so the graph shows who contacted whom, not just that they're linked.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-019, gap assessment §3.2, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Edges render with direction on a multi-phone fixture
- Flow view toggle matches v1's behavior

#### Task: Time-axis layout
Estimate: 8h
Port the time-axis layout mode that positions communication along a temporal axis.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-019, gap assessment §3.2, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Time-axis mode renders the fixture case with events ordered correctly in time
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Server-side graph search, subgraph, and expand-neighbours
Estimate: 12h
Port server-side search + subgraph retrieval and expand-neighbours/pivot so large cases don't ship the whole graph to the client.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-019, gap assessment §3.2, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Searching a person returns a focused subgraph
- Expand-neighbours grows the view one hop at a time on the re-ingested corpus

#### Task: Path-flow between two people + edge-click event detail
Estimate: 10h
Port the two-person path-flow query and the edge-click drill-down to underlying events.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-019, gap assessment §3.2, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Selecting two people renders the communication paths between them
- Clicking an edge lists the underlying events

#### Task: Honest cap counter on the cross-phone graph
Estimate: 4h
v2 hard-caps at 200 persons / 300 links with no user signal; v1 lifted its cap with an honest counter (v1 ref `5bca0a8`; gap assessment §6). Remove the silent cap and show the counter. Ties to the truncation sweep in the Provenance epic.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-019, gap assessment §3.2, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A case exceeding the old caps renders fully or shows an explicit "showing X of Y" counter
- No silent truncation remains in the graph payload path

### Story: Investigator can mark key events and produce a client report
The callouts → client-report workflow and the per-device forensic Report tab with PDF are absent in v2 — one of the two missing tabs (gap assessment §3.2/§3.4, BRG-020; v1 refs `6360848`, `87ae085`, `864d7fa`, `d18eea7`). This is a client-deliverable workflow — coordinate with the case-export story so report generation lands on one foundation.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-020, gap assessment §3.2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Mark key events → assembled report → PDF round-trip works on v2
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Callouts — mark and manage key events
Estimate: 12h
Port the callout endpoints and the mark-key-events UI across cellebrite surfaces.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-020, gap assessment §3.2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Events can be marked/unmarked as callouts from timeline and comms views
- Callouts persist and list per device and per case

#### Task: Report tab — per-device forensic profile + PDF assembly
Estimate: 16h
Port the Report tab (per-device forensic profile) and the assembled client report with PDF output, aligning the PDF path with v2's server-side export foundation rather than v1's frontend-side generation.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-020, gap assessment §3.2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Report tab renders the per-device forensic profile on re-ingested data
- Assembled client report exports to PDF containing the marked callouts

### Story: Unified Search & Discovery center
The Search & Discovery center — the other missing tab — searches across artifact types with typeahead (gap assessment §3.2, BRG-021; v1 ref `b6f5023` + typeahead/search-help commits). Includes the DKT-42 lesson: the search haystack must lowercase participant names.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-021, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- The DKT-42 repro (contact-name search finds a generically-titled 1:1 chat) passes on v2
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Unified search backend across artifact types
Estimate: 14h
Port the cross-artifact search service including the DKT-42 lowercase-participant-names fix and comms-search coverage fixes from the post-May DKT batch.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-021, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Search returns matches across all written artifact types on the fixture corpus
- DKT-42 repro passes; comms searches that previously missed now hit

#### Task: Search & Discovery UI with typeahead and search help
Estimate: 10h
Port the Search & Discovery tab UI: typeahead, search-help affordances, and result navigation into the underlying views.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-021, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Tab exists on v2 with typeahead suggestions
- Selecting a result navigates to the correct artifact view

### Story: Identity resolution and per-device naming
Investigator-asserted person merges (audited, reversible), person search, per-device perspective as default with opt-in rollup, and number-alongside-name via shared PersonName everywhere (gap assessment §3.2, BRG-022; v1 refs `72dfa27`, `ac75970`, `d4ec444`, `06f10d0`, `9c2fd9c`, `b51604d`). These encode explicit product decisions already made — port as specified, don't re-litigate.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-022, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Merge/unmerge is audited and reversible; every cellebrite surface shows number with name
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Audited person merge/unmerge + person search
Estimate: 14h
Port investigator-asserted person merges with audit trail and reversibility, plus person search.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-022, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Merging two persons is recorded with actor and timestamp and can be reversed cleanly
- Person search finds identities by any alias or number

#### Task: Per-device naming defaults + number-alongside-name
Estimate: 10h
Port per-device perspective as the default with opt-in rollup, and the shared PersonName rendering (number alongside name) across all cellebrite surfaces.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-022, gap assessment §3.2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Contact naming defaults to the per-device perspective with a working rollup toggle
- Every cellebrite surface shows the number with the name

### Task: Locations at full scale
Estimate: 12h
Port the canvas all-points layer, lean fetch, removal of the 5,000-point cap (silent truncation of location evidence today), and the map-freeze fix (BRG-023; v1 refs `dc5103e`, `09bd9a8`, `0111bb4`).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-023). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- The full location set renders on the re-ingested corpus without a cap
- Map remains responsive on the location-dense fixture

### Task: DKT regression verification pass
Estimate: 10h
After the timeline, graph, and search stories land, re-run every post-May DKT repro on v2 — DKT-23, 27, 29, 31, 34, 42 plus the comms-center fixes (BRG-024). ~12 user-reported fixes would regress silently otherwise; most should be covered by the ports — this ticket is the proof.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-024). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each DKT repro is documented as passing on v2
- Any repro that fails gets a ticket before this closes

### Task: Decide comms tally / "most contacted" (DKT-43)
Priority: P3
Estimate: 3h
DKT-43 was built then reverted on v1 main itself (BRG-025). Decide with Neil whether The Platform wants it; the envelope-path implementation exists on branch `docket/DKT-43` if yes.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-025). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded; if yes, the branch implementation is scheduled as a follow-up ticket; if no, the drop is documented
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Task: Port the data_version audit filter, reconciled with v2's mode axis
Estimate: 14h
v1's `data_version=legacy|v2` separates original extractions from re-audited ones on the transaction list and PDF export; v2 instead separates evidence-backed vs LLM-inferred via `mode=transactions|intelligence` (gap assessment §3.1, BRG-026; v1 ref `d03757b` era). These answer different questions — keep both axes and specify their combined behavior.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-026, gap assessment §3.1). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Both filters work independently on the transaction list and export
- Combined-filter behavior is specified and covered by tests

### Task: Payments/Receipts semantics
Estimate: 8h
v1 computes sign-based Payments (negative amounts) vs Receipts (positive); v2 still shows the pre-sprint "Money In / Money Out" cards with no sign convention (gap assessment §3.1, BRG-027; v1 ref `c4fe355`). Includes the sign-normalization convention from TRANSACTION_REPROCESS_PLAN §3.0.1.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-027, gap assessment §3.1). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Summary cards and export match v1's Payments/Receipts semantics on migrated data
- Sign normalization follows the documented convention

### Story: One financial export offering both stacks' perspectives
v1's export gained the Money Flow perspective, per-entity breakdown pages, a section picker, and embedded volume/category charts; v2 independently built provenance labels, entity-flow tables, and grouping (gap assessment §3.1, BRG-028). Don't port v1's file wholesale — specify the union on v2's export foundation.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-028, gap assessment §3.1). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- One export offers both v1's and v2's perspectives; corrected amounts keep the ✎ marker and footnotes; section picker works
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Specify the union export
Estimate: 4h
Write the section-by-section spec merging v1's sprint design with v2's provenance labels and entity-flow tables, on v2's export service.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-028, gap assessment §3.1). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Spec reviewed and agreed; every v1 sprint section and v2 addition is mapped in or explicitly excluded
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Implement Money Flow perspective, per-entity pages, and section picker
Estimate: 16h
Build the v1 sprint sections into v2's export service per the spec (BRG-028).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-028, gap assessment §3.1). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Money Flow perspective section renders on real data
- Per-entity breakdown pages generate per the spec; section picker includes/excludes sections correctly

#### Task: Embedded charts + correction footnotes
Estimate: 8h
Add the embedded volume/category charts and preserve corrected-amount markers (✎) with footnotes in the export.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-028, gap assessment §3.1). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Charts render embedded in the PDF
- Corrected amounts show ✎ with the correction reason footnoted

### Task: Decide CSV notes import + transaction ref IDs + auto-extract categories
Priority: P3
Estimate: 4h
Built for the reprocess sprint workflow (`/upload-notes`, ref IDs, auto-extract categories — gap assessment §3.1, BRG-029; v1 ref `7dbbe46`). Decide with Neil whether The Platform needs bulk notes import or whether it was sprint scaffolding.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-029, gap assessment §3.1). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded; if yes, a scoped port ticket is created; if no, the drop is documented
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Story: v2 has real transaction data
Priority: P1
v2 has zero statement-extracted transactions; its financial module can't be QA'd at all until data lands (gap assessment "second fact", BRG-030 — DECIDE first). Two paths: (a) migrate v1's curated Neo4j transaction subgraph (preserves the reprocess sprint's 10K+ re-extracted, categorized, audited transactions) or (b) re-extract from source statements through evidence-engine (clean but re-does months of curation). Roadmap recommendation: (a) — the curation and audit trail are the value.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-030). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Chosen path executed; v1/v2 totals reconcile; curation history (original_amount, correction_reason) intact
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Decide the transaction data path
Priority: P1
Estimate: 2h
Confirm path (a) vs (b) with Neil before any migration work starts — this blocks the epic's QA.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-030). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded with rationale
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Migrate the curated transaction subgraph and reconcile
Priority: P1
Estimate: 20h
Execute the chosen path (assumed (a)): migrate v1's curated transaction subgraph into v2, preserving audit fields, then reconcile totals against v1.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-030). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- v1/v2 transaction counts and totals reconcile, with differences explained
- original_amount and correction_reason survive intact on migrated transactions

## Epic: AI, Workspace, Reports & Exports
Color: #b64f82
Make AI output cited and controllable, preserve investigator work, and produce authorised, sanitised and consistently branded case deliverables.

### Story: Choose one Chat/Agent/side-rail information architecture
Priority: P0
Source: Release backlog AI-001 (repository and product audit, 16 July 2026). Clarify when users ask, investigate with tools, review artifacts and use the global side rail.
Release gate: Before feature freeze. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A new user can predict where to ask a question, run an investigation and find prior output; there are no competing chat histories.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Map current Chat page, Investigation Agent, right-rail Chat and report/artifact workflows
Priority: P0
Estimate: 4h
Source: Release backlog AI-001, task 1. Map current Chat page, Investigation Agent, right-rail Chat and report/artifact workflows.
Implement this bounded change under “Choose one Chat/Agent/side-rail information architecture”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Map current Chat page, Investigation Agent, right-rail Chat and report/artifact workflows
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A new user can predict where to ask a question, run an investigation and find prior output; there are no competing chat histories.

#### Task: User-test at least two coherent models and choose names, entry points and conversation ownership
Priority: P0
Estimate: 6h
Source: Release backlog AI-001, task 2. User-test at least two coherent models and choose names, entry points and conversation ownership.
Implement this bounded change under “Choose one Chat/Agent/side-rail information architecture”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: User-test at least two coherent models and choose names, entry points and conversation ownership
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A new user can predict where to ask a question, run an investigation and find prior output; there are no competing chat histories.

#### Task: Define whether the side rail shares threads/context with the full page and what selection scope it inherits
Priority: P0
Estimate: 4h
Source: Release backlog AI-001, task 3. Define whether the side rail shares threads/context with the full page and what selection scope it inherits.
Implement this bounded change under “Choose one Chat/Agent/side-rail information architecture”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define whether the side rail shares threads/context with the full page and what selection scope it inherits
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A new user can predict where to ask a question, run an investigation and find prior output; there are no competing chat histories.

#### Task: Remove duplicate/inconsistent routes and migrate existing conversations if needed
Priority: P0
Estimate: 8h
Source: Release backlog AI-001, task 4. Remove duplicate/inconsistent routes and migrate existing conversations if needed.
Implement this bounded change under “Choose one Chat/Agent/side-rail information architecture”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove duplicate/inconsistent routes and migrate existing conversations if needed
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- A new user can predict where to ask a question, run an investigation and find prior output; there are no competing chat histories.

#### Task: Update navigation, onboarding, permissions, analytics and end-to-end tests
Priority: P0
Estimate: 6h
Source: Release backlog AI-001, task 5. Update navigation, onboarding, permissions, analytics and end-to-end tests.
Implement this bounded change under “Choose one Chat/Agent/side-rail information architecture”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Update navigation, onboarding, permissions, analytics and end-to-end tests
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A new user can predict where to ask a question, run an investigation and find prior output; there are no competing chat histories.

### Story: Enforce a source-citation and AI-limitation contract
Priority: P0
Source: Release backlog AI-002 (repository and product audit, 16 July 2026). Material factual claims must link to exact evidence or state that support was not found.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Every tested material claim has an exact working citation or an explicit unsupported marker; warnings cannot be dismissed permanently.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Require file/page/chunk/quote citations for material claims and make each citation open the protected source location
Priority: P0
Estimate: 8h
Source: Release backlog AI-002, task 1. Require file/page/chunk/quote citations for material claims and make each citation open the protected source location.
Implement this bounded change under “Enforce a source-citation and AI-limitation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Require file/page/chunk/quote citations for material claims and make each citation open the protected source location
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every tested material claim has an exact working citation or an explicit unsupported marker; warnings cannot be dismissed permanently.

#### Task: Clearly separate retrieved evidence, model reasoning and investigator assertions
Priority: P0
Estimate: 8h
Source: Release backlog AI-002, task 2. Clearly separate retrieved evidence, model reasoning and investigator assertions.
Implement this bounded change under “Enforce a source-citation and AI-limitation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Clearly separate retrieved evidence, model reasoning and investigator assertions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every tested material claim has an exact working citation or an explicit unsupported marker; warnings cannot be dismissed permanently.

#### Task: Add a persistent human-review warning and prevent absence-of-evidence claims without appropriate qualification
Priority: P0
Estimate: 8h
Source: Release backlog AI-002, task 3. Add a persistent human-review warning and prevent absence-of-evidence claims without appropriate qualification.
Implement this bounded change under “Enforce a source-citation and AI-limitation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add a persistent human-review warning and prevent absence-of-evidence claims without appropriate qualification
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every tested material claim has an exact working citation or an explicit unsupported marker; warnings cannot be dismissed permanently.

#### Task: Handle deleted/recycled/broken sources and snapshot the citation context used for an answer
Priority: P0
Estimate: 8h
Source: Release backlog AI-002, task 4. Handle deleted/recycled/broken sources and snapshot the citation context used for an answer.
Implement this bounded change under “Enforce a source-citation and AI-limitation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Handle deleted/recycled/broken sources and snapshot the citation context used for an answer
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every tested material claim has an exact working citation or an explicit unsupported marker; warnings cannot be dismissed permanently.

#### Task: Add fixture-based answer/citation acceptance tests and unsupported-question tests
Priority: P0
Estimate: 8h
Source: Release backlog AI-002, task 5. Add fixture-based answer/citation acceptance tests and unsupported-question tests.
Implement this bounded change under “Enforce a source-citation and AI-limitation contract”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add fixture-based answer/citation acceptance tests and unsupported-question tests
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every tested material claim has an exact working citation or an explicit unsupported marker; warnings cannot be dismissed permanently.

### Story: Promote Agent artifacts into durable case work
Priority: P1
Source: Release backlog AI-003 (repository and product audit, 16 July 2026). Let investigators deliberately save, name, review and reuse generated tables, graphs, maps, charts and reports outside one thread.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- An approved artifact is discoverable in the case workspace, retains its investigation trail and can be safely exported or recycled.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Add Save to Workspace/Report with destination, title and optional note instead of relying only on automatic thread persistence
Priority: P1
Estimate: 8h
Source: Release backlog AI-003, task 1. Add Save to Workspace/Report with destination, title and optional note instead of relying only on automatic thread persistence.
Implement this bounded change under “Promote Agent artifacts into durable case work”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add Save to Workspace/Report with destination, title and optional note instead of relying only on automatic thread persistence
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An approved artifact is discoverable in the case workspace, retains its investigation trail and can be safely exported or recycled.

#### Task: Mark generated artifacts Draft until a user approves; store creator/model/run/tools/citations and version
Priority: P1
Estimate: 8h
Source: Release backlog AI-003, task 2. Mark generated artifacts Draft until a user approves; store creator/model/run/tools/citations and version.
Implement this bounded change under “Promote Agent artifacts into durable case work”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Mark generated artifacts Draft until a user approves; store creator/model/run/tools/citations and version
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An approved artifact is discoverable in the case workspace, retains its investigation trail and can be safely exported or recycled.

#### Task: Support list/open/rename/update/recycle with permissions, concurrency and audit
Priority: P1
Estimate: 8h
Source: Release backlog AI-003, task 3. Support list/open/rename/update/recycle with permissions, concurrency and audit.
Implement this bounded change under “Promote Agent artifacts into durable case work”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Support list/open/rename/update/recycle with permissions, concurrency and audit
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An approved artifact is discoverable in the case workspace, retains its investigation trail and can be safely exported or recycled.

#### Task: Keep source links and case scoping through export and workspace/report embedding
Priority: P1
Estimate: 8h
Source: Release backlog AI-003, task 4. Keep source links and case scoping through export and workspace/report embedding.
Implement this bounded change under “Promote Agent artifacts into durable case work”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep source links and case scoping through export and workspace/report embedding
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An approved artifact is discoverable in the case workspace, retains its investigation trail and can be safely exported or recycled.

#### Task: Test unsupported/deleted sources, large artifacts and re-opening after session restart
Priority: P1
Estimate: 8h
Source: Release backlog AI-003, task 5. Test unsupported/deleted sources, large artifacts and re-opening after session restart.
Implement this bounded change under “Promote Agent artifacts into durable case work”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test unsupported/deleted sources, large artifacts and re-opening after session restart
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- An approved artifact is discoverable in the case workspace, retains its investigation trail and can be safely exported or recycled.

### Story: Design and gate multi-provider support
Priority: P1
Source: Release backlog AI-004 (repository and product audit, 16 July 2026). Add providers for resilience or contractual needs—not a shallow model dropdown with incompatible guarantees.
Release gate: Before provider commitment. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Each advertised provider passes the shared capability/safety contract and the deployed provider terms match customer documentation.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Define provider abstraction for chat, tools, structured output, vision, transcription and embeddings, including capability fallbacks
Priority: P1
Estimate: 4h
Source: Release backlog AI-004, task 1. Define provider abstraction for chat, tools, structured output, vision, transcription and embeddings, including capability fallbacks.
Implement this bounded change under “Design and gate multi-provider support”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before provider commitment so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define provider abstraction for chat, tools, structured output, vision, transcription and embeddings, including capability fallbacks
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Each advertised provider passes the shared capability/safety contract and the deployed provider terms match customer documentation.

#### Task: Evaluate OpenAI, Anthropic, Gemini and approved local models for data terms, region, retention, training, cost and quality
Priority: P1
Estimate: 4h
Source: Release backlog AI-004, task 2. Evaluate OpenAI, Anthropic, Gemini and approved local models for data terms, region, retention, training, cost and quality.
Implement this bounded change under “Design and gate multi-provider support”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before provider commitment so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Evaluate OpenAI, Anthropic, Gemini and approved local models for data terms, region, retention, training, cost and quality
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Each advertised provider passes the shared capability/safety contract and the deployed provider terms match customer documentation.

#### Task: Store provider secrets per instance, expose an admin allowlist and record provider/model on every run/artifact/cost
Priority: P1
Estimate: 8h
Source: Release backlog AI-004, task 3. Store provider secrets per instance, expose an admin allowlist and record provider/model on every run/artifact/cost.
Implement this bounded change under “Design and gate multi-provider support”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before provider commitment so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Store provider secrets per instance, expose an admin allowlist and record provider/model on every run/artifact/cost
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Each advertised provider passes the shared capability/safety contract and the deployed provider terms match customer documentation.

#### Task: Handle model retirement, outage/fallback and embedding-dimension migrations without silent behavior changes
Priority: P1
Estimate: 16h
Source: Release backlog AI-004, task 4. Handle model retirement, outage/fallback and embedding-dimension migrations without silent behavior changes.
Implement this bounded change under “Design and gate multi-provider support”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before provider commitment so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Handle model retirement, outage/fallback and embedding-dimension migrations without silent behavior changes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Each advertised provider passes the shared capability/safety contract and the deployed provider terms match customer documentation.

#### Task: Run the same extraction, citation, tool and safety fixtures for every supported provider
Priority: P1
Estimate: 8h
Source: Release backlog AI-004, task 5. Run the same extraction, citation, tool and safety fixtures for every supported provider.
Implement this bounded change under “Design and gate multi-provider support”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before provider commitment so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Run the same extraction, citation, tool and safety fixtures for every supported provider
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Each advertised provider passes the shared capability/safety contract and the deployed provider terms match customer documentation.

### Story: Bound and authorise every Agent tool
Priority: P0
Source: Release backlog AI-005 (repository and product audit, 16 July 2026). Outer endpoint permission checks are insufficient when tools can query, export or mutate case data.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Adversarial fixtures cannot cross cases, mutate/export without approval, exceed budgets or bypass the query policy.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Enforce case/user permission inside every tool and validate returned keys belong to that case
Priority: P0
Estimate: 8h
Source: Release backlog AI-005, task 1. Enforce case/user permission inside every tool and validate returned keys belong to that case.
Implement this bounded change under “Bound and authorise every Agent tool”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Enforce case/user permission inside every tool and validate returned keys belong to that case
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Adversarial fixtures cannot cross cases, mutate/export without approval, exceed budgets or bypass the query policy.

#### Task: Keep tools read-only by default; require explicit, scoped confirmation for mutation, export or expensive work
Priority: P0
Estimate: 8h
Source: Release backlog AI-005, task 2. Keep tools read-only by default; require explicit, scoped confirmation for mutation, export or expensive work.
Implement this bounded change under “Bound and authorise every Agent tool”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep tools read-only by default; require explicit, scoped confirmation for mutation, export or expensive work
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Adversarial fixtures cannot cross cases, mutate/export without approval, exceed budgets or bypass the query policy.

#### Task: Cap steps, retries, query/result size, runtime, concurrent runs and spend
Priority: P0
Estimate: 8h
Source: Release backlog AI-005, task 3. Cap steps, retries, query/result size, runtime, concurrent runs and spend.
Implement this bounded change under “Bound and authorise every Agent tool”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Cap steps, retries, query/result size, runtime, concurrent runs and spend
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Adversarial fixtures cannot cross cases, mutate/export without approval, exceed budgets or bypass the query policy.

#### Task: Use parser/allowlist-backed query safety rather than string blocklists; remove unrestricted Cypher
Priority: P0
Estimate: 4h
Source: Release backlog AI-005, task 4. Use parser/allowlist-backed query safety rather than string blocklists; remove unrestricted Cypher.
Implement this bounded change under “Bound and authorise every Agent tool”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Use parser/allowlist-backed query safety rather than string blocklists; remove unrestricted Cypher
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Adversarial fixtures cannot cross cases, mutate/export without approval, exceed budgets or bypass the query policy.

#### Task: Threat-test prompt injection, malicious evidence/tool output, cross-case guessing, duplicate calls, cancellation races and partial failure
Priority: P0
Estimate: 12h
Source: Release backlog AI-005, task 5. Threat-test prompt injection, malicious evidence/tool output, cross-case guessing, duplicate calls, cancellation races and partial failure.
Implement this bounded change under “Bound and authorise every Agent tool”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Threat-test prompt injection, malicious evidence/tool output, cross-case guessing, duplicate calls, cancellation races and partial failure
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Adversarial fixtures cannot cross cases, mutate/export without approval, exceed budgets or bypass the query policy.

### Story: Add AI budgets, outage behavior and complete cost attribution
Priority: P1
Source: Release backlog AI-006 (repository and product audit, 16 July 2026). Costs should remain an operational control and AI failure should not strand user work.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Known usage reconciles to provider billing within tolerance; caps stop work safely and provider outage preserves user context.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Set per-case/per-user/monthly warning and hard caps for ingestion, chat and agent usage
Priority: P1
Estimate: 4h
Source: Release backlog AI-006, task 1. Set per-case/per-user/monthly warning and hard caps for ingestion, chat and agent usage.
Implement this bounded change under “Add AI budgets, outage behavior and complete cost attribution”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Set per-case/per-user/monthly warning and hard caps for ingestion, chat and agent usage
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Known usage reconciles to provider billing within tolerance; caps stop work safely and provider outage preserves user context.

#### Task: Attribute every provider call—including retries/tools/embeddings—to user, case, operation, model and source job/run
Priority: P1
Estimate: 8h
Source: Release backlog AI-006, task 2. Also sourced from V2 Alpha Bridging Plan BRG-040 / Gap Assessment §2 and §3.5. Attribute every provider call—including classification, Cypher generation, relationship analysis, triage, evidence processing, retries, tools and embeddings—to user, case, operation, provider, model and source job/run; record local/Ollama inference at zero cost rather than omitting the ledger row.
Implement this bounded change under “Add AI budgets, outage behavior and complete cost attribution”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Attribute every provider call—including retries/tools/embeddings—to user, case, operation, model and source job/run
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known usage reconciles to provider billing within tolerance; caps stop work safely and provider outage preserves user context.

#### Task: Show estimated/actual cost for expensive actions and clear cap errors
Priority: P1
Estimate: 4h
Source: Release backlog AI-006, task 3. Show estimated/actual cost for expensive actions and clear cap errors.
Implement this bounded change under “Add AI budgets, outage behavior and complete cost attribution”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show estimated/actual cost for expensive actions and clear cap errors
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known usage reconciles to provider billing within tolerance; caps stop work safely and provider outage preserves user context.

#### Task: Add provider timeout/circuit-breaker/retry behavior and preserve drafts when unavailable
Priority: P1
Estimate: 12h
Source: Release backlog AI-006, task 4. Add provider timeout/circuit-breaker/retry behavior and preserve drafts when unavailable.
Implement this bounded change under “Add AI budgets, outage behavior and complete cost attribution”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add provider timeout/circuit-breaker/retry behavior and preserve drafts when unavailable
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known usage reconciles to provider billing within tolerance; caps stop work safely and provider outage preserves user context.

#### Task: Alert on abnormal spend, missing pricing and repeated provider failure
Priority: P1
Estimate: 8h
Source: Release backlog AI-006, task 5. Alert on abnormal spend, missing pricing and repeated provider failure.
Implement this bounded change under “Add AI budgets, outage behavior and complete cost attribution”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Alert on abnormal spend, missing pricing and repeated provider failure
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Known usage reconciles to provider billing within tolerance; caps stop work safely and provider outage preserves user context.

### Story: Prove Notes no longer disappear or fail to save
Priority: P0
Source: Release backlog WORK-001 (repository and product audit, 16 July 2026). Treat the storage migration as a hypothesis until current end-to-end and concurrency tests close the reports.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Notes survive refresh/restart/concurrency and remain visible only in the correct case; simulated failures do not lose or duplicate content.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Reproduce the original create/save/disappear scenarios on migrated and fresh cases
Priority: P0
Estimate: 6h
Source: Release backlog WORK-001, task 1. Reproduce the original create/save/disappear scenarios on migrated and fresh cases.
Implement this bounded change under “Prove Notes no longer disappear or fail to save”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Reproduce the original create/save/disappear scenarios on migrated and fresh cases
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Notes survive refresh/restart/concurrency and remain visible only in the correct case; simulated failures do not lose or duplicate content.

#### Task: Verify case/user permissions, list filters and transaction rollback on failed saves
Priority: P0
Estimate: 6h
Source: Release backlog WORK-001, task 2. Verify case/user permissions, list filters and transaction rollback on failed saves.
Implement this bounded change under “Prove Notes no longer disappear or fail to save”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify case/user permissions, list filters and transaction rollback on failed saves
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Notes survive refresh/restart/concurrency and remain visible only in the correct case; simulated failures do not lose or duplicate content.

#### Task: Test concurrent create/edit, refresh, multiple workers and migration idempotency
Priority: P0
Estimate: 12h
Source: Release backlog WORK-001, task 3. Test concurrent create/edit, refresh, multiple workers and migration idempotency.
Implement this bounded change under “Prove Notes no longer disappear or fail to save”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test concurrent create/edit, refresh, multiple workers and migration idempotency
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Notes survive refresh/restart/concurrency and remain visible only in the correct case; simulated failures do not lose or duplicate content.

#### Task: Add visible retry/recovery and prevent duplicate notes after timeout
Priority: P0
Estimate: 8h
Source: Release backlog WORK-001, task 4. Add visible retry/recovery and prevent duplicate notes after timeout.
Implement this bounded change under “Prove Notes no longer disappear or fail to save”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add visible retry/recovery and prevent duplicate notes after timeout
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Notes survive refresh/restart/concurrency and remain visible only in the correct case; simulated failures do not lose or duplicate content.

#### Task: Close BUG-007/008 only with durable database and browser assertions
Priority: P0
Estimate: 8h
Source: Release backlog WORK-001, task 5. Close BUG-007/008 only with durable database and browser assertions.
Implement this bounded change under “Prove Notes no longer disappear or fail to save”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Close BUG-007/008 only with durable database and browser assertions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Notes survive refresh/restart/concurrency and remain visible only in the correct case; simulated failures do not lose or duplicate content.

### Story: Complete Findings and inline evidence summaries
Priority: P1
Source: Release backlog WORK-002 (repository and product audit, 16 July 2026). Provide a structured, source-linked place for conclusions distinct from private working notes.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A finding is durable, reviewable and exportable with working evidence links; file summaries are visible without opening each file.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Finish Findings create/edit/reorder/recycle with linked evidence, entities and documents
Priority: P1
Estimate: 4h
Source: Release backlog WORK-002, task 1. Finish Findings create/edit/reorder/recycle with linked evidence, entities and documents.
Implement this bounded change under “Complete Findings and inline evidence summaries”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Finish Findings create/edit/reorder/recycle with linked evidence, entities and documents
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A finding is durable, reviewable and exportable with working evidence links; file summaries are visible without opening each file.

#### Task: Show inline file summaries in Workspace with clear AI/human status and source open action
Priority: P1
Estimate: 4h
Source: Release backlog WORK-002, task 2. Show inline file summaries in Workspace with clear AI/human status and source open action.
Implement this bounded change under “Complete Findings and inline evidence summaries”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show inline file summaries in Workspace with clear AI/human status and source open action
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A finding is durable, reviewable and exportable with working evidence links; file summaries are visible without opening each file.

#### Task: Place Findings first in approved report output while retaining author, citations and review state
Priority: P1
Estimate: 6h
Source: Release backlog WORK-002, task 3. Place Findings first in approved report output while retaining author, citations and review state.
Implement this bounded change under “Complete Findings and inline evidence summaries”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Place Findings first in approved report output while retaining author, citations and review state
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A finding is durable, reviewable and exportable with working evidence links; file summaries are visible without opening each file.

#### Task: Enforce case permissions, audit and optimistic concurrency
Priority: P1
Estimate: 8h
Source: Release backlog WORK-002, task 4. Enforce case permissions, audit and optimistic concurrency.
Implement this bounded change under “Complete Findings and inline evidence summaries”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Enforce case permissions, audit and optimistic concurrency
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A finding is durable, reviewable and exportable with working evidence links; file summaries are visible without opening each file.

#### Task: Test broken/recycled links and large linked-item sets
Priority: P1
Estimate: 6h
Source: Release backlog WORK-002, task 5. Test broken/recycled links and large linked-item sets.
Implement this bounded change under “Complete Findings and inline evidence summaries”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test broken/recycled links and large linked-item sets
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A finding is durable, reviewable and exportable with working evidence links; file summaries are visible without opening each file.

### Story: Reorganise Workspace around investigation outcomes
Priority: P1
Source: Release backlog WORK-003 (repository and product audit, 16 July 2026). Reduce clutter and align section naming/order with the approved domain workflow.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The signed workspace map matches navigation and exports, and a usability walkthrough can find each core object without developer help.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Approve and implement the section order covering deadlines/tasks, findings, context/exposure, theories, notes, snapshots, witnesses, entities,…
Priority: P1
Estimate: 12h
Source: Release backlog WORK-003, task 1. Approve and implement the section order covering deadlines/tasks, findings, context/exposure, theories, notes, snapshots, witnesses, entities, evidence, files, graph, timeline, map and audit.
Implement this bounded change under “Reorganise Workspace around investigation outcomes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Approve and implement the section order covering deadlines/tasks, findings, context/exposure, theories, notes, snapshots, witnesses, entities, evidence, files, graph, timeline, map and audit
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The signed workspace map matches navigation and exports, and a usability walkthrough can find each core object without developer help.

#### Task: Make the left navigation match and remember collapsed state per user/case
Priority: P1
Estimate: 8h
Source: Release backlog WORK-003, task 2. Make the left navigation match and remember collapsed state per user/case.
Implement this bounded change under “Reorganise Workspace around investigation outcomes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make the left navigation match and remember collapsed state per user/case
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The signed workspace map matches navigation and exports, and a usability walkthrough can find each core object without developer help.

#### Task: Condense Witness Matrix default rows; add Interviewed by and rename Witness Interview to Interview or Statement
Priority: P1
Estimate: 8h
Source: Release backlog WORK-003, task 3. Condense Witness Matrix default rows; add Interviewed by and rename Witness Interview to Interview or Statement.
Implement this bounded change under “Reorganise Workspace around investigation outcomes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Condense Witness Matrix default rows; add Interviewed by and rename Witness Interview to Interview or Statement
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The signed workspace map matches navigation and exports, and a usability walkthrough can find each core object without developer help.

#### Task: Consolidate excessive AI facts/insights into navigable summaries without dropping atomic sources
Priority: P1
Estimate: 8h
Source: Release backlog WORK-003, task 4. Consolidate excessive AI facts/insights into navigable summaries without dropping atomic sources.
Implement this bounded change under “Reorganise Workspace around investigation outcomes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Consolidate excessive AI facts/insights into navigable summaries without dropping atomic sources
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The signed workspace map matches navigation and exports, and a usability walkthrough can find each core object without developer help.

#### Task: Remove or rename legally misleading Chain of Custody / Audit Log labels following legal review
Priority: P1
Estimate: 6h
Source: Release backlog WORK-003, task 5. Remove or rename legally misleading Chain of Custody / Audit Log labels following legal review.
Implement this bounded change under “Reorganise Workspace around investigation outcomes”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove or rename legally misleading Chain of Custody / Audit Log labels following legal review
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- The signed workspace map matches navigation and exports, and a usability walkthrough can find each core object without developer help.

### Story: Unify Details, AI Chat and Notebook right-rail behavior
Priority: P1
Source: Release backlog WORK-004 (repository and product audit, 16 July 2026). The shared rail should behave consistently across Graph, Evidence, Timeline, Map, Table, Financial and Cellebrite.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The rail keeps correct case/selection context and identical collapse, scroll and keyboard behavior on every supported route.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Define a single tab/state model, with Evidence Processing as a route-specific addition
Priority: P1
Estimate: 8h
Source: Release backlog WORK-004, task 1. Define a single tab/state model, with Evidence Processing as a route-specific addition.
Implement this bounded change under “Unify Details, AI Chat and Notebook right-rail behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define a single tab/state model, with Evidence Processing as a route-specific addition
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The rail keeps correct case/selection context and identical collapse, scroll and keyboard behavior on every supported route.

#### Task: Keep selection/context correct when switching tabs/routes and never show another case’s entity or thread
Priority: P1
Estimate: 8h
Source: Release backlog WORK-004, task 2. Keep selection/context correct when switching tabs/routes and never show another case’s entity or thread.
Implement this bounded change under “Unify Details, AI Chat and Notebook right-rail behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep selection/context correct when switching tabs/routes and never show another case’s entity or thread
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The rail keeps correct case/selection context and identical collapse, scroll and keyboard behavior on every supported route.

#### Task: Make collapse/resize/scroll/focus behavior consistent and persisted; fix nested overflow in all tool overlays
Priority: P1
Estimate: 8h
Source: Release backlog WORK-004, task 3. Make collapse/resize/scroll/focus behavior consistent and persisted; fix nested overflow in all tool overlays.
Implement this bounded change under “Unify Details, AI Chat and Notebook right-rail behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make collapse/resize/scroll/focus behavior consistent and persisted; fix nested overflow in all tool overlays
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The rail keeps correct case/selection context and identical collapse, scroll and keyboard behavior on every supported route.

#### Task: Resolve Graph’s separate rail and Agent’s full-width exception through the AI information-architecture decision
Priority: P1
Estimate: 8h
Source: Release backlog WORK-004, task 4. Resolve Graph’s separate rail and Agent’s full-width exception through the AI information-architecture decision.
Implement this bounded change under “Unify Details, AI Chat and Notebook right-rail behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Resolve Graph’s separate rail and Agent’s full-width exception through the AI information-architecture decision
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The rail keeps correct case/selection context and identical collapse, scroll and keyboard behavior on every supported route.

#### Task: Add keyboard shortcuts, accessible tab semantics and browser tests across every case route
Priority: P1
Estimate: 12h
Source: Release backlog WORK-004, task 5. Add keyboard shortcuts, accessible tab semantics and browser tests across every case route.
Implement this bounded change under “Unify Details, AI Chat and Notebook right-rail behavior”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add keyboard shortcuts, accessible tab semantics and browser tests across every case route
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The rail keeps correct case/selection context and identical collapse, scroll and keyboard behavior on every supported route.

### Story: Protect unsaved work and concurrent edits
Priority: P1
Source: Release backlog WORK-005 (repository and product audit, 16 July 2026). Outside clicks, navigation and another investigator must not silently discard or overwrite long-form work.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Dirty editors cannot close or overwrite silently; simulated conflicts preserve both users’ work and offer a clear resolution.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Inventory every modal/sheet/editor and classify draft, destructive close and autosave behavior
Priority: P1
Estimate: 4h
Source: Release backlog WORK-005, task 1. Inventory every modal/sheet/editor and classify draft, destructive close and autosave behavior.
Implement this bounded change under “Protect unsaved work and concurrent edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Inventory every modal/sheet/editor and classify draft, destructive close and autosave behavior
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Dirty editors cannot close or overwrite silently; simulated conflicts preserve both users’ work and offer a clear resolution.

#### Task: Block accidental backdrop/Escape/navigation close when dirty; offer save/discard/cancel
Priority: P1
Estimate: 8h
Source: Release backlog WORK-005, task 2. Block accidental backdrop/Escape/navigation close when dirty; offer save/discard/cancel.
Implement this bounded change under “Protect unsaved work and concurrent edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Block accidental backdrop/Escape/navigation close when dirty; offer save/discard/cancel
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Dirty editors cannot close or overwrite silently; simulated conflicts preserve both users’ work and offer a clear resolution.

#### Task: Add local/server drafts where long-form work warrants it
Priority: P1
Estimate: 8h
Source: Release backlog WORK-005, task 3. Add local/server drafts where long-form work warrants it.
Implement this bounded change under “Protect unsaved work and concurrent edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add local/server drafts where long-form work warrants it
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Dirty editors cannot close or overwrite silently; simulated conflicts preserve both users’ work and offer a clear resolution.

#### Task: Use optimistic concurrency/version checks and present merge/reload choices on conflict
Priority: P1
Estimate: 8h
Source: Release backlog WORK-005, task 4. Use optimistic concurrency/version checks and present merge/reload choices on conflict.
Implement this bounded change under “Protect unsaved work and concurrent edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Use optimistic concurrency/version checks and present merge/reload choices on conflict
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Dirty editors cannot close or overwrite silently; simulated conflicts preserve both users’ work and offer a clear resolution.

#### Task: Cover notes, theories, witnesses, summaries, reports, chat saves, financial details and settings in browser tests
Priority: P1
Estimate: 6h
Source: Release backlog WORK-005, task 5. Cover notes, theories, witnesses, summaries, reports, chat saves, financial details and settings in browser tests.
Implement this bounded change under “Protect unsaved work and concurrent edits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Cover notes, theories, witnesses, summaries, reports, chat saves, financial details and settings in browser tests
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Dirty editors cannot close or overwrite silently; simulated conflicts preserve both users’ work and offer a clear resolution.

### Story: Make personal Settings truthful and persistent
Priority: P1
Source: Release backlog SET-001 (repository and product audit, 16 July 2026). Theme works, but notification/default-view controls currently look functional without a persistence contract.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Every visible setting changes real behavior after refresh on supported devices, or is removed from the release UI.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Persist supported preferences server-side or clearly local-only with documented scope
Priority: P1
Estimate: 12h
Source: Release backlog SET-001, task 1. Persist supported preferences server-side or clearly local-only with documented scope.
Implement this bounded change under “Make personal Settings truthful and persistent”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Persist supported preferences server-side or clearly local-only with documented scope
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible setting changes real behavior after refresh on supported devices, or is removed from the release UI.

#### Task: Implement default case view and ensure opening a case respects it
Priority: P1
Estimate: 12h
Source: Release backlog SET-001, task 2. Implement default case view and ensure opening a case respects it.
Implement this bounded change under “Make personal Settings truthful and persistent”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Implement default case view and ensure opening a case respects it
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible setting changes real behavior after refresh on supported devices, or is removed from the release UI.

#### Task: Wire notification preferences to real browser/in-app behavior and permission prompts, or remove them
Priority: P1
Estimate: 4h
Source: Release backlog SET-001, task 3. Wire notification preferences to real browser/in-app behavior and permission prompts, or remove them.
Implement this bounded change under “Make personal Settings truthful and persistent”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Wire notification preferences to real browser/in-app behavior and permission prompts, or remove them
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible setting changes real behavior after refresh on supported devices, or is removed from the release UI.

#### Task: Add change-password/session management and approved profile fields
Priority: P1
Estimate: 8h
Source: Release backlog SET-001, task 4. Add change-password/session management and approved profile fields.
Implement this bounded change under “Make personal Settings truthful and persistent”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add change-password/session management and approved profile fields
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every visible setting changes real behavior after refresh on supported devices, or is removed from the release UI.

#### Task: Verify shortcuts shown in Settings match implemented shortcuts and do not conflict with browser/assistive tech
Priority: P1
Estimate: 12h
Source: Release backlog SET-001, task 5. Verify shortcuts shown in Settings match implemented shortcuts and do not conflict with browser/assistive tech.
Implement this bounded change under “Make personal Settings truthful and persistent”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify shortcuts shown in Settings match implemented shortcuts and do not conflict with browser/assistive tech
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Every visible setting changes real behavior after refresh on supported devices, or is removed from the release UI.

### Story: Deliver the V1 Reports product on the shared export foundation
Priority: P0
Source: Release backlog REP-001 (repository and product audit, 16 July 2026). The bridging plan confirms that a complete case deliverable is required, while the current Reports page targets an unregistered backend. Build the retained Reports workflow on the shared server-side export foundation and remove only superseded duplicate paths.
Release gate: Before feature freeze. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Reports provides one complete, authorised and tested case-deliverable workflow on the shared export service; no broken or duplicate report entry point remains.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Confirm the dedicated report builder, its 15-section case-export contract and its relationship to Snapshot, Timeline, Notebook, Financial and…
Priority: P0
Estimate: 12h
Source: Release backlog REP-001, task 1. Confirm the dedicated report builder, its 15-section case-export contract and its relationship to Snapshot, Timeline, Notebook, Financial and Agent exports.
Implement this bounded change under “Deliver the V1 Reports product on the shared export foundation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Confirm the dedicated report builder, its 15-section case-export contract and its relationship to Snapshot, Timeline, Notebook, Financial and Agent exports
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Reports provides one complete, authorised and tested case-deliverable workflow on the shared export service; no broken or duplicate report entry point remains.

#### Task: Define report ownership, sections, versioning, approval, citations and supported formats
Priority: P0
Estimate: 8h
Source: Release backlog REP-001, task 2. Define report ownership, sections, versioning, approval, citations and supported formats.
Implement this bounded change under “Deliver the V1 Reports product on the shared export foundation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define report ownership, sections, versioning, approval, citations and supported formats
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Reports provides one complete, authorised and tested case-deliverable workflow on the shared export service; no broken or duplicate report entry point remains.

#### Task: Implement case-authorised persistence and generation, then wire Print, Export and Recycle end to end
Priority: P0
Estimate: 12h
Source: Release backlog REP-001, task 3. Implement case-authorised persistence and generation, then wire Print, Export and Recycle end to end.
Implement this bounded change under “Deliver the V1 Reports product on the shared export foundation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Implement case-authorised persistence and generation, then wire Print, Export and Recycle end to end
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Reports provides one complete, authorised and tested case-deliverable workflow on the shared export service; no broken or duplicate report entry point remains.

#### Task: Remove obsolete or duplicate report routes and navigation only after existing report data and supported journeys are migrated
Priority: P0
Estimate: 8h
Source: Release backlog REP-001, task 4. Remove obsolete or duplicate report routes and navigation only after existing report data and supported journeys are migrated.
Implement this bounded change under “Deliver the V1 Reports product on the shared export foundation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove obsolete or duplicate report routes and navigation only after existing report data and supported journeys are migrated
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- Reports provides one complete, authorised and tested case-deliverable workflow on the shared export service; no broken or duplicate report entry point remains.

#### Task: Add end-to-end create, reopen, edit, approve, export and recycle coverage
Priority: P0
Estimate: 8h
Source: Release backlog REP-001, task 5. Add end-to-end create, reopen, edit, approve, export and recycle coverage.
Implement this bounded change under “Deliver the V1 Reports product on the shared export foundation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add end-to-end create, reopen, edit, approve, export and recycle coverage
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Reports provides one complete, authorised and tested case-deliverable workflow on the shared export service; no broken or duplicate report entry point remains.

### Story: Sanitise report content and isolate document rendering
Priority: P0
Source: Release backlog REP-002 (repository and product audit, 16 July 2026). Unsafe/AI-generated HTML must not execute in the application origin or access user sessions.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Security fixtures cannot execute code, load unauthorised resources or read local/session data through report preview/export.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Store structured content or constrained Markdown instead of arbitrary HTML
Priority: P0
Estimate: 8h
Source: Release backlog REP-002, task 1. Store structured content or constrained Markdown instead of arbitrary HTML.
Implement this bounded change under “Sanitise report content and isolate document rendering”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Store structured content or constrained Markdown instead of arbitrary HTML
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Security fixtures cannot execute code, load unauthorised resources or read local/session data through report preview/export.

#### Task: Render through an allowlisted sanitizer with links/images/styles policy and strict CSP
Priority: P0
Estimate: 8h
Source: Release backlog REP-002, task 2. Render through an allowlisted sanitizer with links/images/styles policy and strict CSP.
Implement this bounded change under “Sanitise report content and isolate document rendering”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Render through an allowlisted sanitizer with links/images/styles policy and strict CSP
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Security fixtures cannot execute code, load unauthorised resources or read local/session data through report preview/export.

#### Task: Generate PDF/DOCX server-side in an isolated, resource-bounded process
Priority: P0
Estimate: 12h
Source: Release backlog REP-002, task 3. Generate PDF/DOCX server-side in an isolated, resource-bounded process.
Implement this bounded change under “Sanitise report content and isolate document rendering”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Generate PDF/DOCX server-side in an isolated, resource-bounded process
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Security fixtures cannot execute code, load unauthorised resources or read local/session data through report preview/export.

#### Task: Block external resource fetches, local-file access and script/event attributes
Priority: P0
Estimate: 8h
Source: Release backlog REP-002, task 4. Block external resource fetches, local-file access and script/event attributes.
Implement this bounded change under “Sanitise report content and isolate document rendering”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Block external resource fetches, local-file access and script/event attributes
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Security fixtures cannot execute code, load unauthorised resources or read local/session data through report preview/export.

#### Task: Add stored-XSS, malicious SVG/URL, huge-content and prompt-injected markup tests
Priority: P0
Estimate: 8h
Source: Release backlog REP-002, task 5. Add stored-XSS, malicious SVG/URL, huge-content and prompt-injected markup tests.
Implement this bounded change under “Sanitise report content and isolate document rendering”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add stored-XSS, malicious SVG/URL, huge-content and prompt-injected markup tests
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Security fixtures cannot execute code, load unauthorised resources or read local/session data through report preview/export.

### Story: Create one export design and metadata standard
Priority: P1
Source: Release backlog REP-003 (repository and product audit, 16 July 2026). Apply a consistent, legible and legally reviewed document frame to every promised export.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Every promised export passes the same brand/metadata/citation checklist and renders consistently from one template system.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Freeze logo/name, colour, typography and accessibility-safe fallbacks; reconcile legacy #222248/Cinzel/Lato feedback with the current Loupe brand…
Priority: P1
Estimate: 12h
Source: Release backlog REP-003, task 1. Freeze logo/name, colour, typography and accessibility-safe fallbacks; reconcile legacy #222248/Cinzel/Lato feedback with the current Loupe brand decision.
Implement this bounded change under “Create one export design and metadata standard”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Freeze logo/name, colour, typography and accessibility-safe fallbacks; reconcile legacy #222248/Cinzel/Lato feedback with the current Loupe brand decision
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Every promised export passes the same brand/metadata/citation checklist and renders consistently from one template system.

#### Task: Standardise cover/header/footer, case identity, document title/version, author, generation timestamp, page numbers and confidentiality classification
Priority: P1
Estimate: 4h
Source: Release backlog REP-003, task 2. Standardise cover/header/footer, case identity, document title/version, author, generation timestamp, page numbers and confidentiality classification.
Implement this bounded change under “Create one export design and metadata standard”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Standardise cover/header/footer, case identity, document title/version, author, generation timestamp, page numbers and confidentiality classification
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every promised export passes the same brand/metadata/citation checklist and renders consistently from one template system.

#### Task: Include filters/scope, stable IDs, source citations and AI/human-review statement where relevant
Priority: P1
Estimate: 6h
Source: Release backlog REP-003, task 3. Include filters/scope, stable IDs, source citations and AI/human-review statement where relevant.
Implement this bounded change under “Create one export design and metadata standard”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Include filters/scope, stable IDs, source citations and AI/human-review statement where relevant
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every promised export passes the same brand/metadata/citation checklist and renders consistently from one template system.

#### Task: Create reusable PDF/DOCX/CSV templates used by Graph, Timeline, Financial, Snapshot, Notebook, Agent and Reports
Priority: P1
Estimate: 8h
Source: Release backlog REP-003, task 4. Create reusable PDF/DOCX/CSV templates used by Graph, Timeline, Financial, Snapshot, Notebook, Agent and Reports.
Implement this bounded change under “Create one export design and metadata standard”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create reusable PDF/DOCX/CSV templates used by Graph, Timeline, Financial, Snapshot, Notebook, Agent and Reports
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every promised export passes the same brand/metadata/citation checklist and renders consistently from one template system.

#### Task: Add visual regression fixtures for fonts, page breaks, long tables, non-Latin text and missing assets
Priority: P1
Estimate: 8h
Source: Release backlog REP-003, task 5. Add visual regression fixtures for fonts, page breaks, long tables, non-Latin text and missing assets.
Implement this bounded change under “Create one export design and metadata standard”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add visual regression fixtures for fonts, page breaks, long tables, non-Latin text and missing assets
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Every promised export passes the same brand/metadata/citation checklist and renders consistently from one template system.

### Story: Fix Snapshot export fidelity and scope
Priority: P1
Source: Release backlog REP-004 (repository and product audit, 16 July 2026). Snapshot reports must contain a sharp graph and only the timeline/events saved with that snapshot.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Fixture exports are sharp, contain only snapshot-scoped content and reproduce the same saved version on re-export.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Render graph images at print-appropriate vector/high DPI with deterministic colours and labels
Priority: P1
Estimate: 8h
Source: Release backlog REP-004, task 1. Render graph images at print-appropriate vector/high DPI with deterministic colours and labels.
Implement this bounded change under “Fix Snapshot export fidelity and scope”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Render graph images at print-appropriate vector/high DPI with deterministic colours and labels
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Fixture exports are sharp, contain only snapshot-scoped content and reproduce the same saved version on re-export.

#### Task: Scope events/entities/notes to the saved snapshot rather than the whole case
Priority: P1
Estimate: 8h
Source: Release backlog REP-004, task 2. Scope events/entities/notes to the saved snapshot rather than the whole case.
Implement this bounded change under “Fix Snapshot export fidelity and scope”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Scope events/entities/notes to the saved snapshot rather than the whole case
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Fixture exports are sharp, contain only snapshot-scoped content and reproduce the same saved version on re-export.

#### Task: Add source citations and approved confidentiality labels
Priority: P1
Estimate: 8h
Source: Release backlog REP-004, task 3. Add source citations and approved confidentiality labels.
Implement this bounded change under “Fix Snapshot export fidelity and scope”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add source citations and approved confidentiality labels
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Fixture exports are sharp, contain only snapshot-scoped content and reproduce the same saved version on re-export.

#### Task: Test empty/large graphs, dark/light UI independence, long timelines and recycled sources
Priority: P1
Estimate: 6h
Source: Release backlog REP-004, task 4. Test empty/large graphs, dark/light UI independence, long timelines and recycled sources.
Implement this bounded change under “Fix Snapshot export fidelity and scope”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test empty/large graphs, dark/light UI independence, long timelines and recycled sources
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Fixture exports are sharp, contain only snapshot-scoped content and reproduce the same saved version on re-export.

#### Task: Reconcile generated report content with the saved snapshot version/hash
Priority: P1
Estimate: 12h
Source: Release backlog REP-004, task 5. Reconcile generated report content with the saved snapshot version/hash.
Implement this bounded change under “Fix Snapshot export fidelity and scope”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Reconcile generated report content with the saved snapshot version/hash
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Fixture exports are sharp, contain only snapshot-scoped content and reproduce the same saved version on re-export.

### Story: Authorise, audit and integrity-test all exports
Priority: P0
Source: Release backlog REP-005 (repository and product audit, 16 July 2026). Exports are a high-impact disclosure path and need the same case boundary as on-screen data.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A non-member cannot generate or fetch any export; authorised exports exactly match their selected case/scope and are auditable.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Inventory every download/print/file endpoint and require case permission server-side
Priority: P0
Estimate: 12h
Source: Release backlog REP-005, task 1. Inventory every download/print/file endpoint and require case permission server-side.
Implement this bounded change under “Authorise, audit and integrity-test all exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Inventory every download/print/file endpoint and require case permission server-side
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A non-member cannot generate or fetch any export; authorised exports exactly match their selected case/scope and are auditable.

#### Task: Record actor, case, export type, scope, result and correlation ID without logging evidence content
Priority: P0
Estimate: 8h
Source: Release backlog REP-005, task 2. Record actor, case, export type, scope, result and correlation ID without logging evidence content.
Implement this bounded change under “Authorise, audit and integrity-test all exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Record actor, case, export type, scope, result and correlation ID without logging evidence content
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A non-member cannot generate or fetch any export; authorised exports exactly match their selected case/scope and are auditable.

#### Task: Prevent IDOR, guessed artifact/report IDs and cross-case cached files
Priority: P0
Estimate: 8h
Source: Release backlog REP-005, task 3. Prevent IDOR, guessed artifact/report IDs and cross-case cached files.
Implement this bounded change under “Authorise, audit and integrity-test all exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prevent IDOR, guessed artifact/report IDs and cross-case cached files
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A non-member cannot generate or fetch any export; authorised exports exactly match their selected case/scope and are auditable.

#### Task: Apply safe filenames, content types, no-sniff/cache headers and expiring download URLs where needed
Priority: P0
Estimate: 8h
Source: Release backlog REP-005, task 4. Apply safe filenames, content types, no-sniff/cache headers and expiring download URLs where needed.
Implement this bounded change under “Authorise, audit and integrity-test all exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Apply safe filenames, content types, no-sniff/cache headers and expiring download URLs where needed
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A non-member cannot generate or fetch any export; authorised exports exactly match their selected case/scope and are auditable.

#### Task: Add negative security tests plus dataset-to-export count/hash assertions
Priority: P0
Estimate: 8h
Source: Release backlog REP-005, task 5. Add negative security tests plus dataset-to-export count/hash assertions.
Implement this bounded change under “Authorise, audit and integrity-test all exports”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add negative security tests plus dataset-to-export count/hash assertions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A non-member cannot generate or fetch any export; authorised exports exactly match their selected case/scope and are auditable.

### Story: Freeze and apply the production identity
Priority: P1
Source: Release backlog BRAND-001 (repository and product audit, 16 July 2026). Finish the Loupe decision across customer-visible product, documentation, operations and legal materials.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Customer-visible release artifacts present one cleared name and identity; any retained legacy technical identifier is documented and invisible.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Complete company/domain/social/trademark clearance with appropriate professional advice
Priority: P1
Estimate: 8h
Source: Release backlog BRAND-001, task 1. Complete company/domain/social/trademark clearance with appropriate professional advice.
Implement this bounded change under “Freeze and apply the production identity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Complete company/domain/social/trademark clearance with appropriate professional advice
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Customer-visible release artifacts present one cleared name and identity; any retained legacy technical identifier is documented and invisible.

#### Task: Create an inventory of visible Owl/Deduce/Loupe names, logos, favicons, email copy and generated documents
Priority: P1
Estimate: 8h
Source: Release backlog BRAND-001, task 2. Create an inventory of visible Owl/Deduce/Loupe names, logos, favicons, email copy and generated documents.
Implement this bounded change under “Freeze and apply the production identity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create an inventory of visible Owl/Deduce/Loupe names, logos, favicons, email copy and generated documents
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Customer-visible release artifacts present one cleared name and identity; any retained legacy technical identifier is documented and invisible.

#### Task: Replace customer-visible legacy identity while deliberately versioning internal technical identifiers that cannot safely change at once
Priority: P1
Estimate: 8h
Source: Release backlog BRAND-001, task 3. Replace customer-visible legacy identity while deliberately versioning internal technical identifiers that cannot safely change at once.
Implement this bounded change under “Freeze and apply the production identity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Replace customer-visible legacy identity while deliberately versioning internal technical identifiers that cannot safely change at once
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Customer-visible release artifacts present one cleared name and identity; any retained legacy technical identifier is documented and invisible.

#### Task: Align landing claims, login, app shell, exports, user guide, release notes, system emails and legal terms
Priority: P1
Estimate: 8h
Source: Release backlog BRAND-001, task 4. Align landing claims, login, app shell, exports, user guide, release notes, system emails and legal terms.
Implement this bounded change under “Freeze and apply the production identity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Align landing claims, login, app shell, exports, user guide, release notes, system emails and legal terms
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Customer-visible release artifacts present one cleared name and identity; any retained legacy technical identifier is documented and invisible.

#### Task: Add brand smoke screenshots and a pre-release string/asset scan
Priority: P1
Estimate: 8h
Source: Release backlog BRAND-001, task 5. Add brand smoke screenshots and a pre-release string/asset scan.
Implement this bounded change under “Freeze and apply the production identity”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add brand smoke screenshots and a pre-release string/asset scan
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Customer-visible release artifacts present one cleared name and identity; any retained legacy technical identifier is documented and invisible.

### Bug: Fix /api/chat/extract-nodes 500
Priority: P0
Estimate: 4h
`get_graph_summary()` is called without its required `case_id`, so the "show me the graph behind this answer" provenance feature 500s deterministically on every call (gap assessment §2/§5, BRG-004). Port the v1 fix (ref commit `cbf70e9`), which also adds the missing case isolation.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-004, gap assessment §2/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Endpoint returns a result graph for a real case
- Cross-case leakage test passes (nodes from other cases never appear)

### Bug: Fix theory & investigation timeline 500
Priority: P0
Estimate: 12h
`DetachedInstanceError: <EvidenceFile> is not bound to a Session` in `workspace_service.get_theory_timeline` / `get_investigation_timeline` breaks theories and snapshot inputs (gap assessment §5, BRG-005). Eager-load the relationships or re-query inside the session.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-005, gap assessment §5). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Both endpoints return 200 with correct events on a case that has theories with attached evidence
- Snapshot creation consuming the investigation timeline works again

### Story: Investigator can export a complete case file
The 15-section case export rebuilt server-side on v2's `timeline_view_service` foundation, using v1's export as the content spec (BRG-035, split per the roadmap; v1 ref `05dc351` for content).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-035). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A full case export renders with every section on real data; audit log included; output snapshot reviewed by an investigator
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Export framework + section picker on the v2 export service
Estimate: 12h
Build the multi-section document framework on `timeline_view_service`/WeasyPrint: section registry, section picker, pagination, headers/footers.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-035). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A skeleton export with selectable sections renders to PDF server-side
- Section picker includes/excludes sections correctly

#### Task: Content sections — summary, entities, notes, audit log, transcriptions
Estimate: 14h
Implement the data-driven sections from v1's 15-section spec, including the audit log and evidence transcriptions.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-035). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each implemented section matches v1's content spec on a real case
- Audit log section reflects the case's actual audit trail

#### Task: Rendered graph, timeline, and map visualizations in the export
Estimate: 12h
Server-side rendering of the visualization sections (graph, timeline, map) embedded in the export document.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-035). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Graph, timeline, and map sections render as images/vector in the PDF for a real case
- Visualizations reflect the case state at export time

#### Task: Confidentiality labels + investigator review pass
Estimate: 6h
Apply v1's post-fork confidentiality-label work to the export, then have an investigator review a full output against v1's export for fitness.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-035). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Confidentiality labels appear per the v1 spec
- Investigator sign-off recorded on a sample export

### Task: Theory-scoped export
Estimate: 10h
Rebuild theory export on the case-export foundation — depends on the case-export story (gap assessment §3.4, BRG-036).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-036, gap assessment §3.4). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A theory exports with its scoped events, evidence, and narrative sections
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Task: Map locations CSV export
Estimate: 3h
Restore the map locations CSV export lost in the port (gap assessment §3.4, BRG-038; v1 ref `25bce82`, DKT-5).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-038, gap assessment §3.4). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Map view exports its current location set to CSV matching v1's columns
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Task: View-aware chat context from the ported views
Priority: P3
Estimate: 14h
v1 published what-the-analyst-sees (with row previews) from financial, cellebrite comms/events/files, graph-table, and workspace views; v2's narrower contract has one publisher (gap assessment §2 chat delta, BRG-042; spec from v1 `f871397`). Re-publish from the ported views using v2's contract. Depends on the cellebrite and financial epics landing.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-042, gap assessment §2). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Chat context includes the active financial, cellebrite, and table views with row previews
- Answers reference the visible view state where relevant

### Task: Decide chat privacy semantics
Priority: P1
Estimate: 3h
v1 conversations are owner-only; v2 lets any case member read any member's conversations — a silent semantics change (gap assessment §3.5, BRG-043 DECIDE). Pick deliberately; roadmap suggests the enterprise default of owner-only with explicit share. P1 because alpha testers' chats are exposed to each other until decided.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-043, gap assessment §3.5). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded and implemented as an access rule
- Behavior covered by a test for both member and owner access

### Task: Investigator-controlled merge path inside v2's merge job
Priority: P3
Estimate: 16h
v2's AI merge is more robust (async, locks, crash recovery, reversible) but the LLM chooses the surviving facts; v1's manual merge and 3-step bulk wizard let the investigator decide field-by-field (gap assessment §4, BRG-044 DECIDE). For forensic defensibility, restore a manual mode inside v2's merge job — investigator-reviewed field selection — not a port of the old wizard. Includes the product decision with Neil before implementation.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-044, gap assessment §4). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded on merge control semantics
- Merge job offers an investigator-reviewed field-selection mode; AI-selected mode remains available
- Manual-mode merges are audited and reversible like AI merges

### Bug: Preserve boolean types in generated Cypher
Priority: P1
Estimate: 3h
Source: V2 Alpha Bridging Plan BRG-039 and gap assessment §3.5. Generated Cypher currently serialises booleans as `1`/`0` because integer handling runs before boolean handling. Correct the serializer while the manual-node provenance work is implemented under the Graph stories. This is required for the initial release because type corruption changes evidential properties silently.

Acceptance criteria:
- Boolean properties generated through every supported write path round-trip through Neo4j as `true`/`false`, not `1`/`0`.
- Regression fixtures cover booleans beside integers and confirm existing numeric properties remain numeric.

### Task: Rebuild snapshot PDF export on the shared export service
Priority: P1
Estimate: 10h
Snapshot PDF export is absent from V2 even though investigators use saved snapshots as stable review artifacts (V2 Gap Assessment §3.4 item 39, BRG-037). Implement the PDF endpoint and UI action on the shared server-side export foundation, retaining the scope and fidelity requirements in the Snapshot export story. This is required for a credible alpha because a saved snapshot must be deliverable outside the application.

Acceptance criteria:
- A permitted investigator can export a saved snapshot to PDF from its current UI surface.
- The PDF contains only the snapshot’s saved graph, events, entities and notes and carries its snapshot version/hash.
- Exporting does not change snapshot capture or restore behavior, and a non-member receives 403.

### Task: Restore explicit provenance stamps on investigator-created nodes
Priority: P1
Estimate: 5h
V2 lost the `user_created`, `created_by`, `created_at` and `source: 'manual'` fields that distinguish investigator assertions from ingested evidence (V2 Gap Assessment §3.5, BRG-039). Restore these fields across every manual node-creation path and expose them through the approved details/provenance UI. This is required for a credible alpha because authored assertions must never be mistaken for extracted facts.

Acceptance criteria:
- Every manually created node stores `user_created=true`, the authenticated creator, creation timestamp and `source='manual'`.
- Ingested nodes do not receive a false manual provenance stamp.
- Graph details, exports and audit history preserve and display the distinction after edit, merge, recycle and restore.

## Epic: Administration, Deployment & Recovery
Color: #3f6f8f
Operate each isolated customer instance through guarded administration, immutable releases, strict readiness checks, monitored backups and rehearsed clean restores.

### Story: Retain AI Costs as an admin operations control
Priority: P0
Source: Release backlog OPS-001 (repository and product audit, 16 July 2026). Cost visibility is release-critical even if the tab is not useful to ordinary investigators.
Release gate: Before feature freeze. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The scope decision is explicit; operators can reconcile and cap AI spend without exposing inappropriate provider details.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Confirm AI Costs remains admin-only and rename/reposition it under Operations if clearer
Priority: P0
Estimate: 4h
Source: Release backlog OPS-001, task 1. Confirm AI Costs remains admin-only and rename/reposition it under Operations if clearer.
Implement this bounded change under “Retain AI Costs as an admin operations control”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Confirm AI Costs remains admin-only and rename/reposition it under Operations if clearer
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The scope decision is explicit; operators can reconcile and cap AI spend without exposing inappropriate provider details.

#### Task: Reconcile every ingestion/chat/agent/provider call and surface unattributed/missing-price records
Priority: P0
Estimate: 12h
Source: Release backlog OPS-001, task 2. Reconcile every ingestion/chat/agent/provider call and surface unattributed/missing-price records.
Implement this bounded change under “Retain AI Costs as an admin operations control”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Reconcile every ingestion/chat/agent/provider call and surface unattributed/missing-price records
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The scope decision is explicit; operators can reconcile and cap AI spend without exposing inappropriate provider details.

#### Task: Add budgets, forecasts, warnings, hard caps and anomaly alerts by case/user/provider
Priority: P0
Estimate: 8h
Source: Release backlog OPS-001, task 3. Add budgets, forecasts, warnings, hard caps and anomaly alerts by case/user/provider.
Implement this bounded change under “Retain AI Costs as an admin operations control”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add budgets, forecasts, warnings, hard caps and anomaly alerts by case/user/provider
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The scope decision is explicit; operators can reconcile and cap AI spend without exposing inappropriate provider details.

#### Task: Add authorised CSV/PDF export for billing/support reconciliation
Priority: P0
Estimate: 8h
Source: Release backlog OPS-001, task 4. Add authorised CSV/PDF export for billing/support reconciliation.
Implement this bounded change under “Retain AI Costs as an admin operations control”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add authorised CSV/PDF export for billing/support reconciliation
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The scope decision is explicit; operators can reconcile and cap AI spend without exposing inappropriate provider details.

#### Task: If customer admins should not see provider economics, separate customer usage allowances from internal cost detail
Priority: P0
Estimate: 8h
Source: Release backlog OPS-001, task 5. If customer admins should not see provider economics, separate customer usage allowances from internal cost detail.
Implement this bounded change under “Retain AI Costs as an admin operations control”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before feature freeze so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: If customer admins should not see provider economics, separate customer usage allowances from internal cost detail
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The scope decision is explicit; operators can reconcile and cap AI spend without exposing inappropriate provider details.

### Story: Separate immutable security audit from technical logs
Priority: P0
Source: Release backlog OPS-002 (repository and product audit, 16 July 2026). Do not let a compromised application admin erase the history needed to investigate access or deletion.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Required events are queryable after an application-level log clear or database compromise scenario and contain no evidence payloads/secrets.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Define security event coverage for auth, case access, evidence, exports, permissions, admin/support and destructive actions
Priority: P0
Estimate: 8h
Source: Release backlog OPS-002, task 1. Define security event coverage for auth, case access, evidence, exports, permissions, admin/support and destructive actions.
Implement this bounded change under “Separate immutable security audit from technical logs”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define security event coverage for auth, case access, evidence, exports, permissions, admin/support and destructive actions
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Required events are queryable after an application-level log clear or database compromise scenario and contain no evidence payloads/secrets.

#### Task: Store actor, case/object, action, result, IP/session and correlation ID while redacting content/secrets
Priority: P0
Estimate: 8h
Source: Release backlog OPS-002, task 2. Store actor, case/object, action, result, IP/session and correlation ID while redacting content/secrets.
Implement this bounded change under “Separate immutable security audit from technical logs”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Store actor, case/object, action, result, IP/session and correlation ID while redacting content/secrets
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Required events are queryable after an application-level log clear or database compromise scenario and contain no evidence payloads/secrets.

#### Task: Export security events to a protected append-only sink with time-based retention
Priority: P0
Estimate: 8h
Source: Release backlog OPS-002, task 3. Export security events to a protected append-only sink with time-based retention.
Implement this bounded change under “Separate immutable security audit from technical logs”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Export security events to a protected append-only sink with time-based retention
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Required events are queryable after an application-level log clear or database compromise scenario and contain no evidence payloads/secrets.

#### Task: Keep technical diagnostics separately searchable and privacy-safe
Priority: P0
Estimate: 8h
Source: Release backlog OPS-002, task 4. Keep technical diagnostics separately searchable and privacy-safe.
Implement this bounded change under “Separate immutable security audit from technical logs”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep technical diagnostics separately searchable and privacy-safe
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Required events are queryable after an application-level log clear or database compromise scenario and contain no evidence payloads/secrets.

#### Task: Remove ordinary clear-log power and test tampering/retention boundaries
Priority: P0
Estimate: 6h
Source: Release backlog OPS-002, task 5. Remove ordinary clear-log power and test tampering/retention boundaries.
Implement this bounded change under “Separate immutable security audit from technical logs”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove ordinary clear-log power and test tampering/retention boundaries
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- Required events are queryable after an application-level log clear or database compromise scenario and contain no evidence payloads/secrets.

### Story: Make background tasks and platform updates safe to operate
Priority: P1
Source: Release backlog OPS-003 (repository and product audit, 16 July 2026). Admin controls need accurate state, confirmation, concurrency protection and recovery.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- An admin can diagnose/recover a failed task or update without shell access, duplicated work or unaudited global mutation.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Show task owner/case/type/age/progress/error/retry/cancel with safe redaction
Priority: P1
Estimate: 8h
Source: Release backlog OPS-003, task 1. Show task owner/case/type/age/progress/error/retry/cancel with safe redaction.
Implement this bounded change under “Make background tasks and platform updates safe to operate”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Show task owner/case/type/age/progress/error/retry/cancel with safe redaction
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An admin can diagnose/recover a failed task or update without shell access, duplicated work or unaudited global mutation.

#### Task: Prevent duplicate incompatible maintenance/update jobs and require reason/confirmation for destructive tasks
Priority: P1
Estimate: 8h
Source: Release backlog OPS-003, task 2. Prevent duplicate incompatible maintenance/update jobs and require reason/confirmation for destructive tasks.
Implement this bounded change under “Make background tasks and platform updates safe to operate”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Prevent duplicate incompatible maintenance/update jobs and require reason/confirmation for destructive tasks
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An admin can diagnose/recover a failed task or update without shell access, duplicated work or unaudited global mutation.

#### Task: Replace unrestricted global repair/backfill actions with admin policy, dry run and audit
Priority: P1
Estimate: 8h
Source: Release backlog OPS-003, task 3. Replace unrestricted global repair/backfill actions with admin policy, dry run and audit.
Implement this bounded change under “Make background tasks and platform updates safe to operate”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Replace unrestricted global repair/backfill actions with admin policy, dry run and audit
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An admin can diagnose/recover a failed task or update without shell access, duplicated work or unaudited global mutation.

#### Task: Report exact application/schema version and update result; preserve control after disconnect
Priority: P1
Estimate: 8h
Source: Release backlog OPS-003, task 4. Report exact application/schema version and update result; preserve control after disconnect.
Implement this bounded change under “Make background tasks and platform updates safe to operate”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Report exact application/schema version and update result; preserve control after disconnect
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- An admin can diagnose/recover a failed task or update without shell access, duplicated work or unaudited global mutation.

#### Task: Test stuck task, process restart, failed update and stale UI state
Priority: P1
Estimate: 6h
Source: Release backlog OPS-003, task 5. Test stuck task, process restart, failed update and stale UI state.
Implement this bounded change under “Make background tasks and platform updates safe to operate”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test stuck task, process restart, failed update and stale UI state
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- An admin can diagnose/recover a failed task or update without shell access, duplicated work or unaudited global mutation.

### Story: Implement trustworthy liveness, readiness and instance inventory
Priority: P0
Source: Release backlog OPS-004 (repository and product audit, 16 July 2026). A top-level ‘ok’ must not hide an unavailable database, worker or ingestion engine.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Stopping any required dependency fails readiness, blocks deployment promotion and produces an actionable inventory/alert state.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Separate liveness from readiness and return non-2xx when a required dependency is unavailable
Priority: P0
Estimate: 8h
Source: Release backlog OPS-004, task 1. Separate liveness from readiness and return non-2xx when a required dependency is unavailable.
Implement this bounded change under “Implement trustworthy liveness, readiness and instance inventory”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Separate liveness from readiness and return non-2xx when a required dependency is unavailable
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stopping any required dependency fails readiness, blocks deployment promotion and produces an actionable inventory/alert state.

#### Task: Check Postgres, Neo4j, Redis, Chroma, ingestion API/worker/queue, storage and required provider configuration
Priority: P0
Estimate: 8h
Source: Release backlog OPS-004, task 2. Check Postgres, Neo4j, Redis, Chroma, ingestion API/worker/queue, storage and required provider configuration.
Implement this bounded change under “Implement trustworthy liveness, readiness and instance inventory”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Check Postgres, Neo4j, Redis, Chroma, ingestion API/worker/queue, storage and required provider configuration
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stopping any required dependency fails readiness, blocks deployment promotion and produces an actionable inventory/alert state.

#### Task: Make deploy success require readiness plus authenticated smoke actions
Priority: P0
Estimate: 8h
Source: Release backlog OPS-004, task 3. Make deploy success require readiness plus authenticated smoke actions.
Implement this bounded change under “Implement trustworthy liveness, readiness and instance inventory”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Make deploy success require readiness plus authenticated smoke actions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stopping any required dependency fails readiness, blocks deployment promotion and produces an actionable inventory/alert state.

#### Task: Track instance/customer/environment/region/version/schema/storage/last backup/last restore/deploy/health
Priority: P0
Estimate: 12h
Source: Release backlog OPS-004, task 4. Track instance/customer/environment/region/version/schema/storage/last backup/last restore/deploy/health.
Implement this bounded change under “Implement trustworthy liveness, readiness and instance inventory”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Track instance/customer/environment/region/version/schema/storage/last backup/last restore/deploy/health
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stopping any required dependency fails readiness, blocks deployment promotion and produces an actionable inventory/alert state.

#### Task: Expose only safe diagnostics to customer admins; keep sensitive details in operations tooling
Priority: P0
Estimate: 8h
Source: Release backlog OPS-004, task 5. Expose only safe diagnostics to customer admins; keep sensitive details in operations tooling.
Implement this bounded change under “Implement trustworthy liveness, readiness and instance inventory”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Expose only safe diagnostics to customer admins; keep sensitive details in operations tooling
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Stopping any required dependency fails readiness, blocks deployment promotion and produces an actionable inventory/alert state.

### Story: Build a production network and HTTPS boundary
Priority: P0
Source: Release backlog DEP-001 (repository and product audit, 16 July 2026). Serve static assets through a supported production edge and keep application/internal services private.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Only approved HTTPS endpoints are internet-reachable and production traffic never reaches Vite preview or raw Uvicorn directly.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Place Caddy/Nginx/managed load balancer in front; expose only 80/443 and redirect to HTTPS
Priority: P0
Estimate: 8h
Source: Release backlog DEP-001, task 1. Place Caddy/Nginx/managed load balancer in front; expose only 80/443 and redirect to HTTPS.
Implement this bounded change under “Build a production network and HTTPS boundary”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Place Caddy/Nginx/managed load balancer in front; expose only 80/443 and redirect to HTTPS
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Only approved HTTPS endpoints are internet-reachable and production traffic never reaches Vite preview or raw Uvicorn directly.

#### Task: Serve versioned static frontend assets; bind backend and preview/internal services to private/loopback interfaces
Priority: P0
Estimate: 6h
Source: Release backlog DEP-001, task 2. Serve versioned static frontend assets; bind backend and preview/internal services to private/loopback interfaces.
Implement this bounded change under “Build a production network and HTTPS boundary”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Serve versioned static frontend assets; bind backend and preview/internal services to private/loopback interfaces
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Only approved HTTPS endpoints are internet-reachable and production traffic never reaches Vite preview or raw Uvicorn directly.

#### Task: Configure automatic certificates, HSTS, CSP/security headers, trusted proxy settings and request/upload limits
Priority: P0
Estimate: 8h
Source: Release backlog DEP-001, task 3. Configure automatic certificates, HSTS, CSP/security headers, trusted proxy settings and request/upload limits.
Implement this bounded change under “Build a production network and HTTPS boundary”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Configure automatic certificates, HSTS, CSP/security headers, trusted proxy settings and request/upload limits
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Only approved HTTPS endpoints are internet-reachable and production traffic never reaches Vite preview or raw Uvicorn directly.

#### Task: Restrict SSH/admin through IAP, VPN or approved network and harden host/service accounts/firewalls
Priority: P0
Estimate: 4h
Source: Release backlog DEP-001, task 4. Restrict SSH/admin through IAP, VPN or approved network and harden host/service accounts/firewalls.
Implement this bounded change under “Build a production network and HTTPS boundary”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Restrict SSH/admin through IAP, VPN or approved network and harden host/service accounts/firewalls
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Only approved HTTPS endpoints are internet-reachable and production traffic never reaches Vite preview or raw Uvicorn directly.

#### Task: Run external port, TLS and header scans in the release drill
Priority: P0
Estimate: 6h
Source: Release backlog DEP-001, task 5. Run external port, TLS and header scans in the release drill.
Implement this bounded change under “Build a production network and HTTPS boundary”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Run external port, TLS and header scans in the release drill
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Only approved HTTPS endpoints are internet-reachable and production traffic never reaches Vite preview or raw Uvicorn directly.

### Story: Release immutable, versioned artifacts through promotion stages
Priority: P0
Source: Release backlog DEP-002 (repository and product audit, 16 July 2026). Build once in CI and promote the same tested artifact instead of mutating customer servers from Git.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The digest tested in CI is the digest running on the instance, and operations can identify every customer’s exact version.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Create CI that builds signed/versioned frontend/backend/engine/container artifacts after all gates pass
Priority: P0
Estimate: 12h
Source: Release backlog DEP-002, task 1. Create CI that builds signed/versioned frontend/backend/engine/container artifacts after all gates pass.
Implement this bounded change under “Release immutable, versioned artifacts through promotion stages”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create CI that builds signed/versioned frontend/backend/engine/container artifacts after all gates pass
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The digest tested in CI is the digest running on the instance, and operations can identify every customer’s exact version.

#### Task: Publish to an approved registry with SBOM, provenance and vulnerability results
Priority: P0
Estimate: 4h
Source: Release backlog DEP-002, task 2. Publish to an approved registry with SBOM, provenance and vulnerability results.
Implement this bounded change under “Release immutable, versioned artifacts through promotion stages”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Publish to an approved registry with SBOM, provenance and vulnerability results
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The digest tested in CI is the digest running on the instance, and operations can identify every customer’s exact version.

#### Task: Deploy exact versions to staging → internal → canary → customers with recorded release channel
Priority: P0
Estimate: 8h
Source: Release backlog DEP-002, task 3. Deploy exact versions to staging → internal → canary → customers with recorded release channel.
Implement this bounded change under “Release immutable, versioned artifacts through promotion stages”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Deploy exact versions to staging → internal → canary → customers with recorded release channel
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The digest tested in CI is the digest running on the instance, and operations can identify every customer’s exact version.

#### Task: Remove production git pull, pip/npm install and source build paths
Priority: P0
Estimate: 12h
Source: Release backlog DEP-002, task 4. Remove production git pull, pip/npm install and source build paths.
Implement this bounded change under “Release immutable, versioned artifacts through promotion stages”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove production git pull, pip/npm install and source build paths
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- The digest tested in CI is the digest running on the instance, and operations can identify every customer’s exact version.

#### Task: Add authenticated smoke checks and automatic halt—not unsafe rollback—on failure
Priority: P0
Estimate: 8h
Source: Release backlog DEP-002, task 5. Add authenticated smoke checks and automatic halt—not unsafe rollback—on failure.
Implement this bounded change under “Release immutable, versioned artifacts through promotion stages”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add authenticated smoke checks and automatic halt—not unsafe rollback—on failure
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The digest tested in CI is the digest running on the instance, and operations can identify every customer’s exact version.

### Story: Make migrations and rollback recovery-safe
Priority: P0
Source: Release backlog DEP-003 (repository and product audit, 16 July 2026). Code rollback cannot be claimed when the schema may already be incompatible.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A simulated failed migration/deploy returns to a verified compatible state without data loss or manual production edits.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Adopt expand/contract backward-compatible migrations and document compatibility window per release
Priority: P0
Estimate: 12h
Source: Release backlog DEP-003, task 1. Adopt expand/contract backward-compatible migrations and document compatibility window per release.
Implement this bounded change under “Make migrations and rollback recovery-safe”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Adopt expand/contract backward-compatible migrations and document compatibility window per release
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A simulated failed migration/deploy returns to a verified compatible state without data loss or manual production edits.

#### Task: Test upgrades from the oldest supported customer version using realistic backup data
Priority: P0
Estimate: 12h
Source: Release backlog DEP-003, task 2. Test upgrades from the oldest supported customer version using realistic backup data.
Implement this bounded change under “Make migrations and rollback recovery-safe”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test upgrades from the oldest supported customer version using realistic backup data
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A simulated failed migration/deploy returns to a verified compatible state without data loss or manual production edits.

#### Task: Take/verify a pre-migration recovery point and record app/schema versions
Priority: P0
Estimate: 12h
Source: Release backlog DEP-003, task 3. Take/verify a pre-migration recovery point and record app/schema versions.
Implement this bounded change under “Make migrations and rollback recovery-safe”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Take/verify a pre-migration recovery point and record app/schema versions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A simulated failed migration/deploy returns to a verified compatible state without data loss or manual production edits.

#### Task: Declare code rollback, roll-forward or full restore strategy for every migration-bearing release
Priority: P0
Estimate: 16h
Source: Release backlog DEP-003, task 4. Declare code rollback, roll-forward or full restore strategy for every migration-bearing release.
Implement this bounded change under “Make migrations and rollback recovery-safe”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Declare code rollback, roll-forward or full restore strategy for every migration-bearing release
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A simulated failed migration/deploy returns to a verified compatible state without data loss or manual production edits.

#### Task: Replace checkout/reset scripts with immutable deployment rollback and rehearse failure after migration
Priority: P0
Estimate: 16h
Source: Release backlog DEP-003, task 5. Replace checkout/reset scripts with immutable deployment rollback and rehearse failure after migration.
Implement this bounded change under “Make migrations and rollback recovery-safe”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Replace checkout/reset scripts with immutable deployment rollback and rehearse failure after migration
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A simulated failed migration/deploy returns to a verified compatible state without data loss or manual production edits.

### Story: Implement encrypted off-instance backup and clean restore
Priority: P0
Source: Release backlog DR-001 (repository and product audit, 16 July 2026). Protect Postgres, Neo4j, evidence, generated artifacts and vector rebuild inputs as one recoverable instance.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A scheduled recovery set restores into a clean project within RTO and original evidence hashes match; the drill is recorded.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Create coordinated, versioned recovery sets with database dumps/snapshots, immutable evidence, config references and app/schema versions
Priority: P0
Estimate: 8h
Source: Release backlog DR-001, task 1. Create coordinated, versioned recovery sets with database dumps/snapshots, immutable evidence, config references and app/schema versions.
Implement this bounded change under “Implement encrypted off-instance backup and clean restore”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create coordinated, versioned recovery sets with database dumps/snapshots, immutable evidence, config references and app/schema versions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A scheduled recovery set restores into a clean project within RTO and original evidence hashes match; the drill is recorded.

#### Task: Encrypt in transit/at rest, restrict deletion, retain multiple generations and copy outside the VM failure boundary
Priority: P0
Estimate: 8h
Source: Release backlog DR-001, task 2. Encrypt in transit/at rest, restrict deletion, retain multiple generations and copy outside the VM failure boundary.
Implement this bounded change under “Implement encrypted off-instance backup and clean restore”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Encrypt in transit/at rest, restrict deletion, retain multiple generations and copy outside the VM failure boundary
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A scheduled recovery set restores into a clean project within RTO and original evidence hashes match; the drill is recorded.

#### Task: Monitor freshness/size/failure and take a verified pre-deployment backup
Priority: P0
Estimate: 12h
Source: Release backlog DR-001, task 3. Monitor freshness/size/failure and take a verified pre-deployment backup.
Implement this bounded change under “Implement encrypted off-instance backup and clean restore”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Monitor freshness/size/failure and take a verified pre-deployment backup
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A scheduled recovery set restores into a clean project within RTO and original evidence hashes match; the drill is recorded.

#### Task: Write automated clean-environment restore and rebuild Chroma when chosen
Priority: P0
Estimate: 16h
Source: Release backlog DR-001, task 4. Write automated clean-environment restore and rebuild Chroma when chosen.
Implement this bounded change under “Implement encrypted off-instance backup and clean restore”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Write automated clean-environment restore and rebuild Chroma when chosen
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A scheduled recovery set restores into a clean project within RTO and original evidence hashes match; the drill is recorded.

#### Task: Verify users/permissions, file hashes, every product view, citations, chats, audit and exports after restore
Priority: P0
Estimate: 12h
Source: Release backlog DR-001, task 5. Verify users/permissions, file hashes, every product view, citations, chats, audit and exports after restore.
Implement this bounded change under “Implement encrypted off-instance backup and clean restore”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Verify users/permissions, file hashes, every product view, citations, chats, audit and exports after restore
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A scheduled recovery set restores into a clean project within RTO and original evidence hashes match; the drill is recorded.

### Story: Add monitoring, alerts and incident runbooks
Priority: P0
Source: Release backlog OPS-005 (repository and product audit, 16 July 2026). Important failures must reach a named person with a tested response—not remain in local logs.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Each simulated critical failure produces an actionable alert and the on-call responder can follow a tested runbook to recovery/escalation.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Monitor HTTPS/certs, CPU/memory/disk, containers, API latency/errors, workers/queue, job failures, provider errors, storage and costs
Priority: P0
Estimate: 8h
Source: Release backlog OPS-005, task 1. Monitor HTTPS/certs, CPU/memory/disk, containers, API latency/errors, workers/queue, job failures, provider errors, storage and costs.
Implement this bounded change under “Add monitoring, alerts and incident runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Monitor HTTPS/certs, CPU/memory/disk, containers, API latency/errors, workers/queue, job failures, provider errors, storage and costs
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Each simulated critical failure produces an actionable alert and the on-call responder can follow a tested runbook to recovery/escalation.

#### Task: Alert on backup freshness/failure, low disk, restart loops, readiness, cost spikes and unsupported version
Priority: P0
Estimate: 12h
Source: Release backlog OPS-005, task 2. Alert on backup freshness/failure, low disk, restart loops, readiness, cost spikes and unsupported version.
Implement this bounded change under “Add monitoring, alerts and incident runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Alert on backup freshness/failure, low disk, restart loops, readiness, cost spikes and unsupported version
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Each simulated critical failure produces an actionable alert and the on-call responder can follow a tested runbook to recovery/escalation.

#### Task: Route urgent alerts to named responders with escalation/severity/support targets
Priority: P0
Estimate: 8h
Source: Release backlog OPS-005, task 3. Route urgent alerts to named responders with escalation/severity/support targets.
Implement this bounded change under “Add monitoring, alerts and incident runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Route urgent alerts to named responders with escalation/severity/support targets
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Each simulated critical failure produces an actionable alert and the on-call responder can follow a tested runbook to recovery/escalation.

#### Task: Write and exercise runbooks for outage, stuck jobs, disk full, failed backup/deploy, lost admin, provider outage and suspected breach
Priority: P0
Estimate: 12h
Source: Release backlog OPS-005, task 4. Write and exercise runbooks for outage, stuck jobs, disk full, failed backup/deploy, lost admin, provider outage and suspected breach.
Implement this bounded change under “Add monitoring, alerts and incident runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Write and exercise runbooks for outage, stuck jobs, disk full, failed backup/deploy, lost admin, provider outage and suspected breach
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Each simulated critical failure produces an actionable alert and the on-call responder can follow a tested runbook to recovery/escalation.

#### Task: Add privacy-safe structured error reporting with correlation IDs
Priority: P0
Estimate: 8h
Source: Release backlog OPS-005, task 5. Add privacy-safe structured error reporting with correlation IDs.
Implement this bounded change under “Add monitoring, alerts and incident runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add privacy-safe structured error reporting with correlation IDs
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Each simulated critical failure produces an actionable alert and the on-call responder can follow a tested runbook to recovery/escalation.

### Story: Automate isolated customer provisioning and offboarding
Priority: P0
Source: Release backlog INFRA-001 (repository and product audit, 16 July 2026). Create consistent instances without shared credentials, storage or founder-only manual steps.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A fresh customer can be provisioned and later offboarded from documented automation with no shared secret or storage path.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Build Terraform/equivalent for project/network/compute/storage/secrets/DNS/TLS/backups/monitoring/budgets
Priority: P0
Estimate: 16h
Source: Release backlog INFRA-001, task 1. Build Terraform/equivalent for project/network/compute/storage/secrets/DNS/TLS/backups/monitoring/budgets.
Implement this bounded change under “Automate isolated customer provisioning and offboarding”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Build Terraform/equivalent for project/network/compute/storage/secrets/DNS/TLS/backups/monitoring/budgets
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A fresh customer can be provisioned and later offboarded from documented automation with no shared secret or storage path.

#### Task: Use one approved isolation boundary and unique instance/service/admin identities
Priority: P0
Estimate: 4h
Source: Release backlog INFRA-001, task 2. Use one approved isolation boundary and unique instance/service/admin identities.
Implement this bounded change under “Automate isolated customer provisioning and offboarding”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Use one approved isolation boundary and unique instance/service/admin identities
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A fresh customer can be provisioned and later offboarded from documented automation with no shared secret or storage path.

#### Task: Record region, URL, customer, version, backups, health and support access in inventory
Priority: P0
Estimate: 12h
Source: Release backlog INFRA-001, task 3. Record region, URL, customer, version, backups, health and support access in inventory.
Implement this bounded change under “Automate isolated customer provisioning and offboarding”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Record region, URL, customer, version, backups, health and support access in inventory
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A fresh customer can be provisioned and later offboarded from documented automation with no shared secret or storage path.

#### Task: Implement time-bound audited support access and emergency break-glass
Priority: P0
Estimate: 12h
Source: Release backlog INFRA-001, task 4. Implement time-bound audited support access and emergency break-glass.
Implement this bounded change under “Automate isolated customer provisioning and offboarding”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Implement time-bound audited support access and emergency break-glass
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A fresh customer can be provisioned and later offboarded from documented automation with no shared secret or storage path.

#### Task: Automate export/offboarding, retention expiry and two-person irreversible deletion
Priority: P0
Estimate: 12h
Source: Release backlog INFRA-001, task 5. Automate export/offboarding, retention expiry and two-person irreversible deletion.
Implement this bounded change under “Automate isolated customer provisioning and offboarding”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Automate export/offboarding, retention expiry and two-person irreversible deletion
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A fresh customer can be provisioned and later offboarded from documented automation with no shared secret or storage path.

### Task: Stop event-loop blocking on Neo4j calls
Priority: P0
Estimate: 12h
Every v2 route handler is `async def` calling the blocking Neo4j driver directly, so one long graph query freezes the whole backend (gap assessment §3.6, BRG-008). Apply v1's pattern (ref commit `fe6d266`): sync `def` handlers or `to_thread` so blocking calls run in the threadpool.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-008, gap assessment §3.6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Blocking Neo4j calls run in the threadpool across all routers
- Concurrent-request smoke test passes while a heavy graph query is running

### Task: System-log case filter + audit retention policy
Priority: P3
Estimate: 12h
Restore the `case_id` audit filter lost in the port, and replace the silent 10K-row hard-trim with archival or an explicit retention policy — hard-deleting the oldest audit rows is indefensible for an enterprise audit trail (gap assessment §3.5/§6, BRG-041; v1 ref `3861f4d`).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-041, gap assessment §3.5/). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- System logs filter by case_id
- Old audit rows are archived or retained per an explicit documented policy; nothing is silently deleted

### Task: Exercise the six-service operations runbook against known host failures
Priority: P3
Estimate: 14h
The V2 stack adds Neo4j, Postgres, Redis, ChromaDB, engine API and engine worker, while the current host has experienced transaction-log corruption under memory pressure, tmpfs OOM and UID ownership breakage (V2 Gap Assessment Phase 4, BRG-049). Extend the shared operations runbook with service-specific health checks, restart procedures and disk/memory watermarks, then drill each known failure. This remains in the release plan because operators must be able to recover the alpha environment without improvising on customer evidence.

Acceptance criteria:
- The runbook lists health checks, safe restart order, dependencies and disk/memory thresholds for all six services.
- Monitoring produces an actionable alert for each documented watermark and service failure.
- Recorded drills cover transaction-log pressure, tmpfs exhaustion and UID ownership breakage, with corrections incorporated into the runbook.

## Epic: Quality, Performance & Accessibility
Color: #43866f
Turn release confidence into repeatable automated evidence across tests, browsers, supported data scale, dependency security, accessibility and honest result limits.

### Story: Make every required automated gate deterministic and green
Priority: P0
Source: Release backlog QA-001 (repository and product audit, 16 July 2026). The current main frontend suite/lint fail and the backend aggregate run needs a reliable completion path.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A clean checkout completes the documented quality command in CI with zero required failures and a bounded runtime.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Fix the localStorage test environment, missing Router wrapper, Markdown expectation and any underlying regressions behind 11 frontend failures
Priority: P0
Estimate: 8h
Source: Release backlog QA-001, task 1. Fix the localStorage test environment, missing Router wrapper, Markdown expectation and any underlying regressions behind 11 frontend failures.
Implement this bounded change under “Make every required automated gate deterministic and green”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Fix the localStorage test environment, missing Router wrapper, Markdown expectation and any underlying regressions behind 11 frontend failures
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A clean checkout completes the documented quality command in CI with zero required failures and a bounded runtime.

#### Task: Fix 28 lint errors/22 warnings and exclude generated Storybook output from source lint
Priority: P0
Estimate: 8h
Source: Release backlog QA-001, task 2. Fix 28 lint errors/22 warnings and exclude generated Storybook output from source lint.
Implement this bounded change under “Make every required automated gate deterministic and green”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Fix 28 lint errors/22 warnings and exclude generated Storybook output from source lint
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A clean checkout completes the documented quality command in CI with zero required failures and a bounded runtime.

#### Task: Diagnose the backend all-suite non-completion, add per-test timeouts and make the complete suite finish reliably
Priority: P0
Estimate: 8h
Source: Release backlog QA-001, task 3. Diagnose the backend all-suite non-completion, add per-test timeouts and make the complete suite finish reliably.
Implement this bounded change under “Make every required automated gate deterministic and green”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Diagnose the backend all-suite non-completion, add per-test timeouts and make the complete suite finish reliably
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A clean checkout completes the documented quality command in CI with zero required failures and a bounded runtime.

#### Task: Keep Evidence Engine 34/34 and add regression tests for changed ingestion/security behavior
Priority: P0
Estimate: 8h
Source: Release backlog QA-001, task 4. Keep Evidence Engine 34/34 and add regression tests for changed ingestion/security behavior.
Implement this bounded change under “Make every required automated gate deterministic and green”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Keep Evidence Engine 34/34 and add regression tests for changed ingestion/security behavior
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A clean checkout completes the documented quality command in CI with zero required failures and a bounded runtime.

#### Task: Publish coverage and fail release creation on test/lint/type/build failure
Priority: P0
Estimate: 12h
Source: Release backlog QA-001, task 5. Publish coverage and fail release creation on test/lint/type/build failure.
Implement this bounded change under “Make every required automated gate deterministic and green”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Publish coverage and fail release creation on test/lint/type/build failure
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A clean checkout completes the documented quality command in CI with zero required failures and a bounded runtime.

### Story: Create CI and browser end-to-end release journeys
Priority: P0
Source: Release backlog QA-002 (repository and product audit, 16 July 2026). Automate the real flows and permission boundaries that unit tests currently miss.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- CI can detect each confirmed release blocker class and produces no releasable artifact when a required journey fails.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Run Python checks/tests, frontend lint/type/test/build, dependency/secret/container scans and migration upgrade tests on every PR
Priority: P0
Estimate: 12h
Source: Release backlog QA-002, task 1. Run Python checks/tests, frontend lint/type/test/build, dependency/secret/container scans and migration upgrade tests on every PR.
Implement this bounded change under “Create CI and browser end-to-end release journeys”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Run Python checks/tests, frontend lint/type/test/build, dependency/secret/container scans and migration upgrade tests on every PR
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- CI can detect each confirmed release blocker class and produces no releasable artifact when a required journey fails.

#### Task: Add browser journeys for login/logout/session expiry, case/members, upload/process, Graph merge/recycle, Timeline, Map, Financial, Chat citations,…
Priority: P0
Estimate: 16h
Source: Release backlog QA-002, task 2. Add browser journeys for login/logout/session expiry, case/members, upload/process, Graph merge/recycle, Timeline, Map, Financial, Chat citations, Agent approval, Workspace save, Reports/exports and admin boundaries.
Implement this bounded change under “Create CI and browser end-to-end release journeys”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add browser journeys for login/logout/session expiry, case/members, upload/process, Graph merge/recycle, Timeline, Map, Financial, Chat citations, Agent approval, Workspace save, Reports/exports and admin boundaries
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- CI can detect each confirmed release blocker class and produces no releasable artifact when a required journey fails.

#### Task: Run owner/editor/viewer/non-member/direct-URL/direct-API negative cases
Priority: P0
Estimate: 6h
Source: Release backlog QA-002, task 3. Run owner/editor/viewer/non-member/direct-URL/direct-API negative cases.
Implement this bounded change under “Create CI and browser end-to-end release journeys”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Run owner/editor/viewer/non-member/direct-URL/direct-API negative cases
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- CI can detect each confirmed release blocker class and produces no releasable artifact when a required journey fails.

#### Task: Capture screenshots/traces on failure using synthetic fixture data
Priority: P0
Estimate: 8h
Source: Release backlog QA-002, task 4. Capture screenshots/traces on failure using synthetic fixture data.
Implement this bounded change under “Create CI and browser end-to-end release journeys”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Capture screenshots/traces on failure using synthetic fixture data
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- CI can detect each confirmed release blocker class and produces no releasable artifact when a required journey fails.

#### Task: Block artifact publishing/promotion unless required jobs pass
Priority: P0
Estimate: 4h
Source: Release backlog QA-002, task 5. Block artifact publishing/promotion unless required jobs pass.
Implement this bounded change under “Create CI and browser end-to-end release journeys”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Block artifact publishing/promotion unless required jobs pass
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- CI can detect each confirmed release blocker class and produces no releasable artifact when a required journey fails.

### Story: Resolve and continuously scan vulnerable dependencies
Priority: P0
Source: Release backlog QA-003 (repository and product audit, 16 July 2026). Update React Router/lodash paths and keep risk visible across JavaScript, Python and container images.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- No unaccepted critical/high release vulnerability remains and every exception is time-bound, owned and documented.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Upgrade or otherwise remove the current high/moderate runtime advisories and run regression tests
Priority: P0
Estimate: 6h
Source: Release backlog QA-003, task 1. Upgrade or otherwise remove the current high/moderate runtime advisories and run regression tests.
Implement this bounded change under “Resolve and continuously scan vulnerable dependencies”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Upgrade or otherwise remove the current high/moderate runtime advisories and run regression tests
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- No unaccepted critical/high release vulnerability remains and every exception is time-bound, owned and documented.

#### Task: Audit Python direct/transitive packages and base/container images with an agreed scanner
Priority: P0
Estimate: 6h
Source: Release backlog QA-003, task 2. Audit Python direct/transitive packages and base/container images with an agreed scanner.
Implement this bounded change under “Resolve and continuously scan vulnerable dependencies”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Audit Python direct/transitive packages and base/container images with an agreed scanner
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- No unaccepted critical/high release vulnerability remains and every exception is time-bound, owned and documented.

#### Task: Generate SBOMs and record accepted exceptions with owner, exploitability and expiry
Priority: P0
Estimate: 8h
Source: Release backlog QA-003, task 3. Generate SBOMs and record accepted exceptions with owner, exploitability and expiry.
Implement this bounded change under “Resolve and continuously scan vulnerable dependencies”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Generate SBOMs and record accepted exceptions with owner, exploitability and expiry
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- No unaccepted critical/high release vulnerability remains and every exception is time-bound, owned and documented.

#### Task: Enable dependency update automation and a supported-version policy
Priority: P0
Estimate: 8h
Source: Release backlog QA-003, task 4. Enable dependency update automation and a supported-version policy.
Implement this bounded change under “Resolve and continuously scan vulnerable dependencies”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Enable dependency update automation and a supported-version policy
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- No unaccepted critical/high release vulnerability remains and every exception is time-bound, owned and documented.

#### Task: Add secret scanning for current/history/release artifacts
Priority: P0
Estimate: 8h
Source: Release backlog QA-003, task 5. Add secret scanning for current/history/release artifacts.
Implement this bounded change under “Resolve and continuously scan vulnerable dependencies”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add secret scanning for current/history/release artifacts
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- No unaccepted critical/high release vulnerability remains and every exception is time-bound, owned and documented.

### Story: Meet frontend performance and bundle budgets
Priority: P1
Source: Release backlog PERF-001 (repository and product audit, 16 July 2026). Code splitting exists for pages, but the shared initial bundle remains too large and the 3D landing hero triggers a warning.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Both sites meet signed bundle and Core Web Vitals budgets without removing required functionality or accessibility fallbacks.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Analyse main bundle and split shared chart/editor/map/utility dependencies into cacheable lazy chunks
Priority: P1
Estimate: 8h
Source: Release backlog PERF-001, task 1. Analyse main bundle and split shared chart/editor/map/utility dependencies into cacheable lazy chunks.
Implement this bounded change under “Meet frontend performance and bundle budgets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Analyse main bundle and split shared chart/editor/map/utility dependencies into cacheable lazy chunks
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Both sites meet signed bundle and Core Web Vitals budgets without removing required functionality or accessibility fallbacks.

#### Task: Set budgets for initial JS/CSS, route chunks, LCP, INP and CLS on target hardware/network
Priority: P1
Estimate: 8h
Source: Release backlog PERF-001, task 2. Set budgets for initial JS/CSS, route chunks, LCP, INP and CLS on target hardware/network.
Implement this bounded change under “Meet frontend performance and bundle budgets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Set budgets for initial JS/CSS, route chunks, LCP, INP and CLS on target hardware/network
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Both sites meet signed bundle and Core Web Vitals budgets without removing required functionality or accessibility fallbacks.

#### Task: Optimise/defer the landing 3D asset/chunk and keep a fast reduced-motion/WebGL fallback
Priority: P1
Estimate: 8h
Source: Release backlog PERF-001, task 3. Optimise/defer the landing 3D asset/chunk and keep a fast reduced-motion/WebGL fallback.
Implement this bounded change under “Meet frontend performance and bundle budgets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Optimise/defer the landing 3D asset/chunk and keep a fast reduced-motion/WebGL fallback
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Both sites meet signed bundle and Core Web Vitals budgets without removing required functionality or accessibility fallbacks.

#### Task: Move expensive Graph/Timeline/Cellebrite computation off the main thread where profiling justifies it
Priority: P1
Estimate: 8h
Source: Release backlog PERF-001, task 4. Move expensive Graph/Timeline/Cellebrite computation off the main thread where profiling justifies it.
Implement this bounded change under “Meet frontend performance and bundle budgets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Move expensive Graph/Timeline/Cellebrite computation off the main thread where profiling justifies it
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Both sites meet signed bundle and Core Web Vitals budgets without removing required functionality or accessibility fallbacks.

#### Task: Measure cold/warm load and route transitions in CI or scheduled lab runs
Priority: P1
Estimate: 8h
Source: Release backlog PERF-001, task 5. Measure cold/warm load and route transitions in CI or scheduled lab runs.
Implement this bounded change under “Meet frontend performance and bundle budgets”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Measure cold/warm load and route transitions in CI or scheduled lab runs
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Both sites meet signed bundle and Core Web Vitals budgets without removing required functionality or accessibility fallbacks.

### Story: Publish and prove supported data-scale limits
Priority: P1
Source: Release backlog PERF-002 (repository and product audit, 16 July 2026). Replace implicit unlimited claims with measured case/file/entity/event/transaction/mobile-report thresholds.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Published limits come from a passing measured test and the UI clearly handles attempts beyond them.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Create small/typical/maximum synthetic datasets with many small and very large files
Priority: P1
Estimate: 8h
Source: Release backlog PERF-002, task 1. Create small/typical/maximum synthetic datasets with many small and very large files.
Implement this bounded change under “Publish and prove supported data-scale limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create small/typical/maximum synthetic datasets with many small and very large files
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Published limits come from a passing measured test and the UI clearly handles attempts beyond them.

#### Task: Load-test simultaneous ingestion and investigation plus worker restart/near-full disk/provider delay
Priority: P1
Estimate: 12h
Source: Release backlog PERF-002, task 2. Load-test simultaneous ingestion and investigation plus worker restart/near-full disk/provider delay.
Implement this bounded change under “Publish and prove supported data-scale limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Load-test simultaneous ingestion and investigation plus worker restart/near-full disk/provider delay
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Published limits come from a passing measured test and the UI clearly handles attempts beyond them.

#### Task: Measure API latency, queue delay, completion time, browser memory/FPS and export duration/error rate
Priority: P1
Estimate: 6h
Source: Release backlog PERF-002, task 3. Measure API latency, queue delay, completion time, browser memory/FPS and export duration/error rate.
Implement this bounded change under “Publish and prove supported data-scale limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Measure API latency, queue delay, completion time, browser memory/FPS and export duration/error rate
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- Published limits come from a passing measured test and the UI clearly handles attempts beyond them.

#### Task: Optimise or lower published limits where thresholds fail; show caps and partial results in UI
Priority: P1
Estimate: 4h
Source: Release backlog PERF-002, task 4. Optimise or lower published limits where thresholds fail; show caps and partial results in UI.
Implement this bounded change under “Publish and prove supported data-scale limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Optimise or lower published limits where thresholds fail; show caps and partial results in UI
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Published limits come from a passing measured test and the UI clearly handles attempts beyond them.

#### Task: Repeat the maximum case test before release promotion
Priority: P1
Estimate: 6h
Source: Release backlog PERF-002, task 5. Repeat the maximum case test before release promotion.
Implement this bounded change under “Publish and prove supported data-scale limits”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Repeat the maximum case test before release promotion
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Published limits come from a passing measured test and the UI clearly handles attempts beyond them.

### Story: Complete accessibility and keyboard acceptance
Priority: P1
Source: Release backlog A11Y-001 (repository and product audit, 16 July 2026). The data-dense application needs a supported keyboard/high-zoom/screen-reader path, not only visual polish.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A keyboard/high-zoom user can complete the documented core journey, and no critical/serious automated issue remains unexplained.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Audit WCAG 2.1 AA essentials: names/roles/states, focus order/visibility, contrast, headings, dialogs, errors and live progress
Priority: P1
Estimate: 6h
Source: Release backlog A11Y-001, task 1. Audit WCAG 2.1 AA essentials: names/roles/states, focus order/visibility, contrast, headings, dialogs, errors and live progress.
Implement this bounded change under “Complete accessibility and keyboard acceptance”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Audit WCAG 2.1 AA essentials: names/roles/states, focus order/visibility, contrast, headings, dialogs, errors and live progress
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A keyboard/high-zoom user can complete the documented core journey, and no critical/serious automated issue remains unexplained.

#### Task: Test keyboard-only Graph alternatives, tables, filters, drag/drop move alternative, right rail, menus and exports
Priority: P1
Estimate: 6h
Source: Release backlog A11Y-001, task 2. Test keyboard-only Graph alternatives, tables, filters, drag/drop move alternative, right rail, menus and exports.
Implement this bounded change under “Complete accessibility and keyboard acceptance”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test keyboard-only Graph alternatives, tables, filters, drag/drop move alternative, right rail, menus and exports
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A keyboard/high-zoom user can complete the documented core journey, and no critical/serious automated issue remains unexplained.

#### Task: Test 200–400% zoom/reflow at supported desktop widths and reduced motion
Priority: P1
Estimate: 8h
Source: Release backlog A11Y-001, task 3. Test 200–400% zoom/reflow at supported desktop widths and reduced motion.
Implement this bounded change under “Complete accessibility and keyboard acceptance”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test 200–400% zoom/reflow at supported desktop widths and reduced motion
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A keyboard/high-zoom user can complete the documented core journey, and no critical/serious automated issue remains unexplained.

#### Task: Provide text/table alternatives for canvas/map information needed to complete core tasks
Priority: P1
Estimate: 8h
Source: Release backlog A11Y-001, task 4. Provide text/table alternatives for canvas/map information needed to complete core tasks.
Implement this bounded change under “Complete accessibility and keyboard acceptance”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Provide text/table alternatives for canvas/map information needed to complete core tasks
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A keyboard/high-zoom user can complete the documented core journey, and no critical/serious automated issue remains unexplained.

#### Task: Add Storybook accessibility checks and browser smoke coverage for critical flows
Priority: P1
Estimate: 8h
Source: Release backlog A11Y-001, task 5. Add Storybook accessibility checks and browser smoke coverage for critical flows.
Implement this bounded change under “Complete accessibility and keyboard acceptance”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add Storybook accessibility checks and browser smoke coverage for critical flows
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A keyboard/high-zoom user can complete the documented core journey, and no critical/serious automated issue remains unexplained.

### Story: Validate supported browsers and every state
Priority: P1
Source: Release backlog QA-004 (repository and product audit, 16 July 2026). Polish loading, empty, error, offline/degraded and concurrency states across the whole application.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The supported-browser matrix passes and every primary route has usable non-happy-path behavior with no visible placeholder action.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Define supported Chrome/Edge versions and minimum desktop resolution; add others only if promised
Priority: P1
Estimate: 8h
Source: Release backlog QA-004, task 1. Define supported Chrome/Edge versions and minimum desktop resolution; add others only if promised.
Implement this bounded change under “Validate supported browsers and every state”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define supported Chrome/Edge versions and minimum desktop resolution; add others only if promised
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The supported-browser matrix passes and every primary route has usable non-happy-path behavior with no visible placeholder action.

#### Task: Walk every route with empty, loading, partial, permission denied, API error, timeout and session-expired states
Priority: P1
Estimate: 16h
Source: Release backlog QA-004, task 2. Walk every route with empty, loading, partial, permission denied, API error, timeout and session-expired states.
Implement this bounded change under “Validate supported browsers and every state”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Walk every route with empty, loading, partial, permission denied, API error, timeout and session-expired states
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The supported-browser matrix passes and every primary route has usable non-happy-path behavior with no visible placeholder action.

#### Task: Test slow network, refresh during long work, two simultaneous users and provider/database degradation
Priority: P1
Estimate: 6h
Source: Release backlog QA-004, task 3. Test slow network, refresh during long work, two simultaneous users and provider/database degradation.
Implement this bounded change under “Validate supported browsers and every state”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test slow network, refresh during long work, two simultaneous users and provider/database degradation
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The supported-browser matrix passes and every primary route has usable non-happy-path behavior with no visible placeholder action.

#### Task: Remove console-only errors, technical dead ends, placeholder copy and unhandled buttons
Priority: P1
Estimate: 4h
Source: Release backlog QA-004, task 4. Remove console-only errors, technical dead ends, placeholder copy and unhandled buttons.
Implement this bounded change under “Validate supported browsers and every state”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- Repository, navigation and API checks demonstrate that the named surface is absent: Remove console-only errors, technical dead ends, placeholder copy and unhandled buttons
- Regression coverage demonstrates that the supported replacement path remains available and authorised.
- The supported-browser matrix passes and every primary route has usable non-happy-path behavior with no visible placeholder action.

#### Task: Run a non-developer exploratory ‘day in the life’ and triage every blocker
Priority: P1
Estimate: 6h
Source: Release backlog QA-004, task 5. Run a non-developer exploratory ‘day in the life’ and triage every blocker.
Implement this bounded change under “Validate supported browsers and every state”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Run a non-developer exploratory ‘day in the life’ and triage every blocker
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The supported-browser matrix passes and every primary route has usable non-happy-path behavior with no visible placeholder action.

### Story: No silently truncated result set anywhere
One sweep across every capped surface (gap assessment §6, BRG-046): `/api/graph` (~20K, feeds table/map/CSV), cellebrite intersections (20K loader discards `truncated`), cross-phone graph (200/300), comms search (200), cellebrite timeline `total_estimate`, v2 timeline client 100-page stop. An analyst asserting "these phones never intersected" must never be reading a silently truncated set. Pattern: v1 `5bca0a8`, `61961f4`.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-046, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Every listed surface returns honest totals and shows a truncation banner when capped
- A grep-level audit confirms no remaining silent caps

#### Task: Return total + truncated on every capped endpoint
Priority: P3
Estimate: 12h
Add honest `total` and `truncated` fields to each listed backend surface, following the v1 pattern.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-046, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each listed endpoint returns total and truncated accurately on an over-cap fixture
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Truncation banners in the UI
Priority: P3
Estimate: 8h
Render a visible "showing X of Y" banner on every consuming view when truncated is set, including the timeline client's 100-page stop.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-046, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Every consuming view shows the banner on an over-cap fixture; no view renders a truncated set unannounced
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Grep-level cap audit + regression tests
Priority: P3
Estimate: 4h
Sweep the codebase for remaining hard caps/limits without signals and add regression tests for the fixed surfaces.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-046, gap assessment §6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Audit findings documented; every remaining cap either signals honestly or has a ticket
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Task: Scale verification
Priority: P3
Estimate: 14h
v1 500s on 571k-node cases; prove v2's architecture actually handles production scale — ingest, graph reads, and exports — or fix what doesn't (gap assessment Phase 4, BRG-048).
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-048). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Ingest, graph reads, and exports complete on a 571k-node-scale case without 500s
- Any failure has a profiled root cause and a ticket

## Epic: Customer Release, Compliance & Cutover
Color: #63727a
Align the public promise, documentation, legal terms, onboarding, alpha feedback and V1 cutover so the first customer receives the product that was tested and approved.

### Story: Make the landing site production-complete and evidence-based
Priority: P1
Source: Release backlog WEB-001 (repository and product audit, 16 July 2026). Public control/provenance claims must match implemented architecture and the walkthrough request must fail clearly when email is not configured.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The deployed landing site has working contact/legal paths, passes the browser matrix and makes no unsupported product/security claim.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Review every security, provenance, deployment and portability claim against the release evidence
Priority: P1
Estimate: 6h
Source: Release backlog WEB-001, task 1. Review every security, provenance, deployment and portability claim against the release evidence.
Implement this bounded change under “Make the landing site production-complete and evidence-based”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Review every security, provenance, deployment and portability claim against the release evidence
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The deployed landing site has working contact/legal paths, passes the browser matrix and makes no unsupported product/security claim.

#### Task: Require/validate the contact email at build/deploy; provide a no-mail-client fallback or clear support contact
Priority: P1
Estimate: 12h
Source: Release backlog WEB-001, task 2. Require/validate the contact email at build/deploy; provide a no-mail-client fallback or clear support contact.
Implement this bounded change under “Make the landing site production-complete and evidence-based”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Require/validate the contact email at build/deploy; provide a no-mail-client fallback or clear support contact
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The deployed landing site has working contact/legal paths, passes the browser matrix and makes no unsupported product/security claim.

#### Task: Add Privacy, Terms, security/contact and accessibility links in the footer
Priority: P1
Estimate: 8h
Source: Release backlog WEB-001, task 3. Add Privacy, Terms, security/contact and accessibility links in the footer.
Implement this bounded change under “Make the landing site production-complete and evidence-based”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add Privacy, Terms, security/contact and accessibility links in the footer
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The deployed landing site has working contact/legal paths, passes the browser matrix and makes no unsupported product/security claim.

#### Task: Test metadata, favicon, social preview, canonical URL, sitemap/robots and analytics consent if analytics is added
Priority: P1
Estimate: 8h
Source: Release backlog WEB-001, task 4. Test metadata, favicon, social preview, canonical URL, sitemap/robots and analytics consent if analytics is added.
Implement this bounded change under “Make the landing site production-complete and evidence-based”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Test metadata, favicon, social preview, canonical URL, sitemap/robots and analytics consent if analytics is added
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The deployed landing site has working contact/legal paths, passes the browser matrix and makes no unsupported product/security claim.

#### Task: Run responsive, keyboard, reduced-motion, no-WebGL and performance checks
Priority: P1
Estimate: 6h
Source: Release backlog WEB-001, task 5. Run responsive, keyboard, reduced-motion, no-WebGL and performance checks.
Implement this bounded change under “Make the landing site production-complete and evidence-based”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Run responsive, keyboard, reduced-motion, no-WebGL and performance checks
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- The deployed landing site has working contact/legal paths, passes the browser matrix and makes no unsupported product/security claim.

### Story: Publish versioned customer documentation
Priority: P1
Source: Release backlog DOC-001 (repository and product audit, 16 July 2026). A new investigator should complete core work without undocumented founder knowledge.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- The documentation-only usability run completes the agreed journey; docs version and screenshots match the release candidate.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Write first login/MFA, roles, case collaboration, supported evidence/limits, processing errors and recovery
Priority: P1
Estimate: 8h
Source: Release backlog DOC-001, task 1. Write first login/MFA, roles, case collaboration, supported evidence/limits, processing errors and recovery.
Implement this bounded change under “Publish versioned customer documentation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Write first login/MFA, roles, case collaboration, supported evidence/limits, processing errors and recovery
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The documentation-only usability run completes the agreed journey; docs version and screenshots match the release candidate.

#### Task: Document Graph, Table, Timeline, Map, Financial, Cellebrite, Workspace/Notebook, AI/citations, Agent approvals and promised Reports/exports
Priority: P1
Estimate: 4h
Source: Release backlog DOC-001, task 2. Document Graph, Table, Timeline, Map, Financial, Cellebrite, Workspace/Notebook, AI/citations, Agent approvals and promised Reports/exports.
Implement this bounded change under “Publish versioned customer documentation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Document Graph, Table, Timeline, Map, Financial, Cellebrite, Workspace/Notebook, AI/citations, Agent approvals and promised Reports/exports
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- The documentation-only usability run completes the agreed journey; docs version and screenshots match the release candidate.

#### Task: Explain confidence, provenance, human review, retention, restore requests, deletion, support and known limitations
Priority: P1
Estimate: 12h
Source: Release backlog DOC-001, task 3. Explain confidence, provenance, human review, retention, restore requests, deletion, support and known limitations.
Implement this bounded change under “Publish versioned customer documentation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Explain confidence, provenance, human review, retention, restore requests, deletion, support and known limitations
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The documentation-only usability run completes the agreed journey; docs version and screenshots match the release candidate.

#### Task: Generate branded PDF/web outputs from versioned source and tie them to application versions
Priority: P1
Estimate: 8h
Source: Release backlog DOC-001, task 4. Generate branded PDF/web outputs from versioned source and tie them to application versions.
Implement this bounded change under “Publish versioned customer documentation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Generate branded PDF/web outputs from versioned source and tie them to application versions
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The documentation-only usability run completes the agreed journey; docs version and screenshots match the release candidate.

#### Task: Have a non-developer complete a first investigation using only the guide
Priority: P1
Estimate: 8h
Source: Release backlog DOC-001, task 5. Have a non-developer complete a first investigation using only the guide.
Implement this bounded change under “Publish versioned customer documentation”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Have a non-developer complete a first investigation using only the guide
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- The documentation-only usability run completes the agreed journey; docs version and screenshots match the release candidate.

### Story: Write and exercise internal operating runbooks
Priority: P0
Source: Release backlog DOC-002 (repository and product audit, 16 July 2026). Provisioning and incidents must not depend on one person’s memory.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A second operator can execute each critical runbook in a rehearsal without undocumented steps or unsafe access.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Document customer provisioning, secret rotation, admin recovery and support access
Priority: P0
Estimate: 8h
Source: Release backlog DOC-002, task 1. Document customer provisioning, secret rotation, admin recovery and support access.
Implement this bounded change under “Write and exercise internal operating runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Document customer provisioning, secret rotation, admin recovery and support access
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A second operator can execute each critical runbook in a rehearsal without undocumented steps or unsafe access.

#### Task: Document deploy/canary/migration/rollback/restore and version inventory
Priority: P0
Estimate: 12h
Source: Release backlog DOC-002, task 2. Document deploy/canary/migration/rollback/restore and version inventory.
Implement this bounded change under “Write and exercise internal operating runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Document deploy/canary/migration/rollback/restore and version inventory
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A second operator can execute each critical runbook in a rehearsal without undocumented steps or unsafe access.

#### Task: Document outage, worker/provider failure, disk/cost spike, failed backup and suspected breach response
Priority: P0
Estimate: 12h
Source: Release backlog DOC-002, task 3. Document outage, worker/provider failure, disk/cost spike, failed backup and suspected breach response.
Implement this bounded change under “Write and exercise internal operating runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Document outage, worker/provider failure, disk/cost spike, failed backup and suspected breach response
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A second operator can execute each critical runbook in a rehearsal without undocumented steps or unsafe access.

#### Task: Document customer export/offboarding/retention expiry/deletion and evidence preservation
Priority: P0
Estimate: 4h
Source: Release backlog DOC-002, task 4. Document customer export/offboarding/retention expiry/deletion and evidence preservation.
Implement this bounded change under “Write and exercise internal operating runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Document customer export/offboarding/retention expiry/deletion and evidence preservation
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A second operator can execute each critical runbook in a rehearsal without undocumented steps or unsafe access.

#### Task: Exercise each high-risk runbook and record corrections/owner/review date
Priority: P0
Estimate: 6h
Source: Release backlog DOC-002, task 5. Exercise each high-risk runbook and record corrections/owner/review date.
Implement this bounded change under “Write and exercise internal operating runbooks”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The named check is executed against the release candidate and attached evidence demonstrates: Exercise each high-risk runbook and record corrections/owner/review date
- Every unexplained mismatch or failed threshold produces a linked blocking ticket before this task can close.
- A second operator can execute each critical runbook in a rehearsal without undocumented steps or unsafe access.

### Story: Complete customer legal, privacy and AI terms
Priority: P0
Source: Release backlog LEGAL-001 (repository and product audit, 16 July 2026). Investigation data is highly sensitive; contracts and notices must accurately allocate responsibility and describe processing.
Release gate: Before external data. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- Signed terms and notices match the deployed architecture/provider settings and the promised release limits/support model.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Finalise customer/service agreement, DPA, privacy notice, acceptable-use, confidentiality, IP and liability/termination/payment terms with…
Priority: P0
Estimate: 8h
Source: Release backlog LEGAL-001, task 1. Finalise customer/service agreement, DPA, privacy notice, acceptable-use, confidentiality, IP and liability/termination/payment terms with qualified advice.
Implement this bounded change under “Complete customer legal, privacy and AI terms”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Finalise customer/service agreement, DPA, privacy notice, acceptable-use, confidentiality, IP and liability/termination/payment terms with qualified advice
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Signed terms and notices match the deployed architecture/provider settings and the promised release limits/support model.

#### Task: Define controller/processor roles, regions/transfers, retention, backup, deletion, legal hold and breach notification
Priority: P0
Estimate: 12h
Source: Release backlog LEGAL-001, task 2. Define controller/processor roles, regions/transfers, retention, backup, deletion, legal hold and breach notification.
Implement this bounded change under “Complete customer legal, privacy and AI terms”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define controller/processor roles, regions/transfers, retention, backup, deletion, legal hold and breach notification
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Signed terms and notices match the deployed architecture/provider settings and the promised release limits/support model.

#### Task: Publish subprocessors for cloud, AI, maps/geocoding, email, monitoring and support
Priority: P0
Estimate: 8h
Source: Release backlog LEGAL-001, task 3. Publish subprocessors for cloud, AI, maps/geocoding, email, monitoring and support.
Implement this bounded change under “Complete customer legal, privacy and AI terms”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Publish subprocessors for cloud, AI, maps/geocoding, email, monitoring and support
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- Signed terms and notices match the deployed architecture/provider settings and the promised release limits/support model.

#### Task: Add AI limitations, human-review obligations, prohibited/high-risk uses and provider training/retention terms
Priority: P0
Estimate: 8h
Source: Release backlog LEGAL-001, task 4. Add AI limitations, human-review obligations, prohibited/high-risk uses and provider training/retention terms.
Implement this bounded change under “Complete customer legal, privacy and AI terms”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add AI limitations, human-review obligations, prohibited/high-risk uses and provider training/retention terms
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Signed terms and notices match the deployed architecture/provider settings and the promised release limits/support model.

#### Task: Align support/SLA/RPO/RTO/offboarding wording to measured operations and never overclaim legal privilege/chain of custody
Priority: P0
Estimate: 8h
Source: Release backlog LEGAL-001, task 5. Align support/SLA/RPO/RTO/offboarding wording to measured operations and never overclaim legal privilege/chain of custody.
Implement this bounded change under “Complete customer legal, privacy and AI terms”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before external data so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Align support/SLA/RPO/RTO/offboarding wording to measured operations and never overclaim legal privilege/chain of custody
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- Signed terms and notices match the deployed architecture/provider settings and the promised release limits/support model.

### Story: Deliver first-run onboarding, demo data and support channels
Priority: P1
Source: Release backlog ONB-001 (repository and product audit, 16 July 2026). Make the first customer session safe and intentional.
Release gate: Before independent pilot. This story is required for the initial release because leaving the gap open would make the named workflow unsafe, incomplete, misleading or unavailable.

Acceptance criteria:
- A pilot user completes onboarding and the first investigation with synthetic data, knows support/security contacts and agrees measured success criteria.
- Every child item has implementation or decision evidence attached to this story, and unresolved failures remain open release blockers.

#### Task: Create a synthetic representative demo case with known expected graph/timeline/map/financial/Cellebrite/AI outputs
Priority: P1
Estimate: 8h
Source: Release backlog ONB-001, task 1. Create a synthetic representative demo case with known expected graph/timeline/map/financial/Cellebrite/AI outputs.
Implement this bounded change under “Deliver first-run onboarding, demo data and support channels”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Create a synthetic representative demo case with known expected graph/timeline/map/financial/Cellebrite/AI outputs
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A pilot user completes onboarding and the first investigation with synthetic data, knows support/security contacts and agrees measured success criteria.

#### Task: Add a first-login checklist covering MFA, profile, first case, collaborator, upload, citations and support
Priority: P1
Estimate: 8h
Source: Release backlog ONB-001, task 2. Add a first-login checklist covering MFA, profile, first case, collaborator, upload, citations and support.
Implement this bounded change under “Deliver first-run onboarding, demo data and support channels”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Add a first-login checklist covering MFA, profile, first case, collaborator, upload, citations and support
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A pilot user completes onboarding and the first investigation with synthetic data, knows support/security contacts and agrees measured success criteria.

#### Task: Establish support@ and security@ channels with SPF, DKIM, DMARC, ownership and escalation
Priority: P1
Estimate: 8h
Source: Release backlog ONB-001, task 3. Establish support@ and security@ channels with SPF, DKIM, DMARC, ownership and escalation.
Implement this bounded change under “Deliver first-run onboarding, demo data and support channels”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Establish support@ and security@ channels with SPF, DKIM, DMARC, ownership and escalation
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A pilot user completes onboarding and the first investigation with synthetic data, knows support/security contacts and agrees measured success criteria.

#### Task: Define pilot price/duration/users/cases/storage/AI allowance/support/success measures and feedback cadence
Priority: P1
Estimate: 8h
Source: Release backlog ONB-001, task 4. Define pilot price/duration/users/cases/storage/AI allowance/support/success measures and feedback cadence.
Implement this bounded change under “Deliver first-run onboarding, demo data and support channels”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- A versioned decision or specification records the outcome of: Define pilot price/duration/users/cases/storage/AI allowance/support/success measures and feedback cadence
- Every implementation consequence is linked to an owned ticket or explicitly excluded with rationale and approval.
- A pilot user completes onboarding and the first investigation with synthetic data, knows support/security contacts and agrees measured success criteria.

#### Task: Separate pilot bugs from feature requests and require a formal pilot review before customer two
Priority: P1
Estimate: 6h
Source: Release backlog ONB-001, task 5. Separate pilot bugs from feature requests and require a formal pilot review before customer two.
Implement this bounded change under “Deliver first-run onboarding, demo data and support channels”, preserving the case-permission, provenance, failure-state and regression expectations defined by the parent story. It must be complete before independent pilot so the release is not accepted on an unverified assumption.

Acceptance criteria:
- The release candidate exposes the specified UI, API or data outcome on the story fixture: Separate pilot bugs from feature requests and require a formal pilot review before customer two
- Automated coverage exercises the successful path and the relevant permission, failure, empty or concurrency boundary.
- A pilot user completes onboarding and the first investigation with synthetic data, knows support/security contacts and agrees measured success criteria.

### Story: v2 passes behavioral QA on the production corpus
Load the production corpus into v2 and re-run the 45-item yardstick as live QA — impossible today because v2 is empty (gap assessment Phase 4, BRG-047). Fed by the UFED re-ingest and transaction-migration tickets.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-047, gap assessment §7). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Production corpus loaded; the 45-item yardstick re-run as behavioral QA with results documented
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Load the production corpus into v2
Priority: P3
Estimate: 8h
Run the production data load through the now-complete ingest and migration paths, with reconciliation.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-047, gap assessment §7). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- All production cases present on v2 with reconciled counts
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

#### Task: Re-run the 45-item yardstick as behavioral QA
Priority: P3
Estimate: 16h
Work through the corrected per-feature verdict list (gap assessment §7) as live behavioral QA on real data, filing tickets for failures.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-047, gap assessment §7). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Each of the 45 items has a documented pass/fail on v2 with real data
- Every fail has a filed ticket

### Task: Alpha feedback channel on v2
Priority: P1
Estimate: 8h
v1's `/api/testing/*` QA hub (tester checklist + feedback capture, the TESTING_FEEDBACK_STATE workflow) is the live channel for tester feedback and exists only on v1 (gap assessment §3.6, BRG-045 + BRG-050). If alpha testing moves to v2, this must move with it or be replaced — decide, then implement. P1 because alpha cannot start without a feedback channel.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-045, BRG-050, gap assessment §3.6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded (port the QA hub vs replace it)
- Testers can file feedback against v2 from day one of alpha

### Task: Command palette — finish or remove
Priority: P3
Estimate: 4h
Cmd-K is scaffolding-only in both trees and does nothing (gap assessment §7 item 5, BRG-051 DECIDE). Ship a minimal working palette or delete the dead state — decide with Neil, then execute.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-051, gap assessment §7). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Decision recorded; either Cmd-K performs useful navigation or the dead code and binding are removed
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Task: Restore note→profile linking
Priority: P3
Estimate: 4h
Gap assessment §3.6 (yardstick item 37): the note→profile linking endpoints are gone in v2. Not covered by any roadmap ticket or conscious drop — added so the gap is closed or consciously dropped. Restore the endpoints and the linking UI affordance.
Source: V2 Alpha Bridging Plan (13 July 2026; Gap assessment §3.6). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- A note can be linked to a case profile and the link is visible from both sides
- A regression test or recorded fixture result demonstrates the stated outcome on the release candidate.

### Task: v1 cutover & decommission plan
Priority: P1
Estimate: 10h
Cutover date, read-only grace period, data archival, DNS/port switch (gap assessment Phase 4, BRG-052). Until this executes, v1 runs in production with unauthenticated write-Cypher and `/api/timeline` — the pace of the whole roadmap is a security decision.
Source: V2 Alpha Bridging Plan (13 July 2026; BRG-052). This item is required for the initial release because unresolved V1→V2 parity would leave the named workflow broken, incomplete, misleading or unavailable.

Acceptance criteria:
- Written plan covering cutover date, read-only grace period, archival, and DNS/port switch, agreed with Neil
- v1 decommission checklist exists with owners per step
