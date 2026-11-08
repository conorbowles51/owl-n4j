import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { AgentCapabilitiesHelp } from "./AgentCapabilitiesHelp"
import { agentAPI } from "../api"
import type { AgentCapabilities } from "../types"

afterEach(() => vi.restoreAllMocks())

const help: AgentCapabilities = {
  schema: "loupe.agent.capabilities/1",
  total: 2,
  note: "Ask in your own words.",
  types: [
    { id: "phones", label: "Phones", description: "Messages and calls.", examples: ["Who does this phone contact most?"] },
    {
      id: "evidence_files",
      label: "Evidence files and their processing",
      description: "Which files are processed.",
      examples: ["Which files failed, and why?"],
    },
  ],
}

it("lists every kind of material from the registry and puts an example in the question box", async () => {
  const get = vi.spyOn(agentAPI, "getCapabilities").mockResolvedValue(help)
  const pick = vi.fn()
  render(<AgentCapabilitiesHelp onPick={pick} />)
  expect(get).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "What can I ask?" }))
  expect(await screen.findByText("Evidence files and their processing")).toBeInTheDocument()
  expect(screen.getByText("Phones")).toBeInTheDocument()
  expect(screen.getByText(/these 2 kinds of case material/)).toBeInTheDocument()
  expect(screen.queryByText(/_/)).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Which files failed, and why?" }))
  expect(pick).toHaveBeenCalledWith("Which files failed, and why?")
  expect(get).toHaveBeenCalledTimes(1)
})

it("says when the list could not be loaded", async () => {
  vi.spyOn(agentAPI, "getCapabilities").mockRejectedValue(new Error("down"))
  render(<AgentCapabilitiesHelp onPick={() => {}} />)
  fireEvent.click(screen.getByRole("button", { name: "What can I ask?" }))
  await waitFor(() => expect(screen.getByText(/could not be loaded just now/)).toBeInTheDocument())
})
