import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { readSavedFinancialReport } from "../lib/financial-report"
import { FinancialReportDocument } from "./FinancialReportDocument"

export function SavedFinancialReport({
  caseId,
  entry,
}: {
  caseId: string
  entry: CaseworkEntry
}) {
  const [open, setOpen] = useState(false)
  const load = useMutation({
    retry: false,
    mutationFn: () => readSavedFinancialReport(entry, caseId),
  })
  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true)
          load.mutate()
        }}
      >
        Open financial report
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-6xl max-h-[95vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Saved financial report</DialogTitle>
            <DialogDescription>
              This report retains the versions of the findings selected when it
              was prepared.
            </DialogDescription>
          </DialogHeader>
          {load.isPending && <p role="status">Opening saved report…</p>}
          {load.isError && (
            <p role="alert">
              The saved report could not be opened. {load.error.message}
            </p>
          )}
          {load.data && !load.isError && !load.isPending && (
            <FinancialReportDocument
              key={load.data.envelope.sha256}
              report={load.data}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
