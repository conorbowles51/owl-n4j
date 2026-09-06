import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"

export interface ReviewedDocument {
  document_id: string
  filename: string
  revision: string
}
export interface DuplicateSelection {
  caseId: string
  document: ReviewedDocument
  primary?: ReviewedDocument
}
const answer = z.object({
  case_id: z.string(),
  document_id: z.string(),
  action: z.enum(["exclude", "restore"]),
  applied: z.literal(true),
  changed_rows: z.number().int().nonnegative(),
  adjudication_id: z.string().min(1),
})

export function DuplicateDecisionForm({
  selection,
  onClose,
}: {
  selection: DuplicateSelection
  onClose: () => void
}) {
  const [reason, setReason] = useState("")
  const lock = useRef(false)
  const client = useQueryClient()
  const action = selection.primary ? "exclude" : "restore"
  const mutation = useMutation({
    retry: false,
    mutationFn: async ({
      selected,
      reason,
    }: {
      selected: DuplicateSelection
      reason: string
    }) => {
      const action = selected.primary ? "exclude" : "restore"
      const raw = await fetchAPI<unknown>(
        `/api/financial/documents/${encodeURIComponent(selected.document.document_id)}/duplicate-decision?${new URLSearchParams({ case_id: selected.caseId })}`,
        {
          method: "POST",
          body: {
            action,
            reason,
            expected_revision: selected.document.revision,
            ...(selected.primary
              ? {
                  primary_id: selected.primary.document_id,
                  expected_primary_revision: selected.primary.revision,
                }
              : {}),
          },
        }
      )
      const data = answer.parse(raw)
      if (
        data.case_id !== selected.caseId ||
        data.document_id !== selected.document.document_id ||
        data.action !== action
      )
        throw new Error("The response did not confirm the requested decision.")
      return data
    },
    onSettled: (_data, _error, variables) => {
      void client.invalidateQueries({
        queryKey: ["financial-ledger", variables.selected.caseId],
      })
      void client.invalidateQueries({
        queryKey: ["financial-decisions", variables.selected.caseId],
      })
    },
  })
  const refused =
    mutation.error instanceof ApiError &&
    [400, 401, 403, 404, 409, 422].includes(mutation.error.status)
  return (
    <form
      aria-label="Duplicate decision"
      className="space-y-3 rounded border p-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (
          lock.current ||
          !reason.trim() ||
          mutation.isSuccess ||
          mutation.isError
        )
          return
        lock.current = true
        mutation.mutate(
          { selected: selection, reason },
          {
            onSettled: () => {
              lock.current = false
            },
          }
        )
      }}
    >
      <h3 className="text-sm font-semibold">
        {action === "exclude"
          ? "Confirm duplicate exclusion"
          : "Restore excluded document"}
      </h3>
      <p className="text-sm">{selection.document.filename}</p>
      {selection.primary ? (
        <p className="text-sm">
          Retain: {selection.primary.filename}. Admitted rows in the excluded
          copy will be removed from ledger totals. The source and decision
          history stay available.
        </p>
      ) : (
        <p className="text-sm">
          Only rows recorded by this exclusion will return to the ledger.
          Corrected or otherwise held-out rows will not be readmitted. Both
          copies may then count.
        </p>
      )}
      <label className="block text-sm">
        Reason for this decision
        <textarea
          className="mt-1 block w-full rounded border bg-background p-2"
          required
          maxLength={4000}
          value={reason}
          disabled={
            mutation.isPending || mutation.isSuccess || mutation.isError
          }
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      {mutation.isSuccess && (
        <p role="status">
          Decision recorded. {mutation.data.changed_rows} rows{" "}
          {action === "exclude" ? "excluded" : "restored"}.
        </p>
      )}
      {mutation.isError && (
        <p role="alert">
          {refused
            ? `Decision refused: ${mutation.error.message}`
            : "The decision could not be confirmed. It may have been recorded. Check the refreshed comparison and decision history before trying again."}
        </p>
      )}
      <div className="flex gap-2">
        {!mutation.isSuccess && !mutation.isError && (
          <Button type="submit" disabled={!reason.trim() || mutation.isPending}>
            {mutation.isPending ? "Recording decision..." : "Record decision"}
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={mutation.isPending}
          onClick={onClose}
        >
          Close decision
        </Button>
      </div>
    </form>
  )
}
