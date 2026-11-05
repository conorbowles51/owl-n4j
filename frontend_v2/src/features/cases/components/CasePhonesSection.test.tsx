import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CasePhonesSection } from "./CasePhonesSection"

const api = vi.hoisted(() => ({ getPhones: vi.fn(), getExternalProcessing: vi.fn(), setExternalProcessing: vi.fn(), getSettings: vi.fn(),
  putSettings: vi.fn(), putCaseRegion: vi.fn(), putTowerReference: vi.fn() }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))

const show = (isSuperAdmin: boolean) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <CasePhonesSection caseId="c" isSuperAdmin={isSuperAdmin} />
      </MemoryRouter>
    </QueryClientProvider>,
  )

describe("Case settings, Phones (07 section 5)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getPhones.mockResolvedValue({ phones: [{ extraction_id: "e1", label: "C3" }] })
    api.getExternalProcessing.mockResolvedValue({ external_processing: false, decided_by: null, decided_at: null, reason: null })
    api.getSettings.mockResolvedValue({ case_id: "c", time_zone: null, effective: { name: "UTC", basis: "default", note: null }, updated_at: null, updated_by: null,
      default_region: { region: null, name: null, words: "Numbers written without + are read as US, assumed.", regions: [{ code: "IE", name: "Ireland" }, { code: "US", name: "United States" }] },
      cell_reference: { in_use: null, datasets: [{ id: "d1", name: "Synthetic towers", retrieved_on: "2026-01-01" }] } })
  })

  it("sets the case default country with a reason and says the phones are read again", async () => {
    api.putCaseRegion.mockResolvedValue({})
    show(false)
    expect(await screen.findByText(/Changing it reads those phones again/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Case default country"), { target: { value: "IE" } })
    const save = screen.getByRole("button", { name: "Save and read again" })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Reason, in your own words"), { target: { value: "Irish phones" } })
    fireEvent.click(save)
    await waitFor(() => expect(api.putCaseRegion).toHaveBeenCalledWith("c", "IE", "Irish phones"))
  })

  it("saves the case time zone", async () => {
    api.putSettings.mockResolvedValue({})
    show(false)
    fireEvent.change(await screen.findByLabelText("Case time zone"), { target: { value: "America/New_York" } })
    fireEvent.click(screen.getByRole("button", { name: "Save time zone" }))
    await waitFor(() => expect(api.putSettings).toHaveBeenCalledWith("c", "America/New_York"))
  })

  it("offers the tower reference to an administrator only", async () => {
    const first = show(false)
    expect(await screen.findByText(/Only an administrator can change this/)).toBeInTheDocument()
    expect(screen.queryByLabelText("Tower reference for this case")).toBeNull()
    first.unmount()
    api.putTowerReference.mockResolvedValue({})
    show(true)
    fireEvent.change(await screen.findByLabelText("Tower reference for this case"), { target: { value: "d1" } })
    fireEvent.change(screen.getByLabelText("Reason, in your own words"), { target: { value: "Licensed copy" } })
    fireEvent.click(screen.getByRole("button", { name: "Save and read again" }))
    await waitFor(() => expect(api.putTowerReference).toHaveBeenCalledWith("c", "d1", "Licensed copy"))
  })

  it("is absent in a case with no phone", async () => {
    api.getPhones.mockResolvedValue({ phones: [] })
    show(false)
    await waitFor(() => expect(api.getPhones).toHaveBeenCalled())
    expect(screen.queryByText("Phones")).toBeNull()
  })

  it("a person who is not the system owner sees the decision and why they cannot change it", async () => {
    show(false)
    expect(await screen.findByText(/Only the system owner can decide this/)).toBeInTheDocument()
    expect(await screen.findByText(/Not allowed\./)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Allow" })).toBeNull()
  })

  it("the system owner allows a phone with a reason", async () => {
    api.setExternalProcessing.mockResolvedValue({ external_processing: true, decided_by: "Owner", decided_at: null, reason: "needed" })
    show(true)
    fireEvent.click(await screen.findByRole("button", { name: "Allow" }))
    const form = within(await screen.findByRole("form", { name: "Outside services for C3" }))
    const go = form.getByRole("button", { name: "Allow for this phone" })
    expect(go).toBeDisabled()
    fireEvent.change(form.getByLabelText("Reason, in your own words"), { target: { value: "needed" } })
    fireEvent.click(go)
    await waitFor(() => expect(api.setExternalProcessing).toHaveBeenCalledWith("c", "e1", true, "needed"))
  })
})
