import { Outlet } from "react-router-dom"
import { ErrorBoundary } from "@/components/ui/error-boundary"

export function CaseLayout() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-auto">
        <ErrorBoundary level="page">
          <Outlet />
        </ErrorBoundary>
      </div>
    </div>
  )
}
