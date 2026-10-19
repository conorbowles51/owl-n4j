import { Button } from "@/components/ui/button"
import { retainedNames } from "../lib/statement-copies"
import {
  wholeCopyFileIds,
  type BatchStartChoiceValue,
  type BatchStartPreview,
} from "../lib/batch-start"

const files = (n: number) => `${n} ${n === 1 ? "file" : "files"}`

function findingText(
  finding: BatchStartPreview["copies"][number]["findings"][number]
) {
  const of = retainedNames(finding.retained.map((r) => r.filename))
  if (finding.kind === "identical_bytes_in_financial")
    return `Same file content as ${of}, already in Financial.`
  if (finding.kind === "identical_bytes_in_selection")
    return `Same file content as ${of}, also in this selection.`
  const { copies = 0, statements = 0 } = finding
  return copies >= statements
    ? `When last read, all ${statements} of its statements were copies of ${of} — nothing to review.`
    : `When last read, ${copies} of its ${statements} statements were copies of ${of}.`
}

/**
 * Shown before a batch starts: open batches already holding these files
 * (continue is the default), and files that are copies. Nothing is removed
 * unless the investigator chooses to leave copies out of the selection.
 */
export function BatchStartChoice({
  preview,
  selectedCount,
  busy,
  onChoose,
  onLeaveOut,
  onCancel,
  showPrepare = true,
}: {
  preview: BatchStartPreview
  selectedCount: number
  busy: boolean
  onChoose: (choice: BatchStartChoiceValue) => void
  onLeaveOut?: (fileIds: string[]) => void
  onCancel?: () => void
  /** Without an open batch, offer "Prepare N files" (off when the caller has its own button). */
  showPrepare?: boolean
}) {
  const suggested = preview.open_batches.find(
    (batch) => batch.id === preview.suggested_batch_id
  )
  const others = suggested ? suggested.other_files.length : 0
  const when = suggested
    ? new Date(suggested.created_at).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
      })
    : ""
  const leaveOut = wholeCopyFileIds(preview)
  return (
    <section
      aria-label="Before preparing these statements"
      className="space-y-3 rounded border border-amber-400 p-3"
    >
      {suggested && (
        <div className="space-y-1" role="status">
          <p className="font-medium">
            {suggested.covers_selection
              ? `${selectedCount === 1 ? "This file is" : `These ${selectedCount} files are`} already in the batch from ${when}. Continue it?`
              : `${suggested.shared_files} of these ${files(selectedCount)} are already in the batch from ${when}. Continue it?`}
          </p>
          <p className="text-sm text-muted-foreground">
            That batch has {files(suggested.file_count)} and{" "}
            {suggested.unfinished_statements} statements still to finish
            {suggested.files_reading
              ? `, with ${files(suggested.files_reading)} still being read`
              : ""}
            . Continuing keeps its corrections and saved work.
            {others > 0 &&
              ` The other ${files(others)} will be prepared in a new batch of their own.`}
            {preview.open_batches.length > 1 &&
              ` ${preview.open_batches.length - 1} other unfinished ${preview.open_batches.length === 2 ? "batch also holds" : "batches also hold"} some of these files.`}
          </p>
        </div>
      )}
      {preview.copies.length > 0 && (
        <div className="space-y-1">
          <p className="font-medium">
            {preview.copies.length === 1
              ? "1 selected file holds copies of statements kept elsewhere"
              : `${preview.copies.length} selected files hold copies of statements kept elsewhere`}
          </p>
          <ul className="max-h-40 space-y-1 overflow-auto text-sm">
            {preview.copies.map((file) => (
              <li key={file.file_id} className="break-words">
                <strong>{file.filename}</strong>:{" "}
                {file.findings.map(findingText).join(" ")}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            Copies are set aside automatically when read and are never deleted.
          </p>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {suggested ? (
          <>
            <Button
              autoFocus
              disabled={busy}
              onClick={() => onChoose("continue")}
            >
              {others > 0
                ? `Continue that batch and prepare the other ${files(others)}`
                : "Continue that batch"}
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => onChoose("new")}
            >
              Start a fresh batch with all {files(selectedCount)}
            </Button>
          </>
        ) : (
          showPrepare && (
            <Button autoFocus disabled={busy} onClick={() => onChoose("new")}>
              Prepare {files(selectedCount)}
            </Button>
          )
        )}
        {onLeaveOut &&
          leaveOut.length > 0 &&
          leaveOut.length < selectedCount && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => onLeaveOut(leaveOut)}
            >
              Leave the {files(leaveOut.length)} of copies out
            </Button>
          )}
        {onCancel && (
          <Button variant="ghost" disabled={busy} onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </section>
  )
}
