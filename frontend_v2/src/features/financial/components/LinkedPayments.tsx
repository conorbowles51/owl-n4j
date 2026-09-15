import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { readSelectedPayment } from "../lib/selected-payment-source"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { SelectedPaymentsReview } from "./SelectedPaymentsReview"
import {
  InvestigationTransactionTable,
  PaymentTotals,
} from "./InvestigationTransactionTable"
import { SavePaymentSelection } from "./SavePaymentSelection"

/** Resolve analysis references into recognisable payments, only when the person opens the list. */
export function LinkedPayments({
  caseId,
  ids,
  label = "View payments",
}: {
  caseId: string
  ids: string[]
  label?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <section className="space-y-3">
      <Button variant="outline" onClick={() => setOpen(!open)}>
        {open ? "Hide payments" : label} ({ids.length})
      </Button>
      {open && (
        <PaymentList
          key={JSON.stringify([caseId, ids])}
          caseId={caseId}
          ids={[...new Set(ids)]}
        />
      )}
    </section>
  )
}
function PaymentList({ caseId, ids }: { caseId: string; ids: string[] }) {
  const { canEdit } = useFinancialAccess()
  const [selected, setSelected] = useFinancialDraft<string[]>(
    caseId,
    "selected-payments",
    []
  )
  const [reviewSelection, setReviewSelection] = useState(false)
  const [page, setPage] = useState(0),
    [source, setSource] = useState<{ id: string; note: boolean } | null>(null)
  const visible = ids.slice(page * 20, page * 20 + 20)
  const query = useQuery({
    queryKey: ["financial-linked-payments", caseId, visible],
    retry: false,
    queryFn: async ({ signal }) => {
      const result = []
      for (let i = 0; i < visible.length; i += 5) {
        const batch = await Promise.all(
          visible.slice(i, i + 5).map(async (id) => {
            const data = await readSelectedPayment(caseId, id, signal)
            return data.transaction
          })
        )
        result.push(...batch)
      }
      return result
    },
  })
  return (
    <div className="space-y-3">
      {query.isPending && <p role="status">Loading payment details…</p>}
      {query.isError && (
        <p role="alert">
          Payments could not be loaded. {query.error.message}{" "}
          <Button variant="outline" onClick={() => void query.refetch()}>
            Try again
          </Button>
        </p>
      )}
      {query.data && (
        <>
          <p className="text-sm">
            {ids.length} linked payments. Tick payments to add them to the same
            selection you use in Transactions, up to 100 across all views. Open
            a payment to inspect changes since this analysis.
          </p>
          <InvestigationTransactionTable
            rows={query.data}
            selected={selected}
            onToggle={(row, checked) =>
              setSelected((previous) =>
                checked
                  ? [...new Set([...previous, row.key])].slice(0, 100)
                  : previous.filter((id) => id !== row.key)
              )
            }
            onOpen={(row) => setSource({ id: row.key, note: false })}
            onNote={
              canEdit
                ? (row) => setSource({ id: row.key, note: true })
                : undefined
            }
          />
          <PaymentTotals label="Payments on this page" rows={query.data} />
        </>
      )}
      {!!selected.length && (
        <div className="space-y-2">
          <p>
            {selected.length} payments selected across Financial.{" "}
            {selected.filter((id) => !ids.includes(id)).length} are outside this
            result and will also be saved.
          </p>
          <Button variant="outline" onClick={() => setReviewSelection(true)}>
            Review selected payments
          </Button>
          <SavePaymentSelection
            caseId={caseId}
            ids={selected}
            onReviewSelection={() => setReviewSelection(true)}
          />
          {reviewSelection && (
            <SelectedPaymentsReview
              key={caseId}
              caseId={caseId}
              ids={selected}
              onRemove={(id) => {
                setSelected((previous) =>
                  previous.filter((value) => value !== id)
                )
                if (selected.length === 1) setReviewSelection(false)
              }}
              onClose={() => setReviewSelection(false)}
            />
          )}
        </div>
      )}
      {ids.length > 20 && (
        <div className="flex gap-2 items-center">
          <Button
            disabled={!page || query.isFetching}
            onClick={() => setPage(page - 1)}
          >
            Previous payments
          </Button>
          <span>
            Page {page + 1} of {Math.ceil(ids.length / 20)}
          </span>
          <Button
            disabled={(page + 1) * 20 >= ids.length || query.isFetching}
            onClick={() => setPage(page + 1)}
          >
            Next payments
          </Button>
        </div>
      )}
      {source && (
        <LedgerSourceDialog
          key={source.id}
          caseId={caseId}
          transactionId={source.id}
          initialNoteOpen={source.note}
          onClose={() => setSource(null)}
        />
      )}
    </div>
  )
}
