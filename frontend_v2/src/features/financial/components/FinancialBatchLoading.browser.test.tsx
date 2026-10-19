import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: false }),
}))
const batch = {
  id: "batch",
  case_id: "case",
  status: "review",
  files: [],
  counts: { ready: 0, attention: 0, imported: 0 },
  total: 0,
  items: [],
  ready_transactions: 0,
  ready_revision: "a".repeat(64),
  operations: [],
}
let client: QueryClient
function Location() {
  const location = useLocation()
  return <output aria-label="Current destination">{location.search}</output>
}
function mount() {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/cases/case/financial?view=statements&batch=batch"]}
      >
        <main className="p-4">
          <FinancialBatchPanel caseId="case" />
          <Location />
        </main>
      </MemoryRouter>
    </QueryClientProvider>
  )
}
afterEach(() => {
  cleanup()
  client?.clear()
})
it.each([1280, 390])(
  "keeps stalled batch reads recoverable without restarting work at %ipx",
  async (width) => {
    useFinancialDraftStore.setState({ drafts: {} })
    await page.viewport(width, 900)
    let rejectRead: (error: Error) => void = () => {},
      attempts = 0,
      signal: AbortSignal | null | undefined
    vi.mocked(fetchAPI).mockReset()
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (url.includes("/batches/batch?")) {
        attempts++
        signal = options?.signal
        expect(options?.timeout).toBe(60000)
        if (attempts !== 2)
          return new Promise((_, reject) => {
            rejectRead = reject
          })
        return batch
      }
      return { case_id: "case", batches: [] }
    })
    mount()
    await screen.findByRole("region", {
      name: "Opening financial processing batch",
    })
    expect(
      screen.getByRole("button", { name: "Back to statement files" })
    ).toBeVisible()
    await act(async () =>
      rejectRead(new DOMException("Synthetic timeout", "AbortError"))
    )
    await screen.findByRole("alert")
    expect(screen.getByRole("alert")).toHaveTextContent(
      "did not respond within one minute"
    )
    expect(attempts).toBe(1)
    await page.getByRole("button", { name: "Retry batch", exact: true }).click()
    await screen.findByRole("region", { name: "Financial processing batch" })
    expect(attempts).toBe(2)
    cleanup()
    client.clear()
    mount()
    await screen.findByRole("region", {
      name: "Opening financial processing batch",
    })
    await page.screenshot({
      path: `/private/tmp/loupe-batch-loading-${width}.png`,
    })
    await page
      .getByRole("button", { name: "Back to statement files", exact: true })
      .click()
    await waitFor(() =>
      expect(screen.getByLabelText("Current destination")).toHaveTextContent(
        "files=1"
      )
    )
    expect(signal?.aborted).toBe(true)
    expect(
      vi.mocked(fetchAPI).mock.calls.every(([, options]) => !options?.method)
    ).toBe(true)
  }
)
