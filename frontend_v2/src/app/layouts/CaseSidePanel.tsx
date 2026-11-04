import { lazy, Suspense, useState } from "react"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import { LazyPanel } from "@/components/ui/lazy-panel"
import {
  Info,
  Loader2,
  MessageSquare,
  NotebookPen,
  PanelRightClose,
  Search,
} from "lucide-react"
import { useParams, useMatch } from "react-router-dom"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useUIStore } from "@/stores/ui.store"
import { useGraphStore } from "@/stores/graph.store"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { cn } from "@/lib/cn"
import { LoadingWords } from "@/components/ui/loading-spinner"

// Each panel's code loads when the panel is first shown, not with the app shell: the node editor alone brings the
// map library (about 1 MB), and the statement panel, chat and notebook bring their own (lx-shell bundle report).
const NodeDetailSheet = lazy(() =>
  import("@/features/graph/components/NodeDetailSheet").then((m) => ({ default: m.NodeDetailSheet }))
)
const EditNodeDialog = lazy(() =>
  import("@/features/graph/components/EditNodeDialog").then((m) => ({ default: m.EditNodeDialog }))
)
const ChatSidePanel = lazy(() =>
  import("@/features/chat/components/ChatSidePanel").then((m) => ({ default: m.ChatSidePanel }))
)
const NotebookPanel = lazy(() =>
  import("@/features/notebook/components/NotebookPanel").then((m) => ({ default: m.NotebookPanel }))
)
// The statement panel and its access check (which brings the schema library) load together, on Financial only.
const StatementFilesWithAccess = lazy(async () => {
  const [access, panel] = await Promise.all([
    import("@/features/financial/components/FinancialAccessProvider"),
    import("@/features/financial/components/StatementFilesPanel"),
  ])
  function StatementFiles({ caseId }: { caseId: string }) {
    return (
      <access.FinancialAccessProvider caseId={caseId} quietFailure>
        <panel.StatementFilesPanel key={caseId} caseId={caseId} />
      </access.FinancialAccessProvider>
    )
  }
  return { default: StatementFiles }
})

/**
 * Collapsed icon rail for non-graph case views.
 * Same look as GraphSidePanelRail, but without graph-specific tool overlays.
 */
export function CaseSidePanelRail() {
  const tab = useUIStore((s) => s.graphPanelTab)
  const expandTo = useUIStore((s) => s.expandGraphPanelTo)
  const isEvidenceRoute = !!useMatch("/cases/:id/evidence")
  const isFinancialRoute = !!useMatch("/cases/:id/financial")
  const evidenceSidebarTab = useEvidenceStore((s) => s.sidebarTab)
  const setSidebarTab = useEvidenceStore((s) => s.setSidebarTab)
  const textSearchTerm = useEvidenceStore((s) => s.textSearchTerm)
  const textSearchOverlayOpen = useEvidenceStore((s) => s.textSearchOverlayOpen)
  const setSearchMode = useEvidenceStore((s) => s.setSearchMode)
  const closeTextSearch = useEvidenceStore((s) => s.closeTextSearch)

  const handleExpand = (target: string) => {
    if (isEvidenceRoute) {
      setSidebarTab(target as "details" | "processing" | "chat" | "notebook")
      closeTextSearch()
    } else {
      expandTo(target as "detail" | "chat" | "notebook")
    }
    useUIStore.getState().setGraphPanelCollapsed(false)
  }

  // Determine which tab is active for indicator
  const isDetailsActive = isEvidenceRoute
    ? evidenceSidebarTab === "details"
    : tab === "detail"
  const isProcessingActive =
    isEvidenceRoute && evidenceSidebarTab === "processing"
  const isChatActive = isEvidenceRoute
    ? evidenceSidebarTab === "chat"
    : tab === "chat"
  const isNotebookActive = isEvidenceRoute
    ? evidenceSidebarTab === "notebook"
    : tab === "notebook"

  return (
    <div className="flex h-full w-12 flex-col items-center gap-1 border-l border-border bg-panel pt-2">
      {isEvidenceRoute && textSearchTerm.trim().length > 0 && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Reopen text search"
              className={cn(
                "relative",
                textSearchOverlayOpen && "text-foreground"
              )}
              onClick={() => {
                setSearchMode("text")
                useUIStore.getState().setGraphPanelCollapsed(false)
              }}
            >
              <Search className="size-4" />
              {textSearchOverlayOpen && (
                <span className="absolute -left-1 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="left">Reopen text search</TooltipContent>
        </Tooltip>
      )}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={
              isFinancialRoute ? "Open statement files" : "Open case details"
            }
            className={cn("relative", isDetailsActive && "text-foreground")}
            onClick={() => handleExpand(isEvidenceRoute ? "details" : "detail")}
          >
            <Info className="size-4" />
            {isDetailsActive && (
              <span className="absolute -left-1 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-amber-500" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">
          {isFinancialRoute ? "Statements" : "Details"}
        </TooltipContent>
      </Tooltip>
      {isEvidenceRoute && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Open evidence processing"
              className={cn(
                "relative",
                isProcessingActive && "text-foreground"
              )}
              onClick={() => handleExpand("processing")}
            >
              <Loader2 className="size-4" />
              {isProcessingActive && (
                <span className="absolute -left-1 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-amber-500" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="left">Processing</TooltipContent>
        </Tooltip>
      )}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Open AI chat"
            className={cn("relative", isChatActive && "text-foreground")}
            onClick={() => handleExpand("chat")}
          >
            <MessageSquare className="size-4" />
            {isChatActive && (
              <span className="absolute -left-1 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-amber-500" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">AI Chat</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Open Notebook"
            className={cn("relative", isNotebookActive && "text-foreground")}
            onClick={() => handleExpand("notebook")}
          >
            <NotebookPen className="size-4" />
            {isNotebookActive && (
              <span className="absolute -left-1 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-amber-500" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">Notebook</TooltipContent>
      </Tooltip>
    </div>
  )
}

/**
 * Expanded panel content for non-graph case views.
 * Shows entity details (NodeDetailSheet) or AI chat — no tool overlays.
 */
export function CaseSidePanelContent() {
  const { id: caseId } = useParams()
  const isFinancialRoute = !!useMatch("/cases/:id/financial")
  const tab = useUIStore((s) => s.graphPanelTab)
  const setCollapsed = useUIStore((s) => s.setGraphPanelCollapsed)
  const setTab = useUIStore((s) => s.setGraphPanelTab)
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const hasSelection = selectedNodeKeys.size > 0
  const [editNodeKey, setEditNodeKey] = useState<string | null>(null)
  // The editor's code is fetched on the first edit and then stays mounted, so closing keeps its close animation.
  const [editorWanted, setEditorWanted] = useState(false)

  return (
    <div className="flex h-full flex-col border-l border-border bg-panel-raised">
      {/* Tab bar + collapse chevron */}
      <div className="flex items-center border-b border-border bg-panel">
        <button
          type="button"
          onClick={() => setTab("detail")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2",
            tab === "detail"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Info className="size-3.5" />
          {isFinancialRoute ? "Statements" : "Details"}
        </button>
        <button
          type="button"
          onClick={() => setTab("chat")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2",
            tab === "chat"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <MessageSquare className="size-3.5" />
          AI Chat
        </button>
        <button
          type="button"
          onClick={() => setTab("notebook")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2",
            tab === "notebook"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <NotebookPen className="size-3.5" />
          Notebook
        </button>
        <div className="ml-auto pr-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Collapse side panel"
                onClick={() => setCollapsed(true)}
              >
                <PanelRightClose className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Collapse panel</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Panel content */}
      <div className="flex-1 overflow-hidden">
        {isFinancialRoute && caseId && (
          <div className="h-full" hidden={tab !== "detail"}>
            <LazyPanel>
              <StatementFilesWithAccess key={caseId} caseId={caseId} />
            </LazyPanel>
          </div>
        )}
        <LazyPanel>
        {tab === "detail" ? (
          isFinancialRoute ? null : hasSelection ? (
            <NodeDetailSheet
              caseId={caseId!}
              onEditNode={(nodeKey) => {
                setEditorWanted(true)
                setEditNodeKey(nodeKey)
              }}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <Info className="size-8 text-muted-foreground/40" />
              <p className="text-sm font-medium text-muted-foreground">
                Select an entity to view details
              </p>
              <p className="text-xs text-muted-foreground/70">
                Click a node on the graph or use search
              </p>
            </div>
          )
        ) : tab === "chat" ? (
          caseId && <ChatSidePanel caseId={caseId} />
        ) : (
          caseId && <NotebookPanel caseId={caseId} />
        )}
        </LazyPanel>
      </div>

      {editorWanted && (
        <ErrorBoundary level="section">
        <Suspense
          fallback={
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20">
              <LoadingWords className="rounded-md bg-background p-4 shadow">Opening the editor…</LoadingWords>
            </div>
          }
        >
          <EditNodeDialog
            open={!!editNodeKey}
            onOpenChange={(open) => !open && setEditNodeKey(null)}
            nodeKey={editNodeKey}
            caseId={caseId!}
          />
        </Suspense>
        </ErrorBoundary>
      )}
    </div>
  )
}
