import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { duplicateCandidates } from "@/test/duplicate-fixture"
import { DuplicateCandidatesPanel } from "./DuplicateCandidatesPanel"

afterEach(() => vi.restoreAllMocks())
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <DuplicateCandidatesPanel caseId="case-1" />
      </QueryClientProvider>
    ),
  }
}
it("compares on request, shows actual disposition and refreshes on ledger invalidation", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(duplicateCandidates())))
  // Each fetch needs a fresh Response body.
  fetch.mockImplementation(
    async () => new Response(JSON.stringify(duplicateCandidates()))
  )
  const { client } = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Compare documents" }))
  expect(
    await screen.findByText(
      "2 of 3 financial documents compared. 1 not compared."
    )
  ).toBeInTheDocument()
  fireEvent.click(screen.getByText(/Candidate group 1/))
  expect(screen.getByText("Document status: superseded")).toBeInTheDocument()
  expect(screen.getByText("2 superseded rows")).toBeInTheDocument()
  expect(
    screen.getByText(/does not exclude documents or change totals/)
  ).toBeInTheDocument()
  await client.invalidateQueries({ queryKey: ["financial-ledger", "case-1"] })
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(String(fetch.mock.calls[0][0])).toBe(
    "/api/financial/duplicates?case_id=case-1"
  )
})
it("hides an earlier successful comparison after a refresh fails", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(
      async () => new Response(JSON.stringify(duplicateCandidates()))
    )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Compare documents" }))
  await screen.findByText(/Candidate group 1/)
  fetch.mockImplementation(
    async () => new Response("Unavailable", { status: 500 })
  )
  fireEvent.click(screen.getByRole("button", { name: "Refresh comparison" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "No results are shown"
  )
  expect(screen.queryByText(/Candidate group 1/)).toBeNull()
})
