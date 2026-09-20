import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"

const statement = z.object({
  id: z.string(),
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
  const [currency, setCurrency] = useState("MXN")
  const [selected, setSelected] = useState<Record<string, Item>>({})
  const [page, setPage] = useState(0)
  const [message, setMessage] = useState("")
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
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      const result = z
        .object({
          case_id: z.string(),
          batch_id: z.string(),
          updated: z.number(),
          currency: z.string(),
        })
        .parse(
          await fetchAPI(`${prefix}/currency?case_id=${caseId}`, {
            method: "POST",
            body: {
              currency,
              statements: Object.values(selected).map((item) => ({
                id: item.id,
                revision: item.currency_revision,
              })),
            },
          })
        )
      if (result.case_id !== caseId || result.batch_id !== batchId)
        throw Error("The response belongs to another batch.")
      return result
    },
    onSuccess: (result) => {
      setMessage(
        `${result.currency} saved for ${result.updated} statements. Amounts were not converted. Your other corrections are kept.`
      )
      setSelected({})
      void query.refetch()
      onSaved()
    },
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
      {message && <p role="status">{message}</p>}
      {open && (
        <>
          <p className="text-sm">
            Find statements by filename, account or date, select them, then
            apply USD, MXN or EUR. This labels the amounts; it does not exchange
            currencies. Already imported statements are not changed.
          </p>
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
                    {["USD", "MXN", "EUR"].map((code) => (
                      <option key={code}>{code}</option>
                    ))}
                  </select>
                </label>
                <Button
                  disabled={!count || save.isPending}
                  onClick={() => {
                    setMessage("")
                    save.mutate()
                  }}
                >
                  {save.isPending
                    ? "Saving currencies…"
                    : `Apply ${currency} to ${count} statements`}
                </Button>
                <Button
                  variant="outline"
                  disabled={save.isPending}
                  onClick={() => {
                    setSelected({})
                    void query.refetch()
                  }}
                >
                  Refresh currency list
                </Button>
              </div>
            </>
          )}
          {save.isError && (
            <p role="alert">{save.error.message} Your selection is kept.</p>
          )}
        </>
      )}
    </section>
  )
}
