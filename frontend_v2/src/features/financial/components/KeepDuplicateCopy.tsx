import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"

export type KeepDuplicateCopyProps = {
  caseId: string
  sourceDocumentId: string
}

/** Count this set-aside copy instead of the copy that was retained for it. */
export function KeepDuplicateCopy({
  caseId,
  sourceDocumentId,
}: KeepDuplicateCopyProps) {
  const client = useQueryClient()
  const [reason, setReason] = useState("")
  const mutation = useMutation({
    retry: false,
    mutationFn: () =>
      fetchAPI<unknown>(
        `/api/financial/documents/${encodeURIComponent(sourceDocumentId)}/keep-duplicate-copy?${new URLSearchParams({ case_id: caseId })}`,
        { method: "POST", body: { reason: reason.trim() } }
      ),
    onSuccess: () => void client.invalidateQueries(),
  })
  return (
    <form
      className="space-y-2"
      aria-label="Keep this copy instead"
      onSubmit={(event) => {
        event.preventDefault()
        if (reason.trim() && !mutation.isPending) mutation.mutate()
      }}
    >
      <label className="block text-sm">
        Why this copy should count instead
        <textarea
          className="mt-1 block w-full rounded border p-2"
          value={reason}
          maxLength={4000}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      <Button
        type="submit"
        variant="outline"
        disabled={!reason.trim() || mutation.isPending || mutation.isSuccess}
      >
        Keep this copy instead
      </Button>
      {mutation.isError && (
        <p role="alert">
          {mutation.error instanceof Error
            ? mutation.error.message
            : "The decision could not be confirmed."}{" "}
          Nothing changed. Refresh this statement and try again.
        </p>
      )}
      {mutation.isSuccess && (
        <p role="status">
          This copy now counts in Transactions. The other copy stays in the
          case, set aside as its duplicate.
        </p>
      )}
    </form>
  )
}
