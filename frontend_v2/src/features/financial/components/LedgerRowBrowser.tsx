import { correctionMinor } from "../lib/correction-contract"
import { LedgerExportButton } from "./LedgerExportButton"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { useState, type ComponentProps } from "react"
import { Button } from "@/components/ui/button"
import { LedgerTable } from "./LedgerTable"
import type { LedgerTransaction } from "../api"
function exactAmount(row: LedgerTransaction) {
  const value = row.amount_minor
  if (typeof value === "number" && !Number.isSafeInteger(value)) return null
  const text = String(value)
  return /^(0|[1-9][0-9]{0,18})$/.test(text) ? BigInt(text) : null
}
export function LedgerRowBrowser({
  transactions,
  exportContext,
  ...actions
}: ComponentProps<typeof LedgerTable> & {
  exportContext?: { caseId: string; params: LedgerQueryParams }
}) {
  const [search, setSearch] = useState(""),
    [currency, setCurrency] = useState(""),
    [minimum, setMinimum] = useState(""),
    [maximum, setMaximum] = useState(""),
    [direction, setDirection] = useState(""),
    [proof, setProof] = useState(""),
    [sort, setSort] = useState("ledger"),
    [page, setPage] = useState(0)
  const query = search.trim().toLowerCase()
  const minMinor = minimum.trim() ? correctionMinor(minimum, currency) : ""
  const maxMinor = maximum.trim() ? correctionMinor(maximum, currency) : ""
  const invalidRange =
    minMinor === null ||
    maxMinor === null ||
    (!!minMinor && !!maxMinor && BigInt(minMinor) > BigInt(maxMinor))
  const rows = transactions.filter(
    (row) =>
      !invalidRange &&
      (!minMinor ||
        (exactAmount(row) !== null && exactAmount(row)! >= BigInt(minMinor))) &&
      (!maxMinor ||
        (exactAmount(row) !== null && exactAmount(row)! <= BigInt(maxMinor))) &&
      (!currency || row.currency === currency) &&
      (!direction || row.direction === direction) &&
      (!proof || row.proof_class === proof) &&
      (!query ||
        [
          row.description,
          row.counterparty_raw,
          row.bank_reference,
          row.ref_id,
          row.key,
          row.account_id,
          row.source_document_id,
        ].some(
          (value) =>
            typeof value === "string" && value.toLowerCase().includes(query)
        ))
  )
  const amountAllowed = new Set(rows.map((row) => row.currency)).size <= 1
  if (sort === "newest")
    rows.sort((a, b) => b.ordering_date.localeCompare(a.ordering_date))
  if (sort === "oldest")
    rows.sort((a, b) => a.ordering_date.localeCompare(b.ordering_date))
  if (sort.startsWith("amount") && amountAllowed)
    rows.sort((a, b) => {
      const left = exactAmount(a),
        right = exactAmount(b)
      if (left === null) return right === null ? 0 : 1
      if (right === null) return -1
      const order = left < right ? -1 : left > right ? 1 : 0
      return sort === "amount-desc" ? -order : order
    })
  const index = Math.min(page, Math.max(0, Math.ceil(rows.length / 50) - 1))
  return (
    <section aria-label="Browse ledger rows" className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label>
          Find in loaded rows
          <input
            aria-label="Find in loaded rows"
            className="block rounded border bg-background p-2"
            maxLength={256}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(0)
            }}
            placeholder="Description, name or reference"
          />
        </label>
        <label>
          Table currency
          <select
            aria-label="Table currency"
            className="block rounded border bg-background p-2"
            value={currency}
            onChange={(e) => {
              setCurrency(e.target.value)
              setMinimum("")
              setMaximum("")
              setPage(0)
              if (sort.startsWith("amount")) setSort("ledger")
            }}
          >
            <option value="">All currencies</option>
            {[...new Set(transactions.map((r) => r.currency))]
              .sort()
              .map((c) => (
                <option key={c}>{c}</option>
              ))}
          </select>
        </label>
        <label>
          Minimum amount {currency}
          <input
            aria-label="Table minimum amount"
            className="block w-40 rounded border bg-background p-2"
            inputMode="decimal"
            maxLength={32}
            disabled={!currency}
            value={minimum}
            onChange={(e) => {
              setMinimum(e.target.value)
              setPage(0)
            }}
          />
        </label>
        <label>
          Maximum amount {currency}
          <input
            aria-label="Table maximum amount"
            className="block w-40 rounded border bg-background p-2"
            inputMode="decimal"
            maxLength={32}
            disabled={!currency}
            value={maximum}
            onChange={(e) => {
              setMaximum(e.target.value)
              setPage(0)
            }}
          />
        </label>
        <label>
          Table direction
          <select
            aria-label="Table direction"
            className="block rounded border bg-background p-2"
            value={direction}
            onChange={(e) => {
              setDirection(e.target.value)
              setPage(0)
            }}
          >
            <option value="">Both directions</option>
            <option value="credit">Incoming</option>
            <option value="debit">Outgoing</option>
          </select>
        </label>
        <label>
          Table proof class
          <select
            aria-label="Table proof class"
            className="block rounded border bg-background p-2"
            value={proof}
            onChange={(e) => {
              setProof(e.target.value)
              setPage(0)
            }}
          >
            <option value="">All proof classes</option>
            {[...new Set(transactions.map((r) => r.proof_class))]
              .sort()
              .map((p) => (
                <option key={p}>{p}</option>
              ))}
          </select>
        </label>
        <label>
          Table order
          <select
            aria-label="Table order"
            className="block rounded border bg-background p-2"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value)
              setPage(0)
            }}
          >
            <option value="ledger">Ledger order</option>
            <option value="oldest">Oldest first</option>
            <option value="newest">Newest first</option>
            <option value="amount-desc" disabled={!amountAllowed}>
              Largest amount first (one currency)
            </option>
            <option value="amount-asc" disabled={!amountAllowed}>
              Smallest amount first (one currency)
            </option>
          </select>
        </label>
        <Button
          variant="outline"
          onClick={() => {
            setSearch("")
            setCurrency("")
            setMinimum("")
            setMaximum("")
            setDirection("")
            setProof("")
            setSort("ledger")
            setPage(0)
          }}
        >
          Reset table view
        </Button>
      </div>
      {invalidRange && (
        <p role="alert">
          Enter valid amounts for {currency}, with the minimum no greater than
          the maximum. The table export is unavailable until the range is valid.
        </p>
      )}
      <p className="text-sm">
        Amount bounds are inclusive and compare posting amounts in the chosen
        currency. Choose incoming or outgoing separately; changing currency
        clears the range.
      </p>
      <p className="text-sm">
        {rows.length} of {transactions.length} loaded rows match this table
        view. Main totals and the ledger snapshot use the applied account/date
        filters. The table-view export also records the filters and order above.
        Display sorting does not establish bank sequence.
      </p>
      {!rows.length ? (
        <p>
          No loaded rows match this table search. Evidence may still be
          incomplete.
        </p>
      ) : (
        <LedgerTable
          transactions={rows.slice(index * 50, index * 50 + 50)}
          {...actions}
        />
      )}
      {exportContext && !invalidRange && (
        <details className="rounded border p-3">
          <summary className="cursor-pointer font-medium">
            Download these transactions
          </summary>
          <LedgerExportButton
            caseId={exportContext.caseId}
            params={exportContext.params}
            tableView={{
              search,
              currency,
              direction,
              proof,
              minimum_minor: minMinor ?? "",
              maximum_minor: maxMinor ?? "",
              sort:
                sort.startsWith("amount") && !amountAllowed ? "ledger" : sort,
            }}
          />
        </details>
      )}
      {rows.length > 50 && (
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            disabled={!index}
            onClick={() => setPage(index - 1)}
          >
            Previous ledger rows
          </Button>
          <span>
            {index * 50 + 1}–{Math.min((index + 1) * 50, rows.length)} of{" "}
            {rows.length} matching rows
          </span>
          <Button
            variant="outline"
            disabled={(index + 1) * 50 >= rows.length}
            onClick={() => setPage(index + 1)}
          >
            Next ledger rows
          </Button>
        </div>
      )}
    </section>
  )
}
