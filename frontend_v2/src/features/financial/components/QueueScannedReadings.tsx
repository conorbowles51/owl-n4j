import { useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import type { PdfPageScan } from "../lib/pdf-page-scan"
import {
  scannedPageProposals,
  verifyQueuedMapping,
  type ScannedPageProposal,
} from "../lib/scanned-reading-queue"
export function QueueScannedReadings({
  scan,
  onBusy,
  onSaved,
}: {
  scan: PdfPageScan
  onBusy: (busy: boolean) => void
  onSaved?: (id: string) => void
}) {
  const [selected, setSelected] = useState<number[]>([]),
    [undated, setUndated] = useState(false),
    [phase, setPhase] = useState("idle"),
    [message, setMessage] = useState(""),
    [saved, setSaved] = useState<
      { page: number; id: string; count: number; group: number }[]
    >([])
  const active = useRef(true),
    lock = useRef(false),
    client = useQueryClient()
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  const eligible = scan.pages.filter(
    (p) =>
      p.source_revision &&
      (p.suggestions.length || (undated && p.undated_charges.length))
  )
  const chosen = eligible.filter((p) => selected.includes(p.page_number))
  const count = chosen.reduce(
    (n, p) =>
      n +
      new Set([
        ...p.suggestions.map((r) => r.row_index),
        ...(undated ? p.undated_charges.map((r) => r.row_index) : []),
      ]).size,
    0
  )
  const running = phase === "checking" || phase === "saving"
  const queue = async () => {
    if (lock.current || !count || count > 1000 || phase !== "idle") return
    lock.current = true
    onBusy(true)
    setPhase("checking")
    let attemptedPage: number | null = null
    let attemptedGroup: number | null = null
    try {
      const plans: ScannedPageProposal[] = []
      for (const page of chosen) {
        if (!active.current) return
        setMessage(`Checking original source on page ${page.page_number}…`)
        const source = await fetchAPI(
          candidateUrl(
            `candidate-sources/${encodeURIComponent(scan.evidence_file_id)}/pages/${page.page_number}`,
            scan.case_id
          ) + `&table_index=${scan.table_index}`
        )
        plans.push(...scannedPageProposals(scan, page, source, undated))
      }
      if (!active.current) return
      setPhase("saving")
      for (const [groupIndex, proposal] of plans.entries()) {
        if (!active.current) return
        attemptedPage = proposal.page_number
        attemptedGroup = groupIndex + 1
        setMessage(
          `Adding review group ${groupIndex + 1} of ${plans.length} (page ${attemptedPage})…`
        )
        const raw = await fetchAPI(
          candidateUrl("candidate-mappings", scan.case_id),
          { method: "POST", body: proposal }
        )
        const mapping = verifyQueuedMapping(raw, proposal)
        if (!active.current) return
        setSaved((old) => [
          ...old,
          {
            page: proposal.page_number,
            group: groupIndex + 1,
            id: mapping.id,
            count: mapping.candidates.length,
          },
        ])
        attemptedPage = null
      }
      setPhase("complete")
      setMessage(
        "Selected proposals are available in PDF readings. Existing review decisions are retained. No transactions were admitted."
      )
    } catch (error) {
      if (active.current) {
        setPhase("stopped")
        setMessage(
          `${error instanceof Error ? error.message : "The queue stopped."} ${attemptedPage === null ? "No further pages will be added. Review the saved pages below and scan again before continuing." : `The save outcome for review group ${attemptedGroup} on page ${attemptedPage} must be checked in saved PDF readings before retrying. Earlier saved groups remain available; later groups were not attempted.`}`
        )
      }
    } finally {
      lock.current = false
      onBusy(false)
      void client.invalidateQueries({
        queryKey: ["financial-candidates", scan.case_id, "list"],
      })
    }
  }
  return (
    <section
      aria-label="Queue scanned PDF readings"
      className="space-y-3 rounded border p-3"
    >
      <h4 className="font-semibold">Add scan proposals to pending review</h4>
      <p>
        Choose pages to avoid setting up each table again. All selected source
        revisions and cells are checked before the first save, then checked
        again by each page’s save. Each distinct row layout is saved separately,
        including when columns shift on one page. Column meanings remain
        proposals; account, dates, amounts and direction still need review
        before admission.
      </p>
      <fieldset disabled={phase !== "idle"} className="space-y-2">
        <label className="block">
          <input
            type="checkbox"
            checked={undated}
            onChange={(e) => {
              setUndated(e.target.checked)
              setSelected([])
            }}
          />{" "}
          Include undated fee and interest proposals, with dates unresolved
        </label>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => setSelected(eligible.map((p) => p.page_number))}
          >
            Select all eligible scan pages
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => setSelected([])}
          >
            Clear queue selection
          </Button>
        </div>
        <div className="grid max-h-64 gap-2 overflow-auto sm:grid-cols-3">
          {eligible.map((p) => (
            <label key={p.page_number}>
              <input
                type="checkbox"
                aria-label={`Queue proposals on page ${p.page_number}`}
                checked={selected.includes(p.page_number)}
                onChange={(e) =>
                  setSelected((old) =>
                    e.target.checked
                      ? [...old, p.page_number]
                      : old.filter((n) => n !== p.page_number)
                  )
                }
              />{" "}
              Page {p.page_number}:{" "}
              {
                new Set([
                  ...p.suggestions.map((r) => r.row_index),
                  ...(undated ? p.undated_charges.map((r) => r.row_index) : []),
                ]).size
              }{" "}
              possible rows
            </label>
          ))}
        </div>
        <p>
          {count} possible rows on {chosen.length} selected pages. Unchecked
          pages and unselected rows stay outside this queue.
        </p>
        {count > 1000 && (
          <p role="alert">Choose at most 1,000 possible rows in one queue.</p>
        )}
        <Button
          type="button"
          disabled={!count || count > 1000}
          onClick={() => void queue()}
        >
          Add selected scan proposals to review
        </Button>
      </fieldset>
      {message && (
        <p role={phase === "stopped" ? "alert" : "status"}>{message}</p>
      )}
      {running && (
        <p>
          Keep this view open while the selected pages are saved. Leaving stops
          further pages after the current request.
        </p>
      )}
      {!!saved.length && (
        <ul className="space-y-2">
          {saved.map((p) => (
            <li key={p.id}>
              Page {p.page}, review group {p.group}: {p.count} saved readings.{" "}
              {onSaved && (
                <Button
                  variant="outline"
                  disabled={running}
                  onClick={() => onSaved(p.id)}
                >
                  Open saved review group {p.group} for page {p.page}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
