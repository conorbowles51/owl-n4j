import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { AgentRunRecordPanel } from "./AgentRunRecordPanel"
import { agentAPI } from "../api"
import type { AgentRunRecord } from "../types"

const record: AgentRunRecord = {
  run_id: "11111111-2222-3333-4444-555555555555",
  status: "completed",
  for_user: { id: "u", name: "Synthetic Person", email: "person@example.test" },
  started_at: "2026-11-03T18:00:00+00:00",
  completed_at: "2026-11-03T18:01:00+00:00",
  provider: "deepseek",
  model_id: "deepseek-v4-pro",
  prompt_version: "a".repeat(64),
  prompt_version_label: "v1 · 2026-11-03 · aaaaaaaa",
  tool_budget: 28,
  tool_calls_used: 3,
  unrun_tool_calls: [{ name: "get_financial_transactions" }],
  case_layer: "all",
  summary: {
    items_returned: 12, items_opened: 2, items_cited: 3, items_in_artifact: 1, items_not_examined: 7,
    tool_not_returned: 40, model_not_shown: 0,
  },
  calls: [],
  not_deterministic: "Replays on a hosted model are not deterministic.",
}

it("opens the stored run record with its counts and offers both exports in CSV and PDF", async () => {
  const get = vi.spyOn(agentAPI, "getRunRecord").mockResolvedValue(record)
  render(<AgentRunRecordPanel runId={record.run_id} />)
  expect(get).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Run record" }))
  await waitFor(() => expect(screen.getByTestId("run-record-calls")).toHaveTextContent(
    "3 of 28; 1 more asked for but stopped by the budget"))
  expect(screen.getByTestId("run-record-items")).toHaveTextContent(
    "12: 2 read further, 3 cited, 1 used in an artifact, 7 not examined")
  expect(screen.getByTestId("run-record-clipped")).toHaveTextContent("40 matching items on pages not read")
  expect(screen.getByText("v1 · 2026-11-03 · aaaaaaaa")).toBeInTheDocument()
  expect(screen.getByText(/not deterministic/)).toBeInTheDocument()
  for (const label of ["Search strategy (CSV)", "Search strategy (PDF)", "What was not examined (CSV)",
    "What was not examined (PDF)"]) {
    expect(screen.getByRole("button", { name: label })).toBeInTheDocument()
  }
  expect(agentAPI.runRecordExportUrl(record.run_id, "not_examined", "pdf")).toBe(
    `/api/agent/runs/${record.run_id}/record/export?kind=not_examined&format=pdf`)
})
