import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import type { QueueEntry } from "../lib/review-queue"
import { BatchStatementImportChoice } from "./BatchStatementImportChoice"
import { batchItemQuery } from "./FinancialBatchPanel"

export const LEFT_OUT_MESSAGE =
  "Left out of the import: not a statement. The PDF and its reading are kept and count under Left out by you. To put it back, open its batch and choose Restore to review."

/**
 * The clear exit for a document that is not a bank or card statement: the
 * batch's own "Leave unimported" choice (same call, a reason required, checked
 * against the statement's current revision), offered on the queue item. The
 * statement's revision is read when the person asks, not for every item.
 */
export function QueueNotStatement({
  caseId,
  entry,
  onLeftOut,
}: {
  caseId: string
  entry: QueueEntry
  onLeftOut: (entry: QueueEntry) => void
}) {
  const [open, setOpen] = useState(false)
  const item = useQuery({ ...batchItemQuery(caseId, entry.batch_id!, entry.id), enabled: open })
  if (!open)
    return (
      <Button size="sm" variant="ghost" className="px-1" onClick={() => setOpen(true)}>
        This isn't a statement
      </Button>
    )
  if (item.isError)
    return (
      <p role="alert" className="text-xs">
        {item.error.message} Open the statement to leave it out from there.{" "}
        <Button size="sm" variant="ghost" className="px-1" onClick={() => setOpen(false)}>
          Close
        </Button>
      </p>
    )
  if (!item.data) return <p role="status" className="text-xs">Loading the statement…</p>
  if (!item.data.disposition_revision)
    return (
      <p role="status" className="text-xs">
        This statement cannot be left out from here now. Open its batch to change its import choice.
      </p>
    )
  return (
    <BatchStatementImportChoice
      caseId={caseId}
      batchId={entry.batch_id!}
      itemId={entry.id}
      revision={item.data.disposition_revision}
      skipped={item.data.status === "skipped"}
      startOpen
      skipLabel="Leave it out: not a statement"
      skipText="Use this when the document is not a bank or card statement (a letter, a notice, a form). It is left out of the import and nothing from it reaches Transactions. The PDF and its reading are kept, and you can put it back from its batch with Restore to review. Say what the document is."
      onCancel={() => setOpen(false)}
      refresh={() => onLeftOut(entry)}
    />
  )
}
