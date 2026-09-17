import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useStatementWorkspace } from "../stores/statement-workspace"

export type StatementSection = {
  id: string
  institution: string
  account_reference: string
  account_label?: string
  document_kind?: "deposit_receipt"
  statement_date?: string
  printed_statement_date?: string
  period_start: string
  period_end: string
  page_numbers: number[]
  checks?: {
    balance_status: "matches" | "difference" | "unavailable"
    has_difference?: boolean
    flagged_rows: number
    transaction_count?: number
  }
}
function sectionLabel(item: StatementSection) {
  return [
    item.document_kind ? "Deposit receipt" : item.institution,
    item.account_reference || "Account needs review",
    item.account_label,
    item.period_start
      ? `${item.period_start} to ${item.period_end}`
      : item.statement_date ||
        `Check date: ${item.printed_statement_date || "unreadable"}`,
    `pages ${item.page_numbers.join(", ")}`,
  ]
    .filter(Boolean)
    .join(" · ")
}
function checkLabel(item: StatementSection) {
  const checks = item.checks
  if (!checks) return ""
  return [
    checks.has_difference
      ? "Balance difference"
      : checks.balance_status === "matches"
        ? "Extracted balances agree"
        : checks.balance_status === "difference"
          ? "Balance difference"
          : "Balance check unavailable",
    checks.transaction_count === undefined
      ? ""
      : `${checks.transaction_count} transactions`,
    checks.flagged_rows ? `${checks.flagged_rows} rows to check` : "",
  ]
    .filter(Boolean)
    .join(" · ")
}

export function StatementPeriodSelect({
  choices,
  value,
  onChoose,
}: {
  choices: StatementSection[]
  value: string
  onChoose: (id: string) => void
}) {
  const [search, setSearch] = useState("")
  const accountKey = (item: StatementSection) =>
    JSON.stringify([
      item.institution,
      item.account_reference,
      item.account_label,
      item.document_kind,
    ])
  const selected = choices.find((item) => item.id === value)
  const account = selected ? accountKey(selected) : ""
  const accounts = [
    ...new Map(choices.map((item) => [accountKey(item), item])).entries(),
  ]
  const periods = choices
    .filter((item) => !account || accountKey(item) === account)
    .sort((a, b) =>
      (a.period_start || a.statement_date || "").localeCompare(
        b.period_start || b.statement_date || ""
      )
    )
  const terms = search.toLowerCase().trim().split(/\s+/).filter(Boolean)
  const shown = periods.filter((item) =>
    terms.every((term) => sectionLabel(item).toLowerCase().includes(term))
  )
  const index = periods.findIndex((item) => item.id === value)
  return (
    <div className="rounded border bg-muted/20 p-3 space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <label className="min-w-0 text-sm font-medium">
          Account ({accounts.length} available)
          <select
            aria-label="Statement account"
            className="mt-1 block w-full rounded border bg-background p-2"
            value={account}
            onChange={(event) => {
              const first = choices
                .filter((item) => accountKey(item) === event.target.value)
                .sort((a, b) => a.period_start.localeCompare(b.period_start))[0]
              setSearch("")
              if (first) onChoose(first.id)
            }}
          >
            <option value="" disabled>
              Choose an account
            </option>
            {accounts.map(([key, item]) => (
              <option value={key} key={key}>
                {[
                  item.institution,
                  item.account_reference || "Account needs review",
                  item.account_label,
                  item.document_kind ? "Deposit receipts" : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0 text-sm font-medium">
          Statement period ({periods.length} available)
          <select
            aria-label="Statement period"
            className="mt-1 block w-full rounded border bg-background p-2"
            value={shown.some((item) => item.id === value) ? value : ""}
            onChange={(event) => onChoose(event.target.value)}
          >
            <option value="" disabled>
              Choose a period
            </option>
            {shown.map((item) => (
              <option key={item.id} value={item.id}>
                {!account ? `${item.account_reference} · ` : ""}
                {item.period_start
                  ? `${item.period_start} to ${item.period_end}`
                  : item.statement_date || "Check printed date"}
                {checkLabel(item) ? ` · ${checkLabel(item)}` : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        {periods.length > 10 && (
          <label className="text-sm flex-1 min-w-40">
            Find a period
            <input
              aria-label="Find a period"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Year, month or page number"
              className="block w-full rounded border bg-background p-2"
            />
          </label>
        )}
        <Button
          variant="outline"
          disabled={index <= 0}
          onClick={() => {
            setSearch("")
            onChoose(periods[index - 1].id)
          }}
        >
          Previous period
        </Button>
        <Button
          variant="outline"
          disabled={index < 0 || index >= periods.length - 1}
          onClick={() => {
            setSearch("")
            onChoose(periods[index + 1].id)
          }}
        >
          Next period
        </Button>
        {selected && (
          <span className="text-sm text-muted-foreground">
            PDF pages {selected.page_numbers.join(", ")}
          </span>
        )}
        {!shown.length && (
          <p className="w-full text-sm">
            No periods match.{" "}
            <button className="underline" onClick={() => setSearch("")}>
              Clear period search
            </button>
          </p>
        )}
      </div>
    </div>
  )
}

export function StatementSectionPicker({
  choices,
  scope,
  onChoose,
}: {
  choices: StatementSection[]
  scope: string
  onChoose: (id: string) => void
}) {
  const search = useStatementWorkspace(
    (state) => state.sectionSearches[scope] ?? ""
  )
  const setSearch = (value: string) =>
    useStatementWorkspace.getState().setSectionSearch(scope, value)
  const hasReceipts = choices.some(
    (item) => item.document_kind === "deposit_receipt"
  )
  const terms = search.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  const shown = choices.filter((item) =>
    terms.every((term) => sectionLabel(item).toLocaleLowerCase().includes(term))
  )
  return (
    <section className="space-y-3 py-4" aria-label="Statements in this PDF">
      <h3 className="font-semibold">
        {hasReceipts
          ? "Statements and receipts in this PDF"
          : `This PDF contains ${choices.length} statements`}
      </h3>
      <p>
        Choose an account and statement period to review. Savings and checking
        sections are separate choices.{" "}
        {hasReceipts &&
          "Deposit receipts are reviewed separately and do not add transactions."}{" "}
        Page numbers refer to the original PDF.
      </p>
      <StatementPeriodSelect choices={choices} value="" onChoose={onChoose} />
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-0 flex-1 text-sm">
          Find a statement or receipt
          <input
            className="mt-1 block w-full rounded border bg-background p-2"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Account, year, date or PDF page"
          />
        </label>
        {search && (
          <Button variant="outline" onClick={() => setSearch("")}>
            Clear search
          </Button>
        )}
      </div>
      <p className="text-sm text-muted-foreground" role="status">
        {shown.length} of {choices.length} sections shown, in PDF order.
      </p>
      {!shown.length && (
        <p>
          No sections match this search. Try an account number or a date such as
          2020-09, or clear the search.
        </p>
      )}
      <div className="grid sm:grid-cols-2 gap-2 max-h-72 overflow-y-auto">
        {shown.map((item) => (
          <Button
            variant="outline"
            className="h-auto whitespace-normal text-left justify-start p-3"
            key={item.id}
            onClick={() => onChoose(item.id)}
          >
            {sectionLabel(item)}
          </Button>
        ))}
      </div>
    </section>
  )
}
