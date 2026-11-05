import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useRef } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { dayStart } from "@/lib/evidence-time"
import { phoneSettingsQuery } from "@/features/phones/phone-queries"
import { peopleAPI } from "@/features/phones/people.api"
import { scopeHref, scopeWords } from "@/features/phones/ui/scope"
import { useUrlScope } from "@/features/phones/ui/use-phone-scope"
import { useEdgeWindow } from "@/features/graph/stores/edge-window.store"
import { useGraphStore } from "@/stores/graph.store"
import { graphScopeKeys, graphScopeLimits } from "../lib/phone-scope"
import type { GraphEdge, GraphNode } from "@/types/graph.types"

/**
 * Open in Graph (07 4.5): the phone scope carried in the address spotlights its people and phones, and the time
 * window goes to the communication edges. The Graph draws fewer identities than the phones hold and has no filter for
 * direction or kind of record, so what is left out is said here, with its number.
 */
export function GraphPhoneScope({ caseId, nodes, edges }: { caseId: string; nodes: GraphNode[]; edges: GraphEdge[] }) {
  const [params] = useSearchParams()
  const carried = params.get("scope") === "phones"
  return carried ? <Carried caseId={caseId} nodes={nodes} edges={edges} /> : null
}

function Carried({ caseId, nodes, edges }: { caseId: string; nodes: GraphNode[]; edges: GraphEdge[] }) {
  const { scope } = useUrlScope(caseId)
  const settings = useQuery({ ...phoneSettingsQuery(caseId) })
  const phoneIds = scope.phones.map((p) => p.id)
  const inScope = useQuery({
    queryKey: ["phone-scope-identities", caseId, phoneIds.join(",")],
    queryFn: () => peopleAPI.scopeIdentities(caseId, phoneIds),
    enabled: scope.people.length === 0,
    staleTime: 60_000,
  })
  const keys = useMemo(() => graphScopeKeys(scope, nodes, edges), [scope, nodes, edges])
  const addToSubgraph = useGraphStore((s) => s.addToSubgraph)
  const clearSubgraph = useGraphStore((s) => s.clearSubgraph)
  const setSpotlightVisible = useGraphStore((s) => s.setSpotlightVisible)
  const setWindow = useEdgeWindow((s) => s.setWindow)
  const signature = keys.join("|")
  const done = useRef<string | null>(null)
  useEffect(() => {
    if (!nodes.length || !keys.length || done.current === signature) return
    done.current = signature
    clearSubgraph()
    addToSubgraph(keys)
    setSpotlightVisible(true)
  }, [nodes.length, keys, signature, addToSubgraph, clearSubgraph, setSpotlightVisible])
  const zone = settings.data?.effective.name
  const from = scope.window?.from
  const to = scope.window?.to
  useEffect(() => {
    if (!from || !to || !zone) return
    const next = new Date(`${to}T00:00:00Z`)
    next.setUTCDate(next.getUTCDate() + 1)
    setWindow({ from: new Date(dayStart(from, zone)).toISOString(), to: new Date(dayStart(next.toISOString().slice(0, 10), zone) - 1).toISOString() })
    return () => setWindow(null)
  }, [from, to, zone, setWindow])
  const phoneNodes = Math.max(scope.phones.length, keys.filter((k) => k.startsWith("phone-extraction:")).length)
  const held = scope.people.length ? scope.people.length + scope.phones.length : inScope.data ? inScope.data.total + phoneNodes : null
  const limits = graphScopeLimits(scope, keys.length, held)
  return (
    <div role="status" aria-label="Phone scope on the Graph" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border bg-status-review-soft px-4 py-1.5 text-xs">
      <span className="font-medium">Phone scope: {scopeWords(scope)}.</span>
      {limits.map((l) => <span key={l}>{l}</span>)}
      <Link className="underline underline-offset-2" to={scopeHref(`/cases/${encodeURIComponent(caseId)}/conversations`, scope)}>Back to Conversations</Link>
    </div>
  )
}
