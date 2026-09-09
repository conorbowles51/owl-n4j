# Workspace migration inventory

> Status: Phase 8 application cutover record. Canonical consumers and writes are live; legacy business tables remain only as retained migration sources pending a separately approved contract migration.

## Reader and intended action

This document is for the engineer migrating or retiring an existing Workspace subsystem. After reading it, they should be able to identify every known consumer of a legacy store, choose the correct canonical replacement, and verify that a compatibility path can be removed without losing case data or breaking a dependent workflow.

The product model and phase acceptance criteria remain defined by the Workspace redesign plan. This inventory owns implementation routing and retirement evidence only.

## Migration invariants

- Canonical services become the sole write target before any legacy endpoint is removed.
- Compatibility endpoints translate to canonical services. They do not dual-write independent stores.
- Every legacy identifier remains traceable through an explicit source and identifier mapping.
- Ambiguous references become recoverable migration warnings. They are never guessed or discarded.
- Original timestamps, authorship, soft-deletion state, archive state, and relationship metadata are preserved where available.
- A legacy store remains readable until every consumer below has switched and reconciliation is complete.
- Contract migrations are separate from expand, backfill, and switch migrations.

## Store ownership and replacement paths

| Legacy store or subsystem | Known readers and cross-consumers | Current writers | Canonical owner and phase | Compatibility and retirement gate |
| --- | --- | --- | --- | --- |
| Workspace context | Canonical Workspace overview, Chat, and Agent mandate consumers | Canonical Case Context and Mandate routes only | Typed Case Context, investigation templates, and versioned Mandate | Cut over. Legacy JSON remains a read-only reconciliation source until the contract migration. |
| Workspace notes | Canonical Notebook and Casework surfaces; Dossier links | Canonical Workspace Entry service only | Workspace Entries with type Note | Cut over. Stable mappings remain for support and retained source accounting. |
| Workspace findings | Canonical Casework, overview, attention, and Dossier surfaces | Canonical Workspace Entry service only | Workspace Entries with type Finding | Cut over. Significance and relationship migration are reconciled per case. |
| Workspace theories | Canonical Casework, Dossier, and cited AI surfaces | Canonical Workspace Entry service only | Workspace Entries with type Theory and Entry Links | Cut over. The obsolete legacy evidence-relevance and graph-building routes are removed. |
| Notebook notes and links | Persistent unified Notebook and evidence Timeline integration | Canonical Workspace Entry service through the Notebook API | Workspace Entries and Entry Links | Cut over. Notebook compatibility remains a user-facing integration, not a second casework store. |
| Workspace witnesses | Dossier list/detail, assessments, interviews, and AI review | Canonical Dossier service only | Dossiers, Assessments, Interviews, and Dossier Links | Cut over. Every retained Witness is mapped or surfaced as an explicit reconciliation review item. |
| Case Profiles and profile link tables | Dossier route and compatibility redirect from old Profiles URLs | Canonical Dossier service; evidence actions use Dossier links | Dossiers and Dossier Links | Cut over. The database model keeps its historical table name until the separately approved contract migration. |
| Workspace tasks | Work view, overview, and attention service | Canonical Task service only | Normalised Tasks and Task Links | Cut over. Member assignment, subtask, deadline, and cross-case rules are enforced canonically. |
| Workspace deadline configuration | Retained migration source only | Canonical Case Deadline routes only | Case Deadlines | Cut over. Legacy configuration is reconciled and no longer has an application writer. |
| Workspace pinned items | Retained migration source only | Shared Evidence Pin service only | Shared, evidence-only case pins | Cut over. Evidence and Cellebrite actions use the bounded canonical pin API. |
| Reconstructed Workspace timeline | None | None | No replacement in this redesign | Removed. The evidence Timeline remains a separate viewer and is unchanged. |

## Cross-cutting consumers that must be characterised

### Profile and Dossier relationships

Case Profiles currently resolve legacy Workspace note and finding identifiers into contextual records. Phase 1 must provide a stable entry mapping before Phase 3 migrates those profile relationships. Dossier migration must consume the mapping rather than copying legacy identifiers into a second compatibility layer.

### Evidence relevance from theories

The existing evidence relevance operation collects evidence and document identifiers from a legacy Theory. Before legacy Theory reads are removed, the operation must read canonical Entry Links, normalise both legacy attachment names to evidence, and retain the source Theory identifier through the migration map.

### Notebook use by the evidence Timeline

The evidence Timeline may include Notebook notes while creating or exporting a saved view. This is a legitimate cross-area consumer and must switch to canonical Note entries. Removing the Workspace Timeline does not remove this evidence-Timeline integration.

### Evidence and Cellebrite actions

Evidence and Cellebrite currently create profile relationships and pins directly through legacy API families. These actions must move to Dossier and shared-pin services respectively. Bulk interactions remain supported and must not load the full evidence collection to hydrate selected records.

### Workspace graph-building actions

Legacy Witness, Note, and Theory records can seed graph-building requests. Theory entry links and Dossier graph identity replace those inputs. A Note link must never silently create a Dossier.

## Rollout control

Phase 8 removed the temporary environment flag and case allow-list. `WorkspacePage` now has one implementation for every case, and no production frontend code imports the legacy Workspace components or API clients. A rollback must deploy the last canonical-compatible application release; it must not re-enable the retired legacy UI against new canonical writes.

## Preflight operation

Run the deterministic preflight from the backend environment:

```powershell
python -m scripts.workspace_preflight
```

Use `--case-id` to scope a rehearsal and `--output` to retain machine-readable JSON. The command is read-only with respect to the database and reports:

- Counts by legacy table and case.
- Missing or malformed external identifiers.
- Orphaned profile, Notebook, and Theory evidence links that can be checked relationally.
- Duplicate pins for the same case and source item.
- Multiple Case Profiles claiming the same graph entity.
- Conflicting dates across Case Deadlines, Workspace context, and legacy deadline configuration.

Two runs against unchanged data must produce byte-identical JSON. The report intentionally omits a generation timestamp so it can be used as deterministic reconciliation evidence.

## Retirement checklist

A legacy subsystem can be removed only when all of the following are evidenced:

1. The canonical backfill is idempotent and accounts for every source record.
2. Every consumer in this inventory reads the canonical service or an explicit compatibility adapter.
3. Legacy mutation routes translate to the canonical service and no active caller writes the old store.
4. Viewer and editor permissions, cross-case isolation, and failure paths pass at service and route boundaries.
5. Shadow-read comparison reports no unexpected difference.
6. Every unresolved reference remains recoverable and has an accepted review disposition.
7. Rollback has been rehearsed without deleting canonical writes.
8. A restorable backup and the required retention and product sign-off gates exist before any table is dropped.

## Phase 8 cutover evidence

- `phase8-backfill-idempotence.json` proves the final canonical backfills converge on a second pass.
- `phase8-reconciliation.json` accounts for all 18 retained cases after verification-fixture cleanup, with zero unexpected differences, zero review items, and zero unknown acceptances.
- `phase8-backup-restore.json` proves a production-shaped PostgreSQL custom backup restores into isolation, matches source counts, reaches the single migration head, boots the API, and reconciles cleanly.
- `test_workspace_cutover_contract.py` requires canonical routes and rejects the retired Note, Finding, Theory, Witness, Case Profiles, evidence entity-link, Workspace Timeline, presence, and graph-building route families.
- Cellebrite evidence-to-subject actions use canonical Dossier evidence routes and `DossierLink`; historical evidence/Profile arrays are copied idempotently and remain readable only by the cutover backfill and reconciliation gate.
- Legacy migration readers remain intentionally in preflight, backfill, and reconciliation services. They are not live business-service consumers or writers.
- No legacy table was dropped. Contract deletion still requires the agreed retention period, a real environment backup, and explicit product and engineering sign-off.
