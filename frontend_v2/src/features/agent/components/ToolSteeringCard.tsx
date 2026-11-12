import { useEffect, useMemo, useState, type FormEvent } from "react"

import { agentAPI } from "../api"
import type { AgentRunSteering, AgentToolGroup, AgentToolTraceItem } from "../types"

const POLL_MS = 3000

/** The tool groups of a running answer, each with its state, a switch the person flips while it works, and a note
 * box: "Tools for this question" (Neil, 12 Nov 2026, approved mock-up). A switch applies from the run's next step;
 * the running step finishes first. Every switch and note is taken by the run and written into the trail with its
 * step (backend services/agent/tool_groups.py). */
export function ToolSteeringCard({
  runId,
  trace = [],
  streamed,
  onSteering,
}: {
  runId: string | null
  /** Calls this tab has seen stream in; the run's stored calls are used when they are more. */
  trace?: AgentToolTraceItem[]
  /** The run's switches as its stream last said (taken entries with their step). */
  streamed?: Pick<AgentRunSteering, "applied" | "off"> | null
  onSteering?: (steering: AgentRunSteering | null) => void
}) {
  const [groups, setGroups] = useState<AgentToolGroup[]>([])
  const [steering, setSteering] = useState<AgentRunSteering | null>(null)
  const [storedTrace, setStoredTrace] = useState<AgentToolTraceItem[]>([])
  const [changeLine, setChangeLine] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState("")

  useEffect(() => {
    let cancelled = false
    agentAPI
      .toolGroups()
      .then(({ groups: list }) => {
        if (!cancelled) setGroups(list)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!runId) return
    let cancelled = false
    const tick = async () => {
      try {
        const detail = await agentAPI.getRun(runId)
        if (cancelled) return
        if (detail.steering) setSteering(detail.steering)
        if (detail.tool_trace) setStoredTrace(detail.tool_trace)
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
  }, [runId])

  // The stream says at once when the run took a switch; the poll catches up within a few seconds.
  const view = useMemo<AgentRunSteering | null>(() => {
    if (!steering && !streamed) return null
    const base = steering ?? { chosen: [], applied: [], pending: [], off: [] }
    if (!streamed || streamed.applied.length <= base.applied.length) return base
    const taken = new Set(streamed.applied.map((entry) => entry.id))
    return { ...base, applied: streamed.applied, pending: base.pending.filter((entry) => !taken.has(entry.id)),
      off: streamed.off }
  }, [steering, streamed])

  useEffect(() => {
    onSteering?.(view)
  }, [view, onSteering])

  const calls = trace.length >= storedTrace.length ? trace : storedTrace
  const usedByGroup = useMemo(() => {
    const groupOf = new Map<string, string>()
    groups.forEach((group) => group.tools.forEach((tool) => groupOf.set(tool, group.id)))
    const counts = new Map<string, number>()
    calls.forEach((call) => {
      const id = groupOf.get(call.name)
      if (id) counts.set(id, (counts.get(id) ?? 0) + 1)
    })
    return counts
  }, [calls, groups])

  if (!runId || groups.length === 0) return null

  const off = new Set(view?.off ?? [])
  const chosen = new Set(view?.chosen ?? [])
  const offAt = (groupId: string) => {
    const applied = [...(view?.applied ?? [])].reverse()
      .find((entry) => entry.kind === "switch" && entry.group === groupId && !entry.on)
    return applied?.step ?? null
  }

  const flip = async (group: AgentToolGroup, on: boolean) => {
    setBusy(group.id)
    setError(null)
    try {
      const result = await agentAPI.steerRun(runId, { kind: "switch", group: group.id, on })
      setSteering(result.steering)
      setChangeLine(
        `${on ? "Switched on" : "Switched off"}: ${group.name}. The agent picks this up at its next step; the running step finishes first.`,
      )
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The switch was not saved. Try again.")
    } finally {
      setBusy(null)
    }
  }

  const send = async (event: FormEvent) => {
    event.preventDefault()
    const text = note.trim()
    if (!text) return
    setBusy("note")
    setError(null)
    try {
      const result = await agentAPI.steerRun(runId, { kind: "note", note: text })
      setSteering(result.steering)
      setNote("")
      setChangeLine("Note sent. The agent reads it before its next step.")
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The note was not sent. Try again.")
    } finally {
      setBusy(null)
    }
  }

  return (
    <section
      aria-labelledby="agent-tools-heading"
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-3.5 text-sm"
      data-testid="agent-tool-steering"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="agent-tools-heading" className="text-sm font-semibold text-foreground">
          Tools for this question
        </h2>
        <span className="text-xs text-muted-foreground">
          Chosen from your question. Switch one off or on; it applies from the next step.
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {groups.map((group) => {
          const isOff = off.has(group.id)
          const used = usedByGroup.get(group.id) ?? 0
          const at = isOff ? offAt(group.id) : null
          const stateText = !group.switchable
            ? `Always on${used ? ` · ${used} ${used === 1 ? "call" : "calls"}` : ""}`
            : isOff
              ? at !== null
                ? `Off · switched off by you at step ${at}`
                : "Off · applies from the next step"
              : used
                ? `In use · ${used} ${used === 1 ? "call" : "calls"}`
                : chosen.has(group.id)
                  ? "Chosen, not used yet"
                  : "Available, not chosen"
          return (
            <div
              key={group.id}
              data-testid={`tool-group-${group.id}`}
              className={
                isOff
                  ? "rounded-md border border-[#3a3420] bg-muted/10 px-3 py-2.5 opacity-85"
                  : "rounded-md border border-border bg-muted/20 px-3 py-2.5"
              }
            >
              <div className="flex items-center gap-2.5">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-foreground">{group.name}</div>
                  <div
                    className={
                      isOff
                        ? "mt-0.5 text-xs text-[#f0d48a]"
                        : used && group.switchable
                          ? "mt-0.5 text-xs text-[#86d19a]"
                          : "mt-0.5 text-xs text-muted-foreground"
                    }
                  >
                    {stateText}
                  </div>
                </div>
                {group.switchable && (
                  <label className="flex min-h-11 cursor-pointer items-center gap-2">
                    <span className="text-xs text-muted-foreground">{isOff ? "Off" : "On"}</span>
                    <input
                      type="checkbox"
                      checked={!isOff}
                      disabled={busy !== null}
                      onChange={() => void flip(group, isOff)}
                      aria-label={`${isOff ? "Switch on" : "Switch off"} ${group.name}`}
                      className="size-[18px] cursor-pointer accent-[#b8323a]"
                    />
                  </label>
                )}
              </div>
              <div className="mt-1.5 text-xs leading-5 text-muted-foreground">{group.about}</div>
            </div>
          )
        })}
      </div>
      {changeLine && (
        <div
          role="status"
          className="rounded-md border border-[#5a4a1d] bg-[#1d1a12] px-2.5 py-2 text-[13px] text-[#f0d48a]"
        >
          {changeLine}
        </div>
      )}
      {error && (
        <div role="alert" className="rounded-md border border-destructive/40 px-2.5 py-2 text-[13px] text-destructive">
          {error}
        </div>
      )}
      <form className="flex flex-wrap gap-2" onSubmit={send}>
        <label htmlFor="agent-steer-note" className="sr-only">
          Direct the agent
        </label>
        <input
          id="agent-steer-note"
          type="text"
          value={note}
          maxLength={500}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Direct the next step, e.g. “Check the May 2024 statement first”"
          className="min-h-10 flex-[1_1_320px] rounded-md border border-border bg-background px-3 text-sm text-foreground"
        />
        <button
          type="submit"
          disabled={busy !== null || !note.trim()}
          className="min-h-10 rounded-md bg-[#7a1d24] px-3.5 text-sm text-white disabled:opacity-60"
        >
          Send to the agent
        </button>
      </form>
    </section>
  )
}
