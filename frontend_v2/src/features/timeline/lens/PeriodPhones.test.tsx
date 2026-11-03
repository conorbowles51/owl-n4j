import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({ getPeriodCrossing: vi.fn() }))
const lens = vi.hoisted(() => ({ lensIndex: vi.fn(), lensBuckets: vi.fn() }))
const listed = vi.hoisted(() => ({ filters: [] as unknown[] }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))
vi.mock("./lens-api", async (orig) => ({ ...(await orig<object>()), ...lens }))
vi.mock("./PhoneLens", () => ({ LensList: (p: { filter: unknown }) => { listed.filters.push(p.filter); return <p data-testid="lens-list" /> } }))

import { PeriodPhones } from "./PeriodPhones"

/** 07 XF-4: a lane mark lists exactly its own day on its own phone, so the list holds the number the mark shows. */
it("a mark opens its own bucket on its own phone, and undated records are stated beside the count", async () => {
  const lf = { case_id: "case-1", zone: { mode: "case", phone: null }, from_instant: "2023-03-01T00:00:00+00:00", to_instant: "2023-03-30T23:59:59.999000+00:00", include_no_time: false, lens_kinds: ["messages", "calls", "emails"], lane_by: "phone" }
  api.getPeriodCrossing.mockResolvedValue({ from: "2023-03-01", to: "2023-03-30", zone: "UTC", total: 1480, lens_filter: lf, sentence: "1,480 messages, calls and emails on 1 phone from 2023-03-01 to 2023-03-30 (days in UTC).",
    phones: [{ extraction_id: "ext-1", label: "C1", count: 1480, conversations_href: "/cases/case-1/conversations?phones=ext-1&from=2023-03-01&to=2023-03-30&notime=0", no_time: 3 }] })
  lens.lensIndex.mockResolvedValue({ snapshot: "snap" })
  lens.lensBuckets.mockResolvedValue({ zone: "UTC", no_data_words: "No data", empty_words: "", lanes: [{ key: "ext-1", label: "C1", buckets: [
    { start: "2023-03-05T00:00:00.000Z", count: 12, no_data: false }, { start: "2023-03-06T00:00:00.000Z", count: 0, no_data: true }] }] })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>
    <PeriodPhones caseId="case-1" caseName="Case" from="2023-03-01" to="2023-03-30" />
  </MemoryRouter></QueryClientProvider>)
  fireEvent.click(screen.getByRole("button", { name: "What the phones did" }))
  expect(await screen.findByText("C1: 1,480 in Conversations")).toBeInTheDocument()
  expect(screen.getByText(/and 3 with no time/)).toBeInTheDocument()
  const mark = await screen.findByRole("button", { name: /12 entries/ })
  expect(mark.closest("a")).toBeNull()
  fireEvent.click(mark)
  await waitFor(() => expect(listed.filters.length).toBeGreaterThan(0))
  expect(listed.filters.at(-1)).toMatchObject({ phones: ["ext-1"], from_instant: "2023-03-05T00:00:00.000Z", to_instant: "2023-03-05T23:59:59.999Z", include_no_time: false })
})
