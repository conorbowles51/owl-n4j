import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { HowThisWasFound } from "./HowThisWasFound"

const mocks = vi.hoisted(() => ({ explain: vi.fn() }))
vi.mock("@/features/phones/api", () => ({ getFindingExplanation: mocks.explain }))

const show = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <HowThisWasFound caseId="case-1" entryId="entry-1" />
    </QueryClientProvider>,
  )

describe("How this was found (07 J-17)", () => {
  it("shows the generated block with its label, reasons, scope, readings and assumptions", async () => {
    mocks.explain.mockResolvedValue({
      entry_id: "entry-1", heading: "How this was found", has_phone_links: true,
      links: { total: 4, by_type: { phone_selection: 1, phone_record: 2, phone_identity: 1 } },
      scope: [{ kind: "selection", words: "Two synthetic messages", records: 2, events: 2 }],
      searches: [{ query: "synthetic", exact: false }],
      readings: { records: 3, confirmed: 2, unconfirmed: 1, as_recorded: 0, not_in_current_reading: 0 },
      identities: [{ identity: "+1 202-555-0143", decisions: 0, linked_to_person: false, missing: false }],
      assumptions: [{ phone: "C1", code: "owner_computed", words: "The owner of C1 is the system's reading of the report, not confirmed by a person." }],
      label: "Lead for enquiry",
      label_reasons: ["1 reading is mapped by the system and not yet confirmed by a person."],
    })
    show()
    expect(await screen.findByRole("heading", { name: "How this was found" })).toBeInTheDocument()
    expect(screen.getByText("Lead for enquiry")).toBeInTheDocument()
    expect(screen.getByText("from 4 phone links")).toBeInTheDocument()
    expect(screen.getByText("1 reading is mapped by the system and not yet confirmed by a person.")).toBeInTheDocument()
    expect(screen.getByText(/Two synthetic messages \(2 records\)/)).toBeInTheDocument()
    expect(screen.getByText(/3 records: 2 confirmed by a person, 1 mapped by the system/)).toBeInTheDocument()
    expect(screen.getByText(/owner_computed/)).toBeInTheDocument()
  })

  it("shows nothing for a finding with no phone links", async () => {
    mocks.explain.mockResolvedValue({ entry_id: "entry-1", heading: "How this was found", has_phone_links: false, links: { total: 0, by_type: {} } })
    const { container } = show()
    await vi.waitFor(() => expect(mocks.explain).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
