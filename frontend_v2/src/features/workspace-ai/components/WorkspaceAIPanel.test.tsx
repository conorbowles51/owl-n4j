import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { DossierInterview } from "@/features/dossiers/api"
import type { WorkspaceAIOutput } from "../api"
import { WorkspaceAIPanel } from "./WorkspaceAIPanel"

const mocks = vi.hoisted(() => ({
  outputs: vi.fn(),
  mutate: vi.fn(),
  start: vi.fn(),
  refetch: vi.fn(),
}))

vi.mock("../hooks", () => ({
  useWorkspaceAIOutputs: () => mocks.outputs(),
  useWorkspaceAIMutation: () => ({
    mutateAsync: mocks.mutate,
    isPending: false,
  }),
}))
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: () => ({ objectUrl: "/mock-source.pdf", loading: false, error: null }),
  openProtectedFile: vi.fn(),
}))

function Location() {
  return <div data-testid="location">{useLocation().pathname}</div>
}
vi.mock("../api", () => {
  return {
    workspaceAIAPI: {
      start: mocks.start,
      cancel: vi.fn(),
      retry: vi.fn(),
      accept: vi.fn(),
      reject: vi.fn(),
    },
  }
})

const baseOutput: WorkspaceAIOutput = {
  id: "output-1",
  case_id: "case-1",
  target_type: "theory",
  target_id: "theory-1",
  output_type: "theory_analysis",
  version: 1,
  job_status: "completed",
  review_status: "pending_review",
  citation_status: "valid",
  progress: 100,
  cancel_requested: false,
  content: {
    headline: "Departure timing",
    supporting: [{ text: "The gate log records an early departure.", citation_ids: ["S1"] }],
    contradicting: [],
    contradicting_not_found_reason: "No reliable contradiction was found.",
    limitations: ["Clock calibration was not checked."],
  },
  citations: [
    {
      source_id: "S1",
      evidence_file_id: "evidence-1",
      filename: "gate-log.pdf",
      source_anchor: { page: 4 },
      content_hash: "abc",
      excerpt: "Gate log record",
      url: "/cases/case-1/evidence?file=evidence-1&page=4",
    },
  ],
  source_set: [],
  proposed_actions: [],
  accepted_targets: [],
  model_metadata: { model_id: "stub" },
  mandate_version_id: "mandate-1",
  mandate_version_number: 3,
  requested_by_user_id: "user-1",
  requested_by_name: "Alex",
  created_at: "2026-09-02T12:00:00Z",
}

function setup(outputs: WorkspaceAIOutput[] = [baseOutput]) {
  mocks.outputs.mockReturnValue({
    data: { outputs, total: outputs.length, limit: 100, offset: 0 },
    isLoading: false,
    isError: false,
    refetch: mocks.refetch,
  })
}

describe("Workspace AI review panel", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset())
    mocks.refetch.mockResolvedValue(undefined)
    mocks.start.mockResolvedValue(baseOutput)
    setup()
  })

  it.each(["theory", "dossier"] as const)("opens %s citations in place and keeps the analysis after closing", async (targetType) => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={["/cases/case-1/workspace"]}>
        <Location />
        <WorkspaceAIPanel caseId="case-1" targetType={targetType} targetId="theory-1" canEdit={false} />
      </MemoryRouter>,
    )
    await user.click(screen.getByRole("button", { name: /Departure timing/ }))
    expect(screen.getByText("The gate log records an early departure.")).toBeVisible()
    expect(screen.getByText(/No material found: No reliable contradiction/)).toBeVisible()
    expect(screen.queryByText("S1")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "gate-log.pdf, p.4" }))
    expect(screen.getByRole("dialog", { name: "gate-log.pdf" })).toBeVisible()
    expect(document.querySelector("iframe")?.getAttribute("src")).toContain("#page=4")
    expect(screen.getByTestId("location")).toHaveTextContent("/cases/case-1/workspace")
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.getByText("The gate log records an early departure.")).toBeVisible()
    expect(screen.queryByRole("button", { name: /Accept proposal/i })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Search both sides/i })).not.toBeInTheDocument()
  })

  it("requires explicit interview selection and starts a Dossier summary", async () => {
    const user = userEvent.setup()
    const interviews: DossierInterview[] = [
      {
        id: "interview-1",
        participants: ["Witness"],
        interviewer_user_ids: [],
        status: "completed",
        evidence_links: [
          {
            id: "link-1",
            evidence_file_id: "evidence-1",
            source_anchor: { page: 2 },
            evidence: {
              id: "evidence-1",
              original_filename: "statement.pdf",
              status: "processed",
              size: 100,
              sha256: "abc",
              metadata: {},
              file_url: "/api/evidence/evidence-1/file",
            },
          },
        ],
      },
    ]
    setup([])
    render(
      <MemoryRouter>
        <WorkspaceAIPanel caseId="case-1" targetType="dossier" targetId="dossier-1" canEdit interviews={interviews} />
      </MemoryRouter>,
    )
    const summarise = screen.getByRole("button", { name: /Summarise selection/i })
    expect(summarise).toBeDisabled()
    await user.click(screen.getByLabelText("Select interview 1"))
    expect(summarise).toBeEnabled()
    await user.click(summarise)
    expect(mocks.start).toHaveBeenCalledWith("case-1", {
      target_type: "dossier",
      target_id: "dossier-1",
      output_type: "statement_summary",
      interview_ids: ["interview-1"],
    })
  })

  it("defaults to the latest collapsed version and keeps older versions in a dropdown", async () => {
    const user = userEvent.setup()
    setup([baseOutput, { ...baseOutput, id: "output-2", parent_output_id: baseOutput.id, version: 2, content: { headline: "Latest summary", claims: [{ text: "Latest findings", citation_ids: [] }] } }])
    const view = render(<WorkspaceAIPanel caseId="case-1" targetType="dossier" targetId="dossier-1" canEdit={false} />)
    expect(screen.queryByText("Departure timing")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Latest summary/ })).toHaveAttribute("aria-expanded", "false")
    await user.click(screen.getByRole("button", { name: /Latest summary/ }))
    expect(screen.getByText("Latest findings")).toBeVisible()
    await user.selectOptions(screen.getByRole("combobox", { name: "Summary version" }), "output-1")
    expect(screen.getByRole("button", { name: /Departure timing/ })).toHaveAttribute("aria-expanded", "false")
    view.unmount()
    render(<WorkspaceAIPanel caseId="case-1" targetType="dossier" targetId="dossier-1" canEdit={false} />)
    expect(screen.getByRole("combobox", { name: "Summary version" })).toHaveValue("output-2")
    expect(screen.getByRole("button", { name: /Latest summary/ })).toHaveAttribute("aria-expanded", "false")
  })

  it("makes pending, accepted, rejected, and running states distinct", () => {
    setup([
      baseOutput,
      { ...baseOutput, id: "accepted", version: 2, review_status: "accepted", reviewed_by_name: "Morgan" },
      { ...baseOutput, id: "rejected", version: 3, review_status: "rejected", rejection_reason: "Insufficient depth" },
      { ...baseOutput, id: "running", version: 4, job_status: "running", review_status: "pending_review", progress: 45, content: {} },
    ])
    render(
      <MemoryRouter>
        <WorkspaceAIPanel caseId="case-1" targetType="theory" targetId="theory-1" canEdit />
      </MemoryRouter>,
    )
    expect(screen.getAllByText("Pending review").length).toBeGreaterThan(0)
    expect(screen.getByText(/Accepted by Morgan/)).toBeVisible()
    expect(screen.queryByText("Accepted")).not.toBeInTheDocument()
    expect(screen.getByText("Rejected")).toBeVisible()
    expect(screen.getByText("Running")).toBeVisible()
    expect(screen.getByText(/Safe to leave this page/)).toBeVisible()
  })
})
