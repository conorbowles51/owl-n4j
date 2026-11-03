import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({ prepareEntryExport: vi.fn(), describeExport: vi.fn(), createExport: vi.fn(), getExport: vi.fn() }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { EntryPhoneExport } from "./EntryPhoneExport"

/** 07 XF-7 / CO-12: a finding's phone records export as the frozen selection, its total the collected count. */
it("gathers the finding's phone records, states what is not in the export and exports them as a finding", async () => {
  const filter = { case_id: "case-1", selection: "sel-9", collapse_copies: false }
  api.prepareEntryExport.mockResolvedValue({ selection_id: "sel-9", filter, collected: 2, events: 2,
    words: "The phone records of finding “Cargo”", sentence: "Not in this export: 1 person on the phones." })
  api.describeExport.mockResolvedValue({ case_id: "case-1", total: 2, messages: 2, calls: 0, other: 0, unconfirmed: 0, phones: 1,
    collapsed_copies: 0, zone: "UTC", left_out: "", limits: [], snapshot: {}, machine_text: { total: 0, unconfirmed: 0, items: [], items_cap: 50 } })
  api.createExport.mockResolvedValue({ export_id: "x1" })
  api.getExport.mockResolvedValue({ export_id: "x1", state: "queued", progress: 0, counts: {}, format: "pdf", source: "finding" })
  render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <EntryPhoneExport caseId="case-1" entryId="entry-1" />
  </QueryClientProvider></MemoryRouter>)
  fireEvent.click(screen.getByRole("button", { name: "Export the phone records" }))
  await waitFor(() => expect(api.prepareEntryExport).toHaveBeenCalledWith("case-1", "entry-1"))
  expect(await screen.findByText(/All 2 messages, The phone records of finding/)).toBeInTheDocument()
  expect(screen.getByText("Not in this export: 1 person on the phones.")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Export PDF" }))
  await waitFor(() => expect(api.createExport).toHaveBeenCalled())
  const call = api.createExport.mock.calls[0]
  expect(call[0]).toBe("case-1")
  expect(call[1]).toEqual(filter)
  expect(call[4]).toBe("finding")
})

it("says so when the records cannot be gathered", async () => {
  api.prepareEntryExport.mockRejectedValue(new Error("This entry has no messages or calls from the phones to export."))
  render(<MemoryRouter><QueryClientProvider client={new QueryClient()}>
    <EntryPhoneExport caseId="case-1" entryId="entry-2" />
  </QueryClientProvider></MemoryRouter>)
  fireEvent.click(screen.getByRole("button", { name: "Export the phone records" }))
  expect(await screen.findByRole("alert")).toBeInTheDocument()
})
