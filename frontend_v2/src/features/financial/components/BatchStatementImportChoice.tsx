import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"

export function BatchStatementImportChoice({
  caseId,
  batchId,
  itemId,
  revision,
  skipped,
  refresh,
}: {
  caseId: string
  batchId: string
  itemId: string
  revision: string
  skipped: boolean
  refresh: () => void
}) {
  const [open, setOpen] = useState(false),
    [reason, setReason] = useState("")
  const action = skipped ? "restore" : "skip"
  const save = useMutation({
    retry: false,
    mutationFn: () =>
      fetchAPI(
        `/api/financial/statement-import/batches/${batchId}/items/${itemId}/import-choice?case_id=${caseId}`,
        {
          method: "POST",
          body: { action, reason, expected_revision: revision },
        }
      ),
    onSuccess: () => {
      setOpen(false)
      setReason("")
      refresh()
    },
  })
  const label = skipped ? "Restore to review" : "Leave unimported"
  return (
    <div className="text-sm space-y-2">
      {!open ? (
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          {label}
        </Button>
      ) : (
        <div className="rounded border p-3 space-y-2">
          <p>
            {skipped
              ? "Return this statement to review. Current values and checks will determine whether it is ready."
              : "Leave this statement out of this batch's import. Its PDF and saved corrections remain available."}
          </p>
          <label className="block">
            Reason
            <textarea
              aria-label={`Reason to ${label.toLowerCase()}`}
              maxLength={2000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className="block border rounded bg-background p-2 w-full"
            />
          </label>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={!reason.trim() || save.isPending}
              onClick={() => save.mutate()}
            >
              {save.isPending ? "Saving…" : label}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={save.isPending}
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
          </div>
          {save.isError && <p role="alert">{save.error.message}</p>}
        </div>
      )}
    </div>
  )
}
