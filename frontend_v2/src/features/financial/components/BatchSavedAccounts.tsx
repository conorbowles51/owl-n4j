import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { batchSavedAccountsScope } from "../lib/batch-saved-accounts"
import { AccountHistory } from "./AccountHistory"

export function BatchSavedAccounts({
  caseId,
  batchId,
  operationId,
  onShowAll,
}: {
  caseId: string
  batchId: string
  operationId: string | null
  onShowAll: () => void
}) {
  const [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ["financial-batch-saved-accounts", caseId, batchId, operationId],
    retry: false,
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({ case_id: caseId })
      if (operationId) params.set("operation_id", operationId)
      const result = batchSavedAccountsScope.parse(
        await fetchAPI(
          `/api/financial/statement-import/batches/${encodeURIComponent(batchId)}/imported-transactions?${params}`,
          { signal, timeout: 60000 }
        )
      )
      if (result.case_id !== caseId || result.batch_id !== batchId)
        throw Error(
          "These saved results belong to another case or batch. Return to the batch and open its receipt again."
        )
      return { ...result, account_ids: [...new Set(result.account_ids)] }
    },
  })
  const ids = query.data?.account_ids ?? []
  const pageOffset = Math.min(
    offset,
    Math.max(0, Math.floor((ids.length - 1) / 8) * 8)
  )
  return (
    <section aria-label="Accounts from saved statements" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">
          Accounts from {operationId ? "this import" : "this batch"}
        </h3>
        <Button variant="outline" onClick={onShowAll}>
          Show all accounts in this case
        </Button>
      </div>
      {query.isPending && (
        <p role="status">Opening accounts from the saved statement receipt…</p>
      )}
      {query.isError && (
        <div role="alert">
          <p>
            {query.error.name === "AbortError"
              ? "Saved accounts did not respond within one minute. Retry this view or return to the batch; the saved statements are unchanged."
              : query.error.message}
          </p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            Retry saved accounts
          </Button>
        </div>
      )}
      {query.data && (
        <>
          <p>
            {query.data.statement_count} saved statements · {ids.length}{" "}
            {ids.length === 1 ? "account" : "accounts"} ·{" "}
            {query.data.transaction_count} imported transactions.
          </p>
          <p className="text-sm text-muted-foreground">
            These are the accounts recorded by the selected receipt. Their
            recorded statement dates and balances appear below, including
            periods saved earlier. This view does not change your transaction
            filters.
          </p>
          {!ids.length ? (
            <p>
              No current accounts are attached to this receipt. Return to the
              batch to inspect its saved statements.
            </p>
          ) : (
            <AccountHistory
              key={`${pageOffset}:${ids.join(",")}`}
              caseId={caseId}
              accountIds={ids.slice(pageOffset, pageOffset + 8)}
            />
          )}
          {ids.length > 8 && (
            <nav
              aria-label="Saved account pages"
              className="flex flex-wrap items-center gap-2"
            >
              <Button
                variant="outline"
                disabled={!pageOffset}
                onClick={() => setOffset(pageOffset - 8)}
              >
                Previous saved accounts
              </Button>
              <span>
                {pageOffset + 1}–{Math.min(pageOffset + 8, ids.length)} of{" "}
                {ids.length} accounts
              </span>
              <Button
                variant="outline"
                disabled={pageOffset + 8 >= ids.length}
                onClick={() => setOffset(pageOffset + 8)}
              >
                Next saved accounts
              </Button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}
