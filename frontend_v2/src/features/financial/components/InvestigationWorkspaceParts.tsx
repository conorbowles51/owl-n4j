import { PaymentLabelsEditor } from "./PaymentLabelsEditor"
import { useLedgerTransactions } from "../hooks/use-ledger-transactions"
import { useMediaQuery } from "@/hooks/use-media-query"
import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useInvestigationScope } from "../stores/investigation-scope"
import { useFinancialDraft } from "../stores/financial-drafts"
import { InvestigationFilters } from "./InvestigationFilters"
import { InvestigationTransactionTable } from "./InvestigationTransactionTable"
import { PaymentComparison } from "./PaymentComparison"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

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
export function WorkspaceScope({ caseId }: { caseId: string }) {
  const [params, setParams] = useInvestigationScope(caseId)
  const accountRows = useLedgerTransactions(
    params.accountId ? caseId : undefined,
    params
  )
  const accountLabel = accountRows.data?.transactions.find(
    (row) => row.account_id === params.accountId
  )?.account_label
  return (
    <details
      className="finance-tint rounded-lg border px-4 py-3 text-sm"
      data-finance-tone="info"
    >
      <summary className="cursor-pointer font-medium">
        Accounts and dates{" "}
        <span className="ml-2 font-normal text-muted-foreground">
          {params.accountId
            ? accountLabel || "Selected account"
            : "All accounts"}{" "}
          · {params.startDate || "First available date"} to{" "}
          {params.endDate || "latest available date"}
        </span>
      </summary>
      <div className="pt-3">
        <InvestigationFilters
          key={JSON.stringify(params)}
          caseId={caseId}
          initialParams={params}
          onApply={setParams}
        />
      </div>
    </details>
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
export function PaymentSet({
  caseId,
  rows,
  title,
}: {
  caseId: string
  rows: LedgerTransaction[]
  title: string
}) {
  const { canEdit } = useFinancialAccess()
  const [selected, setSelected] = useFinancialDraft<string[]>(
    caseId,
    `investigation-payments:${title}`,
    []
  )
  const wide = useMediaQuery("(min-width: 1280px)")
  const [source, setSource] = useFinancialDraft<string | null>(
    caseId,
    `investigation-source:${title}`,
    null
  )
  const [labelIds, setLabelIds] = useState<string[] | null>(null)
  const [comparison, setComparison] = useState(false)
  const [finding, setFinding] = useState(false)
  const [requestedPage, setPage] = useFinancialDraft(
    caseId,
    `investigation-page:${title}`,
    0
  )
  const selectedSet = new Set(selected)
  const chosen = rows.filter((row) => selectedSet.has(row.key))
  const ids = selected
  const hiddenCount = selected.length - chosen.length
  const page = Math.min(
    requestedPage,
    Math.max(0, Math.ceil(rows.length / 25) - 1)
  )
  return (
    <section className="space-y-3" aria-label={title}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold">{title}</h3>
          <p className="text-xs text-muted-foreground">
            {rows.length} payments
            {selected.length ? ` · ${selected.length} selected` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={
              !rows.length || rows.every((row) => selectedSet.has(row.key))
            }
            onClick={() =>
              setSelected((current) => [
                ...new Set([...current, ...rows.map((row) => row.key)]),
              ])
            }
          >
            Select all {rows.length} payments
          </Button>
          {ids.length > 0 && (
            <>
              <Button
                variant="outline"
                disabled={!ids.length}
                onClick={() => setComparison(true)}
              >
                Compare {ids.length} payments
              </Button>
              {canEdit && (
                <Button
                  variant="outline"
                  disabled={!ids.length}
                  onClick={() => setLabelIds(ids)}
                >
                  Categorize {ids.length} payments
                </Button>
              )}
              {canEdit && (
                <Button disabled={!ids.length} onClick={() => setFinding(true)}>
                  Create finding
                </Button>
              )}
              {selected.length > 0 && (
                <Button variant="ghost" onClick={() => setSelected([])}>
                  Clear selection
                </Button>
              )}
            </>
          )}
        </div>
      </div>
      {!!hiddenCount && (
        <p className="text-sm">
          {hiddenCount} selected payments are outside this view. Compare opens
          the complete selection.
        </p>
      )}
      <div
        className={`grid gap-4 ${source && wide ? "xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]" : ""}`}
      >
        <div className="min-w-0">
          <InvestigationTransactionTable
            compact
            showAccount={new Set(rows.map((row) => row.account_id)).size > 1}
            rows={rows.slice(page * 25, (page + 1) * 25)}
            selected={chosen.map((row) => row.key)}
            onToggle={(row, checked) =>
              setSelected((current) =>
                checked
                  ? [...new Set([...current, row.key])]
                  : current.filter((id) => id !== row.key)
              )
            }
            onOpen={(row) => setSource(row.key)}
            onCategorize={canEdit ? (row) => setLabelIds([row.key]) : undefined}
          />
          {rows.length > 25 && (
            <div className="flex items-center gap-3 py-3">
              <Button
                variant="outline"
                disabled={!page}
                onClick={() => setPage(page - 1)}
              >
                Previous payments
              </Button>
              <span className="text-sm">
                {page * 25 + 1} to {Math.min(rows.length, (page + 1) * 25)} of{" "}
                {rows.length}
              </span>
              <Button
                variant="outline"
                disabled={(page + 1) * 25 >= rows.length}
                onClick={() => setPage(page + 1)}
              >
                Next payments
              </Button>
            </div>
          )}
        </div>
        {source && (
          <LedgerSourceDialog
            inline={wide}
            key={source}
            caseId={caseId}
            transactionId={source}
            onClose={() => setSource(null)}
          />
        )}
      </div>
      {labelIds && (
        <PaymentLabelsEditor
          caseId={caseId}
          ids={labelIds}
          onClose={() => setLabelIds(null)}
        />
      )}
      {comparison && (
        <PaymentComparison
          caseId={caseId}
          ids={ids}
          title={title}
          onClose={() => setComparison(false)}
        />
      )}
      {finding && (
        <InvestigatorFindingEditor
          caseId={caseId}
          ids={ids}
          onClose={() => setFinding(false)}
        />
      )}
    </section>
  )
}
