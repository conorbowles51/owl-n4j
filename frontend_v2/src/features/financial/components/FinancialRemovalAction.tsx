import { useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { z } from "zod"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { newReviewId } from "../lib/statement-review-id"

const previewSchema = z.object({
  case_id: z.string(),
  revision: z.string(),
  file_count: z.number(),
  reading_count: z.number(),
  transaction_count: z.number(),
  incomplete_count: z.number(),
  statement_count: z.number(),
  batch_count: z.number(),
  archived_batch_count: z.number(),
  updated_batch_count: z.number(),
  files: z.array(z.object({ id: z.string(), filename: z.string() })),
  can_remove: z.boolean(),
  blocked_reason: z.string().nullish(),
})
const receiptSchema = previewSchema.extend({
  removed: z.literal(true),
  restart_file_ids: z.array(z.string()),
})
const batchSchema = z.object({ id: z.string(), case_id: z.string() })

async function prepareRetainedPdfs(
  caseId: string,
  fileIds: string[],
  requestId: string
) {
  const result = batchSchema.parse(
    await fetchAPI(
      `/api/financial/statement-import/batches?case_id=${caseId}`,
      {
        method: "POST",
        body: { request_id: requestId, file_ids: fileIds, folder_ids: [] },
      }
    )
  )
  if (result.case_id !== caseId)
    throw Error("The returned batch belongs to another case.")
  return `/cases/${caseId}/financial?view=statements&batch=${result.id}`
}

export function FinancialRemovalAction({
  caseId,
  batchIds = [],
  fileIds = [],
  label = "Remove selected",
  accessibleLabel,
  onRemoved,
}: {
  caseId: string
  batchIds?: string[]
  fileIds?: string[]
  label?: string
  accessibleLabel?: string
  onRemoved?: () => void
}) {
  const { canEdit, canUpload } = useFinancialAccess()
  const client = useQueryClient(),
    navigate = useNavigate()
  const owner = useAuthStore(
    (s) => s.user?.id || s.user?.username || "anonymous"
  )
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("")
  const [preview, setPreview] = useState<z.infer<typeof previewSchema> | null>(
    null
  )
  const [receipt, setReceipt] = useState<z.infer<typeof receiptSchema> | null>(
    null
  )
  const selection = useRef({ batch_ids: batchIds, file_ids: fileIds })
  const restartRequest = useRef("")
  const prefix = `/api/financial/statement-import/removals`
  const load = async (newSelection = false) => {
    if (newSelection) {
      selection.current = { batch_ids: [...batchIds], file_ids: [...fileIds] }
      setReceipt(null)
      restartRequest.current = newReviewId()
    }
    setOpen(true)
    setBusy(true)
    setError("")
    setPreview(null)
    try {
      const result = previewSchema.parse(
        await fetchAPI(`${prefix}/preview?case_id=${caseId}`, {
          method: "POST",
          body: selection.current,
        })
      )
      if (result.case_id !== caseId)
        throw Error("The preview belongs to another case.")
      setPreview(result)
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not load the removal preview."
      )
    } finally {
      setBusy(false)
    }
  }
  const remove = async (restart: boolean) => {
    if (!preview) return
    setBusy(true)
    setError("")
    let removed = receipt
    try {
      if (!removed) {
        removed = receiptSchema.parse(
          await fetchAPI(`${prefix}/confirm?case_id=${caseId}`, {
            method: "POST",
            body: { ...selection.current, expected_revision: preview.revision },
          })
        )
        if (removed.case_id !== caseId)
          throw Error(
            "The removal result belongs to another case. Refresh the page."
          )
        setReceipt(removed)
        toast.success(
          `Removed ${removed.transaction_count} transactions from active Financial. Original PDFs retained in Removed files.`
        )
        const workspace = useStatementWorkspace.getState()
        workspace.select(`${owner}:${caseId}`, null)
        workspace.setOpen(`${owner}:${caseId}`, false)
      }
      if (restart) {
        const url = await prepareRetainedPdfs(
          caseId,
          removed.restart_file_ids,
          restartRequest.current
        )
        setOpen(false)
        navigate(url)
      }
      onRemoved?.()
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The operation could not be confirmed. Refresh before trying again."
      )
    } finally {
      // Refresh every financial view, including totals, profiles and coverage.
      await client.invalidateQueries({
        predicate: (q) => q.queryKey.includes(caseId),
      })
      setBusy(false)
    }
  }
  if (!canEdit) return null
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        aria-label={accessibleLabel}
        disabled={busy || (!batchIds.length && !fileIds.length)}
        onClick={() => void load(true)}
      >
        {label}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value)
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogTitle>
            {receipt
              ? "Financial imports removed"
              : "Remove financial imports?"}
          </DialogTitle>
          <DialogDescription>
            {receipt
              ? "The removed records no longer appear in active financial totals. You can process the retained PDFs again in this case."
              : "Review the affected files and records before confirming. This applies to everyone working in this case."}
          </DialogDescription>
          {busy && (
            <p role="status">
              {preview ? "Saving…" : "Checking affected imports…"}
            </p>
          )}
          {preview && (
            <div className="space-y-3">
              <p className="font-medium">
                {preview.file_count} PDFs · {preview.statement_count} statement
                periods · {preview.transaction_count} transactions ·{" "}
                {preview.incomplete_count} incomplete records
              </p>
              <p className="text-sm">
                {preview.archived_batch_count} processing{" "}
                {preview.archived_batch_count === 1 ? "batch" : "batches"} will
                be removed.
                {preview.updated_batch_count > 0 &&
                  ` ${preview.updated_batch_count} shared batches will keep their other files and saved reviews.`}
              </p>
              <ul className="max-h-48 overflow-y-auto list-disc pl-5 text-sm">
                {preview.files.map((file) => (
                  <li key={file.id}>{file.filename}</li>
                ))}
              </ul>
              <p className="text-sm">
                All {preview.reading_count} saved readings and copies of these
                PDFs are included. Original PDFs, case notes, findings and cited
                import history are retained. Processing afresh reads the PDFs
                again without reusing the removed imports or review corrections.
              </p>
              {preview.blocked_reason && !receipt && (
                <p role="alert">{preview.blocked_reason}</p>
              )}
            </div>
          )}
          {error && (
            <p role="alert">
              {receipt
                ? "The imports were removed, but fresh processing could not start. "
                : ""}
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {!receipt && (
              <Button
                disabled={busy || !preview?.can_remove}
                onClick={() => void remove(false)}
              >
                Remove imports
              </Button>
            )}
            {canUpload && (
              <Button
                disabled={busy || !preview?.can_remove}
                onClick={() => void remove(true)}
              >
                {receipt ? "Process PDFs afresh" : "Remove and process afresh"}
              </Button>
            )}
            {!receipt && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void load()}
              >
                Refresh preview
              </Button>
            )}
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              {receipt ? "Close" : "Cancel"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export function ProcessRemovedFile({
  caseId,
  fileId,
}: {
  caseId: string
  fileId: string
}) {
  const { canUpload, canEdit } = useFinancialAccess()
  const navigate = useNavigate()
  const request = useRef(newReviewId())
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("")
  if (!canEdit || !canUpload) return null
  return (
    <div className="space-y-2">
      <Button
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={async () => {
          setBusy(true)
          setError("")
          try {
            navigate(
              await prepareRetainedPdfs(caseId, [fileId], request.current)
            )
          } catch (failure) {
            setError(
              failure instanceof Error
                ? failure.message
                : "Could not prepare this PDF."
            )
          } finally {
            setBusy(false)
          }
        }}
      >
        {busy ? "Starting fresh processing…" : "Process PDF afresh"}
      </Button>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
