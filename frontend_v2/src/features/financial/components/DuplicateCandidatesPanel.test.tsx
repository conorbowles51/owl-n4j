import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { duplicateCandidates } from "@/test/duplicate-fixture"
import { DuplicateCandidatesPanel } from "./DuplicateCandidatesPanel"
import { FinancialAccessContext } from "../hooks/use-financial-access"

afterEach(() => vi.restoreAllMocks())
function mount(canEdit = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <FinancialAccessContext.Provider
          value={{ canEdit, canUpload: false, ready: true, error: false }}
        >
          <DuplicateCandidatesPanel caseId="case-1" />
        </FinancialAccessContext.Provider>
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
  expect(screen.getByText("Excluded from Transactions")).toBeInTheDocument()
  expect(screen.getByText("2 excluded or corrected rows")).toBeInTheDocument()
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

it("shows hash-only matches separately without offering exclusions for those matches", async () => {
  const fixture = duplicateCandidates()
  const members = fixture.groups[0].members.map((row) => ({
    ...row,
    source_transaction_id: null,
  }))
  const data = {
    ...fixture,
    groups: [],
    source_hash_groups: [
      {
        sha256_at_ingestion: "a".repeat(64),
        members,
        limitation: "Recorded hashes only; coverage differs.",
      },
    ],
  }
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () => new Response(JSON.stringify(data))
  )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Compare documents" }))
  expect(
    await screen.findByRole("region", {
      name: "Matching source hashes across coverage",
    })
  ).toBeInTheDocument()
  expect(
    screen.getByText("Recorded hashes only; coverage differs.")
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: /Exclude this copy/ })
  ).not.toBeInTheDocument()
})

it("opens the original for each matching copy without making a duplicate decision", async () => {
  const data = duplicateCandidates()
  data.groups[0].members[0].source_transaction_id = "first-payment"
  data.groups[0].members[1].source_transaction_id = "excluded-payment"
  data.excluded_documents = [data.groups[0].members[1]]
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (url) =>
      String(url).includes("/duplicates?")
        ? new Response(JSON.stringify(data))
        : new Response("Source temporarily unavailable", { status: 503 })
    )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Compare documents" }))
  fireEvent.click(await screen.findByText(/Candidate group 1/))
  expect(
    screen.queryByRole("button", { name: /Exclude this copy|Restore copy/ })
  ).not.toBeInTheDocument()
  expect(
    screen.getByText(/requires permission to edit this case/)
  ).toBeInTheDocument()
  for (const [filename, payment] of [
    ["original.ofx", "first-payment"],
    ["copy.ofx", "excluded-payment"],
  ]) {
    fireEvent.click(
      screen.getByRole("button", { name: `View source for ${filename}` })
    )
    await screen.findByText(/Transaction details could not be loaded/)
    expect(
      fetch.mock.calls.some(
        ([url]) =>
          String(url) ===
          `/api/financial/ledger/${payment}/source?case_id=case-1`
      )
    ).toBe(true)
    fireEvent.click(screen.getByRole("button", { name: "Close" }))
  }
  expect(
    fetch.mock.calls.every(
      ([, options]) => !options?.method || options.method === "GET"
    )
  ).toBe(true)
})

it("offers duplicate exclusion and restoration to members who can edit the case", async () => {
  const data = duplicateCandidates()
  const priorCopy = {
    ...data.groups[0].members[1],
    document_id: "older-copy",
    filename: "older.pdf",
  }
  data.groups[0].members[1] = {
    ...data.groups[0].members[1],
    status: "admitted",
    superseded_by_id: null,
  }
  data.excluded_documents = [priorCopy]
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () => new Response(JSON.stringify(data))
  )
  mount(true)
  fireEvent.click(screen.getByRole("button", { name: "Compare documents" }))
  fireEvent.click(await screen.findByText(/Candidate group 1/))
  expect(
    screen.getByRole("button", {
      name: "Exclude this copy; retain original.ofx",
    })
  ).toBeInTheDocument()
  fireEvent.click(screen.getByText("Excluded documents (1)"))
  expect(
    screen.getByRole("button", { name: "Restore older.pdf" })
  ).toBeInTheDocument()
})
