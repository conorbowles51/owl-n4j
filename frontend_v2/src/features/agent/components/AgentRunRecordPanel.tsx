import { useState } from "react"
import { Button } from "@/components/ui/button"
import { downloadProtectedFile } from "@/lib/protected-file"
import { agentAPI } from "../api"
import type { AgentRunRecord } from "../types"

type Kind = "strategy" | "not_examined"
type Format = "csv" | "pdf"

const EXPORTS: { kind: Kind; format: Format; label: string }[] = [
  { kind: "strategy", format: "csv", label: "Search strategy (CSV)" },
  { kind: "strategy", format: "pdf", label: "Search strategy (PDF)" },
  { kind: "not_examined", format: "csv", label: "What was not examined (CSV)" },
  { kind: "not_examined", format: "pdf", label: "What was not examined (PDF)" },
]

function when(value: string | null) {
  if (!value) return "not ended"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : `${date.toISOString().slice(0, 19).replace("T", " ")} UTC`
}

function n(value: number | undefined) {
  return typeof value === "number" ? value.toLocaleString() : "not recorded"
}

/** The run record of one answer: who it was for, when, the model and prompt version, the tool budget used, and
 * what the run examined and did not. Every number comes from the stored record, computed by code. The two
 * exports are the disclosure documents (search strategy; what was not examined). */
export function AgentRunRecordPanel({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false)
  const [record, setRecord] = useState<AgentRunRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next && !record && !loading) {
      setLoading(true)
      setError(null)
      try {
        setRecord(await agentAPI.getRunRecord(runId))
      } catch (e) {
        setError(e instanceof Error ? e.message : "The run record could not be read.")
      } finally {
        setLoading(false)
      }
    }
  }

  const download = async (kind: Kind, format: Format) => {
    const key = `${kind}.${format}`
    setBusy(key)
    setError(null)
    try {
      await downloadProtectedFile(
        agentAPI.runRecordExportUrl(runId, kind, format),
        `agent-run-${runId.slice(0, 8)}-${kind === "strategy" ? "strategy" : "not-examined"}.${format}`,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : "The export could not be downloaded.")
    } finally {
      setBusy(null)
    }
  }

  const s = record?.summary ?? {}
  return (
    <div className="mt-1 max-w-3xl text-xs" data-testid="agent-run-record">
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={toggle} aria-expanded={open}>
        {open ? "Hide run record" : "Run record"}
      </Button>
      {open ? (
        <div className="mt-1 rounded-md border border-border bg-muted/20 px-3 py-2 text-muted-foreground">
          {loading ? <p>Reading the run record of this answer…</p> : null}
          {record ? (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                <dt>Run for</dt>
                <dd className="text-foreground">
                  {[record.for_user.name, record.for_user.email].filter(Boolean).join(" · ") || "not recorded"}
                </dd>
                <dt>Started / ended</dt>
                <dd className="text-foreground">
                  {when(record.started_at)} / {when(record.completed_at)}
                </dd>
                <dt>Model</dt>
                <dd className="text-foreground">
                  {record.provider} / {record.model_id}
                </dd>
                <dt>Prompt version</dt>
                <dd className="text-foreground">{record.prompt_version_label ?? "not recorded"}</dd>
                <dt>Tool calls</dt>
                <dd className="text-foreground" data-testid="run-record-calls">
                  {record.tool_calls_used} of {record.tool_budget ?? "not recorded"}
                  {record.unrun_tool_calls.length
                    ? `; ${record.unrun_tool_calls.length} more asked for but stopped by the budget`
                    : ""}
                </dd>
                <dt>Cases read</dt>
                <dd className="text-foreground" data-testid="run-record-cases">
                  {record.all_cases ? "All my cases mode: " : "This case only: "}
                  {(record.cases_read ?? [])
                    .map((c) => (c.case_name ?? c.case_id) + (c.this_case ? " (this case)" : ""))
                    .join("; ") || "this case"}
                </dd>
                <dt>Items returned</dt>
                <dd className="text-foreground" data-testid="run-record-items">
                  {n(s.items_returned)}: {n(s.items_opened)} read further, {n(s.items_cited)} cited by link,{" "}
                  {n(s.items_in_artifact)} used in an artifact, {n(s.items_not_examined)} none of these
                </dd>
                <dt>Clipped</dt>
                <dd className="text-foreground" data-testid="run-record-clipped">
                  {n(s.tool_not_returned)} matching items on pages not read; {n(s.model_not_shown)} returned but not
                  shown to the model
                </dd>
              </dl>
              {s.basis ? <p className="mt-1">{s.basis}</p> : null}
              <p className="mt-1">{record.not_deterministic}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {EXPORTS.map((x) => (
                  <Button
                    key={`${x.kind}.${x.format}`}
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    disabled={busy !== null}
                    onClick={() => download(x.kind, x.format)}
                  >
                    {busy === `${x.kind}.${x.format}` ? "Preparing…" : x.label}
                  </Button>
                ))}
              </div>
            </>
          ) : null}
          {error ? <p className="mt-1 text-destructive">{error}</p> : null}
        </div>
      ) : null}
    </div>
  )
}
