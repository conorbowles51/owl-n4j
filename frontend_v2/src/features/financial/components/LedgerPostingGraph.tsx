import { lazy, Suspense, useState } from "react"
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
  if (!caseId) return <p>Choose a case to view its posting graph.</p>
  return (
    <section aria-label="Ledger posting graph" className="space-y-4 p-4">
      <h2 className="font-semibold">Payment connections</h2>
      <p>
        See which accounts paid or received money from each name. Select an
        account or name to show its payments below the graph. Open a payment for
        its statement, notes and corrections.
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
  const edges =
    query.data?.edges.filter(
      (e) => !node || e.source === node || e.target === node
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
      {opened && query.isPending && (
        <p role="status">Loading current postings…</p>
      )}
      {query.isError && (
        <p role="alert">Posting graph unavailable. {query.error.message}</p>
      )}
      {query.data && !query.isFetching && !query.isError && (
        <>
          <p>
            {query.data.edges.length} current postings ·{" "}
            {query.data.excluded_rows} excluded
          </p>
          <details>
            <summary className="cursor-pointer">
              How these connections were drawn
            </summary>
            <p>{query.data.limitation}</p>
          </details>
          {!query.data.edges.length ? (
            <p>
              No postings in this scope. This does not prove there were no
              transactions.
            </p>
          ) : (
            <>
              <Suspense fallback={<p role="status">Drawing posting graph…</p>}>
                <Canvas
                  key={query.data.snapshot_sha256}
                  data={query.data}
                  onNode={selectNode}
                  onSource={setSource}
                />
              </Suspense>
              <label>
                Choose an account or name
                <select
                  aria-label="Choose an account or name"
                  className="ml-2 max-w-full rounded border bg-background p-2"
                  value={node}
                  onChange={(e) => selectNode(e.target.value)}
                >
                  <option value="">All payments</option>
                  {query.data.nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.label}
                    </option>
                  ))}
                </select>
              </label>
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
