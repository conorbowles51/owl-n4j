import { create } from "zustand"

export type AgentRunTerminalState = "completed" | "failed" | "cancelled" | "needs_revision"

/** The plain line for the step a run is on (backend services/agent/live_runs.py). */
export interface AgentRunProgress {
  phase: "starting" | "thinking" | "tool" | "writing" | "retrying" | string
  step: number
  /** phase "retrying": which try this is, of how many (the model service failed and the run tries again). */
  attempt?: number
  attempts?: number
  title: string
  since?: string
}

export interface AgentRunNavigationState {
  runId: string | null
  threadId: string | null
  isLoading: boolean
  statusText: string | null
  /** When the run started (ms since epoch) on this browser's clock: the server's start corrected by the server's
   * clock when the server has said it, else when this browser sent the question. */
  startedAt?: number | null
  terminalState: AgentRunTerminalState | null
  error: string | null
  progress?: AgentRunProgress | null
  /** "stream": this tab is reading the run's events; "poll": the run goes on server-side and is read every 2 s. */
  source?: "stream" | "poll"
  /** The run's worker stopped beating: it is no longer working. */
  stale?: boolean
  /** The question the run is answering, for Retry. */
  inputMessage?: string | null
}

/** Start time on this browser's clock from the server's start and the server's clock at the same moment. */
export function localStartMs(startedAt?: string | null, serverTime?: string | null): number {
  const now = Date.now()
  if (!startedAt) return now
  const started = Date.parse(startedAt)
  const server = serverTime ? Date.parse(serverTime) : NaN
  if (Number.isNaN(started)) return now
  return Number.isNaN(server) ? started : now - Math.max(0, server - started)
}

interface AgentRunStore {
  runsByCase: Record<string, AgentRunNavigationState>
  startRun: (caseId: string, threadId: string | null, inputMessage?: string | null) => void
  updateRun: (caseId: string, patch: Partial<AgentRunNavigationState>) => void
  finishRun: (
    caseId: string,
    terminalState: AgentRunTerminalState,
    error?: string | null
  ) => void
  clearRun: (caseId: string, runId?: string | null) => void
}

export const useAgentRunStore = create<AgentRunStore>((set) => ({
  runsByCase: {},

  startRun: (caseId, threadId, inputMessage = null) =>
    set((state) => ({
      runsByCase: {
        ...state.runsByCase,
        [caseId]: {
          runId: null,
          threadId,
          isLoading: true,
          statusText: "Starting agent run",
          startedAt: Date.now(),
          terminalState: null,
          error: null,
          progress: { phase: "starting", step: 0, title: "Sending your question" },
          source: "stream",
          stale: false,
          inputMessage,
        },
      },
    })),

  updateRun: (caseId, patch) =>
    set((state) => {
      const current = state.runsByCase[caseId]
      if (!current) return state
      return {
        runsByCase: {
          ...state.runsByCase,
          [caseId]: { ...current, ...patch },
        },
      }
    }),

  finishRun: (caseId, terminalState, error = null) =>
    set((state) => {
      const current = state.runsByCase[caseId]
      if (!current) return state
      return {
        runsByCase: {
          ...state.runsByCase,
          [caseId]: {
            ...current,
            isLoading: false,
            terminalState,
            error,
          },
        },
      }
    }),

  clearRun: (caseId, runId) =>
    set((state) => {
      const current = state.runsByCase[caseId]
      if (!current || (runId !== undefined && current.runId !== runId)) return state
      const runsByCase = { ...state.runsByCase }
      delete runsByCase[caseId]
      return { runsByCase }
    }),
}))
