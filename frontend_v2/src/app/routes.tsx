import { lazy, Suspense } from "react"
import { Routes, Route, Navigate } from "react-router-dom"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { LoginPage } from "@/features/auth/components/LoginPage"
import { ProtectedRoute } from "@/features/auth/components/ProtectedRoute"
import { AppLayout } from "./layouts/AppLayout"
import { CaseLayout } from "./layouts/CaseLayout"
import { AdminLayout } from "./layouts/AdminLayout"
import { CaseManagementPage } from "@/features/cases/components/CaseManagementPage"
import { EvidenceExplorer } from "@/features/evidence/components/EvidenceExplorer"

// Lazy-loaded heavy views
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

function PageLoading() {
  return (
    <div className="flex h-full items-center justify-center">
      <LoadingSpinner size="lg" />
    </div>
  )
}

function LazyPage({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<PageLoading />}>{children}</Suspense>
}

export function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/cases" replace />} />
          <Route path="/cases" element={<CaseManagementPage />} />
          <Route path="/triage" element={<LazyPage><TriagePage /></LazyPage>} />

          {/* Case routes */}
          <Route path="/cases/:id" element={<CaseLayout />}>
            <Route index element={<Navigate to="workspace" replace />} />
            <Route path="graph" element={<LazyPage><GraphPage /></LazyPage>} />
            <Route path="timeline" element={<LazyPage><TimelinePage /></LazyPage>} />
            <Route path="map" element={<LazyPage><MapPage /></LazyPage>} />
            <Route path="table" element={<LazyPage><TablePage /></LazyPage>} />
            <Route path="financial" element={<LazyPage><FinancialPage /></LazyPage>} />
            <Route path="cellebrite" element={<Navigate to="../phones" replace />} />
            <Route path="phones-prototype/:view?" element={<LazyPage><PhonePrototypePage /></LazyPage>} />
            <Route path="phone-review" element={<LazyPage><PhoneReviewPage /></LazyPage>} />
            <Route path="conversations" element={<LazyPage><ConversationsPage /></LazyPage>} />
            <Route path="phones" element={<LazyPage><PhonesIndexPage /></LazyPage>} />
            <Route path="phones/:extraction" element={<LazyPage><PhoneSummaryPage /></LazyPage>} />
            <Route path="phones/:extraction/records/conversations" element={<LazyPage><ConversationsPage /></LazyPage>} />
            <Route path="phones/:extraction/records/media" element={<LazyPage><MediaPage /></LazyPage>} />
            <Route path="phones/:extraction/records/media/spread" element={<LazyPage><MediaSpreadPage /></LazyPage>} />
            <Route path="phones/:extraction/records/:recordType" element={<LazyPage><PhoneRecordsRoute /></LazyPage>} />
            <Route path="records/:recordUid" element={<LazyPage><RecordByIdRoute /></LazyPage>} />
            <Route path="search" element={<LazyPage><SearchResultsPage /></LazyPage>} />
            <Route path="phone-patterns" element={<LazyPage><PatternsPage /></LazyPage>} />
            <Route path="phone-money" element={<LazyPage><MoneySignalsPage /></LazyPage>} />
            <Route path="phone-analyses/deletions" element={<LazyPage><DeletionTimelinePage /></LazyPage>} />
            <Route path="phone-analyses/relationships" element={<LazyPage><RelationshipsPage /></LazyPage>} />
            <Route path="phone-analyses/groups" element={<LazyPage><GroupRolesPage /></LazyPage>} />
            <Route path="phone-analyses/typed-words" element={<LazyPage><TypedWordsPage /></LazyPage>} />
            <Route path="phone-analyses/searches" element={<LazyPage><IntentPage /></LazyPage>} />
            <Route path="phone-analyses/common-contacts" element={<LazyPage><CommonContactsPage /></LazyPage>} />
            <Route path="phone-analyses/who-contacts-whom" element={<LazyPage><ContactMatrixPage /></LazyPage>} />
            <Route path="phone-analyses/number-changes" element={<LazyPage><NumberSwitchingPage /></LazyPage>} />
            <Route path="phone-analyses/two-extractions" element={<LazyPage><ExtractionComparisonPage /></LazyPage>} />
            <Route path="phone-analyses/two-phones" element={<LazyPage><DeviceUsersPage /></LazyPage>} />
            <Route path="phone-analyses/read-again" element={<LazyPage><ReparsePage /></LazyPage>} />
            <Route path="phone-analyses/messages" element={<LazyPage><MessagesAcrossPhonesPage /></LazyPage>} />
            <Route path="phone-analyses/incident-window" element={<LazyPage><IncidentWindowPage /></LazyPage>} />
            <Route path="phone-analyses" element={<LazyPage><AnalysesPage /></LazyPage>} />
            <Route path="profiles" element={<Navigate to="../dossiers" replace />} />
            <Route path="dossiers" element={<LazyPage><DossiersPage /></LazyPage>} />
            <Route path="evidence" element={<EvidenceExplorer />} />
            <Route path="chat" element={<LazyPage><ChatPage /></LazyPage>} />
            <Route path="agent" element={<LazyPage><AgentPage /></LazyPage>} />
            <Route path="workspace" element={<LazyPage><WorkspacePage /></LazyPage>} />
            <Route path="reports" element={<LazyPage><ReportsPage /></LazyPage>} />
            <Route path="settings" element={<LazyPage><CaseSettingsPage /></LazyPage>} />
          </Route>

          {/* Admin routes */}
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<LazyPage><AdminDashboardPage /></LazyPage>} />
            <Route path="ai-costs" element={<LazyPage><AICostsPage /></LazyPage>} />
            <Route path="users" element={<LazyPage><UserManagementPage /></LazyPage>} />
            <Route path="profiles" element={<LazyPage><ProfileManagementPage /></LazyPage>} />
            <Route path="logs" element={<LazyPage><SystemLogsPage /></LazyPage>} />
            <Route path="activity" element={<LazyPage><ActivityPage /></LazyPage>} />
            <Route path="speed" element={<LazyPage><SpeedPage /></LazyPage>} />
            <Route path="tasks" element={<LazyPage><BackgroundTasksPage /></LazyPage>} />
            <Route path="updates" element={<LazyPage><PlatformUpdatesPage /></LazyPage>} />
            <Route path="usage" element={<Navigate to="/admin/ai-costs" replace />} />
          </Route>

          <Route path="/settings" element={<LazyPage><SettingsPage /></LazyPage>} />
          <Route path="/settings/ai" element={<LazyPage><AISettingsPage /></LazyPage>} />
          <Route path="/guide/phones" element={<LazyPage><PhoneGuidePage /></LazyPage>} />
        </Route>
      </Route>
    </Routes>
  )
}
