import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { proofStanding } from "@/test/proof-standing-fixture"
import { ProofStandingPanel } from "./ProofStandingPanel"

afterEach(() => vi.restoreAllMocks())
it("reads the case census, expands its rules and explicitly refreshes it in Chromium", async () => {
  const originalFetch = globalThis.fetch
  let reads = 0
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
    if (!String(url).startsWith("/api/financial/proof-standing"))
      return originalFetch(url, options)
    expect(String(url)).toBe("/api/financial/proof-standing?case_id=case-1")
    reads++
    return new Response(JSON.stringify(proofStanding()), { status: 200 })
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ProofStandingPanel caseId="case-1" />
    </QueryClientProvider>
  )
  expect(await screen.findByTestId("proof-standing-totals")).toHaveTextContent(
    "5 financial source documents"
  )
  fireEvent.click(screen.getByText("View all classes and their rules"))
  expect(screen.getByRole("table")).toBeVisible()
  expect(screen.getAllByRole("row")).toHaveLength(6)
  expect(
    within(screen.getAllByRole("row")[4])
      .getAllByRole("cell")
      .map((cell) => cell.textContent)
  ).toEqual(["2", "4", "No", "Yes", "Yes", "No"])
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh classification" })
  )
  await waitFor(() => expect(reads).toBe(2))
})
