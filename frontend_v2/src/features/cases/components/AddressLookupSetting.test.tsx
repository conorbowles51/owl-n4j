import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AddressLookupSetting } from "./AddressLookupSetting"

const getMode = vi.fn()
const setMode = vi.fn()
vi.mock("../api", () => ({
  casesAPI: {
    getAddressLookup: (...args: unknown[]) => getMode(...args),
    setAddressLookup: (...args: unknown[]) => setMode(...args),
  },
}))

function renderSetting(role: "owner" | "viewer" = "owner") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AddressLookupSetting caseData={{ id: "case-1", user_role: role, is_owner: role === "owner" }} />
    </QueryClientProvider>
  )
}

describe("AddressLookupSetting", () => {
  beforeEach(() => {
    getMode.mockReset()
    setMode.mockReset()
    getMode.mockResolvedValue({ mode: "auto", chosen: null, default_mode: "auto", words: "", waiting: 0 })
  })

  it("shows the mode in force and that the case follows the system default", async () => {
    renderSetting()
    const automatic = await screen.findByRole("radio", { name: /Automatic/ })
    expect(automatic).toBeChecked()
    expect(screen.getByText(/follows the system default/)).toBeInTheDocument()
    expect(screen.getByText(/outside this server/)).toBeInTheDocument()
  })

  it("lets the owner switch the case to looking up only on a click, and shows what is waiting", async () => {
    setMode.mockResolvedValue({ mode: "flag", chosen: "flag", default_mode: "auto", words: "", waiting: 3 })
    renderSetting()
    fireEvent.click(await screen.findByRole("radio", { name: /Only when a person clicks/ }))
    await waitFor(() => expect(setMode).toHaveBeenCalledWith("case-1", "flag"))
    await screen.findByText(/3 addresses are waiting in Needs review/)
    fireEvent.click(screen.getByRole("button", { name: "Use the system default" }))
    await waitFor(() => expect(setMode).toHaveBeenLastCalledWith("case-1", null))
  })

  it("is read-only for someone who is not the owner", async () => {
    renderSetting("viewer")
    expect(await screen.findByRole("radio", { name: /Automatic/ })).toBeDisabled()
    expect(screen.getByText(/Only the case's owner or an admin can change this/)).toBeInTheDocument()
  })
})
