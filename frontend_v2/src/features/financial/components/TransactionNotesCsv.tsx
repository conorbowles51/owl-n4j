import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { sha256 } from "@noble/hashes/sha2.js"
import { caseworkAPI } from "@/features/workspace/casework-api"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import type { LedgerTransaction } from "../api"
import {
  captureFindingPayments,
  emptyFinding,
  findingBody,
  findingTags,
} from "../lib/investigator-finding"
import {
  parseNotesCsv,
  downloadCsv,
  transactionCsv,
} from "../lib/transaction-csv"

export function TransactionNotesCsv({
  caseId,
  rows,
  onClose,
}: {
  caseId: string
  rows: LedgerTransaction[]
  onClose: () => void
}) {
  const client = useQueryClient()
  const [notes, setNotes] = useState<ReturnType<typeof parseNotesCsv>>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [progress, setProgress] = useState("")
  const references = new Map<string, LedgerTransaction[]>()
  for (const row of rows) {
    const key = (row.ref_id || row.key).toUpperCase()
    references.set(key, [...(references.get(key) ?? []), row])
  }
  const preview = notes.map((note) => ({
    ...note,
    matches: references.get(note.refId.toUpperCase()) ?? [],
  }))
  const matched = preview.filter((note) => note.matches.length === 1)
  const save = async () => {
    setBusy(true)
    setError("")
    let saved = 0,
      skipped = 0
    try {
      for (const note of matched) {
        const row = note.matches[0]
        const digest = Array.from(
          sha256(
            new TextEncoder().encode(
              JSON.stringify([caseId, row.key, note.notes])
            )
          ),
          (v) => v.toString(16).padStart(2, "0")
        ).join("")
        const tag = `financial-csv-${digest.slice(0, 48)}`
        // An uncertain previous response can be retried without creating the same note again.
        const existing = await caseworkAPI.list(caseId, { tag, limit: 1 })
        if (
          existing.entries.some(
            (e) => e.case_id === caseId && e.tags.includes(tag)
          )
        )
          skipped++
        else {
          const links = await captureFindingPayments(caseId, [row.key])
          const draft = {
            ...emptyFinding,
            kind: "observation" as const,
            title: `Note · ${note.refId}`,
            explanation: note.notes,
          }
          const entry = await caseworkAPI.create(caseId, {
            entry_type: "note",
            title: draft.title,
            body: findingBody(draft),
            tags: [...findingTags(draft), tag],
            links,
          })
          if (entry.case_id !== caseId)
            throw Error("The note response did not match this case.")
          saved++
        }
        setProgress(
          `${saved} notes saved; ${skipped} already present; ${matched.length - saved - skipped} remaining.`
        )
      }
      await client.invalidateQueries({ queryKey: ["casework", caseId] })
    } catch (e) {
      setError(
        `${e instanceof Error ? e.message : "Could not save notes."} Completed notes are retained. Retry checks for notes already saved.`
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import notes from CSV</DialogTitle>
          <DialogDescription>
            Match notes to transaction references in the current account and
            date range. Existing notes and transaction values are kept.
          </DialogDescription>
        </DialogHeader>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            downloadCsv(
              transactionCsv(rows),
              "loupe-transaction-notes-template.csv"
            )
          }
        >
          Download references and blank notes column
        </Button>
        <label className="text-sm">
          CSV with ref_id and notes columns
          <input
            className="mt-1 block w-full rounded border p-2"
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            aria-label="Notes CSV file"
            onChange={async (e) => {
              setNotes([])
              setProgress("")
              setError("")
              const file = e.target.files?.[0]
              if (!file) return
              if (file.size > 2 * 1024 * 1024) {
                setError("Use a CSV smaller than 2 MB.")
                return
              }
              try {
                setNotes(parseNotesCsv(await file.text()))
              } catch (err) {
                setError(
                  err instanceof Error ? err.message : "Could not read CSV."
                )
              }
            }}
          />
        </label>
        {error && (
          <p role="alert" className="text-sm">
            {error}
          </p>
        )}
        {notes.length > 0 && (
          <>
            <p className="text-sm">
              {matched.length} notes match exactly one transaction.{" "}
              {notes.length - matched.length} unmatched or ambiguous references
              will be skipped.
            </p>
            <div className="max-h-64 overflow-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr>
                    <th className="p-2 text-left">Reference</th>
                    <th className="p-2 text-left">Note</th>
                    <th className="p-2 text-left">Match</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.map((n, i) => (
                    <tr key={i} className="border-t">
                      <td className="p-2">{n.refId}</td>
                      <td className="whitespace-pre-wrap p-2">{n.notes}</td>
                      <td className="p-2">
                        {n.matches.length === 1
                          ? n.matches[0].description
                          : n.matches.length
                            ? "Ambiguous — skipped"
                            : "Not found — skipped"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Button
              disabled={busy || !matched.length}
              onClick={() => void save()}
            >
              {busy
                ? "Saving notes…"
                : `Import ${matched.length} matching notes`}
            </Button>
          </>
        )}
        {progress && (
          <p role="status" className="text-sm">
            {progress} Saved notes appear on the transactions and in Findings.
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
