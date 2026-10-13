import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  readingSentence,
  readUnreadStatements,
  type ReadingProgress as Progress,
} from "../lib/review-queue"

const plural = (n: number, one: string, many: string) =>
  `${n} ${n === 1 ? one : many}`

/**
 * Next to the status line: "Reading 12 of 40 files…" while statements are read
 * in the background, and the one action for statement files never read.
 */
export function ReadingProgress({
  caseId,
  reading,
}: {
  caseId: string
  reading?: Progress
}) {
  const access = useFinancialAccess()
  const canEdit = access.canEdit && access.canUpload
  const client = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const sentence = readingSentence(reading)
  const unread = reading?.unread_statement_files ?? 0
  if (!sentence && !unread && !message) return null
  const start = async () => {
    setBusy(true)
    setMessage("")
    try {
      const result = await readUnreadStatements(caseId)
      setMessage(
        result.added
          ? `${plural(result.added, "file is", "files are")} being read; statements appear in the queue as each file finishes.${result.copies ? ` ${plural(result.copies, "copy", "copies")} of files already in Financial ${result.copies === 1 ? "was" : "were"} not read again.` : ""}`
          : "Nothing new to read: these files are already being read or are copies of files in Financial."
      )
      await client.invalidateQueries({ queryKey: ["financial-review-queue", caseId] })
      await client.invalidateQueries({ queryKey: ["financial-review-status", caseId] })
      void client.invalidateQueries({ queryKey: ["financial-batches", caseId] })
    } catch (failure) {
      setMessage(
        `${failure instanceof Error ? failure.message : "Reading could not start."} Nothing was changed; try again.`
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm" aria-label="Statement reading">
      {sentence && (
        <p role="status" aria-live="polite">
          {sentence}
        </p>
      )}
      {!!unread && canEdit && (
        <Button size="sm" variant="outline" disabled={busy} onClick={() => void start()}>
          {busy
            ? "Starting…"
            : `Read ${plural(unread, "unread statement file", "unread statement files")}`}
        </Button>
      )}
      {message && <p role="status">{message}</p>}
    </div>
  )
}
