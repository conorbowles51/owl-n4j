import { useNavigate } from "react-router-dom"
import { usesPdfStatementReader } from "../hooks/use-statement-register"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { newReviewId } from "../lib/statement-review-id"
import { z } from "zod"
import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Folder, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { fetchAPI } from "@/lib/api-client"
import { foldersAPI } from "@/features/evidence/folders.api"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  intakeSelection,
  type IntakeSelection,
} from "../lib/evidence-selection"

export function EvidenceFinancialPicker({
  caseId,
  initialFileIds = [],
  initialFolderId = null,
  label = "Choose from Evidence",
}: {
  caseId: string
  initialFileIds?: string[]
  initialFolderId?: string | null
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const { canEdit, canUpload } = useFinancialAccess()
  if (!canEdit || !canUpload) return null
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        {label}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="flex max-h-[92dvh] flex-col sm:max-w-5xl">
          <DialogTitle>Send existing evidence to Financial</DialogTitle>
          <DialogDescription>
            Select files whose contents are relevant to your financial
            investigation, including CSV, spreadsheets, Word documents, images
            and PDFs. Folders include their subfolders; review the list before
            sending. File type determines the available reader, not financial
            relevance.
          </DialogDescription>
          {open && (
            <EvidenceBrowser
              key={caseId}
              caseId={caseId}
              initialFileIds={initialFileIds}
              initialFolderId={initialFolderId}
              onStarted={() => setOpen(false)}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function EvidenceBrowser({
  caseId,
  initialFileIds,
  initialFolderId,
  onStarted,
}: {
  onStarted: () => void
  caseId: string
  initialFileIds: string[]
  initialFolderId: string | null
}) {
  const { canEdit, canUpload } = useFinancialAccess()
  const client = useQueryClient()
  const go = useNavigate()
  const [requestId, setRequestId] = useState(newReviewId)
  const [folder, setFolder] = useState(initialFolderId)
  const [files, setFiles] = useState<string[]>(initialFileIds)
  const [folders, setFolders] = useState<string[]>(
    initialFileIds.length ? [] : initialFolderId ? [initialFolderId] : []
  )
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState("")
  const [review, setReview] = useState<IntakeSelection | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const listing = useQuery({
    queryKey: ["financial-evidence-browser", caseId, folder, page, search],
    queryFn: ({ signal }) =>
      foldersAPI.getContents(
        caseId,
        folder,
        {
          limit: 100,
          offset: page * 100,
          search,
          sort_by: "name",
          sort_direction: "asc",
        },
        signal
      ),
  })
  const navigate = (id: string | null) => {
    setFolder(id)
    setPage(0)
    setSearch("")
  }
  const toggle = (values: string[], id: string) =>
    values.includes(id)
      ? values.filter((value) => value !== id)
      : [...values, id]
  const inspect = async () => {
    setBusy(true)
    setError("")
    try {
      const result = intakeSelection.parse(
        await fetchAPI(
          `/api/financial/statement-import/selection/resolve?${new URLSearchParams({ case_id: caseId })}`,
          {
            method: "POST",
            body: {
              file_ids: files,
              folder_ids: folders,
              include_other_formats: true,
            },
          }
        )
      )
      if (result.case_id !== caseId)
        throw Error("The selection belongs to another case.")
      setReview(result)
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "The selection could not be read."
      )
    } finally {
      setBusy(false)
    }
  }
  const changed = () => {
    void client.invalidateQueries({
      queryKey: ["statement-import-files", caseId],
    })
    void client.invalidateQueries({
      queryKey: ["statement-import-status", caseId],
    })
    void client.invalidateQueries({
      queryKey: ["financial-evidence-browser", caseId],
    })
    void client.invalidateQueries({
      queryKey: ["evidence-folder-contents", caseId],
    })
  }
  return (
    <div className="min-h-0 overflow-auto space-y-4">
      {error && <p role="alert">{error}</p>}
      {!review ? (
        <>
          <nav
            aria-label="Evidence folders"
            className="flex flex-wrap items-center gap-1 text-sm"
          >
            <Button variant="ghost" size="sm" onClick={() => navigate(null)}>
              Evidence root
            </Button>
            {listing.data?.breadcrumbs.map((item) => (
              <span key={item.id} className="flex items-center">
                <ChevronRight size={14} />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate(item.id)}
                >
                  {item.name}
                </Button>
              </span>
            ))}
          </nav>
          <div className="flex flex-wrap gap-3 items-center">
            <label className="text-sm">
              Find files in this folder{" "}
              <input
                className="rounded border bg-background p-2"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value)
                  setPage(0)
                }}
              />
            </label>
            {folder && (
              <label className="text-sm">
                <input
                  type="checkbox"
                  checked={folders.includes(folder)}
                  onChange={() => setFolders(toggle(folders, folder))}
                />{" "}
                Select this folder and its subfolders
              </label>
            )}
          </div>
          {listing.isPending && <p role="status">Loading folder…</p>}
          {listing.isError && (
            <p role="alert">
              Could not load this folder.{" "}
              <Button variant="outline" onClick={() => void listing.refetch()}>
                Retry
              </Button>
            </p>
          )}
          <div className="max-h-[42dvh] overflow-auto rounded border divide-y">
            {listing.data?.folders.map((item) => (
              <div key={item.id} className="flex items-center gap-3 p-3">
                <input
                  type="checkbox"
                  aria-label={`Select folder ${item.name}`}
                  checked={folders.includes(item.id)}
                  onChange={() => setFolders(toggle(folders, item.id))}
                />
                <Folder className="text-amber-600" size={18} />
                <button
                  className="text-left hover:underline"
                  onClick={() => navigate(item.id)}
                >
                  {item.name}
                </button>
                <span className="text-xs text-muted-foreground">
                  Folder and subfolders
                </span>
              </div>
            ))}
            {listing.data?.files.map((file) => (
              <label
                key={file.id}
                className="flex items-center gap-3 p-3 text-sm"
              >
                <input
                  type="checkbox"
                  aria-label={`Select file ${file.original_filename}`}
                  checked={files.includes(file.id)}
                  onChange={() => setFiles(toggle(files, file.id))}
                />
                <span className="min-w-0 flex-1 break-words">
                  {file.original_filename}
                </span>
                <span className="text-xs">{file.status}</span>
              </label>
            ))}
            {listing.data &&
              !listing.data.files.length &&
              !listing.data.folders.length && (
                <p className="p-3 text-sm">
                  No files or folders match this view.
                </p>
              )}
          </div>
          {listing.data && listing.data.file_total > 100 && (
            <div className="flex items-center gap-2 text-sm">
              <Button
                variant="outline"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                Previous files
              </Button>
              <span>
                Page {page + 1} of {Math.ceil(listing.data.file_total / 100)}
              </span>
              <Button
                variant="outline"
                disabled={(page + 1) * 100 >= listing.data.file_total}
                onClick={() => setPage(page + 1)}
              >
                Next files
              </Button>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm">
              {files.length} files and {folders.length} folders selected
            </span>
            <Button
              disabled={busy || (!files.length && !folders.length)}
              onClick={() => void inspect()}
            >
              {busy ? "Checking selection…" : "Review selected files"}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setFiles([])
                setFolders([])
              }}
            >
              Clear selection
            </Button>
          </div>
        </>
      ) : (
        <>
          <h3 className="font-semibold">
            {review.files.length} files to send to Financial
          </h3>
          <p className="text-sm">
            Files selected more than once are included once. Previously removed
            sources will be restored to Financial. Remove any unrelated files
            from this preview before sending.
          </p>
          <ul className="max-h-[35dvh] overflow-auto divide-y rounded border">
            {review.files.map((file) => (
              <li className="p-2 text-sm break-words" key={file.id}>
                {file.original_filename}
                {file.financial_removed ? " · removed, will be restored" : ""}
                <span className="block text-muted-foreground">
                  {usesPdfStatementReader(file)
                    ? "PDF statement reading"
                    : "Source review; no automatic transaction import"}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  aria-label={`Remove ${file.original_filename} from selection`}
                  onClick={() => {
                    setRequestId(newReviewId())
                    setReview({
                      ...review,
                      files: review.files.filter((item) => item.id !== file.id),
                    })
                  }}
                >
                  Remove from selection
                </Button>
              </li>
            ))}
          </ul>
          <p className="text-sm">
            PDFs enter statement preparation; existing evidence results are
            kept. Other formats are added as sources to review, with their
            processing status and a link to the original. Adding a source does
            not confirm its contents as transactions. No transactions are
            imported at this step.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!canEdit || !canUpload || busy || !review.files.length}
              onClick={async () => {
                setError("")
                setBusy(true)
                try {
                  const otherSources = review.files.filter(
                    (file) => !usesPdfStatementReader(file)
                  )
                  if (otherSources.length) {
                    const included = z
                      .object({
                        case_id: z.string(),
                        file_ids: z.array(z.string()),
                      })
                      .parse(
                        await fetchAPI(
                          `/api/financial/statement-import/selection/include?case_id=${caseId}`,
                          {
                            method: "POST",
                            body: {
                              files: otherSources.map((file) => ({
                                evidence_file_id: file.id,
                                expected_revision:
                                  file.financial_visibility_revision,
                              })),
                            },
                          }
                        )
                      )
                    if (
                      included.case_id !== caseId ||
                      included.file_ids.length !== otherSources.length ||
                      otherSources.some(
                        (file) => !included.file_ids.includes(file.id)
                      )
                    )
                      throw Error(
                        "The returned sources do not match this selection. Refresh Financial to check the result."
                      )
                    changed()
                  }
                  const pdfs = review.files.filter(usesPdfStatementReader)
                  let batchId: string | undefined
                  if (pdfs.length) {
                    const batch = z
                      .object({ id: z.string(), case_id: z.string() })
                      .parse(
                        await fetchAPI(
                          `/api/financial/statement-import/batches?case_id=${caseId}`,
                          {
                            method: "POST",
                            body: {
                              request_id: requestId,
                              file_ids: pdfs.map((file) => file.id),
                              folder_ids: [],
                            },
                          }
                        )
                      )
                    if (batch.case_id !== caseId)
                      throw Error("The batch belongs to another case.")
                    batchId = batch.id
                  }
                  changed()
                  const user = useAuthStore.getState().user
                  useStatementWorkspace
                    .getState()
                    .setOpen(
                      `${user?.id || user?.username || "anonymous"}:${caseId}`,
                      false
                    )
                  onStarted()
                  go(
                    `/cases/${caseId}/financial?view=statements${batchId && !otherSources.length ? `&batch=${encodeURIComponent(batchId)}` : "&files=1"}`
                  )
                } catch (error) {
                  setError(
                    (error instanceof Error
                      ? error.message
                      : "The selection could not be confirmed.") +
                      " Some sources may already be saved in Financial. Retry checks the same selection without creating copies."
                  )
                } finally {
                  setBusy(false)
                }
              }}
            >
              Send {review.files.length} files to Financial
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setRequestId(newReviewId())
                setReview(null)
              }}
            >
              Change selection
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
