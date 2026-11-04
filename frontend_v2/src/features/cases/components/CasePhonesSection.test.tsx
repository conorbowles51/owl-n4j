import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CasePhonesSection } from "./CasePhonesSection"

const api = vi.hoisted(() => ({ getPhones: vi.fn(), getExternalProcessing: vi.fn(), setExternalProcessing: vi.fn() }))
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
