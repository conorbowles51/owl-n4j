import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Registry, RegistryItem } from "@/features/phones/people.api"

const api = vi.hoisted(() => ({ registry: vi.fn(), phones: vi.fn() }))
vi.mock("@/features/phones/people.api", async (orig) => ({
  ...(await orig<typeof import("@/features/phones/people.api")>()),
  peopleAPI: { registry: api.registry },
}))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<typeof import("@/features/phones/api")>()), getPhones: api.phones }))
vi.mock("@/features/phones/review/IdentityLinkGroup", () => ({
  IdentityLinkGroup: ({ identityKey, canEdit }: { identityKey: string; canEdit: boolean }) => <p>Decision panel for {identityKey} ({canEdit ? "may edit" : "view only"})</p>,
}))
vi.mock("@/features/phones/review/PeopleSuggestions", () => ({ PeopleSuggestions: () => <p>Suggestion panel</p> }))
import { PhoneIdentitiesTab } from "./PhoneIdentitiesTab"

/** 03 10.2, 10.5 U-1; 07 XF-5. Invented data only. */
const ANA: RegistryItem = {
  identity_key: "phone:+1", kind: "phone", subkind: "msisdn", value_display: "+1 202 555 0143",
  names: [{ phone_label: "C3", extraction_id: "e3", name: "Maria L", basis: "contact" }, { phone_label: "C7", extraction_id: "e7", name: "Mom", basis: "contact" }],
  person: { id: "d1", display_name: "Ana Synthetic" }, event_count: 12,
  phones: [{ extraction_id: "e3", phone_label: "C3", events: 9 }, { extraction_id: "e7", phone_label: "C7", events: 3 }],
  first_contact: "2023-03-13T09:00:00Z", last_contact: "2023-05-01T09:00:00Z", can_be_a_person: true,
}
const BEN: RegistryItem = { ...ANA, identity_key: "email:b", kind: "email", subkind: null, value_display: "ben@synthetic.test", names: [], person: null, event_count: 0, phones: [], first_contact: null, last_contact: null }
const LIST: Registry = { case_id: "c1", items: [ANA, BEN], total: 120, next_cursor: 50, in_case: 300, linked_in_case: 7 }

function Where() {
  return <p data-testid="where">{useLocation().search}</p>
}
function tab(canEdit = true, onOpen = vi.fn(), phones = [{ extraction_id: "e3", label: "C3" }, { extraction_id: "e7", label: "C7" }]) {
  api.phones.mockResolvedValue({ phones })
  api.registry.mockResolvedValue(LIST)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c1/dossiers?tab=phone-identities"]}>
        <PhoneIdentitiesTab caseId="c1" canEdit={canEdit} onOpenDossier={onOpen} />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return onOpen
}

describe("Phone identities", () => {
  beforeEach(() => vi.clearAllMocks())

  it("U-1: shows each phone's own name, never one merged name, and counts that open Conversations", async () => {
    tab()
    const row = (await screen.findByRole("button", { name: "+1 202 555 0143" })).closest("tr")!
    expect(within(row).getByText("C3: Maria L; C7: Mom")).toBeInTheDocument()
    expect(within(row).getByRole("link", { name: "C3: 9" })).toHaveAttribute("href", "/cases/c1/conversations?tab=people&people=phone%3A%2B1&phones=e3")
    expect(within(row).getByText("2023-03-13")).toBeInTheDocument()
    expect(within(screen.getByRole("table")).getByText("Not linked")).toBeInTheDocument()
    expect(screen.getByText("No phone gives a name")).toBeInTheDocument()
  })

  it("states the true total and pages through it", async () => {
    tab()
    expect(await screen.findByText(/Showing 1 to 2 of 120 identities, busiest first\./)).toBeInTheDocument()
    expect(screen.getByText(/7 of 300 in this case are linked to a person\./)).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole("button", { name: "Next" }))
    await waitFor(() => expect(api.registry).toHaveBeenLastCalledWith("c1", expect.objectContaining({ cursor: 50, limit: 50 })))
  })

  it("filters by phone and by link", async () => {
    const user = userEvent.setup()
    tab()
    await screen.findByRole("button", { name: "+1 202 555 0143" })
    await user.selectOptions(screen.getByLabelText("Phone"), "e7")
    await user.selectOptions(screen.getByLabelText("Linked to a person"), "no")
    await waitFor(() => expect(api.registry).toHaveBeenLastCalledWith("c1", expect.objectContaining({ phone: "e7", linked: false, cursor: 0 })))
  })

  it("opens the decision path for an identity and a person's dossier from the row, and keeps it in the URL", async () => {
    const user = userEvent.setup()
    const open = tab(false)
    await user.click(await screen.findByRole("button", { name: "+1 202 555 0143" }))
    expect(screen.getByText("Decision panel for phone:+1 (view only)")).toBeInTheDocument()
    expect(screen.getByTestId("where")).toHaveTextContent("identity=phone%3A%2B1")
    await user.click(screen.getByRole("button", { name: "Ana Synthetic" }))
    expect(open).toHaveBeenCalledWith("d1")
  })

  it("docks the suggestions, which stay suggestions until someone decides", async () => {
    const user = userEvent.setup()
    tab()
    await user.click(await screen.findByRole("button", { name: "People suggestions" }))
    expect(screen.getByText("Suggestion panel")).toBeInTheDocument()
  })

  it("says when the case has no phone", async () => {
    tab(true, vi.fn(), [])
    expect(await screen.findByText("No phone in this case")).toBeInTheDocument()
  })
})
