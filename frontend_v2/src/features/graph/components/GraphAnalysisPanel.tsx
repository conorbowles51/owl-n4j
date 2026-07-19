import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { NodeBadge } from "@/components/ui/node-badge"
import { BarChart3, Network, Route, Crown } from "lucide-react"
import { useGraphStore } from "@/stores/graph.store"
import {
  usePageRank,
  useLouvainCommunities,
  useBetweennessCentrality,
  useShortestPaths,
} from "../hooks/use-graph-analysis"
import type {
  PageRankResult,
  BetweennessResult,
  CommunityResult,
} from "@/types/graph.types"
import type { CaseLayer } from "@/features/significant/types"

interface GraphAnalysisPanelProps {
  caseId: string
  scope: CaseLayer
}

export function GraphAnalysisPanel({ caseId, scope }: GraphAnalysisPanelProps) {
  const { selectedNodeKeys, clearSubgraph, addToSubgraph } = useGraphStore()

  const showInSpotlight = (keys: string[]) => {
    clearSubgraph()
    if (keys.length > 0) addToSubgraph(keys)
  }

  const pageRank = usePageRank(caseId)
  const louvain = useLouvainCommunities(caseId)
  const betweenness = useBetweennessCentrality(caseId)
  const shortestPaths = useShortestPaths(caseId)

  const [prResults, setPrResults] = useState<PageRankResult[]>([])
  const [communities, setCommunities] = useState<CommunityResult[]>([])
  const [btResults, setBtResults] = useState<BetweennessResult[]>([])

  const runPageRank = () => {
    pageRank.mutate({ scope }, {
      onSuccess: (data) => {
        setPrResults(data.results)
        showInSpotlight(data.results.map((r) => r.key))
      },
    })
  }

  const runLouvain = () => {
    louvain.mutate({ scope }, {
      onSuccess: (data) => {
        setCommunities(data.communities)
        const keys: string[] = []
        for (const c of data.communities) {
          for (const n of c.nodes) keys.push(n.key)
        }
        showInSpotlight(keys)
      },
    })
  }

  const runBetweenness = () => {
    betweenness.mutate({ scope }, {
      onSuccess: (data) => {
        setBtResults(data.results)
        showInSpotlight(data.results.map((r) => r.key))
      },
    })
  }

  const runShortestPaths = () => {
    const keys = Array.from(selectedNodeKeys)
    if (keys.length < 2) return
    shortestPaths.mutate({ nodeKeys: keys, scope }, {
      onSuccess: (data) => {
        const pathNodes = new Set<string>()
        for (const p of data.paths) {
          for (const nk of p.nodes) pathNodes.add(nk)
        }
        showInSpotlight(Array.from(pathNodes))
      },
    })
  }

  return (
    <div className="space-y-3 p-4">
      <h3 className="text-sm font-semibold">Graph Analysis</h3>
      {scope === "significant" && (
        <p className="text-xs text-muted-foreground">
          Results use only Significant entities and relationships between them.
        </p>
      )}

      {/* PageRank */}
      <div className="rounded-lg border p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <Crown className="size-3.5 text-amber-500" />
            <span className="text-xs font-medium">PageRank</span>
          </div>
          <Button variant="outline" size="sm" onClick={runPageRank} disabled={pageRank.isPending}>
            {pageRank.isPending ? <LoadingSpinner size="sm" /> : "Run"}
          </Button>
        </div>
        {prResults.length > 0 && (
          <ScrollArea className="max-h-[150px]">
            <div className="space-y-0.5">
              {prResults.map((r, i) => (
                <div key={r.key} className="flex items-center gap-2 rounded px-1.5 py-0.5 hover:bg-muted/50">
                  <span className="w-4 text-right text-[10px] text-muted-foreground">{i + 1}</span>
                  <NodeBadge type={r.type} />
                  <span className="min-w-0 flex-1 truncate text-xs">{r.name}</span>
                  <Badge variant="slate" className="text-[10px]">
                    {r.score.toFixed(4)}
                  </Badge>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </div>

      <Separator />

      {/* Louvain Communities */}
      <div className="rounded-lg border p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <Network className="size-3.5 text-blue-500" />
            <span className="text-xs font-medium">Communities</span>
          </div>
          <Button variant="outline" size="sm" onClick={runLouvain} disabled={louvain.isPending}>
            {louvain.isPending ? <LoadingSpinner size="sm" /> : "Run"}
          </Button>
        </div>
        {communities.length > 0 && (
          <div className="space-y-1">
            {communities.map((c) => (
              <div key={c.community_id} className="flex items-center justify-between rounded px-1.5 py-0.5 hover:bg-muted/50">
                <span className="text-xs">Community {c.community_id}</span>
                <Badge variant="slate" className="text-[10px]">{c.size} nodes</Badge>
              </div>
            ))}
          </div>
        )}
      </div>

      <Separator />

      {/* Betweenness */}
      <div className="rounded-lg border p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="size-3.5 text-green-500" />
            <span className="text-xs font-medium">Betweenness</span>
          </div>
          <Button variant="outline" size="sm" onClick={runBetweenness} disabled={betweenness.isPending}>
            {betweenness.isPending ? <LoadingSpinner size="sm" /> : "Run"}
          </Button>
        </div>
        {btResults.length > 0 && (
          <ScrollArea className="max-h-[150px]">
            <div className="space-y-0.5">
              {btResults.map((r, i) => (
                <div key={r.key} className="flex items-center gap-2 rounded px-1.5 py-0.5 hover:bg-muted/50">
                  <span className="w-4 text-right text-[10px] text-muted-foreground">{i + 1}</span>
                  <NodeBadge type={r.type} />
                  <span className="min-w-0 flex-1 truncate text-xs">{r.name}</span>
                  <Badge variant="slate" className="text-[10px]">
                    {r.score.toFixed(4)}
                  </Badge>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </div>

      <Separator />

      {/* Shortest Paths */}
      <div className="rounded-lg border p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <Route className="size-3.5 text-purple-500" />
            <span className="text-xs font-medium">Shortest Paths</span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={runShortestPaths}
            disabled={shortestPaths.isPending || selectedNodeKeys.size < 2}
          >
            {shortestPaths.isPending ? <LoadingSpinner size="sm" /> : "Find"}
          </Button>
        </div>
        {selectedNodeKeys.size < 2 && (
          <p className="text-[10px] text-muted-foreground">
            Select 2+ nodes to find shortest paths
          </p>
        )}
        {shortestPaths.data && (
          <p className="text-xs text-muted-foreground">
            Found {shortestPaths.data.paths.length} path(s) — shown in spotlight
          </p>
        )}
      </div>
    </div>
  )
}
