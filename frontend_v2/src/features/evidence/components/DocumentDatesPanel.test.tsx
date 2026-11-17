import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { DocumentDatesPanel, type DocumentDate } from "./DocumentDatesPanel"

const fetchAPI = vi.fn()
vi.mock("@/lib/api-client", () => ({ fetchAPI: (...args: unknown[]) => fetchAPI(...args) }))

const reading: DocumentDate = {
  id: "r1", kind: "written", date_from: "2026-08-05", date_to: "2026-08-05", source: "rule",
  words: "Invoice date: 5 August 2026", page: 2, confirmed: false, confirmed_by: null,
  label: "Read by Loupe · not confirmed", original: null,
}

function show(dates: DocumentDate[], canEdit = true) {
  fetchAPI.mockImplementation((url: string) => Promise.resolve(String(url ?? "").endsWith("/dates") ? { dates } : {}))
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DocumentDatesPanel caseId="c" fileId="f" canEdit={canEdit} />
    </QueryClientProvider>
  )
}

beforeEach(() => fetchAPI.mockReset())

it("shows a date Loupe read with its words and page, marked not confirmed", async () => {
  show([reading])
  expect(await screen.findByText(/Read by Loupe · not confirmed/)).toBeTruthy()
  expect(screen.getByText(/Invoice date: 5 August 2026/)).toBeTruthy()
  expect(screen.getByText(/page 2/)).toBeTruthy()
})

it("confirms a reading", async () => {
  show([reading])
  fireEvent.click(await screen.findByText("Confirm"))
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledWith("/api/evidence/f/dates/r1/confirm", { method: "POST" }))
})

it("corrects the original reading and keeps it visible beside the corrected date", async () => {
  const corrected: DocumentDate = { ...reading, id: "p1", source: "person", date_from: "2026-08-07", date_to: "2026-08-07",
    confirmed: true, confirmed_by: "Neil Byrne", label: null, original: reading }
  show([corrected])
  expect(await screen.findByText(/Corrected by Neil Byrne/)).toBeTruthy()
  expect(screen.getByText(/Read by Loupe: 2026-08-05/)).toBeTruthy()
  fireEvent.click(screen.getByText("Correct"))
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-08-08" } })
  fireEvent.click(screen.getByText("Save"))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith("/api/evidence/f/dates/r1/correct", {
      method: "POST", body: { date_from: "2026-08-08", date_to: "2026-08-07" },
    })
  )
})

it("offers no buttons to a viewer", async () => {
  show([reading], false)
  await screen.findByText(/Read by Loupe/)
  expect(screen.queryByText("Confirm")).toBeNull()
})
