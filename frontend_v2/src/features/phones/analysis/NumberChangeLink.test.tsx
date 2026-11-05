import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

/** 05 16c.4: the row's identity-link action, through the existing decision. Invented data only. */
const api = vi.hoisted(() => ({ pair: vi.fn(), decide: vi.fn() }))
vi.mock("../review/identities.api", () => ({ identitiesAPI: api, errorWords: (e: Error) => e.message }))
vi.mock("@/features/dossiers/api", () => ({ dossiersAPI: { list: vi.fn().mockResolvedValue({ dossiers: [{ id: "d1", display_name: "Ana" }, { id: "d2", display_name: "Ben" }] }) } }))
import { NumberChangeLink } from "./NumberChangeLink"

const X = "phone:+12025550111", Y = "phone:+12025550122"
const item = (key: string, dossier: { id: string; name: string } | null = null) => ({ identity_key: key, value_display: key, linked_dossier: dossier, can_be_a_person: true })
function page(from = X, to = Y) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><NumberChangeLink caseId="c" from={from} to={to} fromDisplay="old number" toDisplay="new number" /></MemoryRouter>
    </QueryClientProvider>)
}
const open = () => userEvent.click(screen.getByRole("button", { name: "Link these two to one person…" }))

describe("Link these two to one person", () => {
  beforeEach(() => { api.pair.mockReset(); api.decide.mockReset().mockResolvedValue({ decisions: ["a", "b"] }) })

  it("records the decision on both sides with the number-change reason and the revision it read", async () => {
    api.pair.mockResolvedValue({ items: [item(X), item(Y)], expected_revision: "rev1" })
    page()
    await open()
    await userEvent.selectOptions(await screen.findByLabelText("Person"), await screen.findByRole("option", { name: "Ana" }))
    await userEvent.click(screen.getByRole("button", { name: "Link" }))
    await waitFor(() => expect(api.decide).toHaveBeenCalledWith("c", expect.objectContaining({
      decision: "link_phone_identity", identity_keys: [X, Y], dossier_id: "d1", reasons_shown: [{ reason: "number_change" }], origin: "number_switching", expected_revision: "rev1" })))
    expect(await screen.findByRole("status")).toHaveTextContent("Linked old number and new number to Ana.")
  })

  it("joins the free side to the person the other side already is, with no choice", async () => {
    api.pair.mockResolvedValue({ items: [item(X, { id: "d2", name: "Ben" }), item(Y)], expected_revision: "rev2" })
    page()
    await open()
    await screen.findByText("The other side is already Ben, so this joins it to them.")
    expect(screen.queryByLabelText("Person")).toBeNull()
    await userEvent.click(screen.getByRole("button", { name: "Link" }))
    await waitFor(() => expect(api.decide).toHaveBeenCalledWith("c", expect.objectContaining({ dossier_id: "d2" })))
  })

  it("refuses to move a link: two different people offers nothing", async () => {
    api.pair.mockResolvedValue({ items: [item(X, { id: "d1", name: "Ana" }), item(Y, { id: "d2", name: "Ben" })], expected_revision: "r" })
    page()
    await open()
    await screen.findByText(/already linked to different people: Ana and Ben/)
    expect(screen.queryByRole("button", { name: "Link" })).toBeNull()
  })

  it("takes a side that is already a reviewed person as that person", async () => {
    api.pair.mockResolvedValue({ items: [item(Y)], expected_revision: "r" })
    page("person:d1", Y)
    await open()
    await screen.findByText("The other side is already Ana, so this joins it to them.")
    await userEvent.click(screen.getByRole("button", { name: "Link" }))
    await waitFor(() => expect(api.decide).toHaveBeenCalledWith("c", expect.objectContaining({ identity_keys: [Y], dossier_id: "d1" })))
  })
})
