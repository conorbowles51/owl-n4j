import { Outlet } from "react-router-dom"
import { AppSidebar } from "@/components/ui/sidebar"
import { ErrorBoundary } from "@/components/ui/error-boundary"

export function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <AppSidebar />
      <main className="flex-1 overflow-hidden">
        <ErrorBoundary level="page">
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
