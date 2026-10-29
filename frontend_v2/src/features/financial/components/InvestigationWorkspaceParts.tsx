import { accountSelectionSummary } from "../lib/account-selection"
import { retainPaymentTableView } from "../lib/payment-table-draft"
import { useLedgerTransactions } from "../hooks/use-ledger-transactions"
import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useInvestigationScope } from "../stores/investigation-scope"
import { InvestigationFilters } from "./InvestigationFilters"

export function InvestigationReadState({
  data,
  children,
}: {
  data: ReturnType<typeof useInvestigatorPayments>
  children: ReactNode
}) {
  if (data.query.isPending)
    return (
      <p role="status" className="p-6">
        Loading this case’s payments…
      </p>
    )
  if (data.query.isError || !data.complete)
    return (
      <div role="alert" className="rounded border p-4 space-y-2">
        <p>
          {data.query.isError
            ? data.query.error.message
            : "Not all payments were returned. These views cannot yet describe the whole selection."}
        </p>
        <Button onClick={() => void data.query.refetch()}>
          Load payments again
        </Button>
      </div>
    )
  return children
}
export function WorkspaceScope({
  caseId,
  datesOnly = false,
}: {
  caseId: string
  datesOnly?: boolean
}) {
  const [params, setParams] = useInvestigationScope(caseId)
  const [open, setOpen] = useState(false)
  const accountRows = useLedgerTransactions(
    params.accountId ? caseId : undefined,
    params
  )
  const accountLabel = accountRows.data?.transactions.find(
    (row) => row.account_id === params.accountId
  )?.account_label
  return (
    <div
      className="finance-tint rounded-lg border px-4 py-3 text-sm"
      data-finance-tone="info"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="inline-flex max-w-full flex-wrap items-center gap-x-2 rounded-md border bg-background px-3 py-1.5 text-left font-semibold hover:bg-muted"
      >
        {datesOnly ? "Date range" : "Accounts and dates"}{" "}
        <span className="font-normal text-muted-foreground">
          {params.accountId &&
          !params.accountIds?.length &&
          !params.accountHolders?.length
            ? accountLabel || "Selected account"
            : accountSelectionSummary(params)}{" "}
          · {params.startDate || "First available date"} to{" "}
          {params.endDate || "latest available date"}
        </span>
        <span aria-hidden="true" className="text-muted-foreground">{open ? "▴ Close" : "▾ Change"}</span>
      </button>
      <div className={open ? "pt-3" : "hidden"}>
        <InvestigationFilters
          key={JSON.stringify(params)}
          caseId={caseId}
          initialParams={params}
          accountSelection={!datesOnly}
          onApply={(next) => {
            if (datesOnly) retainPaymentTableView(caseId, params, next)
            setParams(next)
          }}
        />
      </div>
    </div>
  )
}
export function WorkspaceHeading({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </header>
  )
}
// Kept here for existing imports; it lives in its own module so AccountHistory
// can use it without an import cycle through InvestigationTransactionTable.
export { PaymentSet } from "./PaymentSet"
