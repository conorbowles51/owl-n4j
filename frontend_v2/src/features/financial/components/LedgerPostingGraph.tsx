import { lazy, Suspense, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import { postingGraph } from "../lib/ledger-graph"
import { LinkedPayments } from "./LinkedPayments"
import { InvestigationFilters } from "./InvestigationFilters"
import {
  useInvestigationScope,
  useAnalysisPopulation,
} from "../stores/investigation-scope"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
const Canvas = lazy(() => import("./LedgerGraphCanvas"))
export function LedgerPostingGraph({ caseId }: { caseId: string | undefined }) {
  const [params, setParams] = useInvestigationScope(caseId)
  const [population, setPopulation] = useAnalysisPopulation(caseId)
  if (!caseId) return <p>Choose a case to view its payment connections.</p>
  return (
    <section aria-label="Ledger posting graph" className="space-y-4 p-4">
      <h2 className="font-semibold">Payment connections</h2>
      <p>
        See which accounts paid or received money from each name. Select an
        account or name to focus the graph and show its payments below. Open a
        payment for its statement, notes and corrections.
      </p>
      <InvestigationFilters
        key={JSON.stringify(params)}
        caseId={caseId}
        initialParams={params}
        onApply={setParams}
      />
      <label>
        Payments to include
        <select
          aria-label="Payments to include"
          className="ml-2 rounded border bg-background p-2"
          value={population}
          onChange={(e) =>
            setPopulation(e.target.value as "working" | "verified")
          }
        >
          <option value="working">All imported payments</option>
          <option value="verified">Verified payments only</option>
        </select>
      </label>
      <GraphScope
        key={JSON.stringify([caseId, params, population])}
        caseId={caseId}
        params={params}
        population={population}
      />
    </section>
  )
}
function GraphScope({
  caseId,
  params,
  population,
}: {
  caseId: string
  params: LedgerQueryParams
  population: "working" | "verified"
}) {
  const [opened, setOpened] = useState(false),
    [node, setNode] = useState(""),
    [search, setSearch] = useState(""),
    [source, setSource] = useState<string | null>(null)
  const account = params.accountId ?? null,
    start = params.startDate ?? null,
    end = params.endDate ?? null
  const query = useQuery({
    queryKey: [
      "financial-ledger",
      caseId,
      "posting-graph",
      account,
      start,
      end,
      population,
    ],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const search = new URLSearchParams({ population })
      if (account) search.set("account_id", account)
      if (start) search.set("start_date", start)
      if (end) search.set("end_date", end)
      const data = postingGraph.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("ledger-posting-graph", caseId)}&${search}`
        )
      )
      if (
        data.case_id !== caseId ||
        data.account_id !== account ||
        data.start_date !== start ||
        data.end_date !== end ||
        data.population !== population
      )
        throw Error("Graph returned for a different case or filter scope.")
      return data
    },
  })
  const focusedGraph = useMemo(() => {
    if (!query.data) return null
    const edges = query.data.edges.filter(
      (edge) => !node || edge.source === node || edge.target === node
    )
    const connected = new Set(
      edges.flatMap((edge) => [edge.source, edge.target])
    )
    return {
      nodes: query.data.nodes.filter((item) => connected.has(item.id)),
      edges,
    }
  }, [query.data, node])
  const edges = focusedGraph?.edges ?? []
  const matchingNodes =
    query.data?.nodes.filter(
      (item) =>
        item.id === node ||
        item.label.toLowerCase().includes(search.trim().toLowerCase())
    ) ?? []
  const selectNode = (id: string) => {
    setNode(id)
  }
  return (
    <div className="space-y-3">
      <Button
        disabled={query.isFetching}
        onClick={() => {
          if (opened) void query.refetch()
          else setOpened(true)
        }}
      >
        {opened ? "Refresh connections" : "Show connections"}
      </Button>
      {opened && query.isPending && <p role="status">Loading payments…</p>}
      {query.isError && (
        <p role="alert">
          Payment connections are unavailable. {query.error.message}
        </p>
      )}
      {query.data && !query.isFetching && !query.isError && (
        <>
          <p>
            {query.data.edges.length} payments · {query.data.excluded_rows}{" "}
            excluded
          </p>
          <details>
            <summary className="cursor-pointer">
              How these connections were drawn
            </summary>
            <p>{query.data.limitation}</p>
          </details>
          {!query.data.edges.length ? (
            <p>
              No payments match these filters. Change the account or dates, or
              open Statements to check the imported files.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-3">
                <label>
                  Find an account or name
                  <input
                    className="block rounded border bg-background p-2"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Type part of the name"
                  />
                </label>
                <label>
                  Choose an account or name
                  <select
                    aria-label="Choose an account or name"
                    className="block max-w-full rounded border bg-background p-2"
                    value={node}
                    onChange={(event) => selectNode(event.target.value)}
                  >
                    <option value="">All payments</option>
                    {matchingNodes.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                {node && (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setNode("")
                      setSearch("")
                    }}
                  >
                    Show all connections
                  </Button>
                )}
              </div>
              {search.trim() && matchingNodes.length === 0 && (
                <p>
                  No account or name matches this search. Change or clear the
                  text.
                </p>
              )}
              <p role="status">
                Showing {edges.length} of {query.data.edges.length} payments in
                this graph.
              </p>
              <Suspense
                fallback={<p role="status">Drawing payment connections…</p>}
              >
                <Canvas
                  key={query.data.snapshot_sha256 + ":" + node}
                  data={focusedGraph!}
                  onNode={selectNode}
                  onSource={setSource}
                />
              </Suspense>
              <LinkedPayments
                caseId={caseId}
                ids={edges.map((e) => e.transaction_id)}
                label="View selected connections"
              />
            </>
          )}
        </>
      )}
      {source &&
        !query.isError &&
        !query.isFetching &&
        query.data?.edges.some((e) => e.transaction_id === source) && (
          <LedgerSourceDialog
            caseId={caseId}
            transactionId={source}
            onClose={() => setSource(null)}
          />
        )}
    </div>
  )
}
