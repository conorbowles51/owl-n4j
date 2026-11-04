import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { WorkspaceOverviewResponse } from "../api"
import { CanonicalWorkspaceOverview } from "./CanonicalWorkspaceOverview"

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  setAttention: vi.fn(),
  caseContext: vi.fn(),
}))

const overview: WorkspaceOverviewResponse = {
  case_id: "case-1",
  as_of: "2026-09-02T12:00:00Z",
  timezone: "Europe/Dublin",
  shared_attention: [
    {
      attention_key: "deadline:deadline-1:deadline_overdue:v1",
      source_type: "deadline",
      source_id: "deadline-1",
      reason_code: "deadline_overdue",
      reason_label: "Deadline overdue",
      rank: 1,
      priority_band: 0,
      title: "Disclosure response",
      due_at: "2026-09-01T00:00:00+01:00",
      href: "/cases/case-1/workspace?view=work&item=deadline-1",
      metadata: {},
    },
  ],
  personal_attention: [
    {
      attention_key: "task:task-1:task_urgent:v2",
      source_type: "task",
      source_id: "task-1",
      reason_code: "task_urgent",
      reason_label: "Urgent task",
      rank: 1,
      priority_band: 0,
      title: "Review account statement",
      summary: "Resolve the unexplained transfer.",
      href: "/cases/case-1/workspace?view=work&item=task-1",
      metadata: {},
    },
  ],
  context: {
    case_summary: "Cross-border asset tracing investigation",
    background: "A disclosure raised questions about beneficial control.",
    investigation_type: "Asset tracing",
    jurisdiction: "Ireland",
    mandate_complete: true,
    mandate: {
      id: "mandate-1",
      version_number: 2,
      objective: "Trace the disputed transfers",
      key_questions: ["Who controlled the destination account?"],
    },
  },
  recent_casework: [
    {
      id: "entry-1",
      entry_type: "finding",
      title: "Control was retained",
      summary: "Signing authority remained unchanged.",
      review_state: "pending",
      href: "/cases/case-1/workspace?view=casework&entry=entry-1",
    },
  ],
  dossier_highlights: [
    {
      id: "dossier-1",
      display_name: "Henry Example",
      dossier_type: "person",
      summary: "Account signatory and company director.",
      importance: "high",
      needs_link_review: false,
      href: "/cases/case-1/dossiers?dossier=dossier-1",
    },
  ],
  pinned_evidence: [
    {
      id: "pin-1",
      item_type: "evidence",
      item_id: "evidence-1",
      evidence_file_id: "evidence-1",
      filename: "account-statement.pdf",
      pinned_by_name: "Case Owner",
    },
  ],
  bounded: true,
  limits: { shared_attention: 12, personal_attention: 12 },
}

vi.mock("../hooks/use-workspace", () => ({
  useWorkspaceOverview: (...args: unknown[]) => mocks.overview(...args),
  useSetAttentionState: () => ({
    mutateAsync: mocks.setAttention,
    isPending: false,
  }),
}))

vi.mock("./CaseContextSection", () => ({
  CaseContextSection: () => {
    mocks.caseContext()
    return <div>Full case context editor</div>
  },
}))

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock("./CaseBriefPanel", () => ({
  CaseBriefPanel: ({ caseId }: { caseId: string }) => <div data-testid="case-brief-panel">{caseId}</div>,
}))
vi.mock("./CaseFileSummaries", () => ({
  CaseFileSummaries: ({ caseId }: { caseId: string }) => <div data-testid="case-file-summaries">{caseId}</div>,
}))
vi.mock("@/features/cases/components/SnapshotsSection", () => ({
  SnapshotsSection: ({ caseId }: { caseId: string }) => <div data-testid="snapshots-section">{caseId}</div>,
}))
vi.mock("./HowThisWasFound", () => ({
  HowThisWasFound: ({ entryId }: { entryId: string }) => <div data-testid="how-this-was-found">{entryId}</div>,
}))

function renderOverview(canEdit = true) {
  return render(
    <MemoryRouter>
      <CanonicalWorkspaceOverview
        caseId="case-1"
        canEdit={canEdit}
        onOpenCasework={vi.fn()}
      />
    </MemoryRouter>,
  )
}

describe("CanonicalWorkspaceOverview", () => {
  beforeEach(() => {
    mocks.overview.mockReset().mockReturnValue({
      data: overview,
      isLoading: false,
      isError: false,
    })
    mocks.setAttention.mockReset().mockResolvedValue({})
    mocks.caseContext.mockReset()
  })

  it("separates ranked shared awareness from personal work using one overview query", () => {
    renderOverview()

    expect(screen.getByRole("heading", { name: "Case right now" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Your work" })).toBeInTheDocument()
    expect(screen.getByText("Deadline overdue")).toBeInTheDocument()
    expect(screen.getAllByText("Priority 1")).toHaveLength(2)
    expect(screen.getByText("Review account statement")).toBeInTheDocument()
    expect(screen.getByText("Henry Example")).toBeInTheDocument()
    expect(screen.getByText("account-statement.pdf")).toBeInTheDocument()
    expect(mocks.overview).toHaveBeenCalledTimes(1)
    expect(mocks.caseContext).not.toHaveBeenCalled()
  })

  it("a ready phone's card says Conversations are ready and opens its summary (07 J-1 step 4)", () => {
    mocks.overview.mockReturnValue({
      data: {
        ...overview,
        shared_attention: [{
          attention_key: "phone_reading:j1:phone_ready:v1", source_type: "phone_reading", source_id: "j1", reason_code: "phone_ready",
          reason_label: "Phone report ready", rank: 1, priority_band: 4, title: "C3 is ready",
          summary: "Conversations are ready. Nothing is still running.", href: "/cases/case-1/phones/e1",
          metadata: { action: { label: "Open the phone summary", href: "/cases/case-1/phones/e1" } },
        }, { ...overview.shared_attention[0], metadata: { action: { label: "Elsewhere", href: "https://example.invalid" } } }],
      },
      isLoading: false,
      isError: false,
    })
    renderOverview()
    expect(screen.getByText(/Conversations are ready\./)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Open the phone summary" })).toHaveAttribute("href", "/cases/case-1/phones/e1")
    expect(screen.queryByRole("link", { name: "Elsewhere" })).toBeNull() // only paths inside the app
  })

  it("a finding in Recent casework carries its How this was found block, outside its button (07 J-17)", () => {
    renderOverview()
    const block = screen.getByTestId("how-this-was-found")
    expect(block).toHaveTextContent("entry-1")
    expect(block.closest("button")).toBeNull()
  })

  it("loads the full context editor only when an editor requests it", () => {
    renderOverview()
    fireEvent.click(screen.getByRole("button", { name: "Edit case setup" }))
    expect(screen.getByText("Full case context editor")).toBeInTheDocument()
    expect(mocks.caseContext).toHaveBeenCalledTimes(1)
  })

  it("lets a viewer manage only their personal attention state", async () => {
    renderOverview(false)

    expect(screen.queryByRole("button", { name: "Edit case setup" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /dismiss disclosure response/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /dismiss review account statement/i }))
    await waitFor(() =>
      expect(mocks.setAttention).toHaveBeenCalledWith({
        attentionKey: "task:task-1:task_urgent:v2",
        action: "dismiss",
        snoozedUntil: undefined,
      }),
    )
  })

  it("renders purposeful empty states for both attention collections", () => {
    mocks.overview.mockReturnValue({
      data: { ...overview, shared_attention: [], personal_attention: [] },
      isLoading: false,
      isError: false,
    })
    renderOverview(false)

    expect(screen.getByText("Nothing critical needs attention")).toBeInTheDocument()
    expect(screen.getByText("You’re caught up")).toBeInTheDocument()
  })

  it("shows this case's snapshots in the Workspace (BUG-009: snapshots were not shown there)", () => {
    renderOverview(true)
    expect(screen.getByRole("heading", { name: "Snapshots" })).toBeInTheDocument()
    expect(screen.getByTestId("snapshots-section")).toHaveTextContent("case-1")
    // FEAT-001: file summaries inline in the Workspace
    expect(screen.getByRole("heading", { name: "Case files" })).toBeInTheDocument()
    expect(screen.getByTestId("case-file-summaries")).toHaveTextContent("case-1")
  })

  it("lays the Workspace out in the users' order (FEAT-011): deadlines and tasks, Findings, then the rest", () => {
    mocks.overview.mockReturnValue({
      data: {
        ...overview,
        casework_by_type: {
          finding: { entries: overview.recent_casework, total: 9 },
          theory: { entries: [{ id: "t1", entry_type: "theory", title: "Nominee director", href: "/t1" }], total: 1 },
          note: { entries: [{ id: "n1", entry_type: "note", title: "Call with bank", href: "/n1" }], total: 1 },
        },
        upcoming_work: {
          deadlines: [{ id: "d1", name: "Disclosure response", due_date: "2026-09-05", href: "/d1" }],
          upcoming_deadline_total: 3,
          past_deadline_total: 2,
          tasks: [{ id: "k1", title: "Chase bank", status: "todo", priority: "urgent", assignee_name: "Owner", href: "/k1" }],
          open_task_total: 1,
        },
        interviews: [{
          id: "i1", dossier_id: "dossier-1", dossier_name: "Henry Example", interview_date: null, date_value: "2026-08",
          participants: ["Henry Example", { name: "Det. Ruiz", role: "interviewed_by" }], status: "completed",
          summary: "Denied signing.", href: "/cases/case-1/dossiers?dossier=dossier-1",
        }],
        interview_total: 4,
      },
      isLoading: false,
      isError: false,
    })
    renderOverview()
    const order = [
      "Case deadlines and tasks", "Findings", "Case right now", "Your work", "case-brief-panel",
      "Client profile and exposure", "Investigative theories", "Notes", "Snapshots",
      "Witnesses: interviews and statements", "Entity summary", "Pinned Evidence", "Case files", "Graph · Timeline · Map",
    ]
    const nodes = order.map((label) =>
      label === "case-brief-panel" ? screen.getByTestId(label) : screen.getAllByText(label, { exact: true })[0])
    for (let i = 1; i < nodes.length; i++) {
      expect(nodes[i - 1].compareDocumentPosition(nodes[i]) & Node.DOCUMENT_POSITION_FOLLOWING, order[i]).toBeTruthy()
    }
    // True counts, never a clipped list shown as whole
    expect(screen.getByText(/Newest 1 of 9 findings/)).toBeInTheDocument()
    expect(screen.getByText(/3 upcoming deadlines · 2 past · 1 open task/)).toBeInTheDocument()
    expect(screen.getByText("Next deadlines (1 of 3)")).toBeInTheDocument()
    expect(screen.getByText(/Newest 1 of 4 interviews and statements/)).toBeInTheDocument()
    expect(screen.getByText(/Interviewed by Det\. Ruiz/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open Timeline" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open Map" })).toBeInTheDocument()
  })
})
