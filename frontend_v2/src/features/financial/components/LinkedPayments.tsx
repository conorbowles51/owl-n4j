import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { citationSchema } from "../lib/source-citation"
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
  const [page, setPage] = useState(0),
    [selected, setSelected] = useState<string[]>([]),
    [source, setSource] = useState<{ id: string; note: boolean } | null>(null)
  const visible = ids.slice(page * 20, page * 20 + 20)
  const query = useQuery({
    queryKey: ["financial-linked-payments", caseId, visible],
    retry: false,
    queryFn: async () => {
      const result = []
      for (let i = 0; i < visible.length; i += 5) {
        const batch = await Promise.all(
          visible.slice(i, i + 5).map(async (id) => {
            const data = citationSchema.parse(
              await fetchAPI(
                `/api/financial/ledger/${encodeURIComponent(id)}/source?${new URLSearchParams({ case_id: caseId })}`
              )
            )
            if (
              data.case_id !== caseId ||
              data.transaction_id !== id ||
              !data.transaction ||
              data.transaction.key !== id ||
              data.transaction.case_id !== caseId ||
              data.transaction.source_document_id !== data.source_document_id
            )
              throw Error(
                "The payment details did not match this case. Refresh this analysis."
              )
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
            {ids.length} linked payments. Select up to 100 to save with a note.
            Details show the current record; open a payment to inspect changes
            since this analysis.
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
            onNote={(row) => setSource({ id: row.key, note: true })}
          />
          <PaymentTotals label="Payments on this page" rows={query.data} />
        </>
      )}
      {!!selected.length && (
        <SavePaymentSelection caseId={caseId} ids={selected} />
      )}
      {ids.length > 20 && (
        <div className="flex gap-2 items-center">
          <Button disabled={!page} onClick={() => setPage(page - 1)}>
            Previous payments
          </Button>
          <span>
            Page {page + 1} of {Math.ceil(ids.length / 20)}
          </span>
          <Button
            disabled={(page + 1) * 20 >= ids.length}
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
