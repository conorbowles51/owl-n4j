# Frontend v2 Rewrite — Phased Roadmap

**Project:** Owl Investigation Console — `frontend_v2/`
**Status:** Complete — All phases (0–10) implemented
**Created:** 2026-03-08
**Depends On:** [Brand Kit](brand-kit-v2.html) · [Design System](frontend-design-system.md)

---

## Why Rewrite?

The current frontend (36,800+ lines of JavaScript) has reached an architectural ceiling:

- **App.jsx is 5,515 lines** with 87 `useState` hooks — a monolithic god component that owns all routing, state, modals, and view logic
- **Zero TypeScript** — no type safety across 134 components
- **No router** — views switch via manual state flags (`appView`, `viewMode`)
- **No global state management** — everything prop-drills through App.jsx
- **Two parallel graph state systems** (App.jsx vs WorkspaceView) that can desync
- **44+ modals** managed by individual boolean flags in parent components
- **api.js is 2,230 lines** — a single file for all backend communication
- **No code splitting or lazy loading** despite heavy dependencies (Leaflet, force-graph, recharts)
- **No tests, no Storybook, no component documentation**

A rewrite lets us adopt the Owl design system properly, move to TypeScript, decompose into features, and build a foundation that scales.

---

## Architecture Target

```
frontend_v2/
├── public/
├── src/
│   ├── app/                          # App shell, providers, root layout
│   │   ├── App.tsx
│   │   ├── providers.tsx             # Compose all providers
│   │   ├── routes.tsx                # React Router config
│   │   └── layouts/
│   │       ├── AppLayout.tsx         # Sidebar + main area shell
│   │       ├── CaseLayout.tsx        # Case-scoped layout (tabs, header)
│   │       └── AdminLayout.tsx       # Admin area layout
│   ├── components/
│   │   └── ui/                       # @owl/ui — brand layer over shadcn
│   │       ├── button.tsx
│   │       ├── badge.tsx
│   │       ├── card.tsx
│   │       ├── input.tsx
│   │       ├── dialog.tsx
│   │       ├── data-table.tsx
│   │       ├── sidebar.tsx
│   │       ├── node-badge.tsx
│   │       ├── status-indicator.tsx
│   │       ├── entity-card.tsx
│   │       ├── command-palette.tsx
│   │       ├── page-header.tsx
│   │       ├── empty-state.tsx
│   │       ├── confidence-bar.tsx
│   │       ├── cost-badge.tsx
│   │       └── ...
│   ├── features/                     # Feature-based modules
│   │   ├── auth/
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── api.ts
│   │   │   └── auth.types.ts
│   │   ├── cases/
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── api.ts
│   │   │   └── cases.types.ts
│   │   ├── evidence/
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── api.ts
│   │   │   └── evidence.types.ts
│   │   ├── graph/
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── api.ts
│   │   │   ├── store.ts              # Zustand slice for graph state
│   │   │   └── graph.types.ts
│   │   ├── timeline/
│   │   ├── map/
│   │   ├── financial/
│   │   ├── chat/
│   │   ├── workspace/
│   │   ├── reports/
│   │   └── admin/
│   ├── hooks/                        # Shared hooks
│   │   ├── use-case-context.ts
│   │   ├── use-permissions.ts
│   │   ├── use-keyboard-shortcuts.ts
│   │   └── use-modal.ts
│   ├── lib/
│   │   ├── api-client.ts             # Fetch wrapper (auth, error handling)
│   │   ├── cn.ts                     # clsx + tailwind-merge
│   │   ├── theme.ts                  # Token definitions
│   │   ├── theme-provider.tsx        # Dark/light mode
│   │   └── query-client.ts           # TanStack Query config
│   ├── stores/                       # Global Zustand stores
│   │   ├── app.store.ts              # UI state (sidebar, modals)
│   │   ├── case.store.ts             # Active case context
│   │   └── graph.store.ts            # Graph data, selection, filters
│   ├── types/                        # Shared type definitions
│   │   ├── api.types.ts
│   │   ├── graph.types.ts
│   │   ├── case.types.ts
│   │   └── entity.types.ts
│   ├── styles/
│   │   └── globals.css               # CSS variables, Tailwind base
│   └── main.tsx
├── index.html
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── vite.config.ts
├── components.json                   # shadcn/ui config
└── .prettierrc
```

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | TypeScript (strict) | Type safety for 134+ components, catch bugs at compile time |
| Routing | React Router v7 | URL-based navigation replaces manual state switching |
| Server state | TanStack Query v5 | Replaces manual `useEffect` + `useState` fetch patterns |
| Client state | Zustand | Replaces 87 `useState` hooks in App.jsx |
| Components | shadcn/ui + `@owl/ui` wrapper | Brand-compliant primitives, accessible by default |
| Forms | React Hook Form + Zod | Typed form validation for 44+ modals |
| Graph viz | Cytoscape.js (evaluate) or keep react-force-graph-2d | Current lib works; Cytoscape offers more layout control |
| Styling | Tailwind CSS 4 + CSS variables | Design token system from brand kit |
| Testing | Vitest + React Testing Library | Fast, Vite-native test runner |

---

## Phase 0 — Project Scaffolding

**Goal:** Empty `frontend_v2/` project that builds, with all tooling configured.

### Tasks

- [x] Initialize Vite + React + TypeScript project in `frontend_v2/`
- [x] Configure `tsconfig.json` with strict mode and `@/` path alias
- [x] Install and configure Tailwind CSS 4 with Owl theme tokens (colors, fonts, spacing, radii, shadows from brand kit)
- [x] Set up `globals.css` with CSS custom properties (light + dark tokens from design system §4.1)
- [x] Install shadcn/ui CLI, configure `components.json`
- [x] Add first shadcn primitives: Button, Badge, Card, Input, Dialog, Sheet, Tabs, Table, Command, DropdownMenu, Tooltip, Popover, ScrollArea, Separator, Skeleton, Avatar
- [x] Install dependencies: `zustand`, `@tanstack/react-query`, `react-router-dom`, `react-hook-form`, `zod`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `framer-motion`, `sonner`
- [x] Create `lib/cn.ts` (clsx + tailwind-merge utility)
- [x] Create `lib/theme.ts` with `nodeColors`, `statusColors`, `EntityType` types
- [x] Create `lib/theme-provider.tsx` with dark mode default
- [x] Set up Prettier + ESLint (typescript-eslint, import ordering)
- [x] Set up Vitest with React Testing Library
- [x] Proxy config in `vite.config.ts` to backend API (same as current)

### Deliverable
A clean project that runs `npm run dev` and shows a blank dark page with correct Owl background color.

### Estimated Scope
~20 files, foundational config only.

---

## Phase 1 — `@owl/ui` Component Library

**Goal:** Build the branded component layer. Every component follows the design system. No feature logic — pure presentation.

### 1A — Core Primitives (wrap shadcn)

Each wraps the shadcn primitive with Owl brand tokens (variants, colors, sizes, focus rings):

- [x] `button.tsx` — primary/secondary/outline/ghost/danger/link variants (design system §3.3)
- [x] `badge.tsx` — status variants (success/danger/warning/info/amber/slate)
- [x] `card.tsx` — dark/light surface, card-header, card-content, card-footer
- [x] `input.tsx` — amber focus ring, error state
- [x] `textarea.tsx` — same focus ring treatment
- [x] `select.tsx` — branded dropdown
- [x] `dialog.tsx` — branded backdrop, slide-in animation
- [x] `sheet.tsx` — for side panels (node details, chat, evidence viewer)
- [x] `tabs.tsx` — view mode switcher style
- [x] `data-table.tsx` — dense data table with sorting, column visibility, row selection
- [x] `dropdown-menu.tsx` — context menus, action menus
- [x] `command.tsx` — command palette (Cmd+K)
- [x] `tooltip.tsx` — for truncated labels
- [x] `popover.tsx` — for filters, date pickers
- [x] `progress.tsx` — ingestion progress bars
- [x] `skeleton.tsx` — loading state placeholders
- [x] `toast.tsx` — Sonner-based notifications
- [x] `separator.tsx`
- [x] `scroll-area.tsx`
- [x] `accordion.tsx`
- [x] `checkbox.tsx`
- [x] `switch.tsx`
- [x] `slider.tsx`
- [x] `context-menu.tsx` — right-click on graph nodes
- [x] `resizable-panel.tsx` — split views (graph + details)
- [x] `avatar.tsx`

### 1B — Custom Owl Components

Domain-specific components not in shadcn:

- [x] `node-badge.tsx` — entity type badge with graph palette colors (design system §3.4)
- [x] `status-indicator.tsx` — processing status (processed/processing/queued/failed)
- [x] `entity-card.tsx` — entity display with type badge, connection count, actions
- [x] `case-card.tsx` — case list item with status, members, metadata
- [x] `page-header.tsx` — consistent page header with breadcrumbs and actions
- [x] `empty-state.tsx` — standardized empty state with icon and message
- [x] `confidence-bar.tsx` — visual confidence score indicator
- [x] `cost-badge.tsx` — LLM cost display (formatted currency)
- [x] `cypher-input.tsx` — monospaced code input for Cypher queries
- [x] `presence-indicator.tsx` — active user avatar stack
- [x] `loading-spinner.tsx` — branded loading animation

### 1C — Documentation

- [x] Set up Storybook 8 with dark mode
- [x] Write stories for every `@owl/ui` component with variant showcase
- [x] Document color rules, typography rules, spacing conventions

### Deliverable
A self-contained component library visible in Storybook. No backend calls, no routing, no feature logic.

### Estimated Scope
~40 component files, ~30 story files.

---

## Phase 2 — App Shell & Navigation

**Goal:** Replace the current manual `appView` state switching with URL-based routing and a proper sidebar navigation.

### 2A — API Client & Auth Foundation

- [x] `lib/api-client.ts` — typed fetch wrapper (port from current `fetchAPI`)
  - JWT token management
  - Case ID injection
  - Timeout configuration
  - Error type discrimination (validation, auth, network)
  - Response typing with generics
- [x] `features/auth/api.ts` — login, logout, getMe, getUsers
- [x] `features/auth/auth.types.ts` — User, AuthState, LoginRequest types
- [x] `features/auth/hooks/use-auth.ts` — auth state hook (Zustand store)
- [x] `features/auth/components/LoginPage.tsx` — login form with Owl branding
- [x] `features/auth/components/ProtectedRoute.tsx` — auth guard wrapper

### 2B — Routing

- [x] `app/routes.tsx` — full route tree (design system §8.2):
  ```
  /                        → Dashboard
  /cases                   → Case list
  /cases/:id               → Redirect to /cases/:id/graph
  /cases/:id/graph         → Graph view
  /cases/:id/timeline      → Timeline view
  /cases/:id/map           → Map view
  /cases/:id/table         → Table view
  /cases/:id/financial     → Financial view
  /cases/:id/evidence      → Evidence management
  /cases/:id/chat          → AI chat
  /cases/:id/workspace     → Workspace (theories, witnesses, tasks, notes)
  /cases/:id/reports       → Reports
  /cases/:id/settings      → Case settings
  /admin                   → Admin dashboard
  /admin/users             → User management
  /admin/profiles          → Profile management
  /settings                → Personal settings
  ```
- [x] Route-based code splitting with `React.lazy()` for heavy views (graph, map, timeline, financial)
- [x] URL-driven view state — remove all `appView`/`viewMode` state flags

### 2C — App Shell Layout

- [x] `app/layouts/AppLayout.tsx` — sidebar + main content area
- [x] `app/layouts/CaseLayout.tsx` — case-scoped layout with:
  - Case header (name, version, status)
  - View mode tabs (Graph, Timeline, Map, Table, Financial)
  - Active case context from URL params
  - Nested `<Outlet />` for view content
- [x] `app/layouts/AdminLayout.tsx` — admin section layout

### 2D — Sidebar Navigation

The current sidebar is minimal and lives inside App.jsx. The new sidebar should:

- [x] `components/ui/sidebar.tsx` — AppSidebar component
  - Collapsible: 56px (icons only) ↔ 240px (expanded) with smooth transition
  - Owl logo at top (amber accent on dark slate)
  - Navigation sections:
    - **Investigation** — Cases, Dashboard
    - **Active Case** (when case loaded) — Graph, Timeline, Map, Table, Financial, Evidence, Chat, Workspace, Reports
    - **Admin** (role-gated) — Users, Profiles, System
    - **Bottom** — Settings, user avatar, theme toggle, collapse button
  - Active route indicator (amber left border + subtle background highlight)
  - Case switcher dropdown at the top (when case is active)
  - Keyboard shortcut hints on hover (e.g., `⌘1` for Graph)
  - Responsive: auto-collapse below 1280px viewport

### 2E — Global UI Infrastructure

- [x] `app/providers.tsx` — compose all providers (Theme, QueryClient, Router, Zustand)
- [x] `stores/app.store.ts` — sidebar expanded/collapsed, active modal stack, command palette open
- [x] `hooks/use-keyboard-shortcuts.ts` — global keyboard shortcut registry
- [x] Command palette integration (`Cmd+K`) — search cases, entities, navigate routes
- [x] Toast notification system (Sonner) wired to API error handling
- [x] Error boundary components (per-route, per-feature)

### Deliverable
A running app with login → sidebar → route navigation. All routes render placeholder pages. No data fetching beyond auth.

### Estimated Scope
~35 files. Core navigation UX is fully functional.

---

## Phase 3 — State Management & Data Layer

**Goal:** Replace the 87 `useState` hooks in App.jsx with Zustand stores and TanStack Query. This is the backbone that all features build on.

### 3A — Zustand Stores

- [x] `stores/case.store.ts` — active case state:
  - `currentCaseId`, `currentCaseName`, `currentCaseVersion`
  - `setActiveCase()`, `clearActiveCase()`
  - Syncs with URL params via React Router
- [x] `stores/graph.store.ts` — graph interaction state:
  - `selectedNodeKeys: Set<string>`
  - `selectionDetails: NodeDetail[]`
  - `focusHistory: FocusEntry[]` (breadcrumb trail)
  - `searchTerm`, `filters`
  - `viewSettings` (layout, physics, labels)
  - Actions: `selectNodes()`, `clearSelection()`, `pushFocus()`, `popFocus()`
- [x] `stores/ui.store.ts` — UI chrome state:
  - `sidebarExpanded: boolean`
  - `modalStack: ModalEntry[]` (replaces 20+ boolean flags)
  - `commandPaletteOpen: boolean`
  - `chatPanelOpen: boolean`
  - Actions: `openModal()`, `closeModal()`, `toggleSidebar()`

### 3B — TanStack Query Integration

- [x] `lib/query-client.ts` — default query client config (stale times, retry, error handling)
- [x] `features/cases/api.ts` — typed case API functions
- [x] `features/cases/hooks/use-cases.ts` — `useQuery` for case list
- [x] `features/cases/hooks/use-case.ts` — `useQuery` for single case
- [x] `features/graph/api.ts` — typed graph API functions
- [x] `features/graph/hooks/use-graph-data.ts` — `useQuery` for graph data
- [x] `features/graph/hooks/use-node-details.ts` — `useQuery` for node details
- [x] `features/evidence/api.ts` — typed evidence API functions
- [x] `features/evidence/hooks/use-evidence.ts` — `useQuery` for evidence list
- [x] `features/chat/api.ts` — chat API with streaming support
- [x] Port remaining API namespaces: `snapshotsAPI`, `timelineAPI`, `workspaceAPI`, `financialAPI`, `profilesAPI`, `caseMembersAPI`, `setupAPI`

### 3C — Shared Types

- [x] `types/graph.types.ts` — Node, Edge, GraphData, NodeDetail, EntityType
- [x] `types/case.types.ts` — Case, CaseVersion, CaseMember, CasePermissions
- [x] `types/evidence.types.ts` — EvidenceFile, ProcessingStatus, IngestionResult
- [x] `types/api.types.ts` — ApiResponse, PaginatedResponse, ApiError
- [x] `types/entity.types.ts` — Entity, Relationship, Property

### 3D — Permission System

- [x] `hooks/use-permissions.ts` — replaces `CasePermissionContext`
  - Derives from case membership data (TanStack Query)
  - `canEdit`, `canDelete`, `canInvite`, `canUploadEvidence`, `isOwner`, `isSuperAdmin`
  - Used by components to conditionally render actions

### Deliverable
All data flows through TanStack Query (server state) and Zustand (client state). No `useState` for data that crosses component boundaries. Permission checks work throughout.

### Estimated Scope
~40 files. Data layer is complete and tested.

---

## Phase 4 — Case Management & Evidence

**Goal:** Rebuild the case browser and evidence processing views — currently the two largest components after App.jsx.

### 4A — Case List & Dashboard

Port from: `CaseManagementView.jsx` (2,348 lines)

- [x] `features/cases/components/CaseListPage.tsx` — case browser
  - Case cards grid/list toggle
  - Search and filter bar
  - Create case button → dialog
  - Case status badges
- [x] `features/cases/components/CaseCard.tsx` — individual case card (in @owl/ui)
  - Name, description, status, member count, last updated
  - Quick actions (open, archive, delete)
- [x] `features/cases/components/CreateCaseDialog.tsx` — case creation form
- [x] `features/cases/components/CaseSettingsPage.tsx` — case settings, members, permissions
  - Member management (invite, remove, change role)
  - Case metadata editing
  - Version management
  - Danger zone (archive, delete)
- [x] `features/cases/components/DashboardPage.tsx` — overview dashboard
  - Recent cases
  - Activity feed
  - Quick stats

### 4B — Evidence Management

Port from: `EvidenceProcessingView.jsx` (2,090 lines), `FileManagementPanel.jsx` (918 lines), `FileInfoViewer.jsx` (1,221 lines), `FolderProfileModal.jsx` (2,115 lines)

- [x] `features/evidence/components/EvidencePage.tsx` — evidence list and management
  - File table with status indicators
  - Upload dropzone
  - Bulk actions (process, delete, categorize)
  - Filter by status, type, date
- [x] `features/evidence/components/EvidenceUploader.tsx` — drag-and-drop file upload
  - Progress tracking
  - File type validation
  - Folder upload support
- [x] `features/evidence/components/EvidenceRow.tsx` — single evidence file row
  - Status indicator (processed/processing/queued/failed)
  - File metadata
  - Actions (view, reprocess, delete)
- [x] `features/evidence/components/EvidenceDetailSheet.tsx` — side panel for file details
  - File content preview
  - Metadata display
  - Processing logs
  - Extracted entities
- [x] `features/evidence/components/FolderProfileDialog.tsx` — folder/file processing configuration
  - Profile assignment
  - Advanced settings
  - Break into smaller sub-components (currently 2,115 lines)
- [x] `features/evidence/components/ProcessingLogViewer.tsx` — processing pipeline logs
- [x] `features/evidence/hooks/use-upload.ts` — upload state management with progress

### 4C — Snapshot System

Port from: `SnapshotList.jsx` (415 lines), `SnapshotsSection.jsx` (717 lines)

- [x] `features/cases/components/SnapshotManager.tsx` — save/load/compare snapshots
- [x] `features/cases/hooks/use-snapshots.ts` — snapshot CRUD with TanStack Query

### Deliverable
Case management and evidence workflows fully functional. Users can create cases, upload evidence, process files, and manage settings — all via URL routes, not modals-from-modals.

### Estimated Scope
~30 component files, replacing ~7,600 lines of current code.

---

## Phase 5 — Graph View

**Goal:** Rebuild the primary investigation view. This is the most complex view and the heart of the application.

### 5A — Graph Canvas

Port from: `GraphView.jsx` (1,514 lines)

- [x] `features/graph/components/GraphPage.tsx` — graph view page (light orchestrator)
- [x] `features/graph/components/GraphCanvas.tsx` — graph renderer
  - Evaluate Cytoscape.js vs keeping react-force-graph-2d
  - Node rendering with Owl entity colors (`nodeColors` from theme)
  - Edge rendering with relationship type labels
  - Pan, zoom, fit-to-view controls
  - Lasso/marquee multi-select
  - Node click → select, double-click → expand
  - Minimap overlay
- [x] `features/graph/components/GraphToolbar.tsx` — toolbar above graph
  - Layout options (force, hierarchical, radial, circular)
  - Search within graph
  - Zoom controls
  - Fit-to-view
  - Screenshot/export
- [x] `features/graph/components/GraphContextMenu.tsx` — right-click menu on nodes/edges
  - Expand node, hide node, pin node
  - Edit entity, merge entities
  - Find paths, show subgraph
  - Copy details
  - Permission-gated actions
- [x] `features/graph/components/GraphSearchFilter.tsx` — search and filter panel
  - Entity type filters
  - Property search
  - Date range filter
  - Confidence threshold slider
  - Advanced: Cypher query input
- [x] `features/graph/hooks/use-graph-layout.ts` — layout computation (Web Worker for large graphs)
- [x] `features/graph/hooks/use-graph-interaction.ts` — selection, hover, context menu state
- [x] `features/graph/hooks/use-graph-search.ts` — search within graph data

### 5B — Node Detail Panel

Port from: `NodeDetails.jsx` (723 lines), plus parts of App.jsx selection handling

- [x] `features/graph/components/NodeDetailSheet.tsx` — resizable side panel
  - Entity header (name, type badge, confidence)
  - Properties table
  - Connections list (grouped by relationship type)
  - Source evidence references
  - Edit button (opens edit dialog)
  - Action buttons (expand, hide, pin)
- [x] `features/graph/components/NodePropertiesTable.tsx` — key-value property display
- [x] `features/graph/components/ConnectionsList.tsx` — grouped relationship list
- [x] `features/graph/components/MultiNodePanel.tsx` — multi-selection summary
  - Selected count
  - Common properties
  - Bulk actions (merge, hide, create subgraph)
  - Compare entities side-by-side

### 5C — Graph Operations

Port from: various modals (AddNodeModal, CreateRelationshipModal, MergeEntitiesModal, EditNodeModal, ExpandGraphModal, etc.)

- [x] `features/graph/components/AddNodeDialog.tsx` — create new entity
- [x] `features/graph/components/EditNodeDialog.tsx` — edit entity properties
- [x] `features/graph/components/CreateRelationshipDialog.tsx` — create relationship between nodes
- [x] `features/graph/components/MergeEntitiesDialog.tsx` — merge duplicate entities
- [x] `features/graph/components/ExpandGraphDialog.tsx` — expand graph from selected nodes
- [x] `features/graph/components/SubgraphAnalysisPanel.tsx` — subgraph analysis results
- [x] `features/graph/components/EntityComparisonSheet.tsx` — side-by-side entity comparison
- [x] `features/graph/components/SimilarEntitiesPanel.tsx` — similar entity suggestions

### 5D — Cypher Query Interface

Port from: `DatabaseModal.jsx` (1,224 lines)

- [x] `features/graph/components/CypherPanel.tsx` — Cypher query input and results
  - Monospaced input with syntax hints
  - Query history
  - Results table
  - Graph preview of results

### Deliverable
Full graph investigation workflow: view graph, search, filter, select nodes, view details, edit entities, create relationships, merge, expand, run Cypher queries. All interactions use Zustand graph store, data fetched via TanStack Query.

### Estimated Scope
~30 component files, replacing ~5,000+ lines of current code.

---

## Phase 6 — Analytical Views

**Goal:** Rebuild Timeline, Map, Table, and Financial views. Each becomes a self-contained feature module.

### 6A — Table View

Port from: `GraphTableView.jsx` (2,595 lines)

- [x] `features/table/components/TablePage.tsx` — table view of graph data
  - Use `@owl/ui` DataTable component
  - Column visibility toggle
  - Sorting, filtering per-column
  - Row expansion for details
  - Virtual scrolling for large datasets (TanStack Virtual)
  - Export to CSV
- [x] `features/table/components/TableColumnConfig.tsx` — column management
- [x] `features/table/hooks/use-table-state.ts` — persisted column/sort preferences

### 6B — Timeline View

Port from: `TimelineView.jsx` (437 lines) + 7 sub-components (1,350 lines total)

- [x] `features/timeline/components/TimelinePage.tsx` — temporal event visualization
- [x] `features/timeline/components/TimelineCanvas.tsx` — main timeline renderer
  - Swim lanes per entity
  - Event markers with type-based icons
  - Relationship lines between events
  - Zoom and pan on time axis
- [x] `features/timeline/components/TimelineControls.tsx` — date range, zoom, playback
- [x] `features/timeline/components/EntityDock.tsx` — entity selector for swim lanes
- [x] `features/timeline/components/TimelineFilterPanel.tsx` — event type filters
- [x] `features/timeline/hooks/use-timeline-data.ts` — transform graph data to timeline events

### 6C — Map View

Port from: `MapView.jsx` (1,476 lines) + 6 sub-components (1,726 lines total)

- [x] `features/map/components/MapPage.tsx` — geospatial visualization
- [x] `features/map/components/MapCanvas.tsx` — Leaflet map with entity markers
  - Marker clustering
  - Entity type colored pins
  - Popup on click with entity summary
- [x] `features/map/components/MapControls.tsx` — layer toggles, zoom
- [x] `features/map/components/HeatmapLayer.tsx` — activity density heatmap
- [x] `features/map/components/MovementTrails.tsx` — entity movement paths
- [x] `features/map/components/RouteAnalysisPanel.tsx` — route analysis tools
- [x] `features/map/components/ProximityAnalysisPanel.tsx` — proximity analysis tools
- [x] `features/map/components/HotspotPanel.tsx` — hotspot detection
- [x] `features/map/hooks/use-map-data.ts` — transform graph data to geo features

### 6D — Financial View

Port from: `FinancialView.jsx` (536 lines) + 8 sub-components (2,693 lines total)

- [x] `features/financial/components/FinancialPage.tsx` — financial analysis view
- [x] `features/financial/components/TransactionTable.tsx` — transaction list with filters
  - Uses DataTable component
  - Inline category editing
  - Row selection for bulk actions
- [x] `features/financial/components/FinancialCharts.tsx` — recharts visualizations
  - Transaction volume over time
  - Category breakdown
  - Flow analysis
- [x] `features/financial/components/FinancialSummaryCards.tsx` — top-level metrics
- [x] `features/financial/components/FinancialFilterPanel.tsx` — date range, entity, category filters
- [x] `features/financial/components/CategoryManagementDialog.tsx` — create/edit categories
- [x] `features/financial/components/BulkCorrectionDialog.tsx` — bulk re-categorize
- [x] `features/financial/components/SubTransactionDialog.tsx` — split transactions
- [x] `features/financial/hooks/use-financial-data.ts` — transaction data with TanStack Query

### Deliverable
All four analytical views fully functional as independent route-based pages. Each shares the graph data store but owns its own view-specific state and data transformations.

### Estimated Scope
~45 component files, replacing ~8,600 lines of current code.

---

## Phase 7 — Chat, Workspace & Reports

**Goal:** Rebuild the remaining major feature areas.

### 7A — AI Chat

Port from: `ChatPanel.jsx` (1,081 lines), `ChatHistoryList.jsx`

- [x] `features/chat/components/ChatPage.tsx` — full-page chat view (also usable as side panel)
- [x] `features/chat/components/ChatMessageList.tsx` — scrollable message list
- [x] `features/chat/components/ChatMessage.tsx` — single message (user or AI)
  - Markdown rendering
  - Code blocks with copy
  - Citation references (clickable → evidence source)
  - Debug/pipeline expansion (collapsible)
- [x] `features/chat/components/ChatInput.tsx` — message input with context badges
  - Selected node context chips
  - Document scope indicator
  - Send button, keyboard submit
- [x] `features/chat/components/ChatHistoryDrawer.tsx` — conversation history browser
- [x] `features/chat/components/CitationPanel.tsx` — source document viewer for citations
- [x] `features/chat/hooks/use-chat.ts` — streaming message state, history management
- [x] `features/chat/hooks/use-chat-context.ts` — selected nodes/documents as context

### 7B — Workspace

Port from: 35 workspace components (12,246 lines total)

The workspace is a collection of case investigation tools. Decompose into discrete sections:

- [x] `features/workspace/components/WorkspacePage.tsx` — workspace layout with collapsible sections
- [x] `features/workspace/components/CaseContextSection.tsx` — case summary and context
- [x] `features/workspace/components/TheoriesSection.tsx` — investigation theories
- [x] `features/workspace/components/TasksSection.tsx` — investigation tasks/checklist
- [x] `features/workspace/components/WitnessMatrixSection.tsx` — witness tracking
- [x] `features/workspace/components/InvestigativeNotesSection.tsx` — case notes
- [x] `features/workspace/components/DocumentsSection.tsx` — linked documents
- [x] `features/workspace/components/CaseFilesSection.tsx` — attached files
- [x] `features/workspace/components/SnapshotsSection.tsx` — graph snapshots
- [x] `features/workspace/components/AttachedItemsDialog.tsx` — item attachment management (break down from 1,346 lines)
- [x] Reusable `WorkspaceSection.tsx` wrapper — standard collapsible section with header, count badge, and action buttons (replaces per-section boilerplate)

### 7C — Reports

- [x] `features/reports/components/ReportsPage.tsx` — report list
- [x] `features/reports/components/ReportBuilder.tsx` — create/edit reports
- [x] `features/reports/components/ReportViewer.tsx` — view generated report
- [x] `features/reports/hooks/use-reports.ts` — report CRUD
- [x] Port PDF/HTML export utilities (`theoryHtmlExport.js`, `theoryPdfExport.js`, `pdfExport.js`)

### Deliverable
All feature areas ported. The application is functionally complete.

### Estimated Scope
~40 component files, replacing ~14,300 lines of current code.

---

## Phase 8 — Admin, Settings & Polish

**Goal:** Admin functionality, user settings, and UX refinements across the entire app.

### 8A — Admin Area

Port from: parts of `CaseManagementView.jsx`, `SystemLogsPanel.jsx` (645 lines), `BackgroundTasksPanel.jsx` (384 lines), `CostLedgerPanel.jsx` (453 lines), `CreateUserModal.jsx`, `ProfileEditor.jsx` (820 lines)

- [x] `features/admin/components/AdminDashboardPage.tsx` — admin overview
- [x] `features/admin/components/UserManagementPage.tsx` — user list, create, edit, disable
- [x] `features/admin/components/ProfileManagementPage.tsx` — LLM/processing profiles
- [x] `features/admin/components/SystemLogsPage.tsx` — system log viewer
- [x] `features/admin/components/BackgroundTasksPage.tsx` — running tasks monitor
- [x] `features/admin/components/UsagePage.tsx` — LLM cost tracking, usage analytics
- [x] `features/admin/components/SetupWizard.tsx` — first-time setup flow

### 8B — Settings

- [x] `features/settings/components/SettingsPage.tsx` — personal settings
  - Theme toggle (dark/light/system)
  - Keyboard shortcuts reference
  - Notification preferences
  - Default view preferences

### 8C — Cross-Cutting Polish

- [x] Global loading states — route-level `Suspense` boundaries with Skeleton placeholders
- [x] Error boundaries — per-feature error recovery with retry
- [x] Toast notifications — success/error/warning for all mutations
- [x] Keyboard shortcuts — register shortcuts for every major action
  - `Cmd+K` → command palette
  - `Cmd+1-6` → switch views
  - `Escape` → close modal/panel
  - `Cmd+S` → save (context-dependent)
  - `Delete` → delete selected (with confirmation)
- [x] Responsive behavior — sidebar auto-collapse, panel → overlay on tablet
- [x] `prefers-reduced-motion` support — disable Framer Motion
- [x] Accessibility audit — keyboard navigation, ARIA labels, contrast ratios
- [x] Empty states — branded empty state for every list/page
- [x] Optimistic updates — for entity edits, relationship creation, status changes

### Deliverable
Feature-complete, polished application matching the Owl design system.

### Estimated Scope
~25 component files + cross-cutting improvements.

---

## Phase 9 — Performance & Testing

**Goal:** Meet performance targets from design system §12, establish test coverage.

### 9A — Performance Optimization

- [x] Route-based code splitting — verify all heavy views are lazy-loaded
- [x] Bundle analysis — identify and tree-shake unused dependencies
- [x] Virtual scrolling — implement TanStack Virtual for DataTable, entity lists, chat history
- [x] Web Worker for graph layout — offload force simulation to worker thread
- [x] Image/asset optimization
- [x] Measure against targets:
  - FCP < 1.2s
  - LCP < 2.0s
  - TTI < 2.5s
  - Initial bundle < 200KB gzipped
  - 1,000 node graph render < 500ms
  - 10,000 node graph render < 2s
  - Route transition < 100ms

### 9B — Testing

- [x] Unit tests for all Zustand stores
- [x] Unit tests for all hooks (custom render helpers)
- [x] Component tests for all `@owl/ui` components
- [x] Integration tests for critical flows:
  - Login → case list → open case → graph view
  - Upload evidence → process → view in graph
  - Chat with context → follow citation
  - Create entity → edit → merge
- [x] API mocking with MSW (Mock Service Worker)
- [x] Visual regression tests for `@owl/ui` (Chromatic or Percy)

### 9C — CI/CD

- [x] Pre-commit: lint + type-check
- [x] CI pipeline: lint → type-check → unit tests → build → integration tests
- [x] Bundle size tracking in CI (fail on regression)

### Deliverable
Performance targets met. Test coverage > 70% for stores/hooks, > 50% for components. CI pipeline green.

### Estimated Scope
~60 test files + CI configuration.

---

## Phase 10 — Migration & Cutover

**Goal:** Switch production traffic from `frontend/` to `frontend_v2/`.

### 10A — Migration Preparation

- [x] Feature parity audit — compare every feature/interaction between v1 and v2
- [x] Data migration — ensure all localStorage/sessionStorage keys are compatible
- [x] API compatibility — verify v2 works with the same backend without API changes
- [x] URL migration plan — document any URL structure changes

### 10B — Parallel Running

- [x] Configure Vite/Nginx to serve both frontends (e.g., `/v2/` prefix for new)
- [x] Internal team testing period on v2
- [x] Bug fix sprint from testing feedback
- [x] User acceptance testing

### 10C — Cutover

- [x] Switch default frontend to v2
- [x] Keep v1 accessible at `/v1/` for rollback
- [x] Monitor error rates, performance metrics
- [x] After stability period, archive `frontend/` directory

### 10D — Cleanup

- [x] Remove `frontend/` directory (or archive)
- [x] Rename `frontend_v2/` to `frontend/`
- [x] Update all documentation, deployment scripts, CI/CD
- [x] Update CLAUDE.md / project memory

---

## Summary

| Phase | Focus | Key Metric |
|-------|-------|------------|
| 0 | Scaffolding | Project builds and runs |
| 1 | `@owl/ui` component library | All components in Storybook |
| 2 | App shell, routing, sidebar | URL-based navigation works |
| 3 | State management & data layer | Zero prop drilling, typed API |
| 4 | Cases & evidence | Case lifecycle fully functional |
| 5 | Graph view | Core investigation workflow |
| 6 | Timeline, Map, Table, Financial | All analytical views |
| 7 | Chat, Workspace, Reports | All features ported |
| 8 | Admin, settings, polish | Feature-complete and polished |
| 9 | Performance & testing | Targets met, tests passing |
| 10 | Migration & cutover | Production switch |

### Guiding Principles

1. **Brand layer is law** — never use raw shadcn or arbitrary Tailwind colors. Everything goes through `@owl/ui`.
2. **Features own their code** — each feature has its own components, hooks, API functions, and types. No cross-feature imports except through shared stores.
3. **URL is the source of truth** — if it's a view, it has a route. No hidden state-driven navigation.
4. **Server state vs client state** — TanStack Query for anything from the API. Zustand for UI state only.
5. **No god components** — if a component exceeds ~300 lines, it needs decomposition. The largest component in v2 should be under 400 lines.
6. **TypeScript strict mode** — no `any`, no `// @ts-ignore`. Types are documentation.
7. **Dark mode default** — every component must look correct in dark mode first, light mode second.
8. **Data density** — 14px base, compact spacing, truncation with tooltips. Investigators need information density.
9. **Keyboard-first** — every action has a shortcut. Command palette is the primary discovery mechanism.
10. **Test what matters** — stores, hooks, and critical user flows. Don't chase coverage numbers on presentational components.
