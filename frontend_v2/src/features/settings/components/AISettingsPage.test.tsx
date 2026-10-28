import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { AISettingsPage } from "./AISettingsPage"

const api = vi.hoisted(() => ({
  get: vi.fn(),
  saveCredential: vi.fn(),
  testCredential: vi.fn(),
  disconnectCredential: vi.fn(),
  updatePolicy: vi.fn(),
}))

vi.mock("../api", () => ({ aiSettingsAPI: api }))

const settings = {
  policy_revision: 3,
  default_provider: "openai",
  providers: [
    {
      id: "openai",
      display_name: "OpenAI",
      description: "Generative models and supporting services.",
      configured: true,
      status: "connected",
      source: "environment",
      key_last_four: "1234",
      revision: 0,
      in_use_by: ["chat"],
    },
    {
      id: "anthropic",
      display_name: "Anthropic",
      description: "Claude models.",
      configured: false,
      status: "disconnected",
      source: null,
      key_last_four: null,
      revision: 0,
      in_use_by: [],
    },
    {
      id: "gemini",
      display_name: "Google Gemini",
      description: "Gemini models.",
      configured: false,
      status: "disconnected",
      source: null,
      key_last_four: null,
      revision: 0,
      in_use_by: [],
    },
    {
      id: "deepseek",
      display_name: "DeepSeek",
      description: "DeepSeek models.",
      configured: false,
      status: "disconnected",
      source: null,
      key_last_four: null,
      revision: 0,
      in_use_by: [],
    },
  ],
  models: [
    { id: "gpt-5.6-terra", name: "GPT-5.6 Terra", provider: "openai", provider_configured: true },
    { id: "claude-sonnet-5", name: "Claude Sonnet 5", provider: "anthropic", provider_configured: false },
    { id: "deepseek-v4-flash", name: "DeepSeek V4 Flash", provider: "deepseek", provider_configured: false },
  ],
  workloads: {
    chat: { label: "AI chat", description: "Chat surfaces", group: "Interactive" },
  },
  routing: { chat: { provider: "openai", model_id: "gpt-5.6-terra" } },
  recommended_profiles: {
    openai: { chat: { provider: "openai", model_id: "gpt-5.6-terra" } },
    anthropic: { chat: { provider: "anthropic", model_id: "claude-sonnet-5" } },
    gemini: { chat: { provider: "gemini", model_id: "gemini-3.6-flash" } },
    deepseek: { chat: { provider: "deepseek", model_id: "deepseek-v4-flash" } },
  },
  supporting_services: [
    { id: "embeddings", label: "Search embeddings", provider: "openai", status: "ready", description: "Semantic search" },
    { id: "pdf_ocr", label: "PDF OCR", provider: "tesseract", status: "ready", description: "Local OCR" },
  ],
  permissions: { can_edit_routing: true, can_manage_credentials: true },
}

describe("AISettingsPage", () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => mock.mockReset())
    api.get.mockResolvedValue(settings)
    api.saveCredential.mockResolvedValue({
      ...settings.providers[1],
      configured: true,
      status: "connected",
      key_last_four: "alue",
      revision: 1,
    })
    useAuthStore.setState({
      isAuthenticated: true,
      user: { username: "root", name: "Root", role: "super_admin", global_role: "super_admin" },
    })
  })

  it("shows Loupe's four supported cloud providers", async () => {
    render(<MemoryRouter><AISettingsPage /></MemoryRouter>)

    expect(await screen.findByText("Provider connections")).toBeInTheDocument()
    expect(screen.getAllByText("OpenAI").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Anthropic").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Google Gemini").length).toBeGreaterThan(0)
    expect(screen.getAllByText("DeepSeek").length).toBeGreaterThan(0)
    expect(screen.getByTestId("provider-logo-openai")).toBeInTheDocument()
    expect(screen.getByTestId("provider-logo-anthropic")).toBeInTheDocument()
    expect(screen.getByTestId("provider-logo-gemini")).toBeInTheDocument()
    expect(screen.getByTestId("provider-logo-deepseek")).toHaveAttribute(
      "src",
      expect.stringMatching(/^data:image\/svg\+xml/)
    )
    expect(screen.queryByText(/ollama/i)).not.toBeInTheDocument()
  })

  it("submits a new key once and never renders it back", async () => {
    render(<MemoryRouter><AISettingsPage /></MemoryRouter>)
    await screen.findByText("Provider connections")

    fireEvent.click(screen.getByRole("button", { name: "Configure Anthropic" }))
    fireEvent.change(screen.getByLabelText("Anthropic API key"), {
      target: { value: "sk-ant-secret-value" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Validate and connect" }))

    await waitFor(() =>
      expect(api.saveCredential).toHaveBeenCalledWith(
        "anthropic",
        "sk-ant-secret-value",
        0
      )
    )
    await waitFor(() =>
      expect(screen.queryByDisplayValue("sk-ant-secret-value")).not.toBeInTheDocument()
    )
  })

  it("shows the page-image chain in order, offers only models that read images, and saves the new order", async () => {
    const chain = [
      { provider: "deepseek", model_id: "deepseek-flash" },
      { provider: "openai", model_id: "gpt-5.6-terra" },
    ]
    const withChain = {
      ...settings,
      models: [
        { id: "gpt-5.6-terra", name: "GPT-5.6 Terra", provider: "openai", provider_configured: true, reads_images: true },
        { id: "deepseek-flash", name: "DeepSeek V4.1 Flash", provider: "deepseek", provider_configured: true, reads_images: true },
        { id: "deepseek-v4-pro", name: "DeepSeek V4 Pro", provider: "deepseek", provider_configured: true, reads_images: false },
      ],
      workloads: {
        ...settings.workloads,
        financial_vision: { label: "Statement page images", description: "Held statements", group: "Financial" },
      },
      routing: { ...settings.routing, financial_vision: { ...chain[0], chain } },
    }
    api.get.mockResolvedValue(withChain)
    api.updatePolicy.mockResolvedValue({ ...withChain, policy_revision: 4 })
    render(<MemoryRouter><AISettingsPage /></MemoryRouter>)
    await screen.findByText("Provider connections")
    fireEvent.click(screen.getByRole("button", { name: /Advanced model routing/ }))

    const editor = await screen.findByTestId("model-chain")
    expect(editor).toHaveTextContent("1. Reads first")
    expect(editor).toHaveTextContent("2. If the one above fails or cannot prove its reading")
    expect(screen.getByLabelText("Statement page images, model 1")).toHaveTextContent("DeepSeek V4.1 Flash")
    expect(screen.getByLabelText("Statement page images, model 2")).toHaveTextContent("GPT-5.6 Terra")
    // Both image models are in the chain and the text-only model is never offered: nothing left to add.
    expect(screen.queryByRole("button", { name: "Add a fallback model" })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Move model 2 up" }))
    fireEvent.click(screen.getByRole("button", { name: "Save routing" }))
    await waitFor(() => expect(api.updatePolicy).toHaveBeenCalled())
    const [, saved] = api.updatePolicy.mock.calls[0]
    expect(saved.financial_vision).toEqual({ provider: "openai", model_id: "gpt-5.6-terra", chain: [chain[1], chain[0]] })
  })
})
