import { PaymentLabelsEditor } from "./PaymentLabelsEditor"
import { useMediaQuery } from "@/hooks/use-media-query"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useFinancialDraft } from "../stores/financial-drafts"
import { InvestigationTransactionTable } from "./InvestigationTransactionTable"
import { PaymentComparison } from "./PaymentComparison"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

/** Payments chosen in an investigation view, with comparison, sources and findings. */
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
