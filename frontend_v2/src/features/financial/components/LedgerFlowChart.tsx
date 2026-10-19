import { LinkedPayments } from "./LinkedPayments"
import { flowBarPercent } from "../lib/flow-bar-percent"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { formatLedgerAmount } from "../lib/ledger-format"
const correctionMoney = (value: string, currency: string) =>
  `${formatLedgerAmount(value, currency).text} ${currency}`
export type FlowGroup = {
  id: string
  label: string
  currency: string
  credits_minor: string
  debits_minor: string
  transaction_ids: string[]
}
export function LedgerFlowChart({
  groups,
  title,
  onSource,
  explanation,
  caseId,
  hasCreditCards = false,
}: {
  groups: FlowGroup[]
  title: string
  onSource: (id: string) => void
  explanation?: string
  caseId?: string
  hasCreditCards?: boolean
}) {
  if (!groups.length) return null
  return (
    <Chart
      key={JSON.stringify(groups)}
      groups={groups}
      title={title}
      onSource={onSource}
      explanation={explanation}
      caseId={caseId}
      hasCreditCards={hasCreditCards}
    />
  )
}
function Chart({
  groups,
  title,
  onSource,
  explanation,
  caseId,
  hasCreditCards = false,
}: {
  groups: FlowGroup[]
  title: string
  onSource: (id: string) => void
  explanation?: string
  caseId?: string
  hasCreditCards?: boolean
}) {
  const currencies = [...new Set(groups.map((g) => g.currency))]
  const [currency, setCurrency] = useState(currencies[0]),
    [chosen, setChosen] = useState<string[] | null>(null),
    [page, setPage] = useState(0),
    [inspecting, setInspecting] = useState<string | null>(null),
    [sourcePage, setSourcePage] = useState(0),
    [inspectTotals, setInspectTotals] = useState(false)
  const scoped = groups.filter((g) => g.currency === currency),
    selected = scoped.filter((g) => chosen === null || chosen.includes(g.id))
  const credits = selected.reduce((n, g) => n + BigInt(g.credits_minor), 0n),
    debits = selected.reduce((n, g) => n + BigInt(g.debits_minor), 0n)
  const maximum = scoped.reduce(
    (n, g) =>
      [n, BigInt(g.credits_minor), BigInt(g.debits_minor)].reduce((a, b) =>
        a > b ? a : b
      ),
    0n
  )
  const inspected = inspectTotals
    ? {
        label: "Selected chart totals",
        transaction_ids: [
          ...new Set(selected.flatMap((g) => g.transaction_ids)),
        ],
      }
    : scoped.find((g) => g.id === inspecting)
  const sourceIndex = Math.min(
    sourcePage,
    Math.max(0, Math.ceil((inspected?.transaction_ids.length ?? 0) / 25) - 1)
  )
  return (
    <section
      aria-label={title}
      className="space-y-4 rounded-lg border bg-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold">{title}</h3>
        <label>
          Chart currency{" "}
          <select
            aria-label={`${title} currency`}
            value={currency}
            className="border bg-background p-2"
            onChange={(e) => {
              setCurrency(e.target.value)
              setChosen(null)
              setPage(0)
              setInspecting(null)
              setInspectTotals(false)
            }}
          >
            {currencies.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-sm text-muted-foreground">
        {hasCreditCards
          ? "Debits are shown on the left and credits on the right. Select items, then open their payments."
          : (explanation ??
            "Money out is shown on the left and money in on the right. Select items to compare their totals, then open the payments behind them.")}
      </p>
      {hasCreditCards && (
        <p className="text-sm">
          Includes credit-card entries. Card debits increase the amount owed;
          credits reduce it. These totals do not measure cash moving between
          bank accounts.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Chart selection changes this comparison. Ledger downloads use the
        applied account and date filters.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded border p-3">
          <p className="text-xs text-muted-foreground">
            {hasCreditCards ? "Selected credits" : "Selected money in"}
          </p>
          <p className="font-semibold text-emerald-500">
            {correctionMoney(credits.toString(), currency)}
          </p>
        </div>
        <div className="rounded border p-3">
          <p className="text-xs text-muted-foreground">
            {hasCreditCards ? "Selected debits" : "Selected money out"}
          </p>
          <p className="font-semibold text-rose-400">
            {correctionMoney(debits.toString(), currency)}
          </p>
        </div>
        <div className="rounded border p-3">
          <p className="text-xs text-muted-foreground">Selected difference</p>
          <p className="font-semibold">
            {correctionMoney((credits - debits).toString(), currency)}
          </p>
        </div>
      </div>
      <p className="text-sm">
        {selected.length} of {scoped.length} groups selected ·{" "}
        {selected.reduce((n, g) => n + g.transaction_ids.length, 0)} payments.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={!selected.length}
          onClick={() => {
            setInspectTotals(true)
            setInspecting(null)
            setSourcePage(0)
          }}
        >
          View payments in selected totals
        </Button>
        <Button variant="outline" onClick={() => setChosen(null)}>
          Select all
        </Button>
        <Button variant="outline" onClick={() => setChosen([])}>
          Clear selection
        </Button>
      </div>
      <div className="space-y-4">
        {scoped.slice(page * 20, page * 20 + 20).map((g) => (
          <div
            key={g.id}
            className={
              chosen === null || chosen.includes(g.id) ? "" : "opacity-50"
            }
          >
            <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
              <label className="flex min-w-0 items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={`Include chart group ${g.label}`}
                  checked={chosen === null || chosen.includes(g.id)}
                  onChange={(e) =>
                    setChosen((old) => {
                      const ids = old ?? scoped.map((v) => v.id)
                      return e.target.checked
                        ? [...ids, g.id]
                        : ids.filter((id) => id !== g.id)
                    })
                  }
                />
                <span className="break-words">{g.label}</span>
              </label>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setInspecting(g.id)
                  setInspectTotals(false)
                  setSourcePage(0)
                }}
              >
                View {g.label} payments
              </Button>
            </div>
            <div className="grid grid-cols-2" aria-hidden="true">
              <div className="flex h-4 justify-end border-r border-muted-foreground/60">
                <div
                  className="h-full rounded-l bg-rose-400"
                  style={{
                    width: `${flowBarPercent(g.debits_minor, maximum)}%`,
                  }}
                />
              </div>
              <div className="h-4">
                <div
                  className="h-full rounded-r bg-emerald-500"
                  style={{
                    width: `${flowBarPercent(g.credits_minor, maximum)}%`,
                  }}
                />
              </div>
            </div>
            <div className="mt-1 flex justify-between gap-3 text-xs">
              <span>
                {hasCreditCards ? "Debit" : "Out"}{" "}
                {correctionMoney(g.debits_minor, currency)}
              </span>
              <span>
                {hasCreditCards ? "Credit" : "In"}{" "}
                {correctionMoney(g.credits_minor, currency)}
              </span>
            </div>
          </div>
        ))}
      </div>
      {scoped.length > 20 && (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            disabled={!page}
            onClick={() => setPage(page - 1)}
          >
            Previous chart groups
          </Button>
          <span>
            {page * 20 + 1}–{Math.min((page + 1) * 20, scoped.length)} of{" "}
            {scoped.length}
          </span>
          <Button
            variant="outline"
            disabled={(page + 1) * 20 >= scoped.length}
            onClick={() => setPage(page + 1)}
          >
            Next chart groups
          </Button>
        </div>
      )}
      {inspected && (
        <section
          aria-label="Chart contributing sources"
          className="space-y-2 rounded border p-3"
        >
          <h4 className="font-semibold">
            {inspected.label} · {inspected.transaction_ids.length} postings
          </h4>
          <p>
            {inspectTotals
              ? "These sources cover the selected incoming and outgoing groups together; their difference produces the selected net. "
              : ""}
            Open a payment to check its original statement or add a note.
          </p>
          {caseId ? (
            <LinkedPayments caseId={caseId} ids={inspected.transaction_ids} />
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                {inspected.transaction_ids
                  .slice(sourceIndex * 25, sourceIndex * 25 + 25)
                  .map((id, i) => (
                    <Button
                      key={id}
                      variant="outline"
                      onClick={() => onSource(id)}
                    >
                      Open chart posting {sourceIndex * 25 + i + 1}
                    </Button>
                  ))}
              </div>
              {inspected.transaction_ids.length > 25 && (
                <div className="flex gap-2">
                  <Button
                    disabled={!sourceIndex}
                    onClick={() => setSourcePage(sourceIndex - 1)}
                  >
                    Previous chart sources
                  </Button>
                  <Button
                    disabled={
                      (sourceIndex + 1) * 25 >= inspected.transaction_ids.length
                    }
                    onClick={() => setSourcePage(sourceIndex + 1)}
                  >
                    Next chart sources
                  </Button>
                </div>
              )}
            </>
          )}
        </section>
      )}
    </section>
  )
}
