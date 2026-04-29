import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { chatAPI } from "./api"

describe("chatAPI.ask", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => null),
      removeItem: vi.fn(),
      setItem: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function mockChatResponse() {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          conversation_id: "conversation-1",
          message_id: "message-1",
          answer: "Answer",
          sources: [],
          model_info: {
            provider: "openai",
            model_id: "gpt-5-mini",
            model_name: "GPT-5 mini",
            server: "OpenAI (remote)",
          },
          provenance: { case_id: "case-1" },
          suggestions: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    )
  }

  it("persists chat requests by default", async () => {
    mockChatResponse()

    await chatAPI.ask({
      question: "What happened?",
      case_id: "case-1",
      scope: "case_overview",
    })

    const [, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    const body = JSON.parse(options?.body as string)
    expect(body.persist).toBe(true)
  })

  it("preserves explicit ephemeral opt-out", async () => {
    mockChatResponse()

    await chatAPI.ask({
      question: "What happened?",
      case_id: "case-1",
      scope: "case_overview",
      persist: false,
    })

    const [, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    const body = JSON.parse(options?.body as string)
    expect(body.persist).toBe(false)
  })
})
