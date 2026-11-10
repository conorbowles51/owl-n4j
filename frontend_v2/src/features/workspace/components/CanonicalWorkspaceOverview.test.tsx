import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CanonicalWorkspaceOverview } from "./CanonicalWorkspaceOverview"
import { overview } from "./overview-fixture"

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  setAttention: vi.fn(),
  retry: vi.fn(),
}))
vi.mock("../hooks/use-workspace", () => ({
  useWorkspaceOverview: () => mocks.overview(),
  useSetAttentionState: () => ({ mutateAsync: mocks.setAttention }),
}))
vi.mock("./CaseBriefPanel", () => ({
  CaseBriefPanel: () => <div>Expanded change brief</div>,
}))
vi.mock("@/features/phones/ContinueReading", () => ({
  AssignedReviewsFeed: () => <div>Assigned review work</div>,
}))
vi.mock("@/features/dossiers/components/DossierSourceViewer", () => ({
  DossierSourceViewer: ({
    source,
    onClose,
  }: {
    source: { name: string }
    onClose: () => void
  }) => (
    <div role="dialog" aria-label={source.name}>
      <button onClick={onClose}>Close source</button>
    </div>
  ),
}))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
const renderOverview = (canEdit = true) =>
  render(
    <MemoryRouter>
      <CanonicalWorkspaceOverview
        caseId="case-1"
        caseName="Harbour Review"
        canEdit={canEdit}
      />
    </MemoryRouter>
  )

describe("Workspace orientation", () => {
  beforeEach(() => {
    mocks.overview
      .mockReset()
      .mockReturnValue({
        data: overview,
        isLoading: false,
        isError: false,
        refetch: mocks.retry,
      })
    mocks.setAttention.mockReset().mockResolvedValue({})
    mocks.retry.mockReset()
  })

  it("starts with case identity and personal work, with separate destinations", () => {
    renderOverview()
    expect(
      screen.getByRole("heading", { name: "Harbour Review" })
    ).toBeInTheDocument()
    const personal = screen.getByRole("region", { name: "Your work" })
    expect(
      within(personal).getByText("Review account statement")
    ).toBeInTheDocument()
    const casework = screen.getByRole("region", { name: "Casework" })
    expect(
      personal.compareDocumentPosition(casework) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
    expect(screen.getByRole("link", { name: "All casework" })).toHaveAttribute(
      "href",
      "/cases/case-1/workspace?view=casework"
    )
    expect(screen.getByRole("link", { name: /Henry Example/ })).toHaveAttribute(
      "href",
      "/cases/case-1/dossiers?dossier=dossier-1"
    )
    expect(screen.getByRole("link", { name: "Case setup" })).toHaveAttribute(
      "href",
      "/cases/case-1/workspace?view=setup"
    )
  })

  it("bounds the preview and links every type and the complete work list", () => {
    mocks.overview.mockReturnValue({
      data: {
        ...overview,
        recent_casework: Array.from({ length: 8 }, (_, i) => ({
          ...overview.recent_casework[0],
          id: `e${i}`,
          title: `Finding ${i}`,
        })),
        casework_by_type: {
          finding: { entries: [], total: 41 },
          note: { entries: [], total: 6 },
          theory: { entries: [], total: 2 },
        },
        upcoming_work: {
          deadlines: Array.from({ length: 5 }, (_, i) => ({
            id: `d${i}`,
            name: `Date ${i}`,
            due_date: "2026-11-18",
            href: `/work/${i}`,
          })),
          upcoming_deadline_total: 5,
          past_deadline_total: 2,
          tasks: [],
          open_task_total: 6,
        },
      },
    })
    renderOverview()
    expect(screen.getAllByText(/^Finding \d$/)).toHaveLength(3)
    expect(screen.getByRole("link", { name: "Findings 41" })).toHaveAttribute(
      "href",
      "/cases/case-1/workspace?view=casework&kind=finding"
    )
    expect(screen.getAllByText(/^Date \d$/)).toHaveLength(3)
    expect(
      screen.getByText("Showing the next 3 of 5 deadlines.")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /2 overdue deadlines/ })
    ).toHaveAttribute("href", "/cases/case-1/workspace?view=work")
    expect(
      screen.getByRole("link", { name: /6 open tasks/ })
    ).toBeInTheDocument()
  })

  it("opens pinned sources over the overview and returns without navigation", () => {
    renderOverview()
    fireEvent.click(
      screen.getByRole("button", { name: "account-statement.pdf" })
    )
    expect(
      screen.getByRole("dialog", { name: "account-statement.pdf" })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Close source" }))
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(
      screen.getByRole("heading", { name: "Harbour Review" })
    ).toBeInTheDocument()
  })

  it("removes retired and duplicated sections and opens the brief on demand", () => {
    renderOverview()
    expect(screen.queryByText("Snapshots")).toBeNull()
    expect(screen.queryByText("Case files")).toBeNull()
    expect(screen.queryByText("Continue reading")).toBeNull()
    expect(screen.queryByText("Expanded change brief")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "What changed" }))
    expect(screen.getByText("Expanded change brief")).toBeInTheDocument()
  })

  it("allows personal reminder dismissal without implying completion", async () => {
    renderOverview(false)
    expect(
      screen.getByRole("link", { name: "Case context" })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /dismiss disclosure response/i })
    ).toBeNull()
    const dismiss = screen.getByRole("button", {
      name: /dismiss review account statement/i,
    })
    expect(dismiss).toHaveAttribute(
      "title",
      expect.stringContaining("does not complete")
    )
    fireEvent.click(dismiss)
    await waitFor(() =>
      expect(mocks.setAttention).toHaveBeenCalledWith({
        attentionKey: overview.personal_attention[0].attention_key,
        action: "dismiss",
        snoozedUntil: undefined,
      })
    )
  })

  it("retains the reminder after failure and permits retry", async () => {
    mocks.setAttention
      .mockRejectedValueOnce(new Error("Unavailable"))
      .mockResolvedValueOnce({})
    renderOverview()
    fireEvent.click(
      screen.getByRole("button", { name: /dismiss review account statement/i })
    )
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: /dismiss review account statement/i,
        })
      ).toBeEnabled()
    )
    expect(screen.getByText("Review account statement")).toBeInTheDocument()
    fireEvent.click(
      screen.getByRole("button", { name: /dismiss review account statement/i })
    )
    await waitFor(() => expect(mocks.setAttention).toHaveBeenCalledTimes(2))
  })

  it("has a small empty state with no description requirement", () => {
    mocks.overview.mockReturnValue({
      data: {
        ...overview,
        context: { mandate_complete: false },
        shared_attention: [],
        personal_attention: [],
        recent_casework: [],
        dossier_highlights: [],
        pinned_evidence: [],
      },
    })
    renderOverview()
    expect(screen.getByText("No task reminders")).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "Case right now" })).toBeNull()
    expect(screen.queryByRole("textbox")).toBeNull()
    expect(
      screen.getByRole("link", { name: "All casework" })
    ).toBeInTheDocument()
  })

  it("recovers overview loading failures", () => {
    mocks.overview.mockReturnValue({ isError: true, refetch: mocks.retry })
    renderOverview()
    fireEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect(mocks.retry).toHaveBeenCalledOnce()
  })

  it("preserves ready-source actions and refuses external metadata links", () => {
    mocks.overview.mockReturnValue({
      data: {
        ...overview,
        shared_attention: [
          {
            ...overview.shared_attention[0],
            attention_key: "ready",
            metadata: {
              action: {
                label: "Open phone summary",
                href: "/cases/case-1/phones/p1",
              },
            },
          },
          {
            ...overview.shared_attention[0],
            attention_key: "unsafe",
            metadata: {
              action: { label: "Elsewhere", href: "//example.invalid" },
            },
          },
        ],
      },
    })
    renderOverview()
    expect(
      screen.getByRole("link", { name: "Open phone summary" })
    ).toHaveAttribute("href", "/cases/case-1/phones/p1")
    expect(screen.queryByRole("link", { name: "Elsewhere" })).toBeNull()
  })
})
