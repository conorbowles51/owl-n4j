import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Addition, Narrative, TheoryReading } from "./api"

const mocks = vi.hoisted(() => ({
  add: vi.fn(),
  newTheory: vi.fn(),
  infer: vi.fn(),
  reading: vi.fn(),
  confirm: vi.fn(),
  loupe: vi.fn(),
}))
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./api", async (importOriginal) => {
  const real = await importOriginal<typeof import("./api")>()
  return {
    ...real,
    theoryAPI: { ...real.theoryAPI, add: mocks.add, newTheory: mocks.newTheory, infer: mocks.infer, reading: mocks.reading, confirm: mocks.confirm, loupe: mocks.loupe },
  }
})
vi.mock("@/features/phones/collect-targets", () => ({
  useCollectTargets: () => ({
    targets: [
      { kind: "note", id: "n1", label: "A note" },
      { kind: "theory", id: "t1", label: "Acme pays Ann" },
      { kind: "dossier", id: "d1", label: "Ann" },
    ],
    note: null,
    loading: false,
    error: null,
  }),
}))

import { AddToTheory } from "./AddToTheory"
import { TheoryReadingSection } from "./TheoryReading"

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<MemoryRouter><QueryClientProvider client={qc}>{node}</QueryClientProvider></MemoryRouter>)
}

const result = { entry_id: "t1", version: 3, added: 1, skipped: 0, added_link_ids: ["L1"], group: { id: "g1", member_count: 2, left_out: 1, left_out_examples: ["x"], label: "2 items" } }

const narrative = (over: Partial<Narrative> = {}): Narrative => ({
  id: "n-1", link_id: "L1", text: "Two payments left on 15 January [m1][m2].", origin: "agent", model: "gpt-x",
  words: "Model reading · gpt-x · not confirmed", written_by: null, asked_by: "Investigator",
  citations: [{ mark: "m1", ref: "financial_transaction:a", label: "row a" }, { mark: "m2", ref: "financial_transaction:b", label: "row b" }],
  basis: { read: 2, of: 2, invalid_citations: 0 }, replaces_id: null, confirmed_by: null, confirmed_at: null, created_at: "2026-11-08T19:00:00Z",
  ...over,
})

const addition = (over: Partial<Addition> = {}): Addition => ({
  link_id: "L1", target_type: "financial_selection", target_id: "g1", label: "2 items from the ledger, chosen: January payments",
  relationship: "unclassified", kind: "group", surface: "financial", why: "January payments", how: { filter: { month: "2026-01" } },
  member_count: 2, left_out: 0, origin: "person", model: null, model_reading: false, added_by: "Investigator", accepted_by: null,
  added_at: "2026-11-08T18:59:00Z", source_anchor: {}, narrative: narrative(), narrative_versions: 1, ...over,
})

describe("Add to theory", () => {
  beforeEach(() => Object.values(mocks).forEach((m) => m.mockReset()))

  it("adds a group with its members, how it was chosen and the person's why, offering theories first and no dossiers", async () => {
    mocks.add.mockResolvedValue(result)
    wrap(
      <AddToTheory
        caseId="c1"
        surface="financial"
        group={{ group_type: "financial_selection", members: [{ type: "financial_transaction", id: "a" }, { type: "financial_transaction", id: "b" }], how: { filter: { month: "2026-01" } }, words: "January payments" }}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: "Add to theory…" }))
    expect(screen.getByText(/2 items from the ledger, chosen: January payments/)).toBeTruthy()
    const options = screen.getAllByRole("option").map((o) => o.textContent)
    expect(options[0]).toContain("Acme pays Ann")
    expect(options.join(" ")).not.toContain("Ann" + "dossier")
    expect(options).toHaveLength(2)
    fireEvent.change(screen.getByLabelText("Why this, in your words"), { target: { value: "money out in January" } })
    fireEvent.click(screen.getAllByRole("option")[0])
    await waitFor(() => expect(mocks.add).toHaveBeenCalled())
    const [caseId, entryId, body] = mocks.add.mock.calls[0]
    expect([caseId, entryId]).toEqual(["c1", "t1"])
    expect(body.surface).toBe("financial")
    expect(body.group.members).toHaveLength(2)
    expect(body.group.how).toEqual({ filter: { month: "2026-01" } })
    expect(body.group.words).toBe("money out in January")
    expect(await screen.findByText(/1 of the chosen items are not in this case and were not kept/)).toBeTruthy()
    expect(mocks.infer).not.toHaveBeenCalled()
  })

  it("asks the model for a reading only when the person asks, and starts a new theory", async () => {
    mocks.newTheory.mockResolvedValue({ ...result, entry_id: "t9" })
    mocks.infer.mockResolvedValue(narrative())
    wrap(<AddToTheory caseId="c1" surface="graph" items={[{ target_type: "graph_entity", target_id: "person:ann", target_label: "Ann" }]} />)
    fireEvent.click(screen.getByRole("button", { name: "Add to theory…" }))
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.change(screen.getByPlaceholderText("Name the theory"), { target: { value: "Ann is the hub" } })
    fireEvent.click(screen.getByRole("button", { name: "Start theory" }))
    await waitFor(() => expect(mocks.infer).toHaveBeenCalledWith("c1", "t9", "L1"))
    expect(mocks.newTheory.mock.calls[0][1]).toMatchObject({ title: "Ann is the hub", surface: "graph", items: [{ target_id: "person:ann" }] })
    expect(await screen.findByText(/labelled as a model reading until you confirm it/)).toBeTruthy()
  })
})

describe("The theory read as a whole", () => {
  beforeEach(() => Object.values(mocks).forEach((m) => m.mockReset()))

  const reading = (additions: Addition[], fit: Narrative | null = null): TheoryReading => ({
    entry: { id: "t1", entry_type: "theory", title: "Acme pays Ann", body: "b", version: 2 }, additions, fit, fit_versions: fit ? 1 : 0,
  })

  it("shows a model reading under the model's name with its citations until confirmed", async () => {
    mocks.reading.mockResolvedValue(reading([addition()]))
    mocks.confirm.mockResolvedValue(narrative({ confirmed_by: "Investigator", words: "Model reading · gpt-x · confirmed by Investigator" }))
    wrap(<TheoryReadingSection caseId="c1" entryId="t1" />)
    expect(await screen.findByText(/Model reading · gpt-x · not confirmed/)).toBeTruthy()
    expect(screen.getByText("row a")).toBeTruthy()
    expect(screen.getByText("Why: January payments")).toBeTruthy()
    expect(screen.getByText("From the ledger")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Confirm the model's reading" }))
    await waitFor(() => expect(mocks.confirm).toHaveBeenCalledWith("c1", "t1", "n-1"))
  })

  it("labels an addition the model chose, and a person's narrative as theirs", async () => {
    mocks.reading.mockResolvedValue(reading([
      addition({ origin: "agent", model: "gpt-x", accepted_by: "Investigator", narrative: narrative({ origin: "person", model: null, words: "Written by Investigator", citations: [], text: "Mine." }) }),
    ]))
    wrap(<TheoryReadingSection caseId="c1" entryId="t1" />)
    expect(await screen.findByText(/Chosen by gpt-x \(a model's choice\), accepted by Investigator/)).toBeTruthy()
    expect(screen.getByText(/Written by Investigator/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Confirm the model's reading" })).toBeNull()
  })

  it("opens one addition through its Loupe with exactly its members, its why and every version", async () => {
    mocks.reading.mockResolvedValue(reading([addition()]))
    const mine = narrative({ id: "n-2", origin: "person", model: null, words: "Written by Investigator", text: "My reading.", citations: [], replaces_id: "n-1" })
    mocks.loupe.mockResolvedValue({
      entry: { id: "t1", title: "Acme pays Ann", entry_type: "theory" },
      addition: addition({ narrative: mine, narrative_versions: 2 }),
      members: [
        { ref: "financial_transaction:a", type: "financial_transaction", id: "a", label: "a", text: "2026-01-15 · 120.00 GBP out · row 1", state: "present", date: "2026-01-15", amount_minor: 12000, currency: "GBP", direction: "debit" },
        { ref: "financial_transaction:b", type: "financial_transaction", id: "b", label: "b", text: "2026-01-15 · 75.50 GBP out · row 2", state: "corrected", date: "2026-01-15", amount_minor: 7550, currency: "GBP", direction: "debit" },
      ],
      member_count: 2, members_shown: 2,
      group: { id: "g1", group_type: "financial_selection", surface: "financial", label: "2 items from the ledger, chosen: January payments", words: "January payments", how: { filter: { month: "2026-01" } }, member_count: 2, left_out: 0, created_at: null },
      history: [mine, narrative()],
    })
    wrap(<TheoryReadingSection caseId="c1" entryId="t1" />)
    fireEvent.click(await screen.findByRole("button", { name: "View through the Loupe" }))
    expect(await screen.findByText("Ledger rows (2)")).toBeTruthy()
    // the corrected row is shown, not counted
    expect(screen.getByText(/out 120.00 GBP · 1 corrected, rejected or missing row\(s\) not counted/)).toBeTruthy()
    expect(screen.getByText(/how: filter month 2026-01/)).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Earlier versions (1)" }))
    expect(screen.getByLabelText("Earlier versions").textContent).toContain("Model reading · gpt-x · not confirmed")
  })
})
