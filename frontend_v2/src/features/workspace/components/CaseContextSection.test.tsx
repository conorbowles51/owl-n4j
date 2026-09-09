import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { CaseContext } from "../api"
import { CaseContextSection } from "./CaseContextSection"

const mocks = vi.hoisted(() => ({
  updateContext: vi.fn(),
  createMandate: vi.fn(),
}))

const context: CaseContext = {
  case_id: "case-1",
  case_summary: "A cross-border asset investigation",
  background: "A disclosure triggered review.",
  investigation_type: "Asset tracing",
  jurisdiction: "Ireland and United Kingdom",
  active_template_key: "generic",
  custom_values: {},
  mandate_complete: true,
  active_mandate: {
    id: "mandate-1",
    case_id: "case-1",
    version_number: 1,
    objective: "Trace the disputed transfers",
    key_questions: ["Who controlled the destination account?"],
    in_scope: "Transfers after notice",
    out_of_scope: null,
    perspective: "Test both innocent and adverse explanations",
    success_criteria: "A cited chronology",
    constraints: "Do not infer beyond evidence",
    author_name: "Case Owner",
    created_at: "2026-09-01T12:00:00Z",
  },
  templates: [
    {
      key: "generic",
      name: "General investigation",
      description: "Universal investigation context.",
      is_builtin: true,
      fields: [],
    },
    {
      key: "criminal_defence",
      name: "Criminal defence",
      description: "Specialised criminal-defence context.",
      is_builtin: true,
      fields: [
        {
          key: "charges",
          label: "Charges / allegations",
          type: "long_text",
          choices: [],
          required: false,
          position: 0,
        },
        {
          key: "custody",
          label: "In custody",
          type: "boolean",
          choices: [],
          required: false,
          position: 1,
        },
        {
          key: "risk_level",
          label: "Risk level",
          type: "single_choice",
          choices: ["Low", "High"],
          required: false,
          position: 2,
        },
      ],
    },
  ],
  updated_at: "2026-09-01T12:00:00Z",
}

vi.mock("../hooks/use-workspace", () => ({
  useCaseContext: () => ({ data: context, isLoading: false }),
  useMandateVersions: () => ({ data: [context.active_mandate] }),
  useUpdateCaseContext: () => ({
    mutateAsync: mocks.updateContext,
    isPending: false,
  }),
  useCreateMandateVersion: () => ({
    mutateAsync: mocks.createMandate,
    isPending: false,
  }),
}))

vi.mock("@/features/dossiers/hooks", () => ({
  useDossiers: () => ({ data: { dossiers: [] } }),
}))

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

describe("CaseContextSection", () => {
  beforeEach(() => {
    mocks.updateContext.mockReset().mockResolvedValue(context)
    mocks.createMandate.mockReset().mockResolvedValue(context.active_mandate)
  })

  it("shows universal context and mandate without edit actions to a viewer", () => {
    render(<CaseContextSection caseId="case-1" canEdit={false} />)

    expect(screen.getByText(context.case_summary!)).toBeInTheDocument()
    expect(screen.getByText("Trace the disputed transfers")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /new version/i }),
    ).not.toBeInTheDocument()
  })

  it("uses typed template controls and saves structured context", async () => {
    render(<CaseContextSection caseId="case-1" canEdit />)
    fireEvent.click(screen.getByRole("button", { name: "Edit" }))
    fireEvent.change(screen.getByDisplayValue("General investigation"), {
      target: { value: "criminal_defence" },
    })
    fireEvent.change(screen.getByLabelText("Charges / allegations"), {
      target: { value: "Fraud and false accounting" },
    })
    fireEvent.click(screen.getByText("No"))
    fireEvent.change(screen.getByLabelText("Risk level"), {
      target: { value: "High" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => expect(mocks.updateContext).toHaveBeenCalledTimes(1))
    expect(mocks.updateContext).toHaveBeenCalledWith(
      expect.objectContaining({
        active_template_key: "criminal_defence",
        custom_values: {
          charges: "Fraud and false accounting",
          custody: true,
          risk_level: "High",
        },
      }),
    )
  })

  it("creates a new immutable mandate version from the visible current version", async () => {
    render(<CaseContextSection caseId="case-1" canEdit />)
    fireEvent.click(screen.getByRole("button", { name: /new version/i }))
    fireEvent.change(screen.getByLabelText("Objective"), {
      target: { value: "Test the revised transfer theory" },
    })
    fireEvent.click(screen.getByRole("button", { name: /activate version/i }))

    await waitFor(() => expect(mocks.createMandate).toHaveBeenCalledTimes(1))
    expect(mocks.createMandate).toHaveBeenCalledWith(
      expect.objectContaining({
        objective: "Test the revised transfer theory",
        key_questions: ["Who controlled the destination account?"],
      }),
    )
  })
})
