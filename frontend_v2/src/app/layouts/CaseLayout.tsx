import { Outlet, useMatch, useParams } from "react-router-dom"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { useUIStore } from "@/stores/ui.store"
import { CaseSidePanelRail, CaseSidePanelContent } from "./CaseSidePanel"
import { EvidenceContextSidebar } from "@/features/evidence/components/EvidenceContextSidebar"
import { useMediaQuery } from "@/hooks/use-media-query"

export function CaseLayout() {
  const { id: caseId } = useParams()
  const graphPanelCollapsed = useUIStore((s) => s.graphPanelCollapsed)
  const isGraphRoute = !!useMatch("/cases/:id/graph")
  const isAgentRoute = !!useMatch("/cases/:id/agent")
  const isEvidenceRoute = !!useMatch("/cases/:id/evidence")
  const narrowViewport = useMediaQuery("(max-width: 767px)")

  // Graph and Agent routes manage their own full-width workspaces.
  const showCaseSidePanel = !isGraphRoute && !isAgentRoute

  return (
    <div className="flex h-full">
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex flex-1 overflow-hidden">
          {showCaseSidePanel ? (
            <div className="relative flex min-w-0 flex-1 overflow-hidden">
              <ResizablePanelGroup orientation="horizontal" className="flex-1">
                <ResizablePanel
                  id="case-content"
                  order={1}
                  defaultSize={
                    narrowViewport || graphPanelCollapsed ? "100" : "70"
                  }
                  minSize="40"
                >
                  <div
                    className={
                      narrowViewport && graphPanelCollapsed
                        ? "h-full min-w-0 overflow-hidden pr-12"
                        : "h-full min-w-0 overflow-hidden"
                    }
                  >
                    <ErrorBoundary level="page">
                      <Outlet />
                    </ErrorBoundary>
                  </div>
                </ResizablePanel>
                {!narrowViewport && !graphPanelCollapsed && (
                  <>
                    <ResizableHandle withHandle />
                    <ResizablePanel
                      id="case-side-panel"
                      order={2}
                      defaultSize="30"
                      minSize="15"
                      maxSize="45"
                    >
                      {isEvidenceRoute ? (
                        <EvidenceContextSidebar caseId={caseId!} />
                      ) : (
                        <CaseSidePanelContent />
                      )}
                    </ResizablePanel>
                  </>
                )}
              </ResizablePanelGroup>
              {narrowViewport &&
                (graphPanelCollapsed ? (
                  <div className="absolute inset-y-0 right-0 z-30">
                    <CaseSidePanelRail />
                  </div>
                ) : (
                  <div className="absolute inset-0 z-40 bg-background">
                    {isEvidenceRoute ? (
                      <EvidenceContextSidebar caseId={caseId!} />
                    ) : (
                      <CaseSidePanelContent />
                    )}
                  </div>
                ))}
            </div>
          ) : (
            <div className="flex-1 overflow-hidden">
              <ErrorBoundary level="page">
                <Outlet />
              </ErrorBoundary>
            </div>
          )}

          {/* Collapsed rail for non-graph views */}
          {showCaseSidePanel && !narrowViewport && graphPanelCollapsed && (
            <CaseSidePanelRail />
          )}
        </div>
      </div>
    </div>
  )
}
