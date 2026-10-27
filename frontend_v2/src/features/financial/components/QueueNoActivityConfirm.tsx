import { Disclosure } from "./Disclosure"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { QueueEntry } from "../lib/review-queue"
import {
  entryFiles,
  listStatements,
  matchEntry,
  previewDetails,
  type DetailsStatement,
  type PlannedDetails,
} from "../lib/queue-statement-details"

// The account-details listing reads each file; keep each request bounded.
const FILES_PER_LISTING = 50
const STATEMENTS_PER_PREVIEW = 200

const chunks = <T,>(items: T[], size: number) =>
  Array.from({ length: Math.ceil(items.length / size) }, (_, i) => items.slice(i * size, (i + 1) * size))

type Plan = {
  planned: PlannedDetails[]
  confirmable: number
  excluded: { filename: string; reason: string }[]
  unlisted: QueueEntry[]
}

/**
 * Confirms "no payments in this period" for many statements at once, through
 * the same per-statement confirmation the shared fix and the statement itself
 * use. The server decides each statement's eligibility in the preview (one
 * with payments, differing printed balances or an incomplete review is
 * excluded with its reason); nothing is saved until she confirms the count.
 */
export function QueueNoActivityConfirm({
  caseId,
  entries,
  chosen,
  onChoose,
  onDone,
}: {
  caseId: string
  /** Every listed statement waiting for this confirmation. */
  entries: QueueEntry[]
  chosen: Set<string>
  onChoose: (ids: Set<string>) => void
  onDone: (confirmed: QueueEntry[], line: string) => void
}) {
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState("")
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState("")
  const selected = entries.filter((entry) => chosen.has(entry.id))
  const reset = () => {
    setPlan(null)
    setError("")
  }
  const check = async () => {
    reset()
    try {
      const rows: DetailsStatement[] = []
      const files = [...new Set(selected.flatMap(entryFiles))]
      for (const [index, part] of chunks(files, FILES_PER_LISTING).entries()) {
        setBusy(`Listing statements (${index * FILES_PER_LISTING + 1}–${index * FILES_PER_LISTING + part.length} of ${files.length} files)…`)
        rows.push(...(await listStatements(caseId, part)).items)
      }
      const targets: DetailsStatement[] = []
      const unlisted: QueueEntry[] = []
      for (const entry of selected) {
        const row = matchEntry(entry, rows)
        if (row) targets.push(row)
        else unlisted.push(entry)
      }
      const planned: PlannedDetails[] = []
      for (const [index, part] of chunks(targets, STATEMENTS_PER_PREVIEW).entries()) {
        setBusy(`Checking which can be confirmed (${index * STATEMENTS_PER_PREVIEW + 1}–${index * STATEMENTS_PER_PREVIEW + part.length} of ${targets.length})…`)
        planned.push(await previewDetails(caseId, part, { no_activity_confirmed: true }, "fill_missing"))
      }
      const items = planned.flatMap((one) => one.preview.items)
      setPlan({
        planned,
        confirmable: planned.reduce((sum, one) => sum + one.preview.updated, 0),
        excluded: items
          .filter((item) => !Object.keys(item.changes).length)
          .map((item) => ({ filename: item.filename, reason: item.excluded_reason || "Nothing to confirm." })),
        unlisted,
      })
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The statements could not be checked.")
    } finally {
      setBusy("")
    }
  }
  const confirm = async () => {
    if (!plan) return
    let confirmed = 0
    try {
      for (const [index, one] of plan.planned.filter((p) => p.preview.updated).entries()) {
        setBusy(`Confirming (part ${index + 1})…`)
        confirmed += (await one.save()).updated
      }
      setPlan(null)
      setChecked(false)
      onChoose(new Set())
      onDone(selected, `${confirmed} ${confirmed === 1 ? "statement" : "statements"} confirmed with no payments`)
    } catch (failure) {
      setError(
        `${failure instanceof Error ? failure.message : "Confirming stopped."} ${confirmed} were confirmed before it stopped; the queue below shows where each stands.`
      )
      if (confirmed) onDone(selected, `${confirmed} confirmed before it stopped`)
    } finally {
      setBusy("")
    }
  }
  const reasons = new Map<string, number>()
  for (const item of plan?.excluded ?? []) reasons.set(item.reason, (reasons.get(item.reason) ?? 0) + 1)
  return (
    <section
      aria-label="Confirm no payments together"
      className="basis-full space-y-2 rounded border p-3 text-sm"
    >
      <p className="font-medium">Confirm statements with no payments together</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={!!busy}
          onClick={() => {
            reset()
            onChoose(new Set(entries.map((entry) => entry.id)))
          }}
        >
          Select all {entries.length}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={!!busy || !selected.length}
          onClick={() => {
            reset()
            onChoose(new Set())
          }}
        >
          Clear selection
        </Button>
        <span aria-label="Statements chosen to confirm">
          {selected.length} of {entries.length} selected
        </span>
      </div>
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={checked}
          disabled={!!busy}
          onChange={(event) => {
            reset()
            setChecked(event.target.checked)
          }}
        />
        I checked every page of the selected statements and confirm they contain no payments. A missing or
        unreadable page is not a period without payments.
      </label>
      {!plan ? (
        <Button size="sm" disabled={!checked || !selected.length || !!busy} onClick={() => void check()}>
          Check which of the {selected.length} can be confirmed
        </Button>
      ) : (
        <div className="space-y-2" role="status" aria-label="What will be confirmed">
          <p>
            <strong>{plan.confirmable}</strong> of {selected.length} selected{" "}
            {plan.confirmable === 1 ? "statement" : "statements"} will be confirmed with no payments.
            {plan.excluded.length > 0 &&
              ` ${plan.excluded.length} cannot be: ${[...reasons].map(([reason, n]) => `${n} ${reason.charAt(0).toLowerCase()}${reason.slice(1)}`).join(" ")}`}
            {plan.unlisted.length > 0 &&
              ` ${plan.unlisted.length} could not be listed now (their file is being read again); open them from the queue.`}
          </p>
          {plan.excluded.length > 0 && (
            <Disclosure label={<>Which {plan.excluded.length} cannot be confirmed (all {plan.excluded.length} listed)</>}>
              <ul className="mt-1 list-disc pl-5">
                {plan.excluded.map((item, index) => (
                  <li key={index}>
                    {item.filename}: {item.reason}
                  </li>
                ))}
              </ul>
            </Disclosure>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={!plan.confirmable || !!busy} onClick={() => void confirm()}>
              Confirm no payments for {plan.confirmable}{" "}
              {plan.confirmable === 1 ? "statement" : "statements"}
            </Button>
            <Button size="sm" variant="ghost" disabled={!!busy} onClick={reset}>
              Back
            </Button>
          </div>
        </div>
      )}
      {busy && <p role="status">{busy}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
