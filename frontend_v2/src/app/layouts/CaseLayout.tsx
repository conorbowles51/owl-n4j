import { Outlet, useMatch } from "react-router-dom"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { useUIStore } from "@/stores/ui.store"
import { CaseSidePanelRail, CaseSidePanelContent } from "./CaseSidePanel"

export function CaseLayout() {
  const graphPanelCollapsed = useUIStore((s) => s.graphPanelCollapsed)
  const isGraphRoute = !!useMatch("/cases/:id/graph")

  // Graph page manages its own side panel with tool overlays
  const showCaseSidePanel = !isGraphRoute

  return (
    <div className="flex h-full">
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex flex-1 overflow-hidden">
          {showCaseSidePanel ? (
            <ResizablePanelGroup orientation="horizontal" className="flex-1">
              <ResizablePanel
                id="case-content"
                order={1}
                defaultSize={graphPanelCollapsed ? "100" : "70"}
                minSize="40"
              >
                <ErrorBoundary level="page">
                  <Outlet />
                </ErrorBoundary>
              </ResizablePanel>
              {!graphPanelCollapsed && (
                <>
                  <ResizableHandle withHandle />
                  <ResizablePanel
                    id="case-side-panel"
                    order={2}
                    defaultSize="30"
                    minSize="15"
                    maxSize="45"
                  >
                    <CaseSidePanelContent />
                  </ResizablePanel>
                </>
              )}
            </ResizablePanelGroup>
          ) : (
            <div className="flex-1 overflow-hidden">
              <ErrorBoundary level="page">
                <Outlet />
              </ErrorBoundary>
            </div>
          )}

          {/* Collapsed rail for non-graph views */}
          {showCaseSidePanel && graphPanelCollapsed && <CaseSidePanelRail />}
        </div>
      </div>
    </div>
  )
}
