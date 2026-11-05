import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import { SecurityPage } from "./SecurityPage"

const api = vi.hoisted(() => ({
  changePassword: vi.fn(),
  twoStepStatus: vi.fn(),
  twoStepStart: vi.fn(),
  twoStepConfirm: vi.fn(),
  twoStepNewRecoveryCodes: vi.fn(),
  twoStepTurnOff: vi.fn(),
}))
vi.mock("@/features/auth/api", () => ({ authAPI: api }))

const off = { enrolled: false, enrolled_at: null, recovery_codes_left: 0, unavailable_reason: null, required: false }

function page() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/settings/security"]}>
        <SecurityPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.twoStepStatus.mockResolvedValue(off)
})

it("changes the password, refusing two different new ones without asking the server", async () => {
  api.changePassword.mockRejectedValueOnce(new Error("Current password is incorrect"))
  api.changePassword.mockResolvedValueOnce(undefined)
  page()
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "old one" } })
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a long new password" } })
  fireEvent.change(screen.getByLabelText("New password again"), { target: { value: "different" } })
  fireEvent.click(screen.getByRole("button", { name: "Change password" }))
  expect((await screen.findByRole("alert")).textContent).toContain("different")
  expect(api.changePassword).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText("New password again"), { target: { value: "a long new password" } })
  fireEvent.click(screen.getByRole("button", { name: "Change password" }))
  expect((await screen.findByRole("alert")).textContent).toContain("incorrect")
  fireEvent.click(screen.getByRole("button", { name: "Change password" }))
  expect((await screen.findByRole("status")).textContent).toContain("Password changed")
  expect(api.changePassword).toHaveBeenLastCalledWith("old one", "a long new password")
  expect((screen.getByLabelText("Current password") as HTMLInputElement).value).toBe("")
})

it("says why nobody can enrol while the server has no key", async () => {
  api.twoStepStatus.mockResolvedValue({ ...off, unavailable_reason: "MFA_ENCRYPTION_KEY is not set" })
  page()
  await screen.findByText(/MFA_ENCRYPTION_KEY is not set/)
  expect(screen.queryByRole("button", { name: /Set up/ })).toBeNull()
})

it("enrols: password, QR code drawn from the rows, code, then recovery codes shown once", async () => {
  api.twoStepStart.mockResolvedValue({ secret: "JBSWY3DP", uri: "otpauth://x", qr: ["101", "010", "101"] })
  api.twoStepConfirm.mockResolvedValue({ recovery_codes: ["AAAA-BBBB-CCCC-DDDD", "EEEE-FFFF-GGGG-HHHH"] })
  page()
  fireEvent.click(await screen.findByRole("button", { name: "Set up two-step sign-in" }))
  fireEvent.change(screen.getByLabelText("Your password"), { target: { value: "my password" } })
  fireEvent.click(screen.getByRole("button", { name: "Continue" }))
  const qr = await screen.findByRole("img", { name: /QR code/ })
  expect(qr.querySelector("path")?.getAttribute("d")).toBe("M0 0h1v1h-1zM2 0h1v1h-1zM1 1h1v1h-1zM0 2h1v1h-1zM2 2h1v1h-1z")
  screen.getByText("JBSWY3DP")
  fireEvent.change(screen.getByLabelText("Code from your authenticator app"), { target: { value: "123456" } })
  fireEvent.click(screen.getByRole("button", { name: "Turn on" }))
  const codes = await screen.findByLabelText("Recovery codes")
  expect(codes.textContent).toContain("AAAA-BBBB-CCCC-DDDD")
  api.twoStepStatus.mockResolvedValue({ ...off, enrolled: true, recovery_codes_left: 2 })
  fireEvent.click(screen.getByRole("button", { name: "I have saved them" }))
  await waitFor(() => expect(screen.queryByLabelText("Recovery codes")).toBeNull())
  await screen.findByText("2")
})

it("hides turn off while administrators must keep it", async () => {
  api.twoStepStatus.mockResolvedValue({ ...off, enrolled: true, recovery_codes_left: 3, required: true })
  page()
  await screen.findByRole("button", { name: "New recovery codes" })
  expect(screen.queryByRole("button", { name: "Turn off" })).toBeNull()
})

it("needs password and code to make new recovery codes, and shows them", async () => {
  api.twoStepStatus.mockResolvedValue({ ...off, enrolled: true, recovery_codes_left: 3 })
  api.twoStepNewRecoveryCodes.mockResolvedValue({ recovery_codes: ["JJJJ-KKKK-MMMM-NNNN"] })
  page()
  fireEvent.click(await screen.findByRole("button", { name: "New recovery codes" }))
  fireEvent.change(screen.getByLabelText("Your password"), { target: { value: "my password" } })
  fireEvent.change(screen.getByLabelText("Code from your authenticator app"), { target: { value: "654321" } })
  fireEvent.click(screen.getByRole("button", { name: "Make new recovery codes" }))
  expect((await screen.findByLabelText("Recovery codes")).textContent).toContain("JJJJ-KKKK-MMMM-NNNN")
  expect(api.twoStepNewRecoveryCodes).toHaveBeenCalledWith("my password", "654321")
})
