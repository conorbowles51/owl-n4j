import { Info, MessageSquare, PanelRightClose, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useUIStore } from "@/stores/ui.store"
import { useGraphStore } from "@/stores/graph.store"
import { cn } from "@/lib/cn"
import { NodeDetailSheet } from "./NodeDetailSheet"
import { ChatSidePanel } from "@/features/chat/components/ChatSidePanel"
import { ForceControlsPanel } from "./ForceControlsPanel"
import { GraphAnalysisPanel } from "./GraphAnalysisPanel"
import { RecycleBinPanel } from "./RecycleBinPanel"
import { CypherPanel } from "./CypherPanel"
import { SimilarEntitiesView } from "./SimilarEntitiesView"
import type { GraphData, GraphNode } from "@/types/graph.types"

const TOOL_LABELS: Record<string, string> = {
  "force-controls": "Force Controls",
  analysis: "Graph Analysis",
  similar: "Similar Entities",
  cypher: "Cypher Query",
  recycle: "Recycle Bin",
}

interface GraphSidePanelProps {
  caseId: string
  graphData?: GraphData
  onEditNode: (node: GraphNode) => void
  onExpandNode: (key: string) => void
  onMergeSelected: () => void
  onCompareSelected: () => void
  onCreateSubgraph: () => void
  onRefreshGraph: () => void
}

/**
 * Collapsed icon rail — rendered outside the ResizablePanelGroup.
 */
export function GraphSidePanelRail() {
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
 * Expanded panel content — rendered inside a ResizablePanel.
 */
export function GraphSidePanelContent({
  caseId,
  graphData,
  onEditNode,
  onExpandNode,
  onMergeSelected,
  onCompareSelected,
  onCreateSubgraph,
  onRefreshGraph,
}: GraphSidePanelProps) {
  const tab = useUIStore((s) => s.graphPanelTab)
  const toolOverlay = useUIStore((s) => s.graphPanelToolOverlay)
  const setCollapsed = useUIStore((s) => s.setGraphPanelCollapsed)
  const setTab = useUIStore((s) => s.setGraphPanelTab)
  const setToolOverlay = useUIStore((s) => s.setGraphPanelToolOverlay)

  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const hasSelection = selectedNodeKeys.size > 0

  const showToolOverlay = toolOverlay !== null

  return (
    <div className="flex h-full flex-col border-l border-border bg-card">
      {/* Tool overlay header */}
      {showToolOverlay ? (
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="text-xs font-semibold">
            {TOOL_LABELS[toolOverlay] ?? toolOverlay}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setToolOverlay(null)}
          >
            <X className="size-3.5" />
          </Button>
        </div>
      ) : (
        /* Tab bar + collapse chevron */
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
      )}

      {/* Panel content */}
      <div className="flex-1 overflow-hidden">
        {showToolOverlay ? (
          <>
            {toolOverlay === "force-controls" && <ForceControlsPanel />}
            {toolOverlay === "analysis" && (
              <GraphAnalysisPanel caseId={caseId} />
            )}
            {toolOverlay === "similar" && (
              <SimilarEntitiesView
                caseId={caseId}
                graphData={graphData}
                onRefresh={onRefreshGraph}
              />
            )}
            {toolOverlay === "cypher" && (
              <CypherPanel caseId={caseId} className="p-4" />
            )}
            {toolOverlay === "recycle" && <RecycleBinPanel caseId={caseId} />}
          </>
        ) : tab === "detail" ? (
          hasSelection ? (
            <NodeDetailSheet
              caseId={caseId}
              graphData={graphData}
              onEditNode={(node) => onEditNode(node)}
              onExpandNode={onExpandNode}
              onMergeSelected={onMergeSelected}
              onCompareSelected={onCompareSelected}
              onCreateSubgraph={onCreateSubgraph}
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
        ) : (
          <ChatSidePanel caseId={caseId} />
        )}
      </div>
    </div>
  )
}
