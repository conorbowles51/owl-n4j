import { useMemo, useRef, useState } from "react"
import { ApiError } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import type {
  AmountCorrection,
  BulkCorrectionResult,
  Transaction,
} from "../api"
import {
  parseCorrectionFile,
  type FileCorrection,
} from "../lib/bulk-correction-file"

interface PreviewCorrection extends FileCorrection {
  expected_amount?: number
  expected_raw_amount?: string
  currency?: string
}
interface BulkImportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  transactions: Transaction[]
  onSubmit: (corrections: AmountCorrection[]) => Promise<BulkCorrectionResult>
  isPending?: boolean
}

export function BulkImportDialog({
  open,
  onOpenChange,
  transactions,
  onSubmit,
  isPending,
}: BulkImportDialogProps) {
  const [parsed, setParsed] = useState<PreviewCorrection[]>([])
  const [error, setError] = useState("")
  const [fileName, setFileName] = useState("")
  const [reading, setReading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [result, setResult] = useState<BulkCorrectionResult | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const fileVersion = useRef(0)
  const lock = useRef(false)
  const busy = saving || isPending
  const txMap = useMemo(
    () => new Map(transactions.map((row) => [row.key, row])),
    [transactions]
  )

  const readFile = async (file: File) => {
    const version = ++fileVersion.current
    setParsed([])
    setError("")
    setResult(null)
    setAttempted(false)
    setUncertain(false)
    setFileName(file.name)
    setReading(true)
    try {
      if (file.size > 2 * 1024 * 1024)
        throw Error("Choose a correction file smaller than 2 MB.")
      if (!/\.(csv|tsv|txt)$/i.test(file.name))
        throw Error(
          "Choose a CSV or TSV file. Save an Excel workbook as CSV first."
        )
      const corrections = parseCorrectionFile(await file.text(), file.name)
      const preview = corrections.map((row) => {
        const transaction = txMap.get(row.node_key)
        if (!transaction)
          throw Error(
            `Line ${row.line}: record ${row.node_key} is not in the current list. Check the key or clear the financial filters.`
          )
        if (
          transaction.amount === null &&
          typeof transaction.raw_amount !== "string"
        )
          throw Error(
            `Line ${row.line}: the original amount text is missing. Reload this record before correcting it.`
          )
        return {
          ...row,
          expected_amount: transaction.amount ?? undefined,
          expected_raw_amount:
            transaction.amount === null
              ? (transaction.raw_amount ?? undefined)
              : undefined,
          currency: transaction.currency,
        }
      })
      if (version === fileVersion.current) setParsed(preview)
    } catch (cause) {
      if (version === fileVersion.current)
        setError(
          cause instanceof Error
            ? cause.message
            : "This file could not be read."
        )
    } finally {
      if (version === fileVersion.current) setReading(false)
    }
  }
  const downloadTemplate = () => {
    const quote = (value: string) => `"${value.replaceAll('"', '""')}"`
    const csv = [
      "key,amount,reason",
      ...transactions.map((row) => `${quote(row.key)},${row.amount ?? ""},`),
    ].join("\r\n")
    const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" })
    )
    const link = document.createElement("a")
    link.href = url
    link.download = "financial-amount-corrections.csv"
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const apply = async () => {
    if (lock.current || busy || reading || attempted || !parsed.length) return
    lock.current = true
    setSaving(true)
    setAttempted(true)
    setError("")
    try {
      setResult(
        await onSubmit(
          parsed.map(
            ({
              node_key,
              new_amount,
              correction_reason,
              expected_amount,
              expected_raw_amount,
            }) => ({
              node_key,
              new_amount,
              correction_reason,
              expected_amount,
              expected_raw_amount,
            })
          )
        )
      )
    } catch (cause) {
      setUncertain(
        !(cause instanceof ApiError) ||
          ![400, 401, 403, 404, 409, 422].includes(cause.status)
      )
      setError(
        cause instanceof Error
          ? cause.message
          : "The correction results could not be confirmed."
      )
    } finally {
      lock.current = false
      setSaving(false)
    }
  }
  const close = (next: boolean) => {
    if (lock.current || busy) return
    if (!next) {
      fileVersion.current++
      setParsed([])
      setError("")
      setFileName("")
      setReading(false)
      setAttempted(false)
      setResult(null)
    }
    onOpenChange(next)
  }
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Correct amounts from a file</DialogTitle>
          <DialogDescription>
            Choose a CSV or TSV containing key, amount and reason columns. Each
            key must identify a record in the current financial list.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm">
            Use amounts with up to two decimal places, such as 1250.50, without
            currency symbols or thousands separators. Include an explanation for
            every correction. Up to 1,000 records and 2 MB per file.
          </p>
          <Button
            variant="outline"
            disabled={
              busy || transactions.length === 0 || transactions.length > 1000
            }
            onClick={downloadTemplate}
          >
            Download correction template
          </Button>
          <p className="text-sm text-muted-foreground">
            The template contains the keys and amounts in the current list. Keep
            only the rows you want to correct, change their amounts and enter a
            reason on each row. Save the file as CSV, then choose it below.
            {transactions.length > 1000 &&
              " Filter the list to 1,000 records or fewer before downloading a template."}
          </p>
          <input
            ref={input}
            className="hidden"
            type="file"
            accept=".csv,.tsv,.txt"
            aria-label="Correction file"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0]
              event.target.value = ""
              if (file) void readFile(file)
            }}
          />
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => input.current?.click()}
          >
            Choose correction file
          </Button>
          {fileName && <p className="text-sm">Selected file: {fileName}</p>}
          {reading && <p role="status">Reading correction file...</p>}
          {error && (
            <div
              role="alert"
              className="rounded border border-destructive p-3 text-sm"
            >
              <p>{error}</p>
              <p>
                {uncertain
                  ? "Check the current records before trying again. A correction may have been saved even if its response was lost."
                  : "No corrections have been applied. Fix the file or reload the records, then choose the file again."}
              </p>
            </div>
          )}
          {parsed.length > 0 && (
            <>
              <p className="text-sm">
                {parsed.length} corrections ready to check. Amounts use each
                record's existing currency.
              </p>
              <div className="max-h-80 overflow-auto rounded border">
                <table
                  className="w-full text-sm"
                  aria-label="Correction file preview"
                >
                  <thead>
                    <tr>
                      {[
                        "File line",
                        "Record key",
                        "Current amount",
                        "New amount",
                        "Reason",
                      ].map((label) => (
                        <th className="p-2 text-left" key={label}>
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.map((row) => (
                      <tr key={row.node_key} className="border-t">
                        <td className="p-2">{row.line}</td>
                        <td className="p-2 break-all">{row.node_key}</td>
                        <td className="p-2 tabular-nums">
                          {row.expected_amount === undefined
                            ? row.expected_raw_amount || "(blank)"
                            : row.expected_amount.toLocaleString("en-IE", {
                                maximumFractionDigits: 20,
                              })}{" "}
                          {row.currency ?? "(currency not recorded)"}
                        </td>
                        <td className="p-2 tabular-nums">
                          {row.new_amount.toLocaleString("en-IE", {
                            maximumFractionDigits: 20,
                          })}{" "}
                          {row.currency ?? "(currency not recorded)"}
                        </td>
                        <td className="p-2 whitespace-pre-wrap break-words">
                          {row.correction_reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {result && (
            <section
              aria-label="Correction results"
              className="space-y-2 rounded border p-3 text-sm"
            >
              <p role="status">
                {result.corrected} of {result.total} corrections saved.{" "}
                {result.errors} failed.
              </p>
              {result.results.map((row) => (
                <p key={row.key}>
                  {row.key}:{" "}
                  {row.status === "corrected"
                    ? "Saved"
                    : row.reason || "Could not be saved"}
                </p>
              ))}
              {result.errors > 0 && (
                <p>
                  Keep the saved corrections. Check the failed records and
                  prepare a new file containing only the corrections still
                  needed.
                </p>
              )}
            </section>
          )}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => close(false)}
          >
            Close
          </Button>
          {!attempted && parsed.length > 0 && (
            <Button
              variant="primary"
              disabled={busy || reading}
              onClick={() => void apply()}
            >
              Apply {parsed.length} corrections
            </Button>
          )}
          {busy && <p role="status">Applying corrections...</p>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
