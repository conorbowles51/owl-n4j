import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { renderHook } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

import { AgentRunProgress, AgentUnansweredNote } from "./AgentRunProgress"
import { formatElapsed, progressLine, unansweredQuestion, useFollowServerRun } from "../agent-run-progress"
import { agentAPI } from "../api"
import { useAgentRunStore, type AgentRunNavigationState } from "../stores/agent-run.store"
import { ChatWaitingLine } from "@/features/chat/components/ChatWaitingLine"

beforeEach(() => useAgentRunStore.setState({ runsByCase: {} }))
afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

const running = (patch: Partial<AgentRunNavigationState> = {}): AgentRunNavigationState => ({
  runId: "run-1",
  threadId: "thread-1",
  isLoading: true,
  statusText: null,
  terminalState: null,
  error: null,
  startedAt: Date.now() - 100_000,
  progress: { phase: "tool", step: 3, title: "Checking the accounts held by Jose Alejandro Reyes Zeind" },
  source: "stream",
  stale: false,
  inputMessage: "Which accounts does he hold?",
  ...patch,
})

it("says what the run is doing, which step and how long so far, in plain words", () => {
  expect(formatElapsed(100)).toBe("1 min 40 s")
  expect(formatElapsed(12)).toBe("12 s")
  expect(progressLine(running(), 100)).toBe(
    "Checking the accounts held by Jose Alejandro Reyes Zeind · step 3 · 1 min 40 s so far",
  )
  expect(progressLine(running({ progress: { phase: "thinking", step: 3, title: "Reading what step 3 found and deciding the next step" } }), 5))
    .toBe("Reading what step 3 found and deciding the next step · 5 s so far")
})

it("says the step against the run's budget once the run states it (tool steering F)", () => {
  expect(progressLine(running({ progress: { phase: "tool", step: 5, budget: 224, title: "Reading the ledger" } }), 72))
    .toBe("Reading the ledger · step 5 of up to 224 · 1 min 12 s so far")
  expect(progressLine(running({ progress: { phase: "thinking", step: 5, budget: 224,
    title: "Reading what step 5 found and deciding the next step" } }), 72))
    .toBe("Reading what step 5 found and deciding the next step · step 5 of up to 224 · 1 min 12 s so far")
})

it("shows the progress line with Stop, and Stop is wired", () => {
  const stop = vi.fn()
  render(<AgentRunProgress run={running()} onStop={stop} />)
  expect(screen.getByTestId("agent-run-progress").textContent).toMatch(
    /Checking the accounts held by Jose Alejandro Reyes Zeind · step 3 · 1 min 4\d s so far/,
  )
  fireEvent.click(screen.getByRole("button", { name: /Stop/ }))
  expect(stop).toHaveBeenCalled()
})

it("a run that stopped heart-beating says so and offers Resume run instead of spinning", () => {
  const retry = vi.fn()
  render(<AgentRunProgress run={running({ stale: true })} onRetry={retry} onDismiss={() => {}} />)
  expect(screen.getByText(/This run stopped responding/)).toBeInTheDocument()
  expect(screen.queryByTestId("agent-run-progress")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: /Resume run/ }))
  expect(retry).toHaveBeenCalled()
})

it("coming back to the page picks up the run still working server-side and follows it to its end", async () => {
  vi.spyOn(agentAPI, "activeRuns").mockResolvedValue({
    runs: [{
      run_id: "run-9", thread_id: "thread-9", input_message: "Who paid Ashdown?",
      started_at: "2026-11-08T22:24:09Z", server_time: "2026-11-08T22:25:49Z",
      progress: { phase: "tool", step: 2, title: "Reading the payments" }, stale: false,
    }],
  })
  const getRun = vi.spyOn(agentAPI, "getRun")
    .mockResolvedValueOnce({ run_id: "run-9", thread_id: "thread-9", status: "running",
      progress: { phase: "tool", step: 4, title: "Adding up the payments" }, stale: false })
    .mockResolvedValue({ run_id: "run-9", thread_id: "thread-9", status: "completed" })
  renderHook(() => useFollowServerRun("case-1"))
  await waitFor(() => expect(useAgentRunStore.getState().runsByCase["case-1"]?.runId).toBe("run-9"))
  const picked = useAgentRunStore.getState().runsByCase["case-1"]!
  expect(picked.source).toBe("poll")
  expect(picked.inputMessage).toBe("Who paid Ashdown?")
  // Started 100 s before the server's clock read: elapsed counts from then on this browser's clock.
  expect(Math.round((Date.now() - (picked.startedAt ?? 0)) / 1000)).toBe(100)
  await waitFor(() => expect(useAgentRunStore.getState().runsByCase["case-1"]?.progress?.step).toBe(4))
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 2100))
  })
  await waitFor(() => expect(useAgentRunStore.getState().runsByCase["case-1"]?.terminalState).toBe("completed"))
  expect(getRun).toHaveBeenCalledWith("run-9")
})

it("a run this tab started is not looked up again", async () => {
  useAgentRunStore.getState().startRun("case-1", null, "q")
  const active = vi.spyOn(agentAPI, "activeRuns").mockResolvedValue({ runs: [] })
  renderHook(() => useFollowServerRun("case-1"))
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(active).not.toHaveBeenCalled()
})

it("the chat panel says what it is doing and for how long, not bare dots", () => {
  render(<ChatWaitingLine />)
  expect(screen.getByRole("status").textContent).toBe("Searching the case and writing an answer · 0 s so far")
})

it("shows a retried step in plain words with the time so far and Stop (lx-callagent AG-06)", () => {
  const onStop = vi.fn()
  render(
    <AgentRunProgress
      run={running({
        progress: {
          phase: "retrying",
          step: 3,
          attempt: 2,
          attempts: 3,
          title: "The model service did not answer in time; trying again (2 of 3)",
        },
      })}
      onStop={onStop}
    />,
  )
  expect(screen.getByTestId("agent-run-progress").textContent).toBe(
    "The model service did not answer in time; trying again (2 of 3) · 1 min 40 s so far",
  )
  expect(screen.getByTestId("agent-run-progress").closest("[data-phase]")?.getAttribute("data-phase")).toBe("retrying")
  fireEvent.click(screen.getByRole("button", { name: /stop/i }))
  expect(onStop).toHaveBeenCalled()
})

it("a stopped run's question gets a plain note with Ask again, not silence", () => {
  const q = { id: "m2", role: "user" as const, content: "List every phone contact" }
  const a = { id: "m1", role: "assistant" as const, content: "Three accounts" }
  expect(unansweredQuestion([a, q])).toBe("List every phone contact")
  expect(unansweredQuestion([q, a])).toBeNull()
  expect(unansweredQuestion([a, { ...q, pending: true }])).toBeNull()
  expect(unansweredQuestion([])).toBeNull()
  const retry = vi.fn()
  render(<AgentUnansweredNote onRetry={retry} />)
  expect(screen.getByText(/stopped before it finished/)).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: /Ask again/ }))
  expect(retry).toHaveBeenCalled()
})
