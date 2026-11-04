import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({ prepareSourceExport: vi.fn(), describeExport: vi.fn(), createExport: vi.fn(), getExport: vi.fn() }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { CollectedPhoneExport } from "./CollectedPhoneExport"

const facts = (total: number) => ({ case_id: "case-1", total, messages: total, calls: 0, other: 0, unconfirmed: 0, phones: 1,
  collapsed_copies: 0, zone: "UTC", left_out: "Saved passwords and card numbers left out.", limits: [], snapshot: {},
  machine_text: { total: 0, unconfirmed: 0, items: [], items_cap: 50 } })
const mount = (ui: React.ReactNode) => render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
  {ui}
</QueryClientProvider></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  api.createExport.mockResolvedValue({ export_id: "x1" })
  api.getExport.mockResolvedValue({ export_id: "x1", state: "queued", progress: 0, counts: {}, format: "pdf", source: "collection" })
})

/** 03 12.2, E-9: a collection exports as collected, its total the collected count, with the scope in words. */
it("exports a collection as the collection, with its scope and reading state in words", async () => {
  const filter = { case_id: "case-1", selection: "sel-1", collapse_copies: false }
  api.prepareSourceExport.mockResolvedValue({ selection_id: "sel-1", filter, collected: 3, members: 3, events: 3,
    words: "The collection “Cargo messages”", sentence: null })
  api.describeExport.mockResolvedValue(facts(3))
  mount(<CollectedPhoneExport caseId="case-1" source="collection" id="sel-1" />)
  fireEvent.click(screen.getByRole("button", { name: "Export this collection" }))
  await waitFor(() => expect(api.prepareSourceExport).toHaveBeenCalledWith("case-1", "collection", { selection_id: "sel-1" }))
  expect(await screen.findByText(/All 3 messages, The collection “Cargo messages”, on 1 phone, times in UTC/)).toBeInTheDocument()
  expect(screen.getByText("Every row rests on readings confirmed by a person.")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Export PDF" }))
  await waitFor(() => expect(api.createExport).toHaveBeenCalled())
  const call = api.createExport.mock.calls[0]
  expect(call[1]).toEqual(filter)
  expect(call[4]).toBe("collection")
})

it("exports a dossier's phone records and says what of the dossier is not in the export", async () => {
  const filter = { case_id: "case-1", selection: "sel-2", collapse_copies: false }
  const sentence = "Not in this export: 1 phone. The dossier's 2 media files are not in a phone export, which holds messages and calls only."
  api.prepareSourceExport.mockResolvedValue({ selection_id: "sel-2", filter, collected: 2, members: 2, events: 2,
    words: "The phone records of the dossier “Synthetic Person”", sentence })
  api.describeExport.mockResolvedValue(facts(2))
  mount(<CollectedPhoneExport caseId="case-1" source="dossier" id="dos-1" />)
  fireEvent.click(screen.getByRole("button", { name: "Export the phone records" }))
  await waitFor(() => expect(api.prepareSourceExport).toHaveBeenCalledWith("case-1", "dossier", { dossier_id: "dos-1" }))
  expect(await screen.findByText(sentence)).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Export PDF" }))
  await waitFor(() => expect(api.createExport).toHaveBeenCalled())
  expect(api.createExport.mock.calls[0][4]).toBe("dossier")
})

it("states the refusal when there is nothing to export", async () => {
  api.prepareSourceExport.mockRejectedValue(new Error("Not in this export: 1 phone."))
  mount(<CollectedPhoneExport caseId="case-1" source="dossier" id="dos-2" />)
  fireEvent.click(screen.getByRole("button", { name: "Export the phone records" }))
  expect(await screen.findByRole("alert")).toBeInTheDocument()
  expect(api.describeExport).not.toHaveBeenCalled()
})
