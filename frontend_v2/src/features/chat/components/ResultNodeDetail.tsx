import { X, ExternalLink } from "lucide-react"
import { useNavigate, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { getNodeColor, type EntityType } from "@/lib/theme"
import type { ResultGraphNode } from "../types"

interface ResultNodeDetailProps {
  node: ResultGraphNode
  onClose: () => void
}

export function ResultNodeDetail({ node, onClose }: ResultNodeDetailProps) {
  const navigate = useNavigate()
  const { id: caseId } = useParams()

  const handleViewInGraph = () => {
    navigate(`/cases/${caseId}/graph?select=${node.key}`)
  }

  const color = getNodeColor(node.type)
  const confidencePercent = Math.round(node.confidence * 100)

  return (
    <div className="border-t border-border bg-background p-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className="size-3 shrink-0 rounded-full"
            style={{ backgroundColor: color }}
          />
          <span className="truncate text-sm font-medium">{node.name}</span>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose}>
          <X className="size-3" />
        </Button>
      </div>

      {/* Type + confidence */}
      <div className="mt-2 flex items-center gap-2">
        <NodeBadge type={node.type as EntityType} />
        <Badge variant="outline" className="text-[10px]">
          {node.type}
        </Badge>
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-500"
              style={{ width: `${confidencePercent}%` }}
            />
          </div>
          <span>{confidencePercent}%</span>
        </div>
      </div>

      {/* Summary */}
      {node.summary && (
        <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
          {node.summary}
        </p>
      )}

      {/* Relevance */}
      {node.relevance_reason && (
        <p className="mt-1.5 text-[10px] text-muted-foreground/70 italic">
          {node.relevance_reason}
        </p>
      )}

      {/* Badges */}
      <div className="mt-2 flex flex-wrap gap-1">
        {node.mentioned && (
          <Badge variant="amber" className="text-[10px]">
            Mentioned in answer
          </Badge>
        )}
        {node.relevance_source && (
          <Badge variant="outline" className="text-[10px]">
            via {node.relevance_source}
          </Badge>
        )}
      </div>

      {/* Actions */}
      <div className="mt-3">
        <Button
          variant="outline"
          size="sm"
          className="w-full text-xs"
          onClick={handleViewInGraph}
        >
          <ExternalLink className="size-3" />
          View in Main Graph
        </Button>
      </div>
    </div>
  )
}
