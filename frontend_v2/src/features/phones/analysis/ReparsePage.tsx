import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { failureText } from "../api"
import { analysisAPI } from "./analysis-api"
import { ApproachLayout } from "./ApproachLayout"
import { TABS, reparseWords } from "./reparse-words"

/**
 * 05 section 17.3: each phone read again by a pinned independent tool (ALEAPP for Android, iLEAPP for iOS) from the
 * production's verified files, and compared with the report. The tool's rows are shown as read by that tool and
 * version, beside the report's records, never merged into them.
 */
export const WHAT_IT_DOES =
  "Reads each phone again with an independent open-source tool (ALEAPP for Android, iLEAPP for iOS) from the files in the production whose fingerprints match the report, then compares what the tool read with the report: totals, records only one side has, and records whose time or content differs. The tool's readings are shown as the tool's, never as the report's records."

type Run = { id: string; tool: string; tool_version: string; status: string; seconds: number | null; peak_rss_mb: number | null; error: string | null; tree: { placed?: number } | null; finished_at: string | null }
type Phone = { extraction_id: string; label: string; os: string | null; os_family: string | null; runs: Run[] }
const TOOL: Record<string, string> = { aleapp: "ALEAPP", ileapp: "iLEAPP" }

export function ReparseRuns({ caseId }: { caseId: string }) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ["phone-reparse-runs", caseId],
    queryFn: () => fetchAPI<{ phones: Phone[]; total: number }>(`/api/phones/reparse/runs?case_id=${encodeURIComponent(caseId)}`),
    refetchInterval: (query) => (query.state.data?.phones.some((p) => p.runs[0] && ["queued", "running"].includes(p.runs[0].status)) ? 3000 : false),
  })
  const start = useMutation({
    mutationFn: (extractionId: string) => fetchAPI("/api/phones/reparse", { method: "POST", body: { case_id: caseId, extraction_id: extractionId } }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["phone-reparse-runs", caseId] }),
  })
  if (q.isError) return <p role="alert">{failureText(q.error, "The re-parse runs could not be loaded.")}</p>
  if (!q.data) return <p className="text-sm text-muted-foreground">Loading the phones and their re-parse runs</p>
  return (
    <section aria-label="Re-parse runs" className="space-y-2 text-sm">
      <h2 className="font-semibold">Read each phone again ({q.data.total} phones)</h2>
      {start.isError && <p role="alert">{failureText(start.error, "The re-parse could not be started.")}</p>}
      <ul className="space-y-1">
        {q.data.phones.map((p) => {
          const r = p.runs[0]
          const open = r && ["queued", "running"].includes(r.status)
          return (
            <li key={p.extraction_id} className="rounded border p-2" data-testid="reparse-phone">
              <p className="font-medium">{p.label} <span className="text-muted-foreground">({p.os ?? "operating system not stated in the report"})</span></p>
              {r ? (
                <p>
                  {TOOL[r.tool]} {r.tool_version}: {r.status === "completed" ? `finished in ${Math.round(r.seconds ?? 0).toLocaleString("en-US")} s, ${(r.tree?.placed ?? 0).toLocaleString("en-US")} verified files read, peak memory ${Math.round(r.peak_rss_mb ?? 0).toLocaleString("en-US")} MB` : r.status === "failed" ? `failed: ${r.error}` : r.status === "running" ? "running" : "waiting its turn (one phone at a time)"}
                </p>
              ) : <p className="text-muted-foreground">Not read again yet.</p>}
              <Button size="sm" variant="outline" disabled={!p.os_family || !!open || start.isPending} onClick={() => start.mutate(p.extraction_id)}>
                {p.os_family ? `Read again with ${p.os_family === "iOS" ? "iLEAPP" : "ALEAPP"}` : "No tool for this operating system"}
              </Button>
            </li>
          )
        })}
      </ul>
      <p className="text-muted-foreground">When the phones are read, run the comparison below.</p>
    </section>
  )
}

export default function ReparsePage() {
  const { id: caseId = "" } = useParams()
  const client = useMemo(() => analysisAPI("reparse_comparison"), [])
  return (
    <ApproachLayout caseId={caseId} title="Read again by an independent tool" whatItDoes={WHAT_IT_DOES} client={client}
      queryKey="phone-reparse" tabs={TABS} words={reparseWords} origin="phone-reparse" testId="reparse-result"
      collectLabel={(r) => reparseWords(r).title} emptyWords="Nothing of this kind for the phones read again."
      extra={<ReparseRuns caseId={caseId} />} />
  )
}
