import { useEffect, useState } from "react"

import { agentAPI } from "./api"
import { localStartMs, useAgentRunStore, type AgentRunNavigationState } from "./stores/agent-run.store"

/** "1 min 40 s", "12 s", "1 h 3 min". */
export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return `${s} s`
  const minutes = Math.floor(s / 60)
  if (minutes < 60) return `${minutes} min ${s % 60} s`
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

/** Ticks once a second so "so far" moves while a step runs. */
export function useElapsedSeconds(startedAt?: number | null, running = true): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [running])
  return startedAt ? (now - startedAt) / 1000 : 0
}

/** The line a person reads while a run works: what it is doing, which step, how long so far. */
export function progressLine(run: Pick<AgentRunNavigationState, "progress" | "statusText">, elapsed: number): string {
  const progress = run.progress
  const title = progress?.title || run.statusText || "Working through the case data"
  const parts = [title]
  if (progress && progress.phase === "tool" && progress.step > 0) parts.push(`step ${progress.step}`)
  parts.push(`${formatElapsed(elapsed)} so far`)
  return parts.join(" · ")
}

const POLL_MS = 2000

/**
 * A run this tab is not streaming (the page was left and opened again, or the stream dropped) goes on server-side:
 * find it and read its progress every 2 s until it ends, then hand it to the page's usual end-of-run handling.
 */
export function useFollowServerRun(caseId: string | undefined) {
  const run = useAgentRunStore((state) => (caseId ? state.runsByCase[caseId] : undefined))

  // On arrival: a run of this person's still working in the case is picked up.
  useEffect(() => {
    if (!caseId) return
    let cancelled = false
    if (useAgentRunStore.getState().runsByCase[caseId]) return
    agentAPI
      .activeRuns(caseId)
      .then(({ runs }) => {
        const latest = runs?.[0]
        if (cancelled || !latest || useAgentRunStore.getState().runsByCase[caseId]) return
        const store = useAgentRunStore.getState()
        store.startRun(caseId, latest.thread_id, latest.input_message ?? null)
        store.updateRun(caseId, {
          runId: latest.run_id,
          source: "poll",
          startedAt: localStartMs(latest.started_at, latest.server_time),
          progress: latest.progress ?? { phase: "thinking", step: 0, title: "Working on your question" },
          statusText: latest.progress?.title ?? null,
          stale: Boolean(latest.stale),
        })
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [caseId])

  const runId = run?.runId ?? null
  const following = Boolean(caseId && runId && run?.isLoading && run?.source === "poll")
  useEffect(() => {
    if (!caseId || !runId || !following) return
    let cancelled = false
    const tick = async () => {
      try {
        const detail = await agentAPI.getRun(runId)
        if (cancelled) return
        const store = useAgentRunStore.getState()
        if (detail.status === "running") {
          store.updateRun(caseId, {
            progress: detail.progress ?? store.runsByCase[caseId]?.progress ?? null,
            statusText: detail.progress?.title ?? store.runsByCase[caseId]?.statusText ?? null,
            stale: Boolean(detail.stale),
            ...(detail.started_at ? { startedAt: localStartMs(detail.started_at, detail.server_time) } : {}),
          })
        } else if (detail.status === "cancelled") {
          store.finishRun(caseId, "cancelled")
        } else if (detail.status === "failed") {
          store.finishRun(caseId, "failed", detail.error || "The run failed")
        } else {
          // completed, a question back to the person, or interrupted (its thread says so): the thread is reloaded.
          store.finishRun(caseId, detail.status === "needs_revision" ? "needs_revision" : "completed")
        }
      } catch {
        // A restart or a dropped connection: the next tick asks again.
      }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [caseId, runId, following])
}

/** The thread's last question when it has no answer after it (its run was stopped or ended without one), else null.
 * Callers show it only when nothing is running for the thread. */
export function unansweredQuestion(
  messages: ReadonlyArray<{ role: "user" | "assistant"; content: string; pending?: boolean }>
): string | null {
  const last = messages.length > 0 ? messages[messages.length - 1] : null
  if (!last || last.role !== "user" || last.pending || !last.content.trim()) return null
  return last.content
}
