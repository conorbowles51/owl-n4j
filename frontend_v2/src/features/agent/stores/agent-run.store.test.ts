import { beforeEach, describe, expect, it } from "vitest"
import { useAgentRunStore } from "./agent-run.store"

describe("agent run navigation store", () => {
  beforeEach(() => {
    useAgentRunStore.setState({ runsByCase: {} })
  })

  it("preserves an active run until its terminal state is consumed", () => {
    const store = useAgentRunStore.getState()
    store.startRun("case-1", null)
    store.updateRun("case-1", {
      runId: "run-1",
      threadId: "thread-1",
      statusText: "Investigating the case",
    })

    expect(useAgentRunStore.getState().runsByCase["case-1"]).toEqual({
      runId: "run-1",
      threadId: "thread-1",
      isLoading: true,
      statusText: "Investigating the case",
      terminalState: null,
      error: null,
    })

    useAgentRunStore.getState().finishRun("case-1", "completed")
    expect(useAgentRunStore.getState().runsByCase["case-1"]).toMatchObject({
      isLoading: false,
      terminalState: "completed",
    })

    useAgentRunStore.getState().clearRun("case-1", "run-1")
    expect(useAgentRunStore.getState().runsByCase["case-1"]).toBeUndefined()
  })

  it("isolates active runs by case", () => {
    const store = useAgentRunStore.getState()
    store.startRun("case-1", "thread-1")
    store.startRun("case-2", "thread-2")
    store.updateRun("case-1", { runId: "run-1" })
    store.updateRun("case-2", { runId: "run-2" })
    store.finishRun("case-1", "cancelled")

    expect(useAgentRunStore.getState().runsByCase["case-1"]).toMatchObject({
      runId: "run-1",
      isLoading: false,
      terminalState: "cancelled",
    })
    expect(useAgentRunStore.getState().runsByCase["case-2"]).toMatchObject({
      runId: "run-2",
      isLoading: true,
      terminalState: null,
    })
  })

  it("does not clear a newer run when an older run is consumed", () => {
    const store = useAgentRunStore.getState()
    store.startRun("case-1", "thread-2")
    store.updateRun("case-1", { runId: "run-2" })

    store.clearRun("case-1", "run-1")

    expect(useAgentRunStore.getState().runsByCase["case-1"]?.runId).toBe("run-2")
  })
})
