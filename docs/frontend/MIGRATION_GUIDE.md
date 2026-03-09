# Frontend v1 → v2 Migration Guide

## Feature Parity Audit

| Feature | v1 (frontend/) | v2 (frontend_v2/) | Status |
|---------|----------------|-------------------|--------|
| Login / Auth | LoginView.jsx | features/auth/components/LoginPage.tsx | ✅ Ported |
| Dashboard | CaseManagementView.jsx | features/cases/components/DashboardPage.tsx | ✅ Ported |
| Case List | CaseManagementView.jsx | features/cases/components/CaseListPage.tsx | ✅ Ported |
| Case Settings | CaseManagementView.jsx | features/cases/components/CaseSettingsPage.tsx | ✅ Ported |
| Evidence Upload | EvidenceProcessingView.jsx | features/evidence/components/EvidencePage.tsx | ✅ Ported |
| Evidence Details | FileInfoViewer.jsx | features/evidence/components/EvidenceDetailSheet.tsx | ✅ Ported |
| Folder Profiles | FolderProfileModal.jsx | features/evidence/components/FolderProfileDialog.tsx | ✅ Ported |
| Graph View | GraphView.jsx | features/graph/components/GraphPage.tsx | ✅ Ported |
| Node Details | NodeDetails.jsx | features/graph/components/NodeDetailSheet.tsx | ✅ Ported |
| Add/Edit Nodes | AddNodeModal.jsx, EditNodeModal.jsx | features/graph/components/AddNodeDialog.tsx, EditNodeDialog.tsx | ✅ Ported |
| Relationships | CreateRelationshipModal.jsx | features/graph/components/CreateRelationshipDialog.tsx | ✅ Ported |
| Merge Entities | MergeEntitiesModal.jsx | features/graph/components/MergeEntitiesDialog.tsx | ✅ Ported |
| Cypher Queries | DatabaseModal.jsx | features/graph/components/CypherPanel.tsx | ✅ Ported |
| Timeline View | TimelineView.jsx + 7 sub-components | features/timeline/components/ (6 files) | ✅ Ported |
| Map View | MapView.jsx + 6 sub-components | features/map/components/ (8 files) | ✅ Ported |
| Table View | GraphTableView.jsx | features/table/components/TablePage.tsx | ✅ Ported |
| Financial View | FinancialView.jsx + 8 sub-components | features/financial/components/ (8 files) | ✅ Ported |
| Chat / AI | ChatPanel.jsx | features/chat/components/ChatPage.tsx | ✅ Ported |
| Workspace | 35 workspace components | features/workspace/components/ (10 files) | ✅ Ported |
| Reports | Report components | features/reports/components/ (3 files) | ✅ Ported |
| Admin Dashboard | CaseManagementView.jsx (partial) | features/admin/components/AdminDashboardPage.tsx | ✅ Ported |
| User Management | CreateUserModal.jsx | features/admin/components/UserManagementPage.tsx | ✅ Ported |
| Profile Management | ProfileEditor.jsx | features/admin/components/ProfileManagementPage.tsx | ✅ Ported |
| System Logs | SystemLogsPanel.jsx | features/admin/components/SystemLogsPage.tsx | ✅ Ported |
| Background Tasks | BackgroundTasksPanel.jsx | features/admin/components/BackgroundTasksPage.tsx | ✅ Ported |
| Usage / Costs | CostLedgerPanel.jsx | features/admin/components/UsagePage.tsx | ✅ Ported |
| Setup Wizard | First-time setup | features/admin/components/SetupWizard.tsx | ✅ Ported |
| Settings | Theme toggle in sidebar | features/settings/components/SettingsPage.tsx | ✅ Ported |
| Snapshots | SnapshotList.jsx, SnapshotsSection.jsx | features/cases/components/SnapshotManager.tsx | ✅ Ported |
| Command Palette | N/A (new) | components/ui/command-palette.tsx | ✅ New |
| Keyboard Shortcuts | Minimal | hooks/use-global-shortcuts.ts | ✅ Enhanced |

## Data Migration — localStorage Keys

| v1 Key | v2 Key | Notes |
|--------|--------|-------|
| `authToken` | `authToken` | Same key, no migration needed |
| `theme` | `theme` | Same key, compatible values (dark/light/system) |

Both versions use the same `authToken` localStorage key for JWT storage. No data migration script is needed.

## API Compatibility

v2 uses the **exact same backend API** — no API changes required.

| Aspect | Details |
|--------|---------|
| Base URL | Same (`/api/...`) — proxied via Vite dev server |
| Auth | Same JWT Bearer token in `Authorization` header |
| Case ID injection | Same pattern — passed per-request |
| Error handling | Same HTTP status codes and `{ detail }` error shape |
| Streaming (chat) | Same SSE endpoint |

The `fetchAPI<T>()` wrapper in v2 (`lib/api-client.ts`) is a TypeScript port of v1's `fetchAPI()` from `services/api.js` with identical behavior.

## URL Structure Changes

| v1 (state-based) | v2 (URL-based) | Notes |
|-------------------|----------------|-------|
| `/#` (hash routing) | `/` | v2 uses browser history routing |
| State: `appView="cases"` | `/cases` | URL-driven |
| State: `appView="graph"` | `/cases/:id/graph` | Case-scoped URL |
| State: `appView="timeline"` | `/cases/:id/timeline` | Case-scoped URL |
| State: `appView="map"` | `/cases/:id/map` | Case-scoped URL |
| State: `appView="table"` | `/cases/:id/table` | Case-scoped URL |
| State: `appView="financial"` | `/cases/:id/financial` | Case-scoped URL |
| State: `appView="evidence"` | `/cases/:id/evidence` | Case-scoped URL |
| State: `appView="chat"` | `/cases/:id/chat` | Case-scoped URL |
| State: `appView="workspace"` | `/cases/:id/workspace` | Case-scoped URL |
| State: `appView="reports"` | `/cases/:id/reports` | Case-scoped URL |
| State: `appView="admin"` | `/admin` | Dedicated admin routes |
| N/A | `/admin/users` | New dedicated page |
| N/A | `/admin/profiles` | New dedicated page |
| N/A | `/admin/logs` | New dedicated page |
| N/A | `/admin/tasks` | New dedicated page |
| N/A | `/admin/usage` | New dedicated page |
| N/A | `/settings` | New dedicated page |
| N/A | `/login` | Dedicated login route |

v1 had no URL routing (all state-driven), so there are no URLs to redirect. Users will simply use the new URL structure.
