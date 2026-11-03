import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { AllCasesSwitch } from "./AllCasesSwitch"
import { AgentRunRecordPanel } from "./AgentRunRecordPanel"
import { agentAPI } from "../api"
import type { AgentRunRecord } from "../types"

afterEach(() => vi.restoreAllMocks())

it("says this case only when off, and asks to turn on all cases", () => {
  const change = vi.fn()
  render(<AllCasesSwitch checked={false} onCheckedChange={change} />)
  expect(screen.getByText("This case only")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("switch", { name: "All my cases" }))
  expect(change).toHaveBeenCalledWith(true)
})

it("says it is reading all cases when on, and cannot be used on the Significant layer", () => {
  const { rerender } = render(<AllCasesSwitch checked onCheckedChange={() => {}} />)
  expect(screen.getByText("Reading all my cases")).toBeInTheDocument()
  rerender(<AllCasesSwitch checked={false} disabled onCheckedChange={() => {}} />)
  expect(screen.getByRole("switch", { name: "All my cases" })).toBeDisabled()
})

it("sends all_cases only when the person switched it on", async () => {
  const bodies: string[] = []
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
    bodies.push(String((init as RequestInit).body))
    return new Response("", { status: 200 })
  })
  for (const allCases of [false, true]) {
    await agentAPI.streamMessage({ caseId: "c", message: "q", allCases }, () => {}).catch(() => {})
  }
  expect(JSON.parse(bodies[0]).all_cases).toBeUndefined()
  expect(JSON.parse(bodies[1]).all_cases).toBe(true)
})

it("the run record lists the cases read", async () => {
  const record = {
    run_id: "r", status: "completed", for_user: { id: null, name: null, email: null }, started_at: null,
    completed_at: null, provider: "p", model_id: "m", prompt_version: null, prompt_version_label: null,
    tool_budget: 28, tool_calls_used: 2, unrun_tool_calls: [], case_layer: "all", all_cases: true,
    cases_read: [{ case_id: "a", case_name: "Matter A", this_case: true },
      { case_id: "b", case_name: "Matter B", this_case: false }],
    summary: {}, calls: [], not_deterministic: "",
  } as AgentRunRecord
  vi.spyOn(agentAPI, "getRunRecord").mockResolvedValue(record)
  render(<AgentRunRecordPanel runId="r" />)
  fireEvent.click(screen.getByRole("button", { name: "Run record" }))
  expect(await screen.findByTestId("run-record-cases")).toHaveTextContent(
    "All my cases mode: Matter A (this case); Matter B")
})
