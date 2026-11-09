import { lazy, Suspense, useEffect, useState } from "react"
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
// library) loads on the first open: the first Ctrl+K (the same event the keymap sends) or a return to saved results.
// A lazy component mounted closed still downloads its chunks, so the mount itself waits for that first ask.
const SearchDialog = lazy(() =>
  import("@/features/search/components/SearchDialog").then((m) => ({ default: m.SearchDialog }))
)

function useSearchWanted(savedResults: boolean): boolean {
  const [wanted, setWanted] = useState(savedResults)
  if (savedResults && !wanted) setWanted(true)
  useEffect(() => {
    if (wanted) return
    const want = () => setWanted(true)
    document.addEventListener("owl:toggle-command-palette", want)
    return () => document.removeEventListener("owl:toggle-command-palette", want)
  }, [wanted])
  return wanted
}

// Shown only on the Evidence page; its code loads with that page, not with every case page.
const LazyEvidenceContextSidebar = lazy(() =>
  import("@/features/evidence/components/EvidenceContextSidebar").then((m) => ({ default: m.EvidenceContextSidebar }))
)

// The job tray, Guide, keys and Report a problem above a phone case's screens; its code loads with the case page, not with the shell.
const CaseStrip = lazy(() => import("@/features/phones/ui/CaseStrip"))

// Guidance and step history (lx-guide): next steps after an action, tours, Start here, and the bottom history bar.
const CaseGuidance = lazy(() => import("@/features/guidance/CaseGuidanceBar"))
const CaseBottomBar = lazy(() => import("@/features/guidance/CaseGuidanceBar").then((m) => ({ default: m.CaseBottomBar })))

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
  const location = useLocation()
  const screen = phoneScreen(location.pathname)
  const searchWanted = useSearchWanted(!!(location.state as { caseSearch?: unknown } | null)?.caseSearch)

  // Graph and Agent routes manage their own full-width workspaces.
  const showCaseSidePanel = !isGraphRoute && !isAgentRoute

  return (
    <div className="flex h-full">
      {caseId && searchWanted && (
        <ErrorBoundary
          fallback={
            <p role="alert" className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-background px-3 py-2 text-xs shadow">
              Case search (Ctrl+K) did not load. Reload the page to use it.
            </p>
          }
        >
          <Suspense fallback={null}>
            <SearchDialog caseId={caseId} initialOpen />
          </Suspense>
        </ErrorBoundary>
      )}
      <div className="flex flex-1 flex-col overflow-hidden">
        {caseId && (
          <ErrorBoundary fallback={<></>}>
            <Suspense fallback={null}>
              <CaseStrip caseId={caseId} problemScreen={screen} />
            </Suspense>
          </ErrorBoundary>
        )}
        <div className="relative flex flex-1 overflow-hidden">
          {caseId && (
            <ErrorBoundary fallback={<></>}>
              <Suspense fallback={null}>
                <CaseGuidance caseId={caseId} />
              </Suspense>
            </ErrorBoundary>
          )}
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
        {caseId && (
          <ErrorBoundary fallback={<></>}>
            <Suspense fallback={<div className="h-7 shrink-0 border-t border-border bg-card" />}>
              <CaseBottomBar caseId={caseId} />
            </Suspense>
          </ErrorBoundary>
        )}
      </div>
    </div>
  )
}
