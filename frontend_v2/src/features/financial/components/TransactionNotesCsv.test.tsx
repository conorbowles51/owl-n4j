import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { TransactionNotesCsv } from "./TransactionNotesCsv"
import { caseworkAPI } from "@/features/workspace/casework-api"
import { captureFindingPayments } from "../lib/investigator-finding"
import { paymentFixture } from "../lib/payment-fixture.test-support"
vi.mock("@/features/workspace/casework-api", () => ({
  caseworkAPI: { list: vi.fn(), create: vi.fn() },
}))
vi.mock("../lib/investigator-finding", async (original) => ({
  ...(await original<typeof import("../lib/investigator-finding")>()),
  captureFindingPayments: vi.fn(),
}))
it("previews references, skips ambiguous rows, keeps originals, and recognizes notes already imported", async () => {
  const rows = [
    { ...paymentFixture, key: "one", ref_id: "TX-1", description: "Rent" },
    { ...paymentFixture, key: "two", ref_id: "TX-2" },
    { ...paymentFixture, key: "three", ref_id: "TX-2" },
  ]
  const original = JSON.stringify(rows),
    stored = new Map<string, unknown>()
  vi.mocked(captureFindingPayments).mockResolvedValue([])
  vi.mocked(caseworkAPI.list).mockImplementation(
    async (_caseId, params) =>
      ({
        entries: stored.has(params?.tag || "")
          ? [stored.get(params!.tag!)]
          : [],
        total: stored.has(params?.tag || "") ? 1 : 0,
      }) as never
  )
  vi.mocked(caseworkAPI.create).mockImplementation(async (caseId, input) => {
    const saved = {
      ...input,
      case_id: caseId,
      id: "note",
      tags: input.tags?.map((t) => t.slice(0, 64)),
    }
    stored.set(saved.tags!.find((t) => t.startsWith("financial-csv-"))!, saved)
    return saved as never
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TransactionNotesCsv caseId="case" rows={rows} onClose={() => {}} />
    </QueryClientProvider>
  )
  const file = {
    size: 90,
    text: async () =>
      'ref_id,notes\nTX-1,"Check rent, please"\nTX-2,Ambiguous\nTX-3,Not found',
  }
  fireEvent.change(screen.getByLabelText("Notes CSV file"), {
    target: { files: [file] },
  })
  await screen.findByText(/1 notes match exactly one transaction/)
  fireEvent.click(
    screen.getByRole("button", { name: "Import 1 matching notes" })
  )
  await screen.findByText(/1 notes saved; 0 already present/)
  expect(caseworkAPI.create).toHaveBeenCalledTimes(1)
  expect(captureFindingPayments).toHaveBeenCalledWith("case", ["one"])
  fireEvent.click(
    screen.getByRole("button", { name: "Import 1 matching notes" })
  )
  await screen.findByText(/0 notes saved; 1 already present/)
  await waitFor(() => expect(caseworkAPI.create).toHaveBeenCalledTimes(1))
  expect(JSON.stringify(rows)).toBe(original)
})
