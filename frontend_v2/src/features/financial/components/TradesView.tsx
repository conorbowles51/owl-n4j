import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  SECURITY_PAGE_SIZE,
  useSecurityRow,
  useSecurityRowAction,
  useSecurityRows,
  type SecurityRow,
  type SecurityRowKind,
} from "../hooks/use-security-rows"
import { formatLedgerAmount } from "../lib/ledger-format"

// Trades and holdings read from the case's brokerage statements. Each row cites its printed line; a trade
// links to its cash leg in the money ledger. A model's reading says so until a person confirms it; a corrected
// value is shown with the value as read beside it.

const SIDE_LABEL: Record<string, string> = {
  buy: "Buy",
  sell: "Sell",
  repo: "Repo",
  repo_start: "Repo start",
  repo_maturity: "Repo maturity",
  other: "Other",
}

const CORRECTABLE: [string, string][] = [
  ["quantity", "Quantity"],
  ["price", "Price"],
  ["instrument", "Instrument"],
  ["trade_date", "Trade date"],
  ["settlement_date", "Settlement date"],
  ["isin", "ISIN"],
  ["net_minor", "Net (minor units)"],
]

function formatMinor(value: number | null | undefined, currency?: string | null) {
  if (value === null || value === undefined) return "–"
  if (!currency) return `${value} (minor units, no currency)`
  const amount = formatLedgerAmount(value, currency)
  return amount.scaled ? `${amount.text} ${amount.currency}` : `${amount.text} ${amount.currency} (minor units)`
}

function formatQuantity(value: string | null) {
  if (value === null || value === undefined || value === "") return null
  const [whole, fraction] = value.split(".")
  return Number(whole).toLocaleString("en-US") + (fraction ? `.${fraction}` : "")
}

function Corrected({ row, field, children }: { row: SecurityRow; field: string; children: React.ReactNode }) {
  const correction = row.corrections[field]
  if (!correction) return <>{children}</>
  return (
    <span>
      {children}
      <span className="block text-xs text-muted-foreground">
        read {String(correction.read ?? "nothing")} · corrected by {correction.by?.name ?? "a person"}
      </span>
    </span>
  )
}

function OriginBadge({ row }: { row: SecurityRow }) {
  const tone =
    row.origin.kind === "model"
      ? "border-amber-500/60 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100"
      : row.origin.kind === "confirmed"
        ? "border-emerald-600/50 text-emerald-800 dark:text-emerald-200"
        : "border-border text-muted-foreground"
  return <span className={`inline-block rounded border px-1.5 py-0.5 text-xs ${tone}`}>{row.origin.text}</span>
}

function RowActions({ caseId, row }: { caseId: string; row: SecurityRow }) {
  const action = useSecurityRowAction(caseId)
  const [open, setOpen] = useState(false)
  const [field, setField] = useState("quantity")
  const [value, setValue] = useState("")
  const [reason, setReason] = useState("")
  const error = action.error instanceof Error ? action.error.message : null
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap gap-1">
        {row.origin.kind !== "confirmed" && (
          <Button
            size="sm"
            variant="outline"
            disabled={action.isPending}
            onClick={() => action.mutate({ id: row.id, action: "confirm", body: { reason: "Checked against the printed line." } })}
          >
            Confirm
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          Correct
        </Button>
      </div>
      {open && (
        <form
          className="space-y-1 rounded border p-2"
          aria-label={`Correct ${row.instrument}`}
          onSubmit={(event) => {
            event.preventDefault()
            action.mutate(
              { id: row.id, action: "correct", body: { field, value, reason } },
              { onSuccess: () => setOpen(false) }
            )
          }}
        >
          <label className="block text-xs">
            Value
            <select
              className="ml-1 rounded border bg-background px-1 text-xs"
              value={field}
              onChange={(event) => setField(event.target.value)}
            >
              {CORRECTABLE.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <Input aria-label="Corrected value" value={value} onChange={(event) => setValue(event.target.value)} />
          <Input
            aria-label="Why"
            placeholder="Why (as printed on page …)"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <Button size="sm" type="submit" disabled={!reason.trim() || action.isPending}>
            Save correction
          </Button>
        </form>
      )}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}

export function TradesView({ caseId }: { caseId: string }) {
  const [params] = useSearchParams()
  const focus = params.get("security")
  const [kind, setKind] = useState<SecurityRowKind>("trade")
  const [instrument, setInstrument] = useState("")
  const [page, setPage] = useState(1)
  const { canEdit } = useFinancialAccess()
  const query = useSecurityRows(caseId, kind, instrument, page)
  const cited = useSecurityRow(caseId, focus)
  const citedKind = cited.data?.row_kind
  useEffect(() => {
    // A citation opens the list of its own kind (a holding's link shows Holdings).
    if (citedKind) {
      setKind(citedKind)
      setPage(1)
    }
  }, [citedKind])
  const data = query.data
  const hiddenStatements = data?.not_shown_statement_not_in_ledger ?? 0
  const first = data ? (data.page - 1) * data.page_size + 1 : 0
  const last = data ? first + data.returned - 1 : 0
  const noun = kind === "trade" ? "trades" : "holdings"

  return (
    <section aria-label="Trades and holdings" className="space-y-3 p-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex gap-1" role="group" aria-label="Show">
          {(["trade", "holding"] as const).map((option) => (
            <Button
              key={option}
              size="sm"
              variant={kind === option ? "primary" : "outline"}
              aria-pressed={kind === option}
              onClick={() => {
                setKind(option)
                setPage(1)
              }}
            >
              {option === "trade" ? "Trades" : "Holdings"}
            </Button>
          ))}
        </div>
        <label className="text-sm">
          Instrument
          <Input
            className="mt-1 w-56"
            placeholder="e.g. BONDESF or CETES"
            value={instrument}
            onChange={(event) => {
              setInstrument(event.target.value)
              setPage(1)
            }}
          />
        </label>
      </div>
      <p className="text-sm text-muted-foreground">
        Read from brokerage statements, each from its printed line. The trade date is the printed operation day:
        these statements print no time of execution. A trade's cash moves in the money ledger on its settlement date.
      </p>

      {focus && cited.data && (
        <div role="region" aria-label="Cited row" className="rounded border border-amber-400 p-3 text-sm">
          <p className="font-medium">
            Cited {cited.data.row_kind}: {cited.data.instrument}
            {cited.data.trade_date ? ` · traded ${cited.data.trade_date}` : ""}
            {cited.data.as_of_date ? ` · held at ${cited.data.as_of_date}` : ""}
            {cited.data.quantity ? ` · ${formatQuantity(cited.data.quantity)} units` : ""}
            {cited.data.net_minor !== null
              ? ` · ${formatMinor(cited.data.net_minor, cited.data.currency)}`
              : cited.data.market_value_minor !== null
                ? ` · ${formatMinor(cited.data.market_value_minor, cited.data.currency)}`
                : ""}
          </p>
          <p className="text-muted-foreground">
            {cited.data.origin.text} ·{" "}
            <a className="underline" href={`/api/evidence/${encodeURIComponent(cited.data.evidence_file_id)}/file${cited.data.citation.page ? `#page=${cited.data.citation.page}` : ""}`}>
              {cited.data.file ?? "source file"}
              {cited.data.citation.page ? `, page ${cited.data.citation.page}` : ""}
            </a>
          </p>
          {cited.data.citation.printed_text && <p className="text-muted-foreground">Printed: {cited.data.citation.printed_text}</p>}
          {!cited.data.counts && <p className="font-medium">Not counted: {cited.data.not_counted_because}</p>}
        </div>
      )}
      {focus && cited.error && (
        <p role="alert" className="text-sm">
          The cited row could not be opened: {cited.error instanceof Error ? cited.error.message : "error"}.
        </p>
      )}
      {query.isLoading && (
        <div role="status" className="rounded border p-3 text-sm">
          Reading the case's {noun} from its brokerage statements…
        </div>
      )}
      {query.error && (
        <p role="alert" className="text-sm">
          The {noun} could not be read: {query.error instanceof Error ? query.error.message : "error"}.{" "}
          <button className="underline" onClick={() => void query.refetch()}>
            Retry
          </button>
        </p>
      )}
      {data && data.total === 0 && (
        <p className="rounded border p-3 text-sm">
          {instrument.trim()
            ? `No ${noun} match “${instrument.trim()}”.`
            : `No ${noun} are in the money ledger for this case. They are read from the brokerage statements in the ledger, and a statement removed from Financial takes its ${noun} with it.`}
          {data.not_shown_cash_leg_not_in_ledger > 0 &&
            ` ${data.not_shown_cash_leg_not_in_ledger} trade(s) are not shown because their cash line is no longer in the money ledger.`}
          {hiddenStatements > 0 &&
            ` ${hiddenStatements} ${noun} are not shown because their statement is no longer in the ledger.`}
        </p>
      )}
      {data && data.total > 0 && (
        <>
          <p className="text-sm" aria-live="polite">
            Showing {first}–{last} of {data.total} {noun}
            {data.not_shown_cash_leg_not_in_ledger > 0 &&
              ` · ${data.not_shown_cash_leg_not_in_ledger} not shown: their cash line is no longer in the money ledger`}
            {hiddenStatements > 0 && ` · ${hiddenStatements} not shown: their statement is no longer in the ledger`}
          </p>
          <div className="overflow-x-auto rounded border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs">
                {kind === "trade" ? (
                  <tr>
                    <th className="p-2">Trade date</th>
                    <th className="p-2">Settled</th>
                    <th className="p-2">Operation</th>
                    <th className="p-2">Instrument</th>
                    <th className="p-2 text-right">Quantity</th>
                    <th className="p-2 text-right">Price</th>
                    <th className="p-2 text-right">Net</th>
                    <th className="p-2">Account</th>
                    <th className="p-2">Reading</th>
                    <th className="p-2">Source</th>
                    {canEdit && <th className="p-2">Review</th>}
                  </tr>
                ) : (
                  <tr>
                    <th className="p-2">As of</th>
                    <th className="p-2">Kind</th>
                    <th className="p-2">Instrument</th>
                    <th className="p-2 text-right">Quantity</th>
                    <th className="p-2 text-right">Price</th>
                    <th className="p-2 text-right">Value</th>
                    <th className="p-2">Account</th>
                    <th className="p-2">Reading</th>
                    <th className="p-2">Source</th>
                    {canEdit && <th className="p-2">Review</th>}
                  </tr>
                )}
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr
                    key={row.id}
                    data-testid="security-row"
                    className={`border-t align-top ${focus === row.id ? "bg-amber-50 dark:bg-amber-950/40" : ""}`}
                  >
                    {kind === "trade" ? (
                      <>
                        <td className="p-2 whitespace-nowrap">
                          <Corrected row={row} field="trade_date">
                            {row.trade_date ?? "not read"}
                          </Corrected>
                        </td>
                        <td className="p-2 whitespace-nowrap">{row.settlement_date ?? "–"}</td>
                        <td className="p-2">
                          {SIDE_LABEL[row.side ?? "other"]}
                          <span className="block text-xs text-muted-foreground">{row.operation}</span>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="p-2 whitespace-nowrap">{row.as_of_date ?? "–"}</td>
                        <td className="p-2">{row.holding_kind === "repo" ? "Open repo" : "Position"}</td>
                      </>
                    )}
                    <td className="p-2 font-mono text-xs">
                      <Corrected row={row} field="instrument">
                        {row.instrument}
                      </Corrected>
                      {row.isin && <span className="block">ISIN {row.isin}</span>}
                    </td>
                    <td className="p-2 text-right tabular-nums">
                      <Corrected row={row} field="quantity">
                        {formatQuantity(row.quantity) ?? <span className="text-muted-foreground">not read</span>}
                      </Corrected>
                    </td>
                    <td className="p-2 text-right tabular-nums">
                      <Corrected row={row} field="price">
                        {row.price ?? "–"}
                      </Corrected>
                    </td>
                    <td className="p-2 text-right tabular-nums whitespace-nowrap">
                      {kind === "trade" ? (
                        <Corrected row={row} field="net_minor">
                          {(row.direction ?? row.citation.cash_leg?.direction) === "debit" && row.net_minor !== null ? "−" : ""}
                          {formatMinor(row.net_minor, row.currency)}
                        </Corrected>
                      ) : (
                        formatMinor(row.market_value_minor, row.currency)
                      )}
                    </td>
                    <td className="p-2 text-xs">{row.account ?? "–"}</td>
                    <td className="p-2">
                      <OriginBadge row={row} />
                      <span className="block text-xs text-muted-foreground">{row.proof_class.toUpperCase()}</span>
                    </td>
                    <td className="p-2 text-xs">
                      <a
                        className="underline"
                        href={`/api/evidence/${encodeURIComponent(row.citation.file_id)}/file${row.citation.page ? `#page=${row.citation.page}` : ""}`}
                        target="_blank"
                        rel="noreferrer"
                        title={row.citation.printed_text ?? undefined}
                      >
                        {row.file ?? "Statement"}
                        {row.citation.page ? `, page ${row.citation.page}` : ""}
                      </a>
                      {row.cash_transaction_id && (
                        <a
                          className="block underline"
                          href={`/cases/${encodeURIComponent(caseId)}/financial?view=transactions&payment=${encodeURIComponent(row.cash_transaction_id)}`}
                        >
                          Cash line
                        </a>
                      )}
                      {row.unread && (
                        <span className="block font-medium">
                          Line not read ({row.unread}). Printed: {row.citation.printed_text}
                        </span>
                      )}
                      {row.not_read.length > 0 && (
                        <span className="block text-muted-foreground">Not read: {row.not_read.join(", ")}</span>
                      )}
                    </td>
                    {canEdit && (
                      <td className="p-2">
                        <RowActions caseId={caseId} row={row} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button size="sm" variant="outline" disabled={!data.next_page} onClick={() => setPage((p) => p + 1)}>
              Next {SECURITY_PAGE_SIZE}
            </Button>
          </div>
        </>
      )}
    </section>
  )
}
