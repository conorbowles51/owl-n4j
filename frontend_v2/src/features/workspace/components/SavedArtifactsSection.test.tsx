import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { SavedArtifactsSection } from "./SavedArtifactsSection"
import { agentAPI } from "@/features/agent/api"
import { downloadProtectedFile } from "@/lib/protected-file"

vi.mock("@/features/agent/api", () => ({
  agentAPI: {
    listSavedArtifacts: vi.fn(),
    savedArtifactExportUrl: vi.fn(),
  },
}))

vi.mock("@/lib/protected-file", () => ({
  downloadProtectedFile: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

function renderSection() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SavedArtifactsSection caseId="case-1" />
    </QueryClientProvider>,
  )
}

describe("SavedArtifactsSection", () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it("renders the empty saved artifact state", async () => {
    vi.mocked(agentAPI.listSavedArtifacts).mockResolvedValue([])

    renderSection()

    expect(await screen.findByText("No saved artifacts yet.")).toBeInTheDocument()
    expect(agentAPI.listSavedArtifacts).toHaveBeenCalledWith("case-1")
  })

  it("renders saved artifacts and exports from the saved endpoint", async () => {
    vi.mocked(agentAPI.listSavedArtifacts).mockResolvedValue([
      {
        id: "saved-1",
        case_id: "case-1",
        destination: "workspace",
        title: "Case payments",
        note: "Use in the report memo",
        artifact_type: "table",
        artifact: {
          id: "saved-1",
          type: "table",
          title: "Case payments",
          data: {},
          metadata: {},
        },
        source_thread_id: "thread-1",
        source_run_id: "run-1",
        source_artifact_id: "artifact-1",
        created_by_user_id: "user-1",
        provenance: { run: { model_id: "gpt-5-mini" } },
        created_at: "2026-07-16T10:00:00Z",
        updated_at: "2026-07-16T10:00:00Z",
      },
    ])
    vi.mocked(agentAPI.savedArtifactExportUrl).mockReturnValue("/api/agent/saved/saved-1/export?format=csv")
    vi.mocked(downloadProtectedFile).mockResolvedValue(undefined)

    renderSection()

    expect(await screen.findByText("Case payments")).toBeInTheDocument()
    expect(screen.getByText("Use in the report memo")).toBeInTheDocument()
    expect(screen.getByText(/gpt-5-mini/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /csv/i }))

    await waitFor(() => {
      expect(agentAPI.savedArtifactExportUrl).toHaveBeenCalledWith("saved-1", "csv")
      expect(downloadProtectedFile).toHaveBeenCalledWith(
        "/api/agent/saved/saved-1/export?format=csv",
        "case-payments-table.csv",
      )
    })
  })
})
