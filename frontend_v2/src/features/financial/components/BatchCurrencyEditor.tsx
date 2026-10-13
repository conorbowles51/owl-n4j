import { CurrencyOptions } from "./CurrencyOptions"
import { useEffect, useRef, useState } from "react"
import { useReviewQueue } from "../lib/review-queue"
import { newReviewId } from "../lib/statement-review-id"
import { useMutation, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"

const statement = z.object({
  id: z.string(),
  file_id: z.string().optional(),
  statement_id: z.string().nullish(),
  filename: z.string(),
  account: z.string().optional(),
  period_start: z.string().optional(),
  period_end: z.string().optional(),
  currency: z.string().optional(),
  status: z.string(),
  currency_revision: z.string(),
})
const listing = z.object({
  case_id: z.string(),
  id: z.string(),
  total: z.number(),
  items: z.array(statement),
})
type Item = z.infer<typeof statement>

export function BatchCurrencyEditor({
  caseId,
  batchId,
  onSaved,
}: {
  caseId: string
  batchId: string
  onSaved: () => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [currency, setCurrency] = useState("")
  const chosenCurrency = currency
  const [selected, setSelected] = useState<Record<string, Item>>({})
  const [page, setPage] = useState(0)
  const [message, setMessage] = useState("")
  const attempt = useRef({ fingerprint: "", id: "" })
  const resultRef = useRef<HTMLDivElement>(null)
  const prefix = `/api/financial/statement-import/batches/${batchId}`
  const query = useQuery({
    queryKey: ["batch-currency-selection", caseId, batchId],
    enabled: open,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const items: Item[] = []
      for (let offset = 0; ; offset += 500) {
        const result = listing.parse(
          await fetchAPI(
            `${prefix}?case_id=${caseId}&offset=${offset}&limit=500`
          )
        )
        if (result.case_id !== caseId || result.id !== batchId)
          throw Error("The statements belong to another batch.")
        if (result.total > 10000)
          throw Error(
            "This batch has over 10,000 statement periods. Use the individual currency controls for this batch."
          )
        items.push(
          ...result.items.filter((item) =>
            ["ready", "attention"].includes(item.status)
          )
        )
        if (offset + 500 >= result.total) return items
      }
    },
  })
  // The queue's proposed currency for this batch's statements without one
  // (value + the saved statements it comes from): one click applies it.
  const queue = useReviewQueue(caseId, [], open)
  const proposal = (() => {
    if (!query.data || !queue.data) return null
    const byStatement = new Map<string, { value: string; label: string; ready: boolean }>()
    for (const entry of [...queue.data.items, ...queue.data.filled]) {
      const currencyProposal = entry.proposals?.currency
      if (currencyProposal)
        byStatement.set(`${entry.file_id}:${entry.statement_id ?? ""}`, {
          ...currencyProposal,
          ready: entry.fix_makes_ready,
        })
    }
    const groups = new Map<string, { value: string; label: string; items: Item[]; ready: number }>()
    for (const item of query.data) {
      if (item.currency) continue
      const found = byStatement.get(`${item.file_id}:${item.statement_id ?? ""}`)
      if (!found) continue
      const group = groups.get(found.value) ?? { value: found.value, label: found.label, items: [], ready: 0 }
      group.items.push(item)
      if (found.ready) group.ready += 1
      groups.set(found.value, group)
    }
    return [...groups.values()].sort((a, b) => b.items.length - a.items.length)[0] ?? null
  })()
  const proposalButton = useRef<HTMLButtonElement>(null)
  const focusedProposal = useRef(false)
  useEffect(() => {
    if (!proposal || focusedProposal.current) return
    focusedProposal.current = true
    proposalButton.current?.focus({ preventScroll: true })
  }, [proposal])
  const save = useMutation({
    retry: false,
    mutationFn: async (
      chosen: { currency: string; items: Item[] } | void
    ) => {
      const currency = chosen ? chosen.currency : chosenCurrency
      const statements = (chosen ? chosen.items : Object.values(selected))
        .map((item) => ({ id: item.id, revision: item.currency_revision }))
        .sort((a, b) => a.id.localeCompare(b.id))
      const fingerprint = JSON.stringify({ currency, statements })
      if (attempt.current.fingerprint !== fingerprint)
        attempt.current = { fingerprint, id: newReviewId() }
      const result = z
        .object({
          case_id: z.string(),
          batch_id: z.string(),
          updated: z.number(),
          currency: z.string(),
          already_applied: z.boolean().optional(),
        })
        .parse(
          await fetchAPI(`${prefix}/currency?case_id=${caseId}`, {
            method: "POST",
            body: {
              currency,
              statements,
              request_id: attempt.current.id,
            },
          })
        )
      if (result.case_id !== caseId || result.batch_id !== batchId)
        throw Error("The response belongs to another batch.")
      return result
    },
    onSuccess: (result) => {
      setMessage(
        `${result.already_applied ? "Earlier save confirmed: " : ""}${result.currency} saved for ${result.updated} statements. Amounts were not converted. Your other corrections are kept. The list shows the latest saved values.`
      )
      setSelected({})
      void query.refetch()
      onSaved()
    },
    onSettled: () =>
      requestAnimationFrame(() => {
        resultRef.current?.focus({ preventScroll: true })
        resultRef.current?.scrollIntoView({ block: "nearest" })
      }),
  })
  const matching = (query.data || []).filter((item) =>
    [
      item.filename,
      item.account,
      item.currency,
      item.period_start,
      item.period_end,
    ]
      .join(" ")
      .toLowerCase()
      .includes(search.toLowerCase())
  )
  const count = Object.keys(selected).length
  const hidden = Object.keys(selected).filter(
    (id) => !matching.some((item) => item.id === id)
  ).length
  return (
    <section
      className="rounded border p-3 space-y-3"
      aria-label="Set statement currencies"
    >
      <Button variant="outline" onClick={() => setOpen(!open)}>
        Set currency for selected statements
      </Button>
      <div ref={resultRef} tabIndex={-1}>
        {message && <p role="status">{message}</p>}
        {save.isError && (
          <p role="alert">
            {save.error.message} Your selection is kept. Retry the same save to
            check its result, or refresh the selection before making a different
            change.
          </p>
        )}
      </div>
      {open && (
        <>
          <p className="text-sm">
            Find statements by filename, account or date, select them, then
            choose their currency. This labels the amounts; it does not exchange
            currencies. Already imported statements are not changed.
          </p>
          {proposal && (
            <div
              aria-label="Proposed currency"
              className="flex flex-wrap items-center gap-2 rounded border border-teal-500/50 p-2 text-sm"
            >
              <span>
                Proposed for {proposal.items.length}{" "}
                {proposal.items.length === 1 ? "statement" : "statements"}{" "}
                without a currency: <strong>{proposal.value}</strong> (
                {proposal.label}).{" "}
                {proposal.ready === proposal.items.length
                  ? "Nothing else is missing: they are then ready to save."
                  : `${proposal.ready} of them ${proposal.ready === 1 ? "is" : "are"} then ready to save; the others have more to fix.`}
              </span>
              <Button
                ref={proposalButton}
                size="sm"
                disabled={save.isPending}
                onClick={() => {
                  setMessage("")
                  save.mutate({ currency: proposal.value, items: proposal.items })
                }}
              >
                Use {proposal.value} for {proposal.items.length}{" "}
                {proposal.items.length === 1 ? "statement" : "statements"}
              </Button>
            </div>
          )}
          {query.isPending ? (
            <p role="status">Loading all statement periods…</p>
          ) : query.isError ? (
            <p role="alert">{query.error.message}</p>
          ) : (
            <>
              <label className="block text-sm">
                Find statements for currency
                <input
                  aria-label="Find statements for currency"
                  className="block border rounded bg-background p-2 w-full"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(0)
                  }}
                />
              </label>
              <div className="flex flex-wrap gap-2 items-center">
                <Button
                  variant="outline"
                  disabled={save.isPending || !matching.length}
                  onClick={() =>
                    setSelected((current) => ({
                      ...current,
                      ...Object.fromEntries(
                        matching.map((item) => [item.id, item])
                      ),
                    }))
                  }
                >
                  Select all {matching.length} matching statements
                </Button>
                <Button
                  variant="ghost"
                  disabled={save.isPending || !count}
                  onClick={() => setSelected({})}
                >
                  Clear currency selection
                </Button>
                <span className="text-sm">
                  {count} selected
                  {hidden ? ` · ${hidden} hidden by search` : ""}
                </span>
              </div>
              <fieldset
                disabled={save.isPending}
                className="divide-y max-h-80 overflow-auto"
              >
                {matching.slice(page * 50, page * 50 + 50).map((item) => (
                  <label
                    key={item.id}
                    className="flex gap-2 py-2 text-sm items-start"
                  >
                    <input
                      type="checkbox"
                      aria-label={`Set currency for ${item.filename} ${item.period_start || item.id}`}
                      checked={!!selected[item.id]}
                      onChange={(e) =>
                        setSelected((current) => {
                          const next = { ...current }
                          if (e.target.checked) next[item.id] = item
                          else delete next[item.id]
                          return next
                        })
                      }
                    />
                    <span>
                      <strong>{item.filename}</strong>
                      <br />
                      {[
                        item.account,
                        item.period_start &&
                          `${item.period_start} to ${item.period_end}`,
                        item.currency || "Currency missing",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </label>
                ))}
              </fieldset>
              {!matching.length && <p>No unimported statements match.</p>}
              {matching.length > 50 && (
                <div className="flex gap-2 items-center">
                  <Button
                    variant="outline"
                    disabled={!page}
                    onClick={() => setPage(page - 1)}
                  >
                    Previous currency page
                  </Button>
                  <span>
                    {page * 50 + 1}–{Math.min(page * 50 + 50, matching.length)}{" "}
                    of {matching.length}
                  </span>
                  <Button
                    variant="outline"
                    disabled={(page + 1) * 50 >= matching.length}
                    onClick={() => setPage(page + 1)}
                  >
                    Next currency page
                  </Button>
                </div>
              )}
              <div className="flex flex-wrap gap-2 items-center">
                <label>
                  Currency{" "}
                  <select
                    aria-label="Currency for selected statements"
                    className="border rounded bg-background p-2"
                    value={currency}
                    disabled={save.isPending}
                    onChange={(e) => setCurrency(e.target.value)}
                  >
                    <option value="">Choose currency</option>
                    <CurrencyOptions />
                  </select>
                </label>
                <Button
                  disabled={!count || !currency || save.isPending}
                  onClick={() => {
                    setMessage("")
                    save.mutate(undefined)
                  }}
                >
                  {save.isPending
                    ? "Saving currencies…"
                    : currency
                      ? `Apply ${currency} to ${count} statements`
                      : "Choose currency to apply"}
                </Button>
                <Button
                  variant="outline"
                  disabled={save.isPending}
                  onClick={() => {
                    void query.refetch().then((result) => {
                      if (!result.data || result.isError) return
                      const latest = new Map(
                        result.data.map((item) => [item.id, item])
                      )
                      setSelected((current) =>
                        Object.fromEntries(
                          Object.keys(current).flatMap((id) =>
                            latest.has(id) ? [[id, latest.get(id)!]] : []
                          )
                        )
                      )
                      setMessage(
                        "Selection refreshed with current saved values. Check the selected statements, then apply your change."
                      )
                      save.reset()
                    })
                  }}
                >
                  Refresh currency list
                </Button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  )
}
