import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { JobTray } from "@/components/ui/job-tray"
import { cancelDeriveBatch, createDeriveBatch, describeDeriveBatch, getDeriveBatches, type DeriveBatchFacts, type MediaFilter } from "../api"
import { batchJob, leftOutWords } from "./batch-words"

const n = (v: number) => v.toLocaleString("en-US")

/**
 * Batch transcription and text reading of the Media scope shown (07 5 Media, M-5): the true number of files it
 * would read and what it leaves out, then the work in the job tray, counted every second from the server.
 */
export function BatchReading({ caseId, filter, scopeWords }: { caseId: string; filter: MediaFilter; scopeWords: string }) {
  const client = useQueryClient()
  const [now, setNow] = useState(() => Date.now())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const transcript = useQuery({ queryKey: ["derive-batch-facts", "transcript", filter], queryFn: () => describeDeriveBatch(filter, "transcript"), enabled: !!caseId })
  const ocr = useQuery({ queryKey: ["derive-batch-facts", "ocr", filter], queryFn: () => describeDeriveBatch(filter, "ocr"), enabled: !!caseId })
  const batches = useQuery({
    queryKey: ["derive-batches", caseId],
    queryFn: () => getDeriveBatches(caseId),
    enabled: !!caseId,
    refetchInterval: (q) => (q.state.data?.items.some((b) => b.state === "running") ? 1000 : false),
  })
  const running = batches.data?.items.some((b) => b.state === "running") ?? false
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [running])
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["derive-batches", caseId] })
    await client.invalidateQueries({ queryKey: ["derive-batch-facts"] })
  }
  const start = async (kind: "ocr" | "transcript") => {
    setBusy(true)
    setError(null)
    try {
      await createDeriveBatch(filter, kind, scopeWords)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : "The batch could not be started.")
    } finally {
      setBusy(false)
    }
  }
  const cancel = (id: string) => async () => {
    try {
      await cancelDeriveBatch(caseId, id)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : "The batch could not be stopped.")
    }
  }
  const jobs = (batches.data?.items ?? []).map((b) => batchJob(b, b.state === "running" ? cancel(b.id) : undefined))
  const offer = (f: DeriveBatchFacts | undefined, kind: "ocr" | "transcript") =>
    f && f.eligible > 0 ? (
      <span className="flex flex-col gap-0.5">
        <Button size="sm" variant="outline" disabled={busy} onClick={() => start(kind)}>
          {kind === "transcript" ? `Transcribe all ${n(f.eligible)} ${f.noun} in this scope` : `Read text in all ${n(f.eligible)} ${f.noun} in this scope`}
        </Button>
        {leftOutWords(f) && <span className="text-muted-foreground">{leftOutWords(f)}</span>}
      </span>
    ) : null
  return (
    <div className="flex flex-wrap items-start gap-2 text-xs">
      {offer(transcript.data, "transcript")}
      {offer(ocr.data, "ocr")}
      {(transcript.data?.eligible || ocr.data?.eligible) ? <span className="self-center text-muted-foreground">Read on this server; nothing is sent anywhere. Each text is marked machine-generated until a person confirms it.</span> : null}
      {jobs.length > 0 && <JobTray jobs={jobs} now={now} />}
      {(transcript.isError || ocr.isError) && <p role="alert">Batch reading cannot be offered for this scope: the count of files to read failed. Nothing was queued.</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
