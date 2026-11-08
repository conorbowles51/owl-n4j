import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { aiCaseLimitAPI, aiCostsAPI, type AIBudget } from "@/features/admin/api"
import { AIBudgetCard } from "./AIBudgetCard"

const none: AIBudget = {
  capped: false, case_limit_usd: null, month_limit_usd: null, month: "2026-11", month_spent_usd: 25.17,
  month_percent: null, cases: [], alerts: [],
  case_choices: [{ id: "c1", title: "Verification" }],
}

function show() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AIBudgetCard />
    </QueryClientProvider>
  )
}

describe("AIBudgetCard", () => {
  beforeEach(() => vi.restoreAllMocks())

  it("says there is no cap when nothing is set", async () => {
    vi.spyOn(aiCostsAPI, "getBudget").mockResolvedValue(none)
    show()
    expect(await screen.findByTestId("ai-budget-no-cap")).toHaveTextContent("no cap")
  })

  it("saves a limit, and clearing the box saves no limit", async () => {
    vi.spyOn(aiCostsAPI, "getBudget").mockResolvedValue(none)
    const save = vi.spyOn(aiCostsAPI, "saveBudget").mockResolvedValue({ ...none, capped: true, case_limit_usd: 300 })
    show()
    fireEvent.change(await screen.findByLabelText("Limit per case in dollars"), { target: { value: "300" } })
    fireEvent.click(screen.getByRole("button", { name: "Save limits" }))
    await waitFor(() => expect(save).toHaveBeenCalledWith({ case_limit_usd: 300, month_limit_usd: null }))
  })

  it("refuses a figure that is not a number", async () => {
    vi.spyOn(aiCostsAPI, "getBudget").mockResolvedValue(none)
    show()
    fireEvent.change(await screen.findByLabelText("Limit per month in dollars"), { target: { value: "lots" } })
    expect(screen.getByRole("button", { name: "Save limits" })).toBeDisabled()
  })

  it("shows the alerts", async () => {
    vi.spyOn(aiCostsAPI, "getBudget").mockResolvedValue({
      ...none, capped: true, case_limit_usd: 10,
      alerts: [{ key: "k", level: 100, at: "2026-11-06T00:00:00", message: "Case Verification has reached its limit." }],
    })
    show()
    expect(await screen.findByText(/Case Verification has reached its limit/)).toBeInTheDocument()
  })

  it("sets and clears one case's own limit", async () => {
    const own = { ...none, capped: true, case_limit_usd: 10, case_limits: { c1: 50 } }
    vi.spyOn(aiCostsAPI, "getBudget").mockResolvedValue(own)
    const save = vi.spyOn(aiCaseLimitAPI, "save").mockResolvedValue(own)
    show()
    fireEvent.change(await screen.findByLabelText("Case for its own limit"), { target: { value: "c1" } })
    fireEvent.change(screen.getByLabelText("Own limit for the chosen case in dollars"), { target: { value: "75" } })
    fireEvent.click(screen.getByRole("button", { name: "Set case limit" }))
    await waitFor(() => expect(save).toHaveBeenCalledWith("c1", 75))
    fireEvent.click(screen.getByRole("button", { name: "Clear case limit" }))
    await waitFor(() => expect(save).toHaveBeenCalledWith("c1", null))
  })
})
