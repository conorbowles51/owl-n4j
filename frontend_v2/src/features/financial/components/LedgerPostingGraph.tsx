import { lazy, Suspense, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import { postingGraph } from "../lib/ledger-graph"
import { correctionMoney } from "../lib/correction-contract"
import { LedgerFilters } from "./LedgerFilters"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
const Canvas = lazy(() => import("./LedgerGraphCanvas"))
export function LedgerPostingGraph({ caseId }: { caseId: string | undefined }) {
  const [params, setParams] = useState<LedgerQueryParams>({}),
    [population, setPopulation] = useState<"working" | "verified">("working")
  if (!caseId) return <p>Choose a case to view its posting graph.</p>
  return (
    <section aria-label="Ledger posting graph" className="space-y-4 p-4">
      <h2 className="font-semibold">Graph of current ledger postings</h2>
      <p>
        Accounts connect to the counterparty labels recorded on their rows.
        Label groups are not resolved people or organisations. Each arrow
        represents one posting, with its original source available.
      </p>
      <LedgerFilters caseId={caseId} onApply={setParams} />
      <label>
        Graph population
        <select
          aria-label="Graph population"
          className="ml-2 rounded border bg-background p-2"
          value={population}
          onChange={(e) =>
            setPopulation(e.target.value as "working" | "verified")
          }
        >
          <option value="working">Working readings, including P3</option>
          <option value="verified">Verified only</option>
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
    [source, setSource] = useState<string | null>(null),
    [page, setPage] = useState(0)
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
  const pageIndex = Math.min(
    page,
    Math.max(0, Math.ceil(edges.length / 25) - 1)
  )
  const selectNode = (id: string) => {
    setNode(id)
    setPage(0)
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
        {opened ? "Refresh posting graph" : "Load posting graph"}
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
          <p className="text-muted-foreground">{query.data.limitation}</p>
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
                Inspect graph node
                <select
                  aria-label="Inspect graph node"
                  className="ml-2 max-w-full rounded border bg-background p-2"
                  value={node}
                  onChange={(e) => selectNode(e.target.value)}
                >
                  <option value="">All postings</option>
                  {query.data.nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.label}
                    </option>
                  ))}
                </select>
              </label>
              <ul className="space-y-2">
                {edges.slice(pageIndex * 25, pageIndex * 25 + 25).map((e) => (
                  <li
                    key={e.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded border p-2"
                  >
                    <span>
                      {e.ordering_date} · {e.description ?? "No description"} ·{" "}
                      {e.direction} ·{" "}
                      {correctionMoney(e.amount_minor, e.currency)}
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setSource(e.transaction_id)}
                    >
                      Open posting source {e.id.slice(0, 8)}
                    </Button>
                  </li>
                ))}
              </ul>
              {edges.length > 25 && (
                <div className="flex gap-2">
                  <Button
                    disabled={!pageIndex}
                    onClick={() => setPage(pageIndex - 1)}
                  >
                    Previous graph postings
                  </Button>
                  <Button
                    disabled={(pageIndex + 1) * 25 >= edges.length}
                    onClick={() => setPage(pageIndex + 1)}
                  >
                    Next graph postings
                  </Button>
                </div>
              )}
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
