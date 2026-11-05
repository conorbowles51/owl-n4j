import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { IdentityDetail, IdentitySuggestion } from "./identities.api"

/** 07 J-7 from the graph's Add to Dossiers: link a phone identity to a person (02 8.8). Synthetic data. */
const api = vi.hoisted(() => ({ get: vi.fn(), suggestions: vi.fn(), decide: vi.fn() }))
const dossiers = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock("./identities.api", () => ({ identitiesAPI: api }))
vi.mock("@/features/dossiers/api", () => ({ dossiersAPI: dossiers }))

import { IdentityLinkGroup } from "./IdentityLinkGroup"

const KEY = "phone:+12025550143"
const DETAIL: IdentityDetail = {
  id: "i1", identity_key: KEY, kind: "phone", subkind: null, value_display: "+1 202-555-0143", sightings: 4, phones: 2,
  names: [{ phone: "C1", name: "Synthetic Ana", basis: "contact", occurrences: 3, is_phone_name: true }],
  linked_dossier: null, can_be_a_person: true, expected_revision: "rev-1",
}
const SUGGESTION: IdentitySuggestion = {
  id: "s1", score: 0.9, dossier_id: "d1", expected_revision: "rev-1",
  identities: [{ id: "i1", identity_key: KEY, kind: "phone", value_display: "+1 202-555-0143" }],
  reasons: [{ reason: "dossier_contact", weight: 0.9, records: [], record_count: 1, phones: [] }],
}

function panel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <IdentityLinkGroup caseId="case-1" identityKey={KEY} />
    </QueryClientProvider>
  )
}

describe("Link to a person", () => {
  beforeEach(() => {
    api.get.mockResolvedValue(DETAIL)
    api.suggestions.mockResolvedValue({ case_id: "case-1", total: 1, suggestions: [SUGGESTION] })
    api.decide.mockResolvedValue({ decisions: ["x"], dossier_id: "d1", revision: "rev-2" })
    dossiers.list.mockResolvedValue({ dossiers: [{ id: "d1", display_name: "Synthetic Person" }], total: 1, limit: 200, offset: 0 })
  })
  afterEach(() => vi.clearAllMocks())

  it("shows each phone's names and links a chosen suggestion with the standard reason it names", async () => {
    panel()
    await screen.findByText("+1 202-555-0143")
    expect(screen.getByText(/C1: Synthetic Ana \(the name this phone uses\)/)).toBeTruthy()
    fireEvent.click(await screen.findByRole("button", { name: "Choose" }))
    await screen.findByText(/standard reason: Linked on the review screen after seeing: a contact detail on this person's dossier\./)
    fireEvent.click(screen.getByRole("button", { name: "Link" }))
    await waitFor(() => expect(api.decide).toHaveBeenCalledWith("case-1", {
      decision: "link_phone_identity", identity_keys: [KEY], dossier_id: "d1",
      reasons_shown: [{ reason: "dossier_contact" }], origin: "review", note: undefined, expected_revision: "rev-1" }))
    await screen.findByText("Linked to Synthetic Person.")
  })

  it("from Dossiers the stored reason names Phone identities, not the review screen", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><IdentityLinkGroup caseId="case-1" identityKey={KEY} origin="dossier" /></QueryClientProvider>)
    fireEvent.click(await screen.findByRole("button", { name: "Choose" }))
    await screen.findByText(/standard reason: Linked on Phone identities in Dossiers after seeing: a contact detail on this person's dossier\./)
    fireEvent.click(screen.getByRole("button", { name: "Link" }))
    await waitFor(() => expect(api.decide).toHaveBeenCalledWith("case-1", expect.objectContaining({ origin: "dossier" })))
  })

  it("a new person needs a name, and with no suggestion shown the reason claims nothing seen", async () => {
    panel()
    const select = await screen.findByLabelText("Person")
    fireEvent.change(select, { target: { value: "new" } })
    const link = screen.getByRole("button", { name: "Link" })
    expect(link).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Name of the new person"), { target: { value: "Synthetic New" } })
    expect(link).toBeEnabled()
    fireEvent.click(link)
    await waitFor(() => expect(api.decide).toHaveBeenCalledWith("case-1", expect.objectContaining({
      decision: "link_phone_identity", new_person_name: "Synthetic New", reasons_shown: undefined })))
  })

  it("an identity already linked shows its person and Unlink waits for a reason", async () => {
    api.get.mockResolvedValue({ ...DETAIL, linked_dossier: { id: "d1", name: "Synthetic Person" } })
    panel()
    await screen.findByText("Linked to Synthetic Person.")
    const unlink = screen.getByRole("button", { name: "Unlink" })
    expect(unlink).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Your reason for unlinking/), { target: { value: "synthetic: wrong person" } })
    fireEvent.click(unlink)
    await waitFor(() => expect(api.decide).toHaveBeenCalledWith("case-1", expect.objectContaining({
      decision: "unlink_phone_identity", reason: "synthetic: wrong person" })))
  })

  it("a group cannot be linked to a person", async () => {
    api.get.mockResolvedValue({ ...DETAIL, kind: "other", subkind: "group", can_be_a_person: false })
    panel()
    await screen.findByText("This is a group, not a person, so it cannot be linked to one.")
    expect(screen.queryByRole("button", { name: "Link" })).toBeNull()
  })
})
