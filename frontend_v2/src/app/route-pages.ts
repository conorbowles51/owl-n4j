import { matchRoutes } from "react-router-dom"
import { timedLazy as lazy } from "@/lib/timed-lazy"

/*
 * The lazy route pages (app/routes.tsx renders them) and the address each one opens at, so main.tsx can start the
 * page code of the address being opened before the shell has rendered. Not a .tsx file of components, so the routes
 * file keeps exporting only components (react-refresh/only-export-components).
 */

// Lazy-loaded heavy views
const EvidenceExplorer = lazy(() =>
  import("@/features/evidence/components/EvidenceExplorer").then((m) => ({
    default: m.EvidenceExplorer,
  }))
)
const GraphPage = lazy(() =>
  import("@/features/graph/components/GraphPage").then((m) => ({
    default: m.GraphPage,
  }))
)
const TimelinePage = lazy(() =>
  import("@/features/timeline/components/TimelinePage").then((m) => ({
    default: m.TimelinePage,
  }))
)
const MapPage = lazy(() =>
  import("@/features/map/components/MapPage").then((m) => ({
    default: m.MapPage,
  }))
)
const TablePage = lazy(() =>
  import("@/features/table/components/TablePage").then((m) => ({
    default: m.TablePage,
  }))
)
const FinancialPage = lazy(() =>
  import("@/features/financial/components/FinancialPage").then((m) => ({
    default: m.FinancialPage,
  }))
)
const PhonePrototypePage = lazy(() => import("@/features/phones/prototype/PhonePrototypePage"))
const PhoneGuidePage = lazy(() => import("@/features/phones/PhoneGuidePage"))
const MoneySignalsPage = lazy(() => import("@/features/phones/analysis/MoneySignalsPage"))
const DeletionTimelinePage = lazy(() => import("@/features/phones/analysis/DeletionTimelinePage"))
const RelationshipsPage = lazy(() => import("@/features/phones/analysis/RelationshipsPage"))
const DeviceUsersPage = lazy(() => import("@/features/phones/analysis/DeviceUsersPage"))
const ReparsePage = lazy(() => import("@/features/phones/analysis/ReparsePage"))
const IncidentWindowPage = lazy(() => import("@/features/phones/analysis/IncidentWindowPage"))
const MessagesAcrossPhonesPage = lazy(() => import("@/features/phones/analysis/MessagesAcrossPhonesPage"))
const GroupRolesPage = lazy(() => import("@/features/phones/analysis/GroupRolesPage"))
const TypedWordsPage = lazy(() => import("@/features/phones/analysis/TypedWordsPage"))
const IntentPage = lazy(() => import("@/features/phones/analysis/IntentPage"))
const CommonContactsPage = lazy(() => import("@/features/phones/analysis/CommonContactsPage"))
const ContactMatrixPage = lazy(() => import("@/features/phones/analysis/ContactMatrixPage"))
const NumberSwitchingPage = lazy(() => import("@/features/phones/analysis/NumberSwitchingPage"))
const ExtractionComparisonPage = lazy(() => import("@/features/phones/analysis/ExtractionComparisonPage"))
const AnalysesPage = lazy(() => import("@/features/phones/analysis/AnalysesPage"))
const PatternsPage = lazy(() =>
  import("@/features/pattern/components/PatternsPage").then((m) => ({ default: m.PatternsPage }))
)
const PhoneReviewPage = lazy(() => import("@/features/phones/review/PhoneReviewPage"))
const ConversationsPage = lazy(() => import("@/features/conversations/ConversationsPage"))
const MediaPage = lazy(() => import("@/features/phones/media/MediaPage"))
const MediaSpreadPage = lazy(() => import("@/features/phones/media/MediaSpreadPage"))
const PhonesIndexPage = lazy(() => import("@/features/conversations/PhoneRoutes").then((m) => ({ default: m.PhonesIndexPage })))
const PhoneRecordsRoute = lazy(() => import("@/features/conversations/PhoneRoutes").then((m) => ({ default: m.PhoneRecordsRoute })))
const SearchResultsPage = lazy(() => import("@/features/search/components/SearchResultsPage"))
const KeywordListsPage = lazy(() => import("@/features/search/components/KeywordListsPage"))
const RecordByIdRoute = lazy(() => import("@/features/conversations/PhoneRoutes").then((m) => ({ default: m.RecordByIdRoute })))
const PhoneSummaryPage = lazy(() => import("@/features/phones/summary/PhoneSummaryPage"))
const DossiersPage = lazy(() =>
  import("@/features/dossiers/components/DossiersPage").then((m) => ({
    default: m.DossiersPage,
  }))
)

// Lazy-loaded feature pages
const ChatPage = lazy(() =>
  import("@/features/chat/components/ChatPage").then((m) => ({
    default: m.ChatPage,
  }))
)
const AgentPage = lazy(() =>
  import("@/features/agent/components/AgentPage").then((m) => ({
    default: m.AgentPage,
  }))
)
const WorkspacePage = lazy(() =>
  import("@/features/workspace/components/WorkspacePage").then((m) => ({
    default: m.WorkspacePage,
  }))
)
const ReportsPage = lazy(() =>
  import("@/features/reports/components/ReportsPage").then((m) => ({
    default: m.ReportsPage,
  }))
)
const TriagePage = lazy(() =>
  import("@/features/triage/components/TriagePage").then((m) => ({
    default: m.TriagePage,
  }))
)
const CaseSettingsPage = lazy(() =>
  import("@/features/cases/components/CaseSettingsPage").then((m) => ({
    default: m.CaseSettingsPage,
  }))
)

// Lazy-loaded admin pages
const AdminDashboardPage = lazy(() =>
  import("@/features/admin/components/AdminDashboardPage").then((m) => ({
    default: m.AdminDashboardPage,
  }))
)
const UserManagementPage = lazy(() =>
  import("@/features/admin/components/UserManagementPage").then((m) => ({
    default: m.UserManagementPage,
  }))
)
const ProfileManagementPage = lazy(() =>
  import("@/features/admin/components/ProfileManagementPage").then((m) => ({
    default: m.ProfileManagementPage,
  }))
)
const SystemLogsPage = lazy(() =>
  import("@/features/admin/components/SystemLogsPage").then((m) => ({
    default: m.SystemLogsPage,
  }))
)
const BackgroundTasksPage = lazy(() =>
  import("@/features/admin/components/BackgroundTasksPage").then((m) => ({
    default: m.BackgroundTasksPage,
  }))
)
const ActivityPage = lazy(() =>
  import("@/features/admin/components/ActivityPage").then((m) => ({
    default: m.ActivityPage,
  }))
)
const SpeedPage = lazy(() =>
  import("@/features/admin/components/SpeedPage").then((m) => ({
    default: m.SpeedPage,
  }))
)
const AICostsPage = lazy(() =>
  import("@/features/admin/components/AICostsPage").then((m) => ({
    default: m.AICostsPage,
  }))
)
const PhoneRegistryPage = lazy(() =>
  import("@/features/admin/components/PhoneRegistryPage").then((m) => ({
    default: m.PhoneRegistryPage,
  }))
)
const PlatformUpdatesPage = lazy(() =>
  import("@/features/admin/components/PlatformUpdatesPage").then((m) => ({
    default: m.PlatformUpdatesPage,
  }))
)

// Lazy-loaded settings
const SettingsPage = lazy(() =>
  import("@/features/settings/components/SettingsPage").then((m) => ({
    default: m.SettingsPage,
  }))
)
const AISettingsPage = lazy(() =>
  import("@/features/settings/components/AISettingsPage").then((m) => ({
    default: m.AISettingsPage,
  }))
)

/** Every lazy route page, by name. */
export const pages = {
  EvidenceExplorer,
  GraphPage,
  TimelinePage,
  MapPage,
  TablePage,
  FinancialPage,
  PhonePrototypePage,
  PhoneGuidePage,
  MoneySignalsPage,
  DeletionTimelinePage,
  RelationshipsPage,
  DeviceUsersPage,
  ReparsePage,
  IncidentWindowPage,
  MessagesAcrossPhonesPage,
  GroupRolesPage,
  TypedWordsPage,
  IntentPage,
  CommonContactsPage,
  ContactMatrixPage,
  NumberSwitchingPage,
  ExtractionComparisonPage,
  AnalysesPage,
  PatternsPage,
  PhoneReviewPage,
  ConversationsPage,
  MediaPage,
  MediaSpreadPage,
  PhonesIndexPage,
  PhoneRecordsRoute,
  SearchResultsPage,
  KeywordListsPage,
  RecordByIdRoute,
  PhoneSummaryPage,
  DossiersPage,
  ChatPage,
  AgentPage,
  WorkspacePage,
  ReportsPage,
  TriagePage,
  CaseSettingsPage,
  AdminDashboardPage,
  UserManagementPage,
  ProfileManagementPage,
  SystemLogsPage,
  BackgroundTasksPage,
  ActivityPage,
  SpeedPage,
  AICostsPage,
  PhoneRegistryPage,
  PlatformUpdatesPage,
  SettingsPage,
  AISettingsPage,
}

/**
 * The lazy page of each address, so the page an address opens can start downloading at startup (main.tsx) beside
 * the shell instead of after it (measured 4 Nov: a fresh /cases/<id>/evidence ran shell, then page code, then data in
 * series). Kept equal to the routes in app/routes.tsx by app/routes-preload.test.ts.
 */
export const PAGE_CHUNK_ROUTES: { path: string; page: { preload: () => Promise<unknown> } }[] = [
  { path: "/triage", page: TriagePage },
  { path: "/cases/:id/graph", page: GraphPage },
  { path: "/cases/:id/timeline", page: TimelinePage },
  { path: "/cases/:id/map", page: MapPage },
  { path: "/cases/:id/table", page: TablePage },
  { path: "/cases/:id/financial", page: FinancialPage },
  { path: "/cases/:id/phones-prototype/:view?", page: PhonePrototypePage },
  { path: "/cases/:id/phone-review", page: PhoneReviewPage },
  { path: "/cases/:id/conversations", page: ConversationsPage },
  { path: "/cases/:id/phones", page: PhonesIndexPage },
  { path: "/cases/:id/phones/:extraction", page: PhoneSummaryPage },
  { path: "/cases/:id/phones/:extraction/records/conversations", page: ConversationsPage },
  { path: "/cases/:id/phones/:extraction/records/media", page: MediaPage },
  { path: "/cases/:id/phones/:extraction/records/media/spread", page: MediaSpreadPage },
  { path: "/cases/:id/phones/:extraction/records/:recordType", page: PhoneRecordsRoute },
  { path: "/cases/:id/records/:recordUid", page: RecordByIdRoute },
  { path: "/cases/:id/search", page: SearchResultsPage },
  { path: "/cases/:id/keyword-lists", page: KeywordListsPage },
  { path: "/cases/:id/phone-patterns", page: PatternsPage },
  { path: "/cases/:id/phone-money", page: MoneySignalsPage },
  { path: "/cases/:id/phone-analyses/deletions", page: DeletionTimelinePage },
  { path: "/cases/:id/phone-analyses/relationships", page: RelationshipsPage },
  { path: "/cases/:id/phone-analyses/groups", page: GroupRolesPage },
  { path: "/cases/:id/phone-analyses/typed-words", page: TypedWordsPage },
  { path: "/cases/:id/phone-analyses/searches", page: IntentPage },
  { path: "/cases/:id/phone-analyses/common-contacts", page: CommonContactsPage },
  { path: "/cases/:id/phone-analyses/who-contacts-whom", page: ContactMatrixPage },
  { path: "/cases/:id/phone-analyses/number-changes", page: NumberSwitchingPage },
  { path: "/cases/:id/phone-analyses/two-extractions", page: ExtractionComparisonPage },
  { path: "/cases/:id/phone-analyses/two-phones", page: DeviceUsersPage },
  { path: "/cases/:id/phone-analyses/read-again", page: ReparsePage },
  { path: "/cases/:id/phone-analyses/messages", page: MessagesAcrossPhonesPage },
  { path: "/cases/:id/phone-analyses/incident-window", page: IncidentWindowPage },
  { path: "/cases/:id/phone-analyses", page: AnalysesPage },
  { path: "/cases/:id/dossiers", page: DossiersPage },
  { path: "/cases/:id/evidence", page: EvidenceExplorer },
  { path: "/cases/:id/chat", page: ChatPage },
  { path: "/cases/:id/agent", page: AgentPage },
  { path: "/cases/:id/workspace", page: WorkspacePage },
  { path: "/cases/:id/reports", page: ReportsPage },
  { path: "/cases/:id/settings", page: CaseSettingsPage },
  { path: "/admin", page: AdminDashboardPage },
  { path: "/admin/ai-costs", page: AICostsPage },
  { path: "/admin/users", page: UserManagementPage },
  { path: "/admin/profiles", page: ProfileManagementPage },
  { path: "/admin/logs", page: SystemLogsPage },
  { path: "/admin/activity", page: ActivityPage },
  { path: "/admin/speed", page: SpeedPage },
  { path: "/admin/tasks", page: BackgroundTasksPage },
  { path: "/admin/updates", page: PlatformUpdatesPage },
  { path: "/admin/phone-registry", page: PhoneRegistryPage },
  { path: "/settings", page: SettingsPage },
  { path: "/settings/ai", page: AISettingsPage },
  { path: "/guide/phones", page: PhoneGuidePage },
  { path: "/cases/:id", page: WorkspacePage },
]

/** Starts downloading the page code of `pathname`'s route, if it has one; the page's own render then reuses it. */
export function preloadRoutePage(pathname: string): string | null {
  const match = matchRoutes(PAGE_CHUNK_ROUTES.map((r) => ({ path: r.path })), pathname)
  const hit = match?.[match.length - 1]?.route.path
  const entry = hit ? PAGE_CHUNK_ROUTES.find((r) => r.path === hit) : undefined
  if (!entry) return null
  void entry.page.preload().catch(() => {}) // a failed download is retried, and reported, by the page's own render
  return entry.path
}
