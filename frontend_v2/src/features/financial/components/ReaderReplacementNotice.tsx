import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"

import type { ReaderReplacement } from "./readerReplacement"

/**
 * A saved statement Loupe replaced with a reading that balances. Both versions
 * stay in the case, linked; Restore puts the earlier version back (and sets the
 * newer reading aside at the same time, so the period never counts twice).
 */
export function ReaderReplacementNotice({
  caseId,
  notice,
  canEdit,
}: {
  caseId: string
  notice: ReaderReplacement
  canEdit: boolean
}) {
  const client = useQueryClient()
  const restore = useMutation({
    retry: false,
    mutationFn: () =>
      fetchAPI(
        `/api/financial/documents/${notice.counting_source_document_id}/restore-replaced-statement?case_id=${caseId}`,
        { method: "POST", body: {} }
      ),
    onSuccess: () => {
      void client.invalidateQueries()
    },
  })
  return (
    <div
      role="status"
      aria-label="Replaced saved statement"
      className="rounded border border-sky-500 p-3 space-y-2"
    >
      <p>{notice.message}</p>
      {canEdit && notice.can_restore && (
        <Button
          variant="outline"
          disabled={restore.isPending}
          onClick={() => restore.mutate()}
        >
          {notice.status === "replaced"
            ? "Restore earlier version"
            : "Use the newer reading again"}
        </Button>
      )}
      {restore.isError && (
        <p role="alert">
          {restore.error instanceof Error
            ? restore.error.message
            : "The restore could not be confirmed. Refresh before trying again."}
        </p>
      )}
    </div>
  )
}
