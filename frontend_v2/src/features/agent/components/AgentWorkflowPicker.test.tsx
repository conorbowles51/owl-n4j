import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { AgentWorkflowPicker } from "./AgentWorkflowPicker"
import { fillWorkflowQuestion, workflowSlots } from "../workflow-question"
import { agentAPI } from "../api"
import type { AgentWorkflow, AgentWorkflowCatalogue } from "../types"

const step = (tool: string, runs = true, extra: Partial<{ in_build: boolean; data_missing: string[]; by_person: boolean }> = {}) => ({
  tool, why: `why ${tool}`, optional: false, by_person: false, in_build: true, data_missing: [] as string[], runs, ...extra,
})

const wf = (over: Partial<AgentWorkflow>): AgentWorkflow => ({
  id: "x", number: 1, title: "X", question: "Q?", starting_question: "Q?", extra: false, steps: [], proposals: [],
  person_confirms: "each item", adds_requirement: null, requirement_met_by: [], ...over,
})

const catalogue: AgentWorkflowCatalogue = {
  schema: "loupe.agent.workflows/1",
  counts: { ledger: 5, phones: 0, documents: 0, dossiers: 4, timeline: 0 },
  total: 3,
  workflows: [
    wf({
      id: "hidden-assets", number: 2, title: "Hidden assets", question: "Which accounts?",
      starting_question: "Which accounts does {person} hold?",
      readiness: { id: "hidden-assets", number: 2, title: "Hidden assets", status: "partial", reasons: [], tools_missing: [],
        steps_that_run: 2, steps: [step("get_money_signal_leads", false, { data_missing: ["phones"] }), step("get_financial_coverage"), step("analyze_financial_transactions")] },
    }),
    wf({
      id: "last-proof-of-life", number: 1, title: "Last proof of life",
      readiness: { id: "last-proof-of-life", number: 1, title: "Last proof of life", status: "not_possible",
        reasons: ["the case holds no phone extractions"], tools_missing: [], steps_that_run: 0, steps: [step("get_day_activity", false)] },
    }),
    wf({ id: "county-lines", number: 11, title: "County lines", extra: true }),
  ],
}

it("fills the named question's slots, and leaves an empty slot visibly empty", () => {
  expect(workflowSlots("{person} paid {other} on {date}; {person}")).toEqual(["person", "other", "date"])
  expect(fillWorkflowQuestion("Did {person} pay {other}?", { person: "Sam" })).toBe("Did Sam pay [Other person]?")
})

it("shows the case's counts, readiness from the server, and starts a workflow with its id and filled question", async () => {
  const list = vi.spyOn(agentAPI, "listWorkflows").mockResolvedValue(catalogue)
  const onStart = vi.fn()
  render(<AgentWorkflowPicker caseId="case-1" disabled={false} onStart={onStart} />)
  expect(screen.getByText(/Reading this case's ledger, phones and documents/)).toBeTruthy()
  await waitFor(() => expect(screen.getByTestId("agent-workflow-picker")).toBeTruthy())
  expect(list).toHaveBeenCalledWith("case-1")
  expect(screen.getByText(/This case holds 5 ledger rows, 0 phones/)).toBeTruthy()
  expect(screen.getByText("Partly: 2 of 3 steps can run")).toBeTruthy()
  expect(screen.getByText("Not possible on this case")).toBeTruthy()
  expect(screen.getByText("the case holds no phone extractions")).toBeTruthy()
  expect((screen.getByLabelText("Use workflow Last proof of life") as HTMLButtonElement).disabled).toBe(true)
  expect(screen.queryByText(/County lines/)).toBeNull()

  fireEvent.click(screen.getByLabelText("Use workflow Hidden assets"))
  expect(screen.getByText(/no phones in this case: reported as not examined/)).toBeTruthy()
  expect(screen.getByText(/1 step will be listed as not examined/)).toBeTruthy()
  const start = screen.getByLabelText("Start workflow Hidden assets") as HTMLButtonElement
  expect(start.disabled).toBe(true)
  fireEvent.change(screen.getByLabelText("Hidden assets: Person"), { target: { value: "Sam Synthetic" } })
  expect(start.disabled).toBe(false)
  fireEvent.click(start)
  expect(onStart).toHaveBeenCalledWith("hidden-assets", "Which accounts does Sam Synthetic hold?")

  fireEvent.click(screen.getByText("Show 1 more workflows"))
  expect(screen.getByText(/County lines/)).toBeTruthy()
})
