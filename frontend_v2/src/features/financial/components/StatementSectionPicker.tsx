import { Button } from "@/components/ui/button"
import { useStatementWorkspace } from "../stores/statement-workspace"

type Section = {
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
}
function sectionLabel(item: Section) {
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
export function StatementSectionPicker({
  choices,
  scope,
  onChoose,
}: {
  choices: Section[]
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
      <div className="grid sm:grid-cols-2 gap-2">
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
