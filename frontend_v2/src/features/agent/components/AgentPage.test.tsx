import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AgentPage } from "./AgentPage"
import { agentAPI } from "../api"
import { usePermissions } from "@/hooks/use-permissions"

const mocks = vi.hoisted(() => ({
  listThreads: vi.fn(),
  getThread: vi.fn(),
  streamMessage: vi.fn(),
  cancelRun: vi.fn(),
  artifactExportUrl: vi.fn(),
  saveArtifact: vi.fn(),
  usePermissions: vi.fn(),
}))

vi.mock("../api", () => ({
  agentAPI: {
    listThreads: mocks.listThreads,
    getThread: mocks.getThread,
    streamMessage: mocks.streamMessage,
    cancelRun: mocks.cancelRun,
    artifactExportUrl: mocks.artifactExportUrl,
    saveArtifact: mocks.saveArtifact,
  },
}))

vi.mock("@/hooks/use-permissions", () => ({
  usePermissions: mocks.usePermissions,
}))

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}))

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

function permission(canEdit: boolean) {
  return {
    canEdit,
    canDelete: false,
    canInvite: false,
    canUploadEvidence: canEdit,
    isOwner: false,
    isSuperAdmin: false,
  }
}

function renderPage(canEdit: boolean) {
  vi.mocked(usePermissions).mockReturnValue(permission(canEdit))
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/cases/case-1/agent"]}>
        <Routes>
          <Route path="/cases/:id/agent" element={<AgentPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function openThread() {
  fireEvent.click(await screen.findByText("Saved thread"))
  await screen.findByRole("heading", { name: "Payments table" })
}

describe("AgentPage artifact save permissions", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(agentAPI.listThreads).mockResolvedValue([
      {
        id: "thread-1",
        case_id: "case-1",
        title: "Saved thread",
        status: "active",
        owner_user_id: "user-1",
        message_count: 1,
        last_message_at: "2026-07-16T10:00:00Z",
        created_at: "2026-07-16T10:00:00Z",
        updated_at: "2026-07-16T10:00:00Z",
      },
    ])
    vi.mocked(agentAPI.getThread).mockResolvedValue({
      id: "thread-1",
      case_id: "case-1",
      title: "Saved thread",
      status: "active",
      owner_user_id: "user-1",
      message_count: 1,
      last_message_at: "2026-07-16T10:00:00Z",
      created_at: "2026-07-16T10:00:00Z",
      updated_at: "2026-07-16T10:00:00Z",
      messages: [],
      artifacts: [
        {
          id: "artifact-1",
          type: "table",
          title: "Payments table",
          data: {
            columns: [{ key: "person", label: "Person" }],
            rows: [{ person: "Daniel Rook" }],
          },
          metadata: {},
        },
      ],
    })
    vi.mocked(agentAPI.artifactExportUrl).mockReturnValue("/api/agent/artifacts/artifact-1/export?format=csv")
  })

  it("disables artifact saving for view-only users", async () => {
    renderPage(false)
    await openThread()

    const saveButton = screen.getByRole("button", { name: /^save$/i })

    expect(saveButton).toBeDisabled()
    expect(saveButton).toHaveAttribute("title", "Saving requires case edit access")
  })

  it("opens artifact saving for editors", async () => {
    renderPage(true)
    await openThread()

    fireEvent.click(screen.getByRole("button", { name: /^save$/i }))

    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: /title/i })).toHaveValue("Payments table")
  })
})
