import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import type {
  CaseworkEntry,
  CaseworkLink,
} from "@/features/workspace/casework-api"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import { fetchAPI } from "@/lib/api-client"
import { indirectWorkpaperReport } from "../lib/indirect-workpaper-report"
import { readSavedIndirect } from "../lib/saved-indirect"
import { indirectCatalog, verifyIndirectReview } from "../lib/indirect-review"
import { correctionMoney } from "../lib/correction-contract"
import { IndirectReviewWorkbench } from "./IndirectReviewWorkbench"

export function SavedIndirectFinding({
  entry,
  link,
  caseId,
}: {
  entry: CaseworkEntry
  link: CaseworkLink
  caseId: string
}) {
  const [open, setOpen] = useState(false)
  const [showCopy, setShowCopy] = useState(false)
  const [source, setSource] = useState<{ id: string; filename: string } | null>(
    null
  )
  const client = useQueryClient()
  const currentCatalog = () =>
    client.fetchQuery({
      queryKey: ["financial-ledger", caseId, "indirect-methods"],
      queryFn: async () => {
        const catalog = indirectCatalog.parse(
          await fetchAPI(
            `/api/financial/indirect-review-methods?case_id=${encodeURIComponent(caseId)}`
          )
        )
        if (catalog.case_id !== caseId)
          throw Error("The method belongs to another case.")
        return catalog
      },
    })
  const load = useMutation({
    retry: false,
    mutationFn: () =>
      readSavedIndirect(link, entry.links, caseId, currentCatalog),
  })
  const copy = useMutation({
    retry: false,
    mutationFn: async () => {
      const saved = await readSavedIndirect(
        link,
        entry.links,
        caseId,
        currentCatalog
      )
      // Historical definitions can be displayed. Editing must also be compatible
      // with the current calculation service, rather than silently dropping fields.
      return verifyIndirectReview(
        saved.review.envelope,
        await currentCatalog(),
        saved.review.value.inputs
      )
    },
    onSuccess: () => {
      setShowCopy(true)
      setOpen(false)
    },
  })
  const saved = !load.isPending && !load.isError ? load.data : undefined
  const value = saved?.review.value
  const reference = (field: {
    basis: string
    source_location: string
    source_file_id: string | null
  }) => {
    const file = value?.sources.find((item) => item.id === field.source_file_id)
    return (
      <div className="space-y-1 text-sm">
        <p className="whitespace-pre-wrap">
          {field.basis || "Explanation not recorded."}
        </p>
        <p>{field.source_location || "Page or location not recorded."}</p>
        {file ? (
          <Button
            variant="outline"
            className="h-auto whitespace-normal text-left"
            onClick={() => setSource(file)}
          >
            Open source: {file.filename}
          </Button>
        ) : (
          <p>Supporting file not recorded.</p>
        )}
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true)
          load.mutate()
        }}
      >
        Open saved workpaper
      </Button>
      {copy.data && (
        <Button variant="outline" onClick={() => setShowCopy(!showCopy)}>
          {showCopy ? "Hide revised copy" : "Continue revised copy"}
        </Button>
      )}
      {copy.data && (
        <div hidden={!showCopy} className="rounded border">
          <IndirectReviewWorkbench
            caseId={caseId}
            initialReview={copy.data}
            copiedFrom={entry.id}
          />
        </div>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-5xl max-h-[95vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Saved workpaper</DialogTitle>
            <DialogDescription>
              These are the inputs and results saved with this note. Use Create
              revised copy to make changes and save a new version alongside the
              original.
            </DialogDescription>
          </DialogHeader>
          {load.isPending && <p role="status">Opening saved workpaper…</p>}
          {load.isError && (
            <p role="alert">
              The saved workpaper could not be opened. {load.error.message}
            </p>
          )}
          {value && saved && (
            <>
              <h3 className="text-lg font-semibold">
                {value.method_label}: {value.inputs.subject}
              </h3>
              <p>
                {value.inputs.start_date} to {value.inputs.end_date} ·{" "}
                {value.inputs.currency}
              </p>
              <p className="font-semibold">
                {value.difference_minor === null
                  ? "No result yet. Complete the items listed below in a revised copy."
                  : `Calculated difference: ${correctionMoney(value.difference_minor, value.inputs.currency)}`}
              </p>
              <p>
                The result compares the amounts entered in this workpaper. Check
                their explanations and sources before drawing a conclusion.
              </p>
              <details>
                <summary className="cursor-pointer text-sm">
                  Explanation saved with the calculation
                </summary>
                <p className="text-sm mt-2">{value.limitation}</p>
              </details>
              {!!value.missing.length && (
                <div>
                  <h4 className="font-semibold">Still to complete</h4>
                  <ul className="list-disc pl-5">
                    {value.missing.map((item) => (
                      <li key={`${item.kind}:${item.id}`}>{item.label}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={copy.isPending}
                  onClick={() => {
                    if (copy.data) {
                      setShowCopy(true)
                      setOpen(false)
                    } else copy.mutate()
                  }}
                >
                  {copy.isPending
                    ? "Preparing copy…"
                    : copy.data
                      ? "Continue revised copy"
                      : "Create revised copy"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    const url = URL.createObjectURL(
                      new Blob([indirectWorkpaperReport(saved, entry)], {
                        type: "text/html;charset=utf-8",
                      })
                    )
                    const anchor = document.createElement("a")
                    anchor.href = url
                    anchor.download = `loupe-workpaper-${entry.id}.html`
                    anchor.click()
                    setTimeout(() => URL.revokeObjectURL(url), 1000)
                  }}
                >
                  Download workpaper report
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    const url = URL.createObjectURL(
                      new Blob(
                        [JSON.stringify(saved.review.envelope, null, 2)],
                        { type: "application/json" }
                      )
                    )
                    const anchor = document.createElement("a")
                    anchor.href = url
                    anchor.download = `loupe-${value.inputs.method}-workpaper.json`
                    anchor.click()
                    setTimeout(() => URL.revokeObjectURL(url), 1000)
                  }}
                >
                  Download workpaper data
                </Button>
              </div>
              {copy.isError && (
                <p role="alert">
                  A revised copy could not be prepared. {copy.error.message} The
                  original is retained.
                </p>
              )}
              <h4 className="font-semibold">Amounts used in the calculation</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="p-2">Item</th>
                      <th className="p-2">Amount</th>
                      <th className="p-2">Explanation and source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {value.lines.map((line) => (
                      <tr className="border-b align-top" key={line.id}>
                        <th className="p-2 text-left font-medium">
                          {line.sign === 1 ? "Add" : "Subtract"}: {line.label}
                        </th>
                        <td className="p-2 whitespace-nowrap">
                          {line.amount_minor === null
                            ? "Not entered"
                            : correctionMoney(
                                line.amount_minor,
                                value.inputs.currency
                              )}
                        </td>
                        <td className="p-2">{reference(line)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h4 className="font-semibold">Recorded checks</h4>
              {saved.catalog.requirements.map((check) => {
                const field = value.inputs.requirements[check.id]
                return (
                  <section
                    key={check.id}
                    className="rounded border p-3 space-y-2"
                  >
                    <h5 className="font-medium">
                      {check.label}:{" "}
                      {field?.status === "reviewed"
                        ? "Marked reviewed"
                        : "Still to review"}
                    </h5>
                    {field ? reference(field) : <p>No review recorded.</p>}
                  </section>
                )
              })}
              <p className="text-sm">
                Download workpaper report includes the saved amounts, checks,
                result and source references in a readable HTML file. Open it in
                a browser to read it or print it to PDF. Download workpaper data
                keeps the calculation file for restoring in Loupe.
              </p>
            </>
          )}
        </DialogContent>
      </Dialog>
      {source && (
        <DocumentViewer
          caseId={caseId}
          evidenceId={source.id}
          open
          onOpenChange={(isOpen) => !isOpen && setSource(null)}
          documentUrl={evidenceAPI.getFileUrl(source.id)}
          documentName={source.filename}
        />
      )}
    </div>
  )
}
