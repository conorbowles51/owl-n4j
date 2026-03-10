import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { NodeBadge } from "@/components/ui/node-badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { ConnectionsList } from "./ConnectionsList"
import { useNodeDetails } from "../hooks/use-node-details"
import {
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  GitMerge,
  X,
} from "lucide-react"
import { useState } from "react"
import type { NodeDetail, SimilarPair } from "@/types/graph.types"

interface EntityComparisonDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** When comparing from similar-entities scan */
  pair?: SimilarPair | null
  /** When comparing pre-fetched entities (e.g. from graph selection) */
  entity1?: NodeDetail | null
  entity2?: NodeDetail | null
  caseId: string
  onMerge?: (pair: SimilarPair) => void
  onReject?: (pair: SimilarPair) => void
}

export function EntityComparisonDialog({
  open,
  onOpenChange,
  pair,
  entity1: propEntity1,
  entity2: propEntity2,
  caseId,
  onMerge,
  onReject,
}: EntityComparisonDialogProps) {
  const { data: fetchedDetail1, isLoading: loading1 } = useNodeDetails(
    !propEntity1 ? (pair?.key1 ?? null) : null,
    caseId
  )
  const { data: fetchedDetail2, isLoading: loading2 } = useNodeDetails(
    !propEntity2 ? (pair?.key2 ?? null) : null,
    caseId
  )

  const detail1 = propEntity1 ?? fetchedDetail1
  const detail2 = propEntity2 ?? fetchedDetail2
  const isLoading = !propEntity1 && !propEntity2 && (loading1 || loading2)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-7xl w-[90vw] max-h-[85vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <DialogTitle className="text-base">Entity Comparison</DialogTitle>
            {pair && (
              <Badge variant="amber">
                {Math.round(pair.similarity * 100)}% similar
              </Badge>
            )}
          </div>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : !detail1 || !detail2 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            Failed to load entity details
          </div>
        ) : (
          <ScrollArea className="flex-1 min-h-0">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-1">
              <EntityColumn detail={detail1} />
              <EntityColumn detail={detail2} />
            </div>
          </ScrollArea>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {pair && onReject && (
            <Button
              variant="ghost"
              onClick={() => {
                onReject(pair)
                onOpenChange(false)
              }}
            >
              <X className="size-3.5" />
              Dismiss
            </Button>
          )}
          {pair && onMerge && (
            <Button
              variant="default"
              onClick={() => {
                onMerge(pair)
                onOpenChange(false)
              }}
            >
              <GitMerge className="size-3.5" />
              Merge
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------------------------------------------ */
/*  Single entity column                                               */
/* ------------------------------------------------------------------ */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function EntityColumn({ detail }: { detail: any }) {
  const [factsExpanded, setFactsExpanded] = useState(true)
  const [insightsExpanded, setInsightsExpanded] = useState(true)

  const facts = detail.verified_facts ?? []
  const insights = detail.ai_insights ?? []
  const connections = detail.connections ?? []
  const properties = detail.properties ?? {}

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Header */}
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <NodeBadge type={detail.type} />
          <h3 className="truncate text-sm font-semibold">{detail.label}</h3>
        </div>
      </div>

      {/* Summary */}
      {detail.summary && (
        <>
          <div className="px-4 py-3">
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Summary
            </h4>
            <p
              className="text-xs leading-relaxed text-foreground"
              style={{ overflowWrap: "anywhere" }}
            >
              {detail.summary}
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
                {facts.map(
                  (fact: { text: string; status?: string }, i: number) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 rounded-md border border-border/50 p-2"
                    >
                      {fact.status === "verified" ? (
                        <CheckCircle2 className="mt-0.5 size-3 shrink-0 text-green-500" />
                      ) : fact.status === "rejected" ? (
                        <XCircle className="mt-0.5 size-3 shrink-0 text-red-500" />
                      ) : (
                        <div className="mt-0.5 size-3 shrink-0" />
                      )}
                      <p className="text-xs break-words">{fact.text}</p>
                    </div>
                  )
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
                {insights.map(
                  (
                    insight: {
                      text: string
                      confidence?: number
                      verified?: boolean
                      rejected?: boolean
                    },
                    i: number
                  ) => (
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
                        <p className="text-xs flex-1 break-words">
                          {insight.text}
                        </p>
                        {insight.confidence != null && (
                          <Badge
                            variant="slate"
                            className="shrink-0 text-[10px]"
                          >
                            {Math.round(insight.confidence * 100)}%
                          </Badge>
                        )}
                      </div>
                    </div>
                  )
                )}
              </div>
            )}
          </div>
          <Separator />
        </>
      )}

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

      {/* Connections */}
      {connections.length > 0 && (
        <>
          <Separator />
          <div className="px-4 py-3">
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Connections
            </h4>
            <ConnectionsList connections={connections} />
          </div>
        </>
      )}
    </div>
  )
}
