import { create } from "zustand"

export type AgentRunTerminalState = "completed" | "failed" | "cancelled"

export interface AgentRunNavigationState {
  runId: string | null
  threadId: string | null
  isLoading: boolean
  statusText: string | null
  terminalState: AgentRunTerminalState | null
  error: string | null
}

interface AgentRunStore {
  runsByCase: Record<string, AgentRunNavigationState>
  startRun: (caseId: string, threadId: string | null) => void
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

  startRun: (caseId, threadId) =>
    set((state) => ({
      runsByCase: {
        ...state.runsByCase,
        [caseId]: {
          runId: null,
          threadId,
          isLoading: true,
          statusText: "Starting agent run",
          terminalState: null,
          error: null,
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
