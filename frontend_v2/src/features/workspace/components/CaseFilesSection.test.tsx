import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CaseFilesSection } from "./CaseFilesSection"

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  getFileUrl: vi.fn((id: string) => `/api/evidence/${id}/file`),
  pin: vi.fn(),
  unpin: vi.fn(),
  pinned: [] as Array<{ id: string; item_id: string }>,
}))

vi.mock("@/features/evidence/api", () => ({
  evidenceAPI: {
    list: mocks.list,
    getFileUrl: mocks.getFileUrl,
  },
}))

vi.mock("../hooks/use-workspace", () => ({
  workspaceKeys: {
    caseFiles: (caseId: string) => ["workspace", caseId, "case-files"],
  },
  usePinnedItems: () => ({ data: mocks.pinned }),
  usePinItem: () => ({ mutate: mocks.pin }),
  useUnpinItem: () => ({ mutate: mocks.unpin }),
}))

function renderSection() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <CaseFilesSection caseId="case-1" />
    </QueryClientProvider>,
  )
}

describe("CaseFilesSection", () => {
  const open = vi.fn()

  beforeEach(() => {
    mocks.list.mockResolvedValue([
      {
        id: "evidence-1",
        original_filename: "forensic-export.zip",
        stored_path: "/evidence/forensic-export.zip",
        size: 512,
        sha256: "a".repeat(64),
        status: "processed",
        created_at: "2026-07-16T12:00:00Z",
        summary: "AI source summary",
        summary_source: "ai",
      },
      {
        id: "evidence-2",
        original_filename: "financial-ledger.csv",
        stored_path: "/evidence/financial-ledger.csv",
        size: 256,
        sha256: "b".repeat(64),
        status: "processed",
        created_at: "2026-07-16T12:05:00Z",
        summary: "Human reviewed source summary",
        summary_source: "human",
      },
      {
        id: "document-1",
        original_filename: "brief.pdf",
        stored_path: "/evidence/brief.pdf",
        size: 128,
        sha256: "c".repeat(64),
        status: "processed",
        created_at: "2026-07-16T12:10:00Z",
        summary: "Document summary",
        summary_source: "ai",
      },
    ])
    mocks.pinned = []
    vi.spyOn(window, "open").mockImplementation((url, target, features) => {
      open(url, target, features)
      return null
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    open.mockReset()
  })

  it("shows inline summaries with AI/human status and opens the source file", async () => {
    renderSection()

    expect(await screen.findByText("forensic-export.zip")).toBeInTheDocument()
    expect(screen.getByText("financial-ledger.csv")).toBeInTheDocument()
    expect(screen.queryByText("brief.pdf")).not.toBeInTheDocument()

    expect(screen.getByText("AI summary")).toBeInTheDocument()
    expect(screen.getByText("AI source summary")).toBeInTheDocument()
    expect(screen.getByText("Human summary")).toBeInTheDocument()
    expect(screen.getByText("Human reviewed source summary")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Open forensic-export.zip" }))

    expect(open).toHaveBeenCalledWith(
      "/api/evidence/evidence-1/file",
      "_blank",
      "noopener,noreferrer",
    )
  })
})
