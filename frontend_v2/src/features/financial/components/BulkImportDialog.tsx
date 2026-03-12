import { useState, useCallback } from "react"
import { Upload, FileSpreadsheet, AlertTriangle, CheckCircle2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Transaction } from "../api"

interface ParsedCorrection {
  node_key: string
  new_amount: number
  correction_reason: string
  matched: boolean
  original_amount?: number
}

interface BulkImportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  transactions: Transaction[]
  onSubmit: (
    corrections: { node_key: string; new_amount: number; correction_reason: string }[]
  ) => void
  isPending?: boolean
}

function parseCSV(text: string): string[][] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  return lines.map((line) => {
    const cells: string[] = []
    let current = ""
    let inQuotes = false
    for (const ch of line) {
      if (ch === '"') {
        inQuotes = !inQuotes
      } else if ((ch === "," || ch === "\t") && !inQuotes) {
        cells.push(current.trim())
        current = ""
      } else {
        current += ch
      }
    }
    cells.push(current.trim())
    return cells
  })
}

function detectColumns(headers: string[]): {
  keyCol: number
  amountCol: number
  reasonCol: number
} {
  const lower = headers.map((h) => h.toLowerCase().replace(/[^a-z]/g, ""))
  const keyCol = lower.findIndex(
    (h) =>
      h.includes("key") ||
      h.includes("id") ||
      h.includes("identifier") ||
      h.includes("nodekey")
  )
  const amountCol = lower.findIndex(
    (h) => h.includes("amount") || h.includes("value") || h.includes("newamount")
  )
  const reasonCol = lower.findIndex(
    (h) => h.includes("reason") || h.includes("note") || h.includes("comment")
  )
  return {
    keyCol: keyCol >= 0 ? keyCol : 0,
    amountCol: amountCol >= 0 ? amountCol : 1,
    reasonCol: reasonCol >= 0 ? reasonCol : 2,
  }
}

export function BulkImportDialog({
  open,
  onOpenChange,
  transactions,
  onSubmit,
  isPending,
}: BulkImportDialogProps) {
  const [parsed, setParsed] = useState<ParsedCorrection[]>([])
  const [error, setError] = useState("")
  const [fileName, setFileName] = useState("")

  const txMap = new Map(transactions.map((t) => [t.key, t]))

  const handleFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return

      setError("")
      setFileName(file.name)

      try {
        const text = await file.text()
        const rows = parseCSV(text)
        if (rows.length < 2) {
          setError("File must have a header row and at least one data row")
          return
        }

        const { keyCol, amountCol, reasonCol } = detectColumns(rows[0])
        const corrections: ParsedCorrection[] = []

        for (let i = 1; i < rows.length; i++) {
          const row = rows[i]
          const key = row[keyCol]
          const amount = parseFloat(row[amountCol])
          const reason = row[reasonCol] || "Bulk correction"

          if (!key || isNaN(amount)) continue

          const tx = txMap.get(key)
          corrections.push({
            node_key: key,
            new_amount: amount,
            correction_reason: reason,
            matched: !!tx,
            original_amount: tx?.amount,
          })
        }

        if (corrections.length === 0) {
          setError("No valid corrections found in file")
          return
        }

        setParsed(corrections)
      } catch {
        setError("Failed to parse file")
      }
    },
    [txMap]
  )

  const matchedCount = parsed.filter((c) => c.matched).length
  const unmatchedCount = parsed.length - matchedCount

  const handleSubmit = () => {
    const matched = parsed.filter((c) => c.matched)
    onSubmit(
      matched.map(({ node_key, new_amount, correction_reason }) => ({
        node_key,
        new_amount,
        correction_reason,
      }))
    )
  }

  const handleClose = (isOpen: boolean) => {
    if (!isOpen) {
      setParsed([])
      setError("")
      setFileName("")
    }
    onOpenChange(isOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <FileSpreadsheet className="size-4" />
            Bulk Import Corrections
          </DialogTitle>
          <DialogDescription className="text-xs">
            Upload a CSV or TSV file with columns: key/id, amount, reason
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Upload */}
          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border p-4 hover:bg-muted/50">
            <Upload className="size-6 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">
              {fileName || "Click to upload CSV, TSV, or XLSX"}
            </span>
            <input
              type="file"
              accept=".csv,.tsv,.txt,.xlsx"
              onChange={handleFile}
              className="hidden"
            />
          </label>

          {error && (
            <div className="flex items-center gap-2 rounded-md bg-red-500/10 px-3 py-2">
              <AlertTriangle className="size-4 text-red-500" />
              <p className="text-xs text-red-500">{error}</p>
            </div>
          )}

          {/* Preview */}
          {parsed.length > 0 && (
            <>
              <div className="flex items-center gap-2">
                <Badge variant="emerald">{matchedCount} matched</Badge>
                {unmatchedCount > 0 && (
                  <Badge variant="destructive">{unmatchedCount} unmatched</Badge>
                )}
              </div>

              <ScrollArea className="max-h-48">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-[10px]">Status</TableHead>
                      <TableHead className="text-[10px]">Key</TableHead>
                      <TableHead className="text-[10px] text-right">
                        Original
                      </TableHead>
                      <TableHead className="text-[10px] text-right">
                        New
                      </TableHead>
                      <TableHead className="text-[10px]">Reason</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {parsed.map((row, i) => (
                      <TableRow key={i}>
                        <TableCell className="py-1">
                          {row.matched ? (
                            <CheckCircle2 className="size-3.5 text-emerald-500" />
                          ) : (
                            <AlertTriangle className="size-3.5 text-red-500" />
                          )}
                        </TableCell>
                        <TableCell className="py-1 font-mono text-[10px]">
                          {row.node_key.length > 20
                            ? `${row.node_key.slice(0, 20)}...`
                            : row.node_key}
                        </TableCell>
                        <TableCell className="py-1 text-right font-mono text-[10px]">
                          {row.original_amount?.toLocaleString() || "—"}
                        </TableCell>
                        <TableCell className="py-1 text-right font-mono text-[10px]">
                          {row.new_amount.toLocaleString()}
                        </TableCell>
                        <TableCell className="py-1 text-[10px] max-w-[120px] truncate">
                          {row.correction_reason}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          {parsed.length > 0 && matchedCount > 0 && (
            <Button
              variant="primary"
              size="sm"
              onClick={handleSubmit}
              disabled={isPending}
            >
              {isPending
                ? "Applying..."
                : `Apply ${matchedCount} Correction${matchedCount !== 1 ? "s" : ""}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
