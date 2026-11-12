import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"

import { agentAPI } from "../api"
import type { AgentLiveRun, AgentRunSteering, AgentToolGroup } from "../types"
import { ToolSteeringCard } from "./ToolSteeringCard"

afterEach(() => vi.restoreAllMocks())

const groups: AgentToolGroup[] = [
  { id: "money", name: "Money and ledger", about: "Statements, ledger rows", tools: ["get_financial_transactions"], switchable: true },
  { id: "phones", name: "Phones", about: "Messages and alerts", tools: ["phone_messages"], switchable: true },
  { id: "places", name: "Map and places", about: "Where phones were", tools: ["phone_places"], switchable: true },
  { id: "always", name: "Always on", about: "Its working notes", tools: ["read_tool_result_page"], switchable: false },
]
const steering = (patch: Partial<AgentRunSteering> = {}): AgentRunSteering => ({
  chosen: ["money", "phones"], applied: [], pending: [], off: [], ...patch,
})

function mockRun(view: AgentRunSteering) {
  vi.spyOn(agentAPI, "toolGroups").mockResolvedValue({ groups })
  vi.spyOn(agentAPI, "getRun").mockResolvedValue({
    run_id: "run-1", thread_id: "t", status: "running", steering: view,
    tool_trace: [
      { id: "c1", name: "get_financial_transactions", arguments: {}, status: "success", duration_ms: 1, summary: "" },
      { id: "c2", name: "get_financial_transactions", arguments: {}, status: "success", duration_ms: 1, summary: "" },
    ],
  } as AgentLiveRun)
}

it("shows each group's state: in use with its calls, chosen, available, always on (tool steering A)", async () => {
  mockRun(steering())
  render(<ToolSteeringCard runId="run-1" />)
  await waitFor(() => expect(screen.getByTestId("tool-group-money").textContent).toContain("In use · 2 calls"))
  expect(screen.getByTestId("tool-group-phones").textContent).toContain("Chosen, not used yet")
  expect(screen.getByTestId("tool-group-places").textContent).toContain("Available, not chosen")
  expect(screen.getByTestId("tool-group-always").textContent).toContain("Always on")
  expect(screen.queryByRole("checkbox", { name: /Always on/ })).toBeNull()
})

it("a switch is sent for the run and says it applies from the next step (tool steering B)", async () => {
  mockRun(steering())
  const steer = vi.spyOn(agentAPI, "steerRun").mockResolvedValue({
    entry: { id: "e1", kind: "switch", group: "phones", on: false, title: "You switched off Phones", result: "" },
    steering: steering({ off: ["phones"], pending: [{ id: "e1", kind: "switch", group: "phones", on: false,
      title: "You switched off Phones", result: "" }] }),
  })
  render(<ToolSteeringCard runId="run-1" />)
  const box = await screen.findByRole("checkbox", { name: "Switch off Phones" })
  await act(async () => {
    fireEvent.click(box)
  })
  expect(steer).toHaveBeenCalledWith("run-1", { kind: "switch", group: "phones", on: false })
  expect(screen.getByRole("status").textContent).toContain("Switched off: Phones. The agent picks this up at its next step")
  expect(screen.getByTestId("tool-group-phones").textContent).toContain("Off · applies from the next step")
  expect(screen.getByRole("checkbox", { name: "Switch on Phones" })).not.toBeChecked()
})

it("an applied switch names its step on the card", async () => {
  mockRun(steering({ off: ["phones"], applied: [{ id: "e1", kind: "switch", group: "phones", on: false,
    title: "You switched off Phones", result: "", step: 5, applies_from: 6 }] }))
  render(<ToolSteeringCard runId="run-1" />)
  await waitFor(() => expect(screen.getByTestId("tool-group-phones").textContent).toContain(
    "Off · switched off by you at step 5"))
})

it("Direct the agent sends the note in the person's words (tool steering E)", async () => {
  mockRun(steering())
  const steer = vi.spyOn(agentAPI, "steerRun").mockResolvedValue({
    entry: { id: "n1", kind: "note", note: "Check the May 2024 statement first", title: "You sent a note to the agent", result: "" },
    steering: steering(),
  })
  render(<ToolSteeringCard runId="run-1" />)
  const input = await screen.findByLabelText("Direct the agent")
  fireEvent.change(input, { target: { value: "Check the May 2024 statement first" } })
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send to the agent" }))
  })
  expect(steer).toHaveBeenCalledWith("run-1", { kind: "note", note: "Check the May 2024 statement first" })
  expect(screen.getByRole("status").textContent).toContain("Note sent. The agent reads it before its next step.")
})

it("a run that finished says the switch was not saved", async () => {
  mockRun(steering())
  vi.spyOn(agentAPI, "steerRun").mockRejectedValue(new Error("This run has finished, so it cannot be changed."))
  render(<ToolSteeringCard runId="run-1" />)
  const box = await screen.findByRole("checkbox", { name: "Switch off Money and ledger" })
  await act(async () => {
    fireEvent.click(box)
  })
  expect(screen.getByRole("alert").textContent).toContain("This run has finished")
})
