import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { DossierPhones } from "@/features/phones/people.api"

const api = vi.hoisted(() => ({ dossierPhones: vi.fn(), decide: vi.fn() }))
vi.mock("@/features/phones/people.api", async (orig) => ({
  ...(await orig<typeof import("@/features/phones/people.api")>()),
  peopleAPI: { dossierPhones: api.dossierPhones },
}))
vi.mock("@/features/phones/review/identities.api", async (orig) => ({
  ...(await orig<typeof import("@/features/phones/review/identities.api")>()),
  identitiesAPI: { decide: api.decide },
}))
import { countHref } from "@/features/phones/people.api"
import { OnThePhonesPanel } from "./OnThePhonesPanel"

/** 03 10.2, 10.5 U-4, U-7, U-8; 07 XF-5. Invented data only. */
const C1 = "/cases/c1/conversations?tab=people&people=phone%3A%2B1&phones=e1"
const DATA: DossierPhones = {
  case_id: "c1",
  dossier: { id: "d1", name: "Ana Synthetic", type: "person" },
  identities: [
    { identity_key: "phone:+1", kind: "phone", value_display: "+1 202 555 0143", events: 4, phones: 2, conversations_href: "/cases/c1/conversations?tab=people&people=phone%3A%2B1" },
    { identity_key: "email:a", kind: "email", value_display: "ana@synthetic.test", events: 1, phones: 1, conversations_href: "/cases/c1/conversations?tab=people&people=email%3Aa" },
  ],
  phones: [
    { extraction_id: "e1", label: "C1", names: [{ name: "Maria L", value_display: "+1 202 555 0143", basis: "contact", contact_created: "2023-01-02T00:00:00Z", contact_modified: "2023-02-03T00:00:00Z" }],
      total: 4, first_contact: "2023-03-13T09:00:00Z", last_contact: "2023-03-14T10:00:00Z",
      kinds: [{ kind: "message", directions: [{ direction: "incoming", events: 3 }, { direction: "outgoing", events: 1 }] }], conversations_href: C1 },
    { extraction_id: "e2", label: "C2", names: [], total: 1, first_contact: "2023-03-20T09:00:00Z", last_contact: "2023-03-20T09:00:00Z",
      kinds: [{ kind: "call", directions: [{ direction: "incoming", events: 1 }] }], conversations_href: "/cases/c1/conversations?tab=people&people=x&phones=e2" },
  ],
  total: 5,
  conversations_href: "/cases/c1/conversations?tab=people&people=phone%3A%2B1,email%3Aa",
  suggested_identities: 2,
  review_href: "/cases/c1/phone-review",
  phones_in_case: 14,
  history: [
    { id: "h1", decision: "unlink_phone_identity", reason: "A different Ana", reason_kind: "typed", actor: "Jane Reviewer", at: "2023-04-01T10:00:00Z", identity_key: "phone:+9", value_display: "+1 202 555 0199" },
    { id: "h2", decision: "reject_phone_identity_link", reason: "Not her", reason_kind: "typed", actor: "Jane Reviewer", at: "2023-04-01T09:00:00Z", identity_key: "phone:+8", value_display: "+1 202 555 0198" },
  ],
  history_total: 2,
  expected_revision: "r1",
}

function panel(canEdit = true, data: DossierPhones = DATA) {
  api.dossierPhones.mockResolvedValue(data)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <OnThePhonesPanel caseId="c1" dossierId="d1" canEdit={canEdit} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("On the phones", () => {
  beforeEach(() => vi.clearAllMocks())

  it("opens every count to its records, and states the phones out of the case's", async () => {
    panel()
    const total = await screen.findByRole("link", { name: "5 messages and calls with Ana Synthetic" })
    expect(total).toHaveAttribute("href", DATA.conversations_href)
    expect(screen.getByText(/on 2 of 14 phones/)).toBeInTheDocument()
    const c1 = screen.getByRole("article", { name: "On C1" })
    expect(within(c1).getByRole("link", { name: "Open conversations (4)" })).toHaveAttribute("href", C1)
    expect(within(c1).getByRole("link", { name: "3 messages in" })).toHaveAttribute("href", countHref(C1, "message", "incoming"))
    expect(screen.getByRole("link", { name: /4 messages and calls on 2 phones/ })).toHaveAttribute("href", DATA.identities[0].conversations_href)
    expect(within(c1).getByText(/Maria L .*contact created 2023-01-02, changed 2023-02-03/)).toBeInTheDocument()
  })

  it("keeps a suggestion apart from the links", async () => {
    panel()
    expect(await screen.findByText(/Suggested, not reviewed: 2 more identities may be Ana Synthetic\. None is counted here\./)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Review the suggestions" })).toHaveAttribute("href", "/cases/c1/phone-review?panel=people")
  })

  it("U-8: Unlink previews its effect, refuses a blank reason and sends the typed one", async () => {
    api.decide.mockResolvedValue({ decisions: ["x"], dossier_id: null, revision: "r2" })
    const user = userEvent.setup()
    panel()
    await user.click(await screen.findByRole("checkbox", { name: /Choose \+1 202 555 0143/ }))
    await user.click(screen.getByRole("button", { name: "Unlink" }))
    const preview = screen.getByRole("group", { name: "Unlink preview" })
    expect(preview).toHaveTextContent("their 4 messages and calls leave this panel")
    const confirm = within(preview).getByRole("button", { name: "Confirm" })
    expect(confirm).toBeDisabled()
    await user.type(within(preview).getByLabelText(/Your reason/), "Wrong person")
    await user.click(confirm)
    expect(api.decide).toHaveBeenCalledWith("c1", { decision: "unlink_phone_identity", identity_keys: ["phone:+1"], reason: "Wrong person" })
  })

  it("Split takes several identities out in one decision", async () => {
    api.decide.mockResolvedValue({ decisions: ["x", "y"], dossier_id: null, revision: "r2" })
    const user = userEvent.setup()
    panel()
    await user.click(await screen.findByRole("checkbox", { name: /Choose \+1 202 555 0143/ }))
    await user.click(screen.getByRole("checkbox", { name: /Choose ana@synthetic/ }))
    await user.click(screen.getByRole("button", { name: "Split 2 out of Ana Synthetic" }))
    await user.type(screen.getByLabelText(/Your reason/), "Two people")
    await user.click(screen.getByRole("button", { name: "Confirm" }))
    expect(api.decide).toHaveBeenCalledWith("c1", { decision: "split", identity_keys: ["phone:+1", "email:a"], reason: "Two people" })
  })

  it("reverses a decision from the history, under the person's name in the record", async () => {
    api.decide.mockResolvedValue({ decisions: ["x"], dossier_id: "d1", revision: "r2" })
    const user = userEvent.setup()
    panel()
    await user.click(await screen.findByText("Link decisions (2)"))
    expect(screen.getByText(/Unlinked: \+1 202 555 0199 by Jane Reviewer, 2023-04-01\. A different Ana/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Link again" }))
    expect(api.decide).toHaveBeenLastCalledWith("c1", expect.objectContaining({ decision: "link_phone_identity", identity_keys: ["phone:+9"], dossier_id: "d1" }))
    await user.click(screen.getByRole("button", { name: "Restore" }))
    expect(api.decide).toHaveBeenLastCalledWith("c1", expect.objectContaining({ decision: "restore_phone_identity_link", identity_keys: ["phone:+8"], dossier_id: "d1" }))
  })

  it("U-7: without permission the controls are disabled with the reason", async () => {
    panel(false)
    expect(await screen.findByRole("checkbox", { name: /Choose \+1 202 555 0143/ })).toBeDisabled()
    expect(screen.getByText("A case admin can change links.")).toBeInTheDocument()
    await userEvent.setup().click(screen.getByText("Link decisions (2)"))
    expect(screen.queryByRole("button", { name: "Link again" })).not.toBeInTheDocument()
  })

  it("says so when nothing is linked yet", async () => {
    panel(true, { ...DATA, identities: [], phones: [], total: 0, conversations_href: null, suggested_identities: 0, history: [], history_total: 0 })
    expect(await screen.findByText(/No phone number, address or account on the phones is linked to Ana Synthetic yet/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Link one in Phone identities" })).toHaveAttribute("href", "/cases/c1/dossiers?tab=phone-identities")
  })
})
