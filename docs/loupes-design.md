# Loupes — design

A **Loupe** is a bonded collection: a first-class container with its own identity,
description and significance, binding documents, highlighted passages, entities, events,
transactions, calls and locations to explain an event, a sequence or a thing. Every member
carries the quote, page and file it came from. The same Loupe is viewable through any lens
— timeline, graph, map, table, ledger — because it is a membership set, not a view.

Loupes move into the case, and the case is built out of them.

## What the platform already has

Three existing patterns decide the shape, and the design follows all three rather than
inventing alongside them.

**`SignificantEntity`** is a durable case-level reference to a Neo4j entity by
`entity_key`, holding `added_by_user_id`, `addition_source`, a `context` document and a
soft-delete. Descriptive data deliberately stays in Neo4j so edits to the canonical entity
reflect in every projection immediately. **Loupe members follow this pattern exactly** —
a Postgres curation manifest over canonical data held elsewhere.

**`TimelineView`** is a curated chronology defined by a `filter_snapshot` — a saved filter,
not a set of members. A Loupe is the membership counterpart: the chronology whose contents
were chosen one at a time. A timeline view can be *backed by* a Loupe instead of a filter.

**`WorkspaceTheory`** is an untyped bonded collection already: `hypothesis`, `type`,
`confidence_score`, `privilege_level`, `counter_arguments`, `supporting_evidence`, and six
parallel lists of `attached_*_ids` in an opaque JSON document. It is the right idea without
types, provenance, nesting or relationships. **Loupes supersede it.**

## Model

### Loupe

`case_id`, `owner_user_id`, `title`, `description`, `significance`, `kind`, `confidence`,
`visibility`, `filter_snapshot` (nullable — a hybrid Loupe seeded from a filter), soft
delete, timestamps.

`kind` distinguishes what the collection is for — `finding`, `theory`, `sequence`,
`chronology`, `subject` — without changing the mechanics. A theory is a Loupe whose
significance is a hypothesis.

### LoupeMember

The polymorphic reference, following `SignificantEntity`:

`loupe_id`, `member_type`, `member_ref`, `position`, `note`, `context`,
`added_by_user_id`, `addition_source`, `removed_at`.

`member_type` ∈ `entity · event · claim · document · passage · transaction · call ·
location · loupe`. `member_ref` is the Neo4j key, the `evidence_claims` id, or a Loupe id.

Two consequences worth stating. **`member_type='loupe'` is how Loupes nest** — significant
items compose into significant structures, and the structure is a DAG rather than a tree, so
one Loupe can be a member of several. A cycle check runs on insert. And **`note` is the
within-Loupe narrative at member granularity**: why *this* passage belongs, alongside the
Loupe's own `significance` explaining why the members belong together.

Claims are the natural unit for anything derived from a document, because provenance already
lives on `evidence_claims` — 23,762 of them — and a member that points at a claim inherits
its quote, page and file without copying them.

### LoupeLink

Typed relationships between Loupes: `from_loupe_id`, `to_loupe_id`, `relation`, `rationale`,
`created_by_user_id`.

`relation` ∈ `supports · contradicts · refines · precedes · duplicates · depends_on`.

This is what makes the case a structure of connected findings rather than a folder of them,
and it is what the disconfirmation agent writes into when it finds material that breaks a
theory: a `contradicts` link with a rationale, pointing at the evidence.

### Revisions

A Loupe is a work product that may end up in front of a court, so membership changes are
recorded. `removed_at` on members preserves what was once in and is no longer, and the
`loupe_revisions` table records who changed what and when. Nothing is hard-deleted.

## Creation surfaces

One core, five adapters. Each adapter's only job is turning a selection into typed member
references; everything downstream is shared.

| Surface | Selection becomes |
|---|---|
| **Timeline** | Selected events → `event` members, ordered by time, `position` preserved |
| **Graph** | Selected nodes and their connecting edges → `entity` members plus the events on the paths between them |
| **Workspace** | An existing theory's attachments → typed members; the hypothesis becomes `significance` |
| **Agent** | A plain-language scenario → the agent assembles candidate members and proposes the Loupe; the investigator disposes |
| **Cellebrite** | Selected messages, calls, contacts or locations → `call`, `event`, `entity` and `location` members with the device as context |

The agent surface is the one that changes the unit of work from a query to a hypothesis, and
it is bounded: the agent proposes a Loupe and its members with reasons; nothing is bound
without a human accepting it.

## Superseding theories and findings

`workspace_theories` holds 4 rows and `workspace_findings` holds 0, so this is a data
transform rather than a migration project.

Each theory becomes a Loupe with `kind='theory'`: `hypothesis` → `significance`,
`confidence_score` → `confidence`, `privilege_level` → `visibility`, and each
`attached_*_ids` list → typed members. `counter_arguments` become `contradicts` links to
Loupes created from the counter-argument text, which is the honest translation — a counter
argument is a finding that opposes this one.

The workspace keeps witnesses and tasks. It loses theories and findings to Loupes.
