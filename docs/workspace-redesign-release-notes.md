# Workspace redesign release notes

The Workspace is now the place where investigators organise and advance a case. Opening a case lands on a concise Overview, with dedicated Casework and Work views and Dossiers directly beneath Workspace in navigation.

## What changed

- Notes, Findings, and Theories now share one authoring, search, revision, and attachment system. Findings retain significance; Theories retain confidence and lifecycle; all three use consistent links and source anchors.
- Dossiers replace the former Profiles and Witness workspace. A Dossier can represent a person, organisation, asset, location, event, or other subject while remaining distinct from evidence-derived graph identity. It can curate roles, media, assessments, interviews, tasks, evidence, and casework.
- Cellebrite file and bulk actions add evidence directly to Dossiers through the same canonical relationship model used everywhere else.
- Tasks use real case members, one-level subtasks, canonical Deadlines, and links to relevant case objects.
- Pinned Evidence is shared across the case and remains a curated set rather than another full document list.
- Case Context uses a small general-investigation core plus optional typed templates. Mandates are versioned and shared with Chat, Agent, and Workspace AI.
- The Overview separates what matters to the case from work relevant to the signed-in investigator.
- Workspace AI outputs are durable, cited, and reviewable. They cannot alter investigator-authored casework without explicit acceptance.
- The obsolete Workspace Timeline, duplicate document lists, duplicate notes/findings summaries, and legacy Witness/Profile surfaces have been removed. The evidence Timeline remains available as a separate viewer.

## Compatibility

- Old case Profile URLs redirect to Dossiers.
- Existing Workspace content, links, witnesses, profiles, tasks, deadlines, and pins are migrated with stable source mappings.
- The temporary Workspace rollout flags were removed; all cases use the canonical Workspace.
- Legacy database tables are retained during the agreed safety period but have no application writers. Their later removal requires a separate approved migration.

## Permissions

Case viewers can read Workspace content but cannot mutate it. Case editors and owners can create and update the supported casework. AI suggestions remain visibly separate from accepted investigator work.
