import { lazy, Suspense, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import type { TransferInputs } from "../lib/ledger-transfers"
import { conditionalTransferGraph } from "../lib/conditional-transfer-graph"
import { correctionMoney } from "../lib/correction-contract"
const Canvas = lazy(() => import("./LedgerGraphCanvas"))
export function ConditionalTransferGraph({
  scope,
  pairs,
  onSource,
}: {
  scope: TransferInputs
  pairs: { debit_id: string; credit_id: string }[]
  onSource: (id: string) => void
}) {
  const [opened, setOpened] = useState(false),
    [node, setNode] = useState(""),
    [edge, setEdge] = useState(""),
    [page, setPage] = useState(0)
  const data = useMemo(
    () => conditionalTransferGraph(scope, pairs),
    [scope, pairs]
  )
  const filtered = data.edges.filter(
    (e) =>
      (!node || e.source === node || e.target === node) &&
      (!edge || e.id === edge)
  )
  const pageIndex = Math.min(
    page,
    Math.max(0, Math.ceil(filtered.length / 20) - 1)
  )
  if (!pairs.length) return null
  return (
    <section
      aria-label="Calculated transfer relationships"
      className="space-y-3 rounded border p-3"
    >
      <Button variant="outline" onClick={() => setOpened((v) => !v)}>
        {opened
          ? "Hide transfer relationship graph"
          : "Show transfer relationship graph"}
      </Button>
      {opened && (
        <>
          <h4 className="font-semibold">Calculated transfer relationships</h4>
          <p>
            {data.nodes.length} accounts connected by {data.edges.length}{" "}
            explicitly paired movements. Arrows show the selected transfer
            assumptions, not proof of common ownership or a tracing allocation.
            Unpaired postings are outside this diagram; view them in the posting
            graph and movement totals.
          </p>
          <Suspense fallback={<p>Drawing transfer relationships…</p>}>
            <Canvas
              data={data}
              spreadAccounts
              onNode={(id) => {
                setNode(id)
                setEdge("")
                setPage(0)
              }}
              onSource={(id) => {
                setEdge(id)
                setNode("")
                setPage(0)
              }}
              instructions="Drag to pan; scroll to zoom. Select an account to inspect its connections, or an arrow to inspect both source postings."
            />
          </Suspense>
          <label>
            Inspect connected account
            <select
              aria-label="Inspect connected account"
              className="ml-2 max-w-full border bg-background p-2"
              value={node}
              onChange={(e) => {
                setNode(e.target.value)
                setEdge("")
                setPage(0)
              }}
            >
              <option value="">All connected accounts</option>
              {data.nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.label}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="outline"
            onClick={() => {
              setNode("")
              setEdge("")
              setPage(0)
            }}
          >
            Show all paired movements
          </Button>
          <p>{filtered.length} paired movements match this graph selection.</p>
          {filtered.slice(pageIndex * 20, (pageIndex + 1) * 20).map((e) => (
            <article key={e.id} className="space-y-2 rounded border p-2">
              <p>
                {data.nodes.find((n) => n.id === e.source)?.label} →{" "}
                {data.nodes.find((n) => n.id === e.target)?.label} ·{" "}
                {correctionMoney(e.amount_minor, e.currency)}
              </p>
              <p>
                Outgoing ordering date {e.ordering_date}; incoming ordering date{" "}
                {e.credit_ordering_date}. These remain the source ordering
                dates.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => onSource(e.transaction_id)}
                >
                  Inspect paired outgoing {e.transaction_id.slice(0, 8)}
                </Button>
                <Button variant="outline" onClick={() => onSource(e.credit_id)}>
                  Inspect paired incoming {e.credit_id.slice(0, 8)}
                </Button>
              </div>
            </article>
          ))}
          {filtered.length > 20 && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={!pageIndex}
                onClick={() => setPage(pageIndex - 1)}
              >
                Previous paired movements
              </Button>
              <Button
                variant="outline"
                disabled={(pageIndex + 1) * 20 >= filtered.length}
                onClick={() => setPage(pageIndex + 1)}
              >
                Next paired movements
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
