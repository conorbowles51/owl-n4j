import { announce } from "@/features/guidance/announce"
import { useState } from "react"
import { ArrowDown, ArrowUp, FileDown } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { PRIVILEGE_MARKING_LABELS, type PrivilegeMarking } from "@/features/cases/snapshots-api"
import { DEFAULT_SECTIONS, SECTION_LABELS, downloadCaseworkReport, moveSection, type CaseworkSection } from "../casework-report"

/** The case's Findings first (by default) with the evidence linked to each, then the chosen sections, as a PDF. */
export function CaseworkReportCard({ caseId }: { caseId: string }) {
  const [order, setOrder] = useState<CaseworkSection[]>(DEFAULT_SECTIONS)
  const [included, setIncluded] = useState<Record<CaseworkSection, boolean>>({ findings: true, theories: true, notes: false })
  const [marking, setMarking] = useState<PrivilegeMarking>("unmarked")
  const [busy, setBusy] = useState(false)
  const chosen = order.filter((s) => included[s])

  const exportReport = async () => {
    setBusy(true)
    try {
      const filename = await downloadCaseworkReport(caseId, chosen, marking)
      toast.success(`Report downloaded: ${filename}`)
      announce(caseId, { kind: "report-built", fileName: filename })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Report not produced")
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded border p-4" aria-labelledby="casework-report-heading">
      <h2 id="casework-report-heading" className="font-medium">Casework report</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        The case's Findings with the evidence linked to each, then Theories and Notes, in the order you set. The audit log
        and timeline are not included.
      </p>
      <ol className="mt-3 space-y-1">
        {order.map((section, index) => (
          <li key={section} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              id={`section-${section}`}
              checked={included[section]}
              onChange={(e) => setIncluded({ ...included, [section]: e.target.checked })}
            />
            <label htmlFor={`section-${section}`} className="flex-1">{index + 1}. {SECTION_LABELS[section]}</label>
            <Button variant="ghost" size="icon-sm" aria-label={`Move ${section} up`} disabled={index === 0} onClick={() => setOrder(moveSection(order, index, -1))}>
              <ArrowUp className="size-3.5" />
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label={`Move ${section} down`} disabled={index === order.length - 1} onClick={() => setOrder(moveSection(order, index, 1))}>
              <ArrowDown className="size-3.5" />
            </Button>
          </li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          Marking
          <select aria-label="Casework report privilege marking" value={marking} disabled={busy} onChange={(e) => setMarking(e.target.value as PrivilegeMarking)}>
            {(Object.keys(PRIVILEGE_MARKING_LABELS) as PrivilegeMarking[]).map((value) => (
              <option key={value} value={value}>{PRIVILEGE_MARKING_LABELS[value]}</option>
            ))}
          </select>
        </label>
        <Button size="sm" onClick={exportReport} disabled={busy || chosen.length === 0}>
          <FileDown className="size-3.5" />
          {busy ? "Preparing report…" : "Export casework report (PDF)"}
        </Button>
        <span className="text-xs text-muted-foreground">The marking is your choice, not a legal privilege determination.</span>
      </div>
    </section>
  )
}
