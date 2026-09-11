import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useCreateCaseworkEntry } from "@/features/workspace/hooks/use-casework"

export function TransactionNote({
  caseId,
  transactionId,
  refId,
  fileId,
  filename,
  locator,
  initialOpen = false,
}: {
  caseId: string
  transactionId: string
  refId: string
  fileId: string
  filename: string
  locator: unknown
  initialOpen?: boolean
}) {
  const [open, setOpen] = useState(initialOpen)
  const [body, setBody] = useState("")
  const save = useCreateCaseworkEntry(caseId)
  if (!open)
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        Add investigation note
      </Button>
    )
  return (
    <section
      className="rounded border p-3 space-y-2"
      aria-label="Transaction investigation note"
    >
      <h3 className="font-semibold">Investigation note</h3>
      <p className="text-sm">
        Record what you noticed or what needs checking. The note is saved in
        this case's Workspace with a link to this transaction and statement.
      </p>
      {save.isSuccess && save.data.case_id === caseId ? (
        <p role="status">
          Note saved.{" "}
          <a
            className="underline"
            href={`/cases/${encodeURIComponent(caseId)}/workspace?view=casework&kind=note&entry=${encodeURIComponent(save.data.id)}`}
          >
            Open Workspace
          </a>
        </p>
      ) : (
        <>
          <label className="block">
            Your note
            <textarea
              aria-label="Your transaction note"
              className="block w-full min-h-28 border rounded p-2 bg-background"
              maxLength={8000}
              value={body}
              disabled={save.isPending}
              onChange={(e) => setBody(e.target.value)}
            />
          </label>
          <Button
            disabled={!body.trim() || save.isPending || save.isSuccess}
            onClick={() =>
              save.mutate({
                entry_type: "note",
                title: `Transaction note: ${filename}`,
                body: body.trim(),
                tags: ["financial", "transaction"],
                links: [
                  {
                    target_type: "evidence",
                    target_id: fileId,
                    target_label: filename,
                    relationship: "context",
                    source_anchor: {
                      financial_transaction_ids: [transactionId],
                      financial_ref_ids: [refId],
                      locator,
                    },
                    metadata: {
                      schema: "loupe.financial.transaction_note/1",
                      transaction_id: transactionId,
                      ref_id: refId,
                    },
                  },
                ],
              })
            }
          >
            {save.isPending ? "Saving note…" : "Save investigation note"}
          </Button>
          {save.isError && (
            <p role="alert">
              The note could not be confirmed. Your text is still here. Check
              Workspace before trying again. {save.error.message}
            </p>
          )}
          {save.isSuccess && save.data.case_id !== caseId && (
            <p role="alert">
              The save response did not match this case. Check Workspace before
              trying again.
            </p>
          )}
        </>
      )}
    </section>
  )
}
