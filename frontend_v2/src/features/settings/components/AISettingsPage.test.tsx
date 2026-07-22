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
  ],
  models: [
    { id: "gpt-5.6-terra", name: "GPT-5.6 Terra", provider: "openai", provider_configured: true },
    { id: "claude-sonnet-5", name: "Claude Sonnet 5", provider: "anthropic", provider_configured: false },
  ],
  workloads: {
    chat: { label: "AI chat", description: "Chat surfaces", group: "Interactive" },
  },
  routing: { chat: { provider: "openai", model_id: "gpt-5.6-terra" } },
  recommended_profiles: {
    openai: { chat: { provider: "openai", model_id: "gpt-5.6-terra" } },
    anthropic: { chat: { provider: "anthropic", model_id: "claude-sonnet-5" } },
    gemini: { chat: { provider: "gemini", model_id: "gemini-3.6-flash" } },
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

  it("shows only Loupe's three supported cloud providers", async () => {
    render(<MemoryRouter><AISettingsPage /></MemoryRouter>)

    expect(await screen.findByText("Provider connections")).toBeInTheDocument()
    expect(screen.getAllByText("OpenAI").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Anthropic").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Google Gemini").length).toBeGreaterThan(0)
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
})
