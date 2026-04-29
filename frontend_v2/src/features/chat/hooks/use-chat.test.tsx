import { type PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useGraphStore } from "@/stores/graph.store"
import { useChatStore } from "../stores/chat.store"
import { useChat } from "./use-chat"

const apiMocks = vi.hoisted(() => ({
  ask: vi.fn(),
  getSuggestions: vi.fn(),
  getConversation: vi.fn(),
}))

vi.mock("../api", () => ({
  chatAPI: {
    ask: apiMocks.ask,
    getSuggestions: apiMocks.getSuggestions,
  },
  chatHistoryAPI: {
    get: apiMocks.getConversation,
  },
}))

const EMPTY_GRAPH = { nodes: [], links: [] }

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

describe("useChat", () => {
  beforeEach(() => {
    apiMocks.ask.mockReset()
    apiMocks.getSuggestions.mockReset()
    apiMocks.getConversation.mockReset()
    apiMocks.getSuggestions.mockReturnValue(new Promise(() => {}))

    useChatStore.setState({
      activeCaseId: null,
      activeConversationId: null,
      messages: [],
      cumulativeGraph: EMPTY_GRAPH,
      lastResponseGraph: EMPTY_GRAPH,
      selectedResultNodeKey: null,
    })
    useGraphStore.setState({ selectedNodeKeys: new Set() })
  })

  it("preserves active conversation state when remounted for the same case", async () => {
    const first = renderHook(() => useChat("case-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(useChatStore.getState().activeCaseId).toBe("case-1")
    })

    act(() => {
      useChatStore.getState().addMessage({
        role: "user",
        content: "What happened?",
      })
      useChatStore.getState().setActiveConversation("conversation-1")
    })

    first.unmount()

    renderHook(() => useChat("case-1"), {
      wrapper: createWrapper(),
    })

    expect(useChatStore.getState().activeConversationId).toBe("conversation-1")
    expect(useChatStore.getState().messages).toEqual([
      { role: "user", content: "What happened?" },
    ])
  })

  it("clears conversation state when the active case changes", async () => {
    const { rerender } = renderHook(
      ({ caseId }) => useChat(caseId),
      {
        initialProps: { caseId: "case-1" },
        wrapper: createWrapper(),
      }
    )

    await waitFor(() => {
      expect(useChatStore.getState().activeCaseId).toBe("case-1")
    })

    act(() => {
      useChatStore.getState().addMessage({
        role: "user",
        content: "What happened?",
      })
      useChatStore.getState().setActiveConversation("conversation-1")
    })

    rerender({ caseId: "case-2" })

    await waitFor(() => {
      expect(useChatStore.getState().activeCaseId).toBe("case-2")
    })
    expect(useChatStore.getState().activeConversationId).toBeNull()
    expect(useChatStore.getState().messages).toEqual([])
  })
})
