import { lazy, Suspense } from "react"
import { Outlet, useLocation, useMatch, useParams } from "react-router-dom"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { useUIStore } from "@/stores/ui.store"
import { CaseSidePanelRail, CaseSidePanelContent } from "./CaseSidePanel"
import { LazyPanel } from "@/components/ui/lazy-panel"
import { useMediaQuery } from "@/hooks/use-media-query"
import { phoneScreen } from "@/lib/phone-screen"

// Case search (Ctrl/Cmd+K) has nothing on screen until it is opened, so its code (search, phones and their schema
// library) loads just after the case page instead of inside the app shell.
const SearchDialog = lazy(() =>
  import("@/features/search/components/SearchDialog").then((m) => ({ default: m.SearchDialog }))
)

// Shown only on the Evidence page; its code loads with that page, not with every case page.
const LazyEvidenceContextSidebar = lazy(() =>
  import("@/features/evidence/components/EvidenceContextSidebar").then((m) => ({ default: m.EvidenceContextSidebar }))
)

const ReportProblem = lazy(() => import("@/components/ui/report-problem").then((m) => ({ default: m.ReportProblem })))

/** Report a problem on every phone screen (07 section 9), above the page so it stays on screen as the page scrolls. */
function PhoneProblemBar({ caseId, screen }: { caseId: string; screen: string }) {
  return (
    <div className="flex shrink-0 justify-end border-b px-2 py-1" data-testid="phone-problem-bar">
      <Suspense fallback={null}>
        <ReportProblem key={screen} caseId={caseId} screen={screen} components={[screen]} />
      </Suspense>
    </div>
  )
}
// The job tray, Guide and keys above a phone case's screens; its code loads with the case page, not with the shell.
const CaseStrip = lazy(() => import("@/features/phones/ui/CaseStrip"))

function EvidenceContextSidebar({ caseId }: { caseId: string }) {
  return (
    <LazyPanel>
      <LazyEvidenceContextSidebar caseId={caseId} />
    </LazyPanel>
  )
}

export function CaseLayout() {
  const { id: caseId } = useParams()
  const graphPanelCollapsed = useUIStore((s) => s.graphPanelCollapsed)
  const isGraphRoute = !!useMatch("/cases/:id/graph")
  const isAgentRoute = !!useMatch("/cases/:id/agent")
  const isEvidenceRoute = !!useMatch("/cases/:id/evidence")
  const narrowViewport = useMediaQuery("(max-width: 767px)")
  const screen = phoneScreen(useLocation().pathname)

  // Graph and Agent routes manage their own full-width workspaces.
  const showCaseSidePanel = !isGraphRoute && !isAgentRoute

  return (
    <div className="flex h-full">
      {caseId && (
        <ErrorBoundary
          fallback={
            <p role="alert" className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-background px-3 py-2 text-xs shadow">
              Case search (Ctrl+K) did not load. Reload the page to use it.
            </p>
          }
        >
          <Suspense fallback={null}>
            <SearchDialog caseId={caseId} />
          </Suspense>
        </ErrorBoundary>
      )}
      <div className="flex flex-1 flex-col overflow-hidden">
        {caseId && (
          <ErrorBoundary fallback={<></>}>
            <Suspense fallback={null}>
              <CaseStrip caseId={caseId} />
            </Suspense>
          </ErrorBoundary>
        )}
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
                    <div className="flex h-full min-h-0 flex-col">
                      {screen && caseId && <PhoneProblemBar caseId={caseId} screen={screen} />}
                      <div className="min-h-0 flex-1">
                        <ErrorBoundary level="page">
                          <Outlet />
                        </ErrorBoundary>
                      </div>
                    </div>
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
