import { Info, MessageSquare, PanelRightClose } from "lucide-react"
import { useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useUIStore } from "@/stores/ui.store"
import { useGraphStore } from "@/stores/graph.store"
import { cn } from "@/lib/cn"
import { NodeDetailSheet } from "@/features/graph/components/NodeDetailSheet"
import { ChatSidePanel } from "@/features/chat/components/ChatSidePanel"

/**
 * Collapsed icon rail for non-graph case views.
 * Same look as GraphSidePanelRail, but without graph-specific tool overlays.
 */
export function CaseSidePanelRail() {
  const tab = useUIStore((s) => s.graphPanelTab)
  const expandTo = useUIStore((s) => s.expandGraphPanelTo)

  return (
    <div className="flex h-full w-12 flex-col items-center gap-1 border-l border-border bg-muted/30 pt-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            className={cn(
              "relative",
              tab === "detail" && "text-foreground"
            )}
            onClick={() => expandTo("detail")}
          >
            <Info className="size-4" />
            {tab === "detail" && (
              <span className="absolute -left-1 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-amber-500" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">Details</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            className={cn(
              "relative",
              tab === "chat" && "text-foreground"
            )}
            onClick={() => expandTo("chat")}
          >
            <MessageSquare className="size-4" />
            {tab === "chat" && (
              <span className="absolute -left-1 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-amber-500" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">AI Chat</TooltipContent>
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
  const tab = useUIStore((s) => s.graphPanelTab)
  const setCollapsed = useUIStore((s) => s.setGraphPanelCollapsed)
  const setTab = useUIStore((s) => s.setGraphPanelTab)
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const hasSelection = selectedNodeKeys.size > 0

  return (
    <div className="flex h-full flex-col border-l border-border bg-card">
      {/* Tab bar + collapse chevron */}
      <div className="flex items-center border-b border-border bg-muted/30">
        <button
          type="button"
          onClick={() => setTab("detail")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2",
            tab === "detail"
              ? "border-foreground text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Info className="size-3.5" />
          Details
        </button>
        <button
          type="button"
          onClick={() => setTab("chat")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2",
            tab === "chat"
              ? "border-amber-500 text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <MessageSquare className="size-3.5" />
          AI Chat
        </button>
        <div className="ml-auto pr-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
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
        {tab === "detail" ? (
          hasSelection ? (
            <NodeDetailSheet caseId={caseId!} />
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
        ) : (
          caseId && <ChatSidePanel caseId={caseId} />
        )}
      </div>
    </div>
  )
}
