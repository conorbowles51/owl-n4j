import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useChatStore } from "../stores/chat.store"
import { ChatSidePanel } from "./ChatSidePanel"
import { useCaseLayerStore } from "@/features/significant/stores/case-layer.store"

const panelMocks = vi.hoisted(() => ({
  sendMessage: vi.fn(),
  startNewConversation: vi.fn(),
  useChat: vi.fn(),
  useConversations: vi.fn(),
  getModels: vi.fn(),
}))

vi.mock("../hooks/use-chat", () => ({
  useChat: panelMocks.useChat,
}))

vi.mock("../hooks/use-conversations", () => ({
  useConversations: panelMocks.useConversations,
}))

vi.mock("@/features/evidence/api", () => ({
  evidenceAPI: {
    findByFilename: vi.fn(),
    getFileUrl: (id: string) => `/api/evidence/${id}/file`,
  },
  llmConfigAPI: {
    getModels: panelMocks.getModels,
  },
}))

vi.hoisted(() => {
  const storedValues = new Map<string, string>()
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      get length() {
        return storedValues.size
      },
      clear: () => storedValues.clear(),
      getItem: (key: string) => storedValues.get(key) ?? null,
      key: (index: number) => Array.from(storedValues.keys())[index] ?? null,
      removeItem: (key: string) => storedValues.delete(key),
      setItem: (key: string, value: string) => storedValues.set(key, value),
    } satisfies Storage,
  })
})

function renderPanel() {
  return render(
    <MemoryRouter initialEntries={["/cases/case-1/chat"]}>
      <ChatSidePanel caseId="case-1" />
    </MemoryRouter>
  )
}

describe("ChatSidePanel", () => {
  beforeEach(() => {
    panelMocks.sendMessage.mockReset()
    panelMocks.startNewConversation.mockReset()
    panelMocks.useChat.mockReset()
    panelMocks.useConversations.mockReset()
    panelMocks.getModels.mockReset()

    panelMocks.getModels.mockReturnValue(new Promise(() => {}))
    panelMocks.useChat.mockReturnValue({
      messages: [],
      isLoading: false,
      sendMessage: panelMocks.sendMessage,
      startNewConversation: panelMocks.startNewConversation,
    })
    panelMocks.useConversations.mockReturnValue({
      data: [
        {
          id: "conversation-1",
          name: "Saved chat",
          timestamp: "2026-04-29T12:00:00Z",
          created_at: "2026-04-29T12:00:00Z",
          updated_at: "2026-04-29T12:00:00Z",
          last_message_at: "2026-04-29T12:00:00Z",
          owner_user_id: "user-1",
          case_id: "case-1",
          message_count: 2,
        },
      ],
    })
    useChatStore.setState({
      activeCaseId: "case-1",
      activeConversationId: "conversation-1",
      messages: [],
    })
    useCaseLayerStore.setState({ layerByCase: {} })
  })

  it("shows the active conversation and starts new chats from compact controls", () => {
    renderPanel()

    expect(screen.getByText("Saved chat")).toBeInTheDocument()

    fireEvent.click(screen.getByTitle("New chat"))

    expect(panelMocks.startNewConversation).toHaveBeenCalledTimes(1)
  })

  it("sends through the persisted chat hook with model and scope", () => {
    renderPanel()

    const input = screen.getByPlaceholderText("Ask a question...")
    fireEvent.change(input, { target: { value: "Follow the money" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(panelMocks.sendMessage).toHaveBeenCalledWith(
      "Follow the money",
      "gpt-5-mini",
      "openai",
      "case_overview",
      expect.objectContaining({
        label: "Case side panel",
        route: "/cases/case-1/chat",
        scope: "case_overview",
        selection_within_scope: false,
        view: "chat",
      })
    )
  })

  it("keeps graph-side selection inside the Significant layer", () => {
    useCaseLayerStore.getState().setLayer("case-1", "significant")

    renderPanel()

    expect(screen.getByText("Significant Layer")).toBeInTheDocument()
    const input = screen.getByPlaceholderText("Ask a question...")
    fireEvent.change(input, { target: { value: "What matters here?" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(panelMocks.sendMessage).toHaveBeenCalledWith(
      "What matters here?",
      "gpt-5-mini",
      "openai",
      "significant",
      expect.objectContaining({
        scope: "significant",
        selection_within_scope: false,
        route: "/cases/case-1/chat",
        view: "chat",
      })
    )
  })
})
