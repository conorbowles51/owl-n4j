/**
 * Explain held files and record a person's decision before offering processing.
 * Sending to the ledger remains separate from admitting to document processing.
 * The backend rechecks the file and enforces the decision before any send.
 *
 * Why it does not reuse RouteBadge
 * --------------------------------
 *
 * `RouteBadge` renders nothing for `not_native`, because an ordinary document
 * needs no label on a list of a thousand files.  But a `not_native` file can be
 * held: the service sets `blocks_document_processing` for reasons its outcome
 * word does not carry, and the gate honours that flag.  Such a file appears in
 * this list, and reusing the badge would print its name with no label beside
 * it -- the one row here that explained nothing.
 */

import { useState } from "react"
import { AlertTriangle } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import {
  ROUTE_OUTCOME_LABEL,
  ROUTE_OUTCOME_VARIANT,
  belongsToLedger,
  routeDetailLines,
  formatLabel,
} from "../utils/financial-route"
import { describeHold } from "../hooks/use-guarded-process"
import type {
  HeldFile,
  HeldRequest,
  ProcessGate,
} from "../hooks/use-guarded-process"
import { SendToLedgerDialog } from "@/features/financial/components/SendToLedgerDialog"

interface ProcessHoldDialogProps {
  /**
   * The whole gate, not its pieces.
   *
   * See {@link ProcessGate}: three separate props would be three chances to
   * wire two of them.
   */
  gate: ProcessGate
}

/**
 * The heading, which says how many rather than what became of the rest.
 *
 * Four shapes, because a hold has four: nothing could be checked, some files
 * could not be checked but the rest were sorted, files were held, or both.
 * `held.length` alone gets the second of those wrong -- it would read
 * "0 files were held back" over a dialog that exists precisely because
 * something went unanswered.
 *
 * Deliberately not exported.  Its four shapes are asserted through the rendered
 * heading rather than by calling it, which is both closer to what a person sees
 * and the reason this file can stay a file that exports only a component --
 * `react-refresh/only-export-components`, which is a real constraint here and
 * not a style rule.
 */
function holdTitle(held: HeldRequest): string {
  if (held.sent?.length) return "Processing requested"
  if (held.held.length === 0 && held.cleared.length === 0)
    return "Nothing was sent"
  if (held.held.length === 0) return "Some files could not be checked"
  return held.held.length === 1
    ? "1 file was held back"
    : `${held.held.length} files were held back`
}

export function ProcessHoldDialog({ gate }: ProcessHoldDialogProps) {
  // Declared before the early return, so that a hold arriving does not change
  // how many hooks this component runs.
  const [isReleasing, setIsReleasing] = useState(false)
  // The held file currently being offered to the ledger, or null. Held here
  // rather than in each row so that only one can be open at a time: the send
  // dialog asks for a period, and two of them open at once would invite the
  // reader to answer that question twice with no sign the answers differed.
  const [sending, setSending] = useState<HeldFile | null>(null)
  const held = gate.held
  const busy = isReleasing || gate.isBusy

  if (!held) return null

  const heldFiles = held.held
  const clearedCount = held.cleared.length

  const handleRelease = async () => {
    setIsReleasing(true)
    // `release` reports rather than throws, and announces its own failure --
    // see `send` in the gate. So a zero here has already been explained, and
    // saying anything more would be a second message about one event.
    const sent = await gate.release()
    // Reset after awaiting rather than on unmount: the dialog closes by `held`
    // becoming null, which renders nothing but keeps this state alive. Left
    // true, the next hold would open showing a spinner over a button nobody
    // had pressed.
    setIsReleasing(false)
    if (sent > 0)
      toast.success(`Processing ${sent} file${sent === 1 ? "" : "s"}`)
  }

  return (
    <>
      <Dialog
        open
        onOpenChange={(open) => {
          // Escape and the overlay dismiss, they do not release. Losing a
          // modal by accident must not send anything anywhere.
          if (!open && !busy) gate.dismiss()
        }}
      >
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-amber-500" />
              {holdTitle(held)}
            </DialogTitle>
            <DialogDescription>{describeHold(held)}</DialogDescription>
          </DialogHeader>

          {heldFiles.length > 0 && (
            <div className="max-h-64 space-y-3 overflow-y-auto pr-1">
              {heldFiles.map((file) => (
                <div
                  key={file.file_id}
                  className="rounded-md border border-border/70 bg-muted/30 p-3"
                >
                  <div className="flex items-start gap-2">
                    <Badge
                      variant={ROUTE_OUTCOME_VARIANT[file.outcome]}
                      className="shrink-0 text-[10px]"
                    >
                      {ROUTE_OUTCOME_LABEL[file.outcome]}
                    </Badge>
                    {/* The id is the fallback because a file with no name still
                      has to be findable on the list behind this dialog. */}
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">
                      {file.file_name ?? file.file_id}
                    </span>
                  </div>
                  {routeDetailLines(file).map((line) => (
                    <p
                      key={line}
                      className="mt-1.5 text-xs text-muted-foreground"
                    >
                      {line}
                    </p>
                  ))}
                  {/* Offered only for `native`, which is narrower than the set
                    of files held here and deliberately so. `belongsToLedger`
                    is not `blocksDocumentProcessing`: an `ambiguous` file is
                    also held, but sending it to the ledger would fail there
                    too, because the reading requires exactly one format to
                    claim the bytes. A button that could only be refused is
                    worse than no button. */}
                  {belongsToLedger(file.outcome) && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-2.5"
                      data-testid={`send-to-ledger-${file.file_id}`}
                      disabled={busy || held.sent?.includes(file.file_id)}
                      onClick={() => setSending(file)}
                    >
                      Send to ledger
                    </Button>
                  )}
                  <FileAdmissionControl
                    key={`${gate.caseId}:${file.file_id}`}
                    gate={gate}
                    file={file}
                    busy={busy}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Shown on its own only when there is no file list to attach it to.
            Alongside a list it would repeat the description above it. */}
          {held.checkError && heldFiles.length === 0 && (
            <p className="rounded-md border border-border/70 bg-muted/30 p-3 text-xs text-muted-foreground">
              {held.checkError}
            </p>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={gate.dismiss} disabled={busy}>
              {clearedCount > 0 ? "Cancel" : "Close"}
            </Button>
            {clearedCount > 0 && (
              <Button onClick={handleRelease} disabled={busy}>
                {isReleasing && <LoadingSpinner className="mr-1.5 size-3.5" />}
                Process {clearedCount} other file{clearedCount === 1 ? "" : "s"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* A sibling rather than a child, so it is not unmounted by the hold
        dialog closing underneath it, and so neither one's escape handling has
        to know about the other. The hold stays open behind it: sending one
        bank file to the ledger says nothing about the rest of the request,
        and the reader still has the cleared files to decide about. */}
      {sending && (
        <SendToLedgerDialog
          caseId={gate.caseId}
          fileId={sending.file_id}
          fileName={sending.file_name ?? null}
          open
          onClose={() => setSending(null)}
        />
      )}
    </>
  )
}

/** A separate form per file: one person's reason must not silently cover a batch. */
function FileAdmissionControl({
  gate,
  file,
  busy,
}: {
  gate: ProcessGate
  file: HeldFile
  busy: boolean
}) {
  const [reason, setReason] = useState("")
  const reading = gate.held?.admissions?.[file.file_id]
  const error = gate.held?.admissionErrors?.[file.file_id]
  const processingError = gate.held?.processingErrors?.[file.file_id]
  const sent = gate.held?.sent?.includes(file.file_id)
  const inputId = `admission-reason-${file.file_id}`
  if (sent)
    return (
      <p role="status" className="mt-3 text-sm">
        Processing requested for this file. Follow its progress in the evidence
        list.
      </p>
    )
  if (file.outcome === "not_found") return null
  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      <p className="text-sm font-medium">Process as a document</p>
      <p className="text-xs text-muted-foreground">
        Your name, reason and the file check will be recorded in the case
        decision history. This does not add verified transactions to the ledger.
      </p>
      {(file.outcome === "native" || reading?.routeOutcome === "native") && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          The processing service still refuses files it identifies as native
          bank records, even after a decision is recorded. Use Send to ledger
          for a supported bank file.
        </p>
      )}
      {reading && (
        <div role="status" className="space-y-1 text-xs">
          <p>{processingError ? "Decision retained." : reading.message}</p>
          {reading.reason && (
            <p>
              {reading.reasonLabel}: {reading.reason}
            </p>
          )}
          {reading.routeOutcome && (
            <p>Latest file check: {reading.routeOutcome}</p>
          )}
          {reading.detectedFormat && (
            <p>Format: {formatLabel(reading.detectedFormat)}</p>
          )}
          {reading.claimants.length > 0 && (
            <p>Claimed by: {reading.claimants.map(formatLabel).join(", ")}</p>
          )}
        </div>
      )}
      {processingError && (
        <p role="alert" className="text-xs text-destructive">
          {processingError}
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      {reading?.canProcess ? (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => void gate.processAdmitted(file.file_id)}
        >
          {processingError ? "Retry processing this file" : "Process this file"}
        </Button>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void gate.recordAdmission(file.file_id, reason)
          }}
          className="space-y-2"
        >
          <label htmlFor={inputId} className="block text-xs">
            Reason for proceeding with {file.file_name ?? file.file_id}
          </label>
          <Textarea
            id={inputId}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            disabled={busy}
          />
          <Button
            type="submit"
            size="sm"
            variant="outline"
            disabled={busy || !reason.trim()}
          >
            Record decision
          </Button>
        </form>
      )}
    </div>
  )
}
