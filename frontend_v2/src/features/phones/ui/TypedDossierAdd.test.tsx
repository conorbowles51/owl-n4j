import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { CollectLink } from "../collect.api"

const api = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), add: vi.fn(), undo: vi.fn() }))
vi.mock("@/features/dossiers/api", () => ({ dossiersAPI: { list: api.list, create: api.create } }))
vi.mock("../collect.api", async (orig) => ({ ...(await orig<typeof import("../collect.api")>()), liveCollectClient: { add: api.add }, undoCollect: api.undo }))
import { TypedDossierAdd } from "./TypedDossierAdd"

/** 07 J-2 (device dossier), J-10 (address dossier), 6.1. Invented data only. */
const LINK: CollectLink = { target_type: "phone_extraction", target_id: "e1", label: "C1", source_anchor: { extraction_id: "e1" } }
function show(disabledReason?: string, type: "device" | "address" = "device") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TypedDossierAdd caseId="c1" type={type} link={LINK} suggestedName="C1" origin="Added from the Phone summary" disabledReason={disabledReason} />
    </QueryClientProvider>,
  )
}

describe("A device or address dossier", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.list.mockResolvedValue({ dossiers: [{ id: "d1", display_name: "Work phone" }], total: 1 })
    api.create.mockResolvedValue({ id: "d2", display_name: "C1" })
    api.add.mockResolvedValue({ added: 1, skipped: 0, refused: 0, linkIds: ["l1"] })
    api.undo.mockResolvedValue(1)
  })

  it("lists dossiers of that type and adds to one, with Undo that takes only the link", async () => {
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole("button", { name: "Add to a device dossier" }))
    await waitFor(() => expect(api.list).toHaveBeenCalledWith({ caseId: "c1", dossierType: "device", limit: 200 }))
    await user.selectOptions(await screen.findByLabelText("Device dossier"), await screen.findByRole("option", { name: "Work phone" }))
    await user.click(screen.getByRole("button", { name: "Add" }))
    expect(await screen.findByText(/Added 1 item to Work phone\./)).toBeInTheDocument()
    expect(api.create).not.toHaveBeenCalled()
    expect(api.add.mock.calls[0][2]).toEqual([LINK])
    await user.click(screen.getByRole("button", { name: "Undo" }))
    await waitFor(() => expect(screen.queryByText(/Added 1 item/)).not.toBeInTheDocument())
    expect(api.undo).toHaveBeenCalled()
  })

  it("makes a new dossier of the type under the typed name, and needs a name", async () => {
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole("button", { name: "Add to a device dossier" }))
    const name = await screen.findByLabelText("Name of the new dossier")
    await user.clear(name)
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled()
    await user.type(name, "Reported handset")
    await user.click(screen.getByRole("button", { name: "Add" }))
    await waitFor(() => expect(api.create).toHaveBeenCalledWith({ case_id: "c1", display_name: "Reported handset", dossier_type: "device" }))
  })

  it("offers the address type from the Map", async () => {
    const user = userEvent.setup()
    show(undefined, "address")
    await user.click(screen.getByRole("button", { name: "Add to an address dossier" }))
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ dossierType: "address" })))
  })

  it("is disabled with the reason when the person may not add", () => {
    show("A case member who can edit can add.")
    expect(screen.getByRole("button", { name: "Add to a device dossier" })).toBeDisabled()
    expect(screen.getByText("A case member who can edit can add.")).toBeInTheDocument()
  })
})
