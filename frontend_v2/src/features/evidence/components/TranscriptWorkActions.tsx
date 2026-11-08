import { useId, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowRight,
  AudioLines,
  CheckCheck,
  ChevronDown,
  FilePenLine,
  LoaderCircle,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { randomRequestId } from "@/lib/browser-crypto"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  transcriptsAPI,
  type ProcessingPlan,
  type PlannedFile,
} from "../transcripts.api"
import { useEvidenceStore } from "../evidence.store"
import { useGuardedProcess } from "../hooks/use-guarded-process"
import { ProcessHoldDialog } from "./ProcessHoldDialog"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"

type QueueScope = "folder" | "subtree" | "case"
type PendingAction = "review" | "preview" | "process"

const SCOPE_LABELS: Record<QueueScope, string> = {
  folder: "This folder",
  subtree: "This folder and subfolders",
  case: "Entire case",
}

export function TranscriptWorkActions({ caseId }: { caseId: string }) {
  const titleId = useId()
  const folderId = useEvidenceStore((state) => state.currentFolderId)
  const [open, setOpen] = useState(false)
  const [scope, setScope] = useState<QueueScope>("folder")
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [readyPlan, setReadyPlan] = useState<ProcessingPlan | null>(null)
  const [readyFiles, setReadyFiles] = useState<PlannedFile[]>([])
  const gate = useGuardedProcess(caseId)
  const capability = useQuery({
    queryKey: ["audio-review-capabilities"],
    queryFn: transcriptsAPI.capabilities,
    retry: false,
    staleTime: 30000,
  })
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)
  const scopeFolder = scope === "case" ? null : folderId
  const recursive = scope !== "folder"
  const queue = useQuery({
    queryKey: ["transcript-queue", caseId, scopeFolder, recursive],
    queryFn: () => transcriptsAPI.queue(caseId, scopeFolder, recursive),
    enabled: capability.data?.enabled === true,
    retry: false,
    refetchInterval: 5000,
  })
  const busy = pendingAction !== null
  const awaiting = queue.data?.counts.awaiting_review ?? 0
  const ready = queue.data?.counts.ready ?? 0
  const total = awaiting + ready

  const run = async (action: PendingAction, operation: () => Promise<void>) => {
    if (busy) return
    setPendingAction(action)
    setActionError(null)
    try {
      await operation()
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Could not load recordings"
      setActionError(message)
      toast.error(message)
    } finally {
      setPendingAction(null)
    }
  }

  const openReview = async () => {
    const firstPage = await transcriptsAPI.queue(caseId, scopeFolder, recursive)
    const files = [...firstPage.items]
    let cursor = firstPage.next_cursor
    while (cursor !== null) {
      const page = await transcriptsAPI.queue(
        caseId,
        scopeFolder,
        recursive,
        "awaiting_review",
        cursor
      )
      files.push(...page.items)
      cursor = page.next_cursor
    }
    if (!files.length) {
      await queue.refetch()
      toast.info("No transcripts are awaiting review in this scope.")
      return
    }
    setOpen(false)
    useEvidenceStore.getState().setTranscriptQueue(files)
    useEvidenceStore.getState().openDetail(files[0].id, { startSeconds: 0 })
  }

  const previewReady = async () => {
    const plan = await transcriptsAPI.plan({
      case_id: caseId,
      folder_id: scopeFolder,
      recursive,
      ready_audio_only: true,
    })
    const files: PlannedFile[] = []
    let cursor: number | null = 0
    while (cursor !== null) {
      const page = await transcriptsAPI.files(plan.id, cursor)
      files.push(...page.items)
      cursor = page.next_cursor
    }
    if (!files.length) {
      await queue.refetch()
      toast.info("No reviewed recordings are ready in this scope.")
      return
    }
    setOpen(false)
    setReadyFiles(files)
    setReadyPlan(plan)
  }

  if (!capability.data?.enabled) return null

  return (
    <>
      <ProcessHoldDialog gate={gate} />
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (next) setActionError(null)
        }}
      >
        <PopoverTrigger asChild>
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1.5 text-xs"
            aria-label="Audio review"
            aria-describedby={
              total > 0 && !queue.isError ? titleId + "-count" : undefined
            }
          >
            <AudioLines className="size-3.5 text-muted-foreground" />
            Audio review
            {total > 0 && !queue.isError && (
              <span
                id={titleId + "-count"}
                className="flex min-w-5 items-center justify-center rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-primary"
                aria-label={
                  total.toLocaleString() +
                  (total === 1
                    ? " recording needs attention"
                    : " recordings need attention")
                }
              >
                {total.toLocaleString()}
              </span>
            )}
            <ChevronDown className="size-3 text-muted-foreground" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          sideOffset={8}
          className="max-h-[var(--radix-popover-content-available-height)] w-[352px] max-w-[calc(100vw-2rem)] overflow-y-auto p-0"
          aria-labelledby={titleId}
        >
          <div className="flex items-start justify-between gap-3 border-b border-border/70 px-4 py-3">
            <div>
              <h2 id={titleId} className="text-sm font-semibold">
                Audio transcripts
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Review recordings before processing.
              </p>
            </div>
            <Button
              size="icon-sm"
              variant="ghost"
              className="-mr-1 shrink-0"
              aria-label="Close audio review"
              onClick={() => setOpen(false)}
            >
              <X className="size-3.5" />
            </Button>
          </div>
          <div className="space-y-3 p-4">
            <div className="space-y-1.5">
              <label
                className="text-xs font-medium"
                htmlFor={titleId + "-scope"}
              >
                Show recordings from
              </label>
              <Select
                value={scope}
                onValueChange={(value) => {
                  setScope(value as QueueScope)
                  setActionError(null)
                }}
                disabled={busy}
              >
                <SelectTrigger
                  id={titleId + "-scope"}
                  aria-label="Transcript queue scope"
                  className="w-full text-xs"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(SCOPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {queue.isError ? (
              <div role="alert" className="rounded-lg bg-muted/50 p-3 text-xs">
                <p className="font-medium">
                  Could not load audio review status.
                </p>
                <p className="mt-1 text-muted-foreground">
                  Your saved transcripts are retained.
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-3 h-9"
                  disabled={queue.isFetching}
                  onClick={() => void queue.refetch()}
                >
                  Try again
                </Button>
              </div>
            ) : !queue.data ? (
              <div
                role="status"
                className="flex items-center gap-2 py-6 text-xs text-muted-foreground"
              >
                <LoaderCircle className="size-4 animate-spin" /> Loading
                recordings…
              </div>
            ) : total === 0 ? (
              <div className="rounded-lg bg-muted/40 px-4 py-5 text-center">
                <AudioLines className="mx-auto mb-2 size-5 text-muted-foreground/60" />
                <p className="text-sm font-medium">
                  No transcripts waiting here
                </p>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                  Transcripts appear here when transcription finishes. Select
                  audio files, then choose{" "}
                  <span className="font-medium text-foreground">
                    Process → Transcribe, then review
                  </span>
                  .
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="rounded-lg bg-muted/40 p-3">
                  <div className="flex items-start gap-2.5">
                    <FilePenLine className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3 text-sm font-medium">
                        <span>Awaiting review</span>
                        <span className="tabular-nums">
                          {awaiting.toLocaleString()}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {awaiting
                          ? "Check the words and speaker identities."
                          : "No recordings awaiting review."}
                      </p>
                    </div>
                  </div>
                  {awaiting > 0 && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-3 h-9 w-full justify-between"
                      disabled={busy}
                      onClick={() => void run("review", openReview)}
                    >
                      {pendingAction === "review"
                        ? "Opening transcripts…"
                        : "Review transcripts"}
                      {pendingAction === "review" ? (
                        <LoaderCircle className="size-3.5 animate-spin" />
                      ) : (
                        <ArrowRight className="size-3.5" />
                      )}
                    </Button>
                  )}
                </div>
                <div className="rounded-lg bg-muted/40 p-3">
                  <div className="flex items-start gap-2.5">
                    <CheckCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3 text-sm font-medium">
                        <span>Ready to process</span>
                        <span className="tabular-nums">
                          {ready.toLocaleString()}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {ready
                          ? "Reviewed and not yet processed."
                          : "Reviewed recordings will appear here."}
                      </p>
                    </div>
                  </div>
                  {ready > 0 && (
                    <Button
                      size="sm"
                      className="mt-3 h-9 w-full justify-between"
                      disabled={busy || !canEdit}
                      onClick={() => void run("preview", previewReady)}
                    >
                      {pendingAction === "preview"
                        ? "Loading preview…"
                        : "Preview ready audio"}
                      {pendingAction === "preview" ? (
                        <LoaderCircle className="size-3.5 animate-spin" />
                      ) : (
                        <ArrowRight className="size-3.5" />
                      )}
                    </Button>
                  )}
                  {ready > 0 && !canEdit && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Case edit access is required to process recordings.
                    </p>
                  )}
                </div>
              </div>
            )}
            {actionError && (
              <p role="alert" className="text-xs text-destructive">
                {actionError}
              </p>
            )}
          </div>
          <p className="border-t border-border/70 px-4 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
            Processing uses your saved, reviewed transcript.
          </p>
        </PopoverContent>
      </Popover>

      <Dialog
        open={!!readyPlan}
        onOpenChange={(next) => {
          if (!next && !busy) setReadyPlan(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Process {readyFiles.length} reviewed{" "}
              {readyFiles.length === 1 ? "recording" : "recordings"}
            </DialogTitle>
            <DialogDescription>
              Scope: {SCOPE_LABELS[scope].toLowerCase()}. Only the reviewed
              revisions listed here will be processed.
            </DialogDescription>
          </DialogHeader>
          <ul className="max-h-64 overflow-auto text-sm">
            {readyFiles.map((file) => (
              <li className="py-1" key={file.id}>
                {file.name}
              </li>
            ))}
          </ul>
          {actionError && (
            <p role="alert" className="text-xs text-destructive">
              {actionError}
            </p>
          )}
          <DialogFooter>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => setReadyPlan(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={busy}
              onClick={() =>
                void run("process", async () => {
                  const result = await gate.start({
                    fileIds: readyFiles.map((file) => file.id),
                    planId: readyPlan!.id,
                    requestKey: randomRequestId(),
                  })
                  if (result === "started") {
                    useEvidenceStore.getState().openSidebarTo("processing")
                    toast.success("Reviewed recordings queued for processing")
                  }
                  setReadyPlan(null)
                })
              }
            >
              {pendingAction === "process"
                ? "Starting processing…"
                : "Process reviewed transcripts"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
