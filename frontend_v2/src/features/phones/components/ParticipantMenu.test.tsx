import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

const get = vi.hoisted(() => vi.fn())
vi.mock("../review/identities.api", () => ({ identitiesAPI: { get } }))
const copied = vi.hoisted(() => vi.fn(() => true))
vi.mock("@/lib/copy-text", () => ({ copyInGesture: copied }))

import { ParticipantMenu } from "./ParticipantMenu"
import type { ParticipantLabelData } from "../schemas"

const label = (key: string | null, display: string): ParticipantLabelData => ({
  identity_key: key, name: "Ana S", name_basis: "contact_on_this_phone", is_owner: false, owner_basis: null, case_names: [],
  identifier: { kind: "phone", subkind: null, display, normalised: true, captured: display } as ParticipantLabelData["identifier"],
})
const A = label("phone:+12025550143", "+1 202 555 0143"), B = label("phone:+12025550188", "+1 202 555 0188")

function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname}{l.search}</p>
}

function page(me: ParticipantLabelData = A) {
  render(
    <MemoryRouter initialEntries={["/cases/c/start"]}>
      <Routes><Route path="*" element={<><ParticipantMenu caseId="c" label={me} parties={{ from: A, to: [B] }} /><Where /></>} /></Routes>
    </MemoryRouter>)
}
const open = async () => userEvent.click(screen.getByRole("button", { name: /Actions for/ }))

describe("the participant menu on a stream row", () => {
  it("offers the four actions", async () => {
    page()
    await open()
    for (const name of ["Show all with this person", "Show this pair", "Open in People", "Copy name and number"]) expect(await screen.findByRole("menuitem", { name })).toBeTruthy()
  })

  it("lands Show all on the person", async () => {
    page()
    await open()
    await userEvent.click(await screen.findByRole("menuitem", { name: "Show all with this person" }))
    expect(screen.getByTestId("where").textContent).toBe("/cases/c/conversations?tab=people&people=phone%3A%2B12025550143")
  })

  it("lands Show this pair on both, between them", async () => {
    page(B)
    await open()
    await userEvent.click(await screen.findByRole("menuitem", { name: "Show this pair" }))
    expect(screen.getByTestId("where").textContent).toBe("/cases/c/conversations?tab=people&people=phone%3A%2B12025550188%2Cphone%3A%2B12025550143&mode=between")
  })

  it("lands Open in People on the linked person's dossier", async () => {
    get.mockResolvedValue({ linked_dossier: { id: "d1", name: "Ana" } })
    page()
    await open()
    await userEvent.click(await screen.findByRole("menuitem", { name: "Open in People" }))
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/cases/c/dossiers?dossier=d1"))
  })

  it("copies the row's own words for the person", async () => {
    page()
    await open()
    await userEvent.click(await screen.findByRole("menuitem", { name: "Copy name and number" }))
    expect(copied).toHaveBeenCalledWith({ text: "Ana S (+1 202 555 0143)" })
    expect((await screen.findByRole("status")).textContent).toBe("Copied.")
  })
})
