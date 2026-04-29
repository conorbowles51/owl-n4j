import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useChatStore } from "../stores/chat.store"
import { ChatSidePanel } from "./ChatSidePanel"

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
  })

  it("shows the active conversation and starts new chats from compact controls", () => {
    render(<ChatSidePanel caseId="case-1" />)

    expect(screen.getByText("Saved chat")).toBeInTheDocument()

    fireEvent.click(screen.getByTitle("New chat"))

    expect(panelMocks.startNewConversation).toHaveBeenCalledTimes(1)
  })

  it("sends through the persisted chat hook with model and scope", () => {
    render(<ChatSidePanel caseId="case-1" />)

    const input = screen.getByPlaceholderText("Ask a question...")
    fireEvent.change(input, { target: { value: "Follow the money" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(panelMocks.sendMessage).toHaveBeenCalledWith(
      "Follow the money",
      "gpt-5-mini",
      "openai",
      "case_overview"
    )
  })
})
