import { useFinancialStore } from "../stores/financial.store"
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
import { readSelectedPayments } from "../lib/selected-payment-source"
import { paymentDay } from "../lib/investigator-workspace"
import { formatLedgerAmount } from "../lib/ledger-format"
import { PaymentTotals } from "./InvestigationTransactionTable"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { useFinancialAccess } from "../hooks/use-financial-access"

export function PaymentComparison({
  caseId,
  ids,
  title = "Compare payments",
  onClose,
}: {
  caseId: string
  ids: string[]
  title?: string
  onClose: () => void
}) {
  const { canEdit } = useFinancialAccess()
  const [source, setSource] = useState<string | null>(null)
  const [finding, setFinding] = useState(false)
  const [page, setPage] = useState(0)
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "compare", ids],
    retry: false,
    queryFn: async ({ signal }) => {
      const records = []
      for (let offset = 0; offset < ids.length; offset += 500)
        records.push(
          ...(await readSelectedPayments(
            caseId,
            ids.slice(offset, offset + 500),
            signal
          ))
        )
      return records.sort(
        (a, b) =>
          (paymentDay(a.transaction) || "9999").localeCompare(
            paymentDay(b.transaction) || "9999"
          ) ||
          a.transaction.row_index - b.transaction.row_index ||
          a.transaction_id.localeCompare(b.transaction_id)
      )
    },
  })
  const rows = query.data?.map((item) => item.transaction) ?? []
  const current = query.data?.every(
    (item) =>
      item.ledger_status === "admitted" && item.superseded_by_id === null
  )
  return (
    <>
      <Dialog open={!finding} onOpenChange={(open) => !open && onClose()}>
        <DialogContent className="sm:max-w-[94vw] max-h-[94vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              Read the entries in date order and open their original statements.
              Similar dates or amounts alone do not establish a transfer.
            </DialogDescription>
          </DialogHeader>
          {query.isPending && (
            <p role="status">Loading all {ids.length} selected payments…</p>
          )}
          {query.isError && (
            <div role="alert">
              <p>{query.error.message}</p>
              <Button onClick={() => void query.refetch()}>
                Try loading payments again
              </Button>
            </div>
          )}
          {query.data && (
            <>
              {!current && (
                <p role="alert">
                  Some payments have changed or were excluded. Open their
                  details and choose their current versions before recording a
                  finding.
                </p>
              )}
              <PaymentTotals rows={rows} label="Payments in this comparison" />
              <div
                className={`grid gap-4 ${source ? "xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.85fr)]" : ""}`}
              >
                <div className="min-w-0 space-y-3">
                  <div className="overflow-x-auto">
                    <table
                      className="w-full text-sm"
                      aria-label="Payments in date order"
                    >
                      <thead className="text-left border-b">
                        <tr>
                          <th className="p-2">Date / gap</th>
                          <th className="p-2">Payment and account</th>
                          <th className="p-2 text-right">Amount</th>
                          <th className="p-2">Original</th>
                        </tr>
                      </thead>
                      <tbody>
                        {query.data
                          .slice(page * 25, (page + 1) * 25)
                          .map((item, offset) => {
                            const row = item.transaction,
                              previous = rows[page * 25 + offset - 1]
                            const date = paymentDay(row),
                              before = previous && paymentDay(previous)
                            const days =
                              date && before
                                ? (Date.parse(date) - Date.parse(before)) /
                                  86400000
                                : null
                            return (
                              <tr
                                key={row.key}
                                className="border-b align-top hover:bg-muted/30"
                              >
                                <td className="p-2 whitespace-nowrap">
                                  {date || "Payment date unknown"}
                                  {days !== null && (
                                    <p className="text-xs text-muted-foreground">
                                      {days === 0
                                        ? "Same day; order not established"
                                        : `${days} days later`}
                                    </p>
                                  )}
                                </td>
                                <td className="p-2">
                                  <strong>
                                    {row.description ||
                                      "Description not recorded"}
                                  </strong>
                                  <p className="text-xs text-muted-foreground">
                                    {row.account_label ||
                                      "Account name not recorded"}
                                  </p>
                                  <p className="text-xs">{item.filename}</p>
                                </td>
                                <td className="p-2 text-right whitespace-nowrap">
                                  <p
                                    className="finance-amount font-semibold"
                                    data-finance-tone={
                                      row.direction === "credit"
                                        ? "credit"
                                        : "debit"
                                    }
                                  >
                                    {
                                      formatLedgerAmount(
                                        row.amount_minor,
                                        row.currency
                                      ).text
                                    }{" "}
                                    {row.currency}
                                  </p>
                                  <p className="text-xs">
                                    {row.account_type === "credit_card"
                                      ? row.direction === "credit"
                                        ? "Card credit"
                                        : "Card charge"
                                      : row.direction === "credit"
                                        ? "Money in"
                                        : "Money out"}
                                  </p>
                                </td>
                                <td className="p-2">
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    aria-label={`Open original for ${row.description} on ${row.ordering_date}`}
                                    onClick={() => setSource(row.key)}
                                  >
                                    View original
                                  </Button>
                                </td>
                              </tr>
                            )
                          })}
                      </tbody>
                    </table>
                  </div>
                  {rows.length > 25 && (
                    <div className="flex gap-3 items-center">
                      <Button
                        variant="outline"
                        disabled={!page}
                        onClick={() => setPage(page - 1)}
                      >
                        Previous payments
                      </Button>
                      <span>
                        {page * 25 + 1} to{" "}
                        {Math.min(rows.length, (page + 1) * 25)} of{" "}
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
                    allowNearby={false}
                    inline
                    key={source}
                    caseId={caseId}
                    transactionId={source}
                    onClose={() => setSource(null)}
                  />
                )}
              </div>
              {canEdit && (
                <Button
                  disabled={!current || !rows.length}
                  onClick={() => setFinding(true)}
                >
                  Create finding from these payments
                </Button>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
      {finding && (
        <InvestigatorFindingEditor
          caseId={caseId}
          ids={ids}
          onClose={() => {
            setFinding(false)
            if (useFinancialStore.getState().mainView === "findings") onClose()
          }}
        />
      )}
    </>
  )
}
