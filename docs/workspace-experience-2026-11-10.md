# Workspace and dossiers experience

Status: implemented and locally verified; commit and push authorized by the user on 10 November 2026. This supersedes the older overview layout decisions in `workspace-redesign.md`; the underlying casework, provenance and permission model remains in force. Production acceptance is recorded separately below.

## Accepted direction

The workspace is where investigators consolidate their work as a case develops. The case picker established the visual reference: restrained typography, generous space, useful identity cues and small, purposeful sections. A description is optional.

- Overview is a compact case home. Identify the case, show personal work, a short casework preview, next deadlines, important dossiers and pinned sources. Keep detailed change briefs available on demand. Remove snapshots, browsing-history suggestions and the duplicated file catalogue.
- Casework opens as one collection. Notes, findings and theories remain meaningful types, with filters rather than a second navigation layer. Preserve authoring, provenance, revisions, permissions and source links.
- Tasks and deadlines share an explicit destination. Both can be completed and reopened. Completion persists, failed saves remain recoverable and completed deadlines stop appearing as upcoming or overdue.
- Dossiers collect material around a subject. Show linked casework in both directions without duplicate writes or ambiguous unlink behaviour. Keep original evidence, original interviews and investigator-authored analysis distinct.
- Case setup has its own destination. Preserve existing context and objectives, unsaved edits and versioned mandate changes.

## Required acceptance journeys

| Journey | Evidence required | State |
| --- | --- | --- |
| Open a case, recognise it, reach casework/dossiers/work and return | Full app Chromium journey at 1440px and 390px; light and dark visual inspection | Passed locally |
| Read a concise overview with realistic populated/empty/error data | Bounded previews, true totals, assigned reviews, explicit retries and source return | Passed locally |
| Browse all casework, filter by type, open/edit/create and reopen | Unit and Chromium tests, deep links, error recovery, refresh during editing | Passed locally |
| Attach existing work to a dossier and return to it | Browser attach/retry/remove flow, preserved original entry | Passed locally |
| Navigate links from either dossier or casework | Case-scoped backend membership tests, browser overlays and real local API journey | Passed locally |
| Complete and reopen deadlines and tasks | Real PostgreSQL persistence, reload/reopen, task independence, overview/case-picker invalidation | Passed locally |
| Work with dates, subtasks, filters, linked context and direct item links | Viewer restrictions, search across parent tasks, completed-parent exclusion, independent relationship choices | Passed locally |
| Edit context/objective without losing drafts | Save/reopen, cancel/confirm, browser Back/Forward, shortcuts, nested source navigation and failed-save retry | Passed locally |
| Compile and build release assets | TypeScript, full ESLint, Vite production build and focused regression suites | Passed locally |

## Data and deployment

- `20261110_deadline_completion` adds a nullable completion timestamp. Existing deadlines remain open. No source evidence or investigation records are removed.
- Local verification uses synthetic fixtures. Screenshots and runtime harnesses remain untracked and are not publication artifacts.
- Existing unrelated financial implementation edits remain outside this work.
- The user subsequently requested commit and push. Push is the existing automatic deployment trigger; no separate manual deployment or worker restart is required.
- Deployment safeguards are unchanged. The deployment script checks ingestion before migrations and service replacement, fails closed when state cannot be established, and supports isolated release trees and guarded handover. The new migration is classified as additive. Live host configuration was not inspected or changed.
- Production revision and production browser acceptance are not verified in this record. The separately recorded live-origin access denial remains in force; successful local checks and a push must not be described as live verification.

## Verification record

- Local development PostgreSQL migration advanced successfully to `20261110_deadline_completion`.
- Backend regression suite: 64 passed across deadline completion, work service, workspace attention, dossier relationships/services and workspace authorization.
- Frontend regression suite: 172 passed across 43 files covering workspace, dossiers, cases, assigned reviews, search, source navigation and keyboard shortcuts.
- Final review found and fixed membership pagination after removing the last dossier on a later page. The four focused source-navigation/pagination tests passed after that change; reopening is no longer required to see the remaining dossiers.
- Combined Chromium suite: 71 passed across 8 files covering workspace setup, task/deadline journeys, casework authoring/detail, dossiers and native/fallback browser history guards.
- Production build passed, including TypeScript and full frontend ESLint. Existing bundle-size/dependency annotations and non-failing test-environment warnings remain.
- Full-shell synthetic browser journey passed overview, all-casework navigation, browser Back, task/deadline destination, setup draft protection, dossier directory and 390px overflow checks in light/dark themes.
- A separate Chromium journey used the real local API and PostgreSQL with an isolated synthetic user/case: persisted deadline completion and reopening, independent linked tasks, overview/case-picker refresh, searchable parent candidates and completed-parent exclusion, task completion/reopening, reverse dossier references, dossier-to-entry navigation and return, case-summary save/reopen, and cancelled Back/keyboard navigation preserving drafts all passed. No API responses were mocked in that journey.
- Source navigation now opens linked tasks, deadlines and timeline events at their exact destinations. Individual saved agent artifacts still have no dedicated viewer in the application; this pre-existing limitation is outside the workspace/dossier changes.
