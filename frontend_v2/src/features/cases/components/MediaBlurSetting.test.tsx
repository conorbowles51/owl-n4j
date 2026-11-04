import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  getSettings: vi.fn(),
  putMediaBlur: vi.fn(),
}))
vi.mock("@/features/phones/api", () => api)
import { MediaBlurSetting } from "./MediaBlurSetting"

const settings = (media_blur: object) => ({ case_id: "c", time_zone: null, effective: { name: "UTC", basis: "default", note: null }, updated_at: null, updated_by: null, media_blur })

describe("Blur phone pictures (Case settings, 03 8.3)", () => {
  it("states the criminal-case default and sets the case default through the server", async () => {
    api.getSettings.mockResolvedValueOnce(settings({ default_on: true, basis: "criminal_case", words: "On by default in a criminal case.", set: null }))
      .mockResolvedValue(settings({ default_on: false, basis: "case_setting", words: "Set for this case by Synthetic.", set: false }))
    api.putMediaBlur.mockResolvedValue({})
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MediaBlurSetting caseId="c" /></QueryClientProvider>)
    expect(await screen.findByText(/Now: blurred by default. On by default in a criminal case./)).toBeInTheDocument()
    expect(screen.getByRole("radio", { name: /Follow the kind of case/ })).toBeChecked()
    fireEvent.click(screen.getByRole("radio", { name: "Do not blur pictures by default" }))
    await waitFor(() => expect(api.putMediaBlur).toHaveBeenCalledWith("c", false))
    expect(await screen.findByText(/Set for this case by Synthetic/)).toBeInTheDocument()
  })

  it("says plainly when the person cannot change it", async () => {
    const { ApiError } = await import("@/lib/api-client")
    api.getSettings.mockResolvedValue(settings({ default_on: false, basis: "not_criminal", words: "Off by default: this is not a criminal case.", set: null }))
    api.putMediaBlur.mockRejectedValue(new ApiError("Forbidden", 403))
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MediaBlurSetting caseId="c" /></QueryClientProvider>)
    fireEvent.click(await screen.findByRole("radio", { name: "Blur pictures for everyone by default" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("You can view this case but not change it.")
  })
})
