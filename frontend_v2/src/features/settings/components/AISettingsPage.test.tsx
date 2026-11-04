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

  it("says Search embeddings is down, why, and since when, instead of Ready", async () => {
    api.get.mockResolvedValue({
      ...settings,
      supporting_services: [
        {
          id: "embeddings", label: "Search embeddings", provider: "openai", status: "down", description: "Semantic search",
          health: {
            status: "down",
            reason: "the search service (OpenAI) has no credits left: 429 insufficient quota",
            down_since: "2026-11-04T05:10:00+00:00",
            last_success_at: "2026-10-27T18:42:49+00:00",
            failures_since_down: 3,
          },
        },
        settings.supporting_services[1],
      ],
    })
    render(<MemoryRouter><AISettingsPage /></MemoryRouter>)

    const line = await screen.findByTestId("service-down-embeddings")
    expect(line).toHaveTextContent("Down: the search service (OpenAI) has no credits left: 429 insufficient quota.")
    expect(line).toHaveTextContent("Failing since")
    expect(line).toHaveTextContent("(3 failed calls recorded)")
    expect(line).toHaveTextContent("Last call that worked:")
    expect(line).toHaveTextContent("Document searches use the words instead and say so.")
    expect(screen.getByText("Down")).toBeInTheDocument()
  })

  it("never shows the first recorded failure as the outage start when the start was not recorded", async () => {
    api.get.mockResolvedValue({
      ...settings,
      supporting_services: [
        {
          id: "embeddings", label: "Search embeddings", provider: "openai", status: "down", description: "Semantic search",
          health: {
            status: "down",
            reason: "the search service (OpenAI) has no credits left: 429 insufficient quota",
            down_since: null,
            down_since_known: false,
            first_recorded_failure_at: "2026-11-04T06:42:22+00:00",
            last_success_at: "2026-10-27T18:42:49+00:00",
            failures_since_down: 5,
          },
        },
      ],
    })
    render(<MemoryRouter><AISettingsPage /></MemoryRouter>)

    const line = await screen.findByTestId("service-down-embeddings")
    expect(line).toHaveTextContent("Failing since some time between")
    expect(line).toHaveTextContent("(the last call that worked)")
    expect(line).toHaveTextContent("(the first failure recorded)")
    expect(line).toHaveTextContent("(5 failed calls recorded)")
    expect(line.textContent).not.toMatch(/Failing since [A-Z][a-z]{2} \d/)
  })

  it("says Audio transcription is down with its own consequence when the OpenAI account refuses calls", async () => {
    api.get.mockResolvedValue({
      ...settings,
      supporting_services: [
        {
          id: "transcription", label: "Audio transcription", provider: "openai", status: "down",
          description: "Transcribes uploaded audio before ingestion.",
          health: {
            status: "down",
            reason: "the OpenAI account has no credits left (429 insufficient quota); found by the search embedding calls, which use the same account",
            down_since: "2026-11-04T05:10:00+00:00",
            last_success_at: "2026-09-17T15:05:45+00:00",
            consequence: "Audio uploaded now cannot be transcribed until the account works again.",
          },
        },
      ],
    })
    render(<MemoryRouter><AISettingsPage /></MemoryRouter>)

    const line = await screen.findByTestId("service-down-transcription")
    expect(line).toHaveTextContent("Down: the OpenAI account has no credits left")
    expect(line).toHaveTextContent("Audio uploaded now cannot be transcribed until the account works again.")
    expect(line).not.toHaveTextContent("Document searches")
    expect(screen.queryByText("Ready")).not.toBeInTheDocument()
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

  it("shows the DeepSeek only switch with who switched it, and saves it switched off", async () => {
    const chain = [
      { provider: "deepseek", model_id: "deepseek-flash" },
      { provider: "openai", model_id: "gpt-5.6-terra" },
    ]
    const withSwitch = {
      ...settings,
      models: [
        { id: "gpt-5.6-terra", name: "GPT-5.6 Terra", provider: "openai", provider_configured: true, reads_images: true },
        { id: "deepseek-flash", name: "DeepSeek V4.1 Flash", provider: "deepseek", provider_configured: true, reads_images: true },
      ],
      workloads: {
        ...settings.workloads,
        financial_vision: { label: "Statement page images", description: "Held statements", group: "Financial" },
      },
      routing: {
        ...settings.routing,
        financial_vision: { ...chain[0], chain, deepseek_only: true, deepseek_only_changed_by: "neil@example.com",
          deepseek_only_changed_at: "2026-10-28T03:30:00+00:00" },
      },
    }
    api.get.mockResolvedValue(withSwitch)
    api.updatePolicy.mockResolvedValue({ ...withSwitch, policy_revision: 4 })
    render(<MemoryRouter><AISettingsPage /></MemoryRouter>)
    await screen.findByText("Provider connections")
    fireEvent.click(screen.getByRole("button", { name: /Advanced model routing/ }))

    const box = await screen.findByTestId("deepseek-only")
    expect(box).toHaveTextContent("On: only DeepSeek reads statements")
    expect(box).toHaveTextContent("Last switched by neil@example.com")
    const toggle = screen.getByRole("switch", { name: "Statement page images: DeepSeek only" })
    expect(toggle).toBeChecked()
    fireEvent.click(toggle)
    expect(box).toHaveTextContent("Off: DeepSeek reads first")
    fireEvent.click(screen.getByRole("button", { name: "Save routing" }))
    await waitFor(() => expect(api.updatePolicy).toHaveBeenCalled())
    const [, saved] = api.updatePolicy.mock.calls[0]
    expect(saved.financial_vision.deepseek_only).toBe(false)
    expect(saved.financial_vision.chain).toEqual(chain)
  })
})
