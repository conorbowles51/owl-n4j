import { useParams } from "react-router-dom"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { useGraphData } from "../hooks/use-graph-data"
import { useGraphStore } from "@/stores/graph.store"
import { GraphCanvas } from "./GraphCanvas"
import { GraphToolbar } from "./GraphToolbar"
import { NodeDetailSheet } from "./NodeDetailSheet"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { Network } from "lucide-react"

export function GraphPage() {
  const { id: caseId } = useParams()
  const { data: graphData, isLoading } = useGraphData(caseId)
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const hasSelection = selectedNodeKeys.size > 0

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!graphData?.nodes.length) {
    return (
      <EmptyState
        icon={Network}
        title="No graph data"
        description="Upload and process evidence to populate the knowledge graph"
      />
    )
  }

  return (
    <div className="flex h-full flex-col">
      <GraphToolbar caseId={caseId!} />
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        <ResizablePanel defaultSize={hasSelection ? 65 : 100} minSize={40}>
          <GraphCanvas data={graphData} caseId={caseId!} />
        </ResizablePanel>
        {hasSelection && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={35} minSize={25} maxSize={50}>
              <NodeDetailSheet caseId={caseId!} />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
    </div>
  )
}
