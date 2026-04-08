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

// Lazy-loaded feature pages
const ChatPage = lazy(() =>
  import("@/features/chat/components/ChatPage").then((m) => ({
    default: m.ChatPage,
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
const AICostsPage = lazy(() =>
  import("@/features/admin/components/AICostsPage").then((m) => ({
    default: m.AICostsPage,
  }))
)

// Lazy-loaded settings
const SettingsPage = lazy(() =>
  import("@/features/settings/components/SettingsPage").then((m) => ({
    default: m.SettingsPage,
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

          {/* Case routes */}
          <Route path="/cases/:id" element={<CaseLayout />}>
            <Route index element={<Navigate to="graph" replace />} />
            <Route path="graph" element={<LazyPage><GraphPage /></LazyPage>} />
            <Route path="timeline" element={<LazyPage><TimelinePage /></LazyPage>} />
            <Route path="map" element={<LazyPage><MapPage /></LazyPage>} />
            <Route path="table" element={<LazyPage><TablePage /></LazyPage>} />
            <Route path="financial" element={<LazyPage><FinancialPage /></LazyPage>} />
            <Route path="evidence" element={<EvidenceExplorer />} />
            <Route path="chat" element={<LazyPage><ChatPage /></LazyPage>} />
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
            <Route path="tasks" element={<LazyPage><BackgroundTasksPage /></LazyPage>} />
            <Route path="usage" element={<Navigate to="/admin/ai-costs" replace />} />
          </Route>

          <Route path="/settings" element={<LazyPage><SettingsPage /></LazyPage>} />
        </Route>
      </Route>
    </Routes>
  )
}
