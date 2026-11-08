import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Square } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { fetchAPI } from "@/lib/api-client"
import { taskPercent, type RunningWork, type RunningWorkList, type StoppedWork } from "../admin-rows"

export const RUNNING_WORK_URL = "/api/background-tasks/running"

/** Work running on the server now, each with a Stop (routers/background_tasks.py, services/running_work.py). */
export function RunningWorkPanel() {
  const client = useQueryClient()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin", "running-work"],
    queryFn: () => fetchAPI<RunningWorkList>(RUNNING_WORK_URL),
    refetchInterval: 5000,
  })
  const [asking, setAsking] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<{ ok: boolean; text: string } | null>(null)
  const stop = useMutation({
    mutationFn: (work: RunningWork) =>
      fetchAPI<StoppedWork>(`${RUNNING_WORK_URL}/${work.kind}/${encodeURIComponent(work.id)}/stop`, { method: "POST" }),
    onSuccess: (result) => {
      setOutcome({ ok: true, text: result.summary ?? "Stopped." })
      setAsking(null)
      void client.invalidateQueries({ queryKey: ["admin", "running-work"] })
    },
    onError: (err: Error) => {
      setOutcome({ ok: false, text: `Not stopped: ${err.message}` })
      setAsking(null)
    },
  })

  if (isLoading) return <p className="text-xs text-muted-foreground">Reading what is running…</p>
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-500">
        Running work could not be read: {error?.message}
      </p>
    )
  }
  const tasks = data?.tasks ?? []
  const stopped = data?.stopped ?? []
  const key = (work: RunningWork) => `${work.kind}:${work.id}`

  return (
    <section className="space-y-2" aria-label="Running now">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Running now</h2>
        <Badge variant={tasks.length > 0 ? "amber" : "slate"}>{tasks.length} running</Badge>
        {data?.scope === "owned_cases" && (
          <span className="text-[11px] text-muted-foreground">Work in the cases you own</span>
        )}
      </div>
      {outcome && (
        <p role="status" className={outcome.ok ? "text-xs text-foreground" : "text-xs text-red-500"}>
          {outcome.text}
        </p>
      )}
      {tasks.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nothing is running now.</p>
      ) : (
        tasks.map((work) => {
          const percent = taskPercent(work.progress)
          const confirming = asking === key(work)
          return (
            <div key={key(work)} className="rounded-lg border border-border bg-card p-3 shadow-sm">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{work.name}</span>
                {work.case_title && <span className="text-xs text-muted-foreground">{work.case_title}</span>}
                <div className="flex-1" />
                {work.started_by && <span className="text-[10px] text-muted-foreground">{work.started_by}</span>}
                {confirming ? (
                  <>
                    <Button size="sm" variant="danger" disabled={stop.isPending} onClick={() => stop.mutate(work)}>
                      Stop now
                    </Button>
                    <Button size="sm" variant="ghost" disabled={stop.isPending} onClick={() => setAsking(null)}>
                      Keep running
                    </Button>
                  </>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => { setOutcome(null); setAsking(key(work)) }}>
                    <Square className="size-3.5" />
                    Stop
                  </Button>
                )}
              </div>
              {confirming && (
                <p className="mt-1 text-xs text-muted-foreground">{STOP_MEANS[work.kind]}</p>
              )}
              {percent !== null && <Progress value={percent} className="mt-2" />}
            </div>
          )
        })
      )}
      {stopped.length > 0 && (
        <div className="space-y-1 pt-2">
          <h3 className="text-xs font-semibold text-muted-foreground">Stopped in the last 7 days</h3>
          {stopped.map((row, index) => (
            <div key={`${row.id}-${row.stopped_at}-${index}`} className="rounded border border-border p-2 text-xs">
              <span className="font-medium">{row.name}</span>{" "}
              <span className="text-muted-foreground">{row.stopped_at ? new Date(row.stopped_at).toLocaleString() : ""}</span>
              <p className="mt-0.5">{row.summary}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

const STOP_MEANS: Record<RunningWork["kind"], string> = {
  processing:
    "Each batch stops after the step it is on. Files already finished stay in the case; the others end cancelled and can be processed again.",
  export: "The export stops and no export file is offered. Ask for the export again to make a whole one.",
  statement_import:
    "Statements already prepared stay in the batch; the ones not started are left as they were. Resume on the batch continues them.",
}
