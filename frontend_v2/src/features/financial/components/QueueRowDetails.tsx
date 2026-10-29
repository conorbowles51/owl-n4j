import { useState } from "react"
import { Button } from "@/components/ui/button"
import { CurrencyOptions } from "./CurrencyOptions"
import { FieldNeed } from "./FieldNeed"
import type { QueueEntry } from "../lib/review-queue"
import { FIELDS, current, fieldsFor, needsRowDetails, type Field } from "../lib/queue-row-fields"
import {
  changeLine,
  entryFiles,
  listStatements,
  matchEntry,
  previewAndSave,
  type DetailChanges,
} from "../lib/queue-statement-details"

/**
 * Currency, bank and account holder fixed on the queue row itself, without
 * opening the statement or a dialog. Saved through the same preview-then-save
 * path as the shared fix, so the server checks it exactly as it checks a
 * shared value; the row then says where the statement stands.
 */
export function QueueRowDetails({
  caseId,
  entry,
  onSaved,
  startOpen = false,
}: {
  caseId: string
  entry: QueueEntry
  onSaved: (entry: QueueEntry, message: string) => void
  /** Open with the fields showing (the quick preview); otherwise only when one of them is what it waits for. */
  startOpen?: boolean
}) {
  const proposal = (field: Field) =>
    field === "currency" || field === "institution" || field === "holder" ? entry.proposals?.[field] : undefined
  const fields = fieldsFor(entry)
  const initial = () =>
    Object.fromEntries(
      fields.map(([field]) => [field, current(entry, field) || proposal(field)?.value || ""])
    ) as Record<Field, string>
  const [open, setOpen] = useState(startOpen || needsRowDetails(entry))
  const [values, setValues] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ message: string; failed: boolean } | null>(null)
  const changed = fields.filter(
    ([field]) => values[field].trim() && values[field].trim() !== current(entry, field)
  )
  const save = async () => {
    if (!changed.length || busy) return
    setBusy(true)
    setResult(null)
    try {
      const listed = await listStatements(caseId, entryFiles(entry))
      const target = matchEntry(entry, listed.items)
      if (!target) {
        setResult({
          failed: true,
          message:
            listed.notices[0]?.message ??
            "This statement cannot be changed here now (its file is being read again). Open it to fix it.",
        })
        return
      }
      const change: DetailChanges = Object.fromEntries(
        changed.map(([field]) => [field, values[field].trim()])
      )
      const outcome = await previewAndSave(caseId, [target], change)
      const item = outcome.preview.items[0]
      if (outcome.conflicts.length) {
        const field = outcome.conflicts[0].conflicts![0]
        setResult({
          failed: true,
          message: `Not saved: the statement now reads ${field} as ${outcome.conflicts[0].refreshed?.[field]?.current || "something else"}. Check the value and save again, or open the statement.`,
        })
        setValues(initial())
        return
      }
      if (!outcome.saved) {
        setResult({
          failed: true,
          message: `Not saved: ${item?.excluded_reason || "these values are already saved."}`,
        })
        return
      }
      const message = `Saved ${item ? changeLine(item) : "the details"}.`
      setResult({ failed: false, message })
      onSaved(entry, message)
    } catch (error) {
      setResult({
        failed: true,
        message: `${error instanceof Error ? error.message : "The details could not be saved."} Nothing was changed; your values are kept.`,
      })
    } finally {
      setBusy(false)
    }
  }
  if (!open)
    return (
      <Button size="sm" variant="ghost" className="px-1" onClick={() => setOpen(true)}>
        {fields.length > FIELDS.length
          ? `Change currency, bank or holder, or add ${fields
              .slice(FIELDS.length)
              .map(([, label]) => label.toLowerCase())
              .join(", ")} here`
          : "Change currency, bank or holder here"}
      </Button>
    )
  return (
    <fieldset
      aria-label={`Details of ${entry.filename}`}
      disabled={busy}
      className="mt-2 flex flex-wrap items-end gap-2 rounded border bg-muted/30 p-2 text-xs"
    >
      {fields.map(([field, label]) => (
        <label key={field} className="flex flex-col gap-1">
          <span>
            {label}
            <FieldNeed required />
            {!current(entry, field) && proposal(field) && values[field] === proposal(field)!.value && (
              <span className="text-muted-foreground"> (proposed: {proposal(field)!.label})</span>
            )}
          </span>
          {field === "currency" ? (
            <select
              aria-label={`Currency for ${entry.filename}`}
              className="rounded border bg-background p-1"
              value={values.currency}
              onChange={(event) => setValues({ ...values, currency: event.target.value })}
            >
              <option value="">Choose printed currency</option>
              <CurrencyOptions />
            </select>
          ) : field.startsWith("period_") ? (
            <input
              type="date"
              aria-label={`${label} for ${entry.filename}`}
              className="rounded border bg-background p-1"
              value={values[field]}
              onChange={(event) => setValues({ ...values, [field]: event.target.value })}
            />
          ) : (
            <input
              aria-label={`${label} for ${entry.filename}`}
              className="w-44 rounded border bg-background p-1"
              maxLength={128}
              value={values[field]}
              placeholder={current(entry, field) ? undefined : "Not read"}
              onChange={(event) => setValues({ ...values, [field]: event.target.value })}
            />
          )}
        </label>
      ))}
      <Button size="sm" disabled={!changed.length || busy} onClick={() => void save()}>
        {busy
          ? "Saving…"
          : changed.length
            ? `Save ${changed.map(([, label]) => label.toLowerCase()).join(", ")}`
            : "Nothing changed"}
      </Button>
      {result && (
        <p
          role={result.failed ? "alert" : "status"}
          aria-label={`Result for ${entry.filename}`}
          className="basis-full"
        >
          {result.message}
        </p>
      )}
    </fieldset>
  )
}
