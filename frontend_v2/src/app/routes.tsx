import { Suspense } from "react"
import { Routes, Route, Navigate } from "react-router-dom"
import { pages } from "./route-pages"
import { PageLoading } from "./page-loading"
import { LoginPage } from "@/features/auth/components/LoginPage"
import { ProtectedRoute } from "@/features/auth/components/ProtectedRoute"
import { AppLayout } from "./layouts/AppLayout"
import { CaseLayout } from "./layouts/CaseLayout"
import { AdminLayout } from "./layouts/AdminLayout"
import { CaseManagementPage } from "@/features/cases/components/CaseManagementPage"

const {
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
} = pages

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
            <Route path="keyword-lists" element={<LazyPage><KeywordListsPage /></LazyPage>} />
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
            <Route path="evidence" element={<LazyPage><EvidenceExplorer /></LazyPage>} />
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
            <Route path="phone-registry" element={<LazyPage><PhoneRegistryPage /></LazyPage>} />
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
