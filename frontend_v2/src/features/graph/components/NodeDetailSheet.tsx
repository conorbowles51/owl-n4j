import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { useGraphStore } from "@/stores/graph.store"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useNodeDetails } from "../hooks/use-node-details"
import { NodeBadge } from "@/components/ui/node-badge"
import { ConfidenceBar } from "@/components/ui/confidence-bar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { MarkdownSummary } from "@/components/ui/markdown-summary"
import { ConnectionsList } from "./ConnectionsList"
import { MultiNodePanel } from "./MultiNodePanel"
import {
  Pencil,
  Expand,
  Star,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  Eye,
} from "lucide-react"
import { graphAPI } from "../api"
import { evidenceAPI } from "@/features/evidence/api"
import type { GraphData, GraphNode } from "@/types/graph.types"

interface NodeDetailSheetProps {
  caseId: string
  graphData?: GraphData
  onEditNode?: (node: GraphNode) => void
  onExpandNode?: (key: string) => void
  onMergeSelected?: () => void
  onCompareSelected?: () => void
  onCreateSubgraph?: () => void
}

export function NodeDetailSheet({
  caseId,
  graphData,
  onEditNode,
  onExpandNode,
  onMergeSelected,
  onCompareSelected,
  onCreateSubgraph,
}: NodeDetailSheetProps) {
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const clearSelection = useGraphStore((s) => s.clearSelection)
  const hideNode = useGraphStore((s) => s.hideNode)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const user = useAuthStore((s) => s.user)

  const firstKey = Array.from(selectedNodeKeys)[0] ?? null
  const { data: detail, isLoading } = useNodeDetails(firstKey, caseId)
  const queryClient = useQueryClient()

  const [factsExpanded, setFactsExpanded] = useState(true)
  const [insightsExpanded, setInsightsExpanded] = useState(true)
  const [showAllFacts, setShowAllFacts] = useState(false)
  const [viewerDoc, setViewerDoc] = useState<{ url: string; name: string; page?: number } | null>(null)

  const nodeQueryKey = ["graph", "node", firstKey, caseId]

  const pinFactMutation = useMutation({
    mutationFn: ({ factIndex, pinned }: { factIndex: number; pinned: boolean }) =>
      graphAPI.pinFact(detail!.key, factIndex, pinned, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeQueryKey })
    },
    onError: () => {
      toast.error("Failed to update pin status")
    },
  })

  const verifyInsightMutation = useMutation({
    mutationFn: ({ insightIndex }: { insightIndex: number }) =>
      graphAPI.verifyInsight(detail!.key, insightIndex, user?.username ?? "user", caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeQueryKey })
      toast.success("Insight verified")
    },
    onError: () => {
      toast.error("Failed to verify insight")
    },
  })

  const rejectInsightMutation = useMutation({
    mutationFn: ({ insightIndex }: { insightIndex: number }) =>
      graphAPI.rejectInsight(detail!.key, insightIndex, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeQueryKey })
      toast.success("Insight rejected")
    },
    onError: () => {
      toast.error("Failed to reject insight")
    },
  })

  const openDocument = async (fileName: string, page?: number) => {
    try {
      const result = await evidenceAPI.findByFilename(fileName, caseId)
      if (!result.found || !result.evidence_id) {
        toast.error("Source file not found")
        return
      }
      const url = evidenceAPI.getFileUrl(result.evidence_id)
      setViewerDoc({ url, name: fileName, page })
    } catch {
      toast.error("Failed to load source file")
    }
  }

  // Multi-select panel
  if (selectedNodeKeys.size > 1) {
    const selectedNodes = graphData?.nodes.filter((n) =>
      selectedNodeKeys.has(n.key)
    ) ?? []

    return (
      <div className="flex h-full flex-col border-l border-border bg-card">
        <MultiNodePanel
          nodes={selectedNodes}
          onMerge={selectedNodeKeys.size === 2 ? onMergeSelected : undefined}
          onCompare={selectedNodeKeys.size === 2 ? onCompareSelected : undefined}
          onHideSelected={() => {
            for (const k of selectedNodeKeys) hideNode(k)
            clearSelection()
          }}
          onCreateSubgraph={onCreateSubgraph}
          onClearSelection={clearSelection}
          className="p-4"
        />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center border-l border-border bg-card">
        <LoadingSpinner />
      </div>
    )
  }

  if (!detail) return null

  const facts = detail.verified_facts ?? []
  const insights = detail.ai_insights ?? []
  const connections = detail.connections ?? []
  const sources = detail.sources ?? []
  const properties = detail.properties ?? {}
  const visibleFacts = showAllFacts ? facts : facts.slice(0, 5)

  return (
    <div className="flex h-full flex-col overflow-hidden border-l border-border bg-card">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-border px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <NodeBadge type={detail.type} />
            <h3 className="truncate text-sm font-semibold">{detail.label}</h3>
          </div>
          {detail.confidence !== undefined && (
            <div className="mt-1.5 max-w-[200px]">
              <ConfidenceBar value={detail.confidence} />
            </div>
          )}
        </div>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => {
              const node = graphData?.nodes.find((n) => n.key === detail.key)
              if (node) onEditNode?.(node)
            }}
          >
            <Pencil className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => onExpandNode?.(detail.key)}
          >
            <Expand className="size-3.5" />
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1 min-w-0 overflow-hidden">
        {/* Summary */}
        {detail.summary && (
          <>
            <div className="px-4 py-3">
              <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Summary
              </h4>
              <div className="min-w-0 overflow-hidden" style={{ overflowWrap: "anywhere" }}>
                <MarkdownSummary content={detail.summary} onOpenFile={openDocument} />
              </div>
            </div>
            <Separator />
          </>
        )}

        {/* Notes */}
        {detail.notes && (
          <>
            <div className="px-4 py-3">
              <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Notes
              </h4>
              <p className="text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap break-words">
                {detail.notes}
              </p>
            </div>
            <Separator />
          </>
        )}

        {/* Verified Facts */}
        {facts.length > 0 && (
          <>
            <div className="px-4 py-3">
              <button
                className="mb-2 flex w-full items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                onClick={() => setFactsExpanded(!factsExpanded)}
              >
                {factsExpanded ? (
                  <ChevronDown className="size-3" />
                ) : (
                  <ChevronRight className="size-3" />
                )}
                Verified Facts
                <Badge variant="slate" className="ml-auto text-[10px]">
                  {facts.length}
                </Badge>
              </button>
              {factsExpanded && (
                <div className="space-y-2">
                  {visibleFacts.map((fact, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 rounded-md border border-border/50 p-2"
                    >
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="mt-0.5 shrink-0"
                        onClick={() =>
                          pinFactMutation.mutate({
                            factIndex: i,
                            pinned: !fact.pinned,
                          })
                        }
                      >
                        <Star
                          className={`size-3 ${fact.pinned ? "fill-amber-500 text-amber-500" : "text-muted-foreground"}`}
                        />
                      </Button>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs break-words">{fact.text}</p>
                        {fact.source_doc && (
                          <button
                            className="mt-0.5 text-[10px] text-muted-foreground hover:text-foreground hover:underline transition-colors text-left"
                            onClick={() => openDocument(fact.source_doc!, fact.page)}
                          >
                            Source: {fact.source_doc}
                            {fact.page != null && ` p.${fact.page}`}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                  {facts.length > 5 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs"
                      onClick={() => setShowAllFacts(!showAllFacts)}
                    >
                      {showAllFacts
                        ? "Show less"
                        : `Show ${facts.length - 5} more`}
                    </Button>
                  )}
                </div>
              )}
            </div>
            <Separator />
          </>
        )}

        {/* AI Insights */}
        {insights.length > 0 && (
          <>
            <div className="px-4 py-3">
              <button
                className="mb-2 flex w-full items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                onClick={() => setInsightsExpanded(!insightsExpanded)}
              >
                {insightsExpanded ? (
                  <ChevronDown className="size-3" />
                ) : (
                  <ChevronRight className="size-3" />
                )}
                AI Insights
                <Badge variant="slate" className="ml-auto text-[10px]">
                  {insights.length}
                </Badge>
              </button>
              {insightsExpanded && (
                <div className="space-y-2">
                  {insights.map((insight, i) => (
                    <div
                      key={i}
                      className={`rounded-md border p-2 ${
                        insight.rejected
                          ? "border-red-800/30 bg-red-900/10 opacity-50"
                          : insight.verified
                            ? "border-green-800/30 bg-green-900/10"
                            : "border-border/50"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 min-w-0">
                        <p className="text-xs flex-1 break-words">{insight.text}</p>
                        {insight.confidence != null && (
                          <Badge variant="slate" className="shrink-0 text-[10px]">
                            {Math.round(insight.confidence * 100)}%
                          </Badge>
                        )}
                      </div>
                      {!insight.verified && !insight.rejected && (
                        <div className="mt-1.5 flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-5 text-[10px] text-green-600 dark:text-green-400"
                            onClick={() =>
                              verifyInsightMutation.mutate({ insightIndex: i })
                            }
                          >
                            <CheckCircle2 className="size-3" />
                            Verify
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-5 text-[10px] text-red-600 dark:text-red-400"
                            onClick={() =>
                              rejectInsightMutation.mutate({ insightIndex: i })
                            }
                          >
                            <XCircle className="size-3" />
                            Reject
                          </Button>
                        </div>
                      )}
                      {insight.verified && insight.verified_by && (
                        <p className="mt-1 text-[10px] text-green-600 dark:text-green-400">
                          Verified by {insight.verified_by}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <Separator />
          </>
        )}

        {/* Connections */}
        <div className="px-4 py-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Connections
          </h4>
          <ConnectionsList
            connections={connections}
            onNodeClick={(key) => selectNodes([key])}
          />
        </div>

        <Separator />

        {/* Properties */}
        <div className="px-4 py-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Properties
          </h4>
          <div className="space-y-1.5">
            {Object.entries(properties).map(([key, value]) => (
              <div key={key} className="flex gap-2 text-xs">
                <span className="shrink-0 text-muted-foreground">{key}:</span>
                <span className="truncate font-medium">{String(value)}</span>
              </div>
            ))}
            {Object.keys(properties).length === 0 && (
              <p className="text-xs text-muted-foreground">No properties</p>
            )}
          </div>
        </div>

        <Separator />

        {/* Sources */}
        <div className="px-4 py-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Sources
          </h4>
          {sources.length === 0 ? (
            <p className="text-xs text-muted-foreground">No sources</p>
          ) : (
            <div className="space-y-1.5">
              {sources.map((src) => (
                <button
                  key={src.fileId}
                  className="flex w-full items-center gap-2 text-xs rounded-md px-1.5 py-1 -mx-1.5 hover:bg-muted/50 transition-colors text-left"
                  onClick={() => openDocument(src.fileName)}
                >
                  <Eye className="size-3 shrink-0 text-muted-foreground" />
                  <span className="truncate hover:underline">{src.fileName}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>

      <DocumentViewer
        open={!!viewerDoc}
        onOpenChange={(open) => { if (!open) setViewerDoc(null) }}
        documentUrl={viewerDoc?.url}
        documentName={viewerDoc?.name}
        initialPage={viewerDoc?.page}
      />
    </div>
  )
}
