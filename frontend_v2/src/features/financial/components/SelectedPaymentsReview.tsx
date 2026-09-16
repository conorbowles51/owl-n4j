import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { readSelectedPayment } from "../lib/selected-payment-source"
import { formatLedgerAmount } from "../lib/ledger-format"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

export function SelectedPaymentsReview({
  caseId,
  ids,
  onRemove,
  onClose,
}: {
  caseId: string
  ids: string[]
  onRemove?: (id: string) => void
  onClose: () => void
}) {
  const [requestedPage, setPage] = useState(0)
  const [source, setSource] = useState<string | null>(null)
  const page = Math.min(
    requestedPage,
    Math.max(0, Math.ceil(ids.length / 20) - 1)
  )
  const visible = ids.slice(page * 20, (page + 1) * 20)
  const query = useQuery({
    queryKey: ["selected-payment-review", caseId, visible],
    retry: false,
    refetchOnMount: "always",
    queryFn: async ({ signal }) => {
      const result = []
      for (let offset = 0; offset < visible.length; offset += 5) {
        const batch = await Promise.all(
          visible.slice(offset, offset + 5).map(async (id) => {
            try {
              return { id, data: await readSelectedPayment(caseId, id, signal) }
            } catch {
              return { id, data: null }
            }
          })
        )
        if (signal.aborted) throw Error("Selection review was closed.")
        result.push(...batch)
      }
      return result
    },
  })
  return (
    <>
      <Dialog open={!source} onOpenChange={(value) => !value && onClose()}>
        <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Review selected payments</DialogTitle>
            <DialogDescription>
              Review payments you chose across all accounts and filters.
              {onRemove
                ? "Removing an entry here does not change the transaction or any saved finding."
                : "Existing findings retain the payment versions cited when they were saved."}
            </DialogDescription>
          </DialogHeader>
          {query.isFetching && <p role="status">Checking selected payments…</p>}
          {!ids.length && (
            <p>
              No payments remain selected. Close this list to choose payments.
            </p>
          )}
          {query.data && !query.isFetching && (
            <ul className="space-y-3">
              {query.data.map(({ id, data }) => {
                const row = data?.transaction
                const changed =
                  data &&
                  (data.ledger_status !== "admitted" ||
                    data.superseded_by_id !== null)
                return (
                  <li key={id} className="rounded border p-3 space-y-2">
                    {row ? (
                      <>
                        <p className="font-medium">
                          {row.description || row.ref_id}
                        </p>
                        <p>
                          {row.ordering_date} ·{" "}
                          {row.direction === "credit"
                            ? row.account_type === "credit_card"
                              ? "Card credit: "
                              : "Money in: "
                            : row.direction === "debit"
                              ? row.account_type === "credit_card"
                                ? "Card charge: "
                                : "Money out: "
                              : "Amount: "}
                          {
                            formatLedgerAmount(row.amount_minor, row.currency)
                              .text
                          }{" "}
                          {row.currency}
                        </p>
                        {row.account_label && (
                          <p className="text-sm">{row.account_label}</p>
                        )}
                        <p className="text-sm break-words">
                          {data.filename} · {row.ref_id}
                        </p>
                        {changed && (
                          <p role="status" className="text-sm">
                            {data.superseded_by_id
                              ? "Corrected since you selected it. Open the transaction to compare versions. Remove this older entry, then choose the corrected payment in Transactions."
                              : "This payment is no longer included in Transactions. Remove it from this selection before saving, or open it to inspect its status."}
                          </p>
                        )}
                      </>
                    ) : (
                      <p role="alert">
                        This selected payment could not be checked. Retry before
                        deciding whether to remove it. Reference: {id}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-2">
                      {data ? (
                        <Button variant="outline" onClick={() => setSource(id)}>
                          Open transaction
                        </Button>
                      ) : (
                        <Button
                          variant="outline"
                          onClick={() => void query.refetch()}
                        >
                          Retry payment check
                        </Button>
                      )}
                      {onRemove && (
                        <Button variant="outline" onClick={() => onRemove(id)}>
                          Remove from selection
                        </Button>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          {query.isError && (
            <p role="alert">
              The selection could not be checked.{" "}
              <Button variant="outline" onClick={() => void query.refetch()}>
                Retry payment check
              </Button>
            </p>
          )}
          {ids.length > 20 && (
            <div className="flex flex-wrap gap-2 items-center">
              <Button
                variant="outline"
                disabled={page === 0 || query.isFetching}
                onClick={() => setPage(page - 1)}
              >
                Previous selected payments
              </Button>
              <span>
                Page {page + 1} of {Math.ceil(ids.length / 20)}
              </span>
              <Button
                variant="outline"
                disabled={(page + 1) * 20 >= ids.length || query.isFetching}
                onClick={() => setPage(page + 1)}
              >
                Next selected payments
              </Button>
            </div>
          )}
          <Button variant="outline" onClick={onClose}>
            Close selection review
          </Button>
        </DialogContent>
      </Dialog>
      {source && (
        <LedgerSourceDialog
          key={source}
          caseId={caseId}
          transactionId={source}
          onClose={() => {
            setSource(null)
            void query.refetch()
          }}
        />
      )}
    </>
  )
}
