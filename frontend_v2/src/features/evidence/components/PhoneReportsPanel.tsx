import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  consequenceText,
  day,
  isUsable,
  phoneReportsAPI,
  phoneReportsKey,
  replaceTargets,
  retireCandidates,
  type PhoneReport,
} from "../phone-reports"

/**
 * The phone reports of a case, with Replace and Retire (docs/cellebrite/01-intake-capture-storage.md section 10.7).
 * Replace never deletes: the older report is retired, its records stay readable, and the typed reason is recorded
 * in the case decision ledger.
 */

function standingText(report: PhoneReport, byId: Map<string, PhoneReport>) {
  if (report.standing === "superseded") {
    const by = report.replaced_by_id ? byId.get(report.replaced_by_id)?.label : null
    return `From a replaced report${by ? `: replaced by ${by}` : ""}, retired on ${day(report.superseded_at)}${
      report.superseded_by ? ` by ${report.superseded_by}` : ""
    }. Reason: ${report.superseded_reason}`
  }
  if (report.standing === "pending") return "Being read"
  return "In use"
}

type Pending = { newer: PhoneReport; older: PhoneReport; mode: "replace" | "retire" }

function Confirm({
  pending,
  candidates,
  onChoose,
  onDone,
  caseId,
}: {
  pending: Pending
  candidates: PhoneReport[]
  onChoose: (newer: PhoneReport) => void
  onDone: () => void
  caseId: string
}) {
  const [reason, setReason] = useState("")
  const client = useQueryClient()
  const run = useMutation({
    mutationFn: () => phoneReportsAPI.supersede(pending.newer.id, pending.older.id, reason.trim()),
    onSuccess: () => {
      toast.success(`${pending.older.label} is retired. ${pending.newer.label} is the report in use.`)
      for (const key of [phoneReportsKey(caseId), ["evidence-jobs", caseId], ["evidence", caseId]])
        client.invalidateQueries({ queryKey: key })
      onDone()
    },
    onError: (error: Error) => toast.error(error.message || "The report could not be replaced"),
  })
  return (
    <div role="alertdialog" aria-label={`Retire ${pending.older.label}`} className="mt-2 rounded-md border p-2 text-[11px]">
      {pending.mode === "retire" && candidates.length > 1 ? (
        <label className="mb-2 block">
          <span className="text-muted-foreground">The report that replaces it</span>
          <select
            className="mt-1 block w-full rounded border bg-background p-1"
            value={pending.newer.id}
            onChange={(e) => {
              const next = candidates.find((c) => c.id === e.target.value)
              if (next) onChoose(next)
            }}
          >
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="mb-1 text-muted-foreground">Replaced by {pending.newer.label}</p>
      )}
      <p>{consequenceText(pending.older)}</p>
      <label className="mt-2 block">
        <span className="text-muted-foreground">Reason (required)</span>
        <Textarea
          aria-label="Reason"
          className="mt-1 min-h-[48px] text-[11px]"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <div className="mt-2 flex gap-2">
        <Button
          size="sm"
          variant="danger"
          className="h-7 text-[11px]"
          disabled={!reason.trim() || run.isPending}
          onClick={() => run.mutate()}
        >
          Retire {pending.older.label}
        </Button>
        <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={onDone}>
          Keep both
        </Button>
      </div>
    </div>
  )
}

export function PhoneReportsPanel({ caseId }: { caseId: string }) {
  const { data } = useQuery({
    queryKey: phoneReportsKey(caseId),
    queryFn: () => phoneReportsAPI.list(caseId),
    refetchInterval: 15000,
  })
  const [pending, setPending] = useState<Pending | null>(null)
  const reports = data || []
  if (!reports.length) return null
  const byId = new Map(reports.map((r) => [r.id, r]))
  const inUse = reports.filter((r) => r.standing === "active").length
  return (
    <section aria-label="Phone reports" className="rounded-lg border bg-card p-3">
      <h4 className="text-xs font-semibold">
        Phone reports: {inUse.toLocaleString("en-US")} in use
        {reports.length > inUse ? `, ${(reports.length - inUse).toLocaleString("en-US")} not in use` : ""}
      </h4>
      <ul className="mt-2 space-y-2">
        {reports.map((report) => {
          const targets = replaceTargets(report, reports)
          const candidates = retireCandidates(report, reports)
          const same = report.possible_same_device.filter((p) => byId.get(p.extraction_id)?.standing === "active")
          return (
            <li key={report.id} className="text-xs">
              <span className="font-medium">{report.label}</span>
              <span className="ml-2 text-muted-foreground">{standingText(report, byId)}</span>
              {report.record_count != null ? (
                <span className="block text-[11px] text-muted-foreground">
                  {report.record_count.toLocaleString("en-US")} records, {(report.file_count ?? 0).toLocaleString("en-US")} files
                </span>
              ) : null}
              {same.length && isUsable(report) ? (
                <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-400">
                  This report appears to be from the same phone as {same.map((p) => byId.get(p.extraction_id)?.label || p.name).join(", ")}. Both are kept. Use Replace on the newer one to retire the older one.
                </p>
              ) : null}
              <div className="mt-1 flex flex-wrap gap-2">
                {targets.map((older) => (
                  <Button
                    key={older.id}
                    size="sm"
                    variant="outline"
                    className="h-6 text-[11px]"
                    onClick={() => setPending({ newer: report, older, mode: "replace" })}
                  >
                    Replace {older.label}
                  </Button>
                ))}
                {candidates.length ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 text-[11px]"
                    onClick={() => setPending({ newer: candidates[candidates.length - 1], older: report, mode: "retire" })}
                  >
                    Retire
                  </Button>
                ) : null}
              </div>
              {pending && pending.older.id === report.id && pending.mode === "retire" ? (
                <Confirm
                  pending={pending}
                  candidates={candidates}
                  caseId={caseId}
                  onChoose={(newer) => setPending({ ...pending, newer })}
                  onDone={() => setPending(null)}
                />
              ) : null}
              {pending && pending.newer.id === report.id && pending.mode === "replace" ? (
                <Confirm pending={pending} candidates={[]} caseId={caseId} onChoose={() => {}} onDone={() => setPending(null)} />
              ) : null}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
