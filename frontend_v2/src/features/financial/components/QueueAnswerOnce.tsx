import { useState } from "react"
import { Button } from "@/components/ui/button"
import { CurrencyOptions } from "./CurrencyOptions"
import type { QueueEntry } from "../lib/review-queue"
import {
  entryFiles,
  listStatements,
  matchEntry,
  previewAndSave,
  type DetailChanges,
  type DetailsStatement,
} from "../lib/queue-statement-details"

const FIELD: Record<string, keyof DetailChanges> = {
  currency: "currency",
  institution: "institution",
  holder: "holder",
  account: "account_number",
}
const NAMES: Record<string, string> = {
  currency: "currency",
  institution: "bank name",
  holder: "account holder",
  account: "account number",
}
const FILES_PER_LISTING = 50

/**
 * One answer saved on every statement of a queue item (one statement, or a
 * group of the same account's statements waiting for the same answer): the
 * proposed value confirmed with one press, or a value entered once. Saved
 * through the same preview-then-save as the shared fix, so the server checks
 * each statement exactly as it checks a value entered in the statement.
 */
export function QueueAnswerOnce({
  caseId,
  reason,
  entries,
  proposal,
  actionLabel,
  onSaved,
}: {
  caseId: string
  /** currency, institution, holder, account or no_activity. */
  reason: string
  entries: QueueEntry[]
  proposal?: { value: string; label: string }
  actionLabel: string
  onSaved: (entries: QueueEntry[], message: string) => void
}) {
  const [value, setValue] = useState("")
  const [typing, setTyping] = useState(!proposal && reason !== "no_activity")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ message: string; failed: boolean } | null>(null)
  const n = entries.length
  const save = async (change: DetailChanges) => {
    if (busy) return
    setBusy(true)
    setResult(null)
    try {
      const files = [...new Set(entries.flatMap(entryFiles))]
      const rows: DetailsStatement[] = []
      for (let start = 0; start < files.length; start += FILES_PER_LISTING)
        rows.push(...(await listStatements(caseId, files.slice(start, start + FILES_PER_LISTING))).items)
      const targets = entries.map((entry) => matchEntry(entry, rows)).filter((row): row is DetailsStatement => !!row)
      if (!targets.length) {
        setResult({ failed: true, message: "Not saved: these statements are being read again. Try again in a minute." })
        return
      }
      const outcome = await previewAndSave(caseId, targets, change, reason === "no_activity" ? "fill_missing" : "replace")
      if (!outcome.saved) {
        const why = outcome.conflicts.length
          ? "a statement now reads this detail differently. Open it to check."
          : outcome.preview.items.find((item) => item.excluded_reason)?.excluded_reason || "nothing needed changing."
        setResult({ failed: true, message: `Not saved: ${why}` })
        return
      }
      const skipped = n - targets.length
      const message = `Saved on ${targets.length} ${targets.length === 1 ? "statement" : "statements"}.${skipped ? ` ${skipped} could not be changed now; ${skipped === 1 ? "it stays" : "they stay"} listed.` : ""}`
      setResult({ failed: false, message })
      onSaved(entries, message)
    } catch (error) {
      setResult({
        failed: true,
        message: `${error instanceof Error ? error.message : "Not saved."} Nothing was changed.`,
      })
    } finally {
      setBusy(false)
    }
  }
  const field = FIELD[reason]
  const name = NAMES[reason] ?? "detail"
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2" aria-label="Answer once">
      {reason === "no_activity" ? (
        <Button size="sm" disabled={busy} onClick={() => void save({ no_activity_confirmed: true })}>
          {busy ? "Saving…" : actionLabel}
        </Button>
      ) : (
        <>
          {proposal && !typing && (
            <>
              <Button size="sm" disabled={busy} onClick={() => void save({ [field]: proposal.value })}>
                {busy ? "Saving…" : actionLabel}
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setTyping(true)}>
                It is something else
              </Button>
            </>
          )}
          {typing && field && (
            <>
              {reason === "currency" ? (
                <select
                  aria-label={`Right ${name}`}
                  className="rounded border bg-background p-1 text-xs"
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                >
                  <option value="">Choose the printed currency</option>
                  <CurrencyOptions />
                </select>
              ) : (
                <input
                  aria-label={`Right ${name}`}
                  className="w-48 rounded border bg-background p-1 text-xs"
                  maxLength={128}
                  value={value}
                  placeholder={`Type the ${name}`}
                  onChange={(event) => setValue(event.target.value)}
                />
              )}
              <Button
                size="sm"
                disabled={busy || !value.trim()}
                onClick={() => void save({ [field]: value.trim() })}
              >
                {busy ? "Saving…" : n > 1 ? `Save on all ${n}` : `Save the ${name}`}
              </Button>
            </>
          )}
        </>
      )}
      {result && (
        <p role={result.failed ? "alert" : "status"} className="basis-full text-xs">
          {result.message}
        </p>
      )}
    </div>
  )
}
