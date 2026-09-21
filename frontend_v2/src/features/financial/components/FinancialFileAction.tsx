import {
  FinancialRemovalAction,
  ProcessRemovedFile,
} from "./FinancialRemovalAction"
import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
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
import type { StatementFile } from "../hooks/use-statement-register"
import { useStatementWorkspace } from "../stores/statement-workspace"

const answer = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  financial_removed: z.boolean(),
  financial_visibility_revision: z.string(),
})

export function FinancialFileAction({
  caseId,
  file,
}: {
  caseId: string
  file: StatementFile
  imported?: boolean
}) {
  const { canEdit } = useFinancialAccess()
  const owner = useAuthStore(
    (s) => s.user?.id || s.user?.username || "anonymous"
  )
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  if (!canEdit) return null
  if (!file.financial_removed)
    return (
      <FinancialRemovalAction
        caseId={caseId}
        fileIds={[file.id]}
        label={`Remove from Financial: ${file.original_filename}`}
      />
    )
  if (file.financial_imports_removed)
    return <ProcessRemovedFile caseId={caseId} fileId={file.id} />
  const change = async (removed: boolean) => {
    setBusy(true)
    setError("")
    try {
      const result = answer.parse(
        await fetchAPI(
          `/api/financial/statement-import/${encodeURIComponent(file.id)}/visibility?${new URLSearchParams({ case_id: caseId })}`,
          {
            method: "POST",
            body: {
              removed,
              expected_revision: file.financial_visibility_revision,
            },
          }
        )
      )
      if (
        result.case_id !== caseId ||
        result.evidence_file_id !== file.id ||
        result.financial_removed !== removed
      )
        throw Error(
          "The returned file does not match this change. Refresh files to check its status."
        )
      client.setQueryData<StatementFile[]>(
        ["statement-import-files", caseId],
        (current) =>
          current?.map((item) =>
            item.id === file.id
              ? {
                  ...item,
                  financial_removed: removed,
                  financial_visibility_revision:
                    result.financial_visibility_revision,
                }
              : item
          )
      )
      const scope = `${owner}:${caseId}`
      const workspace = useStatementWorkspace.getState()
      if (removed && workspace.selections[scope]?.fileId === file.id) {
        workspace.select(scope, null)
        workspace.setOpen(scope, false)
      }
      setOpen(false)
    } catch (failure) {
      setError(
        (failure instanceof Error
          ? failure.message
          : "The change could not be confirmed.") +
          " The original file remains in Evidence."
      )
    } finally {
      await Promise.all([
        client.invalidateQueries({
          queryKey: ["statement-import-files", caseId],
        }),
        client.invalidateQueries({
          queryKey: ["financial-candidates", caseId, "uploaded-pdfs"],
        }),
      ])
      setBusy(false)
    }
  }
  return (
    <div className="space-y-2">
      <Button
        variant="outline"
        size="sm"
        disabled={busy}
        aria-label={`${file.financial_removed ? "Restore to Financial" : "Remove from Financial"}: ${file.original_filename}`}
        onClick={() =>
          file.financial_removed ? void change(false) : setOpen(true)
        }
      >
        {busy
          ? "Saving…"
          : file.financial_removed
            ? "Restore to Financial"
            : "Remove from Financial"}
      </Button>
      {error && !open && (
        <p role="alert" className="text-sm">
          {error}
        </p>
      )}
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value)
        }}
      >
        <DialogContent>
          <DialogTitle>Remove this file from Financial?</DialogTitle>
          <DialogDescription>
            {file.original_filename} will leave the financial file list for
            everyone in this case. The original stays in Evidence. Saved notes
            and review drafts are kept. You can bring it back using Removed
            files.
          </DialogDescription>
          {error && <p role="alert">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => void change(true)}>
              Remove from Financial
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              Keep file
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
