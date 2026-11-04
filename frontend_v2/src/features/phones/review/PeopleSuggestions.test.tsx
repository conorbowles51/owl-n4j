import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { PeopleSuggestions } from "./PeopleSuggestions"

const mocks = vi.hoisted(() => ({ suggestions: vi.fn(), get: vi.fn(), decide: vi.fn() }))
vi.mock("./identities.api", () => ({ identitiesAPI: { suggestions: mocks.suggestions, get: mocks.get, decide: mocks.decide } }))

const SUGG = {
  id: "s1", score: 0.8, dossier_id: null, expected_revision: "rev1",
  identities: [
    { id: "i1", identity_key: "phone:+12025550143", kind: "phone", value_display: "+1 202-555-0143" },
    { id: "i2", identity_key: "whatsapp:12025550143", kind: "account", value_display: "WhatsApp 12025550143" },
  ],
  reasons: [{ reason: "same_card", weight: 0.6, records: ["r1", "r2", "r3", "r4"], record_count: 4, phones: ["C1"] }],
}
const detail = (key: string, name: string) => ({
  id: key, identity_key: key, kind: "phone", subkind: null, value_display: key, sightings: 3, phones: 1,
  names: [{ phone: "C1", name, basis: "contact", occurrences: 3, is_phone_name: true }],
  linked_dossier: null, can_be_a_person: true, expected_revision: "rev1",
})

describe("People suggestions (07 J-7)", () => {
  it("shows one suggestion with names, reasons and 3 examples, counts decisions, and links with the standard reason", async () => {
    mocks.suggestions.mockResolvedValue({ case_id: "c", total: 1, decided: 2, suggestions: [SUGG] })
    mocks.get.mockImplementation((_c: string, key: string) => Promise.resolve(detail(key, "Ana Synthetic")))
    mocks.decide.mockResolvedValue({ decisions: ["d1"], dossier_id: "p1", revision: "rev2" })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><PeopleSuggestions caseId="c" /></MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText("2 of 3 decided")).toBeInTheDocument()
    const reasons = screen.getByRole("region", { name: "Reasons" })
    expect(reasons).toHaveTextContent("listed together on one contact card (on C1): 4 records")
    expect(screen.getAllByRole("link", { name: /Example/ })).toHaveLength(3)
    await waitFor(() => expect(screen.getByLabelText("Name for the new person")).toHaveValue("Ana Synthetic"))
    fireEvent.click(screen.getByRole("button", { name: "Link (y)" }))
    await waitFor(() => expect(mocks.decide).toHaveBeenCalled())
    expect(mocks.decide.mock.calls[0][1]).toMatchObject({
      decision: "link_phone_identity", identity_keys: ["phone:+12025550143", "whatsapp:12025550143"],
      new_person_name: "Ana Synthetic", reasons_shown: [{ reason: "same_card" }], expected_revision: "rev1",
    })
    expect(await screen.findByText("Linked as one person, Ana Synthetic.")).toBeInTheDocument()
  })

  it("lists a faint name-only suggestion with its strength and both parts of its reasons, and filters by strength", async () => {
    const faint = {
      ...SUGG, id: "s2", score: 0.1, level: "faint",
      reasons: [{ reason: "name_only", weight: 0.1, records: [], record_count: 0, phones: [], names: ["ana synthetic"] }],
      strength_reasons: { match: ["the same name only: nothing else links them", "score 0.10"], substantiation: ["no source beyond a saved name"] },
    }
    const moderate = { ...SUGG, score: 0.6, level: "moderate", strength_reasons: { match: ["listed together on one contact card", "score 0.60"], substantiation: ["seen on 1 phone", "4 records"] } }
    mocks.suggestions.mockResolvedValue({
      case_id: "c", total: 2, decided: 0, suggestions: [moderate, faint],
      by_level: { strong: 0, moderate: 1, weak: 0, faint: 1 }, scale: "Strength is set by a stated rule, never by a model.",
    })
    mocks.get.mockImplementation((_c: string, key: string) => Promise.resolve(detail(key, "Ana Synthetic")))
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><PeopleSuggestions caseId="c" /></MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText("Suggestion 1 of 2, strongest first.")).toBeInTheDocument()
    expect(screen.getByLabelText("Strength", { selector: "div" })).toHaveTextContent("Moderate")
    fireEvent.change(screen.getByRole("combobox", { name: /Strength/ }), { target: { value: "faint" } })
    expect(await screen.findByText("Suggestion 1 of 1, strongest first.")).toBeInTheDocument()
    const strength = screen.getByLabelText("Strength", { selector: "div" })
    expect(strength).toHaveTextContent("Faint")
    expect(strength).toHaveTextContent("How well matched: the same name only: nothing else links them; score 0.10")
    expect(strength).toHaveTextContent("How substantiated: no source beyond a saved name")
    expect(screen.getByRole("region", { name: "Reasons" })).toHaveTextContent("the same name only (nothing else links them) (ana synthetic)")
  })
})
