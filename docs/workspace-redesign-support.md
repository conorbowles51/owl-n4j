# Workspace support guide

## First triage

Record the case identifier, affected user, their case role, route, object type and identifier, approximate time, and whether the issue is read, write, migration, citation, or performance related. Do not ask users to recreate content in a second legacy surface; there is only one supported Workspace after cutover.

## Common questions

### Where did Profiles or Witnesses go?

They are Dossiers. Old case Profile links redirect to the Dossier view. A Dossier is investigator-curated context around a subject; its optional graph link points to evidence-derived identity but does not duplicate or overwrite graph facts.

### Where is the Workspace Timeline?

It was removed because it reconstructed unlike records and was not a reliable audit trail. The evidence Timeline viewer still exists. Entry revision and event history remains available for authored casework; it is not presented as a case-wide audit trail.

### Why can I see an item but not edit it?

Viewers have case-read permission only. Owners and editors can mutate supported Workspace objects. Verify the user's current case membership rather than their display name.

### Why can an AI result not be accepted?

Factual summary and comparison claims require resolvable citations from the saved source set. Verify that the linked evidence still exists in the same case and that the citation anchor resolves. Rejection is safe and leaves casework unchanged.

### Why is a Dossier unlinked or marked for review?

Migration never guesses between graph identities. An unlinked Dossier remains usable and preserves all authored material. A permitted investigator can link the correct canonical graph entity after reviewing the candidates.

### Where are all case documents?

Evidence remains the source repository. Workspace shows curated links and Pinned Evidence; it intentionally does not reproduce the exhaustive Evidence list.

## Data-integrity investigation

For one case, run:

```powershell
python backend/scripts/workspace_phase8_reconciliation.py --case-id CASE_UUID --review-template output/workspace-redesign/support-review-template.json --output output/workspace-redesign/support-reconciliation.json
```

- An unexpected difference is an engineering incident, not a user-review decision.
- A review item must be investigated and accepted only with a written reason.
- Never delete an unresolved row to make the count pass.
- Preserve legacy mapping identifiers when repairing historical links.
- Use the canonical services for repairs so revisions, events, permissions, and cross-case validation are retained.

## Escalation information

Attach the scoped reconciliation report, relevant request/response status, server logs around the event, and the release version. Redact evidence content and credentials. Escalate immediately for any cross-case result, missing canonical parent, unexplained source-count difference, missing Entry history, or accepted AI output with an unresolvable citation.

For rollback and migration operations, follow `docs/workspace-redesign-operations.md`; do not restore an old database over newer canonical writes.
